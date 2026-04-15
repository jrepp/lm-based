# Llama Server Stats FAQ

This FAQ explains the `llama-server` stats and memory numbers you will see in local runs.

## Where are the run artifacts?

For each captured run, the launcher writes a directory under `runs/`, for example:

- [runs/20260413T144134Z-qwen3-coder-next-iq4xs](/Users/jrepp/d/qwen/runs/20260413T144134Z-qwen3-coder-next-iq4xs:1)

Typical files:

- `llama-server.log`: raw server log with load, request, checkpoint, and timing lines
- `monitor.csv`: sampled process stats for the server PID
- `metadata.json`: exact launch args, PID, and run settings
- `summary.json`: parsed summary generated from the log and monitor data

## What do `prompt eval time`, `eval time`, and `total time` mean?

- `prompt eval time`: time spent ingesting prompt tokens into the model state
- `eval time`: time spent generating output tokens autoregressively
- `total time`: combined time for the request section reflected by that timing block

Interpretation:

- Prompt eval is usually much faster than decode when cache reuse is good.
- Decode speed is the more important steady-state throughput number for long completions.
- If `prompt eval` is unexpectedly large for a small delta, cache reuse or checkpoint restore likely did not help much for that request.

## What is a slot?

A slot is `llama-server`'s reusable request context container.

In our current runs:

- `parallel=1`, so there is one slot
- the server keeps reusing that slot across requests
- prompt cache and LCP similarity let the server reuse prior state instead of reprocessing the full conversation every time

Relevant lines:

- `selected slot by LCP similarity`
- `new prompt, n_ctx_slot = ...`
- `memory_seq_rm [...]`

## What are context checkpoints?

Checkpoints are serialized snapshots of a slot's prompt state so the server can restore a useful prior state without replaying the entire prompt from zero.

Relevant lines:

- `created context checkpoint ...`
- `restored context checkpoint ...`
- `erasing old context checkpoint ...`

Why they matter:

- They reduce prompt reprocessing when requests share a long common prefix.
- They consume RAM for the checkpoint store.
- High churn means the server is frequently dropping older checkpoints to make room for newer ones.

In the current `Qwen3-Coder-Next` run:

- checkpoint size is about `75.376 MiB` each
- the run summary counted `230` creates and `196` erases
- that is good evidence that checkpointing is active and heavily used

## Why is the slot context only `262144` when we requested `1048576`?

Because the server accepted the requested top-level context but capped the slot context to the model's training context.

We see both in the log:

- requested context at load: `n_ctx = 1048576`
- warning: `the slot context (1048576) exceeds the training context of the model (262144) - capping`
- effective slot context during requests: `n_ctx_slot = 262144`

Interpretation:

- The model and runtime can load under the 1M configuration.
- The server does not actually let this model serve a 1M slot in the current code path.
- This is currently a runtime behavior issue, not a raw memory-fit issue.

## Why is RSS around 49 GiB but VSZ around 475 GiB?

Because RSS and VSZ measure very different things.

- `RSS`: resident set size, the memory pages currently resident in RAM
- `VSZ`: virtual size, total address space mapped or reserved by the process

Why VSZ gets huge in `llama-server`:

- large `mmap` regions for model weights
- large reserved virtual address ranges for Metal/unified-memory buffers
- mapped files and allocator reservations that are not fully resident
- virtual ranges associated with KV, compute buffers, and supporting allocations

So a huge VSZ does **not** mean the process is actively consuming that much physical memory.

In the current run:

- peak RSS: about `49.147 GiB`
- peak VSZ: about `474.646 GiB`

That combination is plausible for a large mapped GGUF plus Metal and unified-memory reservations on macOS.

## How is memory being allocated in this run?

From the load log:

- model weights on Metal mapped buffer: about `40693.42 MiB`
- CPU mapped model buffer: about `166.92 MiB`
- KV buffer on Metal: `6912.00 MiB`
- recurrent state buffer on Metal: `75.38 MiB`
- compute buffers:
  - Metal: `1542.87 MiB`
  - CPU: `1028.27 MiB`

Interpretation:

- Most of the actual model is mapped onto the GPU device path through Metal.
- The KV cache is quantized (`q4_0/q4_0`), which keeps the 1M-request experiment memory-feasible.
- CPU memory is still used for auxiliary compute buffers and mapped file support.

## Why is the KV buffer "only" 6.9 GiB for a 1M request?

Because this architecture is not a standard full-attention dense model across every layer, and the KV cache is quantized.

The log shows:

- `1048576 cells`
- `12 layers`
- `K (q4_0): 3456.00 MiB`
- `V (q4_0): 3456.00 MiB`

That means:

- the effective attention/KV-bearing part of the architecture is smaller than "all 48 layers full attention"
- quantized KV dramatically reduces resident KV size versus `f16`

## Why do prompt speeds drop as the run gets longer?

Because long-context reuse is imperfect even with checkpoints.

As prompt length grows:

- more tokens need to be reconciled against the prior slot state
- checkpoint restore may help, but not enough to make the delta tiny
- memory movement and scheduling overhead increase
- decode speed may also degrade under larger active states

That is visible in this run:

- early best prompt throughput: `1156.08 tok/s`
- later prompt throughput near `145k` tokens: around `43-78 tok/s`
- later decode throughput near that scale: around `10-11 tok/s`

## What does `memory_seq_rm [x, end)` mean?

It indicates the server is trimming or invalidating the suffix of the remembered sequence state from token `x` onward before processing the new request.

This usually happens when:

- a new request diverges from the previously stored prompt tail
- the server wants to preserve the common prefix and discard the changed suffix

It is normal in reused-slot serving.

## What does `selected slot by LCP similarity` mean?

`LCP` is longest common prefix similarity between the incoming prompt and the slot's existing prompt state.

If similarity is high:

- the server prefers reusing that slot
- it can often reuse much of the existing prompt state
- checkpoint restore becomes more effective

In our single-slot setup, this is one of the main reuse signals.

## How should we read the current run at a high level?

The current `Qwen3-Coder-Next-IQ4_XS` run shows:

- load succeeded on Metal
- memory fit is acceptable on this machine
- prompt caching and checkpoint restore are working
- the requested `1M` context did **not** become an effective `1M` slot
- long-prompt performance degrades materially as active context grows

So the next optimization target is not basic loading. It is:

- understanding why slot context is capped to `262144`
- reducing checkpoint churn and prompt replay costs
- improving decode speed under very long active prompts
