import os
import sys
from pathlib import Path

OURO_REPO_ROOT = Path("/Users/jrepp/d/ouro")
VENV_PYTHON = OURO_REPO_ROOT / ".venv" / "bin" / "python"
SERVER_FILE = OURO_REPO_ROOT / "server.py"


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def validate_runtime() -> None:
    if not SERVER_FILE.is_file():
        fail(f"Ouro server file not found: {SERVER_FILE}")


def print_startup(model_id: str, host: str, port: int) -> None:
    print("Starting Ouro inference server")
    print(f"  model: {model_id}")
    print(f"  bind:  http://{host}:{port}")


def main() -> None:
    validate_runtime()

    model_id = os.getenv("OURO_MODEL_ID", "ByteDance/Ouro-2.6B-Thinking")
    host = os.getenv("OURO_HOST", "0.0.0.0")
    port = int(os.getenv("OURO_PORT", "8000"))

    print_startup(model_id, host, port)

    os.chdir(OURO_REPO_ROOT)
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), str(SERVER_FILE)])