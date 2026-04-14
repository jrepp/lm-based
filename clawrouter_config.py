#!/usr/bin/env python3
"""
ClawRouter configuration generator for the local LLM routing stack.

Reads the model sidecars in models/ and produces a ClawRouter-compatible
configuration that routes requests across local (llama-server) and remote
(Cloud via x402/USDC) backends.

Layers (front to back):
  L0  Ingress        – Tailscale, Telegram, open-webui
  L1  Agent          – Claw / Hermes
  L2  Router         – ClawRouter smart routing
  L3  Local Backend  – llama-server (OpenAI-compatible wrapper)
  L4  Cloud Backends – GLM, ChatGPT, MiniMax, etc.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
MODELS_DIR = PROJECT_ROOT / "models"
CONFIG_DIR = PROJECT_ROOT / "clawrouter"
ROUTES_FILE = CONFIG_DIR / "routes.json"
PROFILES_FILE = CONFIG_DIR / "profiles.json"
ENV_FILE = PROJECT_ROOT / ".env"

DEFAULT_PROXY_PORT = 8402
DEFAULT_LOCAL_PORT = 8001
DEFAULT_LOCAL_HOST = "127.0.0.1"


def _load_sidecars() -> list[dict[str, Any]]:
    sidecars: list[dict[str, Any]] = []
    for p in sorted(MODELS_DIR.glob("*.json")):
        with open(p) as f:
            data = json.load(f)
        data["_sidecar_path"] = str(p)
        sidecars.append(data)
    return sidecars


def _read_env() -> dict[str, str]:
    env: dict[str, str] = {}
    if not ENV_FILE.exists():
        return env
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def _write_env(updates: dict[str, str]) -> None:
    existing = _read_env()
    existing.update(updates)
    lines: list[str] = []
    for key, value in sorted(existing.items()):
        lines.append(f"{key}={value}")
    with open(ENV_FILE, "w") as f:
        f.write("\n".join(lines) + "\n")


def _ensure_config_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def generate_routes(
    local_host: str = DEFAULT_LOCAL_HOST,
    local_port: int = DEFAULT_LOCAL_PORT,
    proxy_port: int = DEFAULT_PROXY_PORT,
    profile: str = "auto",
    excluded_models: list[str] | None = None,
    cloud_models: list[str] | None = None,
) -> dict[str, Any]:
    sidecars = _load_sidecars()
    excluded = set(excluded_models or [])
    default_cloud = [
        "zai/glm-5",
        "openai/gpt-4o",
        "minimax/minimax-m2.7",
        "deepseek/deepseek-chat",
        "anthropic/claude-sonnet-4.6",
        "xai/grok-4-1-fast",
        "google/gemini-2.5-pro",
    ]
    cloud = cloud_models or default_cloud

    local_backends: list[dict[str, Any]] = []
    for sc in sidecars:
        artifact = sc.get("artifact", {})
        model = sc.get("model", {})
        launcher = sc.get("launcher", {})
        slug = model.get("slug", "")
        if slug in excluded:
            continue
        local_backends.append(
            {
                "slug": slug,
                "family": model.get("family", "unknown"),
                "name": model.get("name", slug),
                "filename": artifact.get("filename", ""),
                "local_port": local_port,
                "local_host": local_host,
                "openai_base": f"http://{local_host}:{local_port}/v1",
                "profile": launcher.get("profile", profile),
            }
        )

    cloud_backends: list[dict[str, Any]] = []
    for model_id in cloud:
        if model_id in excluded:
            continue
        cloud_backends.append(
            {
                "model": model_id,
                "via": "clawrouter-x402",
                "openai_base": f"http://127.0.0.1:{proxy_port}/v1",
                "api_key": "x402",
            }
        )

    config: dict[str, Any] = {
        "schema_version": 1,
        "generated_by": "clawrouter_config.py",
        "proxy_port": proxy_port,
        "routing_profile": profile,
        "layers": {
            "L0_ingress": {
                "description": "Client entry points",
                "endpoints": [
                    {"name": "tailscale", "type": "vpn", "port": "dynamic"},
                    {"name": "telegram", "type": "bot", "port": "webhook"},
                    {"name": "open-webui", "type": "chat_ux", "port": 8080},
                ],
            },
            "L1_agent": {
                "description": "AI agent orchestration",
                "endpoints": [
                    {"name": "claw", "type": "agent"},
                    {"name": "hermes", "type": "agent"},
                ],
            },
            "L2_router": {
                "description": "ClawRouter smart routing (<1ms, local)",
                "proxy_port": proxy_port,
                "routing_profile": profile,
                "scoring_dimensions": 15,
            },
            "L3_local_backend": {
                "description": "Local GGUF models via llama-server",
                "backends": local_backends,
            },
            "L4_cloud_backend": {
                "description": "Remote models via x402/USDC",
                "backends": cloud_backends,
            },
        },
    }
    return config


def generate_profiles() -> dict[str, Any]:
    return {
        "auto": {
            "description": "Balanced: best cost/quality trade-off",
            "local_priority": True,
            "fallback_to_cloud": True,
            "estimated_savings": "74-100%",
        },
        "eco": {
            "description": "Cheapest possible model per request",
            "local_priority": True,
            "fallback_to_cloud": True,
            "estimated_savings": "95-100%",
        },
        "premium": {
            "description": "Best quality, cost no object",
            "local_priority": False,
            "fallback_to_cloud": True,
            "estimated_savings": "0%",
        },
        "local_only": {
            "description": "Never leave local llama-server",
            "local_priority": True,
            "fallback_to_cloud": False,
            "estimated_savings": "100%",
        },
    }


def write_config(
    local_host: str = DEFAULT_LOCAL_HOST,
    local_port: int = DEFAULT_LOCAL_PORT,
    proxy_port: int = DEFAULT_PROXY_PORT,
    profile: str = "auto",
    excluded_models: list[str] | None = None,
    cloud_models: list[str] | None = None,
) -> None:
    _ensure_config_dir()
    routes = generate_routes(
        local_host, local_port, proxy_port, profile, excluded_models, cloud_models
    )
    profiles = generate_profiles()

    with open(ROUTES_FILE, "w") as f:
        json.dump(routes, f, indent=2)
    with open(PROFILES_FILE, "w") as f:
        json.dump(profiles, f, indent=2)

    print(f"Routes written to {ROUTES_FILE}")
    print(f"Profiles written to {PROFILES_FILE}")


def print_status() -> None:
    if ROUTES_FILE.exists():
        with open(ROUTES_FILE) as f:
            routes = json.load(f)
        layers = routes.get("layers", {})
        print("ClawRouter configuration status:")
        for layer_key, layer in layers.items():
            print(f"  {layer_key}: {layer.get('description', '')}")
            if "backends" in layer:
                for b in layer["backends"]:
                    name = b.get("slug") or b.get("model", "?")
                    print(f"    - {name}")
        print(f"  proxy port: {routes.get('proxy_port', '?')}")
        print(f"  profile:    {routes.get('routing_profile', '?')}")
    else:
        print("No configuration found. Run: python clawrouter_config.py generate")


def start_proxy(proxy_port: int = DEFAULT_PROXY_PORT) -> None:
    if not shutil.which("npx"):
        print("npx not found. Install Node.js first.", file=sys.stderr)
        raise SystemExit(1)
    print(f"Starting ClawRouter proxy on :{proxy_port}")
    env_overrides = {
        "BLOCKRUN_PROXY_PORT": str(proxy_port),
    }
    import os

    env = {**os.environ, **env_overrides}
    subprocess.run(
        ["npx", "@blockrun/clawrouter"],
        env=env,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ClawRouter configuration for local LLM routing stack"
    )
    sub = parser.add_subparsers(dest="command")

    gen = sub.add_parser("generate", help="Generate routing configuration")
    gen.add_argument("--local-host", default=DEFAULT_LOCAL_HOST)
    gen.add_argument("--local-port", type=int, default=DEFAULT_LOCAL_PORT)
    gen.add_argument("--proxy-port", type=int, default=DEFAULT_PROXY_PORT)
    gen.add_argument(
        "--profile", default="auto", choices=["auto", "eco", "premium", "local_only"]
    )
    gen.add_argument("--exclude", nargs="*", default=[], help="Model slugs to exclude")
    gen.add_argument(
        "--cloud-models", nargs="*", default=None, help="Override cloud model list"
    )

    sub.add_parser("status", help="Show current configuration")
    sub.add_parser("start", help="Start ClawRouter proxy")

    start_p = sub.add_parser("routes", help="Print routes JSON to stdout")
    start_p.add_argument("--profile", default="auto")
    start_p.add_argument("--proxy-port", type=int, default=DEFAULT_PROXY_PORT)
    start_p.add_argument("--local-port", type=int, default=DEFAULT_LOCAL_PORT)

    args = parser.parse_args()

    if args.command == "generate":
        write_config(
            local_host=args.local_host,
            local_port=args.local_port,
            proxy_port=args.proxy_port,
            profile=args.profile,
            excluded_models=args.exclude,
            cloud_models=args.cloud_models,
        )
    elif args.command == "status":
        print_status()
    elif args.command == "start":
        start_proxy()
    elif args.command == "routes":
        routes = generate_routes(
            local_port=args.local_port,
            proxy_port=args.proxy_port,
            profile=args.profile,
        )
        print(json.dumps(routes, indent=2))
    else:
        parser.print_help()
        raise SystemExit(1)


if __name__ == "__main__":
    main()
