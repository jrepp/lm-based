from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from lm_launcher import taxdesk_broker as tb

ROOT = Path(__file__).resolve().parents[1]

# A stand-in for the real taxdesk-docs: same argv conventions, JSON on stdout, no network.
FAKE_CLI = r'''#!{python}
import json, os, sys
argv = sys.argv[1:]
cmd = argv[0] if argv else "help"
flags, pos, i = {}, [], 1
while i < len(argv):
    a = argv[i]
    if a.startswith("--"):
        if a == "--stdin": flags["stdin"] = True
        else: flags[a[2:]] = argv[i + 1]; i += 1
    else: pos.append(a)
    i += 1
if cmd == "manifest":
    names = ["manifest", "whoami", "context", "list", "next", "get", "text", "propose", "tables",
             "table", "overlay", "suggest", "report", "txns", "login", "logout", "frobnicate"]
    print(json.dumps({"commands": [{"name": n} for n in names]})); sys.exit(0)
if cmd == "whoami":
    print(json.dumps({"error": "No credential.", "exit": 3})); sys.exit(3)
if cmd == "env":
    print(json.dumps(sorted(os.environ))); sys.exit(0)
if cmd == "get":
    os.makedirs(flags["out"], exist_ok=True)
    path = os.path.join(os.path.abspath(flags["out"]), pos[0] + ".pdf")
    open(path, "wb").write(b"%PDF-fake")
    print(json.dumps({"id": pos[0], "path": path, "bytes": 9})); sys.exit(0)
if cmd == "table":
    path = os.path.abspath(flags["out"])
    open(path, "w").write('{"row":"r1","category":"uncat"}\n')
    print(json.dumps({"path": path, "rows": 1})); sys.exit(0)
if cmd == "propose":
    print(json.dumps({"argv": argv, "stdin": sys.stdin.read()})); sys.exit(0)
print(json.dumps({"argv": argv})); sys.exit(0)
'''


class ParseCallTests(unittest.TestCase):
    def test_accepts_allowlisted_shapes(self) -> None:
        call = tb.parse_call(["list", "--year=2025", "--state", "unread"])
        self.assertEqual(call.argv, ("list", "--year", "2025", "--state", "unread"))
        call = tb.parse_call(["table", "batch", "42", "--out", "/sandbox/ws/rows.ndjson"])
        self.assertEqual(call.argv, ("table", "batch", "42"))
        self.assertEqual(call.outputs, {"out": ("file", "/sandbox/ws/rows.ndjson")})
        call = tb.parse_call(["suggest", "dataset", "7", "--model", "qwen36", "--stdin"])
        self.assertTrue(call.stdin)
        self.assertEqual(call.argv[-1], "--stdin")

    def test_refuses_everything_else(self) -> None:
        refused = [
            ["login"],
            ["logout", "--url", "https://x"],
            ["frobnicate"],
            ["whoami", "--url", "https://evil.example"],
            ["manifest", "--help"],
            ["list", "--year", "20255"],
            ["list", "--year", "2025", "--year", "2024"],
            ["list", "--state", "everything"],
            ["get", "../../etc", "--out", "/sandbox/x"],
            ["get", "-rf"],
            ["get", "12", "13"],
            ["get", "12", "--out", "relative/dir"],
            ["propose", "12", "--body", "/sandbox/p.json"],
            ["context", "--year", "2025", "--stdin"],
            ["text", "12", "--wait", "9999"],
            ["table", "users", "1"],
            ["txns", "--year", "2025", "--account", "1; rm -rf /"],
            ["next", "--year", "2025", "--model"],
            [],
            "whoami",
            ["whoami", 3],
        ]
        for argv in refused:
            with self.subTest(argv=argv), self.assertRaises(tb.BrokerRequestError):
                tb.parse_call(argv)  # type: ignore[arg-type]

    def test_manifest_restricts_allowlist(self) -> None:
        with self.assertRaises(tb.BrokerRequestError):
            tb.parse_call(["report", "--year", "2025"], frozenset({"whoami"}))


class BrokerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="broker-test-"))
        self.cli = self.tmp / "taxdesk-docs"
        self.cli.write_text(FAKE_CLI.replace("{python}", sys.executable))
        self.cli.chmod(0o755)
        self.log = self.tmp / "broker.log"
        env = {"HOME": str(self.tmp), "USER": "tester", "AWS_SECRET_ACCESS_KEY": "nope", "TAXDESK_URL": "https://td.test"}
        self.broker = tb.Broker(self.cli, token="tok", log_path=self.log, env=env)
        self.warnings = self.broker.load_manifest()
        self.server = tb.BrokerServer(self.broker).start()
        self.url = f"http://127.0.0.1:{self.server.port}"

    def tearDown(self) -> None:
        self.server.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def post(self, body: object, token: str = "tok") -> tuple[int, dict]:
        request = urllib.request.Request(
            f"{self.url}/v1/run",
            data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            with error:
                return error.code, json.load(error)

    def test_manifest_warns_about_unknown_commands(self) -> None:
        self.assertTrue(any("frobnicate" in warning for warning in self.warnings))
        self.assertNotIn("frobnicate", self.broker.allowed)
        self.assertNotIn("login", self.broker.allowed)

    def test_token_is_required(self) -> None:
        status, body = self.post({"argv": ["manifest"]}, token="wrong")
        self.assertEqual(status, 401)
        self.assertEqual(body["exit"], 3)

    def test_exit_codes_and_stdout_pass_through(self) -> None:
        status, body = self.post({"argv": ["whoami"]})
        self.assertEqual(status, 200)
        self.assertEqual(body["exit"], 3)
        self.assertEqual(json.loads(body["stdout"])["error"], "No credential.")

    def test_get_streams_file_back_under_sandbox_path(self) -> None:
        status, body = self.post({"argv": ["get", "12", "--out", "/sandbox/ws/files"]})
        self.assertEqual((status, body["exit"]), (200, 0))
        self.assertEqual(json.loads(body["stdout"])["path"], "/sandbox/ws/files/12.pdf")
        self.assertEqual(body["files"], [{"path": "/sandbox/ws/files/12.pdf", "data": base64.b64encode(b"%PDF-fake").decode()}])
        self.assertNotIn(str(self.tmp), json.dumps(body))
        self.assertNotIn("taxdesk-broker-", json.dumps(body))

    def test_table_out_file(self) -> None:
        _, body = self.post({"argv": ["table", "batch", "3", "--out=/sandbox/ws/rows.ndjson"]})
        self.assertEqual(json.loads(body["stdout"])["path"], "/sandbox/ws/rows.ndjson")
        self.assertEqual(base64.b64decode(body["files"][0]["data"]), b'{"row":"r1","category":"uncat"}\n')

    def test_stdin_only_for_commands_that_read_it(self) -> None:
        payload = base64.b64encode(b'{"kind":"receipt"}').decode()
        _, body = self.post({"argv": ["propose", "12", "--model", "qwen", "--stdin"], "stdin": payload})
        self.assertEqual(json.loads(body["stdout"])["stdin"], '{"kind":"receipt"}')
        status, body = self.post({"argv": ["list", "--year", "2025"], "stdin": payload})
        self.assertEqual((status, body["exit"]), (400, 2))

    def test_child_sees_minimal_environment(self) -> None:
        env = tb.child_environment({"HOME": "/h", "AWS_SECRET_ACCESS_KEY": "x", "TAXDESK_CA": "/ca.pem"}, Path("/t"))
        self.assertEqual(env, {"HOME": "/h", "TAXDESK_CA": "/ca.pem", "PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "TMPDIR": "/t"})

    def test_refusals_are_400_and_log_holds_only_names_and_exits(self) -> None:
        status, body = self.post({"argv": ["login"]})
        self.assertEqual((status, body["exit"]), (400, 2))
        self.post({"argv": ["list", "--year", "2025", "--state", "unread"]})
        entries = [json.loads(line) for line in self.log.read_text().splitlines()]
        self.assertEqual([(e["command"], e["exit"]) for e in entries], [("refused", 2), ("list", 0)])
        self.assertNotIn("2025", self.log.read_text())
        self.assertEqual(self.log.stat().st_mode & 0o777, 0o600)

    @unittest.skipUnless(shutil.which("node"), "node is needed for the in-sandbox shim")
    def test_shim_end_to_end(self) -> None:
        config = tb.write_shim_config(self.tmp / "shim" / "broker.json", self.url, "tok")
        self.assertEqual(config.stat().st_mode & 0o777, 0o600)
        work = self.tmp / "ws"
        work.mkdir()
        env = {"PATH": os.environ["PATH"], "TAXDESK_BROKER_CONFIG": str(config)}
        shim = ROOT / "support" / "pi" / "sandbox" / "bin" / "taxdesk-docs"
        result = subprocess.run([str(shim), "get", "77", "--out", "dl"], cwd=work, env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((work / "dl" / "77.pdf").read_bytes(), b"%PDF-fake")
        self.assertEqual(json.loads(result.stdout)["path"], str((work / "dl" / "77.pdf").resolve()))
        refused = subprocess.run([str(shim), "logout"], cwd=work, env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(refused.returncode, 2)
        self.assertIn("person", json.loads(refused.stdout)["error"])


class FindBinaryTests(unittest.TestCase):
    def test_explicit_then_path_then_workspace_dist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binary = root / "dist" / "taxdesk-docs"
            binary.parent.mkdir()
            binary.write_text("#!/bin/sh\n")
            binary.chmod(0o755)
            self.assertEqual(tb.find_binary({"PATH": "/nonexistent"}, root), binary.resolve())
            self.assertEqual(tb.find_binary({"PATH": str(binary.parent)}, Path("/")), binary.resolve())
            self.assertEqual(tb.find_binary({"TAXDESK_DOCS_BIN": str(binary)}, Path("/")), binary.resolve())
            self.assertIsNone(tb.find_binary({"TAXDESK_DOCS_BIN": str(root / "missing")}, root))
            self.assertIsNone(tb.find_binary({"PATH": "/nonexistent"}, Path("/")))


if __name__ == "__main__":
    unittest.main()
