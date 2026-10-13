---
title: MLX decision-model serving via the kev runtime
status: Proposed
created: 2026-10-10T00:00:00Z
deciders: maintainer
tags: [adr, decision-model, kev, mlx, proposed, serving]
id: adr-005
project_id: lm-based
doc_uuid: 640cf74e-85f0-46a8-9f53-a40851d8a122
---

# Context

The operator directed adoption of `RoderickQiu/kev-4b-mlx-8bit` as the local
decision model (typed, calibrated choice/score/yes-no decisions over a state
document), following the 2026-10-10 capability research pass
(`reports/Most capable model 128GB Mac.md`).

Kev-4B ([jaredpalmer/kev-4b](https://huggingface.co/jaredpalmer/kev-4b)) is not
a chat model: it is a prefill-only pointer head over Qwen3.5-4B-Base that
serves the TypeSafe System One API (`POST /v1/systemone`). Findings that shape
this decision:

- The canonical runtime is the `kev` package
  ([github.com/jaredpalmer/kev](https://github.com/jaredpalmer/kev)), run as
  `python -m kev.serve --run <checkpoint>` with `--extra serve`. It is **not on
  PyPI** (the `kev` name is an unrelated ORM) and requires Python 3.12/3.13.
- On Apple Silicon, `kev.serve` auto-selects the MLX backend for hybrid
  (Gated DeltaNet) checkpoints — no torch MPS probe, no mlx_lm involvement.
- `--run` accepts a Hub id, a `repo@revision` pin, or **any local directory
  containing `head.pt`**. The MLX-8bit artifact ships `head.pt` (the pointer
  head + fitted temperature 2.406, unchanged from the canonical checkpoint)
  at its root, so the snapshot directory works directly.
- The 8-bit conversion reports bf16-parity accuracy on-Mac across all five dev
  suites (e.g. decision-v7 0.873 accuracy / ECE 0.010) at ~6.6 GB resident.
- The repo's current MLX path (per
  [ADR-004](./adr-004-mlx-serving-via-mlx-lm.md) hardwires the `mlx` backend
  to `mlx_lm.server`, and `llama_swap/config.py` silently drops sidecars whose
  `artifact.format` is not `gguf`/`safetensors` — so no MLX model can be
  managed by llama-swap today.

# Decision

Generalize the MLX backend from "mlx_lm.server wrapper" into two MLX
sub-modes, dispatched on profile:

- `mlx-kev` profile: `lm_launcher/mlx_server.py` builds
  `uv run --directory <kev_repo> --python 3.13 --extra serve python
  lm_launcher/kev_serve_local.py --weights <dir> --kev-repo <repo> --host
  --port`. The runtime checkout is auto-cloned (shallow, with retries) into
  `support/kev` when missing (`KEV_REPO_DIR` overrides the location),
  mirroring the upstream quick start. `validate_runtime` requires `head.pt`
  in the weights directory.
- `lm_launcher/kev_serve_local.py` (serve shim): `kev.serve --run` rejects
  the MLX-8bit pack because `Checkpoint.full()` requires the head.pt
  weights-mode ("lora") to match the directory layout (merged backbone
  weights). The shim follows the artifact card's documented loading path —
  canonical `Checkpoint` for meta (tokenizer base, pointer head, fitted
  temperature), quantized backbone from the local pack — then hands the
  model to `kev.serve`'s own `Server`/FastAPI app, so batching, the state
  prefix cache and the `/v1/*` endpoints behave exactly as upstream.
- Every other `mlx*` profile keeps the existing `mlx_lm.server` path.

Supporting changes:

- `llama_swap/config.py` accepts `artifact.format: "mlx"` sidecars so MLX
  models appear in the swap pool; kev models use `/v1/models` as the health
  check (kev.serve has no `/health`).
- `lm_launcher/profiles.py` adds `mlx-kev` (no sampler flags — the checkpoint
  ships its own calibrated temperature; `ctx_size` 65536 records the serve
  ceiling, validated context is 8192), plus `qwen3.5-122b` and `qwen3.8`
  llama.cpp profiles for the models deployed alongside this decision.
- Sidecar `models/kev-4b-mlx-8bit.json` (snapshot download of the 8-bit
  pack), with `provenance_status: planned_download` until the snapshot's
  sha256 matches the upstream `provenance.json`.

# Consequences

## Positive

- MLX models become first-class citizens of llama-swap; the backend family,
  not the artifact format, decides health checks and lifecycle.
- Decision serving stays on the canonical kev runtime, so upstream training/
  calibration semantics (temperature, question isolation, prefix cache) are
  inherited unchanged, and TypeSafe SDK clients work as-is.
- A ~4.5 GB artifact adds typed-decision capability at negligible memory cost
  next to the 96–120 GB flagship models.

## Negative

- The runtime is a pinned third-party checkout under `support/kev`; upstream
  is not published to PyPI, so updates are manual re-clones. `kev` needs its
  own Python (3.13), fetched by uv on first run.
- The 8-bit artifact is a community conversion (built for the Qualm app), not
  an official kev release; the canonical fallback is
  `kev.serve --run jaredpalmer/kev-4b`.
- llama-swap proxies raw HTTP, but kev exposes `/v1/systemone`, not
  OpenAI-compatible chat — clients must speak the System One API against this
  model slot.

## Neutral

- kev-27B (Qwen3.8-27B full weights, 51 GB bf16) would fit this machine per
  upstream, but is out of scope here; adding it later is a sidecar + the same
  profile.
- Vision for the GGUF models deployed in the same pass still lacks mmproj
  wiring in the launcher; unrelated to this backend change.

# Alternatives Considered

## ggml-org/Kev-4B-GGUF via llama-server `/v1/systemone` (llama.cpp PR #29819-class)

Viable and backend-light, but the operator chose the native MLX path; the GGUF
remains a fallback that needs no new runtime.

## mlx_lm.server with a custom decision head server

Rejected: re-implements kev.serve's batching, prefix cache and calibration
behind mlx_lm, coupling this repo to model internals the kev runtime already
owns and tests.

## Jakevin/kev-4b-ternary-mlx

Smaller (~1.7 GB) but experimental, with its own bundled runtime; not chosen
for a serving-critical path.

# References

- Upstream model: <https://huggingface.co/jaredpalmer/kev-4b>
- MLX-8bit artifact: <https://huggingface.co/RoderickQiu/kev-4b-mlx-8bit>
- Runtime: <https://github.com/jaredpalmer/kev> (`python -m kev.serve`)
- MLX backend precedent: [ADR-004](./adr-004-mlx-serving-via-mlx-lm.md)
- Capability research: `reports/Most capable model 128GB Mac.md`
