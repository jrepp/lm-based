# ClawRouter Operations

`route-config.py` is the operator entry point for keeping routing config current and debuggable.

## Common commands

Regenerate the config after changing model sidecars or cloud backends:

```bash
./route-config.py
```

Show the current config in a compact, human-readable form:

```bash
./route-config.py --status
```

Validate sidecars and fail on structural errors:

```bash
./route-config.py --validate
```

Run a broader health check:

```bash
./route-config.py --doctor
```

Show credential status for every cloud provider:

```bash
./route-config.py --providers
```

## What `--doctor` checks

- sidecar schema and duplicate slug errors
- whether referenced local GGUF paths exist
- whether `clawrouter.json` is stale relative to `models/*.json`
- whether the local `llama-server` endpoint responds on `HOST` / `PORT`
- whether the local x402 / ClawRouter proxy responds on port `8402`
- which cloud provider keys are set and how each will be routed

## Runtime URLs

Host-side tools:

```text
http://127.0.0.1:8001/v1
```

Dockerized Open WebUI:

```text
http://host.docker.internal:8001/v1
```

## Typical workflow

1. Update `models/*.json` or `CLOUD_PROVIDERS` in `route-config.py`.
2. Run `./route-config.py`.
3. Run `./route-config.py --status`.
4. If requests are failing, run `./route-config.py --doctor`.
