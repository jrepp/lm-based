from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from llama_swap.bin import ensure_binary, find_binary

PROJECT_ROOT = Path(__file__).parent.parent
MODELS_DIR = PROJECT_ROOT / "models"
DEFAULT_LISTEN = "127.0.0.1:8080"
DEFAULT_PORT_START = 10001


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


def _resolve_model_path(sidecar_path: Path) -> Path:
    import json
    with sidecar_path.open(encoding="utf-8") as f:
        rec = json.load(f)

    artifact = rec.get("artifact", {})
    launcher = rec.get("launcher", {})
    recommended_env = launcher.get("recommended_env", {})

    model_file = recommended_env.get("MODEL_FILE") or artifact.get("filename", "")
    local_path_raw = artifact.get("local_path", model_file)
    local_path = Path(local_path_raw)

    if local_path.is_absolute():
        return local_path
    project_relative = PROJECT_ROOT / local_path
    artifacts_relative = PROJECT_ROOT / "artifacts" / local_path
    return project_relative if project_relative.exists() else artifacts_relative


OURO_REPO_ROOT = Path("/Users/jrepp/d/ouro")


def _build_ouro_server_cmd(model_path: Path, port: int) -> str:
    venv_python = OURO_REPO_ROOT / ".venv" / "bin" / "python"
    server_file = OURO_REPO_ROOT / "server.py"
    if not venv_python.exists():
        venv_python = shutil.which("python") or "python"
    return (
        f"{venv_python} {server_file}"
        f" --port {port}"
        f" --host 127.0.0.1"
    )


def _build_llama_server_cmd(
    model_path: Path,
    profile: str,
    port: int,
) -> str:
    model_file = os.environ.get("MODEL_FILE", "")
    profile_env = os.environ.get("PROFILE", profile)

    cmd_parts = [
        shutil.which("llama-server") or "llama-server",
        f"--port {port}",
        f"--model '{model_path}'",
    ]

    common_flags = [
        "--flash-attn auto",
        "--ctx-size 262144",
        "--batch-size 2048",
        "--ubatch-size 512",
        "--parallel 1",
        "--threads 8",
        "--threads-batch 8",
        "--gpu-layers all",
        "--log-verbosity 3",
    ]

    if profile in ("qwen3-coder-next",):
        common_flags.extend([
            "--ctx-size 1048576",
            "--rope-scaling yarn",
            "--rope-scale 4.0",
            "--yarn-orig-ctx 262144",
            "--temperature 1.0",
            "--top-k 40",
            "--top-p 0.95",
            "--min-p 0.0",
            "--batch-size 1024",
            "--ubatch-size 256",
        ])

    if profile in ("gemma4",):
        common_flags.extend([
            "--ctx-size 32768",
            "--batch-size 512",
            "--ubatch-size 128",
        ])

    for flag in common_flags:
        cmd_parts.append(flag)

    return " ".join(cmd_parts)


def _sidecar_to_model_config(sidecar_path: Path, port: int) -> ModelConfig | None:
    import json
    with sidecar_path.open(encoding="utf-8") as f:
        rec = json.load(f)

    artifact = rec.get("artifact", {})
    model = rec.get("model", {})
    launcher = rec.get("launcher", {})
    recommended_env = launcher.get("recommended_env", {})
    download = rec.get("download", {})
    source = rec.get("source", {})

    slug = model.get("slug", "")
    if not slug:
        return None

    profile = recommended_env.get("PROFILE") or launcher.get("profile", "auto")
    model_file = recommended_env.get("MODEL_FILE") or artifact.get("filename", "")
    local_path_raw = artifact.get("local_path", model_file)
    local_path = Path(local_path_raw)

    if local_path.is_absolute():
        model_path = local_path
    else:
        project_relative = PROJECT_ROOT / local_path
        artifacts_relative = PROJECT_ROOT / "artifacts" / local_path
        model_path = project_relative if project_relative.exists() else artifacts_relative

    fmt = artifact.get("format", "gguf")
    is_gguf = fmt == "gguf"
    is_ouro = profile == "ouro"

    if is_ouro:
        cmd = _build_ouro_server_cmd(model_path, port)
    elif is_gguf:
        cmd = _build_llama_server_cmd(model_path, profile, port)
    else:
        return None

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


def build_config(models_dir: Path = MODELS_DIR) -> LlamaSwapConfig:
    cfg = LlamaSwapConfig()
    sidecars = sorted(models_dir.glob("*.json"))
    port = DEFAULT_PORT_START

    for sc in sidecars:
        mc = _sidecar_to_model_config(sc, port)
        if mc:
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