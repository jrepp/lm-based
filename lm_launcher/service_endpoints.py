from __future__ import annotations

from pathlib import Path

from lm_launcher.policy import POLICY_PATH, load_policy


DEFAULT_SWAP_LISTEN = "127.0.0.1:8080"


def swap_listen(policy_path: Path = POLICY_PATH) -> str:
    """Return the policy-owned internal llama-swap listen address."""
    value = load_policy(policy_path).get("ingress", {}).get("swap_listen")
    return value if isinstance(value, str) and value else DEFAULT_SWAP_LISTEN


def swap_api_base(policy_path: Path = POLICY_PATH) -> str:
    return f"http://{swap_listen(policy_path)}/v1"
