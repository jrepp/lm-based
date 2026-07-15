# Serving Design

Planning documents for the repo's future multi-backend local serving plane.

Current design direction:

- service management and orchestration move to Go
- backend-specific model launch and transformer binding code can remain in Python where practical

## Documents

| Document | Contents |
|---|---|
| [architecture-overview.md](architecture-overview.md) | High-level target architecture and ASCII diagram: supervisor, `llama-swap`, `run-server.py`, sidecars, stats, and routing layers |
| [edge-proxy-haproxy.md](edge-proxy-haproxy.md) | HAProxy as the stable edge proxy in front of `llama-swap` |
| [observability-architecture.md](observability-architecture.md) | Vector + Prometheus telemetry model for supervisor, proxy, swap layer, and workers |
| [config-schema-v1.md](config-schema-v1.md) | Initial schemas for `serve-policy.yaml` and `host-capabilities.yaml` |
| [lifecycle-sequences.md](lifecycle-sequences.md) | Startup, plan, apply, reload, drain, and stop sequence flows |
| [porting-map-v1.md](porting-map-v1.md) | Responsibility-by-responsibility migration map from Python control paths to Go supervision |
| [implementation-backlog-v1.md](implementation-backlog-v1.md) | Milestones, epics, rollback points, and completion criteria for the migration |
| [serve-manager-go-spec-v1.md](serve-manager-go-spec-v1.md) | Concrete Go supervisor spec: binary shape, runtime files, child process model, and activation semantics |
| [supervisor-spec-v1.md](supervisor-spec-v1.md) | Proposed operator surface, responsibilities, commands, and runtime contract for the supervisor |
| [transitions-and-state.md](transitions-and-state.md) | Transition model, generation lifecycle, worker states, and runtime state directory layout |
| [host-topology.md](host-topology.md) | Single-host and mixed-hardware deployment model for 128 GB Macs and H100-backed hosts |
| [tmux-service-setup.md](tmux-service-setup.md) | Local tmux service-set launcher design for `./up` and per-service PTY shims |

## Status

These docs are design work only. They describe the intended destination and rollout shape, not the current implementation status.
