from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from lm_launcher.run_capture import (
    RunContext,
    finalize_run,
    install_signal_forwarding,
    make_run_id,
    start_monitor,
    update_metadata,
    write_initial_metadata,
)
from lm_launcher.settings import ServerSettings


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def build_args(settings: ServerSettings) -> list[str]:
    model_ref = str(settings.model_path.parent)
    args = [
        "uv",
        "run",
        "--python",
        settings.backend_python,
        "--with",
        "transformers[serving]>=4.57,<6",
        "--with",
        "torch",
        "--with",
        "torchvision",
        "--with",
        "pillow",
        "transformers",
        "serve",
        "--host",
        settings.host,
        "--port",
        str(settings.port),
        "--force-model",
        model_ref,
        "--dtype",
        "bfloat16",
        "--model-timeout",
        "-1",
        "--continuous-batching",
    ]
    return args


def print_startup(settings: ServerSettings, run_dir: Path | None = None) -> None:
    print("Starting transformers serve")
    print(f"  model: {settings.model_path.parent}")
    print(f"  profile:{settings.profile}")
    print(f"  alias: {settings.alias}")
    print(f"  bind:  http://{settings.host}:{settings.port}")
    print(f"  ctx:   {settings.ctx_size}")
    print("  dtype: bfloat16")
    print("  cb:    on")
    print("  tool:  qwen-family support via OpenAI-compatible endpoint")
    if run_dir is not None:
        print(f"  run:   {run_dir}")


def validate_runtime(settings: ServerSettings) -> None:
    if not settings.model_path or not settings.model_path.is_file():
        fail(f"Model anchor file not found: {settings.model_path}")


def prepare_run_context(settings: ServerSettings) -> tuple[ServerSettings, RunContext]:
    run_id = settings.run_name or make_run_id(settings)
    run_dir = settings.run_dir_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    log_file = settings.log_file or (run_dir / "transformers-serve.log")
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


def start_server(settings: ServerSettings, context: RunContext) -> subprocess.Popen[str]:
    args = build_args(settings)
    env = os.environ.copy()
    env["UV_CACHE_DIR"] = env.get("UV_CACHE_DIR", "/tmp/uv-cache")
    process = subprocess.Popen(args, text=True, env=env)
    context.pid_file.write_text(f"{process.pid}\n", encoding="utf-8")
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


def run_with_capture(settings: ServerSettings) -> int:
    settings, context = prepare_run_context(settings)
    write_initial_metadata(settings, context)
    print(f"  pids:  server->{context.pid_file.name} monitor->{context.monitor_pid_file.name}")
    print(f"  perf:  log={context.log_file.name} samples={context.monitor_csv.name}")
    print_startup(settings, run_dir=context.run_dir)

    process = start_server(settings, context)
    monitor = start_monitor(process, settings, context)
    install_signal_forwarding(process)
    process.wait()
    return finalize_run(process, monitor, context)


def main() -> None:
    settings = ServerSettings()
    validate_runtime(settings)
    if settings.enable_run_capture:
        raise SystemExit(run_with_capture(settings))

    print_startup(settings)
    env = os.environ.copy()
    env["UV_CACHE_DIR"] = env.get("UV_CACHE_DIR", "/tmp/uv-cache")
    os.execvpe("uv", build_args(settings), env)
