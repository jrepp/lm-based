# lm-based — local LLM infrastructure
# Run `just` to see available targets

# ─── setup ────────────────────────────────────────────────────────────────────

# Size a starter model set to this host (writes serve-policy.local.yaml)
init:
    @./up init

# Check prerequisites, downloaded models, and memory
doctor:
    @./up doctor

# Download the enabled models that are missing
pull:
    @./up pull

# ─── pi ───────────────────────────────────────────────────────────────────────

# Install the repo-pinned Pi and its extensions (support/pi/package-lock.json)
pi-install:
    @cd support/pi && npm ci --no-fund --no-audit

# Symlink pi-local onto PATH; it uses the launching directory as Pi's workspace
pi-link dir="~/.local/bin":
    @mkdir -p {{dir}} && ln -sfn "{{justfile_directory()}}/pi-local" {{dir}}/pi-local && ls -l {{dir}}/pi-local

# Symlink the repo's user-facing entry points onto PATH
install dir="$HOME/.local/bin":
    @mkdir -p {{dir}} && for entry in pi-local opencode-local up; do ln -sfn "{{justfile_directory()}}/$entry" "{{dir}}/$entry"; done && ls -l {{dir}}/pi-local {{dir}}/opencode-local {{dir}}/up

# Audit the host: model servers outside llama-swap, wired memory, sidecar context vs GGUF headers
host-doctor:
    @uv run --frozen python -m lm_launcher.host_doctor

# Test the repo Pi extensions, including tool execution regressions
pi-test:
    @node --test support/pi/extensions/*.test.ts support/pi/extensions/*/*.test.ts support/pi/sandbox/*.test.ts

# Show the Pi provider ./pi-local would configure
pi-plan:
    @./pi-local --dry-run

# ─── llama-swap ───────────────────────────────────────────────────────────────

# Download/install llama-swap binary
swap-ensure:
    @uv run --script llama-swap-runner.py ensure

# Generate llama-swap.yaml from model sidecars
swap-config:
    @uv run --script llama-swap-runner.py config

# Print llama-swap.yaml to stdout
swap-config-yaml:
    @uv run --script llama-swap-runner.py config --yaml

# Start llama-swap in the lm-based tmux session (./up --foreground runs it in this terminal)
swap-start:
    @./up swap

# Stop the lm-based tmux session
swap-stop:
    @./up --down

# Show running models
swap-status:
    @uv run --script llama-swap-runner.py status

# Print llama-swap logs
swap-logs:
    @uv run --script llama-swap-runner.py logs

# ─── serving observability ────────────────────────────────────────────────────

# Render staging-only Prometheus and Vector config under .runtime/serve-manager/
serve-observability-render:
    @uv run --script serve-observability.py render

# Print the observability manifest without writing runtime files
serve-observability-show:
    @uv run --script serve-observability.py show

# ─── serve-manager ────────────────────────────────────────────────────────────

# Plan a direct HAProxy staging generation
serve-plan-direct:
    @GOCACHE=/tmp/go-build go run ./cmd/serve-manager plan --mode direct

# Plan a managed HAProxy + llama-swap generation
serve-plan-managed:
    @GOCACHE=/tmp/go-build go run ./cmd/serve-manager plan --mode managed

# Validate binaries, ports, and model artifacts for direct staging
serve-doctor-direct:
    @GOCACHE=/tmp/go-build go run ./cmd/serve-manager doctor --mode direct

# Validate binaries, ports, and model artifacts for managed staging
serve-doctor-managed:
    @GOCACHE=/tmp/go-build go run ./cmd/serve-manager doctor --mode managed

# Apply the direct HAProxy staging generation
serve-apply-direct:
    @GOCACHE=/tmp/go-build go run ./cmd/serve-manager apply --mode direct

# Apply the managed HAProxy + llama-swap staging generation
serve-apply-managed:
    @GOCACHE=/tmp/go-build go run ./cmd/serve-manager apply --mode managed

# Show serve-manager runtime status
serve-status:
    @GOCACHE=/tmp/go-build go run ./cmd/serve-manager status

# Stop staging HAProxy / llama-swap processes
serve-stop:
    @GOCACHE=/tmp/go-build go run ./cmd/serve-manager stop

# ─── routing ──────────────────────────────────────────────────────────────────

# Regenerate clawrouter.json
route-config:
    @./route-config.py

# Show routing config summary
route-status:
    @./route-config.py --status

# Validate sidecars and check credentials
route-doctor:
    @./route-config.py --doctor

# Show credential status
route-providers:
    @./route-config.py --providers
