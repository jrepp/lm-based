from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lm_launcher import onboard
from lm_launcher.env_file import read_dotenv
from lm_launcher.policy import load_policy

GiB = 1024**3
ROOT = Path(__file__).resolve().parents[1]


class PresetTests(unittest.TestCase):
    def test_preset_tracks_memory(self) -> None:
        self.assertEqual(onboard.choose_preset(16).name, "compact")
        self.assertEqual(onboard.choose_preset(64).name, "standard")
        self.assertEqual(onboard.choose_preset(128).name, "workstation")

    def test_preset_models_have_sidecars(self) -> None:
        records = onboard.load_records()
        for preset in onboard.PRESETS:
            for slug in (*preset.chat, *preset.resident):
                with self.subTest(preset=preset.name, slug=slug):
                    self.assertIn(slug, records)

    def test_tracked_default_matches_compact_preset(self) -> None:
        policy = load_policy(ROOT / "serve-policy.yaml", local_path=ROOT / "absent.local.yaml")
        overlay = onboard.preset_overlay(onboard.preset_by_name("compact"))
        self.assertEqual(policy["models"]["enabled"], overlay["models"]["enabled"])

    def test_overlay_groups_chat_and_resident_models(self) -> None:
        overlay = onboard.preset_overlay(onboard.preset_by_name("standard"))
        groups = overlay["swap"]["routing"]["router"]["settings"]["groups"]
        self.assertTrue(groups["main"]["swap"])
        self.assertFalse(groups["small"]["swap"])
        self.assertEqual(groups["small"]["members"], ["glm-ocr-q8_0"])


class InitTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / ".env.example").write_text("MODEL_SLUG=x\n")
        self.local = self.root / "serve-policy.local.yaml"
        self.patches = [
            mock.patch.object(onboard, "ROOT", self.root),
            mock.patch.object(onboard, "LOCAL_POLICY_PATH", self.local),
            mock.patch.object(onboard, "host_memory_bytes", return_value=64 * GiB),
        ]
        for patch in self.patches:
            patch.start()

    def tearDown(self) -> None:
        for patch in self.patches:
            patch.stop()
        self._tmp.cleanup()

    def test_writes_sized_overlay_and_env(self) -> None:
        self.assertEqual(onboard.init(out=io.StringIO()), 0)
        written = json.loads(self.local.read_text())
        self.assertIn("qwen35-35b-a3b-q4km", written["models"]["enabled"])
        self.assertEqual((self.root / ".env").read_text(), "MODEL_SLUG=x\n")

    def test_keeps_existing_overlay_unless_forced(self) -> None:
        self.local.write_text("{}")
        onboard.init(out=io.StringIO())
        self.assertEqual(self.local.read_text(), "{}")
        onboard.init("compact", force=True, out=io.StringIO())
        self.assertEqual(json.loads(self.local.read_text())["models"]["enabled"], ["mistral-7b-instruct-v03-q4km", "glm-ocr-q8_0"])

    def test_unknown_preset_fails(self) -> None:
        with mock.patch("sys.stderr", io.StringIO()):
            self.assertEqual(onboard.init("huge", out=io.StringIO()), 2)


class DoctorTests(unittest.TestCase):
    def _checks(self, policy, records, memory=64 * GiB, present=False, size=0):
        with (
            mock.patch.object(onboard, "artifact_present", return_value=present),
            mock.patch.object(onboard, "record_artifact_path", return_value=Path("/x.gguf")),
            mock.patch.object(onboard, "artifact_bytes", return_value=size),
            mock.patch.object(onboard, "legacy_root_artifacts", return_value=[]),
        ):
            return {c.name: c for c in onboard.doctor_checks(policy, records, memory)}

    def test_missing_model_is_a_warning_and_unknown_slug_fails(self) -> None:
        records = {"a": {"artifact": {"format": "gguf"}}}
        checks = self._checks({"models": {"enabled": ["a", "ghost"]}}, records)
        self.assertEqual(checks["a"].status, "warn")
        self.assertEqual(checks["ghost"].status, "fail")

    def test_memory_budget_counts_resident_group_plus_largest_swapped(self) -> None:
        records = {s: {"artifact": {"format": "gguf"}} for s in ("big", "small", "ocr")}
        groups = {
            "main": {"swap": True, "members": ["big", "small"]},
            "res": {"swap": False, "members": ["ocr"]},
        }
        policy = {"models": {"enabled": ["big", "small", "ocr"]}, "swap": {"routing": {"router": {"settings": {"groups": groups}}}}}
        ok = self._checks(policy, records, memory=64 * GiB, present=True, size=10 * GiB)
        self.assertEqual(ok["memory"].status, "ok")  # 20 GB of 48
        tight = self._checks(policy, records, memory=16 * GiB, present=True, size=10 * GiB)
        self.assertEqual(tight["memory"].status, "fail")  # 20 GB of 12

    def test_artifact_bytes_sums_gguf_shards(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            d = Path(temporary)
            for i in (1, 2, 3):
                (d / f"M-0000{i}-of-00003.gguf").write_bytes(b"x" * i)
            (d / "other.gguf").write_bytes(b"y" * 100)
            self.assertEqual(onboard.artifact_bytes(d / "M-00001-of-00003.gguf"), 6)
            self.assertEqual(onboard.artifact_bytes(d / "other.gguf"), 100)
            self.assertEqual(onboard.artifact_bytes(d / "absent.gguf"), 0)

    def test_dotenv_parser(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            env = Path(temporary) / ".env"
            env.write_text("# comment\nLLAMA_SERVER_BIN='/opt/llama-server'\nEMPTY=\n")
            self.assertEqual(read_dotenv(env), {"LLAMA_SERVER_BIN": "/opt/llama-server", "EMPTY": ""})


if __name__ == "__main__":
    unittest.main()
