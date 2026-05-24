import os
import shutil
import sys
from pathlib import Path

from lm_launcher.settings import ServerSettings


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def add_arg(args: list[str], flag: str, value: object | None) -> None:
    if value is not None:
        args.extend([flag, str(value)])


def resolve_mlx_model(settings: ServerSettings) -> str:
    if settings.model_path and settings.model_path.exists():
        return str(settings.model_path)
    if settings.mlx_model:
        return settings.mlx_model
    if settings.model_file:
        return settings.model_file
    fail("No MLX model path or Hugging Face repo configured.")


def build_args(settings: ServerSettings) -> list[str]:
    args = [
        shutil.which("mlx_lm.server") or "mlx_lm.server",
        "--model",
        resolve_mlx_model(settings),
        "--host",
        settings.host,
        "--port",
        str(settings.port),
    ]

    add_arg(args, "--temp", settings.temperature)
    add_arg(args, "--top-p", settings.top_p)
    add_arg(args, "--top-k", settings.top_k)
    add_arg(args, "--min-p", settings.min_p)
    add_arg(args, "--max-tokens", settings.max_tokens)

    return args


def print_startup(settings: ServerSettings) -> None:
    print("Starting mlx_lm.server")
    print(f"  model: {resolve_mlx_model(settings)}")
    print(f"  profile:{settings.profile}")
    print(f"  alias: {settings.alias}")
    print(f"  bind:  http://{settings.host}:{settings.port}")
    print(f"  ctx:   {settings.ctx_size}")
    print(
        "  samp:  "
        f"temp={settings.temperature if settings.temperature is not None else 'server'}, "
        f"top_k={settings.top_k if settings.top_k is not None else 'server'}, "
        f"top_p={settings.top_p if settings.top_p is not None else 'server'}, "
        f"min_p={settings.min_p if settings.min_p is not None else 'server'}, "
        f"max_tokens={settings.max_tokens if settings.max_tokens is not None else 'server'}, "
        f"repeat={settings.repetition_penalty if settings.repetition_penalty is not None else 'request/default'}"
    )


def validate_runtime(settings: ServerSettings) -> None:
    if shutil.which("mlx_lm.server") is None:
        fail("mlx_lm.server not found. Install mlx-lm before launching MLX profiles.")

    if settings.model_path and settings.model_path.exists():
        return
    if settings.mlx_model:
        return

    fail(f"MLX model path not found: {settings.model_path}")


def main() -> None:
    settings = ServerSettings()
    validate_runtime(settings)
    print_startup(settings)
    os.execvp("mlx_lm.server", build_args(settings))
