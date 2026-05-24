# Porting Map v1

Date: 2026-05-08
Status: Planning

## Purpose

Define the migration map from the current mixed Python/script-based serving stack to the target supervisor-managed architecture.

This document is the execution-oriented companion to the serving RFCs. It answers:

- what exists now
- what should own that responsibility later
- what stays in Python
- what moves to Go
- what is transitional
- what can be deleted after the new stack is live

## Migration Principle

Port by responsibility, not by file.

Bad approach:

- rewrite existing Python files line-for-line in Go

Good approach:

- move orchestration responsibilities to Go
- keep backend-specific worker glue in Python
- remove duplicated launcher logic
- explicitly track transitional components until they can be retired

## Target Architecture Summary

Long-term target:

- Go `serve-manager` owns orchestration and lifecycle
- HAProxy owns stable client ingress
- `llama-swap` owns model hot-swap behavior
- `run-server.py` remains the canonical worker launcher
- Python remains only in the worker/backend layer where it adds value

## Work Streams

The migration should be organized into these streams:

### Stream A: Control Plane Port

Move lifecycle and orchestration responsibilities into Go.

### Stream B: Worker Contract Cleanup

Normalize `run-server.py` into a stable worker launch contract for swap-managed and direct mode.

### Stream C: Edge and Swap Integration

Stand up HAProxy and align `llama-swap` with the new control model.

### Stream D: Observability

Add Vector and Prometheus with clean telemetry ownership.

### Stream E: Transitional Cleanup

Retire or reduce the old Python/shell operational surfaces once the Go supervisor is proven.

## Component Inventory

This section maps current components to their future role.

### `run-server.py`

Current role:

- direct operator entrypoint
- backend dispatcher

Target role:

- canonical worker launcher
- still usable for direct operator/debug mode

Language target:

- stays Python

Why:

- backend-specific launch glue belongs here
- this is the right boundary for `llama-server`, `transformers serve`, and future adapters

Expected changes:

- clearer worker-mode env contract
- reduced assumption that it is only an operator CLI

Deletion plan:

- none

### `lm_launcher/*`

Current role:

- settings resolution
- profile defaults
- llama-server argument building
- run capture
- backend wrappers

Target role:

- worker-layer Python support library

Language target:

- largely stays Python

Why:

- model-family-specific launch logic remains appropriate in Python

Expected changes:

- remove control-plane assumptions
- make worker-mode behavior explicit

Deletion plan:

- none, though pieces may be reorganized

### `lm_launcher/transformers_server.py`

Current role:

- Transformers-serving wrapper

Target role:

- backend adapter used only behind the worker contract

Language target:

- stays Python

Expected changes:

- better alignment with swap-worker expectations
- cleaner health/logging contract

Deletion plan:

- none unless replaced by future backend-specific adapters

### `download_model.py`

Current role:

- local model downloader

Target role:

- remains an operator/tooling utility

Language target:

- can stay Python

Why:

- not part of the long-lived serving control plane

Deletion plan:

- none

### `build_gguf.py`

Current role:

- conversion/build utility

Target role:

- remains an offline operator/build utility

Language target:

- can stay Python

Deletion plan:

- none

### `llama_swap/config.py`

Current role:

- generates `llama-swap` config
- currently contains partial launch logic duplication

Target role:

- replaced by Go `serve-manager` config generation

Language target:

- port to Go

Problem:

- currently risks becoming a second launcher
- currently encodes backend-specific assumptions in the wrong layer

Interim plan:

- treat as transitional reference implementation only

Deletion/replacement point:

- once Go `serve-manager plan/apply` generates `llama-swap` config

### `llama_swap/wrapper.py`

Current role:

- basic `llama-swap` process wrapper

Target role:

- largely replaced by Go process management

Language target:

- port lifecycle ownership to Go

Interim plan:

- keep for local experimentation

Deletion/replacement point:

- once Go supervisor owns PID/log/reload semantics

### `llama_swap/cli.py`

Current role:

- operational CLI for `llama-swap`

Target role:

- replaced by Go `serve-manager` operator surface

Language target:

- port to Go

Interim plan:

- keep as staging/dev-only surface

Deletion/replacement point:

- once Go commands cover plan/apply/status/logs/doctor

### `llama-swap-runner.py`

Current role:

- entrypoint for Python `llama-swap` operational commands

Target role:

- replaced by Go `serve-manager`

Language target:

- port to Go

Interim plan:

- keep for development/testing only

Deletion/replacement point:

- once Go supervisor is the standard operator path

### `justfile`

Current role:

- convenience task runner

