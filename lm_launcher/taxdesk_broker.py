"""Host-side broker that runs the Tax Desk docs CLI on behalf of a sandboxed Pi.

`taxdesk-docs` is a macOS binary that reads its automation credential from the
login Keychain and calls the Tax Desk server over HTTPS. Neither works inside the
OpenShell microVM (Linux, default-deny egress), so `pi-local --sandbox` starts
this broker on the host. The VM reaches it only at the sandbox gateway address,
the same way it reaches llama-swap, and an in-sandbox shim
(`support/pi/sandbox/taxdesk-docs.ts`) makes the agent's `taxdesk-docs ...`
calls look local.

What the broker guarantees:

- Only allowlisted subcommands, each with its own flags and positional
  patterns, run (and only those the host binary's `manifest` also lists).
  `login`, `logout`, `--url` and `--help` never run.
- The binary runs with a minimal environment: no host env beyond HOME/USER/PATH
  and the host's own TAXDESK_URL / TAXDESK_CA. The VM cannot set either.
- File outputs (`--out`) are redirected into a private per-call directory on the
  host and their bytes streamed back for the shim to write inside the VM.
- `--body <file>` is not accepted; the shim reads the file in the VM and sends it
  as stdin with `--stdin`.
- Every request needs the per-launch bearer token the shim reads from its config
  file, so other local processes and web pages cannot drive the broker.
- The log holds command names, exit codes and durations only, never arguments,
  stdin, or output.
"""

from __future__ import annotations

import base64
import hmac
import json
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

PROTOCOL = "taxdesk-broker/1"
MAX_REQUEST_BYTES = 24 * 1024 * 1024  # JSON envelope around at most MAX_STDIN_BYTES of base64
MAX_STDIN_BYTES = 16 * 1024 * 1024
MAX_STDOUT_BYTES = 64 * 1024 * 1024
MAX_STDERR_BYTES = 64 * 1024
MAX_FILE_BYTES = 128 * 1024 * 1024  # all files of one call together
MAX_ARGS = 32
MAX_ARG_CHARS = 1024
CALL_TIMEOUT_S = 600
MAX_CONCURRENT_CALLS = 4

# Value validators. Each takes the raw string from the VM and returns it unchanged or raises.
YEAR = re.compile(r"(?:19|20)\d{2}")
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")
MODEL_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
DIGITS = re.compile(r"\d{1,12}")
CATEGORY = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.:-]{0,63}")


class BrokerRequestError(ValueError):
    """A request the broker refuses; reported to the shim as a usage error (exit 2)."""


@dataclass(frozen=True)
class Value:
    pattern: re.Pattern[str] | None = None
    choices: tuple[str, ...] = ()
    int_range: tuple[int, int] | None = None
    # "file" / "dir": an output path in the VM. The broker substitutes a private host path.
    output: str | None = None

    def check(self, name: str, value: str) -> None:
        if self.output:
            if not value.startswith("/") or "\0" in value or len(value) > MAX_ARG_CHARS or any(ord(c) < 32 for c in value):
                raise BrokerRequestError(f"--{name} must be an absolute sandbox path (the shim resolves it)")
            return
        if self.choices and value not in self.choices:
            raise BrokerRequestError(f"--{name} must be one of {', '.join(self.choices)}")
        if self.pattern is not None and not self.pattern.fullmatch(value):
            raise BrokerRequestError(f"--{name} has an invalid value")
        if self.int_range is not None:
            if not DIGITS.fullmatch(value) or not self.int_range[0] <= int(value) <= self.int_range[1]:
                raise BrokerRequestError(f"--{name} must be an integer {self.int_range[0]}..{self.int_range[1]}")


KIND = Value(choices=("batch", "dataset"))


@dataclass(frozen=True)
class Command:
    positionals: tuple[Value, ...] = ()
    flags: dict[str, Value] = field(default_factory=dict)
    stdin: bool = False  # accepts --stdin and a request body


