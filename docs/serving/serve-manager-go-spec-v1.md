# Serve-Manager Go Spec v1

Date: 2026-05-07
Status: Planning

## Purpose

Define the first concrete Go implementation target for the repo's serving supervisor.

`serve-manager` is the intended operator-facing binary that manages:

- HAProxy
- `llama-swap`
- generated runtime config
- worker launch policy through `run-server.py`
- transition state and runtime status

It is the control plane for the local serving stack.

## Scope

Initial scope:

- single host
- one managed HAProxy instance
- one managed `llama-swap` instance
- generated runtime config
- multiple backend types behind the existing Python worker contract

Out of scope for v1:

- distributed multi-host coordination
- global cluster scheduler behavior
- replacing `run-server.py`
- replacing `llama-swap`

## High-Level Model

Target stack:

```text
operator
  -> serve-manager

client
  -> HAProxy
  -> llama-swap
  -> run-server.py
  -> backend implementation
```

## Binary Shape

Suggested top-level binary:

```text
serve-manager
```

Suggested subcommands:

- `serve-manager plan`
- `serve-manager apply`
- `serve-manager status`
- `serve-manager logs`
- `serve-manager doctor`
- `serve-manager drain`
- `serve-manager stop`

Optional later additions:

- `serve-manager prepare`
- `serve-manager reload`
- `serve-manager inspect`

## Operator Surface

### `plan`

Inputs:

- sidecars
- launcher profiles
- serving policy
- host capability description

Outputs:

- next generation runtime config
- validation results
- diff against active generation

Effects:

- no mutation of live serving state

### `apply`

Applies the latest valid planned generation.

Expected flow:

1. ensure runtime state directory exists
2. materialize generation files
3. write HAProxy config
4. write `llama-swap` config
5. start or reload HAProxy
6. start or reload `llama-swap`
7. verify health
8. mark generation active

### `status`

Shows:

- serve-manager state
- active generation
- HAProxy status
- `llama-swap` status
- known workers
- recent transition outcome

### `logs`

Supports:

- supervisor logs
- HAProxy logs
- `llama-swap` logs
- worker logs

### `doctor`

Checks:

- sidecar validity
- config generation validity
- runtime binary presence
- port conflicts
- directory permissions
- dependency readiness for worker backends
- host capability mismatches

### `drain`

Marks a model slug or generation for graceful retirement.

In v1 this may initially be an intent recorded in runtime state even if drain execution remains conservative.

### `stop`

Gracefully stops supervisor-managed ingress and managed children.

Expected order:

1. stop new traffic at ingress
2. terminate or drain `llama-swap`
3. stop HAProxy
4. preserve runtime state for inspection

## Runtime Inputs

### 1. Sidecars

Authoritative source for:

- slug
- artifact path
- model format
- launcher profile
- recommended environment

### 2. Launcher profiles

Authoritative source for:

- per-family conservative defaults
- backend-specific launch tuning

### 3. Serving policy

Suggested future file:

```text
serve-policy.yaml
```

Suggested contents:

- enabled model set
- warm model set
- ingress ports
- worker port range
- TTL policy
- logging policy
- run-capture policy

### 4. Host capability description

Suggested future file:

```text
host-capabilities.yaml
```

Suggested contents:

- host class
- supported backends
- excluded profiles
- memory tier
- accelerator type

## Runtime State Layout

Suggested path:

```text
.runtime/serve-manager/
```

Suggested contents:

```text
.runtime/serve-manager/
  desired.json
  observed.json
  active-generation
  generations/
    20260507T120000Z/
      haproxy.cfg
      llama-swap.yaml
      validation.json
      activation.json
  pids/
    serve-manager.pid
    haproxy.pid
    llama-swap.pid
  logs/
    serve-manager.log
    haproxy.log
    llama-swap.log
  workers/
    qwen36-27b-q6k/
      latest.json
    qwen25-coder-7b-instruct/
      latest.json
```

This directory is generated runtime state only.

## Process Model

### Parent process

`serve-manager` is the parent process for managed control-plane components.

It owns:

- HAProxy process lifecycle
- `llama-swap` process lifecycle
- generation state
- runtime logs and PIDs

### Managed child processes

Control-plane children:

- HAProxy
- `llama-swap`

Data-plane workers:

- launched by `llama-swap`
- invoked through `run-server.py`

### Worker ownership model

`llama-swap` remains the immediate runtime owner of workers.

`serve-manager` remains the top-level operational owner of the serving plane.

That means:

