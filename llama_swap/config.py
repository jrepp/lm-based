from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from lm_launcher.artifacts import artifact_present
from lm_launcher.policy import enabled_slugs, load_policy

PROJECT_ROOT = Path(__file__).parent.parent
MODELS_DIR = PROJECT_ROOT / "models"
DEFAULT_PORT_START = 10001
_HOT_DEFAULT = object()


@dataclass
class ModelConfig:
    model_id: str
    cmd: str
    name: str = ""
    description: str = ""
    proxy: str = ""
    check_endpoint: str = "/health"
    ttl: int = 0
    unlisted: bool = False
    env: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    filters_strip_params: str = ""
    filters_set_params: dict[str, Any] = field(default_factory=dict)
    concurrency_limit: int = 0
    send_loading_state: bool = True
    use_model_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"cmd": self.cmd}
        if self.name:
            d["name"] = self.name
        if self.description:
            d["description"] = self.description
        if self.proxy:
            d["proxy"] = self.proxy
        if self.check_endpoint != "/health":
            d["checkEndpoint"] = self.check_endpoint
        if self.ttl > 0:
            d["ttl"] = self.ttl
        if self.unlisted:
            d["unlisted"] = True
        if self.env:
            d["env"] = self.env
        if self.aliases:
            d["aliases"] = self.aliases
        if self.metadata:
            d["metadata"] = self.metadata
        if self.filters_strip_params:
            d.setdefault("filters", {})["stripParams"] = self.filters_strip_params
        if self.filters_set_params:
            d.setdefault("filters", {})["setParams"] = self.filters_set_params
        if self.concurrency_limit > 0:
            d["concurrencyLimit"] = self.concurrency_limit
        if not self.send_loading_state:
            d["sendLoadingState"] = False
        if self.use_model_name:
            d["useModelName"] = self.use_model_name
        return d


def _shell_quote(value: str) -> str:
    if not value:
        return "''"
    return "'" + value.replace("'", """'"'"'""") + "'"


def _build_run_server_cmd(slug: str) -> str:
    worker_id = f"swap-{slug}"
    inner = " ".join(
        [
            f"MODEL_SLUG={_shell_quote(slug)}",
            "HOST=127.0.0.1",
            "PORT=${PORT}",
            "RUN_MODE=swap_worker",
            f"SUPERVISOR_WORKER_ID={_shell_quote(worker_id)}",
            "ENABLE_RUN_CAPTURE=0",
            "./run-server.py",
        ]
    )
    # llama-swap execs cmd directly (no shell), so the env-prefix form must
    # be wrapped; ${PORT} is provided by llama-swap in the child's env.
    return f"sh -c {_shell_quote(inner)}"


def _sidecar_to_model_config(sidecar_path: Path) -> ModelConfig | None:
    with sidecar_path.open(encoding="utf-8") as f:
        rec = json.load(f)

    artifact = rec.get("artifact", {})
    model = rec.get("model", {})
    launcher = rec.get("launcher", {})
    recommended_env = launcher.get("recommended_env", {})

    slug = model.get("slug", "")
    if not slug:
        return None

    profile = recommended_env.get("PROFILE") or launcher.get("profile", "auto")
    fmt = artifact.get("format", "gguf")
    if (
        fmt not in {"gguf", "safetensors", "mlx"}
        and profile != "ouro"
        and not profile.endswith("-mlx")
    ):
        return None

    cmd = _build_run_server_cmd(slug)

    name = artifact.get("quantization") or ""

    # kev.serve (decision models) has no /health route; /v1/models is its
    # liveness endpoint. mlx_lm.server keeps the default /health.
    check_endpoint = "/v1/models" if profile == "mlx-kev" else "/health"

    # llama-swap returns metadata in /v1/models under meta.llamaswap, so clients can
    # tell chat models from decision/OCR models without reading the sidecars.
    metadata = {"kind": model.get("kind", "chat")}
    if isinstance(model.get("context_length"), int):
        metadata["context_length"] = model["context_length"]

    return ModelConfig(
        model_id=slug,
        cmd=cmd,
        name=name,
        check_endpoint=check_endpoint,
        send_loading_state=True,
        metadata=metadata,
    )


