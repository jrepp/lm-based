"""Export a runtime trajectory figure from a saved receipt (no model load)."""

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .trajectory import validate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("receipt", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    data = json.loads(args.receipt.read_text())
    checks = validate(data["loop_receipts"], data["generated_token_ids"], data["completion"],
                      prompt_tokens=data["prompt_tokens"], layers=data["config"]["num_hidden_layers"],
                      flash=data["mode"] == "flash")
    valid = all(checks.values()) and data["checks"]["stopped_on_end_token"]
    fig, axes = plt.subplots(3, 1, figsize=(11, 8), sharex=True, constrained_layout=True)
    colors = ("#6b7280", "#277da1", "#f8961e", "#43aa8b")
    for loop, color in zip(range(1, 5), colors):
        rows = [r for r in data["loop_receipts"] if r["loop"] == loop]
        axes[0].plot(range(len(rows)), [r["next_token_entropy"] for r in rows],
                     color=color, linewidth=1, label=f"Loop {loop}")
        axes[1].plot(range(len(rows)), [r["hidden_delta_rms"] for r in rows], color=color, linewidth=1)
    timings = data["decode_seconds_per_token"]
    axes[2].plot(range(1, len(timings) + 1), timings, color="#277da1", linewidth=1)
    axes[0].set_ylabel("Next-token entropy (nats)")
    axes[1].set_ylabel("Hidden-state change (RMS)")
    axes[2].set_ylabel("Decode time (seconds)")
    axes[2].set_xlabel("Prediction step (0 = prompt prefill)")
    axes[0].legend(ncol=4, frameon=False)
    for ax in axes:
        ax.grid(alpha=0.2)
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle(f"Ouro MLX {data['mode']} — {'complete, answer validated' if valid else 'incomplete or failed validation'}\n"
                 "Runtime observations; not a measure of reasoning faithfulness", fontsize=13)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise SystemExit("refusing to overwrite existing figure")
    fig.savefig(args.output)
    print(args.output)


if __name__ == "__main__":
    main()
