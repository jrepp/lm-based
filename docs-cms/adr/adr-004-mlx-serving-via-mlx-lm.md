---
title: MLX serving backend via stock mlx_lm.server
status: Proposed
created: 2026-07-15T06:57:19Z
deciders: maintainer
tags: [bonsai, mlx, proposed, quantization, qwen3-5, serving]
id: adr-004
project_id: lm-based
doc_uuid: 8a9eab60-546f-426b-9c04-8928a407ee7b
---

# Context

We want to serve
[prism-ml/Ternary-Bonsai-27B-mlx-2bit](https://huggingface.co/prism-ml/Ternary-Bonsai-27B-mlx-2bit)
on Apple Silicon through this stack. It is a Qwen3.6-27B-derived ternary model:
`{ -1, 0, +1 }` weights with FP16 group-wise scaling (group 128), ~1.71 bits per
weight, ~7.2 GB deployed, `model_type: qwen3_5` with hybrid attention (~75%
linear / ~25% full) over 64 layers, 262144-token context, and a bundled FP16
vision tower. The published MLX pack measures ~8.49 GB on disk.

Research findings that shape the decision:

- The PrismML `Bonsai-demo` `start_mlx_server.sh` serves the **ternary 2-bit**
  pack on **stock `mlx_lm`** (`python -m mlx_lm.server`). Only the **1-bit**
  binary variant requires the PrismML MLX fork; the 2-bit ternary pack is
  repackaged into MLX's native grouped format (scale + bias per group), which
  stock MLX consumes directly.
- The validated 27B invocation is
  `python -m mlx_lm.server --model <dir> --port <port> --temp 0.7 --top-p 0.95`,
  with the model's recommended sampler settings temperature 0.7, top-p 0.95,
  top-k 20 (thinking mode on by default).
- DSpark speculative decoding ships a drafter layer, but it is a net win only on
  the CUDA path; on Apple Silicon batch-1 verification does not amortize, so it
  is not enabled on-device.
- Open risk: `qwen3_5` hybrid (linear) attention support in `mlx_lm` is the
  verification gate. A recent `mlx_lm` must ship the loader for this
  architecture or serving fails.

This repo already has a non-llama.cpp backend pattern (`transformers_server.py`
via `transformers serve`, dispatched from `run-server.py`), so an MLX backend
fits the established shape.

# Decision

Add an MLX serving backend mirroring `transformers_server.py`:

- `lm_launcher/mlx_server.py`: builds `uv run --with mlx_lm python -m
  mlx_lm.server --model <dir> --host --port --temp --top-p --top-k`, with
  optional run capture like the other backends.
- A dispatch branch in `run-server.py` (`_is_mlx_model()`), keyed on an `mlx`
  profile prefix or a slug containing `bonsai` / `mlx`.
- An `mlx-bonsai` profile in `lm_launcher/profiles.py` with an `infer_profile`
  branch, setting conservative defaults (alias, ctx_size 262144, temperature
  0.7, top_p 0.95, top_k 20).
- A sidecar `models/Ternary-Bonsai-27B-MLX-2bit.json` with `format: mlx`,
  `config.json` as the directory anchor, and `provenance_status:
  planned_download` until the snapshot is downloaded and verified.

KV-cache tuning (`--max-kv-size`, `--kv-bits`, `--kv-group-size`) and DSpark are
deferred until the base path is verified end to end.

# Consequences

## Positive

- Reuses the existing backend + dispatch pattern; no new process model.
- No PrismML MLX fork is required for the ternary 2-bit pack.
- ~7 GB footprint brings a 27B-class model onto a laptop; fits the local-first
  trajectory.

## Negative

- `qwen3_5` hybrid-attention support in `mlx_lm` is unverified; a too-old
  `mlx_lm` will fail to load the model.
- MLX is Apple-Silicon-only; this backend does not run on CUDA/Linux hosts (the
  GGUF path via the PrismML `llama.cpp` fork covers those).
- The vision tower is bundled in the pack, so text-only serving still downloads
  it (it is only loaded on image input).

## Neutral

- The 1-bit companion (`Bonsai-27B-mlx-1bit`) would need the PrismML fork and a
  separate profile if added later.

# Alternatives Considered

## Shell out to the Bonsai-demo repo (like `ouro_server.py`)

Considered: faithful to the upstream demo, but couples this repo to a sibling
checkout and its venv/setup scripts. Rejected in favor of a first-class
`mlx_server.py` backend using stock `mlx_lm`, matching the transformers backend.

## llama.cpp GGUF path via the PrismML llama.cpp fork

Viable (the `Ternary-Bonsai-27B-gguf` pack exists, with custom 2-bit GEMM
kernels for Metal/CUDA), but it is a different artifact and a different serving
path; it can be added as a separate GGUF sidecar/profile without conflicting
with this MLX backend.

## Custom MLX loader against the PrismML MLX fork

Rejected for the 2-bit pack: stock `mlx_lm` is reported sufficient, so a custom
fork loader is unnecessary complexity here.

# References

- Upstream model: <https://huggingface.co/prism-ml/Ternary-Bonsai-27B-mlx-2bit>
- Reference serving script: PrismML `Bonsai-demo/scripts/start_mlx_server.sh`
- Backend pattern: `lm_launcher/transformers_server.py`, `run-server.py`
- [ADR-003](./adr-003-tmux-service-set-launcher.md): a verified MLX worker would
  be a `./up` model-slug target.
