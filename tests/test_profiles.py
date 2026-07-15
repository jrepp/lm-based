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


if __name__ == "__main__":
    unittest.main()
