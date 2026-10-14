"""Per-launch run hygiene for pi-local.

Each launch gets:

- a scratch folder inside the workspace, `<workspace>/.pi-run/<run-id>/` with `tmp/` as the
  agent's TMPDIR. `.pi-run/` carries a `.gitignore` of `*`, so git never shows it, and the
  folder is deleted when Pi exits unless `--keep-run-files` is given;
- a records folder outside the workspace, `.runtime/pi/runs/<run-id>/` (gitignored), holding
  the trajectory the run-record extension writes (every tool call and its output) and the
  taxdesk-docs broker log, so a model's report can be checked against what tools returned.
"""

from __future__ import annotations

import secrets
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUN_RECORDS = ROOT / ".runtime" / "pi" / "runs"
RUN_DIR_NAME = ".pi-run"


@dataclass(frozen=True)
class RunContext:
    run_id: str
    workspace: Path
    keep: bool = False
    trajectory: bool = True
    records_root: Path = RUN_RECORDS

    @property
    def run_dir(self) -> Path:
        return self.workspace / RUN_DIR_NAME / self.run_id

    @property
    def records(self) -> Path:
        return self.records_root / self.run_id


def new_run_id() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + secrets.token_hex(3)


def prepare_run_dir(run: RunContext) -> Path:
    """Create <workspace>/.pi-run/<run-id>/tmp (mode 700) and the self-ignoring .gitignore."""
    tmp = run.run_dir / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    for path in (run.run_dir.parent, run.run_dir, tmp):
        path.chmod(0o700)
    (run.run_dir.parent / ".gitignore").write_text("*\n", encoding="utf-8")
    return tmp


def prepare_records(run: RunContext) -> Path:
    run.records.mkdir(parents=True, exist_ok=True)
    run.records.chmod(0o700)
    return run.records


def run_environment(run: RunContext) -> dict[str, str]:
    env = {
        "TMPDIR": str(run.run_dir / "tmp"),
        "LM_BASED_RUN_DIR": str(run.run_dir),
        "LM_BASED_RUN_ID": run.run_id,
    }
    if run.trajectory:
        env["LM_BASED_TRAJECTORY"] = str(run.records / "trajectory.jsonl")
    return env


def cleanup_run(run: RunContext) -> None:
    """Delete the run's scratch folder (and .pi-run when no other run uses it)."""
    if run.keep:
        return
    shutil.rmtree(run.run_dir, ignore_errors=True)
    parent = run.run_dir.parent
    try:
        leftovers = {path.name for path in parent.iterdir()}
    except OSError:
        return
    if leftovers <= {".gitignore"}:
        shutil.rmtree(parent, ignore_errors=True)


def untracked_files(workspace: Path) -> set[str] | None:
    """Untracked, unignored files of a git workspace; None outside git."""
    try:
        result = subprocess.run(
            ["git", "-C", str(workspace), "ls-files", "--others", "--exclude-standard", "-z"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return {name for name in result.stdout.split("\0") if name}


def run_child(command: list[str], env: dict[str, str] | None = None) -> int:
    """Run Pi (or openshell) in the foreground and return its exit status.

    pi-local outlives the child to clean up after it, so the Ctrl-C meant for the child must
    not kill it. A no-op handler (not SIG_IGN, which the child would inherit) does that.
    """
    previous = signal.signal(signal.SIGINT, lambda *_: None)
    try:
        code = subprocess.Popen(command, env=env).wait()
    finally:
        signal.signal(signal.SIGINT, previous)
    return 128 - code if code < 0 else code


def report_run(run: RunContext, before: set[str] | None) -> list[str]:
    """Tell the person where the records are and what the session left in the workspace."""
    trajectory = run.records / "trajectory.jsonl"
    if trajectory.exists():
        print(f"pi-local: run {run.run_id} trajectory: {trajectory}", file=sys.stderr)
    broker_log = run.records / "broker.log"
    if broker_log.exists():
        print(f"pi-local: taxdesk-docs broker log: {broker_log}", file=sys.stderr)
    if run.keep:
        print(f"pi-local: kept run files in {run.run_dir}", file=sys.stderr)
    if before is None:
        return []
    created = sorted((untracked_files(run.workspace) or set()) - before)
    if created:
        print(f"pi-local: the session left {len(created)} new untracked file(s) in {run.workspace}:", file=sys.stderr)
        for name in created[:20]:
            print(f"  {name}", file=sys.stderr)
        if len(created) > 20:
            print(f"  ... and {len(created) - 20} more", file=sys.stderr)
    return created
