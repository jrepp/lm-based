# Runtime Config Schema v1

Date: 2026-05-07
Status: Planning

## Purpose

Define the first configuration schemas that the Go `serve-manager` should consume directly.

This document covers:

- `serve-policy.yaml`
- `host-capabilities.yaml`

These files describe desired serving behavior and host constraints. They do not replace sidecars.

## Design Principles

1. Sidecars remain the source of truth for model metadata.
2. Policy files describe orchestration intent, not model facts.
3. Config should be explicit, human-readable, and easy to diff.
4. The initial schema should stay small.
5. Missing values should resolve to conservative defaults.

## File 1: `serve-policy.yaml`

### Policy Purpose

Describe the desired serving behavior for one host-local supervisor instance.

### Policy Suggested Shape

```yaml
api_version: v1

ingress:
  public_listen: 127.0.0.1:8080
  swap_listen: 127.0.0.1:8081
  swap_ui_enabled: false

workers:
  host: 127.0.0.1
  port_range:
    start: 10001
    end: 10100
  default_run_mode: swap_worker
  default_enable_run_capture: false

models:
  enabled:
    - qwen36-27b-q6k
    - qwen25-coder-7b-instruct
  disabled: []
  warm:
    - qwen25-coder-7b-instruct
  operator_only: []

swap:
  global_ttl_seconds: 0
  send_loading_state: true

observability:
  metrics_listen: 127.0.0.1:9091
  structured_logs: true

policy:
  allow_non_gguf: true
  require_local_artifact: true
  fail_apply_on_missing_model: true
```

## `serve-policy.yaml` Sections

### `api_version`

Schema version for the policy file.

Initial value:

- `v1`

### `ingress`

Controls the top-level local serving endpoints.

Fields:

- `public_listen`
  HAProxy public bind address
- `swap_listen`
  internal `llama-swap` bind address behind HAProxy
- `swap_ui_enabled`
  whether `llama-swap` UI is intended to be reachable in this environment

### `workers`

Controls how worker processes are launched.

Fields:

- `host`
  worker bind host, usually `127.0.0.1`
- `port_range.start`
- `port_range.end`
  port pool for backend workers
- `default_run_mode`
  expected worker mode, usually `swap_worker`
- `default_enable_run_capture`
  default for swap-managed workers

### `models`

Controls model exposure state.

Fields:

- `enabled`
  slugs eligible for serving through the managed stack
- `disabled`
  indexed models that should not be served
- `warm`
  models the supervisor should prefer to keep ready
- `operator_only`
  models available for direct/manual serving but excluded from normal ingress

### `swap`

Controls `llama-swap` policy defaults.

Fields:

- `global_ttl_seconds`
- `send_loading_state`

This section should remain small in v1.

### `observability`

Controls supervisor-owned observability surfaces.

Fields:

- `metrics_listen`
  Go supervisor metrics bind address
- `structured_logs`
  whether structured logging is required by policy

### `policy`

High-level behavioral switches.

Fields:

- `allow_non_gguf`
  whether non-GGUF models are allowed into the managed serving plane
- `require_local_artifact`
  whether models without a local artifact must fail validation
- `fail_apply_on_missing_model`
  whether apply should fail if an enabled slug cannot be materialized

## File 2: `host-capabilities.yaml`

### Host Purpose

Describe the capabilities and constraints of the current host.

This file is host-specific. It is not model metadata.

### Host Suggested Shape

```yaml
api_version: v1

host:
  id: mac-studio-01
  class: mac128

backends:
  supported:
    - llama-server
    - transformers-serve
  preferred:
    gguf: llama-server
    transformers: transformers-serve

limits:
  memory_class: 128g
  accelerator: apple-metal
  supports_large_bf16: false
  supports_long_context_heavy_models: limited

profiles:
  excluded: []
  preferred:
    - qwen2.5-coder-transformers
    - qwen3.6
```

## `host-capabilities.yaml` Sections

### `host`

Identity and host class.

Fields:

- `id`
- `class`

Suggested initial classes:

- `mac128`
- `h100-80g`

### `backends`

Describes what backend families this host can run.

Fields:

- `supported`
- `preferred`

This lets the supervisor reject invalid placements before activation.

### `limits`

Host-level operating constraints.

Fields:

- `memory_class`
- `accelerator`
- `supports_large_bf16`
- `supports_long_context_heavy_models`

These fields are intentionally descriptive, not overly precise in v1.

### `profiles`

Policy around launcher profiles.

Fields:

- `excluded`
- `preferred`

This is useful when the same repo state is deployed to multiple hardware classes.

## Supervisor Resolution Rules

Suggested resolution order:

1. read sidecar
2. read launcher profile
3. read host capabilities
4. read serve policy
5. decide:
   - eligible or not
   - enabled or not
   - warm or lazy
   - valid backend path or not

## Validation Rules

Examples of v1 validation behavior:

- enabled slug missing from sidecars: error
- enabled slug excluded by host profile policy: error
- enabled slug has no local artifact and `require_local_artifact=true`: error
- indexed slug unsupported on host but not enabled: informational or warning

## Deliberate Omissions

Not included in v1:

- per-model custom port assignments
- per-model backend command overrides
- arbitrary shell command templates
- cluster-wide routing policy

If those are needed later, they should be added carefully and minimally.
