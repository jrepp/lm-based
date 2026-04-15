#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11,<3.14"
# ///
"""
Generate and inspect ClawRouter routing config from model sidecars.

Examples:
  ./clawrouter_config.py            # write clawrouter.json
  ./clawrouter_config.py --status   # show current config summary
  ./clawrouter_config.py --doctor   # validate + probe endpoints + credential audit
  ./clawrouter_config.py --providers
  ./clawrouter_config.py --json
  ./clawrouter_config.py --validate

Credential model
----------------
Each cloud provider has a dedicated env var (e.g. OPENAI_API_KEY).  When that
var is set the provider is routed direct to its native API endpoint.  When it
is not set the provider falls back to the local x402 proxy (default port 8402).

The generated clawrouter.json stores the *name* of the env var (api_key_env),
not the resolved secret, so the file is safe to commit.  ClawRouter resolves
the key from the environment at runtime.

See docs/credentials.md for a full walkthrough.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from lm_launcher.model_index import load_model_records

PROJECT_ROOT = Path(__file__).resolve().parent
MODELS_DIR = PROJECT_ROOT / "models"
CONFIG_FILE = PROJECT_ROOT / "clawrouter.json"

_DEFAULT_PROXY_PORT = 8402


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CloudProvider:
    """Describes a cloud LLM provider: how to credential it and where to send traffic."""
    model_id: str        # e.g. "openai/gpt-4o"
    display: str         # human-readable label
    key_env: str         # env var that holds the API key
    base_env: str        # env var for optional base URL override
    direct_base: str | None  # direct API base URL; None = no known direct endpoint
    x402_capable: bool = True  # can be routed through the x402 proxy


CLOUD_PROVIDERS: list[CloudProvider] = [
    CloudProvider(
        model_id="zai/glm-5",
        display="GLM-5",
        key_env="GLM_API_KEY",
        base_env="GLM_API_BASE",
        direct_base=None,
    ),
    CloudProvider(
        model_id="openai/gpt-4o",
        display="ChatGPT / GPT-4o",
        key_env="OPENAI_API_KEY",
        base_env="OPENAI_API_BASE",
        direct_base="https://api.openai.com/v1",
    ),
    CloudProvider(
        model_id="minimax/minimax-m2.7",
        display="MiniMax M2.7",
        key_env="MINIMAX_API_KEY",
        base_env="MINIMAX_API_BASE",
        direct_base=None,
    ),
    CloudProvider(
        model_id="deepseek/deepseek-chat",
        display="DeepSeek Chat",
        key_env="DEEPSEEK_API_KEY",
        base_env="DEEPSEEK_API_BASE",
        direct_base="https://api.deepseek.com/v1",
    ),
    CloudProvider(
        model_id="anthropic/claude-sonnet-4.6",
        display="Claude Sonnet 4.6",
        key_env="ANTHROPIC_API_KEY",
        base_env="ANTHROPIC_API_BASE",
        direct_base="https://api.anthropic.com/v1",
    ),
    CloudProvider(
        model_id="xai/grok-4-1-fast",
        display="Grok 4.1 Fast",
        key_env="XAI_API_KEY",
        base_env="XAI_API_BASE",
        direct_base="https://api.x.ai/v1",
    ),
    CloudProvider(
        model_id="google/gemini-2.5-pro",
        display="Gemini 2.5 Pro",
        key_env="GEMINI_API_KEY",
        base_env="GEMINI_API_BASE",
        direct_base="https://generativelanguage.googleapis.com/v1beta/openai",
    ),
]


# ---------------------------------------------------------------------------
# Routing profiles
# ---------------------------------------------------------------------------

PROFILES: dict[str, dict[str, bool]] = {
    "auto":       {"local_priority": True,  "fallback_to_cloud": True},
    "eco":        {"local_priority": True,  "fallback_to_cloud": True},
    "premium":    {"local_priority": False, "fallback_to_cloud": True},
    "local_only": {"local_priority": True,  "fallback_to_cloud": False},
}


# ---------------------------------------------------------------------------
# Runtime env helpers
# ---------------------------------------------------------------------------

def _proxy_port(override: int | None = None) -> int:
    if override is not None:
        return override
    return int(os.environ.get("X402_PROXY_PORT", str(_DEFAULT_PROXY_PORT)))


def _host() -> str:
    return os.environ.get("HOST", "127.0.0.1")


def _port() -> int:
    return int(os.environ.get("PORT", "8001"))


def _local_base(host: str, port: int) -> str:
    return f"http://{host}:{port}/v1"


def _proxy_base(pport: int) -> str:
    return f"http://127.0.0.1:{pport}/v1"


def _docker_base(port: int) -> str:
    return f"http://host.docker.internal:{port}/v1"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

@dataclass
class Issue:
    severity: str   # "error" | "warning"
    message: str


def validate_records(records: list[dict[str, Any]]) -> list[Issue]:
    issues: list[Issue] = []
    seen_slugs: dict[str, str] = {}

    for record in records:
        src = record.get("_index_path", "<unknown>")
        artifact = record.get("artifact", {})
        model = record.get("model", {})
        launcher = record.get("launcher", {})
        slug = model.get("slug")

        if record.get("schema_version") != 1:
            issues.append(Issue("error", f"{src}: schema_version must be 1"))
        if not slug:
            issues.append(Issue("error", f"{src}: missing model.slug"))
        elif slug in seen_slugs:
            issues.append(Issue("error", f"{src}: duplicate slug {slug!r} (also in {seen_slugs[slug]})"))
        else:
            seen_slugs[slug] = src

        if not artifact.get("filename"):
            issues.append(Issue("error", f"{src}: missing artifact.filename"))
        if not launcher.get("profile"):
            issues.append(Issue("warning", f"{src}: missing launcher.profile"))
        if launcher.get("script") and Path(str(launcher["script"])).name != "run-server.py":
            issues.append(Issue("warning", f"{src}: launcher.script should point at run-server.py"))

        local_path = artifact.get("local_path")
        if local_path:
            p = Path(local_path)
            if not p.exists():
                issues.append(Issue("warning", f"{src}: artifact not present locally at {p}"))
            elif p.suffix != ".gguf":
                issues.append(Issue("warning", f"{src}: artifact does not end in .gguf"))

    if not records:
        issues.append(Issue("error", f"No model sidecars found in {MODELS_DIR}"))

    return issues


# ---------------------------------------------------------------------------
# Config generation
# ---------------------------------------------------------------------------

def _resolve_provider(provider: CloudProvider, pport: int) -> dict[str, Any]:
    """
    Build a single cloud backend entry.

    Routing decision:
      key set + direct endpoint known  →  routing=direct, openai_base=direct_base
      key set but no direct endpoint   →  routing=proxy  (key will authenticate via proxy)
      key not set                      →  routing=proxy  (x402 payment)

    The JSON stores api_key_env (the var name), never the secret value.
    """
    key_is_set = bool(os.environ.get(provider.key_env))
    base_override = os.environ.get(provider.base_env)

    if key_is_set and (provider.direct_base or base_override):
        openai_base = base_override or provider.direct_base
        routing = "direct"
    else:
        openai_base = base_override or _proxy_base(pport)
        routing = "proxy"

    entry: dict[str, Any] = {
        "model": provider.model_id,
        "display": provider.display,
        "api_key_env": provider.key_env,
        "openai_base": openai_base,
        "routing": routing,
    }
    if provider.direct_base:
        entry["direct_base"] = provider.direct_base
    if provider.x402_capable:
        entry["proxy_base"] = _proxy_base(pport)
    return entry


def build_config(profile: str = "auto", proxy_port_override: int | None = None) -> dict[str, Any]:
    pport = _proxy_port(proxy_port_override)
    host = _host()
    port = _port()

    local = []
    for rec in load_model_records(MODELS_DIR):
        artifact = rec.get("artifact", {})
        model = rec.get("model", {})
        launcher = rec.get("launcher", {})
        local.append({
            "slug": model.get("slug", ""),
            "family": model.get("family", "unknown"),
            "filename": artifact.get("filename", ""),
            "profile": launcher.get("profile", "auto"),
            "local_path": artifact.get("local_path"),
            "openai_base": _local_base(host, port),
        })

    cloud = [_resolve_provider(p, pport) for p in CLOUD_PROVIDERS]

    return {
        "schema_version": 1,
        "profile": profile,
        "proxy_port": pport,
        "local_llama_server": f"http://{host}:{port}",
        "local_openai_base": _local_base(host, port),
        "open_webui_docker_base": _docker_base(port),
        "backends": {"local": local, "cloud": cloud},
        "profiles": PROFILES,
    }


# ---------------------------------------------------------------------------
# Staleness tracking
# ---------------------------------------------------------------------------

def _inputs_mtime() -> float:
    mtimes = [p.stat().st_mtime for p in MODELS_DIR.glob("*.json")]
    return max(mtimes) if mtimes else 0.0


def config_is_stale() -> bool:
    if not CONFIG_FILE.exists():
        return True
    return CONFIG_FILE.stat().st_mtime < _inputs_mtime()


def write_config(config: dict[str, Any]) -> None:
    CONFIG_FILE.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


def load_existing_config() -> dict[str, Any] | None:
    if not CONFIG_FILE.exists():
        return None
    return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Network probes
# ---------------------------------------------------------------------------

def probe_http(url: str, timeout: float = 1.5) -> tuple[bool, str]:
    try:
        req = Request(url, headers={"User-Agent": "clawrouter-config/1"})
        with urlopen(req, timeout=timeout) as r:
            return True, f"HTTP {r.status}"
    except URLError as exc:
        return False, str(exc.reason)
    except Exception as exc:
        return False, str(exc)


def probe_tcp(host: str, port: int, timeout: float = 1.0) -> tuple[bool, str]:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        try:
            sock.connect((host, port))
            return True, "open"
        except OSError as exc:
            return False, str(exc)


# ---------------------------------------------------------------------------
# Credential helpers (shared by --providers and --doctor)
# ---------------------------------------------------------------------------

def _credential_rows() -> list[tuple[str, str, str, str]]:
    """Return (display, key_env, status_label, routing_note) for each provider."""
    rows = []
    for p in CLOUD_PROVIDERS:
        key_is_set = bool(os.environ.get(p.key_env))
        base_override = os.environ.get(p.base_env)
        if key_is_set and (p.direct_base or base_override):
            status = "set"
            note = f"direct → {base_override or p.direct_base}"
        elif key_is_set:
            status = "set"
            note = "set (no direct_base) → x402 proxy"
        elif p.x402_capable:
            status = "not set"
            note = "x402 proxy"
        else:
            status = "not set"
            note = "disabled"
        rows.append((p.display, p.key_env, status, note))
    return rows


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

def show_providers() -> int:
    """--providers: credential audit table."""
    rows = _credential_rows()
    c1 = max(len(r[0]) for r in rows) + 2
    c2 = max(len(r[1]) for r in rows) + 2
    print("Cloud provider credentials  (set keys in .env — see docs/credentials.md)")
    print()
    print(f"  {'Provider':<{c1}}{'Env var':<{c2}}{'Status':<10}Routing")
    print(f"  {'-'*(c1)}{'-'*(c2)}{'-'*10}{'-'*36}")
    for display, key_env, status, note in rows:
        mark = "✓" if status == "set" else "·"
        print(f"  {mark} {display:<{c1-2}}{key_env:<{c2}}{'[' + status + ']':<10}{note}")
    direct = sum(1 for *_, s, n in rows if s == "set" and "direct" in n)
    via_proxy = len(rows) - direct
    print(f"\n  {direct} direct  ·  {via_proxy} via x402 proxy")
    return 0


def show_status() -> int:
    """--status: summarise existing clawrouter.json."""
    config = load_existing_config()
    if config is None:
        print("No config found. Run: ./clawrouter_config.py")
        return 1

    print("ClawRouter config")
    print(f"  file:              {CONFIG_FILE}")
    print(f"  stale:             {'yes — re-run to update' if config_is_stale() else 'no'}")
    print(f"  profile:           {config.get('profile')}")
    print(f"  proxy_port:        {config.get('proxy_port')}")
    print(f"  local_server:      {config.get('local_llama_server')}")
    print(f"  local_openai:      {config.get('local_openai_base')}")
    print(f"  open_webui_docker: {config.get('open_webui_docker_base')}")

    local_backends = config.get("backends", {}).get("local", [])
    print(f"\n  local ({len(local_backends)}):")
    for b in local_backends:
        local_path = b.get("local_path")
        present = Path(local_path).exists() if local_path else False
        mark = "✓" if present else "✗"
        print(f"    {mark} {b.get('slug'):<44} ({b.get('profile')})  →  {b.get('openai_base')}")

    cloud_backends = config.get("backends", {}).get("cloud", [])
    print(f"\n  cloud ({len(cloud_backends)}):")
    for b in cloud_backends:
        routing = b.get("routing", "?")
        key_env = b.get("api_key_env", "")
        key_mark = "✓" if os.environ.get(key_env) else "·"
        tag = f"[{routing}]"
        print(f"    {key_mark} {tag:<9}{b.get('model'):<44}→  {b.get('openai_base')}")

    return 0


def run_doctor(proxy_port_override: int | None = None) -> int:
    """--doctor: validate sidecars, probe endpoints, audit credentials."""
    pport = _proxy_port(proxy_port_override)
    host = _host()
    port = _port()
    records = load_model_records(MODELS_DIR)
    issues = validate_records(records)

    print("ClawRouter doctor")
    print(f"  models_dir:        {MODELS_DIR}")
    print(f"  config_file:       {CONFIG_FILE}")
    print(f"  local_openai:      {_local_base(host, port)}")
    print(f"  open_webui_docker: {_docker_base(port)}")
    print(f"  proxy_openai:      {_proxy_base(pport)}")
    print(f"  config_stale:      {'yes' if config_is_stale() else 'no'}")

    tcp_ok, tcp_d    = probe_tcp(host, port)
    health_ok, hd    = probe_http(f"http://{host}:{port}/health")
    models_ok, md    = probe_http(f"http://{host}:{port}/v1/models")
    proxy_ok, pd     = probe_http(f"http://127.0.0.1:{pport}/v1/models")

    print(f"  probe_tcp:         {'ok' if tcp_ok else 'fail'}  ({tcp_d})")
    print(f"  probe_health:      {'ok' if health_ok else 'fail'}  ({hd})")
    print(f"  probe_v1_models:   {'ok' if models_ok else 'fail'}  ({md})")
    print(f"  probe_proxy:       {'ok' if proxy_ok else 'fail'}  ({pd})")

    if issues:
        print("\n  sidecars:")
        for issue in issues:
            print(f"    {issue.severity}: {issue.message}")
    else:
        print("  sidecars:          ok")

    print("\n  credentials:")
    rows = _credential_rows()
    c1 = max(len(r[0]) for r in rows) + 2
    c2 = max(len(r[1]) for r in rows) + 2
    for display, key_env, status, note in rows:
        mark = "✓" if status == "set" else "·"
        print(f"    {mark} {display:<{c1-2}}{key_env:<{c2}}{note}")

    errors = [i for i in issues if i.severity == "error"]
    if config_is_stale():
        errors.append(Issue("error", "clawrouter.json is stale — re-run to regenerate"))

    if errors:
        print(f"\n  {len(errors)} error(s) found.")
    else:
        print("\n  all checks passed.")

    return 1 if errors else 0


# ---------------------------------------------------------------------------
# Argument parsing & main
# ---------------------------------------------------------------------------

def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate and inspect ClawRouter routing config.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--profile",
        default="auto",
        choices=sorted(PROFILES),
        help="Routing profile written into clawrouter.json (default: auto).",
    )
    parser.add_argument(
        "--proxy-port",
        type=int,
        default=None,
        metavar="PORT",
        help=f"x402 proxy port (default: $X402_PROXY_PORT or {_DEFAULT_PROXY_PORT}).",
    )
    parser.add_argument("--json",      action="store_true", help="Print generated config to stdout, do not write file.")
    parser.add_argument("--status",    action="store_true", help="Print summary of current clawrouter.json.")
    parser.add_argument("--doctor",    action="store_true", help="Validate sidecars + probe endpoints + credential audit.")
    parser.add_argument("--providers", action="store_true", help="Show credential status for all cloud providers.")
    parser.add_argument("--validate",  action="store_true", help="Validate sidecars only, exit non-zero on errors.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])

    if args.status:
        return show_status()
    if args.providers:
        return show_providers()
    if args.doctor:
        return run_doctor(args.proxy_port)

    records = load_model_records(MODELS_DIR)
    issues = validate_records(records)
    errors = [i for i in issues if i.severity == "error"]

    if args.validate:
        for issue in issues:
            print(f"{issue.severity}: {issue.message}")
        return 1 if errors else 0

    config = build_config(profile=args.profile, proxy_port_override=args.proxy_port)

    if args.json:
        print(json.dumps(config, indent=2))
        return 0

    if errors:
        for issue in issues:
            print(f"{issue.severity}: {issue.message}", file=sys.stderr)
        print("Refusing to write clawrouter.json until errors are fixed.", file=sys.stderr)
        return 1

    write_config(config)
    print(f"Written to {CONFIG_FILE}")
    for issue in issues:
        print(f"{issue.severity}: {issue.message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