@dataclass
class LlamaSwapConfig:
    health_check_timeout: int = 120
    log_level: str = "info"
    log_to_stdout: str = "proxy"
    start_port: int = DEFAULT_PORT_START
    send_loading_state: bool = True
    include_aliases_in_list: bool = False
    global_ttl: int = 0
    macros: dict[str, Any] = field(default_factory=dict)
    api_keys: list[str] = field(default_factory=list)
    models: dict[str, ModelConfig] = field(default_factory=dict)
    matrix: dict[str, Any] = field(default_factory=dict)
    routing: dict[str, Any] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)  # enabled but not downloaded

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "healthCheckTimeout": self.health_check_timeout,
            "logLevel": self.log_level,
            "logToStdout": self.log_to_stdout,
            "startPort": self.start_port,
            "sendLoadingState": self.send_loading_state,
            "includeAliasesInList": self.include_aliases_in_list,
            "globalTTL": self.global_ttl,
        }
        if self.macros:
            d["macros"] = self.macros
        if self.api_keys:
            d["apiKeys"] = self.api_keys
        if self.matrix:
            d["matrix"] = self.matrix
        if self.routing:
            d["routing"] = self.routing
        d["models"] = {k: v.to_dict() for k, v in self.models.items()}
        return d


def _policy(policy_path: Path | None = None) -> dict[str, Any]:
    return load_policy(policy_path if policy_path is not None else PROJECT_ROOT / "serve-policy.yaml")


def _read_enabled_slugs(policy_path: Path | None = None) -> set[str] | None:
    """The 'hot' model slugs the operator declared available in serve-policy.yaml.

    Returns the enabled slug set, or None when there is no policy / no enabled
    list (meaning: no hot filter, include every model).
    """
    return set(enabled_slugs(_policy(policy_path))) or None


def _read_policy_routing(policy_path: Path | None = None) -> dict[str, Any]:
    """Operator-declared llama-swap routing (groups/matrix) from serve-policy.yaml.

    Passed through verbatim; an empty dict means llama-swap's default
    (one model at a time instance-wide).
    """
    policy = _policy(policy_path)
    routing = policy.get("routing") or policy.get("swap", {}).get("routing")
    return routing if isinstance(routing, dict) else {}


def _require_local_artifact(policy_path: Path | None = None) -> bool:
    return bool(_policy(policy_path).get("policy", {}).get("require_local_artifact", False))


def _prune_routing(routing: dict[str, Any], served: set[str]) -> dict[str, Any]:
    """Drop group members that are not served; llama-swap rejects unknown members."""
    groups = routing.get("router", {}).get("settings", {}).get("groups")
    if not isinstance(groups, dict):
        return routing
    pruned: dict[str, Any] = {}
    for name, group in groups.items():
        members = [m for m in group.get("members", []) if m in served]
        if members:
            pruned[name] = {**group, "members": members}
    settings = {**routing["router"]["settings"], "groups": pruned}
    return {**routing, "router": {**routing["router"], "settings": settings}}


def build_config(
    models_dir: Path = MODELS_DIR,
    hot_slugs: set[str] | None | object = _HOT_DEFAULT,
    require_artifacts: bool | None = None,
) -> LlamaSwapConfig:
    """llama-swap config for the enabled sidecars.

    With require_artifacts (default: the policy's require_local_artifact), enabled
    models whose weights are not on disk are left out and listed in cfg.skipped, so
    llama-swap only advertises models that can load.
    """
    cfg = LlamaSwapConfig()
    sidecars = sorted(models_dir.glob("*.json"))
    routing = _read_policy_routing()

    if hot_slugs is _HOT_DEFAULT:
        hot: set[str] | None = _read_enabled_slugs()
    else:
        hot = hot_slugs  # None -> every model; a set -> filter to those slugs
    if require_artifacts is None:
        require_artifacts = _require_local_artifact()
    root = models_dir.parent

    for sc in sidecars:
        mc = _sidecar_to_model_config(sc)
        if mc is None:
            continue
        if hot is not None and mc.model_id not in hot:
            continue
        if require_artifacts and not artifact_present(json.loads(sc.read_text(encoding="utf-8")), root):
            cfg.skipped.append(mc.model_id)
            continue
        cfg.models[mc.model_id] = mc

    cfg.routing = _prune_routing(routing, set(cfg.models)) if cfg.skipped else routing
    return cfg


def config_to_yaml(cfg: LlamaSwapConfig) -> str:
    return yaml.dump(cfg.to_dict(), default_flow_style=False, sort_keys=False, allow_unicode=True)


def write_config(cfg: LlamaSwapConfig, path: Path | None = None) -> Path:
    if path is None:
        path = PROJECT_ROOT / "llama-swap.yaml"
    content = config_to_yaml(cfg)
    path.write_text(content, encoding="utf-8")
    return path
