# Implementation Backlog v1

Date: 2026-05-08
Status: Planning

## Purpose

Turn the serving design set into an execution roadmap with:

- clear milestones
- dependency order
- completion criteria
- explicit non-goals during each phase

This backlog is the bridge from planning to implementation.

## Related Docs

- [README.md](README.md)
- [architecture-overview.md](architecture-overview.md)
- [edge-proxy-haproxy.md](edge-proxy-haproxy.md)
- [observability-architecture.md](observability-architecture.md)
- [config-schema-v1.md](config-schema-v1.md)
- [lifecycle-sequences.md](lifecycle-sequences.md)
- [serve-manager-go-spec-v1.md](serve-manager-go-spec-v1.md)
- [supervisor-spec-v1.md](supervisor-spec-v1.md)
- [transitions-and-state.md](transitions-and-state.md)
- [host-topology.md](host-topology.md)
- [porting-map-v1.md](porting-map-v1.md)

## Execution Principles

1. Keep the current direct server on `:8001` untouched until the new stack is proven.
2. Bring up the new serving plane on separate ports and separate runtime state.
3. Port by responsibility, not by file.
4. Do not let `llama-swap` retain duplicated backend launch logic.
5. Treat observability as part of the platform, not as a final add-on.

## Milestone Overview

### Milestone 0: Contract Freeze

Goal:

- freeze the interfaces the implementation depends on

Must be stable:

- worker env contract
- `serve-policy.yaml` schema
- `host-capabilities.yaml` schema
- runtime state directory layout
- ingress port topology
- HAProxy position in the stack
- supervisor command surface

Completion criteria:

- all design docs in `docs/serving/` are internally consistent
- no unresolved ambiguity about whether a responsibility belongs to Go or Python
- no further structural changes required before scaffolding code

### Milestone 1: Observability Foundation

Goal:

- stand up telemetry before orchestration is introduced

Scope:

- Vector config for local collection
- Prometheus config for local scraping
- initial scrape targets defined
- log ownership plan for:
  - current direct server
  - future HAProxy
  - future `llama-swap`
  - future `serve-manager`

Completion criteria:

- Vector is configured to collect at least one existing local source
- Prometheus can scrape at least one stable target
- the observability architecture is reflected in config files or implementation stubs
- port allocations for metrics endpoints are reserved and documented

Not required:

- dashboards
- alerts
- final production retention choices

### Milestone 2: HAProxy Staging Bring-Up

Goal:

- prove the edge proxy independently

Scope:

- HAProxy config generation or initial static config
- HAProxy listens on staging ingress port
- HAProxy proxies to the current direct server on `:8001`
- HAProxy metrics endpoint is available
- HAProxy logs flow into Vector

Completion criteria:

- OpenAI-compatible requests succeed through HAProxy
- streaming behavior is validated through HAProxy
- current direct server remains unchanged
- Prometheus scrapes HAProxy metrics successfully

Not required:

- `llama-swap`
- supervisor ownership

### Milestone 3: `llama-swap` Staging Behind HAProxy

Goal:

- insert the swap layer without yet changing the worker-launch model

Scope:

- `llama-swap` listens behind HAProxy on its internal port
- HAProxy forwards to `llama-swap`
- `llama-swap` health is visible
- logs and basic status are observable

Completion criteria:

- request path works:
  - client -> HAProxy -> `llama-swap` -> target
- `llama-swap` can be restarted without touching the direct server
- HAProxy and `llama-swap` logs are both available

Not required:

- Go supervisor ownership
- `run-server.py` worker unification

### Milestone 4: Go `serve-manager` Read-Only Skeleton

Goal:

- establish the control-plane binary without letting it mutate runtime yet

Scope:

- scaffold Go `serve-manager`
- implement:
  - `plan`
  - `status`
  - `doctor`
- read sidecars
- read `serve-policy.yaml`
- read `host-capabilities.yaml`
- render generation artifacts into runtime state

Completion criteria:

- `serve-manager plan` produces deterministic generation artifacts
- `serve-manager status` can inspect runtime state
- `serve-manager doctor` validates required binaries, ports, and local artifacts
- no live serving processes are started or modified by the Go code

Not required:

- process supervision
- apply/reload

### Milestone 5: Go Supervisor Owns HAProxy

Goal:

- move first real process ownership into Go

Scope:

- generate HAProxy config per generation
- manage HAProxy PID and logs
- implement HAProxy health verification
- wire HAProxy startup/reload into `serve-manager apply`

Completion criteria:

- `serve-manager apply` can bring HAProxy up on the staging port
- runtime state records:
  - generation
  - HAProxy pid
  - activation result
- failed HAProxy activation does not mark the generation active

Not required:

- `llama-swap` ownership

### Milestone 6: Go Supervisor Owns `llama-swap`

Goal:

- complete control-plane ownership of the ingress stack

Scope:

- generate `llama-swap` config per generation
- manage `llama-swap` PID and logs
- verify `llama-swap` health through the Go supervisor
- expose unified `status` and `logs`

