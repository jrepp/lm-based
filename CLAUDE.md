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
| `clawrouter_config.py` | Generate `clawrouter.json` from model sidecars |
| `clawrouter.json` | Generated ClawRouter routing config (do not hand-edit) |
| `run-server.py` | Entry point: builds `ServerSettings` and execs llama-server |
| `download_model.py` | CLI to fetch a model by sidecar slug |
| `docs/` | Architecture diagram, routing docs, open-webui setup |
| `runs/` | Per-run capture dirs (logs, PIDs, monitor CSVs) |

## Adding a model

1. Create `models/<Artifact-QUANT>.gguf.json` following schema_version 1.
   Required keys: `schema_version`, `recorded_at`, `artifact`, `model`, `source`, `download`, `launcher`, `notes`.
2. If the model needs custom serving params, add a profile block in
   `lm_launcher/profiles.py` → `profile_defaults()` and update `infer_profile()`.
3. Append a row to `docs/model-card-index.md`.
4. Regenerate routing config: `python clawrouter_config.py`
5. Verify: `python download_model.py --list` — new slug should appear.

## Sidecar conventions

- `model.slug`: lowercase, hyphen-separated. E.g. `gemma4-e2b-uncensored-aggressive-q4kp`.
- `provenance_status`: `"user_reported"` | `"planned_download"` | `"verified"`. Set `"verified"` only after sha256 is confirmed.
- Leave `size_bytes` and `sha256` null until downloaded and checksummed.
- `launcher.script` should reference `run-server.py`.

## Profiles

`lm_launcher/profiles.py`. Each profile only overrides values that differ from generic defaults.
Current profiles: `generic`, `qwen3.5`, `qwen3-coder-next`, `gemma4`.

## ClawRouter config

`python clawrouter_config.py` regenerates `clawrouter.json` from live model sidecars + the hardcoded `CLOUD_MODELS` list. Add new cloud providers there.

## Commits

No `Co-Authored-By:` trailers.
