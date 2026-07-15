from __future__ import annotations

import unittest

try:
    from lm_launcher.settings import ServerSettings
except ModuleNotFoundError as exc:
    if exc.name in {"pydantic", "pydantic_settings"}:
        ServerSettings = None
    else:
        raise


@unittest.skipIf(ServerSettings is None, "pydantic launcher dependencies are not installed")
class ServerSettingsModelIndexTests(unittest.TestCase):
    def test_model_slug_applies_recommended_llama_server_binary(self) -> None:
        settings = ServerSettings(
            model_slug="qwen36-27b-mtp-ud-q5k-xl",
            enable_run_capture=False,
        )

        self.assertEqual(
            settings.llama_server_bin,
            "/Users/jrepp/d/llama.cpp/build/bin/llama-server",
        )
        self.assertEqual(settings.spec_type, "draft-mtp")
        self.assertEqual(settings.spec_draft_n_max, 4)

    def test_explicit_llama_server_binary_overrides_sidecar_recommendation(self) -> None:
        settings = ServerSettings(
            model_slug="qwen36-27b-mtp-ud-q5k-xl",
            llama_server_bin="/tmp/custom-llama-server",
            enable_run_capture=False,
        )

        self.assertEqual(settings.llama_server_bin, "/tmp/custom-llama-server")


if __name__ == "__main__":
    unittest.main()
