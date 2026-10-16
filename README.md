# lm-based

Local LLM serving for an Apple Silicon Mac: a registry of model sidecars,
on-demand serving behind the [llama-swap](https://github.com/mostlygeek/llama-swap)
hot-swap proxy, and agent harnesses, so every local model is reachable through
one OpenAI-compatible endpoint.

```text
   Pi / OpenCode / open-webui / any OpenAI client
                      │
       llama-swap  127.0.0.1:8081/v1     ← loads the model a request names
          /              \
   llama-server         mlx_lm
   (GGUF models)        (MLX models)
```

---

## Quickstart

You need [uv](https://docs.astral.sh/uv/) and `llama-server`
(`brew install llama.cpp`). tmux is optional.

```bash
git clone https://github.com/jrepp/lm-based && cd lm-based
./up init      # pick a starter model set for this Mac's memory
./up doctor    # check prerequisites, downloads, and memory
./up pull      # download the enabled models (Hugging Face)
./up           # start llama-swap in a tmux session
```

Then point a client at `http://127.0.0.1:8081/v1`:

```bash
curl -s http://127.0.0.1:8081/v1/models
curl -s http://127.0.0.1:8081/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model": "mistral-7b-instruct-v03-q4km", "messages": [{"role": "user", "content": "hi"}]}'
```

The first request for a model loads it, which takes a few seconds. Requests
for another chat model swap it in.

Without tmux, use `./up --foreground` to run llama-swap in the current terminal.
`./up --status` shows what's running, and `./up --down` stops it. If llama-swap
isn't installed, `./llama-swap-runner.py ensure` puts a copy in `.runtime/bin`.

### Starter model sets

`./up init` writes `serve-policy.local.yaml`, which is gitignored. It's merged
over the tracked `serve-policy.yaml`, which defaults to the compact set.

| Preset | Host memory | Chat models (one loaded at a time) | Always loaded |
| --- | --- | --- | --- |
| `compact` | under 48 GB | Mistral 7B | GLM-OCR |
| `standard` | 48–95 GB | Qwen3.5 35B-A3B, Qwen3.6 27B, Mistral 7B | GLM-OCR |
| `workstation` | 96 GB and up | Qwen3-Coder-Next, Qwen3.5 35B-A3B, Qwen3.6 27B | GLM-OCR |

Pass `./up init --preset <name> --force` to choose a different set. To serve
any other registered model, edit `models.enabled` and the routing groups in
your local file. `./download_model.py --list` shows every registered model and
whether it's downloaded. llama-swap skips enabled models that aren't
downloaded, so a partial download still starts.

---

## How it works

You edit declarations, and generators produce the runtime config:

1. **Sidecars**: `models/*.json` describe each model artifact: where to
   download it, its kind (chat, OCR, decision), its native context, and the
   serving profile. Profiles in `lm_launcher/profiles.py` turn that into
   llama-server or mlx_lm flags.
2. **Policy**: `serve-policy.yaml` plus your `serve-policy.local.yaml` decide
   which models llama-swap serves, and which run side by side. A `swap: true`
   group holds one model at a time, and a `swap: false` group stays loaded
   beside it.
3. **Serve**: `./up` regenerates the llama-swap config from the sidecars and
   policy, then starts llama-swap. llama-swap starts each model worker through
   `run-server.py` the first time a request names it.

Weights download to `artifacts/` (set `MODEL_DIR` in `.env` to use another
disk). To run one model directly on `:8001` without the proxy, use
`./up <slug>` or `MODEL_SLUG=<slug> ./run-server.py`.

---

## Clients

| Client | How |
| --- | --- |
| Any OpenAI client | Base URL `http://127.0.0.1:8081/v1`, model = a slug from `/v1/models` |
| [Pi](https://github.com/earendil-works/pi-coding-agent) | `just pi-install` once, then `./pi-local`. Runs a repo-pinned Pi with local models and repo extensions ([docs](docs/pi-local-model.md)) |
| OpenCode | `./opencode-local` ([docs](docs/opencode-local-models.md)) |
| open-webui | [docs/open-webui-local-server.md](docs/open-webui-local-server.md) |

---

## Extras

None of these are needed to serve models locally. Each needs its own tools.

| Extra | What it adds | Needs |
| --- | --- | --- |
| Observability | `./up observability --add`: llama-server stats poller and dashboard on `:9092` | Go |
| serve-manager | `just serve-plan-managed` and related recipes: staged HAProxy + llama-swap generations ([design](docs/serving/README.md)) | Go, HAProxy |
| ClawRouter | `./route-config.py`: routes between local and cloud models, direct or through an x402/USDC proxy ([docs](docs/clawrouter-operations.md), [credentials](docs/credentials.md)) | API keys |
| Decision models | `kev-4b-mlx-8bit`: a TypeSafe System One decision model that Pi's `decide` tool uses ([ADR-005](docs-cms/adr/adr-005-mlx-decision-model-serving-kev.md)) | MLX |
| Pi sandbox | `./pi-local --sandbox`: runs Pi in an OpenShell microVM with a host broker for Tax Desk documents | OpenShell |
| Host audit | `just host-doctor`: model servers outside llama-swap, wired memory, sidecar drift | macOS |

The full stack, including Tailscale, Telegram, and cloud routing, is drawn in
[docs/architecture.html](docs/architecture.html).

---

## Where things live

| Path | Role |
| --- | --- |
| `up` | Front door: `init`, `doctor`, `pull`, and the tmux services |
| `models/*.json` | Sidecar registry: artifacts, upstream cards, launcher profiles |
| `serve-policy.yaml` | Shared default policy: ports, enabled models, model groups |
| `serve-policy.local.yaml` | This host's overrides (gitignored, from `./up init`) |
| `lm_launcher/` | Launcher package: backends, profiles, settings, onboarding |
| `llama_swap/` | llama-swap binary install, config generation, process wrapper |
| `download_model.py` | Fetch models by slug, or `--enabled` for the whole policy |
| `artifacts/`, `runs/`, `.runtime/` | Downloaded weights, run captures, generated config (gitignored) |
| `docs/` | Reference docs, indexed in [docs/README.md](docs/README.md); model research in [docs/research/](docs/research/) |
| `docs-cms/` | Decision records (ADRs, RFCs, memos) |

---

## Contributing

- Generated files are never edited by hand: `llama-swap.yaml`,
  `clawrouter.json`, and `.runtime/`. Change the inputs and regenerate.
- To add a model, follow the checklist and sidecar schema in
  [AGENTS.md](AGENTS.md).
- Checks: `uv run --frozen python -m unittest discover -s tests`,
  `go test ./...`, `./route-config.py --validate`, and
  `pre-commit run --all-files`.
