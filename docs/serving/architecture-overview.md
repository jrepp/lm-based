# Multi-Backend Serving Architecture

Date: 2026-05-07
Status: Planning

## Goal

Define a clean local serving architecture with:

- one operator-facing control surface
- one stable client-facing API surface
- multiple local backend types
- predictable transitions between runtime configurations

The design target is a supervisor-managed serving plane, not a collection of separate scripts.

Implementation direction:

- long-lived orchestration and service management should be implemented in Go
- backend-specific runtime adapters may remain in Python

## Architecture Diagram

```text
                             operator
                                |
                                v
                  +-----------------------------+
                  | serve-manager               |
                  |-----------------------------|
                  | plan / apply / status       |
                  | generation state            |
                  | child process supervision   |
                  | stats poller + dashboard    |
                  +---------------+-------------+
                                  |
              generated runtime   |   runtime observation
              config + lifecycle  |
                                  v
      +---------------------------+----------------------------+
      |                                                        |
      v                                                        v
+-------------+                                      +----------------+
| HAProxy     |                                      | stats outputs  |
|-------------|                                      |----------------|
| stable edge |                                      | current JSON   |
| health      |                                      | buckets        |
| metrics     |                                      | compact trends |
+------+------+                                      +-------+--------+
       |                                                     ^
       | client traffic                                      |
       v                                                     |
+-------------+       worker command        +----------------+--------+
| llama-swap  +---------------------------->+ run-server.py            |
|-------------|                             |--------------------------|
| model route |                             | sidecar lookup           |
| hot swap    |                             | profile resolution       |
| warm / cold |                             | backend adapter launch   |
+------+------+                             +------------+-------------+
       |                                                 |
       | proxied model traffic                            |
       v                                                 v
+------+------+       +----------------+       +----------------------+
| worker A    |       | worker B       |       | worker N             |
|-------------|       |----------------|       |----------------------|
| llama-server|       | transformers   |       | future vLLM/SGLang   |
| GGUF        |       | safetensors    |       | backend adapters     |
+------+------+       +-------+--------+       +----------+-----------+
       ^                      ^                           ^
       |                      |                           |
       +----------+-----------+------------+--------------+
                  |
                  v
        +------------------------+
        | model metadata         |
        |------------------------|
        | models/*.json sidecars |
        | lm_launcher/profiles.py|
        | local artifacts        |
        +------------------------+
```

Traffic path:

```text
client -> HAProxy -> llama-swap -> selected worker backend
```

Control path:

```text
operator -> serve-manager -> generated configs -> managed children
```

Observation path:

```text
worker /slots + /metrics -> stats poller -> rolling JSON -> dashboard/API
```

## Core Components

### Supervisor

The supervisor is the intended operator-facing control surface.

Language direction:

- implement the supervisor in Go
- keep steady-state orchestration out of Python

Responsibilities:

- read desired serving state
- discover sidecars and launcher profiles
- generate runtime config
- validate before activation
- manage `llama-swap`
- expose status, logs, and health
- own transitions between generations

The supervisor should absorb the service-management responsibilities that are currently spread across helper scripts and shell entrypoints.

### `llama-swap`

`llama-swap` is the managed ingress and hot-swap engine.

Responsibilities:

- expose the stable local OpenAI-compatible endpoint
- route by requested model slug
- start or reuse backend workers
- keep workers warm or cold according to policy

Non-responsibilities:

- backend-specific flag construction
- backend-family inference
- operator-facing lifecycle management

### HAProxy

HAProxy is the stable local edge proxy in front of `llama-swap`.

Responsibilities:

- expose the stable client-facing local endpoint
- proxy traffic to `llama-swap`
- provide efficient edge request handling
- expose edge metrics for observability

Non-responsibilities:

- model launch
- backend-family selection
- orchestration or control-plane decisions

### `run-server.py`

`run-server.py` is the canonical worker launcher.

Language direction:

- keep worker launch and backend-specific adapter logic in Python where useful
- do not keep Python as the top-level service controller

Responsibilities:

- launch one worker for one slug
- resolve sidecar metadata
- choose the backend implementation
- apply profile defaults

Backends may include:

- `llama-server` for GGUF
- `transformers serve` for Transformers snapshots
- Ouro custom wrapper
- future `vLLM` / `SGLang` wrappers

### Sidecars and Profiles

`models/*.json` and `lm_launcher/profiles.py` remain the source of truth for:

- slug identity
- artifact path
- model format
- launcher profile
- runtime hints

## Target Flow

1. Client sends an OpenAI-compatible request to the stable ingress endpoint.
2. HAProxy proxies the request to `llama-swap`.
3. `llama-swap` inspects the requested model slug.
4. If no local worker is ready, `llama-swap` launches a worker command.
5. The worker command invokes `run-server.py` with `MODEL_SLUG` and port information.
6. `run-server.py` resolves the sidecar and chooses the correct backend.
7. The worker becomes healthy and receives proxied traffic.

## Design Rules

1. `llama-swap` must not become a second launcher framework.
2. `run-server.py` must be the only worker entrypoint.
3. Sidecars must remain authoritative for model metadata.
4. Runtime config must be generated, not hand-edited.
5. Operator workflows must go through the supervisor, not directly through `llama-swap`.

## Why This Split

This split keeps responsibilities clear:

- supervisor: orchestration
- HAProxy: stable edge proxy
- `llama-swap`: ingress and hot-swap
- `run-server.py`: worker launch
- sidecars: model metadata

That separation is what makes the system understandable when it grows to include multiple hardware classes and backend types.

It also creates a clean language boundary:

- Go owns orchestration, config generation, process supervision, and state transitions
- Python owns backend adapters and model-family-specific launch code
