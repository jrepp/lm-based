# Observability Architecture

Date: 2026-05-07
Status: Planning

## Goal

Create a clean observability stack for:

- the Go supervisor
- HAProxy
- `llama-swap`
- backend workers
- model transitions

The stack should make server swaps, worker lifecycle changes, and degraded states easy to inspect.

## Core Components

### Vector

Vector is the telemetry collection and normalization layer.

Use Vector to collect:

- supervisor logs
- HAProxy logs
- `llama-swap` logs
- worker logs
- Vector internal logs and metrics

Vector can also expose processed metrics for Prometheus scraping.

### Prometheus

Prometheus is the metrics system of record for local serving observability.

Use Prometheus to scrape:

- HAProxy metrics
- supervisor metrics
- `llama-swap` metrics when available
- worker/backend metrics
- Vector-exported metrics

## Component Telemetry Roles

### Go supervisor

Should expose:

- generation state
- apply/reload counts
- activation success/failure
- worker lifecycle counters
- degraded-state counters
- host capability state

### HAProxy

Should expose:

- edge request volume
- response code distribution
- backend health
- open connections
- queue/backpressure indicators

### `llama-swap`

Should expose or make visible:

- loaded workers
- swap events
- warm/cold behavior
- startup failures

### Workers

Workers should expose backend-specific health and metrics where practical.

Examples:

- `llama-server` metrics
- Transformers worker readiness and process-level telemetry
- future `vLLM` / `SGLang` metrics

## Logging Model

Logs should remain component-specific at source, but collected centrally by Vector.

Suggested sources:

- supervisor structured logs
- HAProxy access and runtime logs
- `llama-swap` logs
- worker stdout/stderr or file logs
- Vector `internal_logs`

The supervisor should provide a unified operator-facing `logs` surface even if the underlying storage remains split by component.

## Metrics Model

Prometheus should scrape a small number of stable targets rather than requiring operators to chase ephemeral processes manually.

Suggested scrape targets:

- supervisor metrics endpoint
- HAProxy Prometheus endpoint
- Vector Prometheus exporter endpoint
- selected stable worker metrics endpoints when useful

Use labels carefully to avoid unnecessary cardinality explosions from model IDs, generations, or host metadata.

## Transition Observability

The system should make these events visible:

- generation planned
- generation validated
- generation activated
- reload succeeded
- reload failed
- worker warming
- worker hot
- worker drained
- worker crashed
- ingress degraded

Those events are more important operationally than raw per-process logs alone.

## Why Vector + Prometheus

This pairing keeps roles clean:

- Vector handles collection, normalization, and fan-in
- Prometheus handles scraping, storage, alerting, and dashboards

It also avoids pushing observability responsibilities into the supervisor or request path unnecessarily.

## Sources

- Vector monitoring and internal telemetry:
  https://vector.dev/docs/administration/monitoring/
- Vector Prometheus exporter sink:
  https://vector.dev/docs/reference/configuration/sinks/prometheus_exporter/
- Prometheus configuration and scrape model:
  https://prometheus.io/docs/prometheus/latest/configuration/configuration/
