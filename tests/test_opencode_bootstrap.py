from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from lm_launcher import opencode_bootstrap
from lm_launcher.pi_bootstrap import load_sidecars


class OpenCodeBootstrapTests(unittest.TestCase):
    def test_hot_slugs_generate_openai_compatible_provider(self) -> None:
        sidecars = load_sidecars()
        api_ids = ["qwen36-27b-q6k", "qwen25-coder-7b-instruct"]

        plan = opencode_bootstrap.build_plan(
            "lm-based",
            "http://127.0.0.1:8081/v1/",
            None,
            api_ids,
            sidecars,
        )
        config = opencode_bootstrap.opencode_config(plan)
        provider = config["provider"]["lm-based"]

        self.assertEqual(plan.selected_model, "qwen36-27b-q6k")
        self.assertEqual(config["model"], "lm-based/qwen36-27b-q6k")
        self.assertEqual(provider["options"]["baseURL"], "http://127.0.0.1:8081/v1")
        self.assertEqual(list(provider["models"]), api_ids)
        self.assertTrue(provider["models"]["qwen36-27b-q6k"]["reasoning"])
        self.assertEqual(provider["models"]["qwen36-27b-q6k"]["limit"]["context"], 262144)

    def test_decision_and_ocr_models_are_not_offered_as_chat(self) -> None:
        # llama-swap lists every hot model; kev (decision) and GLM-OCR must not become
        # OpenCode chat models, let alone the default.
        plan = opencode_bootstrap.build_plan(
            "lm-based",
            "http://127.0.0.1:8081/v1",
            None,
            ["kev-4b-mlx-8bit", "glm-ocr-q8_0", "qwen3-coder-next-q6k"],
            load_sidecars(),
        )
        self.assertEqual([model_id for model_id, _ in plan.models], ["qwen3-coder-next-q6k"])
        self.assertEqual(plan.selected_model, "qwen3-coder-next-q6k")

    def test_only_non_chat_models_is_an_error(self) -> None:
        with self.assertRaises(opencode_bootstrap.OpenCodeBootstrapError):
            opencode_bootstrap.build_plan(
                "lm-based", "http://127.0.0.1:8081/v1", None, ["kev-4b-mlx-8bit"], load_sidecars()
            )

    def test_explicit_model_must_be_in_hot_set(self) -> None:
        with self.assertRaisesRegex(opencode_bootstrap.OpenCodeBootstrapError, "is not hot"):
            opencode_bootstrap.build_plan(
                "lm-based",
                "http://127.0.0.1:8081/v1",
                "qwen25-coder-7b-instruct",
                ["qwen36-27b-q6k"],
                load_sidecars(),
            )

    def test_filesystem_model_id_is_rejected(self) -> None:
        with self.assertRaisesRegex(opencode_bootstrap.OpenCodeBootstrapError, "filesystem path"):
            opencode_bootstrap.build_plan(
                "lm-based",
                "http://127.0.0.1:8001/v1",
                None,
                ["/Users/example/models/Qwen"],
                load_sidecars(),
            )

    def test_unknown_public_model_id_is_rejected(self) -> None:
        with self.assertRaisesRegex(opencode_bootstrap.OpenCodeBootstrapError, "match a sidecar slug"):
            opencode_bootstrap.build_plan(
                "lm-based",
                "http://127.0.0.1:8081/v1",
                None,
                ["unknown-model"],
                load_sidecars(),
            )

    def test_generated_config_is_idempotent(self) -> None:
        plan = opencode_bootstrap.build_plan(
            "lm-based",
            "http://127.0.0.1:8081/v1",
            None,
            ["qwen36-27b-q6k"],
            load_sidecars(),
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "opencode.json"
            first = opencode_bootstrap.write_generated_config(
                path,
                opencode_bootstrap.opencode_config(plan),
            )
            second = opencode_bootstrap.write_generated_config(
                path,
                opencode_bootstrap.opencode_config(plan),
            )
            value = json.loads(path.read_text(encoding="utf-8"))

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(value["model"], "lm-based/qwen36-27b-q6k")


if __name__ == "__main__":
    unittest.main()
