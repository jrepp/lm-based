# FlashLoop MLX implementation

Status: experimental generation, trajectory validation, and HTTP metrics, 2026-10-20.
This batch-one correctness engine has a standalone loopback service. It is not yet
registered with llama-swap or the fleet dashboard.

Code lives in [experimental/flashloop_mlx](../experimental/flashloop_mlx/).
It adapts the [upstream implementation](https://github.com/Superone77/FlashLoop/tree/aeaadee10d75b7aa8c4a42a809f15c75d6d3bdc6)
at the pinned revision recorded in the research investigation. The upstream MIT
notice is retained alongside the implementation.

## Implemented

- Physically packed uint8 payloads containing two 4-bit codes per byte, with
  float16 affine metadata. Keys group over tokens; values group over channels.
- An unquantized recent-token tail, preserving complete token groups in the
  compressed prefix. With the defaults the tail contains 64–127 tokens once
  the context is long enough to compress.
- A first-loop anchor and residuals against reconstructed preceding-loop KV.
  Exact per-loop tails avoid accumulating quantization error on recent tokens.
- Single-token decode attention using bounded token tiles and online softmax.
  MLX evaluates each accumulator update to bound the lazy computation graph.
  It does not allocate a full-context dense KV or attention matrix during reads.
- Float16, BF16, and float32 input support; invalid shapes, nonfinite values,
  and unrepresentable float16 metadata are rejected.
- Immutable incremental append, preserving existing packed bytes and flushing
  complete groups from the exact tail. Tests compare boundary crossings against
  complete rebuilds, including multi-token appends.
- Ouro's four shared-layer loops, sandwich normalization, rotary positions, and
  greedy generation from local safetensors.
- Sparse late-loop prefill (25% then 10% of prompt rows, nested selection with the
  last token retained) and decode corrections using loop-2 selected probability
  mass. Receipts count the active projection and MLP rows.

The cache baseline stores residuals for every row in later loops, even though
prefill computes only the selected rows. It does not yet store compact sparse
overrides or their logical-position maps; this differs from the optimized upstream
cache representation. The generation adapter reconstructs one layer's history for early-loop attention;
late loops use selected-row Metal reads on GPU. The standalone bounded-tile attention
reader is tested but is not yet integrated into that adapter.
Construction currently takes dense prefill snapshots, so construction peak memory
can exceed the final compressed cache footprint.

## Reproduce the checks

Run from the repository root:

```bash
just flashloop-mlx-test
just flashloop-mlx-smoke
just flashloop-mlx-parity /path/to/reviewed/FlashLoop
just flashloop-mlx-engine-parity /path/to/local/Ouro /path/to/reviewed/FlashLoop
just flashloop-mlx-engine-parity /path/to/local/Ouro /path/to/reviewed/FlashLoop cpu
```

The parity command requires an existing checkout at
`aeaadee10d75b7aa8c4a42a809f15c75d6d3bdc6`; it checks the revision and loads the
committed codec source rather than a potentially modified working copy.
Dependencies run in isolated uv environments: Python 3.11, MLX 0.32.4,
NumPy 2.4.4 for tests, and Torch 2.8.0 for upstream parity only.
No serving environment is changed.

After reviewing memory headroom, run bounded generation and an independent offline
audit. These commands do not reload llama-swap:

```bash
just flashloop-mlx-thinking /path/to/local/Ouro artifacts/flashloop-mlx/flash.json
just flashloop-mlx-thinking /path/to/local/Ouro artifacts/flashloop-mlx/dense.json dense
just flashloop-mlx-audit artifacts/flashloop-mlx/flash.json
just flashloop-mlx-plot artifacts/flashloop-mlx/flash.json artifacts/flashloop-mlx/trajectory.png
```

The generation check uses one fixed arithmetic problem, local tokenizer files,
and a 1,024-token output ceiling. The receipt includes source/checkpoint SHA-256,
token IDs, visible thinking, timing, cache size, MLX peak allocation, and per-loop
hidden-state change and entropy. Loop metrics describe execution, not semantic
correctness or faithful reasoning. The offline audit verifies emitted tokens
against loop-4 choices and independently checks the expected answer.

Observed on Apple Metal:

| Check | Result |
|---|---|
| Local correctness suite | Twelve tests pass, including append and trajectory checks |
| Upstream codec comparison | Twelve cases pass, including exact payload and metadata comparisons |
| Synthetic cache | Four loops, one batch, two heads, 512 tokens, 128 channels |
| Dense BF16 KV arrays | 2,097,152 bytes |
| Compressed stored arrays, including metadata and tails | 778,240 bytes (37.1% of dense) |
| MLX active allocation above baseline after releasing inputs | 843,784 bytes |
| Tiled attention | Finite output; tests match independent dense softmax over reconstructed KV |

Allocator measurements are from one small synthetic run and include allocation
overhead. Stored-array byte counts are not process RSS or whole-model memory.
This is not a speed benchmark or a task-quality evaluation. Tests compare attention
against the quantized reconstruction, not against an assertion of lossless original
model output.

## Full-checkpoint thinking validation

On 2026-10-20 the prototype completed a local `Ouro-2.6B-Thinking` run:
198 prompt tokens and 347 generated tokens, with all 1,388 loop receipts present.
It computed `19 × 23 = 437`, subtracted 58, closed its thinking block, emitted
`Answer: 379`, and stopped on the end token. No forced thinking termination or
answer injection was used.

The independent audit passed all checks: token/loop alignment, positions, phase
order, projection counts, sparse execution, finite metrics, packed-cache use,
completion, answer correctness, and unchanged source during the run.
Prefill processed 198, 198, 50, and 20 rows across the four loops.

| Measurement | FlashLoop MLX |
|---|---|
| Prefill | 1.321 seconds |
| Median decode time per token | 0.539 seconds |
| Total measured run, including model load | 221.76 seconds |
| Final stored cache | 349,175,808 bytes (333 MiB) |
| Dense BF16 cache calculated at the same 544-token context | 855,638,016 bytes (816 MiB) |
| Final cache as fraction of equivalent dense storage | 40.8% |
| MLX peak allocated memory, including weights | 6,037,615,220 bytes (5.62 GiB) |

These are one-run observations on a shared laptop. The prototype is not a
performance-optimized implementation. The standalone cache savings do not imply
the same reduction in total model memory. Neither an arithmetic success nor the
plotted entropy establishes that visible thinking faithfully explains the model's
internal decisions.

The first FlashLoop run was correctly rejected at a 192-token limit, and an initial
dense run was rejected at 384 tokens: both contained unfinished thinking. Those
failed receipts remain available alongside the completed run.

Machine-local evidence (under gitignored `artifacts/flashloop-mlx/`):

- `2026-10-20-flash-1024.json`: full prompt, token IDs, thinking, source hashes,
  checkpoint identity, timing, and loop receipts.
- `2026-10-20-flash-audit.json`: independent audit summary.
- `2026-10-20-flash-trajectory.png`: exported entropy, hidden-change, and timing plots.
- `parity-cpu.log`: small-model reference comparison, maximum error below 0.0000002.

Completed FlashLoop receipt SHA-256:
`83586f045a67550777903e19b2c27f57344eec08f089470ad26c700229a819e3`.
Checkpoint SHA-256:
`c506a79247dc51fc0400d789365c3d43932f718abce9810f3606ace47d0a3080`.

The dense comparison also completed with `Answer: 379` and a closed thinking
block, using 549 output tokens. Its prompt token IDs, checkpoint SHA-256, and
implementation source hashes match the completed FlashLoop run. The different
completion lengths are observed outcomes, not evidence of a general reasoning
improvement.

| Observed measurement | FlashLoop | Dense |
|---|---|---|
| Generated tokens, including end token | 347 | 549 |
| Median decode seconds/token | 0.539 | 0.300 |
| Total measured seconds | 221.76 | 196.45 |
| MLX peak allocated bytes | 6,037,615,220 | 6,539,133,098 |
| Final cache bytes (different context lengths) | 349,175,808 | 1,173,356,544 |

FlashLoop is slower in this prototype despite its shorter completion. The
same-context cache comparison above is the appropriate storage comparison;
comparing final cache sizes directly would conflate compression with output length.
Dense-only runs bypass checks specific to sparse execution and packed storage.
The dense evidence is saved as `2026-10-20-dense-1024.json` and
`2026-10-20-dense-audit.json` in the same artifact directory.

## Next implementation milestones

1. Add compact sparse late-loop overrides with logical token/group positions.
2. Integrate the bounded-tile reader into generation and avoid reconstructing full
   layer history during decode.
3. Expand real-model quality evaluation beyond the fixed arithmetic smoke case.
4. Profile the reader. Add fused Metal readers where measurements justify it;
   the current implementation uses MLX operations, not custom fused Metal kernels.
5. Add the serving contract: aliases, token usage, sampling, streaming, stop
   sequences, cancellation, and per-request isolation.
6. Consider enabling an experimental backend after evaluation. Keep the original
   backend as a fallback.

The current code intentionally has no deployment switch and cannot replace the
staged Ouro server.

## Reference parity and an upstream issue

The parity harness constructs a tiny random model from the local Ouro configuration
and code without loading the full checkpoint. It compares dense prefill plus three
decode steps to original Ouro, then sparse prefill plus three decode steps to the
pinned FlashLoop engine.

The upstream `consume_inputs=True` sparse path aliases and mutates the previous
hidden state. That state is subsequently used to score loop-4 changes, producing
zero differences. The comparison harness explicitly clones the sparse input to
preserve the intended scoring state. This is parity against an adjusted reference;
it is not claimed to match that upstream defect.

On CPU, checks use absolute tolerance 0.00002. On Metal the largest observed logit
error was 0.0013322 across the eight comparisons. Metal checks require maximum
absolute error within 0.003 (plus relative tolerance 0.0003), relative RMS error
below 0.5%, and identical greedy choices. The short parity prompt has no compressed
prefix; codec and incremental-cache tests separately validate quantized storage.

## Related research

See [Ouro research and alternatives](ouro-research.md) and
[the integration investigation](../docs-cms/memos/memo-002-flashloop-ouro-investigation.md).

## HTTP service and metrics

```bash
just flashloop-mlx-service-test
just flashloop-mlx-serve /path/to/local/Ouro 19095
curl -s http://127.0.0.1:19095/health
curl -s http://127.0.0.1:19095/metrics
curl -s http://127.0.0.1:19095/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"ouro-2.6b-thinking-mlx-flashloop","messages":[{"role":"user","content":"What is 2 + 2?"}],"max_tokens":4}'
```

The service binds only to loopback. Health checks and scrapes do not load weights;
the first completion loads local weights onto a dedicated MLX thread. Weights stay
resident afterward. Generation is greedy, non-streaming, with one request at a time,
a 3,072-token prompt-plus-output limit, and at most 1,024 output tokens. Unsupported
sampling, streaming, tools, and extra request fields are rejected. A second concurrent
request receives 503. Disconnects request cancellation between model steps; the slot
remains occupied until the worker exits. HTTP metrics remain accessible during loading
and generation. This launcher does not modify the live serving configuration.

Metrics come from tokenizer IDs, timed runtime operations, actual loop receipts, and
MLX allocations—not generated text claiming usage. Counters accumulate across requests
until the process restarts. Prometheus histograms retain bucket counts, sums, and counts
for external rolling-window queries; these are not rolling averages inside the service.

| Metric prefix (`flashloop_`) | Meaning |
| --- | --- |
| `prompt_tokens_total`, `generated_tokens_total` | Exact successfully prefilled input and selected output IDs; output includes end tokens |
| `request_seconds`, `time_to_first_token_seconds` | Admission to completion / first selected token, including cold loading; not network delivery latency |
| `load_seconds`, `prefill_seconds`, `decode_seconds` | Completed weight load, prompt prefill, and individual decode timings |
| `generation_requests_total` | Finished attempts by success, error, cancelled, or rejected context |
| `requests_active`, `model_loaded`, `model_loads_total` | Admission and weight-loading state |
| `loop_passes_total`, `qkv_rows_total`, `mlp_rows_total` | Actual completed loop work by prefill/decode phase and loop 1–4 |
| `next_token_entropy_nats`, `hidden_delta_rms` | Histograms of loop trajectory measurements |
| `cache_bytes`, `context_tokens` | Current request cache footprint and cached positions; zero when idle |
| `last_request_cache_bytes` | Most recent observed cache footprint retained when idle |
| `mlx_active_bytes`, `mlx_peak_bytes` | Last sampled MLX allocation and process peak, including weights |
| `last_progress_timestamp_seconds` | Time of the last completed latent loop |
| `http_requests_total` | Response counts using normalized routes and bounded method/status labels |

No prompt text, token IDs, request IDs, filesystem paths, or raw unmatched URLs become
metric labels. `/slots` and `llamacpp:` counter aliases provide the existing
serve-manager poller's input format while `flashloop_backend_info` identifies the
actual backend as MLX. Dashboard registration remains a separate integration step.

Validation on 2026-10-20: five HTTP lifecycle tests cover cumulative counters, exact
response usage, compatibility aliases, concurrent scrapes, busy admission, invalid
requests, errors, cancellation, and registry isolation. Two real four-token requests
each consumed 30 prompt tokens. Counters reached 60 prompt / 8 output tokens with
one weight load; the first request recorded four prefill and twelve decode loop
passes, a last cache footprint of 51,904,512 bytes, and zero active/cache gauges after
completion. This short smoke test validates instrumentation, not reasoning quality.
The temporary test service was stopped afterward.

## Decode optimization and extended service checks

The exact-tail append fast path reuses immutable packed history until the next
complete compression group is ready. It concatenates absolute per-loop tails and
batches finite-value validation into one device evaluation per layer. Group flushes
retain the original quantization path; invalid input still fails atomically.

On 2026-10-20, two 64-step runs before and after this change used the same 198-token
prompt and checkpoint, crossing the 256-position compression boundary. All output
token IDs, loop receipts (including entropy and hidden deltas), and final cache bytes
matched exactly. These are short local comparisons with variable host load, not a
controlled general performance claim.

| Repeat | Before tokens/sec | After tokens/sec | Speedup | Time in cache append, before → after |
| --- | --- | --- | --- | --- |
| 1 | 1.77 | 3.51 | 1.98× | 62.5% → 15.0% |
| 2 | 1.33 | 2.66 | 2.01× | 60.9% → 15.7% |

The benchmark measures each complete decode step with loop receipts enabled. Its
append timer wraps cache appending, including validation and device evaluation.
Raw per-token timings and source hashes are retained in
`artifacts/flashloop-mlx/append-baseline.json` and `append-optimized.json`.

```bash
just flashloop-mlx-benchmark /path/to/local/Ouro artifacts/flashloop-mlx/new-benchmark.json
just flashloop-mlx-service-test
just flashloop-mlx-dashboard-test
# In a separate terminal, launch a fresh service before the opt-in real-model test:
just flashloop-mlx-serve /path/to/local/Ouro 19095
# Run while that otherwise idle test service is listening:
just flashloop-mlx-service-smoke artifacts/flashloop-mlx/new-service-smoke.json
```

The real socket smoke test found that Starlette's function-style HTTP middleware
prevented our disconnect polling from observing a closed client connection. The
metrics wrapper now passes ASGI receive events through unchanged. An event-level
regression test and a real TCP-close test cover the fix. Worker cancellation remains
cooperative between model steps; the slot is held until the worker actually exits.

After the fix, the real smoke test passed context rejection before weight loading,
503 while busy, exact token accounting, network disconnect cancellation, and a
successful request after cancellation. Twenty-two scrapes during generation had a
maximum latency of 4.3 ms. Captured Prometheus aliases and slot JSON feed the Go
poller regression test without depending on a live service. The smoke artifacts are
`artifacts/flashloop-mlx/optimized-service-smoke.{json,prom,slots.json}`.

See [the decode research follow-up](ouro-research.md#decode-speed-follow-up-2026-10-20)
for fused Metal attention, WaveFront speculation, recurrent-depth-aware weight
quantization, and other retained candidates. None of their published speedups is
included in the local measurements above.

The complete optimized thinking run also passed all trajectory checks: 347 output
tokens and 1,388 loop receipts matched the earlier full FlashLoop baseline exactly,
with the same checkpoint hash and 349,175,808-byte final cache. It ended with
`Answer: 379`. Median decode latency was 0.2546 seconds/token (earlier baseline
0.5394), mean decode throughput 3.477 tokens/sec, and total recorded elapsed time
100.87 seconds. The earlier and new full runs were not interleaved, so use the paired
short comparisons above alongside these timings. Receipt:
`artifacts/flashloop-mlx/2026-10-20-optimized-thinking.json`, SHA-256
`5d72fe1599f01c4caec0fc6a373de5ea2208e7f93ce52848d626d30dafaaad45`.

## Selected-row Metal cache reader

`selected_kv.py` implements a fused gather/dequantization kernel for late-loop
attention. For each selected position it reads packed 4-bit payloads and float16
metadata, reconstructs the anchor plus residuals, or reads the exact tail/current
KV directly. It preserves the storage-dtype rounding after each residual addition.
Only selected rows are written to output; it does not construct a dense history.
Attention and its correction formula remain unchanged. This is a fused cache reader,
not yet fused compressed-domain attention.

The kernel handles per-head selections, batch dimensions, odd channel widths,
compression-group boundaries, and empty/uncompressed tails. Invalid indices produce
NaN rather than reading out of bounds. Tests compare gathered values exactly with
full reconstruction followed by gather, for float32, float16 and BF16 at every loop.
The engine's `selected_reads` switch retains the full-history comparison path.

The implementation uses [MLX custom Metal kernels](https://ml-explore.github.io/mlx/build/html/dev/custom_metal_kernels.html).
Kernel objects are cached; context lengths are read from input shapes so growing
the cache does not create a new source specialization for each token. Current code
uses MLX's contiguous-input handling rather than assuming arbitrary strides.

```bash
# Two comparisons with reversed order: full, selected, selected, full.
just flashloop-mlx-selected-benchmark /path/to/local/Ouro artifacts/flashloop-mlx/selected-short.json
# Repeat the prompt four times to test a longer history.
just flashloop-mlx-selected-benchmark /path/to/local/Ouro artifacts/flashloop-mlx/selected-long.json 4
```

These comparisons assert identical emitted token IDs, every loop receipt, and cache
bytes across all runs. The fixed number of decode steps includes cache flush work.
Kernel compilation on first use is included; results therefore do not hide its cost.

The first real selected-reader comparison was interrupted during its fourth run
when the user requested inference-backend cleanup. Three completed runs reported
0.893 tokens/sec (full history), 0.709 and 0.575 (selected reads), amid substantial
host paging. The comparison did not complete its cross-run assertions or write a
final receipt; these partial observations are not a validated speedup. At that point selected
reads remained disabled by default. Four redundant/old serving processes and the
benchmark were stopped; the active managed Qwen reviewer was retained. Rerun the
interleaved benchmark under stable load before considering default enablement.

### Completed comparison after backend cleanup

The replacement short-context run completed all four passes in full/selected/
selected/full order, using 198 prompt tokens and 64 decode steps each. Exact output
IDs, all loop receipts, and final cache bytes matched. Full-history reads delivered
1.107 and 1.196 tokens/sec; selected reads delivered 1.524 and 1.575 tokens/sec.
The paired improvements were 37.6% and 31.7%; pooled throughput was 1.150 versus
1.549 tokens/sec (34.7% higher). These are shared-host measurements with the managed
Qwen worker retained, not isolated maximum-throughput numbers. Raw receipt:
`artifacts/flashloop-mlx/selected-reads-clean-short.json`.

The benchmark now saves each completed pass with `status: incomplete`, then records
`passed` or `failed` after source and comparison checks. An interrupted measurement
therefore retains useful data without appearing to be a completed validation.

The longer comparison used 726 prompt tokens and 64 decode steps, crossing another
compression boundary. Full-history reads delivered 0.793 tokens/sec versus 1.093
with selected reads (37.7% higher). All exact comparisons passed. Receipt:
`artifacts/flashloop-mlx/selected-reads-clean-long.json`.

Selected reads are now enabled by default for FlashLoop on Metal. CPU execution
retains full-history reads, and `OuroEngine(..., selected_reads=False)` explicitly
selects the old path. The same default applies to the experimental HTTP runtime.
Sixteen cache/trajectory tests and CPU/Metal reference-engine checks passed after
enablement. Source hashing in full-generation receipts includes `selected_kv.py`.

An isolated reader microbenchmark, with weights absent and 20 samples per path,
measured the following medians. These are kernel-path measurements, **not** model
throughput improvements; use the complete decode comparisons above for token rate.

| Cached positions | Full reconstruction + gather | Selected Metal read | Reader speedup |
| --- | --- | --- | --- |
| 198 | 1.865 ms | 0.252 ms | 7.39× |
| 1,024 | 4.689 ms | 0.230 ms | 20.36× |
| 3,072 | 12.411 ms | 0.265 ms | 46.87× |

All reader outputs matched exactly. Raw samples:
`artifacts/flashloop-mlx/selected-reader-microbench.jsonl`.
Reproduce with `just flashloop-mlx-selected-microbench`.

The service smoke harness also supports a prompt long enough to exercise packed KV
history, with exact per-loop prefill/decode counter checks:

```bash
just flashloop-mlx-service-packed-smoke artifacts/flashloop-mlx/packed-service-smoke.json
```

The full selected-reader thinking run passed all checks and the independent audit.
Its 347 output tokens, 1,388 loop receipts, checkpoint hash, and final cache bytes
matched the prior complete append-optimized run exactly. It ended with `Answer: 379`.
Receipt: `artifacts/flashloop-mlx/2026-10-20-selected-thinking.json`, SHA-256
`22eb444fdbd5ba0df402437989ee93c1d1a2f7d3558f115159e94b91b8a6be27`.
Host load changed during this validation, so its elapsed time is not used for the
speedup claim; that comes from the paired comparisons above.

The live packed-cache service smoke test also passed: 222 prompt tokens and eight
output tokens matched the exact usage counters and all four loops' prefill/decode
counts. Context rejection, busy admission, TCP disconnect cancellation, and successful
recovery passed. Across 101 scrapes during generation, the maximum scrape latency
was 29.2 ms. Receipt: `artifacts/flashloop-mlx/selected-service-packed-smoke.json`.
The temporary test service was stopped after validation; no extra inference backend
was left running.

### Decode evaluation and compilation controls

`OuroEngine(..., eval_every=8)` bounds lazy decode graphs by evaluating every eight
layers instead of every layer. Loop-end receipt evaluation still completes trailing
layers, including when the interval exceeds a tiny test model's depth. Prefill keeps
its existing evaluation schedule. All loop metrics and observer calls remain enabled.
`compiled_ops=True` separately enables compilation of pure normalization and SwiGLU
activation operations; weights and epsilon are explicit arguments, not captured
mutable engine state. Matrix projections and cache updates are unchanged.

Compare schedules with selected Metal reads enabled in both variants:

```bash
just flashloop-mlx-execution-benchmark "$OURO_MODEL" artifacts/flashloop-mlx/execution-group8.json 8 64 2
just flashloop-mlx-execution-benchmark "$OURO_MODEL" artifacts/flashloop-mlx/execution-compiled.json 8 64 2 --compiled-ops --baseline-eval-every 8
just flashloop-mlx-engine-parity "$OURO_MODEL" "$FLASHLOOP_CHECKOUT" metal --eval-every 8 --compiled-ops
just flashloop-mlx-thinking "$OURO_MODEL" artifacts/flashloop-mlx/group8-thinking.json flash --eval-every 8
```

Comparisons alternate baseline/candidate/candidate/baseline, record raw timings,
prefill time and peak MLX allocator bytes, and require identical token IDs, loop
receipts and cache-byte totals. Peak allocator bytes are not whole-host resident
memory. Compilation may alter rounding; a failure of exact receipt comparison must
remain visible even if greedy outputs agree. Small execution tests additionally
compare logits and reconstructed caches through a compression boundary, with
observer callbacks enabled, in dense and FlashLoop modes.

The first completed evaluation-schedule comparison (`execution-group8.json`) used
198 prompt tokens and 64 decode steps per pass. Per-layer evaluation measured
1.737 and 1.568 tokens/sec; groups of eight measured 4.759 and 6.159 tokens/sec.
Pooled throughput was 1.648 versus 5.369 tokens/sec (3.26×). Tokens, every loop
receipt, and final cache bytes matched exactly. Peak MLX allocator usage was about
5.44 GiB for both schedules (maximum difference 192 KiB). The shared host remained
active, and the first baseline overlapped briefly with a tiny reference check;
the reverse-order baseline also remained slower. These results establish a local
comparison, not a guaranteed rate under other workloads. No loop computation or
telemetry was removed.

Compilation was compared separately with both variants using groups of eight
(`execution-compiled8.json`). All exact comparisons passed. Uncompiled runs measured
1.439 and 1.404 tokens/sec; compiled runs measured 1.725 and 1.322 tokens/sec.
The forward pair improved but the reverse pair regressed, so compilation remains
opt-in; this does not establish a repeatable throughput benefit. Compilation also
adds initial specialization overhead. Small execution tests cover both FP32 and
BF16 weights; the compiled Metal path passed the pinned reference comparison.

The experimental engine and HTTP runtime now default to `eval_every=8`, with
`eval_every=1` retaining the previous schedule. Compilation remains disabled by
default. This changes GPU evaluation boundaries, not recurrent depth or metrics.

Completed default-schedule validation: `execution-group8-thinking.json` passed the
independent trajectory audit and ended with `Answer: 379`. All 347 output tokens,
1,388 loop receipts, prompt IDs, checkpoint hash and final cache bytes matched
`2026-10-20-selected-thinking.json` exactly. Receipt SHA-256:
`5ae9f209fa4b3d9dd8eb475b4f02eece73cd5acf98c9d17f985444a13943e78d`.
This is one arithmetic case, not a general reasoning-quality evaluation.

The live packed-cache HTTP check (`execution-group8-service.json`) passed with
222 prompt tokens and eight output tokens, exact runtime usage and loop counters,
busy admission, context rejection, disconnect cancellation and recovery. Forty-five
metrics scrapes completed during generation; the maximum latency was 49.2 ms.
Seventeen engine/cache/trajectory tests and six HTTP lifecycle tests passed. The
temporary service was stopped after testing; no additional inference backend was
left running and no llama-swap reload was performed.

### Dense Ouro comparison caveat

The earlier complete dense Ouro run averaged 2.805 decode tokens/sec; the latest
grouped-evaluation FlashLoop completion averaged 1.880. The latter's short paired
benchmark averaged 5.369 tokens/sec. These runs had different host load and output
lengths. The 3.26× result above compares two FlashLoop execution schedules, not
FlashLoop against dense Ouro. A fresh interleaved dense-versus-FlashLoop comparison
is required before claiming a speedup over Ouro.
