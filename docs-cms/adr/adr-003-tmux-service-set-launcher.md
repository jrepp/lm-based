---
title: Local operator surface via the ./up tmux service-set launcher
status: Accepted
created: 2026-07-15T06:57:19Z
deciders: maintainer
tags: [operations, operator-surface, serve-manager, tmux]
id: adr-003
project_id: lm-based
doc_uuid: 5225c1ba-ae72-4076-a65b-7ec1527c830e
---

# Context

Iterating on the serving stack means repeatedly bringing up several cooperating
processes at once: a model worker (`run-server.py`), the `llama-swap` hot-swap
proxy, the stats poller, the dashboard, and a status view. Doing this by hand
across many terminals is error-prone, and starting a full process supervisor
(systemd / launchd) is heavyweight, platform-specific, and hostile to rapid
restart-during-development.

The launcher also needs deterministic dependency resolution (e.g. `dashboard`
depends on `stats-poll`) and must degrade to plain text when stdout is not a TTY
so it can be scripted and tested.

# Decision

Provide a single uv-backed entrypoint, `./up`, that resolves a target into an
ordered list of services and starts each in a named tmux window in the
`lm-based` session.

- Targets are one of: a service set (`core`, `direct`, `swap`, `observability`,
  `manager`, `all`), a named service, or a model slug discovered from
  `models/*.json`.
- Dependency resolution happens in Python before tmux is touched; each service
  window then runs through a small bash shim, `support/tmux-service-shim`, that
  records `status`, `shim.pid`, `last-exit`, and a tee'd service log under
  `.runtime/tmux/services/<service>/`.
- `support/model-service` adopts an already-healthy worker for a slug before
  launching `run-server.py`, so repeated `./up <slug>` does not double-bind.
- Rich tables render when stdout is a TTY; stable plain text otherwise.

`serve-manager` still owns generated serving state under
`.runtime/serve-manager/`. The tmux layer owns only the PTY/session layer and
its shim logs.

# Consequences

## Positive

- Zero-daemon, fully inspectable panes; restart a window by re-running `./up`.
- Deterministic target resolution keeps bring-up scriptable and testable.
- Model slugs are first-class targets, so a worker plus its observability come
  up together.

## Negative

- Adds a `tmux` dependency and is single-host only.
- This is a developer operator surface, not a production supervisor: no
  auto-restart policy, no resource isolation, no clustering.

## Neutral

- `serve-manager` (and the `supervisor-spec-v1.md` design) is the long-term
  control plane; `./up` is expected to converge toward it rather than replace
  it.

# Alternatives Considered

## systemd / launchd units

Rejected: platform-specific, heavy to iterate on, poor fit for a developer
laptop bring-up loop.

## A custom Go daemon supervisor

Rejected: premature; the supervisor spec is still being defined and the
immediate need was fast, inspectable bring-up, not lifecycle management.

## Manual multi-terminal bring-up

Rejected: not repeatable, not scriptable, error-prone under restart.

# References

- `docs/serving/tmux-service-setup.md`: full design and target reference.
- [ADR-002](./adr-002-serve-manager-observability.md): `./up` runs the stats
  poller and dashboard windows this ADR depends on.
