# llama-server Cache Architecture Explainer

Recorded: 2026-04-13

## Scope

This note explains how `llama-server` caching actually works for local serving, with emphasis on:

- slots
- prompt cache
- partial sequence removal
- cache reuse via KV shifting
- checkpoints
- parallel serving
- long-context performance
- what this means for `Qwen3-Coder-Next`
- what this means for OpenCode-style coding-agent workloads

The goal is to separate three ideas that often get mixed together:

1. the raw `llama_context`
2. server slot behavior
3. user-facing "cached tokens" and multi-turn reuse

## The Three Cache Layers

There are three distinct reuse layers in `llama-server`.

### 1. KV / sequence memory inside `llama_context`

This is the model-side memory backing already-processed tokens. At the libllama level, the context can be created with `n_ctx > n_ctx_train`; libllama warns but does not itself cap this:

- [llama-context.cpp](/Users/jrepp/d/llama.cpp/src/llama-context.cpp:199)
- [llama-context.cpp](/Users/jrepp/d/llama.cpp/src/llama-context.cpp:215)

For the captured `Qwen3-Coder-Next` run, the raw context was built at `1048576` tokens and used `freq_scale = 0.25`:

- [llama-server.log](/Users/jrepp/d/qwen/runs/20260413T144134Z-qwen3-coder-next-iq4xs/llama-server.log:171)

### 2. Per-slot prompt state in `server_slot`

`llama-server` does not serve directly from the raw context. It wraps work in `server_slot`, which holds:

- slot-local context size `n_ctx`
- task state
- prior prompt tokens
- cached-token counts
- generation state

See:

- [server-context.cpp](/Users/jrepp/d/llama.cpp/tools/server/server-context.cpp:50)

This slot object is the unit that drives request admission, truncation, reuse, and generation.

### 3. Optional host-side prompt cache snapshots

Idle slots can be saved to a host-side prompt cache and later restored. This is separate from the live KV memory currently active in the slot:

- [server-context.cpp](/Users/jrepp/d/llama.cpp/tools/server/server-context.cpp:105)
- [server-context.cpp](/Users/jrepp/d/llama.cpp/tools/server/server-context.cpp:608)

So when the server reports cached tokens, that may come from live slot reuse, shifted KV reuse, or restored prompt-cache state.

## Slots

Slots are the server's reusable execution containers.

Each slot carries its own:

- prompt history
- `n_ctx`
- cached-token count
- generated output state
- timing and release bookkeeping

See:

- [server-context.cpp](/Users/jrepp/d/llama.cpp/tools/server/server-context.cpp:66)
- [server-context.cpp](/Users/jrepp/d/llama.cpp/tools/server/server-context.cpp:70)
- [server-context.cpp](/Users/jrepp/d/llama.cpp/tools/server/server-context.cpp:76)

The important consequence is that server behavior is slot-centric, not just model-centric.

## Why Requested Context And Slot Context Differ

For `Qwen3-Coder-Next`, libllama accepted the 1M context request, but `llama-server` then capped slot context back to the model training window:

- raw context built at `1048576`: [llama-server.log](/Users/jrepp/d/qwen/runs/20260413T144134Z-qwen3-coder-next-iq4xs/llama-server.log:171)
- server warning about slot capping: [llama-server.log](/Users/jrepp/d/qwen/runs/20260413T144134Z-qwen3-coder-next-iq4xs/llama-server.log:206)
- slot created with `n_ctx = 262144`: [llama-server.log](/Users/jrepp/d/qwen/runs/20260413T144134Z-qwen3-coder-next-iq4xs/llama-server.log:209)

The exact server-side cap is here:

- [server-context.cpp](/Users/jrepp/d/llama.cpp/tools/server/server-context.cpp:760)

So:

- libllama says "possible, but overflow risk"
- `llama-server` says "do not expose that as slot capacity"

## Slot Selection

When a new request arrives, the server tries to pick an available slot.

It uses two strategies:

1. Longest Common Prefix similarity against idle slots
2. Least-recently-used fallback

See:

- [server-context.cpp](/Users/jrepp/d/llama.cpp/tools/server/server-context.cpp:962)
- [server-context.cpp](/Users/jrepp/d/llama.cpp/tools/server/server-context.cpp:1008)

The LCP similarity score is measured as:

- common-prefix tokens / new prompt length

The threshold is controlled by `slot_prompt_similarity`:

- [server-context.cpp](/Users/jrepp/d/llama.cpp/tools/server/server-context.cpp:967)

This works well when prompts grow append-only. It works badly when the prompt is semantically similar but token-structurally different.

## Multi-turn Slot Reuse

Multi-turn reuse is mostly prefix reuse.

If a slot already holds a prompt whose token prefix matches the new request, the server can skip reprocessing that shared prefix:

- [server-context.cpp](/Users/jrepp/d/llama.cpp/tools/server/server-context.cpp:2267)

The count of reused prompt tokens is stored in:

- `n_prompt_tokens_cache`

See:

- [server-context.cpp](/Users/jrepp/d/llama.cpp/tools/server/server-context.cpp:2462)

And this is surfaced back to clients as:

