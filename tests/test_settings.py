from __future__ import annotations

import os
import unittest
from unittest import mock
from pathlib import Path
from unittest.mock import patch

try:
    from lm_launcher.settings import ServerSettings
except ModuleNotFoundError as exc:
    if exc.name in {"pydantic", "pydantic_settings"}:
        ServerSettings = None
    else:
        raise


@unittest.skipIf(ServerSettings is None, "pydantic launcher dependencies are not installed")
class ServerSettingsModelIndexTests(unittest.TestCase):
    def test_expands_explicit_binary_override(self) -> None:
        settings = ServerSettings(_env_file=None, llama_server_bin="~/custom/llama-server")
        self.assertEqual(settings.llama_server_bin, os.path.expanduser("~/custom/llama-server"))

    def test_llama_server_binary_comes_from_machine_config(self) -> None:
        # Sidecars never pin a binary path; LLAMA_SERVER_BIN is set per machine (.env).
        with mock.patch.dict(os.environ, {"LLAMA_SERVER_BIN": "/opt/llama.cpp/bin/llama-server"}):
            settings = ServerSettings(
                model_slug="qwen36-27b-mtp-ud-q5k-xl",
                enable_run_capture=False,
            )

        self.assertEqual(settings.llama_server_bin, "/opt/llama.cpp/bin/llama-server")
        self.assertEqual(settings.spec_type, "draft-mtp")
        self.assertEqual(settings.spec_draft_n_max, 4)

    def test_explicit_llama_server_binary_wins(self) -> None:
        settings = ServerSettings(
            model_slug="qwen36-27b-mtp-ud-q5k-xl",
            llama_server_bin="/tmp/custom-llama-server",
            enable_run_capture=False,
        )

        self.assertEqual(settings.llama_server_bin, "/tmp/custom-llama-server")

    def test_profile_context_is_capped_at_native_context(self) -> None:
        # Mistral-7B v0.3 runs on the generic profile (262144) but was trained on 32768.
        settings = ServerSettings(model_slug="mistral-7b-instruct-v03-q4km", enable_run_capture=False)
        self.assertEqual(settings.model_context_length, 32768)
        self.assertEqual(settings.ctx_size, 32768)

    def test_explicit_context_is_not_capped(self) -> None:
        settings = ServerSettings(
            model_slug="mistral-7b-instruct-v03-q4km", ctx_size=65536, enable_run_capture=False
        )
        self.assertEqual(settings.ctx_size, 65536)

    def test_model_slug_applies_recommended_mmproj(self) -> None:
        settings = ServerSettings(
            model_slug="glm-ocr-q8_0",
            enable_run_capture=False,
        )

        # Relative MMPROJ env values resolve against the project root.
        self.assertEqual(
            settings.mmproj,
            Path(__file__).resolve().parents[1] / "mmproj-GLM-OCR-Q8_0.gguf",
        )
        self.assertEqual(settings.profile, "glm-ocr")
        self.assertEqual(settings.temperature, 0.0)

    def test_mlx_slug_resolves_mlx_bonsai_profile_and_anchor(self) -> None:
        settings = ServerSettings(
            model_slug="ternary-bonsai-27b-mlx-2bit",
            enable_run_capture=False,
        )

        self.assertEqual(settings.profile, "mlx-bonsai")
        self.assertEqual(settings.alias, "ternary-bonsai-27b-mlx-2bit")
        self.assertEqual(settings.ctx_size, 262144)
        self.assertEqual(settings.temperature, 0.7)
        self.assertEqual(settings.top_p, 0.95)
        self.assertEqual(settings.top_k, 20)
        # config.json is the directory anchor; mlx_lm serves its parent.
        self.assertEqual(settings.model_path.name, "config.json")
        self.assertEqual(settings.model_path.parent.name, "Ternary-Bonsai-27B-MLX-2bit")

    def test_projector_path_with_and_without_local_artifacts(self) -> None:
        root = Path(__file__).resolve().parents[1]
        filename = "mmproj-GLM-OCR-Q8_0.gguf"
        project_path = root / filename
        artifact_path = root / "artifacts" / filename
        original_exists = Path.exists
        for existing, expected in [
            (set(), project_path),
            ({project_path}, project_path),
            ({artifact_path}, artifact_path),
            ({project_path, artifact_path}, project_path),
        ]:
            with self.subTest(existing=existing):
                def exists(path):
                    return path in existing if path.name == filename else original_exists(path)

                with patch.object(Path, "exists", exists), patch.dict("os.environ", {}, clear=True):
                    settings = ServerSettings(
                        _env_file=None, model_slug="glm-ocr-q8_0",
                        model_dir=root / "artifacts", enable_run_capture=False,
                    )
                self.assertEqual(settings.mmproj, expected)


if __name__ == "__main__":
    unittest.main()
