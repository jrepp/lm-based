# pi With a Local Direct Model

Configure [pi](https://github.com/earendil-works/pi-coding-agent) to use a model
served by this stack's **direct worker** — one model loaded at a time on
`127.0.0.1:8001`.

This covers the working setup for the Ternary Bonsai 27B MLX model, including
the sampler proxy that keeps low-bit models from looping and the thinking-mode
configuration.

## Architecture

```text
pi  ->  sampler-proxy (:8002)  ->  direct worker (:8001)
                                    mlx_lm | llama-server
```

- The **direct worker** is brought up by `./up <slug>` and serves exactly one
  model.
- The **sampler proxy** (`support/sampler-proxy`) injects `repetition_penalty`
  into completion requests. It is required for low-bit MLX models: `mlx_lm` has
  no repetition-penalty flag and pi does not send one, so without the proxy the
  ternary Bonsai model degenerates into repetition loops on long generations.
- pi points at the proxy (`:8002`), not the worker directly.

## Bring up the worker and proxy

```bash
./up ternary-bonsai-27b-mlx-2bit
# brings up: worker :8001 + sampler-proxy :8002 + stats + dashboard
```

`./up` includes the sampler proxy automatically for MLX slugs (it is omitted for
GGUF models, which already get a repetition penalty from their serving profile).
The proxy defaults to `REPETITION_PENALTY=1.15`; run `./support/sampler-proxy`
directly with custom env to tune it.

## pi provider config

`~/.pi/agent/models.json` (outside this repo — pi reads it directly; it reloads
on `/model`):

```json
{
  "providers": {
    "local": {
      "baseUrl": "http://127.0.0.1:8002/v1",
      "api": "openai-completions",
      "apiKey": "local",
      "compat": {
        "supportsDeveloperRole": false,
        "supportsReasoningEffort": false,
        "maxTokensField": "max_tokens"
      },
      "models": [
        {
          "id": "ternary-bonsai-27b-mlx-2bit",
          "name": "Bonsai 27B ternary (MLX, thinking)",
          "reasoning": true,
          "input": ["text"],
          "contextWindow": 262144,
          "maxTokens": 8192,
          "cost": { "input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0 },
          "compat": { "thinkingFormat": "qwen-chat-template" }
        }
      ]
    }
  }
}
```

### Why each setting

| Setting | Reason |
| --- | --- |
| `baseUrl :8002` | pi goes through the sampler proxy, not the bare worker. |
| `apiKey: "local"` | Local servers ignore it, but pi hides a model from `/model` unless auth is present. Dummy value is fine. |
| `supportsDeveloperRole: false` | `mlx_lm`/`llama-server` do not understand the `developer` role; pi sends `system` instead. |
| `supportsReasoningEffort: false` | These servers do not accept `reasoning_effort`. |
| `maxTokensField: "max_tokens"` | They use `max_tokens`, not `max_completion_tokens`. |
| `reasoning: true` + `thinkingFormat: "qwen-chat-template"` | Bonsai is a thinking model. `mlx_lm` honors `chat_template_kwargs.enable_thinking` (and Bonsai's chat template reads it), and returns thinking in a `reasoning` field that pi parses. |
| `maxTokens: 8192` | Capped to avoid runaway generation on the single-slot server; raise if you want longer thinking traces. |

## Select the model

```bash
pi --list-models | grep local      # confirm it loaded
# in the TUI:
/model bonsai                       # fuzzy-matches name/id
```

The thinking toggle maps to the model's `enable_thinking`: on generates a
thinking trace, off does not.

## Tuning

The sampler proxy is controlled by environment variables:

| Variable | Default | Notes |
| --- | --- | --- |
| `REPETITION_PENALTY` | `1.1` | `1.1` mild → `1.3` strong. `1.15` is used for the ternary MLX model; raise it if output still loops, lower it if prose degrades. `1.0` disables injection. |
| `REPETITION_CONTEXT` | unset | How many recent tokens to penalize (upstream default otherwise). |
| `MIN_P` | unset | Optional min-p floor. |

The proxy only injects a value when the request does not already set it, so a
client that sends its own sampler params is never overridden.

## Restarts and worker adoption

`support/model-service` (run inside the `./up` model window) adopts an
already-healthy worker for the requested slug before launching a new one, so
re-running `./up <slug>` does not double-bind the port. It matches the running
server by slug **or** by the model directory path (mlx_lm and transformers
report the directory as the model id, not the slug).

## When to use this vs the routed path

The direct path serves one model at a time and is the simplest way to drive a
single local model from pi. To expose **multiple** models through one pi
provider with model-name routing, use the llama-swap path described in
[serving/hot-models.md](serving/hot-models.md).
