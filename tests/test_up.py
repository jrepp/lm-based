from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_up_module() -> types.ModuleType:
    module = types.ModuleType("up_script")
    module.__file__ = str(ROOT / "up")
    sys.modules[module.__name__] = module
    code = compile((ROOT / "up").read_text(), str(ROOT / "up"), "exec")
    exec(code, module.__dict__)
    return module


class UpResolverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.up = load_up_module()

    def test_dashboard_depends_on_stats_poll(self) -> None:
        registry = self.up.build_registry()
        plan = self.up.resolve_target("dashboard", registry)
        self.assertEqual([service.name for service in plan.services], ["stats-poll", "dashboard"])

    def test_model_slug_expands_to_model_observability(self) -> None:
        registry = self.up.build_registry()
        slug = "qwen36-27b-mtp-ud-q5k-xl"
        plan = self.up.resolve_target(slug, registry)
        self.assertEqual(
            [service.name for service in plan.services],
            [f"model:{slug}", "stats-poll", "dashboard"],
        )
        self.assertEqual(plan.services[0].env["MODEL_SLUG"], slug)
        self.assertEqual(
            plan.services[0].env["LLAMA_SERVER_BIN"],
            "/Users/jrepp/d/llama.cpp/build/bin/llama-server",
        )

    def test_mlx_slug_includes_sampler_proxy(self) -> None:
        registry = self.up.build_registry()
        slug = "ternary-bonsai-27b-mlx-2bit"
        plan = self.up.resolve_target(slug, registry)
        self.assertEqual(
            [service.name for service in plan.services],
            [f"model:{slug}", "sampler-proxy", "stats-poll", "dashboard"],
        )

    def test_gguf_slug_omits_sampler_proxy(self) -> None:
        registry = self.up.build_registry()
        slug = "qwen36-27b-mtp-ud-q5k-xl"
        plan = self.up.resolve_target(slug, registry)
        self.assertNotIn("sampler-proxy", [service.name for service in plan.services])

    def test_direct_service_set_includes_status_window(self) -> None:
        registry = self.up.build_registry()
        plan = self.up.resolve_target("direct", registry)
        self.assertEqual(
            [service.window_name for service in plan.services],
            ["model-qwen36-27b-mtp-ud-q5k-xl", "stats", "dashboard", "status"],
        )

    def test_default_core_service_set_excludes_model_worker(self) -> None:
        registry = self.up.build_registry()
        plan = self.up.resolve_target("core", registry)
        self.assertEqual(
            [service.window_name for service in plan.services],
            ["stats", "dashboard", "status"],
        )

    def test_unknown_target_fails(self) -> None:
        registry = self.up.build_registry()
        with self.assertRaises(KeyError):
            self.up.resolve_target("missing-target", registry)


if __name__ == "__main__":
    unittest.main()
