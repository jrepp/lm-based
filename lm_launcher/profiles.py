import re
from pathlib import Path


def slugify_model_alias(model_name: str) -> str:
    stem = Path(model_name).stem.lower()
    return re.sub(r"[^a-z0-9]+", "-", stem).strip("-")


def infer_profile(model_name: str, requested: str) -> str:
    if requested != "auto":
        return requested

    lowered = model_name.lower()
    if "qwen3-coder-next" in lowered:
        return "qwen3-coder-next"
    if "qwen3.5" in lowered:
        return "qwen3.5"
    if "gemma" in lowered:
        return "gemma4"
    return "generic"


def profile_defaults(profile: str, model_name: str) -> dict[str, object]:
    defaults: dict[str, object] = {
        "ctx_size": 262144,
        "alias": slugify_model_alias(model_name),
        "cache_type_k": "q4_0",
        "cache_type_v": "q4_0",
        "batch_size": 2048,
        "ubatch_size": 512,
        "parallel": 1,
        "threads": 8,
        "threads_batch": 8,
        "gpu_layers": "all",
        "flash_attn": "auto",
        "log_verbosity": 3,
        "enable_context_shift": False,
        "poll": 50,
        "slot_prompt_similarity": 0.10,
    }

    if profile == "gemma4":
        # Gemma 4 uses hybrid attention (local sliding-window + global layers).
        # 2B models fit in a modest context; keep ctx_size conservative until
        # llama.cpp sliding-window support is verified for this build.
        defaults.update(
            {
                "ctx_size": 32768,
                "alias": slugify_model_alias(model_name),
                "cache_type_k": "q4_0",
                "cache_type_v": "q4_0",
                "batch_size": 512,
                "ubatch_size": 128,
            }
        )

    if profile == "qwen3-coder-next":
        # Qwen recommends temperature=1.0, top_p=0.95, top_k=40 on the
        # Qwen3-Coder-Next model card:
        # https://huggingface.co/Qwen/Qwen3-Coder-Next
        #
        # Their llama.cpp guide also uses min_p=0 and recommends
        # --no-context-shift for fixed-window behavior:
        # https://qwen.readthedocs.io/en/latest/run_locally/llama.cpp.html
        defaults.update(
            {
                "ctx_size": 1048576,
                "alias": "qwen3-coder-next-1m",
                "yarn_orig_ctx": 262144,
                "rope_scaling": "yarn",
                "rope_scale": 4.0,
                "batch_size": 1024,
                "ubatch_size": 256,
                "temperature": 1.0,
                "top_k": 40,
                "top_p": 0.95,
                "min_p": 0.0,
                "cache_type_k": "q4_0",
                "cache_type_v": "q4_0",
            }
        )

    return defaults
