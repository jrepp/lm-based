#!/usr/bin/env -S uv run --python 3.11 --script
# /// script
# requires-python = ">=3.11,<3.14"
# ///

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path


PROMPT_RE = re.compile(
    r"prompt eval time =\s+([0-9.]+) ms /\s+(\d+) tokens .*? ([0-9.]+) tokens per second"
)
EVAL_RE = re.compile(
    r"eval time =\s+([0-9.]+) ms /\s+(\d+) tokens .*? ([0-9.]+) tokens per second"
)
TOTAL_RE = re.compile(r"total time =\s+([0-9.]+) ms /\s+(\d+) tokens")
SLOT_CTX_RE = re.compile(r"new prompt, n_ctx_slot = (\d+)")
CAP_RE = re.compile(
    r"the slot context \((\d+)\) exceeds the training context of the model \((\d+)\) - capping"
)
CHECKPOINT_CREATE_RE = re.compile(r"created context checkpoint")
CHECKPOINT_ERASE_RE = re.compile(r"erasing old context checkpoint")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize a captured llama-server run.")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional output file for writing the summary JSON.",
    )
    return parser.parse_args()


def parse_log(log_path: Path) -> dict:
    prompt_blocks = []
    eval_blocks = []
    total_blocks = []
    slot_ctx_values = []
    capped_to = None
    requested_ctx = None
    checkpoint_created = 0
    checkpoint_erased = 0
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in lines:
        match = PROMPT_RE.search(line)
        if match:
            prompt_blocks.append(
                {
                    "time_ms": float(match.group(1)),
                    "tokens": int(match.group(2)),
                    "tokens_per_sec": float(match.group(3)),
                }
            )
            continue

        match = EVAL_RE.search(line)
        if match:
            eval_blocks.append(
                {
                    "time_ms": float(match.group(1)),
                    "tokens": int(match.group(2)),
                    "tokens_per_sec": float(match.group(3)),
                }
            )
            continue

        match = TOTAL_RE.search(line)
        if match:
            total_blocks.append(
                {
                    "time_ms": float(match.group(1)),
                    "tokens": int(match.group(2)),
                }
            )
            continue

        match = SLOT_CTX_RE.search(line)
        if match:
            slot_ctx_values.append(int(match.group(1)))

        match = CAP_RE.search(line)
        if match:
            requested_ctx = int(match.group(1))
            capped_to = int(match.group(2))

        if CHECKPOINT_CREATE_RE.search(line):
            checkpoint_created += 1
        if CHECKPOINT_ERASE_RE.search(line):
            checkpoint_erased += 1

    return {
        "request_count": len(total_blocks),
        "first_prompt_eval": prompt_blocks[0] if prompt_blocks else None,
        "last_prompt_eval": prompt_blocks[-1] if prompt_blocks else None,
        "best_prompt_tps": max((b["tokens_per_sec"] for b in prompt_blocks), default=None),
        "first_eval": eval_blocks[0] if eval_blocks else None,
        "last_eval": eval_blocks[-1] if eval_blocks else None,
        "best_eval_tps": max((b["tokens_per_sec"] for b in eval_blocks), default=None),
        "last_total": total_blocks[-1] if total_blocks else None,
        "slot_context": {
            "requested_ctx": requested_ctx,
            "capped_to": capped_to,
            "observed_n_ctx_slot": sorted(set(slot_ctx_values)),
        },
        "checkpoints": {
            "created": checkpoint_created,
            "erased": checkpoint_erased,
        },
    }


def parse_monitor(csv_path: Path) -> dict:
    peak_rss = 0
    peak_vsz = 0
    peak_cpu = 0.0
    first = None
    last = None
    samples = 0

    with csv_path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            samples += 1
            rss = int(row["rss_kib"])
            vsz = int(row["vsz_kib"])
            cpu = float(row["cpu_percent"])
            peak_rss = max(peak_rss, rss)
            peak_vsz = max(peak_vsz, vsz)
            peak_cpu = max(peak_cpu, cpu)
            if first is None:
                first = row
            last = row

    return {
        "samples": samples,
        "peak_rss_kib": peak_rss,
        "peak_rss_gib": round(peak_rss / 1024 / 1024, 3),
        "peak_vsz_kib": peak_vsz,
        "peak_vsz_gib": round(peak_vsz / 1024 / 1024, 3),
        "peak_cpu_percent": peak_cpu,
        "first_sample_at": first["captured_at"] if first else None,
        "last_sample_at": last["captured_at"] if last else None,
        "duration_sec": float(last["elapsed_sec"]) if last else 0.0,
    }


def main() -> None:
    args = parse_args()
    metadata = json.loads((args.run_dir / "metadata.json").read_text(encoding="utf-8"))
    summary = {
        "run_id": metadata["run_id"],
        "run_dir": str(args.run_dir),
        "log": parse_log(Path(metadata["log_file"])),
        "monitor": parse_monitor(Path(metadata["monitor_csv"])),
        "server": metadata.get("server"),
        "monitor_process": metadata.get("monitor"),
    }
    rendered = json.dumps(summary, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