- `prompt_tokens_details.cached_tokens`
- `cache_read_input_tokens`

See:

- [server-task.cpp](/Users/jrepp/d/llama.cpp/tools/server/server-task.cpp:760)
- [server-task.cpp](/Users/jrepp/d/llama.cpp/tools/server/server-task.cpp:1158)

This is what makes an apparently giant request sometimes only evaluate a small delta.

Example from the local run:

- slot held `88,394` tokens
- timed prompt processing only covered `999` tokens

See:

- [qwen-run-stats.md](/Users/jrepp/d/qwen/qwen-run-stats.md:24)

## Prompt Cache

If the server is about to reuse or evict a slot, it can serialize that slot's prompt state to the host-side prompt cache:

- [server-context.cpp](/Users/jrepp/d/llama.cpp/tools/server/server-context.cpp:1040)

Idle slots can also be saved and cleared explicitly:

- [server-context.cpp](/Users/jrepp/d/llama.cpp/tools/server/server-context.cpp:608)

This is not the same thing as keeping live slot KV around. It is a snapshot/restore path.

The prompt cache helps when:

- a slot is idle
- its prompt is likely to be useful later
- you want to reclaim slot state without losing all reuse potential

It helps less when prompts mutate heavily and no longer share useful prefixes.

## Cache Reuse By KV Shifting

There is a more aggressive reuse path than plain prefix reuse: chunk-level reuse using KV shifting.

This is controlled by `n_cache_reuse` and only applies if:

- `llama_memory_can_shift()` is true
- the prompt is not multimodal

See:

- [server-context.cpp](/Users/jrepp/d/llama.cpp/tools/server/server-context.cpp:2277)

The server scans for matching chunks and, when it finds a big enough match, it physically shifts KV state from old positions to new positions:

- [server-context.cpp](/Users/jrepp/d/llama.cpp/tools/server/server-context.cpp:2311)
- [server-context.cpp](/Users/jrepp/d/llama.cpp/tools/server/server-context.cpp:2319)

This can be powerful, but it is fragile. Small edits near the front of the prompt can invalidate a lot of downstream reuse.

## Partial Sequence Removal

Many of the server's smarter behaviors depend on being able to remove or move only part of a sequence.

This shows up in three major places:

1. speculative compatibility checks
2. context shifting
3. prompt truncation / rollback

Speculative compatibility literally probes for support:

- [speculative.cpp](/Users/jrepp/d/llama.cpp/common/speculative.cpp:823)

Prompt suffix truncation uses partial sequence removal:

- [server-context.cpp](/Users/jrepp/d/llama.cpp/tools/server/server-context.cpp:2481)

Context shifting uses partial removal plus adding shifted spans:

- [server-context.cpp](/Users/jrepp/d/llama.cpp/tools/server/server-context.cpp:2040)

If partial removal is weak or unsupported for a given architecture/memory layout, many server features become less effective or get disabled.

## Context Shift

Context shift is the infinite-generation path that drops older prompt spans and shifts later spans left when a slot fills up.

See:

- [server-context.cpp](/Users/jrepp/d/llama.cpp/tools/server/server-context.cpp:2016)

It is disabled if the context cannot safely shift:

- [server-context.cpp](/Users/jrepp/d/llama.cpp/tools/server/server-context.cpp:735)

If context shift is disabled, generation simply stops when `slot.prompt.n_tokens() + 1 >= slot.n_ctx`:

- [server-context.cpp](/Users/jrepp/d/llama.cpp/tools/server/server-context.cpp:1280)

For `Qwen3-Coder-Next`, this matters because the architecture is hybrid/recurrent and the server is already conservative around memory mutation.

## Checkpoints

Checkpoints exist because exact rollback/reuse is not always possible for recurrent, hybrid, or SWA models.

The server only enables checkpoint creation when:

- task type is completion
- and the model is recurrent, hybrid, or uses SWA without `swa_full`

See:

- [server-context.cpp](/Users/jrepp/d/llama.cpp/tools/server/server-context.cpp:2509)

This is directly relevant for `Qwen3-Coder-Next`.

The checkpoint flow is:

1. create a partial-state snapshot during prompt processing
2. later, try to restore a useful checkpoint
3. if no suitable checkpoint exists, fall back to full prompt reprocessing

Creation path:

- [server-context.cpp](/Users/jrepp/d/llama.cpp/tools/server/server-context.cpp:2655)

Restore path:

- [server-context.cpp](/Users/jrepp/d/llama.cpp/tools/server/server-context.cpp:2416)

Full-reset fallback:

- [server-context.cpp](/Users/jrepp/d/llama.cpp/tools/server/server-context.cpp:2432)

This line is the most important one for understanding long-context pain on hybrid/recurrent models:

- "forcing full prompt re-processing due to lack of cache data"

That is not a rare corner case. It is a fundamental fallback path.

## Why `Qwen3-Coder-Next` Is Special

`Qwen3-Coder-Next` is not a simple dense full-attention model across all layers.

Local logs and llama.cpp model handling show:

- architecture tag `qwen3next`
- hybrid/recurrent-specific handling in server checkpoint code
- recurrent-state buffers in the run

