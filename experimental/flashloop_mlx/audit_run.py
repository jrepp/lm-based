"""Offline trajectory audit; does not load weights or trust model-reported stats."""

import argparse
import hashlib
import json
from pathlib import Path
import statistics

from .trajectory import validate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--layers", type=int, default=48)
    args = parser.parse_args()
    data = json.loads(args.receipt.read_text())
    checks = validate(data["loop_receipts"], data["generated_token_ids"], data["completion"],
                      prompt_tokens=data["prompt_tokens"], layers=args.layers, flash=data["mode"] == "flash")
    checks["stopped_on_end_token"] = data["checks"]["stopped_on_end_token"]
    checks["packed_prefix_exercised"] = data["checks"]["packed_prefix_exercised"]
    checks["source_unchanged_during_run"] = data["checks"].get("source_unchanged_during_run", False)
    timing = data["decode_seconds_per_token"]
    loops = {}
    for loop in range(1, 5):
        values = [r for r in data["loop_receipts"] if r["loop"] == loop]
        loops[str(loop)] = {
            "count": len(values),
            "median_hidden_delta_rms": statistics.median(r["hidden_delta_rms"] for r in values),
            "median_next_token_entropy": statistics.median(r["next_token_entropy"] for r in values),
        }
    print(json.dumps({
        "receipt_sha256": hashlib.sha256(args.receipt.read_bytes()).hexdigest(),
        "mode": data["mode"], "checks": checks,
        "prompt_tokens": data["prompt_tokens"], "completion_tokens": data["completion_tokens"],
        "decode_median_seconds": statistics.median(timing) if timing else None,
        "stored_cache_bytes": data["stored_cache_bytes"], "mlx_peak_bytes": data["mlx_peak_bytes"],
        "loops": loops,
        "interpretation": "Checks execution and one arithmetic answer; does not prove internal reasoning faithfulness.",
    }, indent=2))
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
