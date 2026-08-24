from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from lm_launcher.profiles import profile_defaults
from lm_launcher.service_endpoints import swap_api_base


ROOT = Path(__file__).resolve().parent.parent
RUNTIME_SERVICES = ROOT / ".runtime" / "tmux" / "services"
DEFAULT_AGENT_DIR = Path.home() / ".pi" / "agent"
DEFAULT_PROVIDER = "lm-based"
ZERO_COST = {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}


class BootstrapError(RuntimeError):
    """A user-actionable bootstrap failure."""


@dataclass(frozen=True)
class Sidecar:
    slug: str
    name: str
    profile: str
    context_window: int
    artifact_path: Path
    notes: tuple[str, ...]


@dataclass(frozen=True)
class ServiceState:
    services: frozenset[str]
    model_slugs: tuple[str, ...]
    endpoint: str


@dataclass(frozen=True)
class BootstrapPlan:
    provider: str
    endpoint: str
    models: tuple[dict[str, Any], ...]
    selected_model: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bootstrap Pi against the verified, running lm-based service.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "The bootstrap reads tmux shim ownership, verifies /v1/models, merges an\n"
            "lm-based provider into ~/.pi/agent/models.json, and then launches Pi.\n"
            "Arguments it does not recognize are forwarded to Pi.\n"
            "\n"
            "Examples:\n"
            "  ./pi-local\n"
            "  ./pi-local -p 'Summarize this repository'\n"
            "  ./pi-local --configure-only\n"
            "  ./pi-local --dry-run\n"
        ),
    )
    parser.add_argument("--configure-only", action="store_true", help="configure Pi without launching it")
    parser.add_argument("--dry-run", action="store_true", help="show the derived provider without writing files")
    parser.add_argument("--no-default", action="store_true", help="do not change Pi's default provider and model")
    parser.add_argument("--provider", default=DEFAULT_PROVIDER, help=f"Pi provider name (default: {DEFAULT_PROVIDER})")
    parser.add_argument("--model", help="select one model when the running endpoint exposes several")
    parser.add_argument("--session", default="lm-based", help="tmux session name (default: lm-based)")
    parser.add_argument("--timeout", type=float, default=3.0, help="health-check timeout in seconds (default: 3)")
    parser.add_argument("--agent-dir", type=Path, default=DEFAULT_AGENT_DIR, help=argparse.SUPPRESS)
    return parser


