from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import urlparse
from typing import Any, Callable

from lm_launcher.profiles import profile_defaults
from lm_launcher.service_endpoints import swap_api_base


ROOT = Path(__file__).resolve().parent.parent
RUNTIME_SERVICES = ROOT / ".runtime" / "tmux" / "services"
PI_DIR = ROOT / "support" / "pi"
PI_CLI = PI_DIR / "node_modules" / ".bin" / "pi"
DEFAULT_AGENT_DIR = ROOT / ".runtime" / "pi" / "agent"
# Extensions pinned in support/pi/package.json and loaded from that install.
PI_PACKAGES = (
    PI_DIR / "node_modules" / "@narumitw" / "pi-goal",
    PI_DIR / "node_modules" / "pi-subagents",
)
# Repo-local extensions loaded by file path (not npm packages).
PI_EXTENSIONS = (
    PI_DIR / "extensions" / "llama-swap" / "index.ts",
    PI_DIR / "extensions" / "pdf-extract" / "index.ts",
    PI_DIR / "extensions" / "decide" / "index.ts",
)
# Keep the repo-managed Pi quiet: no version checks or install telemetry.
PI_ENV = {"PI_SKIP_VERSION_CHECK": "1", "PI_TELEMETRY": "0"}
DEFAULT_PROVIDER = "lm-based"
# Decision/classifier models (kev.serve) answer typed questions, not chat; keep them out of /model.
DECISION_PROFILES = frozenset({"mlx-kev"})
# Document OCR models take page images with fixed task prompts; they are not general chat models.
OCR_PROFILES = frozenset({"glm-ocr"})
NON_CHAT_PROFILES = DECISION_PROFILES | OCR_PROFILES

# OpenShell sandboxed launch (pi-local --sandbox): a microVM with default-deny
# egress whose only permitted destination is the host gateway address that
# reaches llama-swap, so the agent never sees host env vars, SSH keys, or the
# filesystem outside its workspace.
SANDBOX_NAME = "pi-local"
SANDBOX_NODE_VERSION = "v22.21.1"
DEFAULT_SANDBOX_GATEWAY = "192.168.127.254"
SANDBOX_NODE_BIN = f"/sandbox/.local/node-{SANDBOX_NODE_VERSION}-linux-arm64/bin/node"
ZERO_COST = {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}


class BootstrapError(RuntimeError):
    """A user-actionable bootstrap failure."""

    hint = "start llama-swap with ./up swap (or a single model with ./up <model-slug>), then rerun ./pi-local"


class PiInstallError(BootstrapError):
    """The repo-pinned Pi install is missing or incomplete."""

    hint = "install the pinned Pi with: just pi-install"


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
    # llama-swap only: model id -> process state ("ready", "starting", ...) or "unloaded".
    swap_states: dict[str, str] | None = None
    # Decision models for the decide extension. models.json cannot declare classifier
    # models (Pi treats every entry as chat), so they travel in LM_BASED_CLASSIFIERS and
    # support/pi/extensions/decide registers them as their own provider.
    classifiers: tuple[dict[str, Any], ...] = ()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bootstrap Pi against the verified, running lm-based service.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        # Unknown flags pass through to Pi; prefix matching would turn Pi's --mode into --model.
        allow_abbrev=False,
        epilog=(
            "The bootstrap reads tmux shim ownership, verifies /v1/models, merges an\n"
            "lm-based provider into .runtime/pi/agent/models.json, and then launches the\n"
            "Pi pinned in support/pi with the goal and subagent extensions.\n"
            "Arguments it does not recognize are forwarded to Pi.\n"
            "\n"
            "Examples:\n"
            "  ./pi-local                  # llama-swap if it is up, else the tmux service\n"
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
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--swap",
        action="store_true",
        help="require the llama-swap proxy (default: use it when /running answers, else tmux discovery)",
    )
    source.add_argument(
        "--tmux",
        action="store_true",
        help="skip llama-swap and use the service registered in the tmux session",
    )
    parser.add_argument(
        "--sandbox",
        action="store_true",
        help="run Pi inside an OpenShell sandbox (isolated filesystem and env; egress limited to llama-swap)",
    )
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


