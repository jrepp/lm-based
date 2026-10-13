# Running Large LLMs via llama.cpp on MacBook Pro M5 Max 128GB (as of October 2026)

Scope: M5 Max hardware facts, macOS GPU wired-memory limit, measured tok/s for large MoE GGUF models on 128GB Max-class Apple Silicon, quantization strategy (Unsloth dynamic quants + KV cache), and llama.cpp support gaps for 2026-era architectures on Metal. All facts reflect sources retrieved 2026-10-10.

## Key Question 1: M5 Max specifics — bandwidth, GPU cores, generational comparison, llama.cpp/MLX optimizations

### Takeaway

The M5 Max (shipped March 11, 2026) has 614 GB/s unified-memory bandwidth, a 32–40-core GPU with a Neural Accelerator in every core, and up to 128GB unified memory. Decode is only ~12% faster than M4 Max (546 GB/s) — bandwidth-bound — but prompt processing gains are large (Apple claims up to 4x vs M4 Pro/Max), mostly realized through MLX; llama.cpp-specific M5 tuning evidence is thin.

### Cited Findings

- M5 Max: 614 GB/s bandwidth (460 GB/s on the 32-core GPU variant), 32–40 GPU cores, 18-core CPU, 36/48/64/128GB unified memory options; M5 Pro is 307 GB/s / 16–20 cores / up to 64GB; base M5 is 153 GB/s; M5 Ultra (Mac Studio, September 2026) is 1,228 GB/s / 64–80 cores / up to 512GB — [LLMCheck M5 Max guide, corrected 2026-10-05](https://llmcheck.net/blog/apple-silicon-m5-max-local-ai-guide/)
- M5 Pro and M5 Max MacBook Pros began shipping March 11, 2026 — [Hardware Corner](https://www.hardware-corner.net/m5-max-local-llm-benchmarks-20261233/), [modelfit.io](https://modelfit.io/blog/m5-pro-max-local-llm-2026/)
- Comparison chips: M4 Max = 546 GB/s (32–40 GPU cores, up to 128GB), M3 Max = 400 GB/s (30–40 cores, up to 128GB), M2 Ultra = 800 GB/s — [LLMCheck](https://llmcheck.net/blog/apple-silicon-m5-max-local-ai-guide/)
- Decode gain of M5 Max over M4 Max ≈ 7–12%, matching the bandwidth ratio (614 vs 546 GB/s); LLMCheck's earlier "28% faster" claim was formally retracted and corrected on 2026-09-23 — [LLMCheck](https://llmcheck.net/blog/apple-silicon-m5-max-local-ai-guide/)
- Every M5-generation GPU core has a Neural Accelerator (matrix hardware); Apple quotes "up to 4x faster LLM prompt processing than M4 Pro and M4 Max"; the gain is in prefill, not decode — [LLMCheck](https://llmcheck.net/blog/apple-silicon-m5-max-local-ai-guide/), [InsiderLLM](https://insiderllm.com/guides/apple-m5-pro-max-local-ai/), [llmrequirements.com](https://llmrequirements.com/apple-m5-max-local-llm-guide)
- The 16-core Neural Engine is a separate block used by Core ML/Apple Intelligence; neither llama.cpp nor MLX runs LLM decode on it — [LLMCheck](https://llmcheck.net/blog/apple-silicon-m5-max-local-ai-guide/)
- MLX often decodes ~20% faster than llama.cpp for the same model on Apple Silicon (one published comparison: 110 vs 90 tok/s for Qwen3 30B-A3B on M4 Max, arXiv 2601.19139), using Metal kernels tuned per-chip including M5 Neural Accelerators — [LLMCheck](https://llmcheck.net/blog/apple-silicon-m5-max-local-ai-guide/)
- Measured first M5 Max 128GB benchmarks (MLX `mlx_lm`, 14-inch MBP, reddit user cryingneko): Qwen3.5-122B-A10B 4-bit (69.6GB) 65.9 t/s gen @4K ctx falling to 54.9 @32K, PP 881–1239 t/s; Qwen3-Coder-Next 8-bit (84.7GB) 79.3 t/s @4K → 48.2 @64K, PP 754–1887 t/s; gpt-oss-120b Q8 (64GB) 87.9 t/s @4K → 64.5 @32K, PP 1325–2710 t/s; Qwen3.5-27B dense 6-bit (26GB) 23.6 t/s @4K → 14.9 @32K — [Hardware Corner](https://www.hardware-corner.net/m5-max-local-llm-benchmarks-20261233/)
- Same review vs RTX Pro 6000 Blackwell 96GB: RTX leads PP by 2.0–4.9x and gen by ~1.5–2.8x depending on model/context; the M5 Max handles 64K+ contexts the RTX 5090 (32GB) cannot load — [Hardware Corner](https://www.hardware-corner.net/m5-max-local-llm-benchmarks-20261233/)
- Only llama.cpp-on-M5 data point found: DFlash2 speculative decoding evaluated on Apple M5 Pro 64GB with Qwen3.8-27B Q4_K_M dense: baseline decode 10.42 t/s; DFlash2 19.31 t/s (1.85x, acceptance ≈ 4.9–5.1 tokens) — [llama.cpp PR #27342](https://github.com/ggml-org/llama.cpp/pull/27342)

### Inferences

- For your 128GB M5 Max, llama.cpp decode will likely land ~10–15% below the MLX figures above for the same models/quants (MLX-vs-llama.cpp gap is ~20% on M4 Max; M5 Max adds ~12% bandwidth over M4 Max).
- Dense-model decode scales almost linearly with bandwidth (contracollective measured tok/s tracking GB/s across M5 Pro/Max/Ultra — [Contracollective](https://contracollective.com/blog/apple-silicon-memory-bandwidth-local-llm-tokens-per-second-m5-2026), snippet-level source); dense 27B Q6 ≈ 20–24 t/s and 70B-class dense Q4 ≈ 25–28 t/s are the realistic M5 Max ballpark (LLMCheck estimates ~29 t/s for Qwen3.8-27B Q4 — [LLMCheck](https://llmcheck.net/blog/apple-silicon-m5-max-local-ai-guide/)).

### Gaps

- No llama.cpp/Metal-specific M5 Max benchmark tables were found (all M5 Max numbers in circulation are MLX-based, or llama.cpp on other M5 chips); llama.cpp Metal usage of M5 Neural Accelerators for prefill is undocumented in the sources found.
- No Apple-published M5 Max die/bandwidth analysis (anandtech-style) was retrieved; figures above trace to Apple spec pages via secondary sites.

## Key Question 2: macOS GPU wired memory limit — default %, raising it, realistic budget on 128GB

### Takeaway

macOS wires ~75% of unified RAM to the GPU by default — 96GB on a 128GB machine. One sysctl raises it: `sudo sysctl iogpu.wired_limit_mb=122880` gives ~120GB; the practical planning number is 96GB stock, ~110–120GB tuned, keeping ~8GB for macOS. It resets on reboot.

### Cited Findings

- Default: Metal's `recommendedMaxWorkingSetSize` is set conservatively at roughly 75% of installed memory; llama.cpp, Ollama and other Metal runtimes treat it as a hard ceiling → ~96GB on 128GB — [LLM Configurator](https://llmconfigurator.com/en/guides/troubleshooting/increase-metal-vram-limit-apple-silicon), [ModelPiper](https://modelpiper.com/blog/iogpu-wired-limit-mb-mac), [ivanopcode devnote](https://github.com/ivanopcode/devnote-override-macos-metal-vram-cap)
- Raise it: `sudo sysctl iogpu.wired_limit_mb=122880` (≈120GB; 98304 = 96GB default; 131072 = 128GB, "not recommended"); on macOS Sonoma 14.x and later the key is `iogpu.wired_limit_mb` (older macOS used `debug.iogpu.wired_limit`) — [stencel.io](https://stencel.io/posts/apple-silicon-limitations-with-usage-on-local-llm%20.html), [RunAIHome 128GB guide](https://runaihome.com/blog/best-local-llm-128gb-unified-memory-2026/)
- Reset to default with `sudo sysctl iogpu.wired_limit_mb=0`; persistence via `/etc/sysctl.conf` is possible but riskier (a bad value freezes the Mac until reboot clears it); llama.cpp issue threads use 122880 on large-memory machines (e.g., issue #13361) — [InsiderLLM Ollama guide](https://insiderllm.com/guides/ollama-mac-setup-optimization/), [LocalAIMaster](https://localaimaster.com/blog/mac-memory-pressure-local-llm)
- Guidance: leave ~8–16GB for macOS or the machine starts paging mid-generation; RunAIHome's planning number for the 128GB tier is "96GB out of the box, ~120GB tuned" — [RunAIHome](https://runaihome.com/blog/best-local-llm-128gb-unified-memory-2026/), [InsiderLLM](https://insiderllm.com/guides/ollama-mac-setup-optimization/)
- Verify the active ceiling in llama.cpp: the `ggml_metal_init: recommendedMaxWorkingSetSize` line printed at startup reflects `iogpu.wired_limit_mb` — [llama.cpp discussion #2182](https://github.com/ggml-org/llama.cpp/discussions/2182)

### Inferences

- On this machine: budget ~96GB without any sysctl (safe default), ~112–118GB (114688–120832 MB) as a stable raised setting, ~120GB (122880) as the community-standard aggressive setting for single-model serving. With llama-swap auto-swapping multiple models, prefer the conservative end because two large models can transiently coexist.
- Fits math for planning: model file + KV cache + ~1–2GB compute buffers must stay under the wired limit; RunAIHome uses "unified memory ≥ 1.5x model file size" as a rule of thumb (LLMCheck states the same) — [RunAIHome](https://runaihome.com/blog/best-local-llm-128gb-unified-memory-2026/)

### Gaps

- No authoritative Apple documentation on `iogpu.wired_limit_mb` was found (it is an undocumented kernel parameter); the "75%" default is consistently reported but not officially specified, and no source confirms a macOS-26.x-specific change to it.
- No systematic report of instability thresholds on M5 Max + 128GB specifically (e.g., whether 120GB vs 116GB matters on this chip) was found.

## Key Question 3: Real-world tok/s for large MoE models on 128GB Max-class Apple Silicon

### Takeaway

The realistic best fit-and-fast models on a 128GB M5 Max are 100B-class MoEs with ≤12B active params: ~50–90 t/s decode (MLX, falling 15–35% at long context), ~0.9–2.7K t/s prompt processing. Frontier 355B–1T MoEs do not fit even at 1–2 bit. Qwen3-235B Q3 (~101GB) needs the raised wired limit; measured ~11 t/s on 256 GB/s Strix Halo implies roughly 2x that on 614 GB/s M5 Max (inference).

### Cited Findings

- Measured, M5 Max 128GB MLX (the only first-party M5 Max numbers found): Qwen3.5-122B-A10B 4-bit 54.9–65.9 t/s; Qwen3-Coder-Next 8-bit 48.2–79.3 t/s (peak memory 87.1–92.6GB, i.e., ~90GB at 64K ctx — fits 128GB only with raised wired limit); gpt-oss-120b Q8 64.5–87.9 t/s; prompt processing 591–2710 t/s depending on model and context — [Hardware Corner](https://www.hardware-corner.net/m5-max-local-llm-benchmarks-20261233/)
- gpt-oss-120b (117B-A5B), MXFP4-native 63.4GB: 34–56 t/s on Strix Halo, 38–55 t/s DGX Spark (community llama.cpp benchmarks; 55.57 t/s tg128 best case) — [RunAIHome](https://runaihome.com/blog/best-local-llm-128gb-unified-memory-2026/), [kyuz0 Strix Halo toolboxes](https://kyuz0.github.io/amd-strix-halo-toolboxes/), [Hardware Corner DGX Spark comparison](https://www.hardware-corner.net/first-dgx-spark-llm-benchmarks/)
- Qwen3-235B-A22B Q3 ≈ 101GB: does NOT load under default limits (needs Linux GTT or macOS `iogpu.wired_limit_mb` raise); measured ~11 t/s on Strix Halo; no Mac-specific measurement found — [RunAIHome](https://runaihome.com/blog/best-local-llm-128gb-unified-memory-2026/)
- Inkling-Small 276B-A12B: Unsloth UD-Q2_K_XL = 87.9GB, the only frontier-adjacent quant under the 96GB default line, with ~8GB left for KV (plan 8–16K context, not the headline 1M); ~20–30 t/s on Strix Halo is an estimate, not a benchmark; 2-bit quality tax unmeasured — [RunAIHome](https://runaihome.com/blog/best-local-llm-128gb-unified-memory-2026/), [Unsloth Inkling docs](https://unsloth.ai/docs/models/inkling)
- Nemotron 3 Super 120B-A12B UD-IQ4_XS (~60–65GB): 18.43 t/s tg128 measured on Strix Halo llama.cpp — [RunAIHome](https://runaihome.com/blog/best-local-llm-128gb-unified-memory-2026/), [Strix Halo wiki llama.cpp table](https://strixhalo.wiki/AI/llamacpp-performance)
- Llama 4 Scout 109B-A17B Q4_K_M ≈ 55GB: fits easily, decode bandwidth-bound between the Qwen and Nemotron figures — [RunAIHome](https://runaihome.com/blog/best-local-llm-128gb-unified-memory-2026/), [Unsloth Llama 4 docs](https://unsloth.ai/docs/models/tutorials/llama-4-how-to-run-and-fine-tune)
- Dense 70B Q4 (~43GB): 15–22 t/s measured on M4 Max 128GB (CraftRigs); LLMCheck estimates ~28 t/s on M5 Max and ~12 t/s for Llama 3.3 70B (their estimates are internally inconsistent across tables — treat as ±2x) — [RunAIHome](https://runaihome.com/blog/best-local-llm-128gb-unified-memory-2026/), [LLMCheck](https://llmcheck.net/blog/apple-silicon-m5-max-local-ai-guide/)
- LLMCheck index estimates for M5 Max 128GB (estimates, not lab measurements): Qwen3.8-Flash-Next Q4 ~49 t/s; DeepSeek V4 Flash 2-bit ~39 t/s (community); KAT-Coder-V2.5 ~117 t/s; Qwen3-Coder-Next ~49 t/s — [LLMCheck](https://llmcheck.net/blog/apple-silicon-m5-max-local-ai-guide/)
- Qwen3.8-Flash-Next (arch `qwen4exp`, 125B-A6B + 51B embedding + 4B MTP): Unsloth GGUF UD-Q4_K_XL = 93.7GB in 3 shards — needs the raised wired limit — [llama.cpp issue #27763](https://github.com/ggml-org/llama.cpp/issues/27763), [llama.cpp PR #27742](https://github.com/ggml-org/llama.cpp/pull/27742)
- Qwen3-Coder-Next (arch `qwen3next`, 80B-A3B, 79.67B params, 512 experts top-10): Q6_K = 61.06 GiB (6.58 BPW), 2–3 shards; MLX 8-bit (84.7GB) runs 48–79 t/s on M5 Max — [llama.cpp issue #27727](https://github.com/ggml-org/llama.cpp/issues/27727), [Hardware Corner](https://www.hardware-corner.net/m5-max-local-llm-benchmarks-20261233/)
- What does NOT fit 128GB (2026 flagships): GLM-5.2 744B (UD-IQ2_M = 239GB, needs 256GB), Kimi K2.7/K3 1T (2-bit ~245–325GB), MiniMax M3 428B (Q2_K_XL = 143GB, ~23GB over the tuned ceiling), Qwen3-Coder 480B (UD-IQ1_M ~150GB) — [RunAIHome](https://runaihome.com/blog/best-local-llm-128gb-unified-memory-2026/)
- Current GLM flagship generation: GLM-5 = 745B total / 44B active MoE, 200K context; GLM-5.2/5.3 = 744B with 1M context; GLM-5.3-Flash is the small sibling — [glm-5.org](https://glm-5.org/zh/), [bigmodel.cn GLM-5.2 docs](https://docs.bigmodel.cn/cn/guide/models/text/glm-5.2), [z.ai](https://z.ai/) (retrieved via Bing, 2026-10)

### Inferences

- Scaling by bandwidth (546 → 614 GB/s, +12%; and 256 → 614, +2.4x): gpt-oss-120b-class on M5 Max llama.cpp should land ~55–70 t/s (consistent with the 64–88 t/s MLX Q8 measurements); Qwen3-235B-A22B Q3 on M5 Max ≈ 20–27 t/s (inference from the 11 t/s Strix Halo measurement).
- The sweet spot for "most capable model that is actually pleasant to serve" on this machine is a 100–125B MoE at 4–5 bpw dynamic quant (60–95GB file), not a 355B+ model at 1–2 bit.
- Your planned Qwen3-Coder-Next IQ4_XS sidecar: Q6_K is confirmed at 61GB; a 4.X-bit build will land roughly 42–48GB by BPW math (unsourced — verify file size on Hugging Face before writing the sidecar `size_bytes`).

### Gaps

- No October-2026 measurements found for GLM-4.5/4.6 355B or GLM-5.x on any 128GB Mac (the GLM flagship line moved to 744B, which cannot fit; GLM-4.6-era community numbers from 2025 were not re-located in this search).
- No 128GB-Mac numbers found for Llama-4-Maverick, DeepSeek V3/R1 full, Kimi (K2.7/K3 don't fit), or MiniMax M2 (only the "MiniMax M3 428B doesn't fit" row was found).
- LLMCheck's per-model figures are explicitly index estimates, not lab measurements — use only as order-of-magnitude priors.

## Key Question 4: Quantization strategy — Unsloth dynamic quants vs standard K-quants, KV cache quantization, long-context costs

### Takeaway

For MoE models, Unsloth dynamic quants (UD-*: IQ1_S → Q6_K variants that spend more bits on attention/shared/expert-critical tensors) are the de-facto standard for the 100B+ class and are what most measured results above use. KV quantization to q8_0 is near-lossless (1.88x compression) and q4_0 is acceptable (3.56x); hybrid-attention models (qwen3next) need only ~2.3GB KV per 100K tokens at f16, while standard-attention large MoEs pay ~10–30GB+ for very long contexts.

### Cited Findings

- Unsloth dynamic quant sizes in current use (128GB tier): Inkling-Small 276B UD-Q2_K_XL 87.9GB; Qwen3-235B Q3 ~101GB (barteri/other Q3, for raised-limit machines); Qwen3.8-Flash-Next UD-Q4_K_XL 93.7GB / UD-IQ4_XS 93.7GB (3 shards); Nemotron 3 Super UD-IQ4_XS ~60–65GB; Qwen3-Coder-Next UD-Q6_K 61.06 GiB (6.58 BPW); gpt-oss-120b ships MXFP4-native 63.4GB; Llama 4 Scout Q4_K_M ~55GB — [RunAIHome](https://runaihome.com/blog/best-local-llm-128gb-unified-memory-2026/), [Unsloth docs](https://unsloth.ai/docs/models/inkling), [llama.cpp issue #27763](https://github.com/ggml-org/llama.cpp/issues/27763), [llama.cpp issue #27727](https://github.com/ggml-org/llama.cpp/issues/27727)
- Low-bit quants of new architectures have needed llama.cpp quantizer fixes: the qwen4exp port required three `llama-quant.cpp` fixes (32-block-type fallback abort, `per_layer_token_embd` tensor-type naming, and a work-buffer sized `nelements*4` that ballooned to 150GB for a 51.2G-element tensor) — [llama.cpp PR #27742](https://github.com/ggml-org/llama.cpp/pull/27742)
- KV cache quantization quality (llama.cpp benchmark, Qwen3.5-4B Q4_K_M, CPU, wikitext-2): f16 PPL 13.8387 / q8_0 13.8348 (1.88x compression, KLD 0.0032) / q4_0 13.8400 (3.56x compression, KLD 0.0091) — i.e., q8_0 is free and q4_0 nearly so on PPL; an experimental TurboQuant KV type (tbq3_0/tbq4_0, 3.06/4.06 bpw) was proposed but not merged (CPU-only, closed June 2026) — [llama.cpp PR #21089](https://github.com/ggml-org/llama.cpp/pull/21089)
- `--cache-type-k/--cache-type-v q8_0` (and q4_0) are in routine production use on 2026 hybrid models in llama.cpp issue reports — [llama.cpp issue #30307](https://github.com/ggml-org/llama.cpp/issues/30307), [issue #30033](https://github.com/ggml-org/llama.cpp/issues/30033)
- Long-context KV cost, hybrid-attention (qwen3next / Qwen3-Coder-Next: 48 layers, only 12 full-attention; 36 Gated-DeltaNet linear-attention layers with fixed recurrent state): llama.cpp allocates a 6,144 MiB KV buffer at the full 262,144-token context (K 3072 MiB + V 3072 MiB, f16) → ≈2.3 GiB per 100K tokens at f16 — [llama.cpp issue #27727 load log](https://github.com/ggml-org/llama.cpp/issues/27727)
- Long-context cost, standard-attention comparison point (MLX): Qwen3-Coder-Next 8-bit peak memory grew 87.1GB @4K → 89.6GB @32K → 92.6GB @64K (≈9GB/100K including all runtime buffers); Qwen3.5-122B-A10B 4-bit (69.6GB weights) "requires around 78GB with full context buffers" — [Hardware Corner](https://www.hardware-corner.net/m5-max-local-llm-benchmarks-20261233/)
- MTP/draft models are separate GGUFs sized ~2–4GB (e.g., `mtp-Qwen3.8-Flash-Next-Q4_0.gguf`; ggml-org/am17an Qwen3.6-27B-MTP and Qwen3.6-35B-A3B-MTP GGUFs) — [llama.cpp PR #22673](https://github.com/ggml-org/llama.cpp/pull/22673), [issue #30307](https://github.com/ggml-org/llama.cpp/issues/30307)

### Inferences

- On 128GB with the ~120GB wired limit and q8_0 KV: a 90–95GB UD-Q4_K_XL 100B-class MoE leaves ~20GB for KV + buffers → roughly 800K–2M tokens of hybrid-attention KV, or ~65–200K tokens for a standard-attention 122B model; the 96GB default limit leaves effectively no long-context room for anything above ~85GB files.
- q4_0 KV (~0.6GB/100K for qwen3next-class hybrids) is the right trade when chasing very long contexts; keep q8_0 for coding workloads where retrieval precision matters (Unsloth-style guidance and general practice; quality deltas above are from the 4B-model test — no 100B-class KV-quant PPL study was found).
- Standard Q4_K_M/Q6_K remain fine for dense and small-MoE models (your Qwen3.6-27B Q6_K at 21GB is comfortably in the quality-safe zone); the UD-* dynamic range matters mainly at ≤3 bpw where per-tensor bit allocation decides whether the model stays coherent.

### Gaps

- No 2026-dated Unsloth blog/doc page quantifying "what fits in 128GB" per-model or MoE-specific low-bpw quality measurements (perplexity/KLD of UD-Q2_K_XL vs Q4) was retrieved; the 87.9GB Inkling figure and quant names come via RunAIHome citing Unsloth docs.
- Per-100K KV costs for specific standard-attention models (GLM-5.2, DeepSeek-V4-class with MLA) were not found; MLA compresses KV heavily but no 2026 Mac-context figure was located.

## Key Question 5: llama.cpp support status/gaps for 2026-era architectures on Metal

### Takeaway

llama.cpp (now versioned v0.6.x, tag builds like b11548) has merged support for the 2026 hybrid wave: native MTP speculative decoding (`--spec-type draft-mtp`, merged May 2026), qwen3next (Gated DeltaNet hybrid), qwen4exp with QSA sparse attention (merged Aug 2026), and DSA sparse attention shared by DeepSeek-4/GLM ("glm-dsa"). The open problems are concentrated in the new hybrid archs: context-depth decode decay, concurrency crashes, and tool-calling leaks — reported almost entirely on CUDA/ROCm; Metal-specific status for these paths is largely unreported.

### Cited Findings

- MTP support (PR #22673, merged 2026-05-16): `--spec-type draft-mtp --spec-draft-n-max N`; MTP model loads from a separate GGUF with its own context/KV; tested on Qwen3.6-27B and Qwen3.6-35B-A3B; steady-state acceptance ~72–83% at draft 2–3, >2x speedup (DGX Spark: 7.1 → 16–21.6 t/s on Q8_0); known costs: PP slowdown from device-to-host embedding transfers, parallel decoding "supported but not fully optimized", Metal drafting improvements deferred to PR #23114 — [llama.cpp PR #22673](https://github.com/ggml-org/llama.cpp/pull/22673)
- Regression affecting your MTP setup class: after PR #30257 (merged post-v0.6.0), qwen4exp + draft-MTP aborts on image input (`GGML_ASSERT(ubatch.token …)` left in `graph_mtp`); open as of 2026-10-10; text-only MTP fine; works on v0.6.0 — [llama.cpp issue #30307](https://github.com/ggml-org/llama.cpp/issues/30307)
- qwen3next (Qwen3-Coder-Next, 80B-A3B): supported; GGA 16/2 heads, head dim 256, SSM state 128 / groups 16 / inner 4096; context 262,144. Backend-specific bugs reported: ROCm token-repeat corruption (closed, not planned), garbled output on ROCm gfx1150 while Vulkan works, silent corruption with `GGML_CUDA_ENABLE_UNIFIED_MEMORY=1` on ROCm, and CUDA fused-Gated-DeltaNet fallback crashes on Blackwell builds (LM Studio engine) — [issue #27727](https://github.com/ggml-org/llama.cpp/issues/27727), [issue #26682](https://github.com/ggml-org/llama.cpp/issues/26682), [issue #26148](https://github.com/ggml-org/llama.cpp/issues/26148), [issue #26481](https://github.com/ggml-org/llama.cpp/issues/26481)
- qwen4exp (Qwen3.8-Flash-Next, PR #27742 merged 2026-08-27): Gated DeltaNet on 3 of 4 layers, 512 experts top-10 + shared expert, QSA sparse attention (top-k budget 2048, compress ratio 4), hyper-connections, interleaved mrope, per-layer embeddings backed by a 97.7 GiB host-side n-gram hash table; wikitext PPL 4.0068 vs 4.0126 reference. Open issues: decode slowing ~linearly with context on CUDA (host-bound QSA block selection; improved but still ~11–42 t/s @250k vs ~50 t/s shallow on 5×3090), garbage output on Jetson Thor SM110 beyond 8 offloaded layers, crash under concurrent multi-slot batching, stochastic tool-call leakage as content, long-context stochastic EOS — [PR #27742](https://github.com/ggml-org/llama.cpp/pull/27742), [issue #28734](https://github.com/ggml-org/llama.cpp/issues/28734), [issue #27763](https://github.com/ggml-org/llama.cpp/issues/27763), [issue #27911](https://github.com/ggml-org/llama.cpp/issues/27911), [issue #30078](https://github.com/ggml-org/llama.cpp/issues/30078)
- DSA/MLA lineage supported: PR #27742 lifted `build_attn_mask_top_k` out of the DSA `build_attn` overload shared with `deepseek32`/`glm-dsa` (both pass CPU bit-exactness tests); the CUDA sparse-FA path whitelists MLA head shapes (576/512) — i.e., DeepSeek-4/GLM-5-class DSA and MLA paths exist in-tree — [PR #27742](https://github.com/ggml-org/llama.cpp/pull/27742)
- Speculative decoding portfolio as of Oct 2026: draft-MTP, classic draft model, ngram/ngram-mod (usable on non-CUDA systems), DFlash2 (merged 2026-08-27; 1.77–1.85x on Apple M5 Pro); MTP+ngram combos documented as experimental — [PR #22673](https://github.com/ggml-org/llama.cpp/pull/22673), [PR #27342](https://github.com/ggml-org/llama.cpp/pull/27342)
- Server features relevant to your llama-swap setup seen in 2026 issue logs: prompt cache (PR #16391), context checkpoints, `--n-cpu-moe`, `--override-tensor per_layer_token_embd=CPU`, `--fit`/`--load-mode` (mmap/mlock/none), `-np` slot model, llama-swap itself cited in a bug report — [issue #27727](https://github.com/ggml-org/llama.cpp/issues/27727), [issue #30307](https://github.com/ggml-org/llama.cpp/issues/30307), [issue #30033](https://github.com/ggml-org/llama.cpp/issues/30033)
- KV cache types in routine use on Metal-adjacent stacks: `-ctk q8_0 -ctv q8_0` / f16; llama.cpp version stamps in reports: v0.6.0, builds b11400–b11548 — [issue #30307](https://github.com/ggml-org/llama.cpp/issues/30307), [issue #30033](https://github.com/ggml-org/llama.cpp/issues/30033)

### Inferences

- Your existing draft-MTP Qwen3.6-27B setup uses the exact merged PR #22673 path; pin llama-server at a v0.6.x tag rather than master until #30307-style regressions settle, and avoid combining MTP with vision input on affected builds.
- The qwen3next arch (your planned Qwen3-Coder-Next IQ4_XS/Q6_K sidecars) is the lowest-risk 2026 hybrid: 61GB Q6_K leaves ~55GB headroom on the raised limit, ~262K context costs only ~6GB KV f16, and none of its reported bugs involve Metal — but validate first-token coherence on Metal before trusting it (all filed bugs are ROCm/CUDA).
- The 51GB host-side per-layer embedding hash table of qwen4exp implies heavy host-memory pressure on macOS (it sits outside the wired GPU pool) — if you ever add Qwen3.8-Flash-Next, budget ~94GB (GPU) + ~55GB+ (host PLE table) against 128GB physical, which likely does not fit; treat that model as 256GB-machine class despite the 93.7GB GGUF.

### Gaps

- No Metal-specific bug reports for qwen3next/qwen4exp/glm-dsa architectures were found in this search — absence of Metal complaints is not confirmation of correctness; no Metal-backed benchmark for these archs was located either.
- No source found confirming whether llama.cpp Metal backend exploits M5 Neural Accelerators (Apple exposes them via Metal; MLX demonstrably benefits; llama.cpp gain unverified).
- llama.cpp release cadence/tag list for 2026 (v0.4→v0.6 observed in issue stamps) was not formally documented in the sources retrieved.
