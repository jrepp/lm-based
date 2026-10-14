"""Read settings the way the launcher does: process environment first, then .env.

Stdlib only, for scripts that run without the project's pydantic dependencies.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read_dotenv(path: Path = ROOT / ".env") -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def setting(name: str, default: str | None = None, root: Path = ROOT) -> str | None:
    return os.environ.get(name) or read_dotenv(root / ".env").get(name) or default
