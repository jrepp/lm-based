# Transitions And Runtime State

Date: 2026-05-07
Status: Planning

## Goal

Make configuration changes and model transitions explicit, inspectable, and reversible.

The serving plane should never rely on an implicit “rewrite file and restart process” model.

The long-lived owner of this transition model should be the Go supervisor.

## Configuration Generations

Each supervisor-managed runtime configuration should be tracked as a generation.

Suggested generation states:

- `observed`
- `generated`
- `validated`
- `staged`
- `active`
- `superseded`
- `retired`

## Runtime States

Supervisor runtime states:

- `idle`
- `reconciling`
- `starting`
- `ready`
- `degraded`
- `draining`
- `stopped`
- `failed`

Worker states:

- `absent`
- `eligible`
- `warming`
- `hot`
- `cooling`
- `drained`
- `error`

## Canonical Transition Flow

1. Read desired state and observed sidecars.
2. Generate the next candidate config.
3. Validate sidecars, commands, ports, and runtime prerequisites.
4. Stage the generation in runtime state.
5. Start or reload HAProxy.
6. Start or reload `llama-swap`.
7. Verify ingress and swap health.
8. Mark the generation active.
9. Drain or retire the previous generation if needed.

This transition engine should live in Go so that process ownership, reload semantics, and runtime reconciliation stay in one place.

## Runtime State Layout

Suggested layout:

```text
.runtime/
  supervisor/
    desired.json
    observed.json
    active-generation
    generations/
      20260507T120000Z/
        config.yaml
        validation.json
        activation.json
    pids/
      supervisor.pid
      haproxy.pid
      llama-swap.pid
    logs/
      supervisor.log
      haproxy.log
      llama-swap.log
    workers/
      qwen36-27b-q6k/
        latest.json
      qwen25-coder-7b-instruct/
        latest.json
```

This tree is runtime state only. It should be generated and disposable.

It should be designed so the Go supervisor can read and write it directly without depending on Python-specific object models.

## What Should Be Recorded

Per generation:

- rendered config
- rendered HAProxy config
- validation result
- activation timestamp
- active ingress address
- resolved model set

Per worker:

- slug
- assigned port
- backend type
- pid if known
- generation id
- current worker state
- last error if any

## Transition Safety

The system should prefer:

- stage before activate
- validate before mutate
- drain before retire
- preserve old generation metadata for inspection

This matters more than elegant implementation details. If operators cannot tell what changed and why, the control surface is not clean.

This is one of the strongest reasons to move service management into Go: lifecycle correctness matters more than reusing existing Python helpers.
