import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import download_model


class DownloadDestinationTests(unittest.TestCase):
    def test_catalog_snapshots_land_in_their_model_directory(self):
        records = [r for r in download_model.load_index()
                   if r.get("download", {}).get("snapshot")]
        self.assertTrue(records)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("project readme")

            def snapshot(**kwargs):
                dest = Path(kwargs["local_dir"])
                dest.mkdir(parents=True, exist_ok=True)
                (dest / "README.md").write_text("model readme")
                return str(dest)

            with patch.object(download_model, "ROOT", root), patch.object(
                download_model, "snapshot_download", side_effect=snapshot
            ) as fetch:
                for record in records:
                    with self.subTest(slug=record["model"]["slug"]):
                        download_model.download_record(record, None, None)
                        expected = (root / "artifacts" / record["artifact"]["local_path"]).parent
                        self.assertEqual(Path(fetch.call_args.kwargs["local_dir"]), expected)
                        self.assertEqual((root / "README.md").read_text(), "project readme")

    def test_explicit_output_overrides_sidecar_destination(self):
        record = json.loads((download_model.INDEX_DIR /
            "Qwen3-Coder-480B-A35B-Instruct-UD-Q4_K_XL.gguf.json").read_text())
        with patch.object(download_model, "snapshot_download", return_value="/tmp/result") as fetch:
            download_model.download_record(record, Path("/tmp/chosen"), None)
        self.assertEqual(fetch.call_args.kwargs["local_dir"], "/tmp/chosen")

    def test_sharded_gguf_keeps_hub_subdirectory_under_artifacts(self):
        record = json.loads((download_model.INDEX_DIR / "Qwen3-Coder-Next-Q6_K.gguf.json").read_text())
        with patch.object(download_model, "hf_hub_download", return_value="/tmp/mock") as fetch:
            download_model.download_record(record, None, None)
        self.assertGreater(fetch.call_count, 1)
        for call in fetch.call_args_list:
            self.assertEqual(call.kwargs["local_dir"], str(download_model.ROOT / "artifacts"))
            self.assertTrue(call.kwargs["filename"].startswith("Q6_K/"))


class DownloadEnabledTests(unittest.TestCase):
    def test_fetches_only_missing_enabled_models(self):
        records = [
            {"model": {"slug": "have"}, "artifact": {"filename": "have.gguf"}},
            {"model": {"slug": "need"}, "artifact": {"filename": "need.gguf"}},
            {"model": {"slug": "off"}, "artifact": {"filename": "off.gguf"}},
        ]
        with patch.object(download_model, "load_policy", return_value={"models": {"enabled": ["have", "need"]}}), \
                patch.object(download_model, "artifact_present", side_effect=lambda r, root: r["model"]["slug"] == "have"), \
                patch.object(download_model, "download_record", return_value=[]) as fetch, \
                patch("builtins.print"):
            download_model.download_enabled(records, None)
        self.assertEqual([call.args[0]["model"]["slug"] for call in fetch.call_args_list], ["need"])

    def test_empty_policy_points_at_init(self):
        with patch.object(download_model, "load_policy", return_value={}):
            with self.assertRaises(SystemExit) as raised:
                download_model.download_enabled([], None)
        self.assertIn("./up init", str(raised.exception))
