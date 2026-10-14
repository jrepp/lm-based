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
model Pi last used, then the first registered model. Only sidecars with `model.kind: chat`
are chat candidates; `decision` models (kev) go to `decide_records` and `ocr` models
(GLM-OCR) to `pdf_extract` (pi-local passes the hot OCR model as `LM_BASED_OCR_MODEL`).

Each model's `contextWindow` is its profile's `ctx_size`, capped at the sidecar's
`model.context_length` (the native window; llama-server caps slots there anyway, see
`docs/llama-server-cache-architecture-explainer.md`). For models that are already loaded,
pi-local also reads the `n_ctx` the server actually allocated (via llama-swap's
`/upstream/<slug>/props`) and uses it when smaller.

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

### Reading confidence

kev returns the full probability distribution for every answer. Its choice `confidence` is
`(p_max - 1/K) / (1 - 1/K)`: 0 at a uniform distribution over the K options, 1 at certainty.
It shrinks as K grows, so a 30-option question with a clear winner at p = 0.4 reports
confidence 0.38. Bool confidence is `|2p - 1|`. To compare questions with different option
counts, the summary also gives, per question:

| Field | Meaning |
|---|---|
| `options`, `uniform_probability` | K and 1/K, the "no idea" baseline |
| `mean_top_probability` | mean probability of the answer given |
| `mean_margin` | mean lead of the answer over the runner-up |
| `mean_probability_when_chosen` | per option, how sure kev was when it picked it |
| `confidence_histogram` | answers per confidence band |

Results files carry `margin`, `runner_up` and `runner_up_probability` on every choice answer,
and `low_confidence` entries show them too.

### Abstaining, examples, and chained stages

- `abstain: {"choice": "unsure"}` adds an "unsure" option to every choice question (with
  `description` as its criterion). `min_confidence` and `min_margin` also count low or close
  answers as unsure. Unsure answers are reported (`abstained` in the summary, per record in the
  results), never forced into an option. kev has no abstain of its own; this is that option
  plus thresholds applied by the tool.
- `examples: [{"record": {...}, "answers": {"category": "medical"}}]`, or
  `examples_from: {"path": "labeled.ndjson", "answer_fields": {"category": "category"}, "limit": 12}`
  to pick rows a person already labeled, round-robin across answers. Examples go into the
  state ahead of the record (`labeled_examples`, then `record`), at most 24 per stage. The
  shared prefix is cached by kev, but examples still count against its state context, so keep
  them few and narrow (use `fields`).
- `stages` replaces `questions` with an ordered list of stages, each with its own
  `questions`, `examples`/`examples_from`, `abstain`, `context`, and a `when` filter on earlier
  stages' answers (`is`, `min_probability`, `min_confidence`, `min_score`/`max_score`; a list
  means all must hold). Filters only look back; at most 6 stages. A record stops at the first
  stage where it abstains, errors, or fails a filter, and is marked `outcome`
  (`complete`, `filtered`, `abstained`, `error`) and `stopped_at`. With `otherwise: "continue"`
  a failed filter skips that stage instead, which is how branches are written.

The tax-row pattern: a bool relevance question first, then a short choice only for relevant
rows, with an abstain option:

```json
{
  "path": "rows.ndjson", "id_field": "row", "fields": ["payee", "amountCents", "memo"],
  "stages": [
    {"id": "relevance", "questions": {"tax_relevant": {"type": "bool",
      "instructions": "Is this a tax-relevant household payment (not a transfer between own accounts, utility, loan or card payment)?"}}},
    {"id": "category",
     "when": {"stage": "relevance", "question": "tax_relevant", "is": true, "min_probability": 0.8},
     "questions": {"category": {"type": "choice", "instructions": "Which category?",
       "criteria": {"medical": "doctors, pharmacy", "charity": "donations", "childcare": "daycare, nanny"}}},
     "abstain": {"choice": "unsure"},
     "examples_from": {"path": "categorized.ndjson", "answer_fields": {"category": "category"}}}
  ]
}
```

