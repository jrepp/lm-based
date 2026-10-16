"""Resolve which ``/v1/models`` ids mean a given slug is already served.

Different backends report different model ids:

- ``llama-server`` reports the ``--alias``, which the profiles set to the slug.
- ``mlx_lm`` and ``transformers serve`` report the absolute model directory path
  they were pointed at (they have no ``--alias`` / ``--model-id`` flag).

This module gives ``support/model-service`` a backend-agnostic way to decide
whether a server already running on a port corresponds to the requested slug,
so adoption works for MLX/Transformers and not just llama-server.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from lm_launcher.artifacts import artifacts_dir


def _model_dirs_abs(repo_root: str, local_path: str) -> list[str]:
    """Absolute paths a backend may have been pointed at for this model directory.

    ``local_path`` is the sidecar's artifact anchor (a file inside the model
    dir, e.g. ``.../config.json`` or ``.../model.safetensors.index.json``); the
    served directory is its parent, under the project root (older downloads)
    or ``artifacts/``.
    """
    model_dir = os.path.dirname(local_path) or "."
    root = Path(repo_root)
    return [
        os.path.normpath(os.path.join(repo_root, model_dir)),
        os.path.normpath(os.path.join(str(artifacts_dir(root)), model_dir)),
    ]


def acceptable_model_ids(
    models_dir: str | Path,
    slug: str,
    repo_root: str | Path | None = None,
) -> list[str]:
    """Return every ``/v1/models`` id that should count as "slug is served".

    Always includes the slug itself (llama-server alias). When the slug resolves
    to a sidecar, also includes the absolute model directory and its basename
    (mlx_lm / transformers serve report one of those).
    """
    models_path = Path(models_dir)
    root = str(repo_root) if repo_root is not None else str(models_path.parent)

    ids: list[str] = [slug]
    for path in sorted(models_path.glob("*.json")):
        try:
            record = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if record.get("model", {}).get("slug") != slug:
            continue
        local_path = record.get("artifact", {}).get("local_path") or ""
        if local_path:
            for abs_dir in _model_dirs_abs(root, local_path):
                ids.append(abs_dir)
                ids.append(os.path.basename(abs_dir))
        break

    # de-duplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for value in ids:
        if value not in seen:
            seen.add(value)
            unique.append(value)
    return unique
