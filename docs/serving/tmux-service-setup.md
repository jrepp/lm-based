# Tmux Service Setup

Date: 2026-05-24
Status: Initial implementation

## Goal

Provide a simple local operator surface for bringing up related serving components in one
named tmux session.

The single lifecycle entrypoint is:

```bash
./up <service-set|service-name|model-slug>
```

It also reports, restarts, and stops the service session:

```bash
./up --status
./up <target> --restart
./up --down
```

The tmux session name is always:

```text
lm-based
```

## Components

| File | Purpose |
| --- | --- |
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
- `session`
- `status`
- `last-exit`

Direct model windows use `support/model-service` so repeated `./up <slug>` runs do not
try to bind a duplicate worker. The wrapper can also adopt a matching server that was
started outside the tmux session.

## Target Types

`./up` accepts three kinds of target; with none it starts `swap`. The setup commands
`./up init`, `./up doctor`, and `./up pull` are not targets (see the README quickstart).
Without tmux, `./up <target> --foreground` runs the target's main service (llama-swap or
the model worker) in the current terminal.

### Service sets

Service sets expand to multiple services and their dependencies:

| Set | Services |
| --- | --- |
| `swap` | llama-swap (the default target; needs no Go) |
| `direct` | direct worker for `MODEL_SLUG` from the environment or `.env` |
| `observability` | stats poller, dashboard, status window (Go) |
| `all` | `swap` plus `observability` |

Add observability beside a running target with `./up observability --add`.

### Service names

Supported named services:

| Service | Purpose |
| --- | --- |
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

MLX models also start the sampler-defaults proxy. For a GGUF worker, add the stats poller
and dashboard with `./up observability --add`. The poller only works with llama-server,
because it reads the llama.cpp-specific `/metrics` and `/slots` endpoints.

## Window Model

Each service runs in a named tmux window:

| Window | Service |
| --- | --- |
| `model-<slug>` | direct model worker |
| `stats` | stats poller |
| `dashboard` | embedded dashboard |
| `swap` | llama-swap proxy |
| `status` | serve-manager status loop |
| `sampler` | sampler-defaults proxy for MLX workers |

`./up <target>` treats the target as desired state:

- running target services are kept
- exited target services are respawned
- service windows outside the target are stopped
- the `control` window is always preserved

This makes repeated starts inexpensive and ensures switching targets does not leave stale
workers or dashboards behind.

Restart all services in the target explicitly:

```bash
./up <target> --restart
```

To add a target without stopping other service windows, use `--add`.

Service panes use tmux's `remain-on-exit` behavior. A failed service therefore remains
visible as an exited pane with its last output, and the next `./up <target>` respawns it.

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

Configure and launch Pi against the running model:

```bash
./pi-local
./pi-local -p "Summarize the repository architecture"
```

The bootstrap reads verified tmux shim registrations, selects the active client-facing
endpoint, checks `/v1/models`, and derives model metadata from the matching sidecar and
launcher profile. It merges the resulting `lm-based` provider into
`~/.pi/agent/models.json`, preserves unrelated Pi configuration, and launches Pi pinned to
that provider and model. Use `./pi-local --configure-only` to update configuration without
launching Pi or `./pi-local --dry-run` to inspect the derived provider without writing it.

Attach later:

```bash
tmux attach -t lm-based
```

Show concise lifecycle status:

```bash
./up --status
```

Stop the whole local service session:

```bash
./up --down
```

Shutdown terminates verified service process groups before removing tmux. If tmux was
removed externally and left a registered shim behind, `./up --status` reports the orphan
and `./up --down` recovers it.

## Interactive Output

When `./up` is run from a real terminal, it renders compact TUI-style tables using Rich.
When stdout is piped or captured, it falls back to stable plain text output for scripts
and tests.

## Design Notes

The `up` script resolves the selected target, reconciles the dedicated tmux session to that
service set, and uses tmux's native window respawn support. This keeps lifecycle state in one
place and avoids nested keep-alive shells.

The shim is deliberately small:

- writes service status before and after execution
- records the shim PID
- tees stdout and stderr into a durable service log
- preserves the command exit status
- records termination signals

The manager still owns generated serving state under `.runtime/serve-manager/`. The tmux
setup owns only the PTY/session layer and its own shim logs under `.runtime/tmux/`.
