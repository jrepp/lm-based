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
- `clawrouter.json` is generated — edit `route-config.py` instead.
- The Python package is `lm_launcher/`. Do not recreate or import from `qwen_launcher`.

## Adding a model (checklist)

```
1. Write  models/<Artifact-QUANT>.gguf.json   (schema below)
2. Extend lm_launcher/profiles.py if a new serving profile is needed
3. Append row to docs/model-card-index.md
4. Run    ./route-config.py               (regenerate routing config)
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

## llama-swap

[llama-swap](https://github.com/mostlygeek/llama-swap) is a Go binary that acts as a hot-swap
reverse proxy for any OpenAI/Anthropic API-compatible inference server (llama-server, vllm, etc.).

The `llama_swap/` Python package wraps it:

| File | Purpose |
|------|---------|
| `llama_swap/bin.py` | Binary discovery and installation |
| `llama_swap/config.py` | YAML config generation from model sidecars |
| `llama_swap/wrapper.py` | Process management wrapper (`LlamaSwap` class) |
| `llama_swap/cli.py` | CLI entry point |

Key commands:
```bash
./llama-swap-runner.py ensure   # download/install llama-swap binary
./llama-swap-runner.py config    # generate llama-swap.yaml from sidecars
./llama-swap-runner.py start     # launch the proxy
./llama-swap-runner.py status    # show loaded models
./llama-swap-runner.py logs      # stream logs
```

Or via `just`:
```bash
just swap-ensure    # install binary
just swap-config     # generate yaml
just swap-start      # launch proxy
just swap-status     # check status
just swap-logs       # stream logs
```

`llama-swap.yaml` is gitignored; it is generated from sidecar metadata and llama-server
profile flags. Regenerate after adding or changing a model.

## ClawRouter and credentials

`clawrouter.json` is gitignored and generated — never hand-edit it.

To add a cloud provider: add a `CloudProvider(...)` entry to `CLOUD_PROVIDERS`
in `route-config.py`, then regenerate.

Credential model (see `docs/credentials.md`):
- Each provider has a `key_env` and `base_env` in `CLOUD_PROVIDERS`.
- Key set + direct_base known → `routing=direct` in generated JSON.
- Key absent → `routing=proxy` (x402).
- The JSON stores `api_key_env` (var name), never the resolved secret.
- Never hard-code API keys in any file.

```bash
./route-config.py --providers  # credential audit
./route-config.py --doctor     # full health check
./route-config.py --status     # summarise current config
./route-config.py --validate   # sidecar lint only
./route-config.py              # regenerate clawrouter.json
```

## Commit style

Plain imperative summary line. No `Co-Authored-By:` trailers.

## Markdown guardrails

Markdown files are linted through pre-commit using `markdownlint-cli2`.
Before publishing doc-heavy changes, run:

```bash
pre-commit run --all-files
```
