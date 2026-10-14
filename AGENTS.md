# AGENTS.md

Instructions for AI agents working in this repository.

## What this repo does

Local LLM infrastructure for one Apple Silicon host: model sidecar metadata, launchers for
llama-server, mlx_lm, and kev (decision models), a llama-swap hot-swap proxy with
parallel model groups, tmux-managed services, client bootstraps for Pi and OpenCode, and
ClawRouter routing config. `docs/architecture.html` shows the full stack.

## Repo map

| Path | Purpose |
| --- | --- |
| `models/*.json` | One sidecar per model artifact (schema below) |
| `lm_launcher/` | Python package: profiles, settings, launchers, client bootstraps |
| `lm_launcher/profiles.py` | Serving profiles: `infer_profile()` and `profile_defaults()` |
| `run-server.py` | Builds `ServerSettings` from a sidecar and execs the backend |
| `serve-policy.yaml` | Which models llama-swap serves, ports, and group routing (JSON content) |
| `llama_swap/`, `llama-swap-runner.py` | llama-swap binary management and config generation |
| `up` | Starts services in the `lm-based` tmux session (`./up --list` for targets) |
| `cmd/serve-manager/` | Go supervisor, dashboard, and stats poller |
| `pi-local`, `opencode-local` | Launch Pi / OpenCode against the running local service |
| `support/pi/` | Repo-pinned Pi install and repo Pi extensions |
| `route-config.py` | Generates and validates `clawrouter.json` |
| `docs/`, `docs-cms/` | Reference docs; decision records (docuchango) |

## Verify before you commit

These are the CI checks (`.github/workflows/ci.yml`); run them locally:

```bash
uv sync --frozen
uv run --frozen python -m unittest discover -s tests   # Python tests
go test ./...                                          # serve-manager
./route-config.py --validate                           # sidecar lint
just pi-test                                           # Pi extension modules (node --test)
pre-commit run --all-files                             # markdownlint + whitespace
```

`.venv` has no pytest; use `unittest` as above. Tests must not depend on live services.

## Key invariants

- Never modify `runs/` contents or model binaries (`.gguf`, safetensors, MLX weights).
- Never set `provenance_status: "verified"` without actually checking the sha256.
- `schema_version` in sidecars is always `1` until explicitly bumped.
- Generated files are gitignored and never hand-edited: `clawrouter.json`
  (`route-config.py`), `llama-swap.yaml` (`llama-swap-runner.py config`), `.runtime/`.
- The Python package is `lm_launcher/`. Do not recreate or import from `qwen_launcher`.
- Never hard-code API keys; sidecars and generated config store env var names only.

## Shared checkout and live services

Several agents often work in this checkout at once, and the host runs real model servers.

- Run `git status` and `git branch --show-current` before acting. Another agent may have
  switched branches or left uncommitted work in files you are about to touch.
- Do not switch branches, stash, reset, or commit files you did not change. To commit your
  work on its own branch, use a worktree:
  `git worktree add -b <branch> <path> origin/main`, copy your files there, and commit.
- Do not stop, restart, or reconfigure services you did not start: llama-swap
  (`127.0.0.1:8081`), its workers (`10001`–`10100`), tmux services (`./up --status`), or
  ad-hoc `run-server.py` processes. Ask first; a restart unloads models other sessions use.
- Before loading a large model, check memory (`memory_pressure`, `/running` on llama-swap).
  Model weights plus KV cache must fit the GPU wired limit (about 96 GB by default on a
  128 GB host), including servers running outside llama-swap.
- Prefer read-only probes (`curl /v1/models`, `/running`, `/health`) when validating.

## Adding a model (checklist)

```text
1. Write  models/<artifact>.json            (schema below)
2. Extend lm_launcher/profiles.py if the model needs a new serving profile
3. Append a row to docs/model-card-index.md
4. Add the slug to serve-policy.yaml models.enabled to serve it through llama-swap,
   and to a routing group if it should run beside other models
5. Regenerate: ./route-config.py  and  ./llama-swap-runner.py config
6. Verify:     ./download_model.py --list   (slug appears)
               ./route-config.py --validate
```