Target role:

- remain a convenience layer only

Language target:

- stays as task glue

Required change:

- it should call the Go supervisor for serving operations rather than directly owning lifecycle behavior

Deletion plan:

- none, but direct serving-related commands should become wrappers around the new control plane

### `README.md`

Current role:

- mixes current-state operations with future-state language

Target role:

- reflect the actual default operator path once the Go supervisor is real

Required change:

- stage docs updates carefully to avoid claiming support before implementation exists

### `route-config.py`

Current role:

- generates cloud/local routing config
- still assumes a simpler local serving base model

Target role:

- may remain Python initially
- eventually should align with the new ingress/supervisor topology

Question:

- whether this becomes a consumer of the new stable ingress surface or later joins the Go control-plane family

Interim plan:

- keep separate from the serving-plane port until ingress topology is stabilized

## Responsibility Map

### Moves to Go

- serve lifecycle management
- HAProxy config generation
- HAProxy process ownership
- `llama-swap` config generation
- `llama-swap` process ownership
- runtime generation state
- apply/reload/drain state machine
- status and log aggregation
- supervisor metrics
- runtime directory ownership

### Stays in Python

- `run-server.py`
- backend-specific launch adapters
- `lm_launcher` worker-layer support
- model download/build utilities

### Transitional / To Be Retired

- `llama_swap/config.py`
- `llama_swap/wrapper.py`
- `llama_swap/cli.py`
- `llama-swap-runner.py`
- direct lifecycle logic embedded in `justfile`

## Phased Migration Order

### Phase 0: Contract Freeze

Stabilize:

- worker env contract
- runtime directory layout
- serve policy schema
- host capability schema
- ingress topology
- observability topology

### Phase 1: Observability Bring-Up

Add in parallel:

- Vector
- Prometheus
- HAProxy metrics target later
- future supervisor metrics target

Why first:

- the new stack should be visible while it is being introduced

### Phase 2: HAProxy Bring-Up

Bring up HAProxy in front of the current direct server on separate ports.

Responsibility owner:

- initially manual/dev
- later Go supervisor

### Phase 3: `llama-swap` Bring-Up

Place `llama-swap` behind HAProxy, still without changing the live direct server path.

Responsibility owner:

- initially staging tooling
- later Go supervisor

### Phase 4: Go `serve-manager` Read-Only

Implement:

- `plan`
- `status`
- `doctor`

No live mutation yet.

### Phase 5: Go Supervisor Owns HAProxy

Implement:

- config generation
- PID ownership
- logs
- health checks

### Phase 6: Go Supervisor Owns `llama-swap`

Implement:

- `llama-swap` config generation
- lifecycle ownership
- activation sequencing

### Phase 7: Worker Launch Unification

Make all swap-managed workers launch through `run-server.py`.

This is the key architectural checkpoint.

### Phase 8: Transition Policy

Add:

- warm/cold model policy
- TTL
- drain behavior
- generation-aware rollout semantics

### Phase 9: Documentation And Cleanup

Once the new control plane is real:

- update README to make Go supervisor the primary path
- demote or remove old Python control-plane docs
- reduce direct lifecycle commands in `justfile`

## Deletion Candidates

These are likely deletion or heavy-deprecation candidates after migration:

- `llama-swap-runner.py`
- most of `llama_swap/cli.py`
- most of `llama_swap/wrapper.py`
- duplicated launch logic in `llama_swap/config.py`

These are not deletion candidates:

- `run-server.py`
- backend wrappers under `lm_launcher`
- model download/build utilities

## Anti-Goals

Avoid these migration mistakes:

1. Porting helper scripts to Go without clarifying ownership boundaries
2. Keeping two equal control planes indefinitely
3. Letting `llama-swap` config continue to duplicate backend launch logic
4. Mixing observability bring-up with control-plane correctness work in one unreviewable batch
5. Breaking the current `:8001` server while staging the new stack

## Acceptance Criteria For The Port

The migration is on track when:

- the Go supervisor owns process lifecycle for HAProxy and `llama-swap`
- the active generation is inspectable in runtime state
- `llama-swap` no longer contains duplicated backend-family launch logic
- one GGUF model and one Transformers model launch through the same worker contract
- old Python lifecycle helpers are clearly non-primary or removed

## Recommended Next Execution Artifact

After this porting map, the next planning artifact should be an implementation backlog split by stream:

- Go supervisor skeleton
- HAProxy integration
- `llama-swap` integration
- worker contract cleanup
- observability rollout
- docs migration

That backlog should be the bridge from architecture to coding work.