Completion criteria:

- `serve-manager apply` can activate a generation containing both HAProxy and `llama-swap`
- supervisor runtime state records both child processes
- failed `llama-swap` activation does not advance the active generation

Not required:

- final worker launch unification

### Milestone 7: Worker Launch Unification

Goal:

- make `run-server.py` the only worker entrypoint used by swap-managed models

Scope:

- stop generating backend-specific launch commands in the swap layer
- make swap-managed worker commands invoke:
  - `run-server.py`
  - `MODEL_SLUG`
  - assigned worker port
- validate with:
  - one GGUF model
  - one Transformers model

Suggested validation pair:

- `qwen36-27b-q6k`
- `qwen25-coder-7b-instruct`

Completion criteria:

- both validation models launch through the same worker contract
- `llama-swap` no longer carries duplicated backend-family launch logic
- direct mode and managed mode resolve the same profile/backend path for the same slug

This is the key architecture checkpoint.

### Milestone 8: Runtime Policy And Transitions

Goal:

- add controlled runtime behavior beyond simple bring-up

Scope:

- warm model set
- lazy model set
- TTL defaults
- drain intent handling
- generation-aware reload semantics

Completion criteria:

- warm vs lazy model policy is represented in config and runtime state
- drain requests are visible and actionable
- generation transitions remain inspectable
- operator can tell which generation and policy are active

Not required:

- advanced multi-host scheduling

### Milestone 9: Transitional Cleanup

Goal:

- demote or retire old control-plane surfaces

Scope:

- deprecate `llama-swap-runner.py` as primary operator path
- demote Python `llama_swap` control helpers to dev/reference status
- reduce lifecycle ownership in `justfile`
- update README and operational docs

Completion criteria:

- the documented primary serving control path is the Go supervisor
- transitional Python lifecycle helpers are clearly marked or removed
- duplicated lifecycle guidance is gone from the repo

### Milestone 10: Controlled Client Migration

Goal:

- move clients to the new ingress safely

Scope:

- test clients against staging ingress
- validate fallback to direct `:8001`
- choose cutover plan

Completion criteria:

- HAProxy + `llama-swap` + `serve-manager` path is stable
- current direct server remains available as fallback
- cutover can be reversed without rebuilding the stack

## Epic Breakdown

### Epic A: Go Supervisor

Tasks:

- scaffold command surface
- implement runtime state writer/reader
- implement config rendering
- implement child-process supervision
- implement status and doctor commands
- implement activation flow

Definition of done:

- supervisor can own HAProxy and `llama-swap`
- supervisor can render and activate generations

### Epic B: HAProxy Integration

Tasks:

- create generated config model
- define metrics endpoint
- define log path
- validate streaming behavior
- validate restart semantics

Definition of done:

- HAProxy is a stable edge component under supervisor control

### Epic C: `llama-swap` Integration

Tasks:

- define generated config model
- remove backend-specific launch duplication
- integrate health checks
- integrate logs and status

Definition of done:

- `llama-swap` is a managed component, not a manually operated primary surface

### Epic D: Worker Contract Cleanup

Tasks:

- formalize `RUN_MODE=swap_worker`
- ensure `run-server.py` handles managed worker mode cleanly
- make backend wrappers consistent with worker expectations

Definition of done:

- one worker contract serves both GGUF and Transformers validation models

### Epic E: Observability

Tasks:

- Vector config
- Prometheus config
- HAProxy metrics scrape
- supervisor metrics scrape
- log path normalization

Definition of done:

- all control-plane and ingress-plane components are observable

### Epic F: Documentation And Cleanup

Tasks:

- keep docs aligned with implementation
- deprecate outdated operational guidance
- reduce old control-plane surface area

Definition of done:

- operator docs describe one primary management model

## Explicit Rollback Points

The implementation plan should preserve these rollback boundaries:

- after Milestone 2:
  remove HAProxy from path and keep direct `:8001`
- after Milestone 3:
  remove `llama-swap` and keep HAProxy-to-direct
- after Milestone 5:
  disable Go HAProxy ownership and return to manual staging
- after Milestone 6:
  disable Go `llama-swap` ownership and keep HAProxy/direct fallback
- after Milestone 7:
  revert swap-managed workers to old staging behavior if worker unification fails

Rollback must always preserve the current direct server path.

## Completion Criteria For The Program

The migration program is complete when:

- the Go supervisor is the primary operator-facing serving surface
- HAProxy is the stable client-facing ingress
- `llama-swap` is managed, not manually operated
- swap-managed workers launch only through `run-server.py`
- one GGUF and one Transformers model work through the new stack
- Vector and Prometheus provide coherent visibility
- the old direct `:8001` path remains available as a fallback or explicit operator mode
- outdated Python control-plane helpers are retired or clearly non-primary

## Anti-Goals

Do not:

- port everything at once
- replace the live direct server in place
- let docs promise support before milestone completion
- keep duplicated backend launch logic alive after worker unification
- entangle observability setup with irreversible traffic cutover
