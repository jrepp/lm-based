#!/usr/bin/env python3
"""
Generate ClawRouter routing config from model sidecars.

  python clawrouter_config.py              # write clawrouter.json
  python clawrouter_config.py --status     # show current config
  python clawrouter_config.py --json       # dump to stdout

Defaults for HOST and PORT come from the environment or .env
(via the same pydantic-settings layer the launcher uses).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from lm_launcher.model_index import load_model_records

PROJECT_ROOT = Path(__file__).resolve().parent
MODELS_DIR = PROJECT_ROOT / "models"
CONFIG_FILE = PROJECT_ROOT / "clawrouter.json"

DEFAULT_PROXY_PORT = 8402

CLOUD_MODELS = [
    "zai/glm-5",
    "openai/gpt-4o",
    "minimax/minimax-m2.7",
    "deepseek/deepseek-chat",
    "anthropic/claude-sonnet-4.6",
    "xai/grok-4-1-fast",
    "google/gemini-2.5-pro",
]

PROFILES = {
    "auto": {"local_priority": True, "fallback_to_cloud": True},
    "eco": {"local_priority": True, "fallback_to_cloud": True},
    "premium": {"local_priority": False, "fallback_to_cloud": True},
    "local_only": {"local_priority": True, "fallback_to_cloud": False},
}


def build_config(
    profile: str = "auto",
    proxy_port: int = DEFAULT_PROXY_PORT,
) -> dict:
    host = os.environ.get("HOST", "127.0.0.1")
    port = os.environ.get("PORT", "8001")

    local = []
    for rec in load_model_records(MODELS_DIR):
        artifact = rec.get("artifact", {})
        model = rec.get("model", {})
        local.append(
            {
                "slug": model.get("slug", ""),
                "family": model.get("family", "unknown"),
                "filename": artifact.get("filename", ""),
                "openai_base": f"http://{host}:{port}/v1",
            }
        )

    cloud = [
        {
            "model": m,
            "openai_base": f"http://127.0.0.1:{proxy_port}/v1",
            "api_key": "x402",
        }
        for m in CLOUD_MODELS
    ]

    return {
        "schema_version": 1,
        "proxy_port": proxy_port,
        "profile": profile,
        "local_llama_server": f"http://{host}:{port}",
        "backends": {"local": local, "cloud": cloud},
        "profiles": PROFILES,
    }


def show_status() -> None:
    if not CONFIG_FILE.exists():
        print("No config found. Run: python clawrouter_config.py")
        return
    cfg = json.loads(CONFIG_FILE.read_text())
    print(f"profile:    {cfg.get('profile')}")
    print(f"proxy:      :{cfg.get('proxy_port')}")
    print(f"llama-srv:  {cfg.get('local_llama_server')}")
    for b in cfg.get("backends", {}).get("local", []):
        print(f"  local:    {b['slug']}")
    for b in cfg.get("backends", {}).get("cloud", []):
        print(f"  cloud:    {b['model']}")


def main() -> None:
    args = sys.argv[1:]

    if "--status" in args:
        return show_status()

    profile = "auto"
    proxy_port = DEFAULT_PROXY_PORT
    for i, a in enumerate(args):
        if a == "--profile" and i + 1 < len(args):
            profile = args[i + 1]
        if a == "--proxy-port" and i + 1 < len(args):
            proxy_port = int(args[i + 1])

    cfg = build_config(profile=profile, proxy_port=proxy_port)

    if "--json" in args:
        print(json.dumps(cfg, indent=2))
        return

    CONFIG_FILE.write_text(json.dumps(cfg, indent=2) + "\n")
    print(f"Written to {CONFIG_FILE}")


if __name__ == "__main__":
    main()