Sidecar file names follow the artifact: `<Artifact-QUANT>.gguf.json`,
`<Artifact>.safetensors.json`, or `<artifact-dir>.json` for MLX directories.

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
    "script": "/Users/jrepp/d/lm-based/run-server.py",
    "profile": "<profile-name>",
    "recommended_env": {
      "MODEL_FILE": "<stem>.gguf",
      "PROFILE": "<profile-name>"
    }
  },
  "notes": []
}
```

- `artifact.format` is `gguf`, `safetensors`, or `mlx`. For MLX, `local_path` points at the
  model directory's `config.json`.
- Leave `size_bytes` and `sha256` null until the artifact is downloaded and checksummed.
- `provenance_status`: `user_reported` | `planned_download` | `verified`.

## Profile guidelines

- Add an `infer_profile()` branch matching a fragment of the model family name.
- Add a `profile_defaults()` block that only overrides values differing from generic.
- Keep `ctx_size` conservative for untested architectures; clients (Pi, OpenCode) take
  their context window from it.
- Non-chat models get their own profile: `mlx-kev` (decision models, TypeSafe System One
  API, health check on `/v1/models`) and `glm-ocr` (document OCR via llama-server
  `--mmproj`). `pi-local` keeps decision models out of Pi's chat model list (`DECISION_PROFILES`).

## Serving

```bash
./up --list          # targets: service sets, services, model slugs
./up swap            # llama-swap plus core services in tmux
./up <model-slug>    # one direct worker on 127.0.0.1:8001
./up --status        # what is running
```

- llama-swap (Homebrew binary, v264+) listens on `127.0.0.1:8081` and starts workers on
  `10001`–`10100`. `serve-policy.yaml` `models.enabled` decides which sidecars it serves;
  `swap.routing` defines groups. Today the `small` group (GLM-OCR, kev) stays resident
  beside whichever `main` group chat model is loaded.
- llama-swap routes OpenAI-style paths by the request's `model`. Other APIs (kev's
  `/v1/systemone`) go through `/upstream/<slug>/...`.
- `/v1/models` lists every configured model; `/running` lists the loaded ones and their state.
- The `llama_swap/` package: `bin.py` (binary discovery/install), `config.py` (YAML from
  sidecars and policy), `wrapper.py` (`LlamaSwap` process wrapper), `cli.py`.

Docs: `docs/serving/` (topology, lifecycle, supervisor spec), `docs/serving/tmux-service-setup.md`.

## Clients: Pi and OpenCode

- `./pi-local` runs the Pi pinned in `support/pi` (`just pi-install`) with its config in
  `.runtime/pi/agent`, never `~/.pi`. With no arguments it uses llama-swap if it is up,
  otherwise the tmux-registered service. `just pi-link` symlinks it onto `PATH`; the
  launching directory becomes Pi's workspace.
- Repo Pi extensions live in `support/pi/extensions/` and are registered in
  `PI_EXTENSIONS` in `lm_launcher/pi_bootstrap.py`. Keep pure logic in modules testable with
  `node --test`.
- Pi's `models.json` only holds chat models. Decision models reach Pi through the `decide`
  extension (`LM_BASED_CLASSIFIERS`).
- When scripting `./pi-local -p`, close stdin (`< /dev/null`) or Pi waits for piped input.
- `./opencode-local` does the same for OpenCode from llama-swap's `/v1/models`.

Details: `docs/pi-local-model.md`, `docs/opencode-local-models.md`.

## ClawRouter and credentials

`clawrouter.json` is gitignored and generated — never hand-edit it.

To add a cloud provider: add a `CloudProvider(...)` entry to `CLOUD_PROVIDERS`
in `route-config.py`, then regenerate.

Credential model (see `docs/credentials.md`):

- Each provider has a `key_env` and `base_env` in `CLOUD_PROVIDERS`.
- Key set + direct_base known → `routing=direct` in generated JSON.
- Key absent → `routing=proxy` (x402).
- The JSON stores `api_key_env` (var name), never the resolved secret.

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

`markdownlint-cli2` runs through pre-commit on `README.md`, `AGENTS.md`, `CLAUDE.md`, and
`docs/` (config: `.markdownlint-cli2.jsonc`; line length is not enforced). Before
publishing doc-heavy changes, run `pre-commit run --all-files`.

## docs-cms (docuchango)

Decision records, proposals, and notes live in the `docs-cms/` micro-CMS, kept
separate from the `docs/` reference tree. It is managed with
[docuchango](https://github.com/jrepp/docuchango).

Document types (templates in `docs-cms/templates/`):

| Type | When |
| --- | --- |
| ADR | a decision has been made or is being proposed |
| RFC | a proposal or design needs review before implementation |
| Memo | investigation results, status, meeting outcomes |
| PRD | product requirements |

Workflow:

1. Copy the matching template into its folder (`adr/`, `rfcs/`, `memos/`, `prd/`).
2. Fill the frontmatter; generate a fresh `doc_uuid`
   (`python -c "import uuid; print(uuid.uuid4())"`) and set `project_id: lm-based`.
3. Keep each document atomic (one decision or topic).
4. Validate (see below), then commit using this repo's commit style.

`docuchango validate` requires Python >= 3.10. The system install targets
Python 3.9 and is broken (`TypeGuard` import), so always run it through uv:

```bash
uv run --no-project --python 3.11 --with docuchango==1.17.1 docuchango validate
```

`docs-cms/` is governed by `docuchango validate`, not markdownlint: docuchango's
templates use per-section `#` headings, which conflict with markdownlint's single-H1
(MD025) rule. The pre-commit trailing-whitespace and end-of-file fixers still run on
all Markdown.

Agent guardrails (see `docuchango bootstrap --guide agent` for detail):

- Propose, don't decide: create ADRs as `Proposed` and RFCs as `Draft` for human
  review. Do not mark your own proposals `Accepted` without review.
- Reference existing decisions when implementing (`per ADR-00X ...`).
- The docuchango agent guide recommends Conventional Commits (`feat:` / `fix:`)
  with AI trailers and semantic-release versioning. **That does not apply here**
  — this repo uses plain imperative summaries with no trailers (see Commit
  style). Only the documentation workflow above applies.
