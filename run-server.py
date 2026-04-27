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


if _is_ouro_model():
    from lm_launcher.ouro_server import main as ouro_main

    if __name__ == "__main__":
        ouro_main()
else:
    from lm_launcher.launcher import main as llama_main

    if __name__ == "__main__":
        llama_main()