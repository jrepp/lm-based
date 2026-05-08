# qwen — local LLM infrastructure
# Run `just` to see available targets

# ─── book ─────────────────────────────────────────────────────────────────────

# Build the Practical Embeddings PDF book
book:
    @./scripts/build_book.sh

# Build book with a specific version
book-version VERSION:
    @./scripts/build_book.sh {{ VERSION }}

# Bump patch version and build
book-patch:
    @./scripts/build_book.sh bump-patch

# Bump minor version and build
book-minor:
    @./scripts/build_book.sh bump-minor

# Build book and open the PDF
book-open: book
    @open pdf-releases/Practical-Embeddings-latest.pdf 2>/dev/null || \
     xdg-open pdf-releases/Practical-Embeddings-latest.pdf 2>/dev/null || \
     echo "PDF ready: pdf-releases/Practical-Embeddings-latest.pdf"

# Remove LaTeX build artifacts
book-clean:
    @./scripts/build_book.sh --clean

# Check that LaTeX (xelatex) is installed
book-check:
    @./scripts/build_book.sh --check

# List built PDFs
book-list:
    @ls -lh pdf-releases/*.pdf 2>/dev/null || echo "No PDFs yet — run: just book"

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

# Start llama-swap proxy (background)
swap-start:
    @uv run --script llama-swap-runner.py start &

# Stop llama-swap proxy
swap-stop:
    @pkill -f "llama-swap" || true

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
