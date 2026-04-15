# lm-based

Local LLM infrastructure: GGUF model registry, llama-server launcher, smart routing to local and cloud backends, and supporting tooling.

```
Tailscale / Telegram / open-webui
           │
      Claw / Hermes agents
           │
       ClawRouter          ← sub-millisecond OpenAI-compatible routing
      /          \
llama-server    Cloud APIs
(local GGUF)    (direct or x402 proxy)
```

See [`docs/architecture.html`](docs/architecture.html) for the interactive diagram.

---

## Quick start

### 1 — Prerequisites

- [`llama-server`](https://github.com/ggml-org/llama.cpp) on your PATH (or set `LLAMA_SERVER_BIN` in `.env`)
- A HuggingFace account (free) if downloading gated models

### 2 — Configure

```bash
cp .env.example .env
```

Edit `.env` and set at minimum:

```
MODEL_SLUG=gemma4-e2b-uncensored-aggressive-q4kp   # or any slug from: ./download_model.py --list
```

Optional: add cloud provider keys (see [docs/credentials.md](docs/credentials.md)).

### 3 — Download a model

```bash
# List available models
./download_model.py --list

# Download by slug
./download_model.py --model gemma4-e2b-uncensored-aggressive-q4kp
```

### 4 — Start the server

```bash
./run-server.py
```

The server binds to `http://127.0.0.1:8001` by default. The model slug is read from `.env`.

To override without editing `.env`:

```bash
MODEL_SLUG=qwen3-coder-next-iq4xs ./run-server.py
```

### 5 — Connect a client

**Any OpenAI-compatible client** — point it at `http://127.0.0.1:8001/v1`.

**open-webui** (Docker):

```bash
docker run -d --name open-webui --restart always \
  -p 3000:8080 \
  --add-host=host.docker.internal:host-gateway \
  -e OPENAI_API_BASE_URL=http://host.docker.internal:8001/v1 \
  -e OPENAI_API_KEY=dummy \
  -v open-webui:/app/backend/data \
  ghcr.io/open-webui/open-webui:main
```

Then open `http://localhost:3000`. See [docs/open-webui-local-server.md](docs/open-webui-local-server.md) for more.

### 6 — Generate routing config (optional)

If you use ClawRouter or want cloud provider routing:

```bash
./clawrouter_config.py          # generate clawrouter.json
./clawrouter_config.py --doctor # health check: sidecars + endpoints + credentials
```

---

## Available models

| Slug | Family | Quant | Size |
|------|--------|-------|------|
| `gemma4-e2b-uncensored-aggressive-q4kp` | Gemma 4 2B | Q4_K_P | 3.4 GB |
| `mistral-7b-instruct-v03-q4km` | Mistral 7B Instruct v0.3 | Q4_K_M | 4.4 GB |
| `qwen3-coder-next-iq4xs` | Qwen3-Coder-Next | IQ4_XS | — |
| `qwen35-35b-a3b-q4km` | Qwen3.5 35B A3B | Q4_K_M | 22 GB |

Full metadata: [`docs/model-card-index.md`](docs/model-card-index.md)

---

## Key commands

```bash
# Model management
./download_model.py --list
./download_model.py --model <slug>

# Server
./run-server.py                    # start (reads .env)
MODEL_SLUG=<slug> ./run-server.py  # override model

# Routing config
./clawrouter_config.py             # regenerate clawrouter.json
./clawrouter_config.py --status    # summarise current config
./clawrouter_config.py --providers # credential status per cloud provider
./clawrouter_config.py --doctor    # full health check
./clawrouter_config.py --validate  # lint sidecars only

# Run analysis
./summarize_run.py --run <run-dir>
```

---

## Repo layout

| Path | Purpose |
|------|---------|
| `models/*.json` | Sidecar metadata per GGUF (schema_version 1) |
| `lm_launcher/` | Python package: launcher, profiles, settings, run capture |
| `run-server.py` | Entry point: reads settings, execs llama-server |
| `download_model.py` | Fetch a model by sidecar slug |
| `clawrouter_config.py` | Generate and inspect ClawRouter routing config |
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
| [docs/model-card-index.md](docs/model-card-index.md) | Model registry with upstream card links |
| [docs/llama-server-stats-faq.md](docs/llama-server-stats-faq.md) | Understanding llama-server logs and memory numbers |
| [docs/llama-server-cache-architecture-explainer.md](docs/llama-server-cache-architecture-explainer.md) | Deep dive: slots, KV cache, checkpoints, long-context |
| [docs/architecture.html](docs/architecture.html) | Interactive stack diagram |
| [CLAUDE.md](CLAUDE.md) | Instructions for Claude Code |
| [AGENTS.md](AGENTS.md) | Instructions for AI agents |
