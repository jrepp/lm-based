from pathlib import Path
from typing import Literal

from pydantic import model_validator
from qwen_launcher.model_index import find_record_by_slug
from pydantic_settings import BaseSettings, SettingsConfigDict
from qwen_launcher.profiles import infer_profile, profile_defaults

_PROJECT_ROOT = Path(__file__).parent.parent


class ServerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
        env_file=_PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
    )

    llama_server_bin: str = "llama-server"
    model_dir: Path = _PROJECT_ROOT
    models_index_dir: Path = _PROJECT_ROOT / "models"
    model_slug: str | None = None
    model_file: str = "Qwen3.5-35B-A3B-Q4_K_M.gguf"
    model_path: Path | None = None
    profile: str = "auto"

    host: str = "127.0.0.1"
    port: int = 8001
    ctx_size: int | None = None
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
    presence_penalty: float | None = None
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
    cache_reuse: int | None = None
    api_key: str | None = None
    min_model_bytes: int = 20_000_000_000

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
            self.model_path = Path(
                artifact.get("local_path", str(self.model_dir / self.model_file))
            )
            if self.profile == "auto":
                self.profile = launcher.get("profile", self.profile)
            if self.alias is None:
                self.alias = record.get("model", {}).get("slug")

            if self.model_file == artifact.get("filename"):
                model_file_env = recommended_env.get("MODEL_FILE")
                if model_file_env:
                    self.model_file = model_file_env
            if self.profile == "auto":
                profile_env = recommended_env.get("PROFILE")
                if profile_env:
                    self.profile = profile_env

        return self

    @model_validator(mode="after")
    def apply_profile_defaults(self) -> "ServerSettings":
        if self.model_path is None:
            self.model_path = self.model_dir / self.model_file

        self.profile = infer_profile(self.model_path.name, self.profile)
        defaults = profile_defaults(self.profile, self.model_path.name)

        for field_name, default_value in defaults.items():
            if getattr(self, field_name) is None:
                setattr(self, field_name, default_value)

        if self.enable_repetition_guard and self.presence_penalty is None:
            self.presence_penalty = self.repetition_guard_presence_penalty

        return self
