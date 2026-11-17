import os
import sys
from pathlib import Path


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def ouro_repo_root() -> Path:
    # Machine-specific: where this host keeps its Ouro checkout.
    root = os.environ.get("OURO_REPO_ROOT")
    return Path(root).expanduser().resolve() if root else Path(__file__).resolve().parents[2] / "ouro"


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

    model_id = os.getenv("OURO_MODEL_ID", str(root / "models" / "Ouro-2.6B-Thinking"))
    host = os.getenv("HOST", os.getenv("OURO_HOST", "127.0.0.1"))
    port = int(os.getenv("PORT", os.getenv("OURO_PORT", "8000")))
    os.environ.update(OURO_MODEL_ID=model_id, OURO_HOST=host, OURO_PORT=str(port))

    print_startup(model_id, host, port)

    venv_python = root / ".venv" / "bin" / "python"
    os.chdir(root)
    os.execv(str(venv_python), [str(venv_python), str(root / "server.py")])
