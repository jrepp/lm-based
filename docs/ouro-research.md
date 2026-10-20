# Ouro research and inference options

Reviewed 2026-10-20. FlashLoop is the selected investigation; deployment is pending.
An [experimental MLX implementation](flashloop-mlx.md) now has synthetic Metal
tests, reference parity checks, and a completed local Ouro-2.6B-Thinking arithmetic
trajectory. A loopback HTTP prototype and runtime metrics have passed live checks;
llama-swap deployment and broader quality evaluation remain pending.
The other candidates below remain recorded for later evaluation.
See [the integration investigation](../docs-cms/memos/memo-002-flashloop-ouro-investigation.md)
for source inspection, limitations, and acceptance criteria.

## Selected: FlashLoop

[FlashLoop: Fast and Memory-Efficient Looped Transformers via Lazy Updates](https://arxiv.org/abs/2609.29812)
by Wanqi Yang and Shiwei Liu (September 2026; reviewed v2) accelerates existing
looped models without retraining. It combines selective token updates, sparse
attention, and quantized differences between successive loops' KV caches.
The authors report up to 1.64× end-to-end speedup and 6× KV-cache reduction
across their evaluated models. These are research results, not measurements on this host.

FlashLoop would replace part of the Ouro inference implementation, while retaining
Ouro weights. It is not a separate model checkpoint to substitute in llama-swap.

The [public implementation](https://github.com/Superone77/FlashLoop) has two paths:

| Path | Intended use | Local relevance |
|---|---|---|
| `flashloop` | Optimized CUDA engine with physically packed cache | Requires a CUDA host or a Metal implementation; not a supported direct Mac replacement |
| `flashloop_torch` | Algorithm reference using materialized, fake-quantized tensors | Potential quality experiment after compatibility checks; does not demonstrate physical cache savings |

Do not interpret theoretical packed-byte accounting from the reference as measured
resident memory. Likewise, a cache reduction does not reduce weight memory by the
same factor. Keep the current backend available as the comparison and fallback.

## Retained alternatives

These are not selected for implementation. Availability of a paper does not establish
that a compatible checkpoint or Apple Silicon runtime is available.

| Work | Improvement and evidence | Relevance and reason to retain |
|---|---|---|
| [HLA — Hybrid Latent Attention](https://arxiv.org/abs/2610.07940), October 2026 | Keeps exact recent KV and compact older states; reports 10.7× cache compression with over 97% of original benchmark accuracy | Strong memory candidate, but requires training additional parameters and compatible attention execution; not selected pending artifact/runtime verification |
| [MELT — Memory-Efficient Looped Transformer](https://arxiv.org/abs/2605.07721), May 2026, revised September | Distills Ouro into a model sharing a gated cache across loops | Addresses cache growth with reasoning depth; memory still grows with context. Requires post-training and a different runtime |
| [RLTT — Reward Latent Thought Trajectories](https://arxiv.org/abs/2602.10520), February 2026, revised May | Rewards intermediate latent computation as well as the final state; reports gains over GRPO on Ouro-1.4B/2.6B | Quality improvement rather than memory optimization. [Public code](https://github.com/jonwill8/RLTT) documents CUDA/Slurm training; compatible released weights remain to be checked |
| [LoopCD — Loop-wise Contrastive Decoding](https://arxiv.org/abs/2609.24196), September 2026 | Contrasts earlier and final-loop logits to improve reasoning without retraining | Potentially smaller decoding experiment; needs task-quality evaluation and access to intermediate logits |
| [Final-loop cache sharing](https://ouro-llm.github.io/#strategy), original Ouro study | One-quarter cache memory on Ouro-1.4B; reported MATH-500 changes from 82.4 to 80.4 | Useful simpler baseline for the memory/quality tradeoff; not yet validated on our 2.6B Thinking runtime |

## Evaluation policy

Use the same checkpoint, tokenizer, prompt set, loop count, and token budget when
comparing inference implementations. Record exact source revisions and distinguish
paper claims, calculated bounds, and host measurements.

For the local decision/review workload, measure task correctness, structured output
validity, tool-call validity, latency to first token, decode throughput, and actual peak
memory. Math benchmark gains alone do not establish a better PR reviewer.
Collect token counts from tokenizer/runtime data rather than model-written summaries.

The MLX FlashLoop prototype has run local Ouro-2.6B-Thinking weights on one
arithmetic smoke case; this is not a general quality or speed benchmark.
Other alternatives have not been loaded or evaluated here.
Ouro's llama-swap changes remain staged until workers are idle.

## Decode-speed follow-up (2026-10-20)

The current port still reconstructs dense KV histories and synchronizes many small
MLX operations. The following ranking is an implementation assessment for our
batch-one, four-loop, BF16 Ouro-2.6B-Thinking service; published speedups are not
predictions for this Mac. Preserve the four-loop baseline and its trajectory metrics
while removing implementation overhead first.

| Priority | Research / primary source | What to investigate here | Constraints |
| --- | --- | --- | --- |
| Immediate | [MLX lazy evaluation guidance](https://github.com/ml-explore/mlx/blob/main/docs/src/usage/lazy_evaluation.rst) | Batch validation/evaluation; avoid rebuilding exact KV tails between compression boundaries | An engineering optimization, not a new decoding algorithm; require identical caches and outputs |
| Next kernel experiment | [Open-TQ-Metal](https://arxiv.org/html/2604.16957v1), April 2026 | Fuse packed-cache decoding with attention; avoid writing a full dequantized history to memory | Authors report 48× attention-kernel improvement at 128K context, not 48× end-to-end decoding. Our contexts are much shorter. Cross-loop residuals and sparse key selections need a different kernel; the paper flags long-context quality gaps |
| Next algorithm experiment | [WaveFront Decoding](https://arxiv.org/abs/2609.23033v2), September 2026; [author code](https://github.com/summerbro-hhj/wavefront-decoding) | Batch shallow drafts and deeper verification using the same recurrent weights; potentially amortize weight reads across token positions | Authors report 2.42× on Ouro-2.6B across Spec-Bench tasks. Current code is CUDA-oriented. Needs mixed-position/depth attention, speculative cache rollback and acceptance metrics; compatibility with FlashLoop approximations is unproven |
| Weight-bandwidth experiment | [Loopy](https://arxiv.org/abs/2610.05265), October 2026 | Calibrate low-bit weights at the actual four-loop deployment depth | Quantization error recurs through the shared block. Paper's W4A4 quality result is not a turnkey MLX weight-only kernel or a measured Mac speedup; evaluate reasoning quality before adopting |
| Alternative cache/kernel | [When Quantization Is Free](https://arxiv.org/html/2605.05699v1), May 2026 | Fuse cache transformation, quantization and packing instead of many small kernels | Reported improvements are modest and model/context dependent: 3–8% ms/token on Gemma-3 1B and 0.7–2.6% on short Qwen2.5-1.5B contexts. Its representation differs from FlashLoop residuals; do not substitute it without quality checks |
| Later serving work | [Continuous Depth Batching](https://arxiv.org/abs/2608.09444), August 2026 | Schedule individual loop iterations and boundary stages across concurrent requests | Authors report 1.5–1.9× offline throughput and lower normalized latency. Our single-request service cannot directly realize those batching gains; needs adaptive-depth support and multiple active requests |
| Quality-changing experiment | [Enabling Dynamic Computation in Looped LMs](https://arxiv.org/abs/2610.09013), October 2026 | Best-available KV allows skipping deeper loops without leaving unusable cache holes | Reports up to 30% FLOP/cache reductions with retained benchmark performance. Changes depth/cache semantics; keep experimental and validate completed reasoning, not merely token agreement on a short prefix |

HLA and MELT remain retained above. HLA's direct latent-cache attention is attractive
for longer contexts, but requires trained additional parameters. None of these papers
establishes a ready replacement for our current checkpoint and Metal execution path.

Benchmark acceptance: use the same checkpoint, prompt IDs, decoding settings and
context positions; include cache flush boundaries; retain loop receipts and raw
per-step timings. Compare token IDs and cache bytes before reporting throughput.
Measure cold load, prefill, decode and end-to-end completion separately. Keep runtime
metrics enabled in service checks and do not infer speed from fewer reported loops.

### Local implementation follow-up

The MLX port now has a selected-row Metal cache reader for late loops. It decodes
only the keys chosen by FlashLoop's existing attention rule, preserving every loop
and the original storage-dtype rounding. In completed comparisons after redundant
backends were stopped, throughput improved by 34.7% pooled at a 198-token prompt
and 37.7% at a 726-token prompt, with identical tokens, loop receipts and cache bytes.
The host still had managed inference workers, so these are local comparative results,
not isolated capacity estimates. See [implementation results](flashloop-mlx.md#completed-comparison-after-backend-cleanup).

This implements fused gather/dequantization, not the full compressed-domain attention
in Open-TQ-Metal. Early-loop attention still reconstructs history. WaveFront,
weight quantization and adaptive depth remain separate research candidates; none of
their published gains is being attributed to this implementation.

### Additional research and execution experiments (2026-10-20)

[LoopQuant: Accurate and Efficient Post-Training Quantization for Looped Transformers](https://arxiv.org/abs/2610.16368)
(12 October 2026; [author code](https://github.com/Kishon-zzx/LoopQuant)) is retained
alongside Loopy. It canonicalizes distributions across loops, allocates activation
precision according to loop sensitivity and interactions, and calibrates the
quantized recurrent trajectory. Authors report 1.7× decoding speedup and 65.3%
lower model memory on Ouro-2.6B with W4A4. These are published results, not local
Metal measurements. It needs calibration and suitable low-bit execution kernels;
ordinary MLX weight-only quantization does not implement its activation scheme.
Evaluate reasoning and structured-output quality before adopting it. No checkpoint
has been converted or substituted.

Immediate implementation work targets execution overhead, following the official
[MLX compilation](https://ml-explore.github.io/mlx/build/html/usage/compile.html) and
[lazy evaluation](https://ml-explore.github.io/mlx/build/html/usage/lazy_evaluation.html)
guidance. The decoder currently evaluates every layer, or 192 layer boundaries per
token across four loops, in addition to receipt/cache work. Test bounded groups of
layers before evaluation and separately compile pure normalization and gated
activation functions. Keep all four loop receipts and observer callbacks. Compilation
can change floating-point rounding; token agreement alone is insufficient to claim
identical execution. Record peak allocator memory because larger lazy graphs retain
intermediates. Prefill remains separately measured, and its evaluation schedule is
unchanged. Grouped evaluation passed exact real-model trajectory comparisons and is now the
engine default; compilation remains opt-in because paired timing gains were not
consistent. See [execution results](flashloop-mlx.md#decode-evaluation-and-compilation-controls)
for raw artifact names, measurements and reproduction commands.

Priorities after this experiment remain full compressed-domain attention, then
WaveFront's mixed-depth drafting/verification and loop-aware weight quantization.
Retain HLA, MELT, adaptive depth and continuous-depth batching as alternatives with
their training/quality/concurrency requirements above. Do not multiply published
speedups: each method changes the bottleneck and none has demonstrated combined
performance with this particular MLX FlashLoop implementation.
