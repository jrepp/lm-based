from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from llama_swap.config import _read_enabled_slugs, build_config


def _write_sidecar(dir_path: Path, slug: str, name: str) -> None:
    record = {
        "model": {"slug": slug},
        "artifact": {"format": "gguf", "quantization": "Q4_K_M"},
        "launcher": {"profile": "generic"},
    }
    (dir_path / name).write_text(json.dumps(record))


class HotModelsConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.models = Path(self._tmp.name) / "models"
        self.models.mkdir()
        _write_sidecar(self.models, "test-a", "test-a.gguf.json")
        _write_sidecar(self.models, "test-b", "test-b.gguf.json")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_no_hot_filter_includes_all_models(self) -> None:
        cfg = build_config(models_dir=self.models, hot_slugs=None)
        self.assertEqual(set(cfg.models), {"test-a", "test-b"})

    def test_hot_filter_restricts_to_enabled_slugs(self) -> None:
        cfg = build_config(models_dir=self.models, hot_slugs={"test-a"})
        self.assertEqual(set(cfg.models), {"test-a"})

    def test_hot_filter_with_only_unknown_slugs_yields_empty(self) -> None:
        cfg = build_config(models_dir=self.models, hot_slugs={"does-not-exist"})
        self.assertEqual(set(cfg.models), set())

    def test_read_enabled_slugs_from_policy(self) -> None:
        policy = Path(self._tmp.name) / "serve-policy.yaml"
        policy.write_text(json.dumps({"models": {"enabled": ["test-a", "test-b"]}}))
        self.assertEqual(_read_enabled_slugs(policy), {"test-a", "test-b"})

    def test_read_enabled_slugs_no_policy_returns_none(self) -> None:
        # None means "no hot filter" -> include all models.
        self.assertIsNone(_read_enabled_slugs(Path(self._tmp.name) / "absent.json"))


if __name__ == "__main__":
    unittest.main()
