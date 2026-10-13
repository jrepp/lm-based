from __future__ import annotations

import unittest

from lm_launcher.profiles import infer_profile, profile_defaults


class MlxBonsaiProfileTests(unittest.TestCase):
    def test_infer_profile_from_model_name(self) -> None:
        self.assertEqual(
            infer_profile("Ternary-Bonsai-27B-MLX-2bit", "auto"),
            "mlx-bonsai",
        )

    def test_explicit_profile_passthrough(self) -> None:
        # When a profile is supplied (e.g. via the sidecar), it is returned as-is
        # even though the anchor filename is "config.json".
        self.assertEqual(infer_profile("config.json", "mlx-bonsai"), "mlx-bonsai")

    def test_profile_defaults_sampler_and_context(self) -> None:
        defaults = profile_defaults("mlx-bonsai", "Ternary-Bonsai-27B-MLX-2bit")
        self.assertEqual(defaults["ctx_size"], 262144)
        self.assertEqual(defaults["temperature"], 0.7)
        self.assertEqual(defaults["top_p"], 0.95)
        self.assertEqual(defaults["top_k"], 20)


class MlxKevProfileTests(unittest.TestCase):
    def test_infer_profile_from_model_name(self) -> None:
        self.assertEqual(infer_profile("kev-4b-mlx-8bit", "auto"), "mlx-kev")

    def test_explicit_profile_passthrough(self) -> None:
        self.assertEqual(infer_profile("config.json", "mlx-kev"), "mlx-kev")

    def test_profile_defaults_record_serve_ceiling_without_sampler(self) -> None:
        # Decision model: no sampler flags (the checkpoint ships its own
        # calibrated temperature); ctx_size records the kev serve ceiling.
        defaults = profile_defaults("mlx-kev", "kev-4b-mlx-8bit")
        self.assertEqual(defaults["ctx_size"], 65536)
        self.assertNotIn("temperature", defaults)
        self.assertNotIn("top_p", defaults)
        self.assertNotIn("top_k", defaults)


class Qwen35122bProfileTests(unittest.TestCase):
    def test_infer_profile_from_model_name(self) -> None:
        self.assertEqual(
            infer_profile(
                "UD-Q4_K_XL/Qwen3.5-122B-A10B-UD-Q4_K_XL-00001-of-00003.gguf", "auto"
            ),
            "qwen3.5-122b",
        )

    def test_profile_defaults_context_and_kv(self) -> None:
        defaults = profile_defaults(
            "qwen3.5-122b", "Qwen3.5-122B-A10B-UD-Q4_K_XL.gguf"
        )
        self.assertEqual(defaults["ctx_size"], 131072)
        self.assertEqual(defaults["cache_type_k"], "q8_0")
        self.assertEqual(defaults["cache_type_v"], "q8_0")


class Qwen38ProfileTests(unittest.TestCase):
    def test_infer_profile_from_model_name(self) -> None:
        self.assertEqual(
            infer_profile("Qwen3.8-27B-UD-Q6_K.gguf", "auto"), "qwen3.8"
        )

    def test_profile_defaults_conservative_context(self) -> None:
        defaults = profile_defaults("qwen3.8", "Qwen3.8-27B-UD-Q6_K.gguf")
        self.assertEqual(defaults["ctx_size"], 131072)


class Qwen38MtpProfileTests(unittest.TestCase):
    def test_infer_profile_prefers_mtp_variant(self) -> None:
        self.assertEqual(
            infer_profile("MTP/mtp-Qwen3.8-27B-Q4_0.gguf", "auto"), "qwen3.8-mtp"
        )

    def test_explicit_profile_passthrough(self) -> None:
        self.assertEqual(infer_profile("config.json", "qwen3.8-mtp"), "qwen3.8-mtp")

    def test_profile_defaults_mirror_qwen36_mtp(self) -> None:
        defaults = profile_defaults("qwen3.8-mtp", "mtp-Qwen3.8-27B-Q4_0.gguf")
        self.assertEqual(defaults["ctx_size"], 262144)
        self.assertEqual(defaults["spec_type"], "draft-mtp")
        self.assertEqual(defaults["spec_draft_n_max"], 4)
        self.assertEqual(defaults["flash_attn"], "on")
        self.assertEqual(defaults["cache_type_k"], "q4_0")


if __name__ == "__main__":
    unittest.main()
