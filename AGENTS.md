# AGENTS.md

Instructions for AI agents working in this repository.

## What this repo does

Manages a local registry of GGUF model artifacts and launches them via `llama-server`.
Each model has a JSON sidecar in `models/` that drives downloads and serving configuration.

## Key invariants

- Never modify `runs/` contents — these are live or historical run captures.
- Never modify `.gguf` binary files.
- Never set `provenance_status` to `"verified"` unless you have actually verified the sha256.
- `schema_version` in sidecars is always `1` until explicitly bumped.

## Adding a model (agent checklist)

```
1. Write models/<Artifact-Name-QUANT>.gguf.json  (schema below)
2. Extend qwen_launcher/profiles.py if a new serving profile is needed
3. Append row to docs/model-card-index.md
4. Confirm `python download_model.py --list` shows the new slug
```

### Minimal sidecar schema

```json
{
  "schema_version": 1,
  "recorded_at": "YYYY-MM-DD",
  "artifact": {
    "filename": "<stem>.gguf",
    "local_path": "/Users/jrepp/d/qwen/<stem>.gguf",
    "format": "gguf",
    "quantization": "<QUANT>",
    "size_bytes": null,
    "sha256": null
  },
  "model": {
    "slug": "<lowercase-hyphen-slug>",
    "family": "<ModelFamily>",
    "name": "<ModelName>",
    "canonical_model_card": "https://huggingface.co/<org>/<repo>"
  },
  "source": {
    "gguf_model_card": "https://huggingface.co/<gguf-org>/<gguf-repo>",
    "publisher": "<publisher>",
    "provenance_status": "planned_download"
  },
  "download": {
    "provider": "huggingface",
    "repo_id": "<org>/<repo>",
    "filename": "<stem>.gguf",
    "revision": null
  },
  "launcher": {
    "script": "/Users/jrepp/d/qwen/run-qwen35-server.py",
    "profile": "<profile-name>",
    "recommended_env": {
      "MODEL_FILE": "<stem>.gguf",
      "PROFILE": "<profile-name>"
    }
  },
  "notes": []
}
```

## Profile guidelines

When creating a new profile in `qwen_launcher/profiles.py`:
- Add an `infer_profile()` branch matching the model family name fragment.
- Add a `profile_defaults()` block that only overrides values that differ from generic.
- Keep ctx_size conservative for untested architectures — user can override via env.

## Commit style

Plain imperative summary line. No `Co-Authored-By:` trailers.
