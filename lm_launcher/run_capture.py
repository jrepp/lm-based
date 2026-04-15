from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lm_launcher.settings import ServerSettings


@dataclass
class RunContext:
    run_id: str
    run_dir: Path
    log_file: Path
    monitor_csv: Path
    metadata_file: Path
    pid_file: Path
    monitor_pid_file: Path


def make_run_id(settings: ServerSettings) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    alias = (settings.alias or settings.profile or "run").replace("/", "-")
    return f"{timestamp}-{alias}"


def prepare_run_context(settings: ServerSettings) -> tuple[ServerSettings, RunContext]:
    run_id = settings.run_name or make_run_id(settings)
    run_dir = settings.run_dir_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    log_file = settings.log_file or (run_dir / "llama-server.log")
    monitor_csv = run_dir / "monitor.csv"
    metadata_file = run_dir / "metadata.json"
    pid_file = run_dir / "server.pid"
    monitor_pid_file = run_dir / "monitor.pid"

    settings.log_file = log_file
    context = RunContext(
        run_id=run_id,
        run_dir=run_dir,
        log_file=log_file,
        monitor_csv=monitor_csv,
        metadata_file=metadata_file,
        pid_file=pid_file,
        monitor_pid_file=monitor_pid_file,
    )
    return settings, context


def _write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_initial_metadata(settings: ServerSettings, context: RunContext) -> None:
    payload = {
        "run_id": context.run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "run_dir": str(context.run_dir),
        "log_file": str(context.log_file),
        "monitor_csv": str(context.monitor_csv),
        "settings": settings.model_dump(mode="json"),
        "launcher": {
            "script": str(Path(__file__).resolve().parents[1] / "run-server.py"),
            "python_executable": sys.executable,
        },
    }
    _write_json(context.metadata_file, payload)


def update_metadata(context: RunContext, updates: dict[str, Any]) -> None:
    payload = json.loads(context.metadata_file.read_text(encoding="utf-8"))
    payload.update(updates)
    _write_json(context.metadata_file, payload)


def start_server(settings: ServerSettings, context: RunContext) -> subprocess.Popen[str]:
    from lm_launcher.launcher import build_args

    args = build_args(settings)
    process = subprocess.Popen(args, text=True)
    _write_text(context.pid_file, f"{process.pid}\n")
    update_metadata(
        context,
        {
            "server": {
                "pid": process.pid,
                "argv": args,
                "started_at": datetime.now(UTC).isoformat(),
            }
        },
    )
    return process


def start_monitor(
    process: subprocess.Popen[str], settings: ServerSettings, context: RunContext
) -> subprocess.Popen[str]:
    monitor_args = [
        sys.executable,
        "-m",
        "lm_launcher.pid_monitor",
        "--pid",
        str(process.pid),
        "--interval-sec",
        str(settings.monitor_interval_sec),
        "--output",
        str(context.monitor_csv),
    ]
    monitor = subprocess.Popen(monitor_args, text=True)
    _write_text(context.monitor_pid_file, f"{monitor.pid}\n")
    update_metadata(
        context,
        {
            "monitor": {
                "pid": monitor.pid,
                "argv": monitor_args,
                "started_at": datetime.now(UTC).isoformat(),
            }
        },
    )
    return monitor


def install_signal_forwarding(process: subprocess.Popen[str]) -> None:
    def handler(signum: int, _frame: Any) -> None:
        if process.poll() is None:
            process.send_signal(signum)

    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)


def stop_monitor(monitor: subprocess.Popen[str] | None) -> None:
    if monitor is None or monitor.poll() is not None:
        return
    monitor.terminate()
    try:
        monitor.wait(timeout=5)
    except subprocess.TimeoutExpired:
        monitor.kill()
        monitor.wait(timeout=5)


def finalize_run(
    process: subprocess.Popen[str],
    monitor: subprocess.Popen[str] | None,
    context: RunContext,
) -> int:
    stop_monitor(monitor)
    update_metadata(
        context,
        {
            "completed_at": datetime.now(UTC).isoformat(),
            "server": {
                **json.loads(context.metadata_file.read_text(encoding="utf-8")).get("server", {}),
                "returncode": process.returncode,
                "finished_at": datetime.now(UTC).isoformat(),
            },
            "monitor": {
                **json.loads(context.metadata_file.read_text(encoding="utf-8")).get("monitor", {}),
                "returncode": monitor.returncode if monitor is not None else None,
                "finished_at": datetime.now(UTC).isoformat() if monitor is not None else None,
            },
        },
    )
    return process.returncode


def run_with_capture(settings: ServerSettings) -> int:
    from lm_launcher.launcher import print_startup

    settings, context = prepare_run_context(settings)
    write_initial_metadata(settings, context)
    print(f"  run:   {context.run_dir}")
    print(f"  pids:  server->{context.pid_file.name} monitor->{context.monitor_pid_file.name}")
    print(f"  perf:  log={context.log_file.name} samples={context.monitor_csv.name}")
    print_startup(settings)

    process = start_server(settings, context)
    monitor = start_monitor(process, settings, context)
    install_signal_forwarding(process)
    process.wait()
    return finalize_run(process, monitor, context)
