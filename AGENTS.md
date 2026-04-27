# AGENTS.md

Instructions for AI agents working in this repository.

## What this repo does

Manages local GGUF model artifacts, launches them via `llama-server`, generates
ClawRouter routing config, and documents the full local-LLM stack (see `docs/architecture.html`).

## Key invariants

- Never modify `runs/` contents.
- Never modify `.gguf` binary files.
- Never set `provenance_status: "verified"` without actually verifying the sha256.
- `schema_version` in sidecars is always `1` until explicitly bumped.
- `clawrouter.json` is generated — edit `clawrouter_config.py` instead.
- The Python package is `lm_launcher/`. Do not recreate or import from `qwen_launcher`.

## Adding a model (checklist)

```
1. Write  models/<Artifact-QUANT>.gguf.json   (schema below)
2. Extend lm_launcher/profiles.py if a new serving profile is needed
3. Append row to docs/model-card-index.md
4. Run    ./clawrouter_config.py               (regenerate routing config)
5. Verify ./download_model.py --list           (new slug appears)
```

### Minimal sidecar schema

```json
{
  "schema_version": 1,
  "recorded_at": "YYYY-MM-DD",
  "artifact": {
    "filename": "<stem>.gguf",
    "local_path": "<stem>.gguf",
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
    "script": "/Users/jrepp/d/qwen/run-server.py",
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

- Add an `infer_profile()` branch matching a fragment of the model family name.
- Add a `profile_defaults()` block that only overrides values differing from generic.
- Keep `ctx_size` conservative for untested architectures.

## ClawRouter and credentials

`clawrouter.json` is gitignored and generated — never hand-edit it.

To add a cloud provider: add a `CloudProvider(...)` entry to `CLOUD_PROVIDERS`
in `clawrouter_config.py`, then regenerate.

Credential model (see `docs/credentials.md`):
- Each provider has a `key_env` and `base_env` in `CLOUD_PROVIDERS`.
- Key set + direct_base known → `routing=direct` in generated JSON.
- Key absent → `routing=proxy` (x402).
- The JSON stores `api_key_env` (var name), never the resolved secret.
- Never hard-code API keys in any file.

```bash
./clawrouter_config.py --providers  # credential audit
./clawrouter_config.py --doctor     # full health check
./clawrouter_config.py --status     # summarise current config
./clawrouter_config.py --validate   # sidecar lint only
./clawrouter_config.py              # regenerate clawrouter.json
```

## Commit style

Plain imperative summary line. No `Co-Authored-By:` trailers.

## Markdown guardrails

Markdown files are linted through pre-commit using `markdownlint-cli2`.
Before publishing doc-heavy changes, run:

```bash
pre-commit run --all-files
```
