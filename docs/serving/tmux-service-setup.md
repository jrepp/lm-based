# Tmux Service Setup

Date: 2026-05-24
Status: Initial implementation

## Goal

Provide a simple local operator surface for bringing up related serving components in one
named tmux session.

The primary entrypoint is:

```bash
./up <service-set|service-name|model-slug>
```

The tmux session name is always:

```text
lm-based
```

## Components

| File | Purpose |
|---|---|
| `up` | uv-backed Python entrypoint that resolves targets and creates tmux windows |
| `support/tmux-service-shim` | per-service PTY lifecycle shim used inside every tmux service window |
| `support/model-service` | direct-model wrapper that adopts an already-running matching model or launches `run-server.py` |

The shim writes service-local runtime state under:

```text
.runtime/tmux/services/<service-name>/
```

Each service directory contains:

- `<service-name>.log`
- `shim.pid`
- `status`
- `last-exit`

Direct model windows use `support/model-service` so repeated `./up <slug>` runs do not
try to bind a duplicate worker if the requested slug is already healthy on the direct
worker port.

## Target Types

`./up` accepts three kinds of target.

### Service sets

Service sets expand to multiple services and their dependencies:

| Set | Services |
|---|---|
| `core` | stats poller, dashboard, status window |
| `direct` | direct default model worker, stats poller, dashboard, status window |
| `observability` | stats poller, dashboard |
| `manager` | stats poller, dashboard, status window |
| `swap` | llama-swap, stats poller, dashboard, status window |
| `all` | same as `swap` for now |

### Service names

Supported named services:

| Service | Purpose |
|---|---|
| `stats-poll` | runs `serve-manager stats-poll` against the direct llama-server port |
| `dashboard` | runs the embedded dashboard server |
| `llama-swap` | regenerates llama-swap config and runs the hot-swap proxy |
| `serve-manager-status` | periodically prints `serve-manager status` |

Dependencies are resolved automatically. For example:

```bash
./up dashboard
```

starts both `stats-poll` and `dashboard`.

### Model slugs

Any slug found in `models/*.json` can be used as a target:

```bash
./up qwen36-27b-mtp-ud-q5k-xl
```

This starts a direct worker window for that slug plus the stats poller and dashboard.

## Window Model

Each service runs in a named tmux window:

| Window | Service |
|---|---|
| `model-<slug>` | direct model worker |
| `stats` | stats poller |
| `dashboard` | embedded dashboard |
| `swap` | llama-swap proxy |
| `status` | serve-manager status loop |

Existing service windows are restarted by default when `./up` is rerun.

Use:

```bash
./up <target> --no-restart
```

to leave existing service windows untouched.

## Common Commands

List known targets:

```bash
./up --list
```

Start the default core service set:

```bash
./up
```

Preview a resolved target without starting tmux:

```bash
./up qwen36-27b-mtp-ud-q5k-xl --dry-run
```

Start and attach:

```bash
./up direct --attach
```

Attach later:

```bash
tmux attach -t lm-based
```

Kill the whole local service session:

```bash
tmux kill-session -t lm-based
```

## Interactive Output

When `./up` is run from a real terminal, it renders compact TUI-style tables using Rich.
When stdout is piped or captured, it falls back to stable plain text output for scripts
and tests.

## Design Notes

The `up` script intentionally does dependency resolution outside tmux, while each service
window runs through the shim. This keeps target selection deterministic and keeps per-service
lifecycle behavior consistent.

The shim is deliberately small:

- writes service status before and after execution
- records the shim PID
- tees stdout and stderr into a durable service log
- preserves the command exit status

The manager still owns generated serving state under `.runtime/serve-manager/`. The tmux
setup owns only the PTY/session layer and its own shim logs under `.runtime/tmux/`.
