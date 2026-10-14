# pi With a Local Direct Model

Configure [pi](https://github.com/earendil-works/pi-coding-agent) to use a model
served by this stack's **direct worker** — one model loaded at a time on
`127.0.0.1:8001`.

This covers the working setup for the Ternary Bonsai 27B MLX model, including
the sampler proxy that keeps low-bit models from looping and the thinking-mode
configuration.

## Architecture

```text
pi  ->  sampler-proxy (:8002)  ->  direct worker (:8001)
                                    mlx_lm | llama-server
```

- The **direct worker** is brought up by `./up <slug>` and serves exactly one
  model.
- The **sampler proxy** (`support/sampler-proxy`) injects `repetition_penalty`
  into completion requests. It is required for low-bit MLX models: `mlx_lm` has
  no repetition-penalty flag and pi does not send one, so without the proxy the
  ternary Bonsai model degenerates into repetition loops on long generations.
- pi points at the proxy (`:8002`), not the worker directly.

## Bring up the worker and proxy

```bash
./up ternary-bonsai-27b-mlx-2bit
# brings up: worker :8001 + sampler-proxy :8002
```

`./up` includes the sampler proxy automatically for MLX slugs (it is omitted for
GGUF models, which already get a repetition penalty from their serving profile).
The proxy defaults to `REPETITION_PENALTY=1.15`; run `./support/sampler-proxy`
directly with custom env to tune it.

The llama-server stats poller and dashboard are omitted because `mlx_lm.server` does not
provide llama.cpp's `/metrics` and `/slots` endpoints.

## Pinned Pi install

`./pi-local` does not use a global `pi`. It runs the version pinned in
`support/pi/package.json` (lockfile committed, `node_modules/` ignored):

| Package | Version | Provides |
|---|---|---|
| `@earendil-works/pi-coding-agent` | 1.2.0 | Pi itself |
| `@narumitw/pi-goal` | 0.54.11 | `/goal` autonomous objective loop (`goal_complete`, `goal_blocked`, `goal_wait`) |
| `pi-subagents` | 0.78.0 | `subagent` delegation, background runs, scout/worker/reviewer/oracle agents |

```bash
just pi-install   # npm ci in support/pi
```

Pi state lives in `.runtime/pi/agent` (`PI_CODING_AGENT_DIR`), not `~/.pi/agent`, so the
repo-managed config, sessions, and subagent artifacts never touch a global Pi setup.
The bootstrap registers both extensions in that directory's `settings.json` as local
package paths, disables install telemetry, and sets `PI_SKIP_VERSION_CHECK=1`.
Subagents run the same pinned CLI and inherit the agent directory and local model.

To upgrade, bump the versions in `support/pi/package.json`, run `npm install` there,
and review the extension source before committing the new lockfile — Pi extensions run
with full system access.

`/goal <objective>` works in the TUI. In print mode (`-p`) pi-goal 0.54.11 fails on
Pi 1.2.0 with `turn_end could not resolve the persisted assistant entry ID`; use the TUI
for goals until that is fixed upstream.

## Run pi-local from any directory

```bash
just pi-link            # ln -s <repo>/pi-local ~/.local/bin/pi-local
cd ~/src/some-project
pi-local                # Pi works in some-project, configured from this repo
```

The launching directory is Pi's workspace: tools run there, project `.pi/` settings and
`AGENTS.md` there apply, and sessions are grouped by that path. Everything else comes from
this repo: the pinned Pi in `support/pi`, the agent directory `.runtime/pi/agent`, the
extensions, and the model sidecars. The script resolves the repo through its own location,
so the symlink needs no environment setup. Its shebang pins `--python >=3.14` so a
`.python-version` near the symlink cannot select another interpreter.

## Hot-swapping models through llama-swap

```bash
./pi-local             # llama-swap if it answers /running, else the tmux-registered service
./pi-local --dry-run   # show every model and whether it is loaded
./pi-local --swap      # require llama-swap (fail instead of falling back)
./pi-local --tmux      # ignore llama-swap; use the tmux service discovery below
```

With no arguments, `./pi-local` first tries the llama-swap proxy from `serve-policy.yaml`. A
valid `/running` response identifies it as llama-swap, so this is not a port guess; it does
not need to run inside tmux. Every chat model with a sidecar is registered in Pi, so `/model`
lists them all; choosing one makes llama-swap load it on the next request and unload the
current one. Decision models (kev) are left out because they are classifiers, not chat models.

The starting model is, in order: `--model`, the model llama-swap already has loaded, the
model Pi last used, then the first registered model. Decision (kev) and OCR (GLM-OCR)
models are never chat candidates.

Each model's `contextWindow` comes from its profile's `ctx_size`, except for models that are
already loaded: pi-local reads the `n_ctx` the server actually allocated (via llama-swap's
`/upstream/<slug>/props`) and uses it when smaller. llama-server caps slot context at the
model's training window (see `docs/llama-server-cache-architecture-explainer.md`), so
Qwen3-Coder-Next's 1M profile serves 262144 tokens, and Pi must compact before that.

`/v1/models` lists every configured model; `/running` says which are in memory. The
bootstrap joins the two:

```text
llama-swap models:
  ○ qwen25-coder-7b-instruct         unloaded
  ● qwen3-coder-next-q6k             ready  <- selected
```

The repo extension `support/pi/extensions/llama-swap` shows the same state inside Pi:

- the footer shows what llama-swap currently holds (`swap: qwen3-coder-next-q6k ready`), refreshed every 3 s
- choosing an unloaded model warns that the next request cold-loads it and which model gets unloaded
- `/swap` opens a picker with ● loaded / ○ unloaded markers and switches to the chosen model

The extension only runs when `./pi-local` launches Pi against llama-swap; it sets
`LM_BASED_SWAP_URL` and `LM_BASED_PROVIDER` for it.

## Decision models as a tool: `decide_records`

The repo extension `support/pi/extensions/decide` gives the chat model a `decide_records`
tool backed by the local decision model (kev). The chat model writes typed questions; the
tool runs every record of a file through kev and returns a summary instead of the data, so
large files never enter the chat context.

| Input | Records |
|---|---|
| `.csv`, `.tsv` | one per row (header row = field names; quoted fields may span lines) |
| `.ndjson`, `.jsonl` | one per line (malformed lines are reported, not fatal) |
| `.json` | one per array element |
| `.log` | one per non-empty line |
| anything else (`.md`, `.txt`, …) | paragraph-aligned chunks of `chunk_chars` (default 6000) |

Questions use Pi's classifier types:

```json
{
  "topic":    {"type": "choice", "instructions": "Main topic?", "criteria": {"outage": "service down", "billing": "payments", "feature": "request"}},
  "urgent":   {"type": "bool",   "instructions": "Needs a response within the hour?"},
  "severity": {"type": "score",  "instructions": "How severe?", "criteria": ["cosmetic", "degraded", "broken", "data loss"]}
}
```

Other parameters: `fields` (columns sent to kev), `id_field`, `context` (shared background
added to every record), `offset`/`limit` (default 1000), `output` (`.csv` or NDJSON; default
`<path>.decisions.ndjson`), `min_confidence` (default 0.5), `concurrency` (default 8).

The output must differ from the input, including symlink and hardlink aliases. A completed
run replaces the output atomically. Cancelled runs leave any previous output intact and
do not publish partial results.

The result reports counts per choice, true/false totals, score distributions, failures, and
the least confident records; per-record answers are in the output file. On a 36-row ticket
CSV, kev labelled every topic correctly in 2.2 s with Coder-Next driving.

Wiring, and why it is not in `models.json`: Pi's `models.json` loader treats every entry as a
chat model, so classifier models must come from an extension provider. `./pi-local` puts the
decision models it finds on llama-swap into `LM_BASED_CLASSIFIERS`; the extension registers
them as the `lm-based-decision` provider using pi-ai's TypeSafe System One client. llama-swap
routes only OpenAI paths by model name, so the classifier base URL is
`http://127.0.0.1:8081/upstream/kev-4b-mlx-8bit/v1`. kev is in the llama-swap `small` group,
so it stays resident alongside the active chat model. Classifiers also work from `codemode`
scripts and from other extensions through `ctx.modelRegistry.classify()`.

When scripting `./pi-local -p`, close stdin (`< /dev/null`): Pi reads piped stdin as prompt
input and waits for it to end.

## PDF and image OCR

The `pdf_extract` tool uses `glm-ocr-q8_0` through llama-swap. Its sidecar downloads
both the language model and the required vision projector from
[ggml-org/GLM-OCR-GGUF](https://huggingface.co/ggml-org/GLM-OCR-GGUF).
PDF conversion also requires Ghostscript (`gs` on PATH).

```bash
./download_model.py glm-ocr-q8_0
./llama-swap-runner.py config
```

Restart llama-swap after regenerating its config unless it is watching for changes.
The OCR model belongs to the `small` group and stays out of Pi's chat picker.
The launcher passes its projector with `--mmproj` and checks that it exists before
starting the worker. `MMPROJ` can override the projector path.

New swap installs use the same pinned release as the Python wrapper. To replace an
older installed binary, stop the proxy and run `./llama-swap-runner.py ensure --overwrite`
before starting it again.

## Bootstrap Pi

Run the repository bootstrap after starting the model:

```bash
./pi-local
```

The bootstrap refuses to guess from open ports alone. It:

1. reads the live service registrations written by `support/tmux-service-shim`
2. verifies that each shim PID belongs to a running pane in the selected tmux session
3. chooses the sampler proxy, direct worker, or llama-swap endpoint from that service set
   (this path runs only with `--tmux`, or when llama-swap is not answering)
4. checks the selected endpoint's `/v1/models` response against model sidecars
5. merges an `lm-based` provider into `.runtime/pi/agent/models.json`
6. sets that provider and model as Pi's default, then launches Pi pinned to both

Other providers and settings are preserved. Before an existing Pi file changes, its previous
contents are copied to a sibling `.lm-based.bak` file.

Inspect the derived provider without changing Pi:

```bash
./pi-local --dry-run
```

Configure Pi without launching it:

```bash
./pi-local --configure-only
```

Unknown arguments are forwarded to Pi, so non-interactive use works through the same
verified bootstrap path:

```bash
./pi-local -p "Summarize this repository"
```

### Why each setting

| Setting | Reason |
| --- | --- |
| `baseUrl :8002` | Pi goes through the sampler proxy when its owned shim is running. |
| `apiKey: "local"` | Local servers ignore it, but pi hides a model from `/model` unless auth is present. Dummy value is fine. |
| `supportsDeveloperRole: false` | `mlx_lm`/`llama-server` do not understand the `developer` role; pi sends `system` instead. |
| `supportsReasoningEffort: false` | These servers do not accept `reasoning_effort`. |
| `maxTokensField: "max_tokens"` | They use `max_tokens`, not `max_completion_tokens`. |
| `reasoning: true` + `thinkingFormat: "qwen-chat-template"` | Bonsai is a thinking model. `mlx_lm` honors `chat_template_kwargs.enable_thinking` (and Bonsai's chat template reads it), and returns thinking in a `reasoning` field that pi parses. |
| `maxTokens: 8192` | Capped to avoid runaway generation on the single-slot server; raise if you want longer thinking traces. |

## Select the model

```bash
pi --list-models lm-based
# in the TUI, if switching back from another provider:
/model bonsai
```

The thinking toggle maps to the model's `enable_thinking`: on generates a
thinking trace, off does not.

## Tuning

The sampler proxy is controlled by environment variables:

| Variable | Default | Notes |
| --- | --- | --- |
| `REPETITION_PENALTY` | `1.1` | `1.1` mild → `1.3` strong. `1.15` is used for the ternary MLX model; raise it if output still loops, lower it if prose degrades. `1.0` disables injection. |
| `REPETITION_CONTEXT` | unset | How many recent tokens to penalize (upstream default otherwise). |
| `MIN_P` | unset | Optional min-p floor. |

The proxy only injects a value when the request does not already set it, so a
client that sends its own sampler params is never overridden.

## Restarts and worker adoption

`./up <slug>` keeps a healthy model window running by default, so repeated starts are
inexpensive. If a matching server was started outside the tmux session,
`support/model-service` adopts it instead of double-binding the port. It matches the
running server by slug **or** by the model directory path (mlx_lm and transformers report
the directory as the model id, not the slug).

## When to use this vs the routed path

The direct path serves one model at a time and is the simplest way to drive a
single local model from pi. To expose **multiple** models through one pi
provider with model-name routing, use the llama-swap path described in
[serving/hot-models.md](serving/hot-models.md).
