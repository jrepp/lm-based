# lm-based

Local LLM infrastructure: GGUF model registry, llama-server launcher, smart routing to local and cloud backends, and supporting tooling.

```
Tailscale / Telegram / open-webui
           │
      Claw / Hermes agents
           │
         llama-swap          ← hot-swap reverse proxy for any OpenAI-compatible server
        /          \
 llama-server    Cloud APIs
 (local GGUF)    (direct or x402 proxy)
```

See [`docs/architecture.html`](docs/architecture.html) for the interactive diagram.

---

## Two ways to serve local models

### llama-swap (recommended)

Hot-swap proxy that automatically loads the right `llama-server` on demand.
Handles concurrent models via a solver, with zero custom config per model.

```bash
# 1. Install the llama-swap binary
./llama-swap-runner.py ensure

# 2. Generate config from your existing model sidecars
./llama-swap-runner.py config

# 3. Start the proxy
./llama-swap-runner.py start
# → proxy available at http://127.0.0.1:8080
# → UI at http://127.0.0.1:8080/ui

# Or via just:
just swap-ensure
just swap-config
just swap-start
```

Switch models by passing the model slug in any OpenAI API request — llama-swap
loads the right server automatically.

### Direct llama-server (one model at a time)

```bash
cp .env.example .env
$EDITOR .env   # set MODEL_SLUG
./run-server.py
# → available at http://127.0.0.1:8001/v1
```

---

## Prerequisites

- [`llama-server`](https://github.com/ggml-org/llama.cpp) on your PATH (or set `LLAMA_SERVER_BIN` in `.env`)
- A HuggingFace account (free) if downloading gated models

---

## Download a model

```bash
./download_model.py --list
./download_model.py --model gemma4-e2b-uncensored-aggressive-q4kp
```

---

## Connect a client

**Any OpenAI-compatible client** — point it at `http://127.0.0.1:8080/v1` (llama-swap) or `http://127.0.0.1:8001/v1` (direct).

**open-webui** (Docker):

```bash
docker run -d --name open-webui --restart always \
  -p 3000:8080 \
  --add-host=host.docker.internal:host-gateway \
  -e OPENAI_API_BASE_URL=http://host.docker.internal:8080/v1 \
  -e OPENAI_API_KEY=dummy \
  -v open-webui:/app/backend/data \
  ghcr.io/open-webui/open-webui:main
```

Then open `http://localhost:3000`. See [docs/open-webui-local-server.md](docs/open-webui-local-server.md) for more.

---

## Routing config (ClawRouter / cloud providers)

```bash
./route-config.py             # regenerate clawrouter.json
./route-config.py --status    # summarise current config
./route-config.py --providers # credential status per cloud provider
./route-config.py --doctor    # full health check
./route-config.py --validate  # lint sidecars only
```

---

## Available models

| Slug | Family | Quant | Size |
|------|--------|-------|------|
| `gemma4-e2b-uncensored-aggressive-q4kp` | Gemma 4 2B | Q4_K_P | 3.4 GB |
| `mistral-7b-instruct-v03-q4km` | Mistral 7B Instruct v0.3 | Q4_K_M | 4.4 GB |
| `qwen25-coder-7b-instruct` | Qwen2.5-Coder-7B-Instruct | BF16 | snapshot |
| `qwen3-coder-next-iq4xs` | Qwen3-Coder-Next | IQ4_XS | — |
| `qwen35-35b-a3b-q4km` | Qwen3.5 35B A3B | Q4_K_M | 22 GB |
| `qwen36-27b-q6k` | Qwen3.6-27B | Q6_K | 22.5 GB |
| `qwen36-27b-mtp-ud-q5k-xl` | Qwen3.6-27B-MTP | UD-Q5_K_XL | — |

Full metadata: [`docs/model-card-index.md`](docs/model-card-index.md)

---

## Key commands

```bash
# Guardrails
pip install pre-commit && pre-commit install

# Model management
./download_model.py --list
./download_model.py --model <slug>
./build_gguf.py --model <slug> --outtype bf16
./build_gguf.py --model <slug> --outtype bf16 --quantize Q6_K

# llama-swap (hot-swap proxy)
./llama-swap-runner.py ensure   # install binary
./llama-swap-runner.py config   # generate yaml from sidecars
./llama-swap-runner.py start    # launch proxy on :8080
./llama-swap-runner.py status   # show loaded models
./llama-swap-runner.py logs     # stream logs

# Direct llama-server (one model at a time)
./run-server.py                    # start (reads .env)
MODEL_SLUG=<slug> ./run-server.py  # override model

# Routing / cloud config
./route-config.py             # regenerate clawrouter.json
./route-config.py --status    # summarise current config
./route-config.py --providers # credential status per cloud provider
./route-config.py --doctor    # full health check
./route-config.py --validate  # lint sidecars only

# Run analysis
./summarize_run.py --run <run-dir>
```

Markdown lint guardrails are enforced through `.pre-commit-config.yaml` using `markdownlint-cli2` over `README.md`, `AGENTS.md`, `CLAUDE.md`, and `docs/*.md`.

---

## Repo layout

| Path | Purpose |
|------|---------|
| `models/*.json` | Sidecar metadata per GGUF or Transformers snapshot (schema_version 1) |
| `lm_launcher/` | Python package: launcher, profiles, settings, run capture |
| `llama_swap/` | Python package: llama-swap binary install, YAML config generation, wrapper |
| `run-server.py` | Entry point for direct llama-server mode |
| `llama-swap-runner.py` | Entrypoint for llama-swap proxy mode |
| `route-config.py` | Generate and inspect routing config |
| `.env.example` | Template for all environment variables |
| `docs/` | Architecture, credentials, operations, model index |
| `artifacts/` | Downloaded GGUF binaries (gitignored); `artifacts/STATUS.md` tracks local provenance |
| `runs/` | Per-run logs, PIDs, monitor CSVs (gitignored) |

---

## Docs index

| Doc | What it covers |
|-----|---------------|
| [docs/credentials.md](docs/credentials.md) | Two-tier credential model: direct API keys vs x402 proxy |
| [docs/clawrouter-operations.md](docs/clawrouter-operations.md) | ClawRouter CLI reference |
| [docs/open-webui-local-server.md](docs/open-webui-local-server.md) | Connecting open-webui to the local server |
| [docs/openai-api-explainer.md](docs/openai-api-explainer.md) | In-depth guide to OpenAI API shapes: responses, chat/completions, streaming, tools, embeddings |
| [docs/embedding-model-research-brief.md](docs/embedding-model-research-brief.md) | Hugging Face research brief on local embedding model options and recommendation |
| [docs/model-card-index.md](docs/model-card-index.md) | Model registry with upstream card links |
| [docs/llama-server-stats-faq.md](docs/llama-server-stats-faq.md) | Understanding llama-server logs and memory numbers |
| [docs/llama-server-cache-architecture-explainer.md](docs/llama-server-cache-architecture-explainer.md) | Deep dive: slots, KV cache, checkpoints, long-context |
| [docs/architecture.html](docs/architecture.html) | Interactive stack diagram |
| [CLAUDE.md](CLAUDE.md) | Instructions for Claude Code |
| [AGENTS.md](AGENTS.md) | Instructions for AI agents |