def swap_root(endpoint: str) -> str:
    return endpoint.rstrip("/").removesuffix("/v1")


def swap_model_states(
    endpoint: str,
    api_ids: list[str],
    timeout: float,
    *,
    opener: Callable[..., object] = urllib.request.urlopen,
) -> dict[str, str]:
    """Join llama-swap /v1/models with /running: every model gets its load state."""
    url = f"{swap_root(endpoint)}/running"
    try:
        with opener(urllib.request.Request(url, headers={"Accept": "application/json"}), timeout=timeout) as response:  # type: ignore[attr-defined]
            payload = json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise BootstrapError(f"{url} is not a healthy llama-swap endpoint: {exc}") from exc
    running = payload.get("running") if isinstance(payload, dict) else None
    if not isinstance(running, list):
        raise BootstrapError(f"{url} returned an invalid llama-swap response")
    states = {model_id: "unloaded" for model_id in api_ids}
    for entry in running:
        if isinstance(entry, dict) and isinstance(entry.get("model"), str):
            states[entry["model"]] = str(entry.get("state") or "unknown")
    return states


def live_context_window(
    props_url: str,
    timeout: float,
    *,
    opener: Callable[..., object] = urllib.request.urlopen,
) -> int | None:
    """n_ctx a running llama-server actually allocated, or None when it cannot say."""
    try:
        with opener(urllib.request.Request(props_url, headers={"Accept": "application/json"}), timeout=timeout) as response:  # type: ignore[attr-defined]
            payload = json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    settings = payload.get("default_generation_settings")
    n_ctx = settings.get("n_ctx") if isinstance(settings, dict) else payload.get("n_ctx")
    return n_ctx if isinstance(n_ctx, int) and n_ctx > 0 else None


def apply_live_context(
    state: ServiceState,
    sidecars: tuple[Sidecar, ...],
    swap_states: dict[str, str] | None,
    timeout: float,
    *,
    probe: Callable[[str, float], int | None] = live_context_window,
) -> tuple[Sidecar, ...]:
    """Lower each loaded model's context window to what its server allocated.

    Profiles state the requested --ctx-size; llama-server can allocate less (for example
    when it caps at the model's training context). Pi compacts based on contextWindow, so
    an overstated value lets requests overflow. Only loaded models are probed: asking
    llama-swap about an unloaded one would start it.
    """
    adjusted: list[Sidecar] = []
    for sidecar in sidecars:
        url = None
        if swap_states is not None and swap_states.get(sidecar.slug) == "ready":
            url = f"{swap_root(state.endpoint)}/upstream/{sidecar.slug}/props"
        elif swap_states is None and state.model_slugs == (sidecar.slug,):
            url = f"{swap_root(state.endpoint)}/props"
        live = probe(url, timeout) if url else None
        if live is not None and live < sidecar.context_window:
            print(
                f"note: {sidecar.slug} serves {live} tokens of context "
                f"(profile requests {sidecar.context_window}); Pi will use {live}",
                file=sys.stderr,
            )
            sidecar = replace(sidecar, context_window=live)
        adjusted.append(sidecar)
    return tuple(adjusted)


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
        if match is not None and match not in resolved and match.profile not in NON_CHAT_PROFILES:
            resolved.append(match)
    if not resolved:
        raise BootstrapError("none of the endpoint models match local chat-model sidecar metadata")
    return tuple(resolved)


def resolve_classifiers(api_ids: list[str], sidecars: dict[str, Sidecar]) -> tuple[Sidecar, ...]:
    resolved: list[Sidecar] = []
    for api_id in api_ids:
        match = next((sidecar for sidecar in sidecars.values() if api_id_matches_sidecar(api_id, sidecar)), None)
        if match is not None and match not in resolved and match.profile in DECISION_PROFILES:
            resolved.append(match)
    return tuple(resolved)


