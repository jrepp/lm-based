# Model Card Index

Recorded: 2026-04-13

This file maps locally stored model artifacts in this workspace to their upstream model cards.

## Local Models

| Local file | Type | Canonical upstream model card | GGUF source card | Notes |
| --- | --- | --- | --- | --- |
| [Qwen3.5-35B-A3B-Q4_K_M.gguf](/Users/jrepp/d/qwen/Qwen3.5-35B-A3B-Q4_K_M.gguf) | Local GGUF quant | [Qwen/Qwen3.5-35B-A3B](https://huggingface.co/Qwen/Qwen3.5-35B-A3B) | [unsloth/Qwen3.5-35B-A3B-GGUF](https://huggingface.co/unsloth/Qwen3.5-35B-A3B-GGUF) | User-reported likely GGUF provenance is Unsloth. Structured sidecar: [models/Qwen3.5-35B-A3B-Q4_K_M.gguf.json](/Users/jrepp/d/qwen/models/Qwen3.5-35B-A3B-Q4_K_M.gguf.json). |
| [Qwen3-Coder-Next-IQ4_XS.gguf](/Users/jrepp/d/qwen/Qwen3-Coder-Next-IQ4_XS.gguf) | Planned GGUF download | [Qwen/Qwen3-Coder-Next](https://huggingface.co/Qwen/Qwen3-Coder-Next) | [unsloth/Qwen3-Coder-Next-GGUF](https://huggingface.co/unsloth/Qwen3-Coder-Next-GGUF) | Structured sidecar: [models/Qwen3-Coder-Next-IQ4_XS.gguf.json](/Users/jrepp/d/qwen/models/Qwen3-Coder-Next-IQ4_XS.gguf.json). Selected slug: `qwen3-coder-next-iq4xs`. |
| [Gemma-4-E2B-Uncensored-HauhauCS-Aggressive-Q4_K_P.gguf](/Users/jrepp/d/qwen/Gemma-4-E2B-Uncensored-HauhauCS-Aggressive-Q4_K_P.gguf) | Planned GGUF download | [HauhauCS/Gemma-4-E2B-Uncensored-HauhauCS-Aggressive](https://huggingface.co/HauhauCS/Gemma-4-E2B-Uncensored-HauhauCS-Aggressive) | [HauhauCS/Gemma-4-E2B-Uncensored-HauhauCS-Aggressive](https://huggingface.co/HauhauCS/Gemma-4-E2B-Uncensored-HauhauCS-Aggressive) | Gemma-4 2B uncensored finetune. Repo uses _P-suffix quants. Multimodal projector also available (mmproj-*-f16.gguf). Structured sidecar: [models/Gemma-4-E2B-Uncensored-HauhauCS-Aggressive-Q4_K_P.gguf.json](/Users/jrepp/d/qwen/models/Gemma-4-E2B-Uncensored-HauhauCS-Aggressive-Q4_K_P.gguf.json). Selected slug: `gemma4-e2b-uncensored-aggressive-q4kp`. |

## Planned / Referenced Models

| Model | Upstream model card | Notes |
| --- | --- | --- |
| Qwen3-Coder-Next | [Qwen/Qwen3-Coder-Next](https://huggingface.co/Qwen/Qwen3-Coder-Next) | Target model for the next llama-server integration work. First planned artifact is `qwen3-coder-next-iq4xs`. |

## Maintenance Notes

- When adding a new local GGUF, append a row here with the exact local filename and the canonical upstream model card.
- If you know the precise GGUF publisher for a local file, replace the generic GGUF source link with that exact repository.
- Keep this index conservative: if provenance is unclear, state that directly instead of inferring a specific quantizer.
