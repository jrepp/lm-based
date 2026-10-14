---
title: Host broker for taxdesk-docs in the Pi sandbox
status: Accepted
created: 2026-10-14T00:00:00Z
deciders: maintainer
tags: [adr, pi, sandbox, security]
id: adr-006
project_id: lm-based
doc_uuid: 9ae91493-034a-40c1-9b55-512647db11a8
---

# Context

`pi-local --sandbox` runs Pi in an OpenShell microVM (Linux) whose only permitted
egress is the host gateway address that reaches llama-swap. The Tax Desk household
records app is reached only through its `taxdesk-docs` CLI, a macOS arm64 binary
that reads an automation credential from the login Keychain through
Security.framework (only that compiled binary is trusted to read it) and calls the
Tax Desk server over HTTPS. Neither the binary, the Keychain, nor HTTPS to the Tax
Desk host is available inside the VM, so a real classification run over about 500
bank rows had to run unsandboxed.

# Decision

`pi-local --sandbox` starts a small broker (`lm_launcher/taxdesk_broker.py`) in
its own process when a host `taxdesk-docs` is found (`TAXDESK_DOCS_BIN`, `PATH`,
or `./dist/taxdesk-docs` in the workspace), and stops it when Pi exits.

- It listens on host loopback, reached from the VM at the sandbox gateway address,
  and the sandbox policy gains one rule for that port, for the node binary only.
- It runs the host binary for allowlisted subcommands only (the CLI's `manifest`,
  intersected with a static list), with strict per-command flag and positional
  validation. `login`, `logout`, `--url` and `--help` never run.
- The binary gets a minimal environment (HOME, USER, PATH, and the host's own
  TAXDESK_URL / TAXDESK_CA) and a private temporary working directory.
- `--out` paths are replaced with host temporary paths; the bytes are streamed back
  and written in the VM by the shim. `--body <file>` becomes stdin with `--stdin`.
- Every request carries a per-launch bearer token from a mode-600 config file in the
  sandbox agent directory. The token grants only what the broker allows; it is not the
  Tax Desk credential.
- The broker log holds command names, exit codes and durations only.

Inside the VM, `support/pi/sandbox/bin/taxdesk-docs` (a node shim) is first on PATH,
so the agent and the Tax Desk skills keep calling `taxdesk-docs ...` unchanged.

# Consequences

## Positive

- Tax Desk runs can use the sandbox: the agent never sees host env, SSH keys, the
  Keychain, or the network beyond the gateway.
- The server-side automation scope (deny by default) remains the primary limit; the
  broker narrows the CLI surface further.

## Negative

- Any process inside the VM can drive the allowlisted commands while the session runs
  (the same reach the agent has).
- The broker port is on host loopback; other local processes could reach it, but they
  need the per-launch token, and they could run the host binary directly anyway.
- The allowlist must track new CLI commands; the broker warns when the manifest lists
  commands it does not allow.

## Neutral

- Unsandboxed `pi-local` is unchanged: the agent runs the host binary directly.

# Alternatives Considered

## Expose the Tax Desk host in the sandbox policy

Would also need the credential inside the VM, which defeats the Keychain trust model.

## Forward the Keychain or the binary into the VM

Not possible: the binary is macOS-only and the Keychain is a host service.

# References

- [ADR-005: MLX decision-model serving via the kev runtime](./adr-005-mlx-decision-model-serving-kev.md)
- `docs/pi-local-model.md` (Sandboxed launches)
