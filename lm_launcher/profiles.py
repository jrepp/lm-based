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
    if "glm-ocr" in lowered:
        return "glm-ocr"
    if "kev" in lowered:
        return "mlx-kev"
    if "qwen3-coder-480b" in lowered:
        return "qwen3-coder-480b"
    if "qwen2.5-coder" in lowered:
        return "qwen2.5-coder-transformers"
    if "qwen3.6" in lowered and "mtp" in lowered:
        return "qwen3.6-mtp"
    if "qwen3.6" in lowered:
        return "qwen3.6"
    if "qwen3.8" in lowered and "mtp" in lowered:
        return "qwen3.8-mtp"
    if "qwen3.8" in lowered:
        return "qwen3.8"
    if "122b" in lowered:
        return "qwen3.5-122b"
    if "qwen3.5" in lowered:
        return "qwen3.5"
    if "gemma" in lowered:
        return "gemma4"
    if "ouro" in lowered:
        return "ouro"
    if "bonsai" in lowered and "mlx" in lowered:
        return "mlx-bonsai"
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

    if profile == "glm-ocr":
        # GLM-OCR (0.9B vision document parser, glm4 arch + mmproj). Greedy
        # decode is the standard for OCR; prompts are task strings like
        # "Text Recognition:" sent with a page image. ctx held well below the
        # 131072 native ceiling until measured.
        defaults.update(
            {
                "ctx_size": 32768,
                "temperature": 0.0,
                "batch_size": 1024,
                "ubatch_size": 256,
            }
        )

    if profile == "qwen3.5-122b":
        # 122B-A10B MoE: unsloth dynamic 4-bit is the 128GB fit. Standard
        # attention KV gets expensive at long context, so use near-lossless
        # q8_0 KV cache and hold 131072 ctx (262144 native ceiling) until
        # measured on the 128GB budget.
        defaults.update(
            {
                "ctx_size": 131072,
                "cache_type_k": "q8_0",
                "cache_type_v": "q8_0",
                "batch_size": 1024,
                "ubatch_size": 256,
            }
        )

    if profile == "qwen3.8":
        # Dense 27B successor to qwen3.6; keep ctx conservative until the
        # architecture is validated on llama.cpp/Metal.
        defaults.update(
            {
                "ctx_size": 131072,
                "batch_size": 1024,
                "ubatch_size": 256,
            }
        )

    if profile == "mlx-kev":
        # kev decision models (kev.serve): prefill-only, served through the
        # /v1/systemone API. No sampler flags — each checkpoint ships its own
        # fitted calibration temperature. ctx_size records the kev serving
        # ceiling (65536-token states); the validated context of kev-4b is
        # 8192 tokens.
        defaults.update(
            {
                "ctx_size": 65536,
            }
        )

    if profile == "qwen3.8-mtp":
        # MTP-preserved quant for native draft-mtp speculative decoding,
        # mirroring the validated qwen3.6-mtp profile. Requires a llama-server
        # build with draft-mtp support (the sidecar pins LLAMA_SERVER_BIN).
        defaults.update(
            {
                "ctx_size": 262144,
                "alias": "qwen38-27b-mtp",
                "cache_type_k": "q4_0",
                "cache_type_v": "q4_0",
                "batch_size": 1024,
                "ubatch_size": 256,
                "parallel": 1,
                "flash_attn": "on",
                "spec_type": "draft-mtp",
                "spec_draft_n_max": 4,
            }
        )

    if profile == "qwen3.6":
        defaults.update(
            {
                "ctx_size": 262144,
                "alias": slugify_model_alias(model_name),
                "cache_type_k": "q4_0",
                "cache_type_v": "q4_0",
                "batch_size": 1024,
                "ubatch_size": 256,
            }
        )

    if profile == "qwen3.6-mtp":
        defaults.update(
            {
                "ctx_size": 262144,
                "alias": "qwen36-27b-mtp",
                "cache_type_k": "q4_0",
                "cache_type_v": "q4_0",
                "batch_size": 1024,
                "ubatch_size": 256,
                "parallel": 1,
                "flash_attn": "on",
                "spec_type": "draft-mtp",
                "spec_draft_n_max": 4,
            }
        )

    if profile == "qwen2.5-coder-transformers":
        defaults.update(
            {
                "ctx_size": 131072,
                "alias": slugify_model_alias(model_name),
                "batch_size": 1024,
                "ubatch_size": 256,
                "temperature": 0.7,
                "top_k": 20,
                "top_p": 0.8,
                "min_p": 0.0,
                "presence_penalty": 1.5,
            }
        )

    if profile in ("qwen3-coder-480b", "qwen3-coder-480b-mlx"):
        # Qwen's Qwen3-Coder-480B-A35B-Instruct card recommends
        # temperature=0.7, top_p=0.8, top_k=20, repetition_penalty=1.05.
        defaults.update(
            {
                "ctx_size": 262144,
                "alias": "qwen3-coder-480b-a35b-instruct",
                "batch_size": 1024,
                "ubatch_size": 256,
                "temperature": 0.7,
                "top_k": 20,
                "top_p": 0.8,
                "max_tokens": 65536,
                "repetition_penalty": 1.05,
                "cache_type_k": "q4_0",
                "cache_type_v": "q4_0",
            }
        )

    if profile == "ouro":
        defaults.update(
            {
                "ctx_size": 8192,
                "alias": "ouro-2.6b-thinking",
                "batch_size": 512,
                "ubatch_size": 128,
                "temperature": 0.7,
                "top_p": 1.0,
            }
        )

    if profile == "mlx-bonsai":
        # Ternary Bonsai 27B (Qwen3.6-27B-derived, qwen3_5 hybrid attention)
        # served via mlx_lm.server on Apple Silicon. Sampler defaults are the
        # upstream thinking-mode best practices (temp 0.7 / top-p 0.95 / top-k 20).
        # ctx_size is metadata only; mlx_lm grows the KV cache to fit.
        defaults.update(
            {
                "ctx_size": 262144,
                "temperature": 0.7,
                "top_p": 0.95,
                "top_k": 20,
            }
        )

    return defaults
