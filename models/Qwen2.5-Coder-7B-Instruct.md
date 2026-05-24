# Qwen2.5-Coder-7B-Instruct

Recorded: 2026-04-29

## Artifact

- Local selector: `qwen25-coder-7b-instruct`
- Local path anchor: [Qwen2.5-Coder-7B-Instruct/model.safetensors.index.json](/Users/jrepp/d/lm-based/Qwen2.5-Coder-7B-Instruct/model.safetensors.index.json)
- Structured sidecar: [Qwen2.5-Coder-7B-Instruct.safetensors.json](/Users/jrepp/d/lm-based/models/Qwen2.5-Coder-7B-Instruct.safetensors.json)
- Upstream Unsloth repo: [unsloth/Qwen2.5-Coder-7B-Instruct](https://huggingface.co/unsloth/Qwen2.5-Coder-7B-Instruct)
- Canonical base model card: [Qwen/Qwen2.5-Coder-7B-Instruct](https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct)
- Format: `safetensors`
- Quantization: `BF16`

## Purpose

This local record tracks the full Unsloth snapshot of `Qwen2.5-Coder-7B-Instruct` as the repo's fast tool-calling Transformers model.

## Serving Path

- This model is served via `transformers serve`, not `llama-server`.
- The repo wrapper is selected by `PROFILE=qwen2.5-coder-transformers`.
- The wrapper uses continuous batching and exposes an OpenAI-compatible endpoint at `http://127.0.0.1:8001/v1`.

## Upstream Guidance

- Qwen lists this as a `7.61B` instruction-tuned coder model.
- Native context is `131,072` tokens.
- Hugging Face `transformers serve` supports OpenAI-style tool calling, and the serving docs say tool calling is currently limited to the Qwen family.

## Operational Notes

- The snapshot contains `4` safetensor shards plus tokenizer and config files.
- Keep the model directory intact; the anchor file is `model.safetensors.index.json`.
- For higher-throughput production serving, the upstream docs still recommend dedicated engines such as `vLLM` or `SGLang`.

## Sources

- Unsloth snapshot: [unsloth/Qwen2.5-Coder-7B-Instruct](https://huggingface.co/unsloth/Qwen2.5-Coder-7B-Instruct)
- Canonical Qwen card: [Qwen/Qwen2.5-Coder-7B-Instruct](https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct)
- Transformers serve docs: https://huggingface.co/docs/transformers/main/en/serving
