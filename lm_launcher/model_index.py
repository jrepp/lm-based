from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_model_records(models_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(models_dir.glob("*.json")):
        with path.open(encoding="utf-8") as f:
            record = json.load(f)
        record["_index_path"] = str(path)
        records.append(record)
    return records


def find_record_by_slug(models_dir: Path, slug: str) -> dict[str, Any] | None:
    for record in load_model_records(models_dir):
        if record.get("model", {}).get("slug") == slug:
            return record
    return None
