# Host Topology

Date: 2026-05-07
Status: Planning

## Goal

Define a simple architecture that works well across:

- modern 128 GB Macs
- attached H100-backed hosts

without turning the serving layer into a confused global scheduler.

## Primary Recommendation

Use host-local supervisor-managed serving on each machine class.

That means:

- each host runs its own supervisor
- each host runs its own managed HAProxy
- each host runs its own managed `llama-swap`
- each host only exposes models it can actually serve

Implementation direction:

- each host-local supervisor should be a Go service
- Python should remain behind the worker contract only when a backend genuinely needs it

If a single cross-host client endpoint is desired later, add a routing layer above these host-local serving planes.

## Why Host-Local First

Macs and H100-backed hosts differ materially in:

- preferred backend type
- startup cost
- memory fit rules
- throughput profile
- context-window practicality

Trying to model those directly inside one raw `llama-swap` config would blur routing and launching concerns.

## Host Classes

Suggested initial host classes:

- `mac128`
- `h100-80g`

Possible future host attributes:

- preferred backend families
- unsupported profiles
- memory tier
- accelerator type
- long-context capability
- throughput tier

## Example Placement Policy

### `mac128`

Prefer:

- GGUF via `llama-server`
- smaller local tool-calling models
- local interactive development models

Be cautious with:

- large dense BF16 Transformers models
- heavy high-throughput production workloads

### `h100-80g`

Prefer:

- larger GGUF or BF16 models
- high-throughput backends
- long-context or heavier production workloads

Candidate future backends:

- `vLLM`
- `SGLang`

## Routing Layers

Single-host:

- clients talk to one host-local HAProxy ingress managed by the supervisor

Multi-host:

- clients talk to a higher-level router
- router chooses the correct host class
- selected host-local HAProxy ingress handles the local edge hop
- selected host-local `llama-swap` instance handles model hot-swap

This keeps:

- host selection above
- model worker orchestration local

## Design Rule

Do not make one global raw swap config carry all hardware scheduling logic.

Instead:

- host-local supervisor decides what is runnable here
- top-level routing decides which host should receive the request

That keeps transitions understandable and operations simple.

It also prevents the Python worker layer from becoming an accidental distributed control plane.
