# Recent Qwen Run Stats

Recorded: 2026-04-13

## Summary

- Request id: `task 9871`
- Slot id: `0`
- Prompt tokens loaded into slot: `88,394`
- Prior context checkpoint erased at position: `58,882`
- Final checkpoint created: `32 of 32` at position `88,389`
- Checkpoint size: `62.813 MiB`
- Generated tokens in timed decode section: `1,319`
- Timed prompt tokens: `999`
- Timed total tokens: `2,318`
- Prompt throughput: `177.32 tok/s`
- Decode throughput: `18.70 tok/s`
- Prompt latency: `5.64 ms/token`
- Decode latency: `53.48 ms/token`
- End-to-end timed request duration: `76,167.86 ms`
- Reasoning budget: activated with `2147483647` token budget, then deactivated naturally
- Request completed successfully: `POST /v1/chat/completions` returned `200`

## Derived Notes

- The timing block only covered `999` prompt tokens even though the slot held `88,394` tokens. That strongly suggests the run benefited from previously cached context and only had to process the delta.
- Decode is roughly `9.5x` slower per token than prompt processing (`53.48 / 5.64`), which is normal for llama.cpp serving and is the main throughput bottleneck for long answers.
- The checkpoint churn is non-trivial: one old checkpoint was erased and the final checkpoint reached the cap of `32 / 32`. That makes `CACHE_REUSE`, slot reuse, and checkpoint policy worth watching as context grows toward `1M`.

## Raw Log Snippet

```text
196.00.663.764 I slot update_slots: id  0 | task 9871 | n_tokens = 88390, memory_seq_rm [88390, end)
196.00.672.532 I reasoning-budget: activated, budget=2147483647 tokens
196.00.672.550 I reasoning-budget: deactivated (natural end)
196.00.673.499 I slot init_sampler: id  0 | task 9871 | init sampler, took 9.59 ms, tokens: text = 88394, total = 88394
196.00.673.501 I slot update_slots: id  0 | task 9871 | prompt processing done, n_tokens = 88394, batch.n_tokens = 4
196.00.673.510 W slot update_slots: id  0 | task 9871 | erasing old context checkpoint (pos_min = 58882, pos_max = 58882, n_tokens = 58883, size = 62.813 MiB)
196.03.473.309 W slot update_slots: id  0 | task 9871 | created context checkpoint 32 of 32 (pos_min = 88389, pos_max = 88389, n_tokens = 88390, size = 62.813 MiB)
196.03.584.895 I srv  log_server_r: done request: POST /v1/chat/completions 127.0.0.1 200
197.14.118.554 I slot print_timing: id  0 | task 9871 |
prompt eval time =    5633.83 ms /   999 tokens (    5.64 ms per token,   177.32 tokens per second)
       eval time =   70534.04 ms /  1319 tokens (   53.48 ms per token,    18.70 tokens per second)
      total time =   76167.86 ms /  2318 tokens
197.14.120.302 I slot      release: id  0 | task 9871 | stop processing: n_tokens = 89712, truncated = 0
197.14.120.336 I srv  update_slots: all slots are idle
```
