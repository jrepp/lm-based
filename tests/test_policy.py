from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from lm_launcher.policy import deep_merge, enabled_slugs, load_policy, local_policy_path


class PolicyOverlayTests(unittest.TestCase):
    def test_objects_merge_and_lists_replace(self) -> None:
        base = {"ingress": {"swap_listen": "a", "public_listen": "b"}, "models": {"enabled": ["x", "y"], "warm": ["x"]}}
        overlay = {"ingress": {"swap_listen": "c"}, "models": {"enabled": ["z"]}}
        self.assertEqual(
            deep_merge(base, overlay),
            {"ingress": {"swap_listen": "c", "public_listen": "b"}, "models": {"enabled": ["z"], "warm": ["x"]}},
        )

    def test_local_file_sits_beside_policy(self) -> None:
        self.assertEqual(local_policy_path(Path("/r/serve-policy.yaml")), Path("/r/serve-policy.local.yaml"))

    def test_load_without_overlay_and_with_unreadable_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            policy = Path(temporary) / "serve-policy.yaml"
            policy.write_text(json.dumps({"models": {"enabled": ["a"]}}))
            self.assertEqual(enabled_slugs(load_policy(policy)), ["a"])
            local_policy_path(policy).write_text("not json")
            self.assertEqual(enabled_slugs(load_policy(policy)), ["a"])
            local_policy_path(policy).write_text(json.dumps({"models": {"enabled": ["b"]}}))
            self.assertEqual(enabled_slugs(load_policy(policy)), ["b"])

    def test_missing_policy_is_empty(self) -> None:
        self.assertEqual(load_policy(Path("/nonexistent/serve-policy.yaml")), {})

    def test_tracked_default_enables_only_models_with_sidecars(self) -> None:
        root = Path(__file__).resolve().parents[1]
        slugs = {json.loads(p.read_text())["model"]["slug"] for p in (root / "models").glob("*.json")}
        policy = load_policy(root / "serve-policy.yaml", local_path=root / "absent.local.yaml")
        self.assertTrue(enabled_slugs(policy))
        self.assertLessEqual(set(enabled_slugs(policy)), slugs)


if __name__ == "__main__":
    unittest.main()
