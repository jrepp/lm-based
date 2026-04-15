import shutil
import sys
from pathlib import Path

from lm_launcher.run_capture import run_with_capture
from lm_launcher.settings import ServerSettings


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def add_arg(args: list[str], flag: str, value: object | None) -> None:
    if value is not None:
        args.extend([flag, str(value)])


def build_args(settings: ServerSettings) -> list[str]:
    args = [
        settings.llama_server_bin,
        "--model",
        str(settings.model_path),
        "--host",
        settings.host,
        "--port",
        str(settings.port),
        "--ctx-size",
        str(settings.ctx_size),
        "--batch-size",
        str(settings.batch_size),
        "--ubatch-size",
        str(settings.ubatch_size),
        "--gpu-layers",
        settings.gpu_layers,
        "--parallel",
        str(settings.parallel),
        "--threads",
        str(settings.threads),
        "--threads-batch",
        str(settings.threads_batch),
        "--poll",
        str(settings.poll),
        "--cache-type-k",
        str(settings.cache_type_k),
        "--cache-type-v",
        str(settings.cache_type_v),
        "--alias",
        str(settings.alias),
        "--flash-attn",
        settings.flash_attn,
        "--verbosity",
        str(settings.log_verbosity),
        "--slot-prompt-similarity",
        str(settings.slot_prompt_similarity),
    ]

    add_arg(args, "--api-key", settings.api_key)
    add_arg(args, "--device", settings.device)
    add_arg(args, "--temp", settings.temperature)
    add_arg(args, "--top-k", settings.top_k)
    add_arg(args, "--top-p", settings.top_p)
    add_arg(args, "--min-p", settings.min_p)
    add_arg(args, "--presence-penalty", settings.presence_penalty)
    add_arg(args, "--rope-scaling", settings.rope_scaling)
    add_arg(args, "--rope-scale", settings.rope_scale)
    add_arg(args, "--rope-freq-base", settings.rope_freq_base)
    add_arg(args, "--rope-freq-scale", settings.rope_freq_scale)
    add_arg(args, "--yarn-orig-ctx", settings.yarn_orig_ctx)
    add_arg(args, "--yarn-ext-factor", settings.yarn_ext_factor)
    add_arg(args, "--yarn-attn-factor", settings.yarn_attn_factor)
    add_arg(args, "--yarn-beta-slow", settings.yarn_beta_slow)
    add_arg(args, "--yarn-beta-fast", settings.yarn_beta_fast)

    if settings.enable_perf:
        args.append("--perf")
    if settings.enable_metrics:
        args.append("--metrics")
    if settings.enable_slots:
        args.append("--slots")
    if settings.enable_log_timestamps:
        args.append("--log-timestamps")
    if settings.enable_log_prefix:
        args.append("--log-prefix")

    args.append("--cont-batching" if settings.enable_cont_batching else "--no-cont-batching")
    args.append("--context-shift" if settings.enable_context_shift else "--no-context-shift")
    args.append("--kv-offload" if settings.enable_kv_offload else "--no-kv-offload")
    args.append("--mmap" if settings.enable_mmap else "--no-mmap")
    args.append("--repack" if settings.enable_repack else "--no-repack")

    if settings.enable_mlock:
        args.append("--mlock")
    if settings.enable_swa_full:
        args.append("--swa-full")
    if settings.cpu_moe:
        args.append("--cpu-moe")

    add_arg(args, "--n-cpu-moe", settings.n_cpu_moe)
    add_arg(args, "--model-draft", settings.model_draft)
    add_arg(args, "--ctx-size-draft", settings.ctx_size_draft)
    add_arg(args, "--gpu-layers-draft", settings.gpu_layers_draft)
    add_arg(args, "--spec-type", settings.spec_type)
    add_arg(args, "--cache-reuse", settings.cache_reuse)
    add_arg(args, "--log-file", settings.log_file)

    return args


def print_startup(settings: ServerSettings) -> None:
    print("Starting llama-server")
    print(f"  model: {settings.model_path}")
    print(f"  profile:{settings.profile}")
    print(f"  alias: {settings.alias}")
    print(f"  bind:  http://{settings.host}:{settings.port}")
    print(f"  ctx:   {settings.ctx_size}")
    print(f"  batch: {settings.batch_size}/{settings.ubatch_size}")
    print(
        "  samp:  "
        f"temp={settings.temperature if settings.temperature is not None else 'model'}, "
        f"top_k={settings.top_k if settings.top_k is not None else 'model'}, "
        f"top_p={settings.top_p if settings.top_p is not None else 'model'}, "
        f"min_p={settings.min_p if settings.min_p is not None else 'model'}, "
        f"presence={settings.presence_penalty if settings.presence_penalty is not None else 'off'}, "
        f"rep_guard={'on' if settings.enable_repetition_guard else 'off'}"
    )
    print(f"  kv:    {settings.cache_type_k}/{settings.cache_type_v}")
    print(f"  ngl:   {settings.gpu_layers}")
    print(f"  moe:   cpu={'on' if settings.cpu_moe else 'off'} first_n={settings.n_cpu_moe or '0'}")
    print(
        "  rope:  "
        f"scaling={settings.rope_scaling or 'model'}, "
        f"scale={settings.rope_scale or 'model'}, "
        f"yarn_orig={settings.yarn_orig_ctx or 'model'}"
    )
    print(
        "  mem:   "
        f"kv_offload={'on' if settings.enable_kv_offload else 'off'}, "
        f"mmap={'on' if settings.enable_mmap else 'off'}, "
        f"mlock={'on' if settings.enable_mlock else 'off'}"
    )
    print(
        "  serve: "
        f"parallel={settings.parallel}, "
        f"cont_batching={'on' if settings.enable_cont_batching else 'off'}, "
        f"context_shift={'on' if settings.enable_context_shift else 'off'}, "
        f"cache_reuse={settings.cache_reuse or 'model'}"
    )
    print(f"  perf:  {'on' if settings.enable_perf else 'off'}")
    print(f"  met:   {'on' if settings.enable_metrics else 'off'}")
    print(f"  slots: {'on' if settings.enable_slots else 'off'}")
    print(
        "  log:   "
        f"verbosity={settings.log_verbosity}, "
        f"timestamps={'on' if settings.enable_log_timestamps else 'off'}, "
        f"prefix={'on' if settings.enable_log_prefix else 'off'}"
    )
    if settings.log_file:
        print(f"  file:  {settings.log_file}")


def validate_runtime(settings: ServerSettings) -> None:
    if shutil.which(settings.llama_server_bin) is None and not Path(
        settings.llama_server_bin
    ).is_file():
        fail(f"llama-server not found at: {settings.llama_server_bin}")

    if not settings.model_path or not settings.model_path.is_file():
        fail(f"Model file not found: {settings.model_path}")

    model_size = settings.model_path.stat().st_size
    if model_size < settings.min_model_bytes:
        fail(
            "\n".join(
                [
                    f"Model file looks incomplete: {settings.model_path}",
                    f"Current size: {model_size} bytes",
                    f"Required minimum: {settings.min_model_bytes} bytes",
                ]
            )
        )


def main() -> None:
    settings = ServerSettings()
    validate_runtime(settings)
    if settings.enable_run_capture:
        raise SystemExit(run_with_capture(settings))

    print_startup(settings)
    import os

    os.execvp(settings.llama_server_bin, build_args(settings))