def pi_classifier(sidecar: Sidecar, swap_endpoint: str) -> dict[str, Any]:
    # llama-swap only routes OpenAI paths by model; /upstream/<slug> passes /v1/systemone through.
    return {
        "id": sidecar.slug,
        "name": f"{sidecar.name} (lm-based decision)",
        "type": "classifier",
        "api": "typesafe-system-one",
        "baseUrl": f"{swap_root(swap_endpoint)}/upstream/{sidecar.slug}/v1",
        "input": ["text"],
        "contextWindow": sidecar.context_window,
        "cost": dict(ZERO_COST),
    }


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
    swap_states: dict[str, str] | None = None,
    previous_model: str | None = None,
    classifiers: tuple[Sidecar, ...] = (),
) -> BootstrapPlan:
    models = tuple(pi_model(sidecar) for sidecar in sidecars)
    model_ids = [model["id"] for model in models]
    loaded = [model_id for model_id in model_ids if (swap_states or {}).get(model_id) == "ready"]
    if requested_model:
        if requested_model not in model_ids:
            raise BootstrapError(f"model {requested_model!r} is not exposed by the running service")
        selected = requested_model
    elif len(model_ids) == 1:
        selected = model_ids[0]
    elif loaded:
        # Start on whatever llama-swap already holds rather than forcing a swap.
        selected = loaded[0]
    elif swap_states is not None:
        # Nothing loaded: llama-swap loads on demand, so resume the last model or take the first.
        selected = previous_model if previous_model in model_ids else model_ids[0]
    else:
        raise BootstrapError(f"choose a running model with --model ({', '.join(model_ids)})")
    return BootstrapPlan(
        provider=provider,
        endpoint=state.endpoint,
        models=models,
        selected_model=selected,
        swap_states=swap_states,
        classifiers=tuple(pi_classifier(sidecar, state.endpoint) for sidecar in classifiers),
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


def merge_packages(existing: object, managed: tuple[Path, ...], owned_root: Path = PI_DIR) -> list[Any]:
    """User entries stay; entries under owned_root are replaced by the current managed set,
    so an extension removed from the repo stops loading."""
    owned = str(owned_root) + os.sep
    packages = [
        entry
        for entry in (existing if isinstance(existing, list) else [])
        if not (isinstance(entry, str) and entry.startswith(owned))
    ]
    for package in managed:
        if str(package) not in packages:
            packages.append(str(package))
    return packages


def configure_pi(
    plan: BootstrapPlan,
    agent_dir: Path,
    *,
    set_default: bool,
    packages: tuple[Path, ...] = PI_PACKAGES,
    extensions: tuple[Path, ...] = PI_EXTENSIONS,
) -> tuple[bool, bool]:
    models_path = agent_dir / "models.json"
    models_config = read_json_object(models_path)
    providers = models_config.setdefault("providers", {})
    if not isinstance(providers, dict):
        raise BootstrapError(f"expected providers to be an object in {models_path}")
    providers[plan.provider] = provider_config(plan)
    models_changed = atomic_write_json(models_path, models_config)

    settings_path = agent_dir / "settings.json"
    settings = read_json_object(settings_path)
    settings["packages"] = merge_packages(settings.get("packages"), packages)
    settings["extensions"] = merge_packages(settings.get("extensions"), extensions)
    settings["enableInstallTelemetry"] = False
    if set_default:
        settings["defaultProvider"] = plan.provider
        settings["defaultModel"] = plan.selected_model
    settings_changed = atomic_write_json(settings_path, settings)
    return models_changed, settings_changed


def check_pi_install(
    cli: Path = PI_CLI,
    packages: tuple[Path, ...] = PI_PACKAGES + PI_EXTENSIONS,
) -> None:
    missing = [path for path in (cli, *packages) if not path.exists()]
    if missing:
        names = ", ".join(str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path) for path in missing)
        raise PiInstallError(f"pinned Pi install is incomplete (missing {names})")


