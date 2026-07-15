from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).parent.parent
MODELS_DIR = PROJECT_ROOT / "models"
DEFAULT_LISTEN = "127.0.0.1:8080"
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


def _build_run_server_cmd(slug: str, port: int) -> str:
    worker_id = f"swap-{slug}"
    parts = [
        f"MODEL_SLUG={_shell_quote(slug)}",
        "HOST=127.0.0.1",
        f"PORT={port}",
        "RUN_MODE=swap_worker",
        f"SUPERVISOR_WORKER_ID={_shell_quote(worker_id)}",
        "ENABLE_RUN_CAPTURE=0",
        "./run-server.py",
    ]
    return " ".join(parts)


def _sidecar_to_model_config(sidecar_path: Path, port: int) -> ModelConfig | None:
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
    if fmt not in {"gguf", "safetensors"} and profile != "ouro":
        return None

    cmd = _build_run_server_cmd(slug, port)

    name = artifact.get("quantization") or ""

    return ModelConfig(
        model_id=slug,
        cmd=cmd,
        name=name,
        check_endpoint="/health",
        send_loading_state=True,
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
        d["models"] = {k: v.to_dict() for k, v in self.models.items()}
        return d


def _read_enabled_slugs(policy_path: Path | None = None) -> set[str] | None:
    """The 'hot' model slugs the operator declared available in serve-policy.yaml.

    Returns the enabled slug set, or None when there is no policy / no enabled
    list (meaning: no hot filter, include every model).
    """
    if policy_path is None:
        policy_path = PROJECT_ROOT / "serve-policy.yaml"
    try:
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    enabled = policy.get("models", {}).get("enabled")
    if not isinstance(enabled, list) or not enabled:
        return None
    return {str(slug) for slug in enabled}


def build_config(
    models_dir: Path = MODELS_DIR,
    hot_slugs: set[str] | None | object = _HOT_DEFAULT,
) -> LlamaSwapConfig:
    cfg = LlamaSwapConfig()
    sidecars = sorted(models_dir.glob("*.json"))

    if hot_slugs is _HOT_DEFAULT:
        hot: set[str] | None = _read_enabled_slugs()
    else:
        hot = hot_slugs  # None -> every model; a set -> filter to those slugs

    port = DEFAULT_PORT_START
    for sc in sidecars:
        mc = _sidecar_to_model_config(sc, port)
        if mc is None:
            continue
        if hot is not None and mc.model_id not in hot:
            continue
        cfg.models[mc.model_id] = mc
        port += 1

    return cfg


def config_to_yaml(cfg: LlamaSwapConfig) -> str:
    return yaml.dump(cfg.to_dict(), default_flow_style=False, sort_keys=False, allow_unicode=True)


def write_config(cfg: LlamaSwapConfig, path: Path | None = None) -> Path:
    if path is None:
        path = PROJECT_ROOT / "llama-swap.yaml"
    content = config_to_yaml(cfg)
    path.write_text(content, encoding="utf-8")
    return path
