import os
import re
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from lm_launcher.model_index import find_record_by_slug
from pydantic_settings import BaseSettings, SettingsConfigDict
from lm_launcher.profiles import infer_profile, profile_defaults

_PROJECT_ROOT = Path(__file__).parent.parent


def _read_project_python() -> str:
    """Default Python for backend ephemeral envs; follows .python-version."""
    version_file = _PROJECT_ROOT / ".python-version"
    try:
        return version_file.read_text().strip() or "3.14"
    except OSError:
        return "3.14"


def _discover_lan_ips() -> list[str]:
    ips: set[str] = set()
    try:
        result = subprocess.run(
            ["ip", "-4", "addr", "show"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                m = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", line)
                if m:
                    ip = m.group(1)
                    if ip not in ("127.0.0.1", "127.0.1.1") and not ip.startswith("169.254"):
                        ips.add(ip)
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    if not ips:
        try:
            result = subprocess.run(
                ["ifconfig"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    m = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", line)
                    if m:
                        ip = m.group(1)
                        if ip not in ("127.0.0.1", "127.0.1.1") and not ip.startswith("169.254"):
                            ips.add(ip)
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
    return sorted(ips)


class ServerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
        env_file=_PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
    )

    llama_server_bin: str = "llama-server"
    backend_python: str = _read_project_python()
    kev_repo_dir: Path | None = None
    kev_python: str = "3.13"
    mmproj: Path | None = None
    model_dir: Path = _PROJECT_ROOT / "artifacts"
    models_index_dir: Path = _PROJECT_ROOT / "models"
    model_slug: str | None = None
    model_file: str = ""
    model_path: Path | None = None
    mmproj: Path | None = None
    mlx_model: str | None = None
    profile: str = "auto"
    run_mode: str = "direct"

    host: str = "0.0.0.0"
    additional_hosts: str = ""
    port: int = 8001
    ctx_size: int | None = None
    # Native (training) context from the sidecar's model.context_length.
    model_context_length: int | None = None
    gpu_layers: str = "all"
    parallel: int | None = None
    threads: int | None = None
    threads_batch: int | None = None
    alias: str | None = None
    flash_attn: Literal["on", "off", "auto"] = "auto"
    cache_type_k: str | None = None
    cache_type_v: str | None = None
    log_verbosity: int | None = None
    batch_size: int | None = None
    ubatch_size: int | None = None
    temperature: float | None = None
    top_k: int | None = None
    top_p: float | None = None
    min_p: float | None = None
    max_tokens: int | None = None
    presence_penalty: float | None = None
    repetition_penalty: float | None = None
    enable_repetition_guard: bool = False
    repetition_guard_presence_penalty: float = 0.5
    poll: int | None = None
    slot_prompt_similarity: float | None = None

    enable_perf: bool = True
    enable_metrics: bool = True
    enable_slots: bool = True
    enable_log_timestamps: bool = True
    enable_log_prefix: bool = True
    enable_kv_offload: bool = True
    enable_mmap: bool = True
    enable_repack: bool = True
    enable_mlock: bool = False
    enable_swa_full: bool = False
    enable_cont_batching: bool = True
    enable_context_shift: bool = False
    enable_run_capture: bool = True

    log_file: Path | None = None
    run_dir_root: Path = _PROJECT_ROOT / "runs"
    run_name: str | None = None
    monitor_interval_sec: float = 1.0
    rope_scaling: str | None = None
    rope_scale: float | None = None
    rope_freq_base: float | None = None
    rope_freq_scale: float | None = None
    yarn_orig_ctx: int | None = None
    yarn_ext_factor: float | None = None
    yarn_attn_factor: float | None = None
    yarn_beta_slow: float | None = None
    yarn_beta_fast: float | None = None
    device: str | None = None
    cpu_moe: bool = False
    n_cpu_moe: int | None = None
    model_draft: Path | None = None
    ctx_size_draft: int | None = None
    gpu_layers_draft: str | None = None
    spec_type: str | None = None
    spec_draft_n_max: int | None = None
    cache_reuse: int | None = None
    api_key: str | None = None
    min_model_bytes: int = 0

    @model_validator(mode="after")
    def apply_model_index(self) -> "ServerSettings":
        if self.model_slug:
            record = find_record_by_slug(self.models_index_dir, self.model_slug)
            if record is None:
                available = ", ".join(
                    p.name for p in sorted(self.models_index_dir.glob("*.json"))
                )
                raise ValueError(
                    f"Unknown model_slug={self.model_slug!r}. Sidecars in index: {available}"
                )

            artifact = record.get("artifact", {})
            launcher = record.get("launcher", {})
            recommended_env = launcher.get("recommended_env", {})

            self.model_file = artifact.get("filename", self.model_file)
            local_path_raw = artifact.get(
                "local_path", str(self.model_dir / self.model_file)
            )
            local_path = Path(local_path_raw)
            if local_path.is_absolute():
                self.model_path = local_path
            else:
                project_relative = _PROJECT_ROOT / local_path
                artifacts_relative = self.model_dir / local_path
                self.model_path = (
                    project_relative if project_relative.exists() else artifacts_relative
                )
            if self.profile == "auto":
                self.profile = launcher.get("profile", self.profile)
            if self.alias is None:
                self.alias = record.get("model", {}).get("slug")
            native = record.get("model", {}).get("context_length")
            if self.model_context_length is None and isinstance(native, int) and native > 0:
                self.model_context_length = native

            if self.model_file == artifact.get("filename"):
                model_file_env = recommended_env.get("MODEL_FILE")
                if model_file_env:
                    self.model_file = model_file_env
            if self.profile == "auto":
                profile_env = recommended_env.get("PROFILE")
                if profile_env:
                    self.profile = profile_env
            if "backend_python" not in self.model_fields_set:
                backend_python_env = recommended_env.get("BACKEND_PYTHON")
                if backend_python_env:
                    self.backend_python = backend_python_env
            if self.mlx_model is None:
                mlx_model_env = recommended_env.get("MLX_MODEL")
                if mlx_model_env:
                    self.mlx_model = mlx_model_env
            if self.mmproj is None and recommended_env.get("MMPROJ"):
                projector = Path(recommended_env["MMPROJ"])
                if not projector.is_absolute():
                    project_relative = _PROJECT_ROOT / projector
                    artifacts_relative = self.model_dir / projector
                    projector = (
                        artifacts_relative
                        if not project_relative.exists() and artifacts_relative.exists()
                        else project_relative
                    )
                self.mmproj = projector

        self.llama_server_bin = os.path.expanduser(self.llama_server_bin)
        return self

    @model_validator(mode="after")
    def apply_profile_defaults(self) -> "ServerSettings":
        if self.model_path is None:
            self.model_path = self.model_dir / self.model_file

        self.profile = infer_profile(self.model_path.name, self.profile)
        defaults = profile_defaults(self.profile, self.model_path.name)

        # Read before applying defaults: setattr below also marks fields as set.
        explicit_ctx = "ctx_size" in self.model_fields_set
        for field_name, default_value in defaults.items():
            if getattr(self, field_name) is None:
                setattr(self, field_name, default_value)

        # llama-server caps the slot at the training context anyway; asking for more only
        # allocates KV cache that can never be used. An explicit CTX_SIZE is left alone.
        if (
            not explicit_ctx
            and self.model_context_length
            and self.ctx_size
            and self.ctx_size > self.model_context_length
        ):
            self.ctx_size = self.model_context_length

        if self.enable_repetition_guard and self.presence_penalty is None:
            self.presence_penalty = self.repetition_guard_presence_penalty

        if self.run_mode == "swap_worker" and "enable_run_capture" not in self.model_fields_set:
            self.enable_run_capture = False

        return self

    @property
    def all_hosts(self) -> list[str]:
        hosts = [self.host]
        if self.additional_hosts:
            for token in self.additional_hosts.split(","):
                token = token.strip()
                if not token:
                    continue
                if token == "+lan":
                    hosts.extend(_discover_lan_ips())
                else:
                    hosts.append(token)
        return hosts