def pi_environment(
    agent_dir: Path,
    base: dict[str, str] | None = None,
    plan: BootstrapPlan | None = None,
) -> dict[str, str]:
    env = dict(os.environ if base is None else base)
    env.update(PI_ENV)
    env["PI_CODING_AGENT_DIR"] = str(agent_dir.resolve())
    if plan is not None and plan.swap_states is not None:
        # Enables the llama-swap status extension (support/pi/extensions/llama-swap).
        env["LM_BASED_SWAP_URL"] = swap_root(plan.endpoint)
        env["LM_BASED_PROVIDER"] = plan.provider
    if plan is not None and plan.classifiers:
        env["LM_BASED_CLASSIFIERS"] = json.dumps(list(plan.classifiers))
    return env


def previous_default_model(agent_dir: Path, provider: str) -> str | None:
    try:
        settings = read_json_object(agent_dir / "settings.json")
    except BootstrapError:
        return None
    model = settings.get("defaultModel")
    return model if settings.get("defaultProvider") == provider and isinstance(model, str) else None


def swap_service(timeout: float) -> tuple[ServiceState, list[str], dict[str, str]]:
    state = ServiceState(services=frozenset({"llama-swap"}), model_slugs=(), endpoint=swap_api_base())
    api_ids = endpoint_model_ids(state.endpoint, timeout)
    return state, api_ids, swap_model_states(state.endpoint, api_ids, timeout)


def derive_plan(args: argparse.Namespace) -> BootstrapPlan:
    sidecars = load_sidecars()
    swap_states = None
    if args.swap:
        state, api_ids, swap_states = swap_service(args.timeout)
    else:
        try:
            if args.tmux:
                raise BootstrapError("llama-swap skipped")
            # llama-swap answering /running is positive identification, not a port guess.
            state, api_ids, swap_states = swap_service(args.timeout)
        except BootstrapError:
            state = service_state(args.session, running_services(args.session))
            api_ids = endpoint_model_ids(state.endpoint, args.timeout)
            if "llama-swap" in state.services and not state.model_slugs:
                swap_states = swap_model_states(state.endpoint, api_ids, args.timeout)
    resolved = apply_live_context(state, resolve_sidecars(state, api_ids, sidecars), swap_states, args.timeout)
    classifiers = resolve_classifiers(api_ids, sidecars) if swap_states is not None else ()
    previous = previous_default_model(args.agent_dir, args.provider)
    return build_plan(args.provider, args.model, state, resolved, swap_states, previous, classifiers)


def print_swap_states(plan: BootstrapPlan) -> None:
    if plan.swap_states is None:
        return
    registered = {model["id"] for model in plan.models}
    classifiers = {model["id"] for model in plan.classifiers}
    sidecars = load_sidecars()
    print("llama-swap models:")
    for model_id, state in plan.swap_states.items():
        mark = "●" if state == "ready" else "○" if state == "unloaded" else "◐"
        note = ""
        if model_id in classifiers:
            note = "  (decision model; classifier for decide_records)"
        elif model_id not in registered:
            profile = sidecars[model_id].profile if model_id in sidecars else None
            kind = "decision model" if profile in DECISION_PROFILES else "OCR model" if profile in OCR_PROFILES else "no sidecar"
            note = f"  ({kind}; not in /model)"
        current = "  <- selected" if model_id == plan.selected_model else ""
        print(f"  {mark} {model_id:<32} {state}{current}{note}")


def print_plan(plan: BootstrapPlan) -> None:
    print(f"service:  {plan.endpoint}")
    print(f"provider: {plan.provider}")
    print(f"model:    {plan.selected_model}")
    print_swap_states(plan)
    print(json.dumps(provider_config(plan), indent=2))
    if plan.classifiers:
        print("classifiers (LM_BASED_CLASSIFIERS):")
        print(json.dumps(list(plan.classifiers), indent=2))