The staged summary gives `outcomes`, `stopped_at` (per stage: filtered / abstained / error),
`paths` (counts per route, such as `relevance>category` or `relevance | filtered@category`),
and per stage `reached`, `skipped`, `filtered`, `abstained`, `errors` and the question
statistics above. Each NDJSON result line holds every stage's answers with probabilities.
With a `.csv` output, columns are `<stage>.<question>`, `_confidence`, and `_margin` for
choice questions. The single-stage shape keeps its original results layout; with `abstain`
it adds an `abstained` field (CSV: a final `abstained` column).

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

## Run files and trajectories

Every launch (sandboxed or not) gets a run id and:

- a scratch folder in the workspace, `.pi-run/<run-id>/`, whose `tmp/` is Pi's `TMPDIR`.
  `.pi-run/` holds a `.gitignore` of `*`, so git never lists it. It is deleted when Pi exits;
  `--keep-run-files` keeps it.
- a records folder outside the workspace, `.runtime/pi/runs/<run-id>/` (gitignored, mode 700):
  `trajectory.jsonl` lists every user prompt, assistant message, tool call with its arguments,
  and tool result (text clipped at 256 KiB, with the full length and sha256), so the numbers in
  a model's report can be checked against what the tools returned. `--no-trajectory` turns it
  off. With household data, the trajectory holds household data too: delete old runs when
  they are no longer needed.

The `run-record` extension (`support/pi/extensions/run-record`) writes the trajectory, tells
the model where scratch files go, and blocks `write`/`edit` calls into shared temp folders
(`/tmp`, `/var/folders`). Bash commands are not intercepted. After an unsandboxed run,
pi-local lists new untracked files the session left in a git workspace.

## Sandboxed launches and Tax Desk

```bash
./pi-local --sandbox                    # OpenShell microVM; egress only to the host gateway
./pi-local --sandbox --no-taxdesk       # the same without the taxdesk-docs broker
./pi-local --sandbox --keep-run-files   # keep .pi-run/<run-id> inside the VM's workspace copy
```

`--sandbox` runs Pi in an OpenShell microVM: the workspace, the pinned Pi, and the agent
directory are uploaded, and the policy allows only the node binary to reach the sandbox
gateway (`LM_BASED_SANDBOX_GATEWAY`, default `192.168.127.254`) on the llama-swap port.
Decision models reach `decide_records` through the same gateway. The VM works on a copy:
files it writes are not synced back to the host workspace.

The Tax Desk CLI (`taxdesk-docs`) is a macOS binary that reads its credential from the login
Keychain and calls the Tax Desk server over HTTPS, so it cannot run in the VM. When pi-local
finds it on the host (`TAXDESK_DOCS_BIN`, then `PATH`, then `./dist/taxdesk-docs` in the
launch directory) it starts a broker (`lm_launcher/taxdesk_broker.py`, ADR-006) for the
session and stops it on exit:

- it listens on `127.0.0.1:<ephemeral port>` (`LM_BASED_TAXDESK_BROKER_PORT` to pin it); the
  policy gains one rule for that port on the gateway, for node only
- inside the VM, `taxdesk-docs` on `PATH` is a shim (`support/pi/sandbox/`) that forwards
  argv and stdin to the broker with a per-launch token, writes `--out` files locally (mode 600),
  and sends `--body <file>` as stdin
- the broker runs only allowlisted subcommands with validated arguments: `manifest`, `whoami`,
  `context`, `list`, `next`, `get`, `text`, `propose`, `tables`, `table`, `overlay`, `suggest`,
  `report`, `txns`, intersected with the host binary's `manifest`. Never `login`, `logout`,
  `--url`, or `--help`.
- the binary runs with a minimal environment (HOME, USER, PATH, and the host's own
  `TAXDESK_URL`/`TAXDESK_CA`) in a private temporary directory; the VM never sees the
  credential, the host environment, or host paths
- `.runtime/pi/runs/<run-id>/broker.log` records command names, exit codes, and durations only

To work on Tax Desk data from the sandbox, a person first runs `bun run login` in the Tax Desk
checkout (in their own terminal, outside the sandbox), then:

```bash
cd ~/src/taxes                     # the Tax Desk checkout (its skills load from .agents/skills)
pi-local --sandbox                 # finds ./dist/taxdesk-docs and starts the broker
```

The in-sandbox trajectory is downloaded to `.runtime/pi/runs/<run-id>/` when Pi exits.

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
