# Qwen3.6-27B

Recorded: 2026-04-27

## Artifact

- Local selector: `qwen36-27b-unsloth`
- Local path anchor: [Qwen3.6-27B/model.safetensors.index.json](/Users/jrepp/d/lm-based/Qwen3.6-27B/model.safetensors.index.json)
- Structured sidecar: [Qwen3.6-27B.safetensors.json](/Users/jrepp/d/lm-based/models/Qwen3.6-27B.safetensors.json)
- Upstream Unsloth repo: [unsloth/Qwen3.6-27B](https://huggingface.co/unsloth/Qwen3.6-27B)
- Canonical base model card: [Qwen/Qwen3.6-27B](https://huggingface.co/Qwen/Qwen3.6-27B)
- Format: `safetensors`
- Quantization: `BF16`

## Purpose

This local record tracks the full Unsloth snapshot of the dense `Qwen3.6-27B` model for local serving and routing experiments in this workspace.

## Snapshot Layout

- The local directory contains `15` safetensor shards plus tokenizer, config, and preprocessing files.
- The anchor file for the shard set is `model.safetensors.index.json`.
- The directory must remain intact; serving code should treat `Qwen3.6-27B/` as one model snapshot, not as independent files.

## Upstream Machine Guidance

The upstream Hugging Face material is the authoritative source for architecture and deployment guidance:

- Qwen lists this as a `27B` dense model with `262,144` native context.
- Qwen documents YaRN-based scaling support for contexts beyond the native window.
- If deployment runs out of memory, context length should be reduced before assuming the model is unusable.

## Local Operational Notes

- This is a Transformers-style snapshot, not a GGUF artifact.
- The current repo validator is still GGUF-biased and warns on non-GGUF sidecars even though this snapshot is indexed correctly.
- Keep provenance conservative unless shard checksums are explicitly verified and recorded.

## Sources

- Unsloth snapshot: [unsloth/Qwen3.6-27B](https://huggingface.co/unsloth/Qwen3.6-27B)
- Canonical Qwen card: [Qwen/Qwen3.6-27B](https://huggingface.co/Qwen/Qwen3.6-27B)
