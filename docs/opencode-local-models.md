# OpenCode with Hot Local Models

Use OpenCode against the models currently enabled by `serve-policy.yaml` without copying
model IDs into a permanent OpenCode configuration.

## Why a bootstrap is needed

OpenCode custom providers currently require a `models` map in configuration. Its native
dynamic discovery for OpenAI-compatible custom providers is still under development, so a
bare provider pointed at `/v1/models` does not populate the model picker in released
OpenCode versions.

The repository's `opencode-local` bootstrap closes that gap. On every invocation it:

1. queries the policy-owned llama-swap endpoint from `serve-policy.yaml`
2. reads the exact hot set from `GET /v1/models`
3. requires every public model ID to match a sidecar slug
4. refuses absolute filesystem paths returned by a direct backend
5. generates `.runtime/opencode/opencode.json`
6. layers that generated provider over the global OpenCode config and launches OpenCode

The global `~/.config/opencode/opencode.json` is not modified.

## Start and use it

Start the routed provider:

```bash
./up swap
```

Then launch OpenCode:

```bash
./opencode-local
./opencode-local run "Summarize this repository"
```

Select a particular hot model:

```bash
./opencode-local --model qwen36-27b-q6k
```

If that slug is not returned by llama-swap, the bootstrap fails and prints the available
hot models instead of silently routing somewhere else.

## Inspect discovery without launching

Print the discovered provider and models without writing configuration:

```bash
./opencode-local --dry-run
```

Generate the transient configuration only:

```bash
./opencode-local --configure-only
OPENCODE_CONFIG=.runtime/opencode/opencode.json opencode models lm-based
```

The generated provider has this shape; the `models` entries are rebuilt from the live
endpoint and enriched with context limits from sidecars:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "model": "lm-based/qwen36-27b-q6k",
  "provider": {
    "lm-based": {
      "name": "lm-based hot models",
      "npm": "@ai-sdk/openai-compatible",
      "options": {
        "baseURL": "http://127.0.0.1:8081/v1",
        "apiKey": "local"
      },
      "models": {
        "qwen36-27b-q6k": {
          "name": "Qwen3.6-27B (lm-based hot)",
          "reasoning": true,
          "temperature": true,
          "tool_call": true,
          "modalities": {
            "input": ["text"],
            "output": ["text"]
          },
          "limit": {
            "context": 262144,
            "output": 16384
          }
        }
      }
    }
  }
}
```

## Why direct `/v1/models` can contain a path

Some backends, notably `mlx_lm.server` and Transformers serving, report the model directory
they loaded as their native model ID and do not offer an alias flag. Port `8001` is the
direct worker boundary, so its response can contain a machine-local path.

OpenCode should use the llama-swap discovery boundary instead. llama-swap publishes the
sidecar slug as the routing key, returns only the enabled hot set, and avoids exposing the
backend's filesystem identity. The internal llama-swap address comes from
`ingress.swap_listen` in `serve-policy.yaml` (currently `127.0.0.1:8081`).

## Refresh the hot set

After changing `models.enabled` in `serve-policy.yaml`, reconcile or restart the routed
service and rerun the bootstrap:

```bash
./up swap --restart
./opencode-local
```

The generated OpenCode configuration is runtime state and is intentionally gitignored.

Upstream references:

- [OpenCode custom providers](https://opencode.ai/docs/providers/#custom-provider)
- [OpenCode custom config path](https://opencode.ai/docs/config/#custom-path)
- [OpenCode dynamic-discovery proposal](https://github.com/anomalyco/opencode/pull/42660)
