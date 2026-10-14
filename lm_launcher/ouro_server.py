import os
import sys
from pathlib import Path


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def ouro_repo_root() -> Path:
    # Machine-specific: where this host keeps its Ouro checkout.
    root = os.environ.get("OURO_REPO_ROOT")
    if not root:
        fail("OURO_REPO_ROOT is not set; export it as the path to your Ouro checkout")
    return Path(root)


def validate_runtime(root: Path) -> None:
    if not (root / "server.py").is_file():
        fail(f"Ouro server file not found: {root / 'server.py'}")


def print_startup(model_id: str, host: str, port: int) -> None:
    print("Starting Ouro inference server")
    print(f"  model: {model_id}")
    print(f"  bind:  http://{host}:{port}")


def main() -> None:
    root = ouro_repo_root()
    validate_runtime(root)

    model_id = os.getenv("OURO_MODEL_ID", "ByteDance/Ouro-2.6B-Thinking")
    host = os.getenv("OURO_HOST", "0.0.0.0")
    port = int(os.getenv("OURO_PORT", "8000"))

    print_startup(model_id, host, port)

    venv_python = root / ".venv" / "bin" / "python"
    os.chdir(root)
    os.execv(str(venv_python), [str(venv_python), str(root / "server.py")])
