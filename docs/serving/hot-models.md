# Hot Models and Routed Access

How the stack decides which models are available for routing, and how clients
(like pi) discover them dynamically.

## Hot vs all

Two populations of models are distinguished:

| Set | Source | Meaning |
| --- | --- | --- |
| **All** | every sidecar in `models/*.json` | the full model index |
| **Hot** | `serve-policy.yaml` -> `models.enabled` | the models the operator wants available right now |

Only **hot** models are exposed for routing and dynamic discovery. The rest of
the index stays recorded but is not routable. This keeps the client-facing
surface small and intentional, regardless of how many sidecars accumulate.

The serve-manager (the control plane) reads `serve-policy.yaml`, so it is
**aware** of the hot set and the full index as distinct things.

## How the hot set flows into routing

```text
serve-policy.yaml (models.enabled)   <-- operator declares the hot set
        |
        v
llama_swap/config.build_config()     <-- filters sidecars to enabled slugs
        |
        v
llama-swap.yaml                      <-- only hot models present
        |
        v
llama-swap :8081/v1/models           <-- clients dynamically query hot models
```

`llama_swap/config.py:build_config` reads the effective policy
(`serve-policy.yaml` with `serve-policy.local.yaml` merged over it) and includes
only the `enabled` slugs when generating `llama-swap.yaml`. If there is no policy
or no `enabled` list, no filter is applied (every model is included), so the hot
filter is opt-in through the policy. With `policy.require_local_artifact`,
enabled models whose weights are not downloaded are left out too, and dropped
from routing groups.

Because `llama-swap.yaml` contains only hot models, the proxy's
`/v1/models` endpoint returns exactly the hot set. That is the **dynamic
query**: a client asks "what is available?" and gets the hot set at runtime,
with no hardcoded list.

## Declaring the hot set

Edit `serve-policy.local.yaml` (gitignored, written by `./up init`). Lists replace
the tracked default's lists, so give the whole set:

```json
{
  "models": {
    "enabled": [
      "ternary-bonsai-27b-mlx-2bit",
      "qwen36-27b-mtp-ud-q5k-xl"
    ],
    "disabled": [],
    "warm": [],
    "operator_only": []
  }
}
```

Then regenerate and restart the proxy:

```bash
./llama-swap-runner.py config     # rewrite llama-swap.yaml from the hot set
./llama-swap-runner.py start      # (or ./up swap --restart in the tmux session)
```

Only slugs that resolve to a real sidecar are emitted; an enabled slug with no
sidecar is a policy error to fix, not a silent route.

## pi configuration (routed, multi-model)

Point a single pi provider at llama-swap and list the hot models. The model
`id` is the routing key — llama-swap hot-swaps to the matching worker on
demand.

```json
{
  "providers": {
    "local-swap": {
      "baseUrl": "http://127.0.0.1:8081/v1",
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
          "contextWindow": 262144,
          "maxTokens": 8192,
          "cost": { "input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0 },
          "compat": { "thinkingFormat": "qwen-chat-template" }
        },
        {
          "id": "qwen36-27b-mtp-ud-q5k-xl",
          "name": "Qwen3.6 27B MTP (GGUF)",
          "contextWindow": 262144,
          "maxTokens": 8192,
          "cost": { "input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0 }
        }
      ]
    }
  }
}
```

### Dynamic discovery (optional)

Instead of maintaining the model list by hand, a tiny pi extension can fetch
`http://127.0.0.1:8081/v1/models` at startup and register whatever the hot set
currently contains — see the pi
[custom-provider docs](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/custom-provider.md)
(async factory pattern). This is the fullest form of "dynamic querying of the
hot models": the client never hardcodes a model list; it reflects whatever the
operator enabled.

## OpenCode configuration (dynamic bootstrap)

Released OpenCode versions require explicit entries for custom-provider models. Use the
repository bootstrap to query llama-swap and generate those entries from the live hot set:

```bash
./up swap
./opencode-local
```

The generated config is written under `.runtime/opencode/`, layered over the global
OpenCode config with `OPENCODE_CONFIG`, and rebuilt on every invocation. Absolute paths or
IDs without matching sidecar slugs are rejected. See
[../opencode-local-models.md](../opencode-local-models.md) for the full example.

## Status: hot vs all

`serve-manager status` reports the model surface. The intent is for it to show
both populations distinctly (hot = enabled and routable; all = full index) so
the operator can see what clients will discover versus what is recorded. (Per-
model `warm` / `operator_only` policy fields are reserved for follow-on
behavior: kept resident, or routable for the operator but hidden from
client-facing `/v1/models`.)

## Relationship to the direct path

The direct path ([../pi-local-model.md](../pi-local-model.md)) serves one model
at a time on `:8001` through the sampler proxy, and is simplest for driving a
single model. The routed path here serves many models through one provider on the
policy-owned `swap_listen` address (`:8081` currently), selected by model name. The
sampler-proxy concern (repetition penalty
for low-bit MLX) is specific to the direct MLX path; routed MLX models would
need the same treatment applied at the proxy edge.
