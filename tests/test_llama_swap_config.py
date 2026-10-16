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
        cfg = build_config(models_dir=self.models, hot_slugs=None, require_artifacts=False)
        self.assertEqual(set(cfg.models), {"test-a", "test-b"})

    def test_hot_filter_restricts_to_enabled_slugs(self) -> None:
        cfg = build_config(models_dir=self.models, hot_slugs={"test-a"}, require_artifacts=False)
        self.assertEqual(set(cfg.models), {"test-a"})
        self.assertIn("PORT=${PORT}", cfg.models["test-a"].cmd)
        # llama-swap execs cmd directly: the env-prefixed script must be
        # wrapped in a shell invocation.
        self.assertTrue(cfg.models["test-a"].cmd.startswith("sh -c "))

    def test_hot_filter_with_only_unknown_slugs_yields_empty(self) -> None:
        cfg = build_config(models_dir=self.models, hot_slugs={"does-not-exist"}, require_artifacts=False)
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
        cfg = build_config(models_dir=self.models, hot_slugs=None, require_artifacts=False)
        self.assertEqual(set(cfg.models), {"bonsai-mlx", "kev-4b-mlx-8bit"})

    def test_kev_profile_uses_v1_models_health_check(self) -> None:
        # kev.serve has no /health; mlx_lm.server keeps the default.
        cfg = build_config(models_dir=self.models, hot_slugs=None, require_artifacts=False)
        self.assertEqual(cfg.models["kev-4b-mlx-8bit"].check_endpoint, "/v1/models")
        self.assertEqual(cfg.models["bonsai-mlx"].check_endpoint, "/health")


class ModelMetadataTests(unittest.TestCase):
    def test_real_sidecars_publish_kind_and_context(self) -> None:
        # llama-swap v264 returns metadata under meta.llamaswap in /v1/models.
        cfg = build_config(hot_slugs=None, require_artifacts=False)
        self.assertEqual(cfg.models["kev-4b-mlx-8bit"].metadata, {"kind": "decision", "context_length": 262144})
        self.assertEqual(cfg.models["glm-ocr-q8_0"].metadata["kind"], "ocr")
        self.assertEqual(cfg.models["qwen3-coder-next-q6k"].metadata["kind"], "chat")


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
            cfg = swap_config.build_config(models_dir=self.models, require_artifacts=False)
        finally:
            swap_config.PROJECT_ROOT = original
        self.assertEqual(cfg.routing, routing)
        self.assertEqual(cfg.to_dict()["routing"], routing)

    def test_no_routing_yields_default(self) -> None:
        from llama_swap.config import _read_policy_routing

        self.assertEqual(_read_policy_routing(Path(self._tmp.name) / "absent.json"), {})


class LocalOverlayAndArtifactTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.models = self.root / "models"
        self.models.mkdir()
        for slug in ("chat-a", "chat-b", "ocr"):
            record = {
                "model": {"slug": slug},
                "artifact": {"format": "gguf", "local_path": f"{slug}.gguf"},
                "launcher": {"profile": "generic"},
            }
            (self.models / f"{slug}.gguf.json").write_text(json.dumps(record))
        (self.root / "artifacts").mkdir()
        (self.root / "artifacts" / "chat-a.gguf").write_text("weights")
        (self.root / "ocr.gguf").write_text("weights")  # older project-root layout
        groups = {
            "main": {"swap": True, "members": ["chat-a", "chat-b"]},
            "small": {"swap": False, "members": ["ocr"]},
            "gone": {"swap": False, "members": ["chat-b"]},
        }
        (self.root / "serve-policy.yaml").write_text(json.dumps({
            "models": {"enabled": ["chat-a"]},
            "swap": {"routing": {"router": {"use": "group", "settings": {"groups": groups}}}},
            "policy": {"require_local_artifact": True},
        }))
        (self.root / "serve-policy.local.yaml").write_text(json.dumps({
            "models": {"enabled": ["chat-a", "chat-b", "ocr"]},
        }))
        from llama_swap import config as swap_config

        self.swap_config = swap_config
        self._original = swap_config.PROJECT_ROOT
        swap_config.PROJECT_ROOT = self.root

    def tearDown(self) -> None:
        self.swap_config.PROJECT_ROOT = self._original
        self._tmp.cleanup()

    def test_local_overlay_replaces_enabled_list(self) -> None:
        self.assertEqual(_read_enabled_slugs(), {"chat-a", "chat-b", "ocr"})

    def test_missing_artifacts_are_skipped_and_pruned_from_groups(self) -> None:
        cfg = self.swap_config.build_config(models_dir=self.models)
        self.assertEqual(sorted(cfg.models), ["chat-a", "ocr"])
        self.assertEqual(cfg.skipped, ["chat-b"])
        groups = cfg.routing["router"]["settings"]["groups"]
        self.assertEqual(groups["main"]["members"], ["chat-a"])
        self.assertEqual(groups["small"]["members"], ["ocr"])
        self.assertNotIn("gone", groups)

    def test_require_artifacts_false_keeps_every_enabled_model(self) -> None:
        cfg = self.swap_config.build_config(models_dir=self.models, require_artifacts=False)
        self.assertEqual(sorted(cfg.models), ["chat-a", "chat-b", "ocr"])
        self.assertEqual(cfg.skipped, [])


if __name__ == "__main__":
    unittest.main()
