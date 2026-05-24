#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parent
INDEX_DIR = ROOT / "models"
DEFAULT_LLAMA_CPP_DIR = Path("~/d/llama.cpp").expanduser()
DEFAULT_LLAMA_CPP_BIN_DIR = DEFAULT_LLAMA_CPP_DIR / "build" / "bin"
UV_CACHE_DIR = Path("/tmp/uv-cache")

CONVERTER_DEPS = [
    "transformers==5.5.1",
    "sentencepiece>=0.1.98,<0.3.0",
    "protobuf>=4.21.0,<5.0.0",
    "numpy",
    "torch",
    "safetensors",
]


def load_index() -> list[dict]:
    records: list[dict] = []
    for path in sorted(INDEX_DIR.glob("*.json")):
        with path.open() as f:
            record = json.load(f)
        record["_index_path"] = path
        records.append(record)
    return records


def record_slug(record: dict) -> str | None:
    return record.get("model", {}).get("slug")


def record_id(record: dict) -> str:
    return record["artifact"]["filename"]


def resolve_record(records: list[dict], selector: str) -> dict:
    for record in records:
        if selector in {
            str(record_slug(record) or ""),
            record_id(record),
            str(record.get("artifact", {}).get("local_path", "")),
            str(record.get("model", {}).get("name", "")),
        }:
            return record
    available = ", ".join(record_slug(record) or record_id(record) for record in records)
    raise SystemExit(f"Unknown model selector: {selector}\nAvailable: {available}")


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def normalize_quant_label(value: str) -> str:
    return value.upper().replace(".", "_")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_command(cmd: list[str], env: dict[str, str] | None = None) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True, env=env)


def find_quantize_binary(llama_cpp_dir: Path) -> Path:
    candidates = [
        llama_cpp_dir / "build" / "bin" / "llama-quantize",
        llama_cpp_dir / "build" / "bin" / "quantize",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise SystemExit(
        f"Could not find llama quantizer under {llama_cpp_dir}. "
        "Expected build/bin/llama-quantize or build/bin/quantize."
    )


def write_sidecar(
    source_record: dict,
    artifact_path: Path,
    quantization: str,
    produced_by: str,
) -> Path:
    rel_artifact_path = artifact_path.relative_to(ROOT)
    artifact_name = artifact_path.name
    model = source_record["model"]
    source = source_record["source"]
    slug = slugify(f"{model['name']}-{quantization}")
    sidecar_path = INDEX_DIR / f"{artifact_name}.json"

    sidecar = {
        "schema_version": 1,
        "recorded_at": str(date.today()),
        "artifact": {
            "filename": artifact_name,
            "local_path": str(rel_artifact_path),
            "format": "gguf",
            "quantization": quantization,
            "size_bytes": artifact_path.stat().st_size,
            "sha256": sha256_file(artifact_path),
        },
        "model": {
            "slug": slug,
            "family": model["family"],
            "name": model["name"],
            "canonical_model_card": model["canonical_model_card"],
        },
        "source": {
            "gguf_model_card": source.get("gguf_model_card"),
            "publisher": produced_by,
            "provenance_status": "user_reported",
        },
        "download": {
            "provider": "local_build",
            "source_slug": record_slug(source_record),
            "source_local_path": source_record["artifact"]["local_path"],
        },
        "launcher": {
            "script": source_record["launcher"]["script"],
            "profile": source_record["launcher"]["profile"],
            "recommended_env": {
                "MODEL_FILE": str(rel_artifact_path),
                "PROFILE": source_record["launcher"]["profile"],
            },
        },
        "notes": [
            f"Locally converted from {source_record['artifact']['local_path']} using llama.cpp.",
            "Checksum reflects the local GGUF artifact only; upstream provenance should be tracked through the source sidecar.",
        ],
    }

    with sidecar_path.open("w") as f:
        json.dump(sidecar, f, indent=2)
        f.write("\n")

    return sidecar_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert a downloaded Hugging Face snapshot into GGUF using a local llama.cpp checkout."
    )
    parser.add_argument(
        "--model",
        required=True,
        help="Model selector. Accepts the same values as download_model.py.",
    )
    parser.add_argument(
        "--llama-cpp-dir",
        type=Path,
        default=DEFAULT_LLAMA_CPP_DIR,
        help=f"Path to llama.cpp checkout. Default: {DEFAULT_LLAMA_CPP_DIR}",
    )
    parser.add_argument(
        "--outtype",
        default="bf16",
        choices=["f32", "f16", "bf16", "q8_0", "tq1_0", "tq2_0", "auto"],
        help="GGUF output type for the conversion step.",
    )
    parser.add_argument(
        "--quantize",
        help="Optional post-conversion quantization target, for example Q6_K or Q4_K_M.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT,
        help="Directory for generated GGUF files. Default: repo root.",
    )
    parser.add_argument(
        "--keep-base",
        action="store_true",
        help="Keep the unquantized GGUF when --quantize is used. By default it is retained anyway; this flag is informational for future compatibility.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    records = load_index()
    record = resolve_record(records, args.model)

    if record["artifact"]["format"] != "safetensors":
        raise SystemExit("build_gguf.py currently supports safetensors snapshot sources only.")

    model_anchor = ROOT / record["artifact"]["local_path"]
    if not model_anchor.exists():
        raise SystemExit(f"Model anchor not found: {model_anchor}")

    model_dir = model_anchor.parent
    llama_cpp_dir = args.llama_cpp_dir.expanduser().resolve()
    converter = llama_cpp_dir / "convert_hf_to_gguf.py"
    if not converter.exists():
        raise SystemExit(f"Could not find converter script: {converter}")

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    model_name = record["model"]["name"]
    base_quant = normalize_quant_label(args.outtype)
    base_output = output_dir / f"{model_name}-{base_quant}.gguf"

    env = os.environ.copy()
    env["UV_CACHE_DIR"] = str(UV_CACHE_DIR)

    convert_cmd = [
        "uv",
        "run",
        "--python",
        "3.11",
    ]
    for dep in CONVERTER_DEPS:
        convert_cmd.extend(["--with", dep])
    convert_cmd.extend(
        [
            "python",
            str(converter),
            str(model_dir),
            "--outfile",
            str(base_output),
            "--outtype",
            args.outtype,
        ]
    )
    run_command(convert_cmd, env=env)

    final_output = base_output
    final_quant = base_quant

    if args.quantize:
        quantization = normalize_quant_label(args.quantize)
        quantizer = find_quantize_binary(llama_cpp_dir)
        quantized_output = output_dir / f"{model_name}-{quantization}.gguf"
        run_command(
            [
                str(quantizer),
                str(base_output),
                str(quantized_output),
                args.quantize,
            ]
        )
        final_output = quantized_output
        final_quant = quantization

    sidecar_path = write_sidecar(
        source_record=record,
        artifact_path=final_output,
        quantization=final_quant,
        produced_by="local-llama-cpp",
    )

    print(final_output)
    print(sidecar_path)


if __name__ == "__main__":
    main()
