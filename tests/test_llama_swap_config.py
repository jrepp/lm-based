from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from llama_swap.config import _read_enabled_slugs, build_config


def _write_sidecar(dir_path: Path, slug: str, name: str, fmt: str = "gguf", profile: str = "generic") -> None:
    record = {
        "model": {"slug": slug},
        "artifact": {"format": fmt, "quantization": "Q4_K_M"},
        "launcher": {"profile": profile},
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
        self.assertIn("PORT=${PORT}", cfg.models["test-a"].cmd)
        # llama-swap execs cmd directly: the env-prefixed script must be
        # wrapped in a shell invocation.
        self.assertTrue(cfg.models["test-a"].cmd.startswith("sh -c "))

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


class MlxSidecarConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.models = Path(self._tmp.name) / "models"
        self.models.mkdir()
        _write_sidecar(self.models, "bonsai-mlx", "bonsai.json", fmt="mlx", profile="mlx-bonsai")
        _write_sidecar(self.models, "kev-4b-mlx-8bit", "kev.json", fmt="mlx", profile="mlx-kev")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_mlx_format_sidecars_are_included(self) -> None:
        cfg = build_config(models_dir=self.models, hot_slugs=None)
        self.assertEqual(set(cfg.models), {"bonsai-mlx", "kev-4b-mlx-8bit"})

    def test_kev_profile_uses_v1_models_health_check(self) -> None:
        # kev.serve has no /health; mlx_lm.server keeps the default.
        cfg = build_config(models_dir=self.models, hot_slugs=None)
        self.assertEqual(cfg.models["kev-4b-mlx-8bit"].check_endpoint, "/v1/models")
        self.assertEqual(cfg.models["bonsai-mlx"].check_endpoint, "/health")


class RoutingPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.models = Path(self._tmp.name) / "models"
        self.models.mkdir()
        _write_sidecar(self.models, "test-a", "test-a.gguf.json")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_routing_passed_through_from_policy(self) -> None:
        import os

        from llama_swap import config as swap_config

        policy = Path(self._tmp.name) / "serve-policy.yaml"
        routing = {"router": {"use": "group", "settings": {"groups": {"small": {"swap": False}}}}}
        policy.write_text(json.dumps({"models": {"enabled": ["test-a"]}, "routing": routing}))

        original = swap_config.PROJECT_ROOT
        try:
            swap_config.PROJECT_ROOT = Path(self._tmp.name)
            cfg = swap_config.build_config(models_dir=self.models)
        finally:
            swap_config.PROJECT_ROOT = original
        self.assertEqual(cfg.routing, routing)
        self.assertEqual(cfg.to_dict()["routing"], routing)

    def test_no_routing_yields_default(self) -> None:
        from llama_swap.config import _read_policy_routing

        self.assertEqual(_read_policy_routing(Path(self._tmp.name) / "absent.json"), {})


if __name__ == "__main__":
    unittest.main()
