# CLAUDE.md

Project: `qwen` — local llama-server launcher and model registry.

## Repo layout

| Path | Purpose |
|------|---------|
| `models/*.json` | Sidecar metadata per GGUF artifact (schema_version 1) |
| `qwen_launcher/` | Python package — launcher, profiles, settings, run capture |
| `docs/` | Human-readable docs and model-card index |
| `runs/` | Per-run capture directories (logs, PID files, monitor CSVs) |
| `download_model.py` | CLI to fetch a model from its sidecar download spec |
| `run-qwen35-server.py` | Entry point that builds `ServerSettings` and execs llama-server |

## Adding a model

1. Create `models/<artifact>.gguf.json` following the existing schema (schema_version 1).
   Required top-level keys: `schema_version`, `recorded_at`, `artifact`, `model`, `source`, `download`, `launcher`, `notes`.
2. If the model needs custom serving parameters, add a named profile block in
   `qwen_launcher/profiles.py` → `profile_defaults()`, and update `infer_profile()`.
3. Append a row to `docs/model-card-index.md`.
4. Verify with `python download_model.py --list` — the new slug should appear.

## Sidecar conventions

- `model.slug`: lowercase, hyphen-separated, no version noise. E.g. `gemma4-e2b-uncensored-aggressive-q4km`.
- `provenance_status`: `"user_reported"` | `"planned_download"` | `"verified"`. Set to `"verified"` only after sha256 is confirmed locally.
- Leave `size_bytes` and `sha256` null until the file is downloaded and checksummed.

## Profiles

Profiles live in `qwen_launcher/profiles.py`. Each profile is a dict that overrides the generic defaults. Keep profiles minimal — only set values that genuinely differ from the generic baseline.

Current profiles: `generic`, `qwen3.5`, `qwen3-coder-next`, `gemma4`.

## Commits

No `Co-Authored-By: Claude` trailers. No `Co-Authored-By:` lines at all unless the user explicitly adds them.
