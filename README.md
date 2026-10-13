# lm-based

Local LLM infrastructure for an Apple Silicon Mac: a model registry, on-demand
serving behind a hot-swap proxy, agent harnesses, and cloud routing — so local
and remote models are reachable through one OpenAI-compatible endpoint.

```text
Tailscale / Telegram / open-webui
           │
      Claw / Hermes agents
           │
         llama-swap          ← hot-swap reverse proxy (parallel model groups)
        /          \
 llama-server    Cloud APIs
 (GGUF / MLX)    (direct or x402 proxy)
```

The interactive version of this diagram lives in
[docs/architecture.html](docs/architecture.html); the design docs are indexed
in [docs/README.md](docs/README.md).

---

## How the repo operates

Everything is driven from a small set of artifacts. You rarely edit serving
logic — you edit declarations, and the generators produce the runtime config.

1. **Register a model** — add a sidecar JSON under `models/` describing the
   artifact, its upstream card, and the launcher profile. The checklist and
   sidecar schema are in [AGENTS.md](AGENTS.md); the registry of recorded
   models is [docs/model-card-index.md](docs/model-card-index.md).
2. **Fetch the artifact** — `./download_model.py` reads the sidecar's download
   block (single files, shard sets, or whole snapshots).
3. **Serve** — `./up swap` starts llama-swap. Its YAML is *generated* from the
   sidecars plus [serve-policy.yaml](serve-policy.yaml) (ingress, enabled
   models, parallel-model groups), so it is never hand-edited. Per-model
   launch flags come from serving profiles in
   [lm_launcher/profiles.py](lm_launcher/profiles.py).
4. **Consume** — point any OpenAI-compatible client at the policy-owned
   endpoint, or use the built-in harnesses below.

A single model can also be served directly without the proxy:
`MODEL_SLUG=<slug> ./run-server.py` (settings resolve through the sidecar;
see `.env.example`).

---

## Day-to-day commands

All commands exist as `just` recipes — run `just --list` for the full set.

```bash
just swap-start        # llama-swap on the serve-policy ingress (UI at /ui)
just swap-status       # which models are loaded right now
just swap-logs         # stream proxy and upstream logs

./download_model.py --list          # registered models
./download_model.py --model <slug>  # fetch one

./route-config.py --doctor          # routing + credential health check

./up swap                           # tmux-owned service set (swap + proxies)
```

Model switching is done by clients: pass the model slug in the API request and
llama-swap cold-loads or hot-swaps the right server. Parallel models are
declared as groups in `serve-policy.yaml` (a small always-warm tier runs
alongside whichever large model is loaded).

---

## Client harnesses

| Harness | What it does |
| --- | --- |
| `./pi-local` | Bootstraps the repo-pinned Pi agent against the running service; verifies `/v1/models`, merges an `lm-based` provider. Loads repo extensions (llama-swap status, `pdf_extract` via the local OCR model) |
| `./opencode-local` | Discovers the live llama-swap model set and launches OpenCode with an ephemeral provider |
| `./serve-manager` | Go control plane for staging generations (`plan` / `doctor` / `apply` / `status`) |
| Any OpenAI client | The swap endpoint (`ingress.swap_listen` in `serve-policy.yaml`); see [docs/open-webui-local-server.md](docs/open-webui-local-server.md) for the open-webui recipe |

---

## Where things live

| Path | Role |
| --- | --- |
| `models/*.json` | Sidecar registry: artifacts, upstream cards, launcher profiles |
| `serve-policy.yaml` | Operator policy: ingress, ports, enabled models, model groups |
| `host-capabilities.yaml` | Host class and backend capabilities |
| `lm_launcher/` | Launcher package: backends, profiles, settings, run capture |
| `llama_swap/` | llama-swap binary install, YAML generation, process wrapper |
| `clawrouter.json` | Generated cloud routing config — edit `route-config.py`, never the JSON |
| `justfile` | Every operational command as a recipe |
| `docs/` | Reference docs, indexed in [docs/README.md](docs/README.md) |
| `reports/`, `research_notes/` | Model-selection research passes and their sources |
| `runs/`, `artifacts/` | Runtime output and downloaded artifacts (gitignored) |

---

## Guardrails

- `clawrouter.json` and `llama-swap.yaml` are generated — change the inputs
  (`route-config.py`, sidecars, `serve-policy.yaml`), then regenerate.
- `runs/` is append-only observability data; never modify recorded runs.
- Markdown lint runs via pre-commit (`pre-commit run --all-files`).
- Agent-specific rules and the model-adding checklist: [AGENTS.md](AGENTS.md).

---

## Learning more

- [docs/README.md](docs/README.md) — full documentation index (serving design,
  credentials, llama-server internals, embeddings course)
- [docs-cms/](docs-cms/README.md) — decision records (ADRs) for architecture
  choices
- [reports/](reports/) — capability research (model selection per hardware
  class, benchmark guides)
