from __future__ import annotations

import argparse
import csv
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sample process stats for a pid.")
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--interval-sec", type=float, default=1.0)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def read_ps_row(pid: int) -> dict[str, str] | None:
    result = subprocess.run(
        [
            "ps",
            "-o",
            "pid=,ppid=,rss=,vsz=,%cpu=,state=,etime=,comm=",
            "-p",
            str(pid),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    row = result.stdout.strip()
    if result.returncode != 0 or not row:
        return None
    parts = row.split(None, 7)
    if len(parts) < 8:
        return None
    return {
        "pid": parts[0],
        "ppid": parts[1],
        "rss_kib": parts[2],
        "vsz_kib": parts[3],
        "cpu_percent": parts[4],
        "state": parts[5],
        "elapsed_ps": parts[6],
        "command": parts[7],
    }


def main() -> None:
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()

    with args.output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "captured_at",
                "elapsed_sec",
                "pid",
                "ppid",
                "rss_kib",
                "vsz_kib",
                "cpu_percent",
                "state",
                "elapsed_ps",
                "command",
            ],
        )
        writer.writeheader()

        while True:
            row = read_ps_row(args.pid)
            if row is None:
                break

            writer.writerow(
                {
                    "captured_at": datetime.now(UTC).isoformat(),
                    "elapsed_sec": f"{time.time() - started:.3f}",
                    **row,
                }
            )
            f.flush()
            time.sleep(args.interval_sec)


if __name__ == "__main__":
    main()
