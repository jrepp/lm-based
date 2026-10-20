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

# Validate durable model research docs and investigation records.
research-docs-check:
    @pre-commit run --files docs/README.md docs/ouro-research.md docs/flashloop-mlx.md docs-cms/memos/memo-002-flashloop-ouro-investigation.md
    @uv run --no-project --python 3.11 --with docuchango==1.17.1 docuchango validate

# Small Metal correctness tests only; no model downloads or service changes.
flashloop-mlx-test:
    @uv run --no-project --python 3.11 --with mlx==0.32.4 --with numpy==2.4.4 python -m unittest discover -s experimental/flashloop_mlx/tests -v

# Compare against a locally reviewed checkout at the pinned upstream revision.
flashloop-mlx-parity checkout:
    @uv run --no-project --python 3.11 --with mlx==0.32.4 --with numpy==2.4.4 --with torch==2.8.0 python -m experimental.flashloop_mlx.verify_upstream "{{checkout}}"

# Report actual stored-array and MLX allocator bytes for a tiny synthetic cache.
flashloop-mlx-smoke:
    @uv run --no-project --python 3.11 --with mlx==0.32.4 python -m experimental.flashloop_mlx.smoke

# Tiny random model; validates four-loop logits without loading checkpoint weights.
flashloop-mlx-engine-parity model checkout device="metal" *flags:
    @uv run --no-project --python 3.11 --with mlx==0.32.4 --with numpy==2.4.4 --with torch==2.8.0 --with transformers==4.54.1 python -m experimental.flashloop_mlx.verify_engine "{{model}}" "{{checkout}}" --device "{{device}}" {{flags}}

# Requires memory/headroom review first. Loads local weights; no swap reload.
flashloop-mlx-thinking model output mode="flash" *flags:
    @uv run --no-project --python 3.11 --with mlx==0.32.4 --with transformers==4.54.1 --with jinja2==3.1.6 python -m experimental.flashloop_mlx.generate "{{model}}" --output "{{output}}" --mode "{{mode}}" {{flags}}

# Independently recheck saved runtime receipts without MLX or model loading.
flashloop-mlx-audit receipt:
    @uv run --no-project --python 3.11 python -m experimental.flashloop_mlx.audit_run "{{receipt}}"

# Export an annotated runtime trajectory figure from a saved generation receipt.
flashloop-mlx-plot receipt output:
    @uv run --no-project --python 3.11 --with matplotlib==3.10.7 python -m experimental.flashloop_mlx.plot_run "{{receipt}}" "{{output}}"

# Serve the experimental MLX backend on loopback; weights load on first request.
flashloop-mlx-serve model port="19095":
    @uv run --no-project --python 3.11 --with mlx==0.32.4 --with transformers==4.54.1 --with jinja2==3.1.6 --with fastapi==0.115.12 --with uvicorn==0.34.2 --with prometheus-client==0.21.1 python -m experimental.flashloop_mlx.service "{{model}}" --port "{{port}}"

# HTTP/metrics lifecycle tests with a fake runtime, without loading model weights.
flashloop-mlx-service-test:
    @uv run --no-project --python 3.11 --with fastapi==0.115.12 --with prometheus-client==0.21.1 --with httpx==0.28.1 python -m unittest discover -s experimental/flashloop_mlx/service_tests -v

# Fixed-prompt repeated decode benchmark; retains token IDs and actual loop receipts.
flashloop-mlx-benchmark model output:
    @uv run --no-project --python 3.11 --with mlx==0.32.4 --with transformers==4.54.1 --with jinja2==3.1.6 python -m experimental.flashloop_mlx.benchmark "{{model}}" "{{output}}"

# Explicit real-model smoke checks; target a fresh, otherwise idle experimental service.
flashloop-mlx-service-smoke output url="http://127.0.0.1:19095":
    @uv run --no-project --python 3.11 python -m experimental.flashloop_mlx.service_smoke --url "{{url}}" --output "{{output}}"

# Verify captured FlashLoop service metrics through the dashboard's actual poller.
flashloop-mlx-dashboard-test:
    @env -u GOROOT go test ./cmd/serve-manager/internal/stats -run TestFlashLoopCapturedMetrics -v

# Interleave dense-history and selected Metal reads; require exact trajectories.
flashloop-mlx-selected-benchmark model output prompt_repeats="1" steps="64" repeats="2":
    @uv run --no-project --python 3.11 --with mlx==0.32.4 --with transformers==4.54.1 --with jinja2==3.1.6 python -m experimental.flashloop_mlx.benchmark "{{model}}" "{{output}}" --compare-selected --prompt-repeats "{{prompt_repeats}}" --steps "{{steps}}" --repeats "{{repeats}}"

# Isolate the selected-reader kernel; synthetic timings are not model throughput.
flashloop-mlx-selected-microbench:
    @uv run --no-project --python 3.11 --with mlx==0.32.4 python -m experimental.flashloop_mlx.benchmark_selected_kv

# Real service checks with a prompt that exercises packed late-loop cache reads.
flashloop-mlx-service-packed-smoke output url="http://127.0.0.1:19095":
    @uv run --no-project --python 3.11 python -m experimental.flashloop_mlx.service_smoke --url "{{url}}" --output "{{output}}" --packed-prompt

# Compare scheduling/fusion against selected-reader baseline, with trajectory checks.
flashloop-mlx-execution-benchmark model output eval_every="8" steps="64" repeats="2" *flags:
    @uv run --no-project --python 3.11 --with mlx==0.32.4 --with transformers==4.54.1 --with jinja2==3.1.6 python -m experimental.flashloop_mlx.benchmark "{{model}}" "{{output}}" --compare-execution --eval-every "{{eval_every}}" --steps "{{steps}}" --repeats "{{repeats}}" {{flags}}
