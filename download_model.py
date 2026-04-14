#!/usr/bin/env -S uv run --python 3.11 --script
# /// script
# requires-python = ">=3.11,<3.14"
# dependencies = [
#   "huggingface_hub>=0.34,<1",
# ]
# ///

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from huggingface_hub import hf_hub_download


ROOT = Path(__file__).resolve().parent
INDEX_DIR = ROOT / "models"


def load_index() -> list[dict]:
    records: list[dict] = []
    for path in sorted(INDEX_DIR.glob("*.json")):
        with path.open() as f:
            record = json.load(f)
        record["_index_path"] = path
        records.append(record)
    return records


def record_id(record: dict) -> str:
    return record["artifact"]["filename"]


def record_slug(record: dict) -> str | None:
    return record.get("model", {}).get("slug")


def resolve_record(records: list[dict], selector: str) -> dict:
    for record in records:
        if selector in {
            str(record_slug(record) or ""),
            record_id(record),
            str(record.get("artifact", {}).get("local_path", "")),
            str(record.get("model", {}).get("name", "")),
        }:
            return record
    available = ", ".join(
        record_slug(record) or record_id(record) for record in records
    )
    raise SystemExit(f"Unknown model selector: {selector}\nAvailable: {available}")


def list_models(records: list[dict]) -> None:
    for record in records:
        artifact = record["artifact"]
        model = record["model"]
        download = record.get("download", {})
        print(record_slug(record) or record_id(record))
        print(f"  model:      {model.get('name')}")
        print(f"  selector:   {record_slug(record) or 'n/a'}")
        print(f"  repo:       {download.get('repo_id', 'n/a')}")
        print(f"  file:       {download.get('filename', artifact.get('filename'))}")
        print(f"  local_path: {artifact.get('local_path')}")


def download_record(record: dict, output_dir: Path | None, token: str | None) -> Path:
    download = record.get("download")
    if not download or download.get("provider") != "huggingface":
        raise SystemExit(f"No supported download metadata for {record_id(record)}")

    repo_id = download["repo_id"]
    filename = download["filename"]
    revision = download.get("revision")
    local_dir = output_dir or Path(record["artifact"]["local_path"]).resolve().parent

    path = hf_hub_download(
        repo_id=repo_id,
        filename=filename,
        revision=revision,
        local_dir=str(local_dir),
        token=token,
    )
    return Path(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download a model selectively from the local model index."
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List indexed models and exit.",
    )
    parser.add_argument(
        "--model",
        help="Model selector. Accepts slug, indexed filename, local path, or model name.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Override the destination directory. Defaults to the indexed local directory.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    records = load_index()

    if args.list:
        list_models(records)
        return

    selector = args.model or os.getenv("MODEL_SELECTOR")
    if not selector:
        raise SystemExit("Pass --model <selector> or use --list to inspect available entries.")

    token = os.getenv("HF_TOKEN")
    record = resolve_record(records, selector)
    path = download_record(record, args.output_dir, token)
    print(path)


if __name__ == "__main__":
    main()
