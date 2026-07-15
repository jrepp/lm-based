from __future__ import annotations

import json
import unittest
from pathlib import Path

from lm_launcher.model_identity import acceptable_model_ids


def _write_sidecar(dir_path: Path, slug: str, local_path: str, name: str) -> None:
    record = {
        "model": {"slug": slug},
        "artifact": {"local_path": local_path},
    }
    (dir_path / name).write_text(json.dumps(record))


class AcceptableModelIdsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(__file__).resolve().parent / "_tmp_model_identity"
        self.models = self.tmp / "models"
        self.models.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        for path in self.models.glob("*.json"):
            path.unlink()
        self.models.rmdir()
        self.tmp.rmdir()

    def test_mlx_sidecar_yields_directory_path_and_basename(self) -> None:
        _write_sidecar(
            self.models,
            slug="ternary-bonsai-27b-mlx-2bit",
            local_path="Ternary-Bonsai-27B-MLX-2bit/config.json",
            name="Ternary-Bonsai-27B-MLX-2bit.json",
        )
        ids = acceptable_model_ids(self.models, "ternary-bonsai-27b-mlx-2bit", repo_root="/repo")
        # mlx_lm reports the absolute model directory; basename covers the rare
        # case where a backend reports just the dir name.
        self.assertIn("/repo/Ternary-Bonsai-27B-MLX-2bit", ids)
        self.assertIn("Ternary-Bonsai-27B-MLX-2bit", ids)
        self.assertIn("ternary-bonsai-27b-mlx-2bit", ids)

    def test_gguf_sidecar_still_includes_slug(self) -> None:
        # llama-server reports the alias (== slug); the directory-derived ids are
        # harmless extras that simply never match in practice.
        _write_sidecar(
            self.models,
            slug="qwen36-27b-q6k",
            local_path="Qwen3.6-27B-Q6_K.gguf",
            name="Qwen3.6-27B-Q6_K.gguf.json",
        )
        ids = acceptable_model_ids(self.models, "qwen36-27b-q6k", repo_root="/repo")
        self.assertIn("qwen36-27b-q6k", ids)

    def test_unknown_slug_falls_back_to_slug_only(self) -> None:
        _write_sidecar(
            self.models,
            slug="ternary-bonsai-27b-mlx-2bit",
            local_path="Ternary-Bonsai-27B-MLX-2bit/config.json",
            name="Ternary-Bonsai-27B-MLX-2bit.json",
        )
        ids = acceptable_model_ids(self.models, "does-not-exist", repo_root="/repo")
        self.assertEqual(ids, ["does-not-exist"])

    def test_real_repo_sidecar_resolves_to_absolute_path(self) -> None:
        # Exercises the actual committed sidecar against the real repo root.
        repo_root = Path(__file__).resolve().parents[1]
        ids = acceptable_model_ids(repo_root / "models", "ternary-bonsai-27b-mlx-2bit", repo_root)
        self.assertIn(str(repo_root / "Ternary-Bonsai-27B-MLX-2bit"), ids)
        self.assertIn("ternary-bonsai-27b-mlx-2bit", ids)


if __name__ == "__main__":
    unittest.main()
