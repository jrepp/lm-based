# Qwen3-Coder-Next Q6_K Local Model Card

Recorded: 2026-04-27

## Artifact

- Local selector: `qwen3-coder-next-q6k`
- Upstream GGUF repo: [unsloth/Qwen3-Coder-Next-GGUF](https://huggingface.co/unsloth/Qwen3-Coder-Next-GGUF)
- Canonical base model card: [Qwen/Qwen3-Coder-Next](https://huggingface.co/Qwen/Qwen3-Coder-Next)
- Quantization: `Q6_K`
- Published GGUF size on Hugging Face: `65.6 GB`

## Purpose

This local record tracks the Unsloth `Q6_K` GGUF variant of `Qwen3-Coder-Next`, selected as a high-quality single-machine deployment target for an `80 GB` accelerator class.

## Upstream Machine Requirements

The upstream Hugging Face model card gives memory-oriented guidance rather than naming exact machine SKUs:

- Unsloth says `4-bit` quants should have more than `45 GB` of unified memory or combined RAM/VRAM.
- Unsloth says any `2-bit XL` quant or above should have more than `30 GB` of unified memory or combined RAM/VRAM for best results.
- The Qwen3-Coder-Next card also notes that if local runs hit OOM, context length should be reduced, with `32,768` tokens given as an example fallback.
- The deployment examples on the upstream card use tensor-parallel serving rather than claiming a single-GPU 256K-context fit.

## Artifact-Specific Machine Fit

The following is an inference from the upstream Hugging Face size table, not a direct vendor requirement:

- `Qwen3-Coder-Next Q6_K` is listed at `65.6 GB`, so a machine needs at least that much effective model memory just to hold the quantized weights.
- Practical single-machine deployment needs additional headroom for KV cache and runtime overhead, especially at long context.
- An `80 GB H100` is therefore a reasonable target for this artifact, while `Q8_0` at `84.8 GB` is not a comfortable fit on the same class of card.

## Operational Notes

- This Unsloth quant is published as a sharded GGUF under the `Q6_K/` prefix.
- For long-context serving, memory pressure is strongly affected by KV cache settings and requested context length.
- If local memory is tight, lowering context is the first upstream-recommended mitigation.

## Sources

- Unsloth GGUF card: [unsloth/Qwen3-Coder-Next-GGUF](https://huggingface.co/unsloth/Qwen3-Coder-Next-GGUF)
- Canonical Qwen card: [Qwen/Qwen3-Coder-Next](https://huggingface.co/Qwen/Qwen3-Coder-Next)