- `serve-manager` should not directly proxy model traffic
- `serve-manager` should know how workers were intended to be launched
- worker metadata should be reflected in runtime state when observable

## HAProxy Config Generation

`serve-manager` should generate HAProxy config per generation.

v1 expectations:

- one stable frontend bind address
- one backend target: local `llama-swap`
- health-aware upstream configuration
- access logging enabled
- Prometheus endpoint enabled
- streaming-friendly configuration

The HAProxy config should be entirely generated and versioned per generation.

## `llama-swap` Config Generation

`serve-manager` should generate `llama-swap` config per generation.

Key rule:

- every swap-managed worker launches through `run-server.py`

Conceptual worker command:

```text
MODEL_SLUG=<slug> HOST=127.0.0.1 PORT=<worker-port> RUN_MODE=swap_worker ./run-server.py
```

`llama-swap` config should not contain:

- model-family-specific `llama-server` flags
- duplicate profile defaults
- backend-family-specific launch logic

That logic belongs behind the worker contract.

## Worker Contract

Workers are launched through Python, but the contract is owned by the Go supervisor design.

Required environment:

- `MODEL_SLUG`
- `PORT`

Recommended environment:

- `HOST=127.0.0.1`
- `RUN_MODE=swap_worker`
- `SUPERVISOR_GENERATION=<id>`
- `SUPERVISOR_WORKER_ID=<id>`

Optional environment:

- `ENABLE_RUN_CAPTURE=0`
- `WORKER_LOG_MODE=supervised`

Worker behavior expectations:

- bind only to loopback
- expose health in a way usable by `llama-swap`
- avoid noisy operator-mode behaviors by default

## Activation Semantics

Activation should be explicit and generation-based.

Suggested flow:

1. generate next config
2. validate config and runtime prerequisites
3. write generation artifacts
4. stage generation
5. reload or restart HAProxy if needed
6. reload or restart `llama-swap` if needed
7. verify ingress and swap health
8. mark active generation

If validation fails, no active generation should change.

## Reload Strategy

### HAProxy

Preferred behavior:

- graceful reload or restart with explicit PID tracking
- no ambiguous shell backgrounding

### `llama-swap`

Preferred behavior:

- managed restart or reload through supervisor-owned process lifecycle
- preserve observability during transition

## Health Model

The supervisor should distinguish:

### Supervisor health

- is the control plane operating normally?

### HAProxy health

- is the stable ingress available?

### `llama-swap` health

- is model-routing ingress available?

### Worker health

- are launched workers healthy and routable?

## Metrics And Logs

### Metrics

The Go supervisor should expose its own metrics endpoint.

Suggested metrics:

- generations planned
- generations applied
- apply failures
- reload failures
- worker start attempts
- worker observed failures
- degraded-state duration

### Logs

The Go supervisor should emit structured logs.

It should also own paths for:

- HAProxy logs
- `llama-swap` logs
- worker log references where available

These become Vector inputs.

## Observability Integration

The v1 design should assume:

- Vector collects logs and selected internal metrics
- Prometheus scrapes:
  - serve-manager
  - HAProxy
  - `llama-swap` if exposed
  - backend metrics where stable

This means observability is not an afterthought; it is part of the runtime contract.

## Failure Handling

Expected failure classes:

- invalid sidecar
- missing runtime binary
- invalid generated config
- port collision
- HAProxy failed to start
- `llama-swap` failed to start
- worker launch contract invalid
- worker dependency environment not ready

The supervisor should surface:

- clear failure reason
- failing generation
- rollback or non-activation behavior

## Security And Binding Defaults

Recommended defaults:

- HAProxy binds to the stable local ingress address
- `llama-swap` binds to loopback behind HAProxy
- workers bind to loopback only
- metrics/admin endpoints bind to loopback unless intentionally exposed

## Initial Acceptance Criteria

v1 is successful when:

- `serve-manager plan` produces a generation cleanly
- `serve-manager apply` activates HAProxy and `llama-swap` for one host
- one GGUF model works through the stack
- one Transformers model works through the stack
- runtime state clearly shows active generation and child PIDs
- operator no longer needs to manage HAProxy or `llama-swap` directly

## Deliberate Deferrals

Not required in v1:

- global multi-host routing
- full distributed coordination
- replacing Python worker adapters
- dynamic service discovery beyond the local host

## Design Rule

If a decision forces backend-specific launch behavior to be duplicated outside `run-server.py`, it is the wrong decision.

That rule should be enforced throughout implementation.
