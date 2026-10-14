"""Where model artifacts live on disk.

Sidecar ``artifact.local_path`` values are relative. Downloads land under
``artifacts/`` (``MODEL_DIR``, from the environment or .env, overrides it).
Older checkouts kept them at the project root, so a file there still wins.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lm_launcher.env_file import setting

ROOT = Path(__file__).resolve().parent.parent


def artifacts_dir(root: Path = ROOT) -> Path:
    override = setting("MODEL_DIR", root=root)
    if override:
        path = Path(override).expanduser()
        return path if path.is_absolute() else root / path
    return root / "artifacts"


def resolve_artifact(local_path: str | Path, root: Path = ROOT, artifacts: Path | None = None) -> Path:
    """Absolute path of a sidecar-relative artifact: project root if present, else artifacts/."""
    path = Path(local_path)
    if path.is_absolute():
        return path
    legacy = root / path
    if legacy.exists():
        return legacy
    return (artifacts if artifacts is not None else artifacts_dir(root)) / path


def record_artifact_path(record: dict[str, Any], root: Path = ROOT, artifacts: Path | None = None) -> Path | None:
    local_path = record.get("artifact", {}).get("local_path")
    if not local_path:
        return None
    return resolve_artifact(local_path, root, artifacts)


def artifact_present(record: dict[str, Any], root: Path = ROOT, artifacts: Path | None = None) -> bool:
    path = record_artifact_path(record, root, artifacts)
    return path is not None and path.exists()
