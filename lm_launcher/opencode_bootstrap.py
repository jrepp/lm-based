from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lm_launcher.pi_bootstrap import (
    BootstrapError,
    Sidecar,
    endpoint_model_ids,
    load_sidecars,
    model_supports_reasoning,
)
from lm_launcher.service_endpoints import swap_api_base


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENDPOINT = swap_api_base()
DEFAULT_PROVIDER = "lm-based"
DEFAULT_CONFIG_PATH = ROOT / ".runtime" / "opencode" / "opencode.json"


class OpenCodeBootstrapError(RuntimeError):
    """A user-actionable OpenCode bootstrap failure."""


@dataclass(frozen=True)
class OpenCodePlan:
    provider: str
    endpoint: str
    models: tuple[tuple[str, dict[str, Any]], ...]
    selected_model: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Launch OpenCode with models discovered from the lm-based hot-model endpoint.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "The bootstrap queries llama-swap /v1/models, verifies stable model slugs\n"
            "against local sidecars, writes a generated OpenCode provider config, and\n"
            "launches OpenCode with that config layered over the global configuration.\n"
            "Arguments it does not recognize are forwarded to OpenCode.\n"
            "\n"
            "Examples:\n"
            "  ./opencode-local\n"
            "  ./opencode-local run 'Summarize this repository'\n"
            "  ./opencode-local --model qwen36-27b-q6k\n"
            "  ./opencode-local --configure-only\n"
            "  ./opencode-local --dry-run\n"
        ),
    )
    parser.add_argument("--configure-only", action="store_true", help="generate config without launching OpenCode")
    parser.add_argument("--dry-run", action="store_true", help="show discovered config without writing files")
    parser.add_argument("--provider", default=DEFAULT_PROVIDER, help=f"provider ID (default: {DEFAULT_PROVIDER})")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help=f"OpenAI base URL (default: {DEFAULT_ENDPOINT})")
    parser.add_argument("--model", help="select one discovered model slug")
    parser.add_argument("--timeout", type=float, default=3.0, help="discovery timeout in seconds (default: 3)")
    parser.add_argument("--config-path", type=Path, default=DEFAULT_CONFIG_PATH, help=argparse.SUPPRESS)
    return parser


def opencode_model(sidecar: Sidecar) -> dict[str, Any]:
    return {
        "name": f"{sidecar.name} (lm-based hot)",
        "reasoning": model_supports_reasoning(sidecar),
        "temperature": True,
        "tool_call": True,
        "modalities": {"input": ["text"], "output": ["text"]},
        "limit": {
            "context": sidecar.context_window,
            "output": min(16384, sidecar.context_window),
        },
    }


def build_plan(
    provider: str,
    endpoint: str,
    requested_model: str | None,
    api_ids: list[str],
    sidecars: dict[str, Sidecar],
) -> OpenCodePlan:
    if not api_ids:
        raise OpenCodeBootstrapError(f"hot-model endpoint {endpoint}/models returned no models")

    models: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    for model_id in api_ids:
        if Path(model_id).is_absolute():
            raise OpenCodeBootstrapError(
                "hot-model discovery returned a local filesystem path; "
                f"use the llama-swap endpoint at {swap_api_base()}, not a direct worker"
            )
        sidecar = sidecars.get(model_id)
        if sidecar is None:
            raise OpenCodeBootstrapError(
                f"hot-model endpoint returned unknown model {model_id!r}; every public ID must match a sidecar slug"
            )
        if model_id not in seen:
            models.append((model_id, opencode_model(sidecar)))
            seen.add(model_id)

    model_ids = [model_id for model_id, _ in models]
    if requested_model is not None:
        if requested_model not in model_ids:
            raise OpenCodeBootstrapError(
                f"model {requested_model!r} is not hot; available models: {', '.join(model_ids)}"
            )
        selected = requested_model
    else:
        selected = model_ids[0]

    return OpenCodePlan(
        provider=provider,
        endpoint=endpoint.rstrip("/"),
        models=tuple(models),
        selected_model=selected,
    )


def opencode_config(plan: OpenCodePlan) -> dict[str, Any]:
    return {
        "$schema": "https://opencode.ai/config.json",
        "model": f"{plan.provider}/{plan.selected_model}",
        "provider": {
            plan.provider: {
                "name": "lm-based hot models",
                "npm": "@ai-sdk/openai-compatible",
                "options": {
                    "baseURL": plan.endpoint,
                    "apiKey": "local",
                },
                "models": dict(plan.models),
            }
        },
    }


def write_generated_config(path: Path, config: dict[str, Any]) -> bool:
    content = json.dumps(config, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return True


def discover_plan(args: argparse.Namespace) -> OpenCodePlan:
    endpoint = args.endpoint.rstrip("/")
    try:
        api_ids = endpoint_model_ids(endpoint, args.timeout)
    except BootstrapError as exc:
        raise OpenCodeBootstrapError(str(exc)) from exc
    return build_plan(args.provider, endpoint, args.model, api_ids, load_sidecars())


def print_plan(plan: OpenCodePlan) -> None:
    print(f"service:  {plan.endpoint}")
    print(f"provider: {plan.provider}")
    print(f"model:    {plan.selected_model}")
    print(f"hot:      {', '.join(model_id for model_id, _ in plan.models)}")
    print(json.dumps(opencode_config(plan), indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args, opencode_args = parser.parse_known_args(argv)
    if opencode_args[:1] == ["--"]:
        opencode_args = opencode_args[1:]
    try:
        plan = discover_plan(args)
        if args.dry_run:
            print_plan(plan)
            return 0

        changed = write_generated_config(args.config_path, opencode_config(plan))
        config_state = "updated" if changed else "current"
        print(f"lm-based service: {plan.endpoint}")
        print(f"OpenCode model:   {plan.provider}/{plan.selected_model}")
        print(f"Hot models:       {', '.join(model_id for model_id, _ in plan.models)}")
        print(f"Generated config: {args.config_path} ({config_state})")
        if args.configure_only:
            print(f"Use with: OPENCODE_CONFIG={args.config_path} opencode models {plan.provider}")
            return 0
        if shutil.which("opencode") is None:
            raise OpenCodeBootstrapError("opencode is not installed or not on PATH")

        command = [
            "opencode",
            "--model",
            f"{plan.provider}/{plan.selected_model}",
            *opencode_args,
        ]
        env = os.environ.copy()
        env["OPENCODE_CONFIG"] = str(args.config_path)
        os.execvpe(command[0], command, env)
    except OpenCodeBootstrapError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print("start the routed provider with ./up swap, then rerun ./opencode-local", file=sys.stderr)
        return 1
    return 0
