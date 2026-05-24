# Supervisor Spec v1

Date: 2026-05-07
Status: Planning

## Purpose

Define the first version of the repo-owned supervisor that manages the local serving plane.

This supervisor is the intended operator-facing surface above `llama-swap` and `run-server.py`.

Implementation direction:

- the supervisor should be implemented in Go
- Python should not remain responsible for top-level service lifecycle management

## Scope

Initial scope:

- single host
- one managed HAProxy instance
- one managed `llama-swap` instance
- generated runtime config
- multiple backend types behind one worker launcher contract

Future scope:

- multiple host classes
- top-level routing across host-local supervisors

## Language Boundary

### Go responsibilities

The Go supervisor should own:

- desired-state reconciliation
- HAProxy lifecycle
- config generation
- `llama-swap` lifecycle
- PID ownership
- health aggregation
- transition state management
- status and log APIs
- runtime state persistence

### Python responsibilities

Python may remain responsible for:

- `run-server.py` worker launch logic
- backend-specific adapters
- `transformers serve` wrapper code
- other model-family-specific runtime glue

### Non-goal

Do not port backend-specific transformer invocation code to Go just for uniformity. The language boundary should optimize for operational clarity, not language purity.

## Responsibilities

The supervisor should:

- discover sidecars
- classify which models are eligible on the host
- generate HAProxy config from desired state
- generate `llama-swap` config from desired state
- validate HAProxy launchability before activation
- validate launchability before activation
- manage HAProxy PID and logs
- manage `llama-swap` PID and logs
- own generation lifecycle
- expose status and health
- expose aggregated logs
- coordinate safe rollout and drain actions

The supervisor should not:

- duplicate backend-specific flag logic
- replace `run-server.py`
- become a model registry
- hand-edit sidecars

## Proposed Commands

Suggested command surface:

- `serve-manager plan`
- `serve-manager apply`
- `serve-manager status`
- `serve-manager logs`
- `serve-manager doctor`
- `serve-manager drain <model>`
- `serve-manager stop`

The exact names can change, but the operator surface should stay small and predictable.

These commands should be exposed by the Go supervisor binary, not assembled from Python controller scripts.

## Command Semantics

### `plan`

Reads sidecars and policy, then produces:

- the next candidate config generation
- validation results
- a diff against the active generation

No mutation of live serving state.

### `apply`

Activates the latest valid planned generation.

Expected behavior:

- stage config
- start or reload managed HAProxy
- start or reload managed `llama-swap`
- verify ingress and swap health
- mark generation active

### `status`

Shows:

- supervisor state
- active generation
- HAProxy health
- `llama-swap` health
- loaded or warm workers
- model eligibility state

### `logs`

Shows:

- supervisor logs
- HAProxy logs
- `llama-swap` logs
- per-worker logs when available

### `doctor`

Checks:

- sidecar consistency
- runtime binary availability
- port conflicts
- dependency readiness
- host capability mismatches

### `drain`

Marks a model or generation for graceful retirement.

Expected behavior:

- stop sending new traffic
- let current work finish where possible
- retire the worker when safe

## Worker Contract

Workers should always launch through `run-server.py`.

Required environment:

- `MODEL_SLUG`
- `PORT`

Recommended environment:

- `HOST=127.0.0.1`
- `RUN_MODE=swap_worker`
- `SUPERVISOR_GENERATION=<id>`
- `SUPERVISOR_WORKER_ID=<id>`

Optional operational environment:

- `ENABLE_RUN_CAPTURE=0`
- `WORKER_LOG_MODE=supervised`

The supervisor should treat Python workers as child processes behind a stable contract, not as peer controllers.

## Runtime Policy

Recommended default policy:

- HAProxy owns the stable client-facing port
- `llama-swap` stays behind HAProxy
- swap-managed workers bind only to loopback
- swap-managed workers default to reduced run-capture noise
- direct `run-server.py` mode remains available for debugging
- dependency installation must not be assumed safe at activation time

## Desired-State Inputs

The supervisor should reconcile from:

- sidecars
- launcher profiles
- host capability policy
- explicit serving policy

It should not derive live behavior from ad hoc shell commands.

The desired-state and runtime-state formats should be stable enough for a Go implementation to own directly.