# The commands a sandboxed agent may run. Mirrors `taxdesk-docs manifest`; `login` and
# `logout` are deliberately absent (they are for a person in their own terminal).
COMMANDS: dict[str, Command] = {
    "manifest": Command(),
    "whoami": Command(),
    "context": Command(flags={"year": Value(YEAR)}),
    "list": Command(flags={"year": Value(YEAR), "state": Value(choices=("unread", "proposed", "decided", "all"))}),
    "next": Command(flags={"year": Value(YEAR), "model": Value(MODEL_NAME)}),
    "get": Command(positionals=(Value(ID),), flags={"out": Value(output="dir")}),
    "text": Command(positionals=(Value(ID),), flags={"wait": Value(int_range=(0, 300))}),
    "propose": Command(positionals=(Value(ID),), flags={"model": Value(MODEL_NAME)}, stdin=True),
    "tables": Command(flags={"year": Value(YEAR)}),
    "table": Command(positionals=(KIND, Value(ID)), flags={"out": Value(output="file")}),
    "overlay": Command(positionals=(KIND, Value(ID)), stdin=True),
    "suggest": Command(positionals=(KIND, Value(ID)), flags={"model": Value(MODEL_NAME)}, stdin=True),
    "report": Command(flags={"year": Value(YEAR), "out": Value(output="file")}),
    "txns": Command(
        flags={
            "year": Value(YEAR),
            "account": Value(DIGITS),
            "category": Value(CATEGORY),
            "out": Value(output="file"),
        }
    ),
}
NEVER = frozenset({"login", "logout"})
# Host configuration the binary may see. The VM cannot supply these.
PASSTHROUGH_ENV = ("HOME", "USER", "LOGNAME", "LANG", "TAXDESK_URL", "TAXDESK_CA")


@dataclass(frozen=True)
class ParsedCall:
    command: str
    argv: tuple[str, ...]  # validated, normalized (--flag value) argv for the binary, outputs not yet substituted
    outputs: dict[str, tuple[str, str]]  # flag -> (kind "file"|"dir", sandbox path)
    stdin: bool


def parse_call(argv: list[Any], allowed: frozenset[str] | None = None) -> ParsedCall:
    """Validate one CLI invocation from the sandbox against the allowlist."""
    if not isinstance(argv, list) or not argv or len(argv) > MAX_ARGS:
        raise BrokerRequestError(f"argv must be a list of 1..{MAX_ARGS} strings")
    for item in argv:
        if not isinstance(item, str) or len(item) > MAX_ARG_CHARS or "\0" in item:
            raise BrokerRequestError("every argument must be a string without NUL")
    command, rest = argv[0], argv[1:]
    if command in NEVER:
        raise BrokerRequestError(f"`{command}` is for a person in their own terminal, not the sandbox")
    spec = COMMANDS.get(command)
    if spec is None or (allowed is not None and command not in allowed):
        raise BrokerRequestError("unknown or disallowed command; run `taxdesk-docs manifest`")

    positionals: list[str] = []
    flags: dict[str, str] = {}
    use_stdin = False
    i = 0
    while i < len(rest):
        arg = rest[i]
        if arg.startswith("--"):
            name, eq, value = arg[2:].partition("=")
            if name == "stdin" and not eq:
                if not spec.stdin:
                    raise BrokerRequestError(f"`{command}` does not read stdin")
                use_stdin = True
                i += 1
                continue
            if name == "body":
                raise BrokerRequestError("--body is read by the shim; send the body as stdin with --stdin")
            if name not in spec.flags:
                raise BrokerRequestError(f"`{command}` does not take --{name}")
            if name in flags:
                raise BrokerRequestError(f"--{name} given twice")
            if not eq:
                if i + 1 >= len(rest) or rest[i + 1].startswith("--"):
                    raise BrokerRequestError(f"--{name} needs a value")
                value = rest[i + 1]
                i += 1
            spec.flags[name].check(name, value)
            flags[name] = value
        else:
            positionals.append(arg)
        i += 1
    if len(positionals) > len(spec.positionals):
        raise BrokerRequestError(f"`{command}` takes at most {len(spec.positionals)} positional argument(s)")
    for index, value in enumerate(positionals):
        if value.startswith("-"):
            raise BrokerRequestError("positional arguments must not start with '-'")
        spec.positionals[index].check(f"arg{index + 1}", value)

    normalized: list[str] = [command, *positionals]
    outputs: dict[str, tuple[str, str]] = {}
    for name, value in flags.items():
        output = spec.flags[name].output
        if output:
            outputs[name] = (output, value)
        else:
            normalized += [f"--{name}", value]
    if use_stdin:
        normalized.append("--stdin")
    return ParsedCall(command=command, argv=tuple(normalized), outputs=outputs, stdin=use_stdin)


