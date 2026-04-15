# CLAUDE.md

Project: `lm-based` — local LLM infrastructure: model registry, llama-server launcher, routing config, and architecture docs.

## Architecture

See `docs/architecture.html` for a rendered diagram of the full stack:

- **L0 Ingress** — Tailscale VPN, Telegram bot, open-webui chat UX
- **L1 Agent** — Claw, Hermes agents
- **L2 Router** — ClawRouter (sub-millisecond OpenAI-compatible routing)
- **L3 Local** — llama-server serving local GGUF models
- **L4 Cloud** — GLM-5, ChatGPT, MiniMax, DeepSeek, Claude, Grok, Gemini (via x402/USDC proxy)

## Repo layout

| Path | Purpose |
|------|---------|
| `models/*.json` | Sidecar metadata per GGUF artifact (schema_version 1) |
| `lm_launcher/` | Python package — launcher, profiles, settings, run capture |
| `clawrouter_config.py` | Generate, validate, and inspect `clawrouter.json` |
| `clawrouter.json` | Generated routing config — gitignored, regenerate with `clawrouter_config.py` |
| `.env.example` | Template for all env vars; copy to `.env` and fill in |
| `run-server.py` | Entry point: builds `ServerSettings` and execs llama-server |
| `download_model.py` | CLI to fetch a model by sidecar slug |
| `docs/` | Architecture diagram, credentials guide, routing and open-webui docs |
| `runs/` | Per-run capture dirs (logs, PIDs, monitor CSVs) |

## First-time setup

```bash
cp .env.example .env        # fill in MODEL_SLUG and any API keys
python clawrouter_config.py # generate clawrouter.json
```

## Adding a model

1. Create `models/<Artifact-QUANT>.gguf.json` (schema_version 1).
   Required keys: `schema_version`, `recorded_at`, `artifact`, `model`, `source`, `download`, `launcher`, `notes`.
2. If the model needs custom serving params, add a profile in
   `lm_launcher/profiles.py` → `profile_defaults()` and update `infer_profile()`.
3. Append a row to `docs/model-card-index.md`.
4. Regenerate: `python clawrouter_config.py`
5. Verify: `python download_model.py --list` — new slug should appear.

## Sidecar conventions

- `model.slug`: lowercase-hyphen, e.g. `gemma4-e2b-uncensored-aggressive-q4kp`.
- `provenance_status`: `"user_reported"` | `"planned_download"` | `"verified"`. Set `"verified"` only after sha256 is confirmed.
- Leave `size_bytes` and `sha256` null until downloaded and checksummed.
- `launcher.script` must reference `run-server.py`.

## Credentials and cloud routing

See `docs/credentials.md` for the full explanation. Short version:

- Each cloud provider has a dedicated env var (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.)
- Key set + provider has a known direct endpoint → traffic goes direct
- Key absent → traffic routes through the local x402 proxy (USDC micropayments)
- `clawrouter.json` stores `api_key_env` (the var *name*), never the resolved secret

```bash
python clawrouter_config.py --providers  # credential status per provider
python clawrouter_config.py --doctor     # full stack: sidecars + endpoints + credentials
python clawrouter_config.py --status     # summary of current clawrouter.json
```

## Adding a cloud provider

Edit `CLOUD_PROVIDERS` in `clawrouter_config.py` — add a `CloudProvider(...)` entry with
`model_id`, `display`, `key_env`, `base_env`, and `direct_base`. Then regenerate.

## Profiles

`lm_launcher/profiles.py`. Each profile only overrides values that differ from generic defaults.
Current profiles: `generic`, `qwen3.5`, `qwen3-coder-next`, `gemma4`.

## Commits

No `Co-Authored-By:` trailers.
