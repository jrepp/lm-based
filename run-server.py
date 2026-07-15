#!/usr/bin/env -S uv run

# /// script
# requires-python = ">=3.11,<3.14"
# dependencies = [
#   "pydantic>=2.11,<3",
#   "pydantic-settings>=2.10,<3",
# ]
# ///

from __future__ import annotations

import os

PROFILE = os.getenv("PROFILE", "auto")
MODEL_SLUG = os.getenv("MODEL_SLUG")


def _is_ouro_model() -> bool:
    if PROFILE == "ouro":
        return True
    if MODEL_SLUG and "ouro" in MODEL_SLUG.lower():
        return True
    if PROFILE == "auto" and MODEL_SLUG is None:
        model_file = os.getenv("MODEL_FILE", "")
        if "ouro" in model_file.lower():
            return True
    return False


def _is_transformers_model() -> bool:
    if PROFILE == "qwen2.5-coder-transformers":
        return True
    if MODEL_SLUG and "qwen25-coder-7b-instruct" in MODEL_SLUG.lower():
        return True
    if PROFILE == "auto" and MODEL_SLUG is None:
        model_file = os.getenv("MODEL_FILE", "")
        if "qwen2.5-coder-7b-instruct" in model_file.lower():
            return True
    return False


def _is_mlx_model() -> bool:
    if PROFILE.startswith("mlx"):
        return True
    if MODEL_SLUG and ("bonsai" in MODEL_SLUG.lower() or "mlx" in MODEL_SLUG.lower()):
        return True
    if PROFILE == "auto" and MODEL_SLUG is None:
        model_file = os.getenv("MODEL_FILE", "")
        lowered = model_file.lower()
        if "bonsai" in lowered or "mlx" in lowered:
            return True
    return False


def select_backend() -> str:
    if _is_ouro_model():
        return "ouro"
    if _is_mlx_model():
        return "mlx"
    if _is_transformers_model():
        return "transformers"
    return "llama"


def main() -> None:
    backend = select_backend()
    if backend == "ouro":
        from lm_launcher.ouro_server import main as backend_main
    elif backend == "mlx":
        from lm_launcher.mlx_server import main as backend_main
    elif backend == "transformers":
        from lm_launcher.transformers_server import main as backend_main
    else:
        from lm_launcher.launcher import main as backend_main
    backend_main()


if __name__ == "__main__":
    main()
