# HAProxy Edge Proxy

Date: 2026-05-07
Status: Planning

## Decision

Use HAProxy as the stable local edge proxy in front of `llama-swap`.

This proxy is part of the data plane. It is not the supervisor and should not replace the supervisor's orchestration role.

## Role In The Serving Plane

Target request path:

```text
client
  -> HAProxy
  -> llama-swap
  -> run-server.py worker
  -> backend implementation
```

Backend implementations may include:

- `llama-server`
- `transformers serve`
- Ouro custom wrapper
- future `vLLM` / `SGLang`

## Why HAProxy

HAProxy is the preferred edge proxy for this design because it is:

- efficient
- simple to reason about
- explicit in behavior
- well suited to local reverse-proxy use
- Prometheus-friendly

It also gives the serving plane a stable data-plane component that is separate from the supervisor.

## Why Not Put The Supervisor In The Request Path

The supervisor should own:

- config generation
- process lifecycle
- state transitions
- status and health aggregation

The supervisor should not:

- hold client sockets
- become the streaming data path
- proxy OpenAI-compatible traffic directly

That separation keeps lifecycle complexity and request-path complexity apart.

## HAProxy Responsibilities

HAProxy should:

- expose the stable local client-facing port
- proxy requests to `llama-swap`
- buffer client-side connection churn where helpful
- preserve streaming behavior for model responses
- expose Prometheus metrics

HAProxy should not:

- decide backend model-family launch flags
- understand sidecars directly
- launch workers
- replace `llama-swap`

## Interaction With `llama-swap`

`llama-swap` remains the model-selection and hot-swap layer.

HAProxy exists above it to provide:

- a stable ingress layer
- cleaner drain/reload behavior
- a place to attach edge metrics
- less visible disruption during swap or supervisor operations

## Streaming And Buffering Guidance

The edge proxy should be configured conservatively for model-serving traffic:

- preserve streaming responses
- avoid pathological buffering of SSE/token streams
- allow graceful draining during reloads and worker transitions

The goal is not to aggressively buffer model output. The goal is to keep the edge stable while the serving stack below it changes state.

## Observability

HAProxy should export Prometheus metrics and be treated as a first-class monitored component.

Metrics should cover at least:

- request counts
- response codes
- backend availability
- open connections
- queue/backpressure behavior

Vector should also collect HAProxy logs as part of the unified local telemetry pipeline.

## Sources

- HAProxy HTTP reverse proxy support:
  <https://www.haproxy.com/documentation/haproxy-configuration-tutorials/protocol-support/http/>
- HAProxy Prometheus exporter:
  <https://www.haproxy.com/documentation/haproxy-configuration-tutorials/alerts-and-monitoring/prometheus/>
