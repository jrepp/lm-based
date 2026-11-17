# Local task queue and Pi progress

The shared job service runs long commands and voice tasks independently of a Pi
session. Per ADR-003, tmux owns the service. SQLite owns task lifecycle; an owned
process group provides cancellation. Existing voice tools, port 8093, token file,
and `.runtime/voice-workbench/` storage remain compatible.

## Use from Pi

Start the service with `./up jobs --add`, then launch a new `./pi-local` session.
The `jobs` target aliases the existing `voice-jobs` service, so starting both does
not create two queues. Existing running services need an operator-managed restart
to load this implementation; starting an already-running target does not upgrade it.

- `job_start(title, argv, cwd?, dependencies?)` queues a command and returns its ID.
- `job_status(job_id, wait_seconds?, cancel?)` reads progress/results and recent logs.
  Waiting streams snapshots for up to 60 seconds, plus an in-flight HTTP request
  timeout. Aborting a wait leaves the task running. Set `cancel=true` to cancel it.
- `jobs(action="list")` rediscovers recent tasks, including voice work.
- `jobs(action="health")` shows queue counts, active progress, disk and cleanup.

The Pi footer refreshes every five seconds and shows queue depth, active stage,
counts when supplied, and stale guardian heartbeats. Reconnecting restores this
view from the service. No background model turns are injected by monitoring.

Example tool input:

```json
{
  "title": "Run Python checks",
  "argv": ["uv", "run", "--frozen", "python", "-m", "unittest", "discover", "-s", "tests"]
}
```

Pi resolves `cwd` against its workspace; direct API clients must provide an
existing absolute directory. `argv` is passed directly to the executable. Shell
syntax requires explicitly invoking a shell. Commands inherit the service's
host environment and permissions, not Pi's interactive shell environment.
Environment overrides are not accepted in requests. This is local host command
execution, not a sandbox; the OpenShell broker and network policy are unchanged.

## Progress contract

Every command receives `LM_JOB_ID`, `LM_JOB_DIR`, and `LM_JOB_PROGRESS_FILE`.
An unmodified executable still gets lifecycle, elapsed time, logs, exit status,
and a guardian heartbeat. For structured progress, atomically replace
`LM_JOB_PROGRESS_FILE` with a JSON object:

```json
{"stage":"processing","completed":12,"total":50,"message":"Processing records"}
```

Python tasks that can import the project may use:

```python
from lm_launcher.job_progress import report

report("processing", completed=12, total=50, message="Processing records")
```

The helper validates counts and publishes atomic snapshots. Other languages can
write a temporary file beside the progress file and rename it over the target.
Results expose `progress_age_seconds` separately from `heartbeat_age_seconds`.
A guardian writes heartbeats every two seconds; older than fifteen seconds is
reported as `monitor_stale`. A healthy guardian does not prove a progressing
command, and stale progress does not automatically kill a slow task. Only lifecycle
state `completed` means success; percentages and log messages cannot mark success.
Command exit zero completes the task; other exits and launch errors fail it.

## Ownership and limits

The shared queue admits 64 active/queued tasks and dispatches one at a time.
Voice tasks retain their GPU checks. Generic commands must manage their own
resource requirements; the service does not unload models or reserve GPU memory.
Do not submit a task that waits for another task in this serial queue.

The service default deadline is two hours, including setup. Configure longer work
with `python -m lm_launcher.job_service --max-seconds SECONDS` when starting an
isolated service or updating its launch configuration. Commands must remain in
the foreground and must not daemonize or escape their owned process group.
Cancellation, deadline expiry, and service shutdown terminate that group; Pi exit
alone does not. Service restart marks previously running tasks interrupted;
queued tasks remain queued. Interrupted work requires explicit resubmission.

Explicit `dependencies` must be completed managed IDs. These edges protect input
artifacts from retention, not schedule a future DAG. Managed logs/progress expire
under the existing retention policy. Output files written in a command's working
directory remain the command's responsibility and are never cleaned by this service.

## API and configuration

The existing authenticated `/jobs`, `/jobs/{id}`, `/jobs/{id}/cancel`, `/health`,
and `/metrics` endpoints now serve every task kind. Submit commands with
`kind="command"`, `title`, `argv`, and `cwd`. List entries include progress,
queue position and timing without logs/results; detail returns a bounded log tail.
Prometheus exposes `local_jobs{state="..."}` alongside legacy `voice_jobs` gauges.

Pi accepts `LM_JOBS_URL` and `LM_JOBS_TOKEN_FILE`, with the legacy
`LM_VOICE_JOBS_URL` and `LM_VOICE_JOBS_TOKEN_FILE` as fallbacks. Defaults remain
loopback port 8093 and `.runtime/voice-workbench/token`. Bearer tokens never appear
in tool results. Both Python entry points share the same store lock. The store
implementation remains in `lm_launcher/voice_jobs.py` for compatibility;
`lm_launcher/job_service.py` is the general entry point.

See [service storage and retention](voice-job-service.md) for recovery, disk
admission, log rotation, voice dependency pinning and cleanup details.
