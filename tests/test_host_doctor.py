from __future__ import annotations

import json
import struct
import subprocess
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from lm_launcher import host_doctor
from lm_launcher.gguf_metadata import context_length, read_metadata


def gguf_bytes(kv: list[tuple[str, int, bytes]]) -> bytes:
    def string(text: str) -> bytes:
        data = text.encode()
        return struct.pack("<Q", len(data)) + data

    out = b"GGUF" + struct.pack("<I", 3) + struct.pack("<Q", 0) + struct.pack("<Q", len(kv))
    for key, value_type, payload in kv:
        out += string(key) + struct.pack("<I", value_type) + payload
    return out


def string_value(text: str) -> bytes:
    data = text.encode()
    return struct.pack("<Q", len(data)) + data


class GgufMetadataTests(unittest.TestCase):
    def test_reads_context_length_and_skips_arrays(self) -> None:
        tokens = struct.pack("<I", 8) + struct.pack("<Q", 2) + string_value("a") + string_value("bb")
        floats = struct.pack("<I", 6) + struct.pack("<Q", 3) + struct.pack("<3f", 1, 2, 3)
        data = gguf_bytes(
            [
                ("general.architecture", 8, string_value("qwen3next")),
                ("tokenizer.ggml.tokens", 9, tokens),
                ("tokenizer.ggml.scores", 9, floats),
                ("qwen3next.context_length", 4, struct.pack("<I", 262144)),
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.gguf"
            path.write_bytes(data)
            self.assertEqual(context_length(path), 262144)
            meta = read_metadata(path)
            self.assertNotIn("tokenizer.ggml.tokens", meta)
            self.assertEqual(meta["general.architecture"], "qwen3next")

    def test_rejects_non_gguf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.gguf"
            path.write_bytes(b"NOPE")
            with self.assertRaises(ValueError):
                read_metadata(path)


PS = """\
  100     1 /opt/homebrew/bin/llama-swap --config llama-swap.yaml --listen 127.0.0.1:8081
  101   100 sh -c MODEL_SLUG=a ./run-server.py
  102   101 llama-server --model /m/Qwen3-Coder-Next-Q6_K-00001-of-00003.gguf --port 10004
  200     1 /usr/bin/python3 /repo/lm_launcher/kev_serve_local.py --port 18001
  300     1 /usr/bin/python3 -m http.server 9000
"""
LSOF = """\
COMMAND     PID  USER   FD   TYPE             DEVICE SIZE/OFF NODE NAME
llama-swa   100 jrepp    8u  IPv4 0x1      0t0  TCP 127.0.0.1:8081 (LISTEN)
llama-ser   102 jrepp    3u  IPv4 0x2      0t0  TCP 127.0.0.1:10004 (LISTEN)
Python      200 jrepp   11u  IPv4 0x3      0t0  TCP 127.0.0.1:18001 (LISTEN)
Python      300 jrepp    3u  IPv4 0x4      0t0  TCP *:9000 (LISTEN)
"""


class HostDoctorTests(unittest.TestCase):
    def test_classifies_model_servers_by_llama_swap_ancestry(self) -> None:
        servers = host_doctor.model_servers(host_doctor.parse_ps(PS), host_doctor.parse_lsof_listen(LSOF))
        self.assertEqual([(s.pid, s.ports, s.under_llama_swap) for s in servers], [
            (102, (10004,), True),
            (200, (18001,), False),
        ])

    def test_parses_memory_figures(self) -> None:
        self.assertEqual(
            host_doctor.parse_wired_bytes("Mach Virtual Memory Statistics: (page size of 16384 bytes)\nPages wired down:   10.\n"),
            163840,
        )
        self.assertEqual(host_doctor.parse_footprint_bytes("    phys_footprint: 5867 MB\n"), 5867 * 1024**2)
        self.assertEqual(host_doctor.wired_limit_bytes(0, 128 * 1024**3), 96 * 1024**3)
        self.assertEqual(host_doctor.wired_limit_bytes(100_000, 128 * 1024**3), 100_000 * 1024**2)

    def test_short_command_names_the_script_and_model(self) -> None:
        self.assertEqual(
            host_doctor.short_command("llama-server --model /m/GLM-OCR-Q8_0.gguf --port 1"), "llama-server GLM-OCR-Q8_0.gguf"
        )
        self.assertTrue(host_doctor.short_command("/usr/bin/python3 /r/kev_serve_local.py --port 1").startswith("kev_serve_local.py"))

    def test_run_flags_orphans_and_wired_pressure(self) -> None:
        outputs = {
            "ps": PS,
            "lsof": LSOF,
            "sysctl": "0\n137438953472\n",
            "footprint": "    phys_footprint: 100 MB\n",
            "vm_stat": "(page size of 16384 bytes)\nPages wired down:   6000000.\n",  # ~91.6 GiB
        }

        def runner(args, **_kwargs):
            return subprocess.CompletedProcess(args, 0, stdout=outputs[args[0]], stderr="")

        with unittest.mock.patch.object(host_doctor, "sidecar_context_mismatches", return_value=[]):
            with unittest.mock.patch("builtins.print"):
                self.assertEqual(host_doctor.run(runner), 1)

    def test_sidecar_context_must_match_gguf_header(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "models").mkdir()
            (root / "artifacts").mkdir()
            (root / "artifacts" / "m.gguf").write_bytes(
                gguf_bytes([
                    ("general.architecture", 8, string_value("llama")),
                    ("llama.context_length", 4, struct.pack("<I", 32768)),
                ])
            )
            sidecar = {"artifact": {"local_path": "m.gguf", "format": "gguf"}, "model": {"context_length": 262144}}
            (root / "models" / "m.gguf.json").write_text(json.dumps(sidecar))
            problems = host_doctor.sidecar_context_mismatches(root / "models", root / "artifacts")
            self.assertEqual(problems, ["m.gguf.json: model.context_length 262144, GGUF header says 32768"])


if __name__ == "__main__":
    unittest.main()
