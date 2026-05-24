# Lifecycle Sequences

Date: 2026-05-07
Status: Planning

## Purpose

Describe the expected runtime sequences for the Go `serve-manager` and the managed serving plane.

This document focuses on:

- startup
- plan
- apply
- reload
- drain
- stop

## Sequence 1: Initial Startup

Goal:

- bring the supervisor up without yet mutating serving state unexpectedly

Expected flow:

1. `serve-manager` starts.
2. It discovers runtime directories and creates them if absent.
3. It reads sidecars, launcher profiles, `serve-policy.yaml`, and `host-capabilities.yaml`.
4. It records `observed.json`.
5. It exposes supervisor health and metrics.
6. It enters `idle` or `ready` depending on whether an active generation already exists.

## Sequence 2: Plan

Goal:

- compute the next candidate serving generation without touching live traffic

Expected flow:

1. Operator runs `serve-manager plan`.
2. Supervisor resolves desired state from policy plus sidecars.
3. Supervisor filters out ineligible models using host capabilities.
4. Supervisor allocates worker ports for enabled models.
5. Supervisor renders:
   - `haproxy.cfg`
   - `llama-swap.yaml`
6. Supervisor validates:
   - sidecars
   - local artifacts
   - runtime binaries
   - port availability
   - worker command construction
7. Supervisor writes generation artifacts under `.runtime/serve-manager/generations/<id>/`.
8. Supervisor marks the generation `validated` if successful.

Result:

- live serving remains unchanged

## Sequence 3: Apply

Goal:

- activate a validated generation safely

Expected flow:

1. Operator runs `serve-manager apply`.
2. Supervisor loads the latest validated generation.
3. Supervisor marks state `reconciling`.
4. Supervisor starts or reloads HAProxy using the staged `haproxy.cfg`.
5. Supervisor verifies HAProxy health.
6. Supervisor starts or reloads `llama-swap` using the staged config.
7. Supervisor verifies `llama-swap` health.
8. Supervisor records the generation as `active`.
9. Supervisor updates `active-generation`.
10. Supervisor transitions to `ready`.

Failure behavior:

- if HAProxy fails, generation does not activate
- if `llama-swap` fails, generation does not activate
- active generation remains unchanged until activation succeeds

## Sequence 4: Request-Time Worker Launch

Goal:

- satisfy a request for a slug that is not already warm

Expected flow:

1. Client hits HAProxy.
2. HAProxy proxies to `llama-swap`.
3. `llama-swap` sees the requested slug.
4. If no worker is ready, `llama-swap` launches the configured worker command.
5. Worker command invokes `run-server.py` with:
   - `MODEL_SLUG`
   - `HOST`
   - `PORT`
   - supervisor metadata env vars
6. `run-server.py` resolves the backend and starts the appropriate runtime.
7. Worker becomes healthy.
8. `llama-swap` forwards traffic to the worker.
9. Supervisor observes or records worker state where possible.

## Sequence 5: Reload / Reconcile

Goal:

- move from active generation `G` to new generation `G+1`

Expected flow:

1. Supervisor plans `G+1`.
2. Supervisor validates `G+1`.
3. Supervisor applies `G+1`.
4. New HAProxy and `llama-swap` config become active.
5. Existing warm workers may remain until aged out or drained.
6. Old generation is marked `superseded`.

Important rule:

- config generation and activation are separate steps

## Sequence 6: Drain A Model

Goal:

- gracefully retire a model worker or make a model unavailable for new work

Expected flow:

1. Operator runs `serve-manager drain <slug>`.
2. Supervisor records drain intent.
3. Supervisor updates desired state or temporary runtime policy.
4. New requests for that slug stop being routed to a warming path.
5. Existing in-flight work is allowed to complete where practical.
6. Worker is eventually marked `drained`.

In v1, the recorded intent and runtime visibility matter more than sophisticated connection migration.

## Sequence 7: Stop

Goal:

- stop the serving plane in an inspectable and orderly way

Expected flow:

1. Operator runs `serve-manager stop`.
2. Supervisor marks state `draining` or `stopped`.
3. Supervisor stops new ingress at HAProxy.
4. Supervisor terminates or drains `llama-swap`.
5. Worker processes exit as traffic drains or as the swap layer stops.
6. Supervisor stops HAProxy.
7. Supervisor preserves runtime state and logs.

## Sequence 8: Failure Recovery

Goal:

- preserve observability and avoid ambiguous partial activation

Expected flow:

1. A child process fails or a validation step fails.
2. Supervisor records:
   - generation id
   - component
   - error
   - timestamp
3. Supervisor marks runtime `degraded` or `failed`.
4. Supervisor does not silently declare the new generation active.
5. Operator can inspect `status`, `logs`, and generation artifacts.

## Key Invariants

1. Plan must not mutate live traffic.
2. Apply must be generation-based.
3. HAProxy and `llama-swap` are managed children.
4. Workers always launch through `run-server.py`.
5. The active generation must always be inspectable.
6. Failures must be attributed to a specific generation and component.