def _rewrite_paths(value: Any, replacements: list[tuple[str, str]]) -> Any:
    if isinstance(value, str):
        for host, sandbox in replacements:
            if value == host or value.startswith(host + "/"):
                return sandbox + value[len(host):]
        return value
    if isinstance(value, list):
        return [_rewrite_paths(item, replacements) for item in value]
    if isinstance(value, dict):
        return {key: _rewrite_paths(item, replacements) for key, item in value.items()}
    return value


def rewrite_stdout(stdout: str, replacements: list[tuple[str, str]]) -> str:
    """Show sandbox paths, never host paths, in the CLI's JSON output."""
    if not replacements:
        return stdout
    try:
        return json.dumps(_rewrite_paths(json.loads(stdout), replacements), indent=2) + "\n"
    except json.JSONDecodeError:
        for host, sandbox in replacements:
            stdout = stdout.replace(host, sandbox)
        return stdout


def child_environment(base: dict[str, str] | None, tmpdir: Path) -> dict[str, str]:
    source = os.environ if base is None else base
    env = {key: source[key] for key in PASSTHROUGH_ENV if source.get(key)}
    env["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin"
    env["TMPDIR"] = str(tmpdir)
    return env


Runner = Callable[..., subprocess.CompletedProcess[bytes]]


class Broker:
    """Validates and executes calls; transport-independent so tests can drive it directly."""

    def __init__(
        self,
        binary: Path,
        *,
        token: str | None = None,
        log_path: Path | None = None,
        env: dict[str, str] | None = None,
        runner: Runner = subprocess.run,
        timeout: float = CALL_TIMEOUT_S,
    ) -> None:
        self.binary = Path(binary)
        self.token = token or secrets.token_hex(32)
        self.log_path = log_path
        self.env = env
        self.runner = runner
        self.timeout = timeout
        self.allowed: frozenset[str] = frozenset(COMMANDS)
        self._slots = threading.BoundedSemaphore(MAX_CONCURRENT_CALLS)
        self._log_lock = threading.Lock()

    # ── setup ────────────────────────────────────────────────────────────────
    def load_manifest(self) -> list[str]:
        """Restrict the allowlist to commands the host binary actually has. Returns warnings."""
        with tempfile.TemporaryDirectory(prefix="taxdesk-broker-") as tmp:
            result = self.runner(
                [str(self.binary), "manifest"],
                capture_output=True,
                cwd=tmp,
                env=child_environment(self.env, Path(tmp)),
                timeout=30,
            )
        if result.returncode != 0:
            raise RuntimeError(f"{self.binary} manifest exited {result.returncode}")
        try:
            manifest = json.loads(result.stdout)
            names = {entry["name"] for entry in manifest["commands"]}
        except (ValueError, KeyError, TypeError) as exc:
            raise RuntimeError(f"{self.binary} manifest is not the expected JSON") from exc
        self.allowed = frozenset(COMMANDS) & names
        warnings = []
        unknown = sorted(names - set(COMMANDS) - NEVER)
        if unknown:
            warnings.append(f"taxdesk-docs has commands the broker does not allow yet: {', '.join(unknown)}")
        missing = sorted(set(COMMANDS) - names)
        if missing:
            warnings.append(f"taxdesk-docs lacks commands the broker allows: {', '.join(missing)} (rebuild it?)")
        return warnings

    def authorized(self, header: str | None) -> bool:
        return hmac.compare_digest((header or "").encode(), f"Bearer {self.token}".encode())

    def log(self, command: str, exit_code: int, started: float) -> None:
        if self.log_path is None:
            return
        line = json.dumps({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "command": command,
            "exit": exit_code,
            "ms": round((time.monotonic() - started) * 1000),
        })
        with self._log_lock:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")
            self.log_path.chmod(0o600)

    # ── calls ────────────────────────────────────────────────────────────────
    def call(self, request: Any) -> dict[str, Any]:
        """Run one validated call. Raises BrokerRequestError for refused requests."""
        started = time.monotonic()
        if not isinstance(request, dict):
            raise BrokerRequestError("request must be a JSON object")
        try:
            parsed = parse_call(request.get("argv"), self.allowed)
        except BrokerRequestError:
            self.log("refused", 2, started)
            raise
        stdin = b""
        if request.get("stdin") is not None:
            if not parsed.stdin:
                self.log(parsed.command, 2, started)
                raise BrokerRequestError(f"`{parsed.command}` takes no stdin; pass --stdin where the command reads it")
            try:
                stdin = base64.b64decode(str(request["stdin"]), validate=True)
            except ValueError as exc:
                raise BrokerRequestError("stdin must be base64") from exc
            if len(stdin) > MAX_STDIN_BYTES:
                raise BrokerRequestError(f"stdin is larger than {MAX_STDIN_BYTES} bytes")

        if not self._slots.acquire(timeout=self.timeout):
            raise BrokerRequestError("too many concurrent taxdesk-docs calls")
        try:
            response = self._execute(parsed, stdin)
        finally:
            self._slots.release()
        self.log(parsed.command, response["exit"], started)
        return response

    def _execute(self, parsed: ParsedCall, stdin: bytes) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="taxdesk-broker-") as tmp:
            work = Path(tmp).resolve()  # /var -> /private/var on macOS, as the binary reports it
            (work / "tmp").mkdir()
            argv = [str(self.binary), *parsed.argv]
            replacements: list[tuple[str, str]] = []
            for index, (name, (kind, sandbox_path)) in enumerate(sorted(parsed.outputs.items())):
                host = work / "out" / str(index)
                if kind == "file":
                    host.mkdir(parents=True)
                    host = host / "output"
                argv += [f"--{name}", str(host)]
                replacements.append((str(host), sandbox_path))
            try:
                result = self.runner(
                    argv,
                    input=stdin,
                    capture_output=True,
                    cwd=work,
                    env=child_environment(self.env, work / "tmp"),
                    timeout=self.timeout,
                )
                exit_code, stdout, stderr = result.returncode, result.stdout or b"", result.stderr or b""
            except subprocess.TimeoutExpired:
                exit_code, stdout = 6, json.dumps({
                    "error": f"taxdesk-docs did not finish within {self.timeout:.0f}s",
                    "exit": 6,
                }).encode()
                stderr = b""
            if len(stdout) > MAX_STDOUT_BYTES:
                exit_code, stdout = 1, json.dumps({
                    "error": "output too large for the sandbox broker; use --out",
                    "exit": 1,
                }).encode()
            files = self._collect(replacements)
            text = stdout.decode("utf-8", errors="replace")
            return {
                "protocol": PROTOCOL,
                "exit": exit_code,
                "stdout": rewrite_stdout(text, replacements),
                "stderr": rewrite_stdout(stderr[:MAX_STDERR_BYTES].decode("utf-8", errors="replace"), replacements),
                "files": files,
            }

    def _collect(self, replacements: list[tuple[str, str]]) -> list[dict[str, Any]]:
        files: list[dict[str, Any]] = []
        total = 0
        for host_root, sandbox_root in replacements:
            root = Path(host_root)
            candidates = [root] if root.is_file() else sorted(p for p in root.rglob("*") if p.is_file()) if root.is_dir() else []
            for path in candidates:
                if path.is_symlink():
                    continue
                data = path.read_bytes()
                total += len(data)
                if total > MAX_FILE_BYTES:
                    raise BrokerRequestError(f"files from one call exceed {MAX_FILE_BYTES} bytes")
                relative = "" if path == root else "/" + path.relative_to(root).as_posix()
                files.append({"path": sandbox_root + relative, "data": base64.b64encode(data).decode("ascii")})
        return files


