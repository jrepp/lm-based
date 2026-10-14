import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from llama_swap.config import build_config
from lm_launcher.launcher import build_args, validate_runtime
from lm_launcher.pi_bootstrap import load_sidecars, resolve_sidecars, ServiceState
from lm_launcher.profiles import infer_profile
from lm_launcher.settings import ServerSettings


class OcrServingTests(unittest.TestCase):
    def test_default_ocr_is_configured_and_group_members_exist(self):
        cfg = build_config()
        self.assertIn("glm-ocr-q8_0", cfg.models)
        for group in cfg.routing["router"]["settings"]["groups"].values():
            for member in group["members"]:
                self.assertIn(member, cfg.models)

    def test_ocr_remains_excluded_from_chat_picker(self):
        sidecars = load_sidecars()
        self.assertIn("glm-ocr-q8_0", sidecars)
        state = ServiceState(frozenset({"llama-swap"}), (), "http://localhost:8081/v1")
        selected = resolve_sidecars(state, ["glm-ocr-q8_0", "qwen36-27b-q6k"], sidecars)
        self.assertEqual([s.slug for s in selected], ["qwen36-27b-q6k"])

    def test_ocr_launcher_includes_projector_and_conservative_context(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = ServerSettings(_env_file=None, model_slug="glm-ocr-q8_0")
        args = build_args(settings)
        self.assertEqual(settings.profile, "glm-ocr")
        self.assertEqual(infer_profile("GLM-OCR-Q8_0.gguf", "auto"), "glm-ocr")
        self.assertLessEqual(settings.ctx_size, 32768)
        self.assertEqual(Path(args[args.index("--mmproj") + 1]).name, "mmproj-GLM-OCR-Q8_0.gguf")
        self.assertTrue(Path(args[args.index("--mmproj") + 1]).is_absolute())

    def test_missing_projector_is_rejected_before_launch(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {}, clear=True):
            # Ordinary temporary files stand in for weights; never write GGUF binaries.
            model = Path(temporary) / "model.bin"
            model.write_bytes(b"test")
            settings = ServerSettings(_env_file=None, model_path=model, min_model_bytes=1,
                                      mmproj=Path(temporary) / "missing.bin")
            with patch("lm_launcher.launcher.shutil.which", return_value="/mock/llama-server"):
                with self.assertRaises(SystemExit):
                    validate_runtime(settings)
