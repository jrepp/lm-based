# Managed voice job service

This service also runs general commands. See [local task queue and Pi progress](job-service.md)
for the shared tools and progress contract.

The voice workbench uses a small loopback HTTP service with a SQLite index. Pi is a
client; closing Pi does not abandon or cancel submitted work. This follows
[ADR-003](../docs-cms/adr/adr-003-tmux-service-set-launcher.md).

## Start and inspect

```bash
./up voice-jobs --add
./up --status
```

`--add` preserves other service windows. `voice` is a service set containing
`voice-jobs`; `all` also includes it. Start only this service when adding voice
support to an already-running host. No model worker or proxy is restarted.

The service listens on `127.0.0.1:8093`. All endpoints require a bearer token from
`.runtime/voice-workbench/token`, created with mode 0600. Pi reads this file without
putting the token into tool output. Override client address/token path through
`LM_VOICE_JOBS_URL` and `LM_VOICE_JOBS_TOKEN_FILE`. The service accepts `--port` and
`--root` for isolated installations. Never expose this local file-access API publicly.

Pi tools:

- `voice_library(action="health")`: queue counts, active job, disk space and last cleanup.
- `voice_library(action="jobs")`: most recent 200 indexed jobs.
- `voice_library(action="voices")`: indexed trained voices, IDs, names and manifest paths.
- `voice_library(action="cleanup")`: dry-run retention plan by default.
- `voice_job(job_id=...)`: durable state, progress, result and bounded recent log.

`voice_render` accepts an indexed voice ID, an unambiguous name, or a manifest path.
The existing preset/reference `/speech-voice` menu remains separate from trained voices.
Restart existing Pi sessions to load changed extensions.

## SQLite and files

All managed state lives in `.runtime/voice-workbench/`:

| Path | Purpose |
| --- | --- |
| `index.sqlite3`, `-wal`, `-shm` | Queue, state transitions, dependency edges, voice index and cleanup history |
| `jobs/job-*/request.json` | Submitted worker request |
| `jobs/job-*/status.json` | Worker result; SQLite is authoritative for lifecycle state |
| `jobs/job-*/progress.json` | Latest worker stage and available progress counts |
| `jobs/job-*/job.log` | Worker output, rotated at 4 MiB with two backups |
| `jobs/job-*/checkpoint/` | New trained weights; retained while indexed |
| `jobs/job-*/trained-voice.json` | Indexed voice manifest |
| `service.jsonl` | Structured lifecycle events, rotated at 4 MiB with three backups |
| `service.lock`, `gpu.lock` | Single service owner and cooperative GPU exclusion |

SQLite uses WAL and FULL synchronous writes. Schema version is recorded with
`PRAGMA user_version`. Queue entries store creation/update timestamps, request,
result/error, artifact bytes, dependencies and pin state. Cleanup runs retain start/end,
state, dry-run flag, candidate job IDs, bytes and errors. Expired jobs remain as
index tombstones. Disk accounting covers completed managed job directories; it excludes
shared caches, legacy jobs and the current worker's growing output.

Datasets record original speaker labels and transcripts, corrections, review notes,
and selected clip IDs. Source files outside the workbench are read-only inputs.

## Lifecycle and limits

The service admits at most 64 queued/running jobs and runs one worker at a time.
GPU work waits for the cooperative workbench lock; workers also check memory before
loading models. This does not reserve resources against unrelated model servers or
the resident speech API. The service never unloads another server.

A worker guardian owns the actual runtime process group. A pipe from the service
stays open throughout the job. Cancellation, service shutdown, or service death
closes that pipe; the guardian sends TERM, waits up to five seconds, then kills
remaining members of its owned process group. Cancellation never signals a saved PID.
SIGINT, SIGTERM and SIGHUP stop admission and interrupt the active job. Queued jobs
remain for the next service start; interrupted jobs require explicit resubmission.
The startup lock prevents two services from dispatching the same store.

Default wall-clock limit is two hours (`--max-seconds`); runtime setup and downloads
count against it. Startup requires at least 5 GiB free disk per dispatch. This is
an admission check, not an output quota. A worker exit without a successful result
becomes a durable failed job. Progress has stage timestamps, not an independent
heartbeat; a slow unchanged stage alone does not prove a hang.

## Retention

Cleanup runs on startup and hourly, using a seven-day terminal-job retention window
(`--retention-days`). It only owns directories created through this service's index.

Indexed trained voices are pinned, together with all upstream dataset/analysis jobs.
Any recent or active job also protects its transitive input dependencies. Cleanup
never deletes external source files, shared model caches, legacy job directories,
or model sidecars. Existing completed legacy training artifacts are indexed read-only
on startup and excluded from cleanup.

Use dry-run first to inspect candidates. `voice_library(action="cleanup", dry_run=false)`
executes the same policy immediately. There is intentionally no automatic trained-voice
expiry or unsafe unpin/delete endpoint. Retiring voices requires a future explicit
library-management operation. Back up the workbench as a unit; do not delete individual
job folders or copy only the SQLite file while WAL writes are active.

## API and observability

Authenticated endpoints:

| Method | Path | Meaning |
| --- | --- | --- |
| GET | `/health` | Queue counts, active job, disk and cleanup status |
| GET | `/metrics` | Prometheus text counters/gauges for job states, uptime, voices and disk |
| GET / POST | `/jobs` | List recent jobs / submit request |
| GET | `/jobs/{id}` | Result, stage, timestamps, log tail |
| POST | `/jobs/{id}/cancel` | Cancel queued or active job |
| GET | `/voices` | Trained-voice index |
| GET / POST | `/cleanup` | Recent cleanup runs / dry-run or execute retention |

The tmux shim also keeps its normal service log/status under
`.runtime/tmux/services/voice-jobs/`. Its tee log follows the existing manager's
retention behavior; the service's own structured log and worker logs rotate separately.
HTTP request bodies are limited to 1 MiB. The authenticated API also accepts explicit command jobs; see the shared task contract.

## Sustaining work

See the [initial review](../docs-cms/memos/memo-003-voice-workbench-sustaining-review.md).
This service addresses ownership, queueing, indexing, dependency-aware cleanup and
observability. Follow-up work remains: restartable analysis stages, long-recording
chunking, content hashes/model revision provenance, fully locked transitive runtimes,
listening-based quality review, normalized WER, speech API admission/cancellation,
and a unified preset/reference/trained-voice selection UI.

Run lifecycle tests without models or live services:

```bash
uv run --frozen python -m unittest discover -s tests -p 'test_voice*.py'
node --test support/pi/extensions/voice-workbench/index.test.ts
```