class _Handler(BaseHTTPRequestHandler):
    server_version = "taxdesk-broker"
    sys_version = ""
    broker: Broker

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - BaseHTTPRequestHandler API
        return  # never log request lines (paths only, but keep the log to Broker.log)

    def _reply(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/healthz":
            self._reply(404, {"error": "not found", "exit": 4})
            return
        self._reply(200, {"protocol": PROTOCOL})

    def do_POST(self) -> None:  # noqa: N802
        broker = self.broker
        if self.path != "/v1/run":
            self._reply(404, {"error": "not found", "exit": 4})
            return
        if not broker.authorized(self.headers.get("Authorization")):
            self._reply(401, {"error": "the sandbox broker refused this caller", "exit": 3})
            return
        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            length = -1
        if not 0 < length <= MAX_REQUEST_BYTES:
            self._reply(413, {"error": "request too large or empty", "exit": 2})
            return
        try:
            request = json.loads(self.rfile.read(length))
            self._reply(200, broker.call(request))
        except json.JSONDecodeError:
            self._reply(400, {"error": "request is not JSON", "exit": 2})
        except BrokerRequestError as exc:
            self._reply(400, {
                "error": str(exc),
                "hint": "The sandbox runs only allowlisted taxdesk-docs commands; see `taxdesk-docs manifest`.",
                "exit": 2,
            })
        except Exception:  # noqa: BLE001 - never leak host details to the VM
            self._reply(500, {"error": "the sandbox broker failed to run taxdesk-docs", "exit": 1})


class BrokerServer:
    """The broker's HTTP listener on a host-loopback port, served from a daemon thread."""

    def __init__(self, broker: Broker, host: str = "127.0.0.1", port: int = 0) -> None:
        handler = type("Handler", (_Handler,), {"broker": broker})
        self.broker = broker
        self.httpd = ThreadingHTTPServer((host, port), handler)
        self.httpd.daemon_threads = True
        self.thread = threading.Thread(target=self.httpd.serve_forever, name="taxdesk-broker", daemon=True)

    @property
    def port(self) -> int:
        return int(self.httpd.server_address[1])

    def start(self) -> "BrokerServer":
        self.thread.start()
        return self

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)


def find_binary(env: dict[str, str] | None = None, cwd: Path | None = None) -> Path | None:
    """The host taxdesk-docs: $TAXDESK_DOCS_BIN, then PATH, then ./dist/taxdesk-docs."""
    source = os.environ if env is None else env
    configured = source.get("TAXDESK_DOCS_BIN")
    if configured:
        path = Path(configured).expanduser()
        return path.resolve() if path.is_file() and os.access(path, os.X_OK) else None
    on_path = shutil.which("taxdesk-docs", path=source.get("PATH"))
    if on_path:
        return Path(on_path).resolve()
    local = (cwd or Path.cwd()) / "dist" / "taxdesk-docs"
    return local.resolve() if local.is_file() and os.access(local, os.X_OK) else None


def write_shim_config(path: Path, url: str, token: str) -> Path:
    """Config the in-sandbox shim reads: broker URL and the per-launch token (not the credential)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump({"protocol": PROTOCOL, "url": url, "token": token}, handle)
    path.chmod(0o600)
    return path
