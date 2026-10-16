"""Load serve-policy.yaml with an optional host-local overlay.

``serve-policy.yaml`` is the tracked default: a small model set any Apple Silicon
Mac can run. ``serve-policy.local.yaml`` (gitignored, written by ``./up init``)
describes this host. Both hold JSON content. The local file is merged over the
default: objects merge key by key, anything else (lists included) replaces.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
POLICY_PATH = ROOT / "serve-policy.yaml"
LOCAL_POLICY_PATH = ROOT / "serve-policy.local.yaml"


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _read(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def local_policy_path(policy_path: Path) -> Path:
    """serve-policy.yaml -> serve-policy.local.yaml beside it."""
    return policy_path.with_name(f"{policy_path.stem}.local{policy_path.suffix}")


def load_policy(policy_path: Path = POLICY_PATH, local_path: Path | None = None) -> dict[str, Any]:
    """The effective policy; {} when neither file is readable."""
    base = _read(policy_path) or {}
    overlay = _read(local_path if local_path is not None else local_policy_path(policy_path))
    return deep_merge(base, overlay) if overlay else base


def enabled_slugs(policy: dict[str, Any]) -> list[str]:
    enabled = policy.get("models", {}).get("enabled")
    return [str(slug) for slug in enabled] if isinstance(enabled, list) else []
