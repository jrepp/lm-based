# Model Card Index

Recorded: 2026-04-13

This file maps locally stored model artifacts in this workspace to their upstream model cards.

## Local Models

| Local file | Type | Canonical upstream model card | GGUF source card | Notes |
| --- | --- | --- | --- | --- |
| [Qwen3.5-35B-A3B-Q4_K_M.gguf](/Users/jrepp/d/lm-based/Qwen3.5-35B-A3B-Q4_K_M.gguf) | Local GGUF quant | [Qwen/Qwen3.5-35B-A3B](https://huggingface.co/Qwen/Qwen3.5-35B-A3B) | [unsloth/Qwen3.5-35B-A3B-GGUF](https://huggingface.co/unsloth/Qwen3.5-35B-A3B-GGUF) | User-reported likely GGUF provenance is Unsloth. Structured sidecar: [models/Qwen3.5-35B-A3B-Q4_K_M.gguf.json](/Users/jrepp/d/lm-based/models/Qwen3.5-35B-A3B-Q4_K_M.gguf.json). |
| [Qwen3-Coder-Next-IQ4_XS.gguf](/Users/jrepp/d/lm-based/Qwen3-Coder-Next-IQ4_XS.gguf) | Planned GGUF download | [Qwen/Qwen3-Coder-Next](https://huggingface.co/Qwen/Qwen3-Coder-Next) | [unsloth/Qwen3-Coder-Next-GGUF](https://huggingface.co/unsloth/Qwen3-Coder-Next-GGUF) | Structured sidecar: [models/Qwen3-Coder-Next-IQ4_XS.gguf.json](/Users/jrepp/d/lm-based/models/Qwen3-Coder-Next-IQ4_XS.gguf.json). Selected slug: `qwen3-coder-next-iq4xs`. |
| [Gemma-4-E2B-Uncensored-HauhauCS-Aggressive-Q4_K_P.gguf](/Users/jrepp/d/lm-based/Gemma-4-E2B-Uncensored-HauhauCS-Aggressive-Q4_K_P.gguf) | Planned GGUF download | [HauhauCS/Gemma-4-E2B-Uncensored-HauhauCS-Aggressive](https://huggingface.co/HauhauCS/Gemma-4-E2B-Uncensored-HauhauCS-Aggressive) | [HauhauCS/Gemma-4-E2B-Uncensored-HauhauCS-Aggressive](https://huggingface.co/HauhauCS/Gemma-4-E2B-Uncensored-HauhauCS-Aggressive) | Gemma-4 2B uncensored finetune. Structured sidecar: [models/Gemma-4-E2B-Uncensored-HauhauCS-Aggressive-Q4_K_P.gguf.json](/Users/jrepp/d/lm-based/models/Gemma-4-E2B-Uncensored-HauhauCS-Aggressive-Q4_K_P.gguf.json). Selected slug: `gemma4-e2b-uncensored-aggressive-q4kp`. |
| [Mistral-7B-Instruct-v0.3-Q4_K_M.gguf](/Users/jrepp/d/lm-based/Mistral-7B-Instruct-v0.3-Q4_K_M.gguf) | Planned GGUF download | [mistralai/Mistral-7B-Instruct-v0.3](https://huggingface.co/mistralai/Mistral-7B-Instruct-v0.3) | [bartowski/Mistral-7B-Instruct-v0.3-GGUF](https://huggingface.co/bartowski/Mistral-7B-Instruct-v0.3-GGUF) | Latest official Mistral 7B instruct (v0.3). Structured sidecar: [models/Mistral-7B-Instruct-v0.3-Q4_K_M.gguf.json](/Users/jrepp/d/lm-based/models/Mistral-7B-Instruct-v0.3-Q4_K_M.gguf.json). Selected slug: `mistral-7b-instruct-v03-q4km`. |
| [Ouro-2.6B-Thinking/](/Users/jrepp/d/ouro/models/Ouro-2.6B-Thinking/) | Local safetensors | [ByteDance/Ouro-2.6B-Thinking](https://huggingface.co/ByteDance/Ouro-2.6B-Thinking) | N/A (transformers-based) | Ouro-2.6B with thinking token support. Uses FastAPI server (not llama-server). Structured sidecar: [models/Ouro-2.6B-Thinking.safetensors.json](/Users/jrepp/d/lm-based/models/Ouro-2.6B-Thinking.safetensors.json). Selected slug: `ouro-2.6b-thinking`. |

## Planned / Referenced Models

| Model | Upstream model card | Notes |
| --- | --- | --- |
| Qwen3-Coder-Next | [Qwen/Qwen3-Coder-Next](https://huggingface.co/Qwen/Qwen3-Coder-Next) | Target model for the next llama-server integration work. First planned artifact is `qwen3-coder-next-iq4xs`. |

## Maintenance Notes

- When adding a new local GGUF, append a row here with the exact local filename and the canonical upstream model card.
- If you know the precise GGUF publisher for a local file, replace the generic GGUF source link with that exact repository.
- Keep this index conservative: if provenance is unclear, state that directly instead of inferring a specific quantizer.
