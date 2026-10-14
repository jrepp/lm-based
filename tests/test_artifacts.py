from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lm_launcher.artifacts import artifact_present, artifacts_dir, resolve_artifact
from lm_launcher.model_identity import acceptable_model_ids


class ArtifactResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "artifacts").mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_defaults_to_artifacts_dir(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MODEL_DIR", None)
            self.assertEqual(resolve_artifact("m.gguf", self.root), self.root / "artifacts" / "m.gguf")

    def test_project_root_copy_wins_when_present(self) -> None:
        (self.root / "m.gguf").write_text("x")
        self.assertEqual(resolve_artifact("m.gguf", self.root), self.root / "m.gguf")

    def test_model_dir_override(self) -> None:
        with mock.patch.dict(os.environ, {"MODEL_DIR": "/data/models"}):
            self.assertEqual(artifacts_dir(self.root), Path("/data/models"))

    def test_presence(self) -> None:
        record = {"artifact": {"local_path": "m.gguf"}}
        self.assertFalse(artifact_present(record, self.root, self.root / "artifacts"))
        (self.root / "artifacts" / "m.gguf").write_text("x")
        self.assertTrue(artifact_present(record, self.root, self.root / "artifacts"))
        self.assertFalse(artifact_present({"artifact": {}}, self.root))

    def test_mlx_ids_cover_both_layouts(self) -> None:
        models = self.root / "models"
        models.mkdir()
        (models / "m.json").write_text('{"model": {"slug": "m"}, "artifact": {"local_path": "M-dir/config.json"}}')
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MODEL_DIR", None)
            ids = acceptable_model_ids(models, "m", self.root)
        self.assertIn(str(self.root / "M-dir"), ids)
        self.assertIn(str(self.root / "artifacts" / "M-dir"), ids)
        self.assertIn("M-dir", ids)


if __name__ == "__main__":
    unittest.main()
