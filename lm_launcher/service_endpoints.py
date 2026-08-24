from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SWAP_LISTEN = "127.0.0.1:8080"


def swap_listen(policy_path: Path = ROOT / "serve-policy.yaml") -> str:
    """Return the policy-owned internal llama-swap listen address."""
    try:
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return DEFAULT_SWAP_LISTEN
    value = policy.get("ingress", {}).get("swap_listen")
    return value if isinstance(value, str) and value else DEFAULT_SWAP_LISTEN


def swap_api_base(policy_path: Path = ROOT / "serve-policy.yaml") -> str:
    return f"http://{swap_listen(policy_path)}/v1"
