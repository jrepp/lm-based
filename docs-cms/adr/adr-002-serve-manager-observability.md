---
title: serve-manager observability via a local stats poller and embedded dashboard
status: Accepted
created: 2026-07-15T06:57:19Z
deciders: maintainer
tags: [dashboard, observability, serve-manager, stats]
id: adr-002
project_id: lm-based
doc_uuid: a4a6ebe3-842f-48c0-880f-6622f040be2b
---

# Context

The recent work on Qwen3.6 MTP speculative decoding created an immediate need to
*measure* decode throughput, slot occupancy, and draft-acceptance behavior on a
single host while iterating. The serving design docs
(`docs/serving/observability-architecture.md`) target a full Vector + Prometheus
telemetry model, but standing that up for local bring-up is heavyweight and
slows the characterization loop.

The poller must consume llama-server's existing `/metrics` (Prometheus text) and
`/slots` (per-slot JSON) endpoints without requiring a separate metrics backend,
and it must keep enough history to show trend without unbounded growth.

# Decision

Implement observability as two internal Go packages under
`cmd/serve-manager/internal/`:

- `stats`: a poller that scrapes `/metrics` and `/slots` on an interval, builds
  rolling snapshots (rates + gauges + per-slot summaries), retains bucketed
  history, and compact long-range trends with delta-of-delta compression
  (recent points kept raw, older points compacted to a bounded count).
- `dashboard`: an embedded static UI (`//go:embed assets/*`) that serves the
  latest rolling snapshot at `/api/stats`.

These are surfaced as `serve-manager` subcommands (`stats`, `stats-poll`,
`dashboard`) and write rolling JSON under `.runtime/serve-manager/stats/`. The
`./up` launcher (ADR-003) runs `stats-poll` and `dashboard` as standard service
windows.

# Consequences

## Positive

- Self-contained, no extra infrastructure; works on a single laptop.
- Fast iteration on speculative-decoding throughput with a live view.
- Trend compaction keeps long history bounded for free.

## Negative

- This is not the designed Vector + Prometheus path; cross-host aggregation and
  alerting are not available yet.
- Single-host rolling JSON is not a multi-tenant metrics store.

## Neutral

- The rolling JSON is a natural feed for a future Prometheus exporter, so this
  does not block the heavier telemetry stack; it precedes it.

# Alternatives Considered

## Full Vector + Prometheus + Grafana from the start

Rejected for now: too heavy for local characterization and premature before the
served workloads and slot semantics have stabilized.

## External dashboard pointed at llama-server `/metrics`

Rejected: loses derived rates, slot join, history, and trend compaction; every
client re-derives the same math.

## Ad-hoc `curl /metrics`

Rejected: no history, no rates, not repeatable.

# References

- [ADR-003](./adr-003-tmux-service-set-launcher.md): `./up` runs these windows.
- `docs/serving/architecture-overview.md`: observation path in the diagram.
- `docs/serving/observability-architecture.md`: the future Prometheus target.