def sandbox_gateway() -> str:
    """Host-side address a sandbox uses to reach services on this host."""
    return os.environ.get("LM_BASED_SANDBOX_GATEWAY", DEFAULT_SANDBOX_GATEWAY)


def render_sandbox_policy(plan: BootstrapPlan, dest: Path) -> Path:
    port = urlparse(plan.endpoint).port or 8081
    gateway = sandbox_gateway()
    policy = (
        "version: 1\n"
        "network_policies:\n"
        "  lm-based-swap:\n"
        "    binaries:\n"
        f"      - {{path: {SANDBOX_NODE_BIN}}}\n"
        "    endpoints:\n"
        f"      - {{host: {gateway}, port: {port}, allowed_ips: [\"{gateway}/32\"]}}\n"
        "  setup-npm:\n"
        "    binaries:\n"
        f"      - {{path: {SANDBOX_NODE_BIN}}}\n"
        "    endpoints:\n"
        "      - {host: registry.npmjs.org, ports: [443]}\n"
        f"      - {{host: {gateway}, port: {port}, allowed_ips: [\"{gateway}/32\"]}}\n"
        f"      - {{host: {gateway}, port: {port}, allowed_ips: [\"{gateway}/32\"]}}\n"
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(policy, encoding="utf-8")
    return dest


def sandbox_agent_dir(args: argparse.Namespace, plan: BootstrapPlan) -> Path:
    """Copy the configured agent dir, pointing providers at the sandbox gateway."""
    import shutil as _shutil

    port = urlparse(plan.endpoint).port or 8081
    source, dest = args.agent_dir, ROOT / ".runtime" / "pi" / "agent-sandbox"
    if dest.exists():
        _shutil.rmtree(dest)
    _shutil.copytree(source, dest)
    for file in dest.rglob("*"):
        if file.is_file() and file.suffix in {".json", ".jsonc", ".toml", ".yaml"}:
            text = file.read_text(encoding="utf-8")
            if f"http://127.0.0.1:{port}" in text:
                file.write_text(
                    text.replace(f"http://127.0.0.1:{port}", f"http://{sandbox_gateway()}:{port}"),
                    encoding="utf-8",
                )
    return dest


def run_openshell(*args: str, timeout: float = 120, check: bool = True, capture: bool = True) -> subprocess.CompletedProcess[str]:
    # `check` mirrors subprocess.run's signature for call-site readability; the
    # CompletedProcess returncode is always inspected by the caller instead.
    # capture=False streams output (upload progress bars) at the cost of not
    # being able to inspect stderr afterwards.
    del check
    openshell = shutil.which("openshell")
    if openshell is None:
        error = BootstrapError("openshell CLI not found on PATH")
        error.hint = "install OpenShell: curl -LsS https://raw.githubusercontent.com/NVIDIA/OpenShell/main/install.sh | sh"
        raise error
    try:
        return subprocess.run(
            [openshell, *args],
            capture_output=capture,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        error = BootstrapError(f"openshell {' '.join(args[:2])} timed out after {timeout:.0f}s")
        error.hint = "the sandbox may be wedged; rerun ./pi-local --sandbox to recreate it"
        raise error from exc


def wait_sandbox_ready(timeout_s: float = 90) -> bool:
    # `sandbox get` can report Phase: Provisioning even for a working sandbox,
    # so readiness is probed with a trivial exec instead of the phase string.
    # A sandbox in phase Error is never going to become ready: return False so
    # the caller can recreate it.
    import time

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        probe = run_openshell(
            "sandbox", "exec", "-n", SANDBOX_NAME, "--", "true", check=False, timeout=30
        )
        if probe.returncode == 0:
            return True
        if "phase: error" in (probe.stdout + probe.stderr).lower():
            return False
        time.sleep(3)
    return False


def ensure_sandbox(plan: BootstrapPlan, args: argparse.Namespace, retry: bool = True) -> None:
    policy = render_sandbox_policy(plan, ROOT / ".runtime" / "pi" / "openshell-policy.yaml")
    print("sandbox: checking for an existing OpenShell sandbox ...", flush=True)
    probe = run_openshell("sandbox", "get", SANDBOX_NAME, check=False, timeout=30)
    if probe.returncode != 0:
        print(f"sandbox: creating {SANDBOX_NAME} (first run takes ~a minute) ...", flush=True)
        created = run_openshell(
            "sandbox", "create", "--name", SANDBOX_NAME, "--policy", str(policy), timeout=180
        )
        if created.returncode != 0:
            error = BootstrapError(f"sandbox create failed: {created.stderr.strip() or created.stdout.strip()}")
            error.hint = "inspect the gateway with: openshell doctor"
            raise error
    else:
        print("sandbox: refreshing policy ...", flush=True)
        # Network rules are live-updatable; keep them in sync with the policy.
        run_openshell("policy", "set", SANDBOX_NAME, "--policy", str(policy), "--wait", timeout=90)
    print("sandbox: waiting for readiness ...", flush=True)
    if not wait_sandbox_ready():
        if not retry:
            raise BootstrapError(f"sandbox {SANDBOX_NAME} is in phase Error and did not recover")
        # A wedged sandbox (e.g. an interrupted upload, restart policy never)
        # only recovers by recreation; the workspace is rebuilt from the host.
        print("sandbox: wedged; recreating ...", flush=True)
        run_openshell("sandbox", "delete", SANDBOX_NAME, check=False)
        return ensure_sandbox(plan, args, retry=False)

    workspace = Path.cwd()
    print("sandbox: syncing workspace, Pi install, and agent config ...", flush=True)
    pi_provisioned = run_openshell(
        "sandbox", "exec", "-n", SANDBOX_NAME, "--",
        "bash", "-c", "[ -x /sandbox/support/pi/node_modules/.bin/pi ]", check=False, timeout=30,
    ).returncode == 0
    # Upload nests <source basename> under <dest>: support/pi lands at
    # /sandbox/support/pi, the workspace at /sandbox/<launch-dir-name>.
    uploads = [
        # (source, dest, no_git_ignore): the workspace honors .gitignore (it
        # excludes model binaries and runs/); only the agent dir lives under a
        # gitignored path and needs the override.
        (workspace, "/sandbox", False),
        (ROOT / "support" / "pi", "/sandbox/support", True),
        (sandbox_agent_dir(args, plan), "/sandbox", True),
    ]
    for source, dest, no_ignore in uploads:
        print(f"sandbox: uploading {source} -> {dest} ...", flush=True)
        args_extra = ["--no-git-ignore"] if no_ignore else []
        result = run_openshell(
            "sandbox", "upload", SANDBOX_NAME, str(source), dest, *args_extra,
            timeout=600,
        )
        if result.returncode != 0:
            detail = (result.stderr or "").strip() or (result.stdout or "").strip() or "(see streamed output above)"
            error = BootstrapError(f"sandbox upload of {source} failed: {detail}")
            error.hint = "check the sandbox is running: openshell sandbox list"
            raise error

    pi_provisioned = run_openshell(
        "sandbox", "exec", "-n", SANDBOX_NAME, "--",
        "bash", "-c", "[ -x /sandbox/support/pi/node_modules/.bin/pi ]", check=False, timeout=30,
    ).returncode == 0
    node_ready = run_openshell(
        "sandbox", "exec", "-n", SANDBOX_NAME, "--",
        "bash", "-c", f"[ -x {SANDBOX_NODE_BIN} ]", check=False, timeout=30,
    )
    if node_ready.returncode != 0:
        print(f"sandbox: installing node {SANDBOX_NODE_VERSION} ...", flush=True)
        tar_path = ROOT / ".runtime" / "pi" / f"node-{SANDBOX_NODE_VERSION}-linux-arm64.tar.gz"
        if not tar_path.is_file():
            url = f"https://nodejs.org/dist/{SANDBOX_NODE_VERSION}/node-{SANDBOX_NODE_VERSION}-linux-arm64.tar.gz"
            tar_path.parent.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(url, tar_path)
        run_openshell("sandbox", "upload", SANDBOX_NAME, str(tar_path), "/sandbox/node.tgz", "--no-git-ignore", timeout=300)
        extract = run_openshell(
            "sandbox", "exec", "-n", SANDBOX_NAME, "--",
            "bash", "-c",
            "mkdir -p ~/.local && tar -xz -C ~/.local -f /sandbox/node.tgz", timeout=120,
        )
        if extract.returncode != 0:
            error = BootstrapError(f"node extract failed in sandbox: {extract.stderr.strip()}")
            error.hint = "inspect with: openshell logs " + SANDBOX_NAME
            raise error
    if not pi_provisioned:
        # support/pi uploads without node_modules (gitignored); install the
        # pinned tree in-sandbox against the lockfile. npm runs as node, so
        # the setup-npm network rule keys on the node binary path.
        print("sandbox: npm ci for the pinned Pi (one-time per sandbox) ...", flush=True)
        npm_ci = run_openshell(
            "sandbox", "exec", "-n", SANDBOX_NAME, "--workdir", "/sandbox/support/pi",
            "--", "bash", "-c",
            f"export PATH=$HOME/.local/node-{SANDBOX_NODE_VERSION}-linux-arm64/bin:$PATH && "
            "npm ci --no-fund --no-audit",
            timeout=600, capture=False,
        )
        if npm_ci.returncode != 0:
            error = BootstrapError("npm ci failed inside the sandbox")
            error.hint = "inspect with: openshell logs " + SANDBOX_NAME
            raise error


def sandbox_command(plan: BootstrapPlan, pi_args: list[str]) -> list[str]:
    port = urlparse(plan.endpoint).port or 8081
    workspace = Path.cwd()
    inner = shlex.join([
        "/sandbox/support/pi/node_modules/.bin/pi",
        "--provider", plan.provider,
        "--model", plan.selected_model,
        *pi_args,
    ])
    script = (
        f"export PATH=$HOME/.local/node-{SANDBOX_NODE_VERSION}-linux-arm64/bin:$PATH "
        f"PI_CODING_AGENT_DIR=/sandbox/agent-sandbox PI_SKIP_VERSION_CHECK=1 PI_TELEMETRY=0 "
        f"LM_BASED_SWAP_URL=http://{sandbox_gateway()}:{port} "
        f"LM_BASED_PROVIDER={shlex.quote(plan.provider)} && "
        f"cd /sandbox/{workspace.name} 2>/dev/null || cd /sandbox; "
        f"exec node {inner}"
    )
    return [
        "sandbox", "exec", "-n", SANDBOX_NAME,
        "--workdir", "/sandbox",
        "--", "bash", "-c", script,
    ]


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args, pi_args = parser.parse_known_args(argv)
    if pi_args[:1] == ["--"]:
        pi_args = pi_args[1:]
    try:
        if not args.dry_run:
            check_pi_install()
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
        print(f"Pi agent dir:     {args.agent_dir}")
        print_swap_states(plan)
        if args.configure_only:
            return 0
        if args.sandbox:
            ensure_sandbox(plan, args)
            os.execvp("openshell", ["openshell", *sandbox_command(plan, pi_args)])
        command = [str(PI_CLI), "--provider", plan.provider, "--model", plan.selected_model, *pi_args]
        os.execve(command[0], command, pi_environment(args.agent_dir, plan=plan))
    except BootstrapError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print(exc.hint, file=sys.stderr)
        return 1
    return 0