Relevant log and code:

- [llama-server.log](/Users/jrepp/d/qwen/runs/20260413T144134Z-qwen3-coder-next-iq4xs/llama-server.log:16)
- [llama-server.log](/Users/jrepp/d/qwen/runs/20260413T144134Z-qwen3-coder-next-iq4xs/llama-server.log:194)
- [server-context.cpp](/Users/jrepp/d/llama.cpp/tools/server/server-context.cpp:2514)

This is why:

- checkpointing is unusually important
- partial sequence removal constraints matter more
- server conservatism around slot context is understandable

## Parallel Serving

Parallelism in `llama-server` is slot-based.

Each slot has its own effective context accounting and reuse lifecycle. With `parallel > 1`, the server can work on multiple requests, but it also increases:

- slot contention
- eviction pressure
- prompt-cache churn
- checkpoint churn
- ambiguity about which slot will best match the next request

For long coding conversations, `parallel = 1` is usually the cleanest configuration if you care about deterministic reuse rather than throughput under concurrent load.

## Long-context Performance

Long context does not just cost more memory. It weakens reuse quality and increases memory-management overhead.

From the local FAQ:

- early prompt throughput: about `1156 tok/s`
- later prompt throughput near `145k` tokens: about `43-78 tok/s`
- later decode throughput there: about `10-11 tok/s`

See:

- [llama-server-stats-faq.md](/Users/jrepp/d/qwen/llama-server-stats-faq.md:141)

The local run also showed heavy checkpoint churn:

- `230` checkpoint creates
- `196` checkpoint erases

See:

- [llama-server-stats-faq.md](/Users/jrepp/d/qwen/llama-server-stats-faq.md:62)

Interpretation:

- longer contexts increase matching and reconciliation work
- checkpoint restore helps, but does not make the delta free
- hybrid/recurrent memory makes rollback and reuse imperfect
- decode remains much slower than prompt ingest

This is why "1M context" is not automatically a win for agentic coding. If the prompt changes structurally every turn, large-context serving can still degenerate into expensive partial or full reprocessing.

## OpenCode-Specific Considerations

OpenCode-style coding agents are especially rough on this caching model.

Why:

- prompts are regenerated frequently
- tool outputs and diffs are inserted into the middle of the conversation state
- retries change instructions near the top
- compaction and summarization preserve meaning but often destroy literal token-prefix continuity

That means:

- LCP slot selection gets weaker
- chunk reuse via KV shifting gets less reliable
- prompt-cache restores become less likely to match well
- checkpoint fallback becomes more important

In practice, OpenCode-like workloads stress exactly the parts of `llama-server` that are hardest for hybrid/recurrent models:

- long prompts
- multi-turn reuse
- structural prompt mutation
- large tool outputs

This is why upstream Qwen3-Coder-Next server work has explicitly mentioned OpenCode friendliness.

## Practical Implications

For `Qwen3-Coder-Next` in `llama-server` today:

- default server behavior should respect the slot cap to `n_ctx_train`
- checkpoints are not optional background detail; they are a core recovery path
- `cache_reuse` is useful only when prompts preserve substantial literal structure
- `parallel = 1` is safer for long coding sessions
- very large contexts help only if the client preserves prefix stability

For coding-agent clients:

- prompt compaction strategy matters as much as model context size
- preserving long shared prefixes is valuable
- giant tool outputs are especially damaging if they force structural changes high in the prompt
- summaries that preserve intent but radically rewrite tokens can reduce practical reuse even while shrinking prompt length

## Bottom Line

The most important mental model is:

- libllama context size is not the same as server slot capacity
- cached tokens are not magic; they come from literal prompt overlap and memory operations that can fail or become invalid
- recurrent/hybrid architectures rely heavily on checkpoint fallback
- long-context serving quality depends as much on prompt stability as on raw `ctx-size`

For `Qwen3-Coder-Next`, `llama-server` currently behaves like a cautious serving layer on top of a more permissive runtime:

- runtime can build oversized context
- server slots remain conservative
- reuse is opportunistic
- checkpoints are the safety net

## References

Local source and notes:

- [server-context.cpp](/Users/jrepp/d/llama.cpp/tools/server/server-context.cpp:50)
- [server-task.cpp](/Users/jrepp/d/llama.cpp/tools/server/server-task.cpp:760)
- [speculative.cpp](/Users/jrepp/d/llama.cpp/common/speculative.cpp:823)
- [llama-context.cpp](/Users/jrepp/d/llama.cpp/src/llama-context.cpp:199)
- [llama-server-stats-faq.md](/Users/jrepp/d/qwen/llama-server-stats-faq.md:62)
- [qwen-run-stats.md](/Users/jrepp/d/qwen/qwen-run-stats.md:24)

External docs:

- Qwen llama.cpp guide: https://qwen.readthedocs.io/en/latest/run_locally/llama.cpp.html
- Qwen3-Coder-Next model card: https://huggingface.co/Qwen/Qwen3-Coder-Next
- Qwen3-Coder-Next GGUF card: https://huggingface.co/Qwen/Qwen3-Coder-Next-GGUF
- OpenCode docs: https://opencode.ai/docs/