def load_sidecars(models_dir: Path = ROOT / "models") -> dict[str, Sidecar]:
    sidecars: dict[str, Sidecar] = {}
    for path in sorted(models_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        model = data.get("model", {})
        launcher = data.get("launcher", {})
        artifact = data.get("artifact", {})
        slug = model.get("slug")
        name = model.get("name")
        if not isinstance(slug, str) or not isinstance(name, str):
            continue
        profile = launcher.get("profile") or "generic"
        defaults = profile_defaults(str(profile), name)
        context_window = int(defaults.get("ctx_size") or 128000)
        local_path = Path(str(artifact.get("local_path") or ""))
        artifact_path = (ROOT / local_path).resolve()
        notes = tuple(note for note in data.get("notes", []) if isinstance(note, str))
        sidecars[slug] = Sidecar(
            slug=slug,
            name=name,
            profile=str(profile),
            context_window=context_window,
            artifact_path=artifact_path,
            notes=notes,
        )
    return sidecars


def process_is_managed_shim(pid: int, *, runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run) -> bool:
    result = runner(["ps", "-p", str(pid), "-o", "command="], text=True, capture_output=True)
    return result.returncode == 0 and str(ROOT / "support" / "tmux-service-shim") in result.stdout


def tmux_service_pids(
    session: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> frozenset[int]:
    result = runner(
        ["tmux", "list-windows", "-t", session, "-F", "#{pane_dead}|#{pane_pid}"],
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        return frozenset()
    pids: set[int] = set()
    for line in result.stdout.splitlines():
        dead, _, pid_value = line.partition("|")
        if dead == "1":
            continue
        try:
            pids.add(int(pid_value))
        except ValueError:
            continue
    return frozenset(pids)


def running_services(
    session: str,
    *,
    services_dir: Path = RUNTIME_SERVICES,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> frozenset[str]:
    services: set[str] = set()
    if not services_dir.is_dir():
        return frozenset()
    tmux_pids = tmux_service_pids(session, runner=runner)
    if not tmux_pids:
        return frozenset()
    for directory in sorted(path for path in services_dir.iterdir() if path.is_dir()):
        try:
            registered_session = (directory / "session").read_text().strip()
            status = (directory / "status").read_text().split()[1]
            pid = int((directory / "shim.pid").read_text().strip())
        except (OSError, ValueError, IndexError):
            continue
        if registered_session != session or status != "running" or pid not in tmux_pids:
            continue
        if process_is_managed_shim(pid, runner=runner):
            services.add(directory.name)
    return frozenset(services)


def service_state(session: str, services: frozenset[str]) -> ServiceState:
    model_slugs = tuple(sorted(name.removeprefix("model:") for name in services if name.startswith("model:")))
    if "sampler-proxy" in services:
        if len(model_slugs) != 1:
            raise BootstrapError("sampler proxy is running without exactly one owned model service")
        endpoint = "http://127.0.0.1:8002/v1"
    elif "llama-swap" in services:
        endpoint = swap_api_base()
    elif len(model_slugs) == 1:
        endpoint = "http://127.0.0.1:8001/v1"
    elif not services:
        raise BootstrapError(f"tmux session {session!r} has no verified running services")
    else:
        raise BootstrapError("cannot identify one client-facing API from the running service set")
    return ServiceState(services=services, model_slugs=model_slugs, endpoint=endpoint)


def endpoint_model_ids(
    endpoint: str,
    timeout: float,
    *,
    opener: Callable[..., object] = urllib.request.urlopen,
) -> list[str]:
    request = urllib.request.Request(
        f"{endpoint}/models",
        headers={"Authorization": "Bearer local", "Accept": "application/json"},
    )
    try:
        with opener(request, timeout=timeout) as response:  # type: ignore[attr-defined]
            payload = json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise BootstrapError(f"service API {endpoint} is not healthy: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise BootstrapError(f"service API {endpoint}/models returned an invalid response")
    model_ids = [item.get("id") for item in payload["data"] if isinstance(item, dict)]
    return [model_id for model_id in model_ids if isinstance(model_id, str) and model_id]


def api_id_matches_sidecar(api_id: str, sidecar: Sidecar) -> bool:
    defaults = profile_defaults(sidecar.profile, sidecar.name)
    aliases = {sidecar.slug, sidecar.name, str(defaults.get("alias") or "")}
    if api_id in aliases:
        return True
    api_path = Path(api_id).expanduser()
    artifact_root = sidecar.artifact_path if sidecar.artifact_path.is_dir() else sidecar.artifact_path.parent
    try:
        return api_path.resolve() == artifact_root.resolve()
    except OSError:
        return False


def resolve_sidecars(
    state: ServiceState,
    api_ids: list[str],
    sidecars: dict[str, Sidecar],
) -> tuple[Sidecar, ...]:
    if not api_ids:
        raise BootstrapError(f"service API {state.endpoint} returned no models")
    if state.model_slugs:
        if len(state.model_slugs) != 1:
            raise BootstrapError("direct serving exposes more than one owned model")
        slug = state.model_slugs[0]
        sidecar = sidecars.get(slug)
        if sidecar is None:
            raise BootstrapError(f"running model {slug!r} has no sidecar")
        if not any(api_id_matches_sidecar(api_id, sidecar) for api_id in api_ids):
            raise BootstrapError(f"running service {slug!r} does not match {state.endpoint}/models")
        return (sidecar,)

    resolved: list[Sidecar] = []
    for api_id in api_ids:
        match = next((sidecar for sidecar in sidecars.values() if api_id_matches_sidecar(api_id, sidecar)), None)
        if match is not None and match not in resolved:
            resolved.append(match)
    if not resolved:
        raise BootstrapError("none of the endpoint models match local sidecar metadata")
    return tuple(resolved)


def model_supports_reasoning(sidecar: Sidecar) -> bool:
    evidence = " ".join((sidecar.name, *sidecar.notes)).lower()
    reasoning_profiles = {"mlx-bonsai", "qwen3.6", "qwen3.6-mtp"}
    return sidecar.profile in reasoning_profiles or "thinking" in evidence


def pi_model(sidecar: Sidecar) -> dict[str, Any]:
    reasoning = model_supports_reasoning(sidecar)
    model: dict[str, Any] = {
        "id": sidecar.slug,
        "name": f"{sidecar.name} (lm-based local)",
        "reasoning": reasoning,
        "input": ["text"],
        "contextWindow": sidecar.context_window,
        "maxTokens": min(8192, sidecar.context_window),
        "cost": dict(ZERO_COST),
    }
    if reasoning and sidecar.profile == "mlx-bonsai":
        model["compat"] = {"thinkingFormat": "qwen-chat-template"}
    return model


def build_plan(
    provider: str,
    requested_model: str | None,
    state: ServiceState,
    sidecars: tuple[Sidecar, ...],
) -> BootstrapPlan:
    models = tuple(pi_model(sidecar) for sidecar in sidecars)
    model_ids = [model["id"] for model in models]
    if requested_model:
        if requested_model not in model_ids:
            raise BootstrapError(f"model {requested_model!r} is not exposed by the running service")
        selected = requested_model
    elif len(model_ids) == 1:
        selected = model_ids[0]
    else:
        raise BootstrapError(f"choose a running model with --model ({', '.join(model_ids)})")
    return BootstrapPlan(
        provider=provider,
        endpoint=state.endpoint,
        models=models,
        selected_model=selected,
    )


def provider_config(plan: BootstrapPlan) -> dict[str, Any]:
    return {
        "baseUrl": plan.endpoint,
        "api": "openai-completions",
        "apiKey": "local",
        "compat": {
            "supportsDeveloperRole": False,
            "supportsReasoningEffort": False,
            "maxTokensField": "max_tokens",
        },
        "models": list(plan.models),
    }


def read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise BootstrapError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise BootstrapError(f"expected a JSON object in {path}")
    return value


def atomic_write_json(path: Path, value: dict[str, Any]) -> bool:
    content = json.dumps(value, indent=2) + "\n"
    if path.exists() and path.read_text() == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        shutil.copy2(path, path.with_name(f"{path.name}.lm-based.bak"))
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w") as handle:
            handle.write(content)
        temporary.chmod(0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return True


def configure_pi(plan: BootstrapPlan, agent_dir: Path, *, set_default: bool) -> tuple[bool, bool]:
    models_path = agent_dir / "models.json"
    models_config = read_json_object(models_path)
    providers = models_config.setdefault("providers", {})
    if not isinstance(providers, dict):
        raise BootstrapError(f"expected providers to be an object in {models_path}")
    providers[plan.provider] = provider_config(plan)
    models_changed = atomic_write_json(models_path, models_config)

    settings_changed = False
    if set_default:
        settings_path = agent_dir / "settings.json"
        settings = read_json_object(settings_path)
        settings["defaultProvider"] = plan.provider
        settings["defaultModel"] = plan.selected_model
        settings_changed = atomic_write_json(settings_path, settings)
    return models_changed, settings_changed


def derive_plan(args: argparse.Namespace) -> BootstrapPlan:
    sidecars = load_sidecars()
    services = running_services(args.session)
    state = service_state(args.session, services)
    api_ids = endpoint_model_ids(state.endpoint, args.timeout)
    resolved = resolve_sidecars(state, api_ids, sidecars)
    return build_plan(args.provider, args.model, state, resolved)


def print_plan(plan: BootstrapPlan) -> None:
    print(f"service:  {plan.endpoint}")
    print(f"provider: {plan.provider}")
    print(f"model:    {plan.selected_model}")
    print(json.dumps(provider_config(plan), indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args, pi_args = parser.parse_known_args(argv)
    if pi_args[:1] == ["--"]:
        pi_args = pi_args[1:]
    try:
        plan = derive_plan(args)
        if args.dry_run:
            print_plan(plan)
            return 0
        models_changed, settings_changed = configure_pi(
            plan,
            args.agent_dir,
            set_default=not args.no_default,
        )
        models_state = "updated" if models_changed else "current"
        settings_state = "updated" if settings_changed else "current"
        print(f"lm-based service: {plan.endpoint}")
        print(f"Pi provider:      {plan.provider}/{plan.selected_model}")
        print(f"Pi configuration: models {models_state}, settings {settings_state}")
        if args.configure_only:
            return 0
        if shutil.which("pi") is None:
            raise BootstrapError("pi is not installed or not on PATH")
        command = ["pi", "--provider", plan.provider, "--model", plan.selected_model, *pi_args]
        os.execvp(command[0], command)
    except BootstrapError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print("start a model with ./up <model-slug>, then rerun ./pi-local", file=sys.stderr)
        return 1
    return 0
