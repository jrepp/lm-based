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

KEV_REPO_URL = "https://github.com/jaredpalmer/kev.git"
KEV_PYTHON = "3.13"  # kev requires 3.12/3.13 (torch wheels); the repo pins 3.13


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def is_kev_profile(settings: ServerSettings) -> bool:
    # kev decision models are served through the kev runtime (kev.serve),
    # not mlx_lm.server. See ADR-005.
    return getattr(settings, "profile", "") == "mlx-kev"


def default_kev_repo_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "support" / "kev"


def ensure_kev_repo(settings: ServerSettings) -> Path:
    """Locate (or clone) the kev runtime checkout.

    kev is not published to PyPI (the `kev` name is taken by an unrelated ORM),
    so the runtime is used from a shallow clone under support/kev, mirroring the
    upstream quick start (`uv run --extra serve python -m kev.serve`).
    """
    repo_dir = getattr(settings, "kev_repo_dir", None) or default_kev_repo_dir()
    if (repo_dir / "pyproject.toml").is_file():
        return repo_dir
    if repo_dir.exists() and any(repo_dir.iterdir()):
        fail(
            f"kev runtime directory {repo_dir} exists but is not a kev checkout "
            f"(missing pyproject.toml). Remove it or set KEV_REPO_DIR."
        )
    print(f"Cloning kev runtime into {repo_dir} ...")
    repo_dir.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, 4):
        result = subprocess.run(
            ["git", "clone", "--depth", "1", KEV_REPO_URL, str(repo_dir)],
        )
        if result.returncode == 0 and (repo_dir / "pyproject.toml").is_file():
            break
        print(f"kev runtime clone attempt {attempt}/3 failed", file=sys.stderr)
        import time

        time.sleep(5 * attempt)
        subprocess.run(["rm", "-rf", str(repo_dir)], check=True)
        repo_dir.mkdir(parents=True, exist_ok=True)
    else:
        fail(f"Failed to clone kev runtime from {KEV_REPO_URL} into {repo_dir}")
    return repo_dir


def build_kev_args(settings: ServerSettings, kev_repo_dir: Path) -> list[str]:
    # Merged MLX packs (backbone weights + adapter-mode head.pt) are rejected
    # by kev.serve --run (Checkpoint.full() requires the head.pt weights-mode
    # to match the directory layout), so serve through the local shim, which
    # follows the artifact card's loading path and reuses kev.serve's
    # Server/app. The shim imports the kev package from the runtime checkout.
    shim = Path(__file__).resolve().parent / "kev_serve_local.py"
    model_dir = str(settings.model_path.parent)
    args = [
        "uv",
        "run",
        "--directory",
        str(kev_repo_dir),
        "--python",
        getattr(settings, "kev_python", KEV_PYTHON),
        "--extra",
        "serve",
        "python",
        str(shim),
        "--weights",
        model_dir,
        "--kev-repo",
        str(kev_repo_dir),
        "--host",
        settings.host,
        "--port",
        str(settings.port),
    ]
    return args


def build_args(settings: ServerSettings) -> list[str]:
    if is_kev_profile(settings):
        return build_kev_args(settings, ensure_kev_repo(settings))
    # config.json is the directory anchor (see the sidecar); mlx_lm loads the
    # whole directory. Use the non-deprecated `mlx_lm.server` console script.
    model_dir = str(settings.model_path.parent)
    args = [
        "uv",
        "run",
        "--python",
        settings.backend_python,
        "--with",
        "mlx_lm",
        "mlx_lm.server",
        "--model",
        model_dir,
        "--host",
        settings.host,
        "--port",
        str(settings.port),
    ]
    if settings.temperature is not None:
        args += ["--temp", str(settings.temperature)]
    if settings.top_p is not None:
        args += ["--top-p", str(settings.top_p)]
    if settings.top_k is not None:
        args += ["--top-k", str(settings.top_k)]
    return args


def print_startup(settings: ServerSettings, run_dir: Path | None = None) -> None:
    if is_kev_profile(settings):
        print_startup_kev(settings, run_dir=run_dir)
        return
    print("Starting mlx_lm.server")
    print(f"  model: {settings.model_path.parent}")
    print(f"  profile:{settings.profile}")
    print(f"  alias: {settings.alias}")
    print(f"  bind:  http://{settings.host}:{settings.port}")
    print(f"  ctx:   {settings.ctx_size}")
    print(
        "  samp:  "
        f"temp={settings.temperature if settings.temperature is not None else 'model'}, "
        f"top_p={settings.top_p if settings.top_p is not None else 'model'}, "
        f"top_k={settings.top_k if settings.top_k is not None else 'model'}"
    )
    print("  think: on (model default)")
    print("  tool:  OpenAI-compatible endpoint via mlx_lm")
    if run_dir is not None:
        print(f"  run:   {run_dir}")


def print_startup_kev(settings: ServerSettings, run_dir: Path | None = None) -> None:
    print("Starting kev.serve (decision model, /v1/systemone)")
    print(f"  run:   {settings.model_path.parent}")
    print(f"  repo:  {getattr(settings, 'kev_repo_dir', None) or default_kev_repo_dir()}")
    print(f"  py:    {getattr(settings, 'kev_python', KEV_PYTHON)}")
    print(f"  alias: {settings.alias}")
    print(f"  bind:  http://{settings.host}:{settings.port}")
    print(f"  ctx:   {settings.ctx_size} (max state tokens; kev-4b validated to 8192)")
    print("  samp:  none (checkpoint ships its own calibrated temperature)")
    print("  api:   POST /v1/systemone, GET /v1/models")
    if run_dir is not None:
        print(f"  run:   {run_dir}")


def validate_runtime(settings: ServerSettings) -> None:
    if not settings.model_path or not settings.model_path.is_file():
        fail(f"MLX model anchor (config.json) not found: {settings.model_path}")
    if is_kev_profile(settings):
        head = settings.model_path.parent / "head.pt"
        if not head.is_file():
            fail(
                f"kev checkpoint requires head.pt in {settings.model_path.parent} "
                "(kev.serve --run only accepts directories containing head.pt)"
            )
        ensure_kev_repo(settings)


def prepare_run_context(settings: ServerSettings) -> tuple[ServerSettings, RunContext]:
    run_id = settings.run_name or make_run_id(settings)
    run_dir = settings.run_dir_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    log_file = settings.log_file or (run_dir / "mlx-server.log")
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
