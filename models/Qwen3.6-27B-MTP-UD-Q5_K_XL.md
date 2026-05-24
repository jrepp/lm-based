# Qwen3.6-27B-MTP UD-Q5_K_XL

Recorded: 2026-05-24

## Artifact

- Local selector: `qwen36-27b-mtp-ud-q5k-xl`
- Local path: [Qwen3.6-27B-UD-Q5_K_XL.gguf](/Users/jrepp/d/lm-based/Qwen3.6-27B-UD-Q5_K_XL.gguf)
- Structured sidecar: [Qwen3.6-27B-MTP-UD-Q5_K_XL.gguf.json](/Users/jrepp/d/lm-based/models/Qwen3.6-27B-MTP-UD-Q5_K_XL.gguf.json)
- GGUF source repo: [unsloth/Qwen3.6-27B-MTP-GGUF](https://huggingface.co/unsloth/Qwen3.6-27B-MTP-GGUF)
- Canonical model card: [Qwen/Qwen3.6-27B](https://huggingface.co/Qwen/Qwen3.6-27B)
- Format: `gguf`
- Quantization: `UD-Q5_K_XL`
- Local size: `20,350,682,240` bytes
- Local SHA-256: `5a3c61033581754d507ffdcbf0629214cbfbd58a2edbec80d93f6ec2af44d227`

## Model Facts

- Qwen3.6 27B non-MoE language model family; the upstream card describes it as a causal language model with a vision encoder.
- MTP is trained with multi-steps.
- Native context length is `262,144` tokens.
- Upstream documentation says the context can be extended beyond native length with RoPE scaling such as YaRN for long-horizon workloads.
- The Unsloth MTP GGUF card lists `UD-Q5_K_XL` in the 5-bit quantization group at about `20.4 GB`.

## Local Serving

- Launcher profile: `qwen3.6-mtp`
- Local server binary: `/Users/jrepp/d/llama.cpp/build/bin/llama-server`
- Context: `262144`
- Speculative decoding: `--spec-type draft-mtp --spec-draft-n-max 4`
- Parallel slots: `1`
- KV cache: `q4_0/q4_0`
- Flash attention: `on`

The current OpenCode config in `../tidal/opencode.json` points at this slug with:

- context limit: `262144`
- output limit: `16384`

## Operational Notes

- The file was downloaded locally on 2026-05-24 from `unsloth/Qwen3.6-27B-MTP-GGUF`.
- Local file size and SHA-256 are recorded, but upstream provenance is not marked `verified` because the checksum has not been matched against a published source checksum.
- llama.cpp reports the embedded MTP context during startup and initializes `draft-mtp` speculative decoding for this artifact.

## Sources

- MTP GGUF source: [unsloth/Qwen3.6-27B-MTP-GGUF](https://huggingface.co/unsloth/Qwen3.6-27B-MTP-GGUF)
- Canonical model card: [Qwen/Qwen3.6-27B](https://huggingface.co/Qwen/Qwen3.6-27B)
