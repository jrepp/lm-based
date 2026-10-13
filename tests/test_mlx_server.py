from __future__ import annotations

import types
import unittest
from pathlib import Path

try:
    from lm_launcher.mlx_server import build_args, default_kev_repo_dir
except ModuleNotFoundError as exc:
    if exc.name in {"pydantic", "pydantic_settings"}:
        build_args = None
    else:
        raise


@unittest.skipIf(build_args is None, "pydantic launcher dependencies are not installed")
class MlxServerArgsTests(unittest.TestCase):
    def _settings(self, **overrides: object) -> object:
        base: dict[str, object] = {
            "model_path": Path("/models/Ternary-Bonsai-27B-MLX-2bit/config.json"),
            "host": "127.0.0.1",
            "port": 8001,
            "temperature": 0.7,
            "top_p": 0.95,
            "top_k": 20,
            "backend_python": "3.14",
        }
        base.update(overrides)
        return types.SimpleNamespace(**base)

    def test_builds_mlx_lm_server_command_with_model_directory(self) -> None:
        settings = self._settings()  # type: ignore[arg-type]
        args = build_args(settings)

        # Non-deprecated mlx_lm.server console script via uv; --python follows
        # the per-model backend_python setting (defaults to the project pin).
        self.assertEqual(args[:3], ["uv", "run", "--python"])
        self.assertEqual(args[3], settings.backend_python)
        self.assertEqual(args[args.index("--with") + 1], "mlx_lm")
        self.assertIn("mlx_lm.server", args)
        # The model is passed as the directory (config.json's parent), not the file.
        self.assertIn("--model", args)
        self.assertEqual(
            args[args.index("--model") + 1],
            "/models/Ternary-Bonsai-27B-MLX-2bit",
        )
        self.assertEqual(args[args.index("--host") + 1], "127.0.0.1")
        self.assertEqual(args[args.index("--port") + 1], "8001")

    def test_backend_python_override_propagates_to_uv(self) -> None:
        # Different models can pin a different backend Python via BACKEND_PYTHON.
        settings = self._settings(backend_python="3.11")  # type: ignore[arg-type]
        args = build_args(settings)
        self.assertEqual(args[args.index("--python") + 1], "3.11")

    def test_includes_upstream_sampler_defaults(self) -> None:
        args = build_args(self._settings())  # type: ignore[arg-type]
        self.assertEqual(args[args.index("--temp") + 1], "0.7")
        self.assertEqual(args[args.index("--top-p") + 1], "0.95")
        self.assertEqual(args[args.index("--top-k") + 1], "20")

    def test_omits_sampler_flags_when_unset(self) -> None:
        args = build_args(
            self._settings(temperature=None, top_p=None, top_k=None)  # type: ignore[arg-type]
        )
        self.assertNotIn("--temp", args)
        self.assertNotIn("--top-p", args)
        self.assertNotIn("--top-k", args)


@unittest.skipIf(build_args is None, "pydantic launcher dependencies are not installed")
class MlxKevArgsTests(unittest.TestCase):
    def _settings(self, **overrides: object) -> object:
        base: dict[str, object] = {
            "model_path": Path("/models/kev-4b-mlx-8bit/config.json"),
            "profile": "mlx-kev",
            "kev_repo_dir": None,
            "kev_python": "3.13",
            "host": "127.0.0.1",
            "port": 8008,
            "ctx_size": 65536,
            "alias": "kev-4b-mlx-8bit",
            "temperature": None,
            "top_p": None,
            "top_k": None,
        }
        base.update(overrides)
        return types.SimpleNamespace(**base)

    def test_builds_kev_serve_command_against_weights_directory(self) -> None:
        import tempfile
        from pathlib import Path as _Path

        with tempfile.TemporaryDirectory() as tmp:
            repo = _Path(tmp) / "kev"
            repo.mkdir()
            (repo / "pyproject.toml").write_text("[project]\nname = 'kev'\n")
            args = build_args(self._settings(kev_repo_dir=repo))  # type: ignore[arg-type]

        self.assertEqual(args[:2], ["uv", "run"])
        self.assertEqual(args[args.index("--directory") + 1], str(repo))
        self.assertEqual(args[args.index("--extra") + 1], "serve")
        self.assertTrue(args[args.index("python") + 1].endswith("kev_serve_local.py"))
        # The shim gets the merged weights directory (config.json's parent).
        self.assertEqual(
            args[args.index("--weights") + 1], "/models/kev-4b-mlx-8bit"
        )
        self.assertEqual(args[args.index("--kev-repo") + 1], str(repo))
        self.assertEqual(args[args.index("--host") + 1], "127.0.0.1")
        self.assertEqual(args[args.index("--port") + 1], "8008")

    def test_kev_python_pin_propagates_to_uv(self) -> None:
        import tempfile
        from pathlib import Path as _Path

        with tempfile.TemporaryDirectory() as tmp:
            repo = _Path(tmp) / "kev"
            repo.mkdir()
            (repo / "pyproject.toml").write_text("[project]\nname = 'kev'\n")
            args = build_args(
                self._settings(kev_repo_dir=repo, kev_python="3.12")  # type: ignore[arg-type]
            )

        self.assertEqual(args[args.index("--python") + 1], "3.12")

    def test_default_kev_repo_dir_is_support_kev(self) -> None:
        self.assertEqual(default_kev_repo_dir().name, "kev")


if __name__ == "__main__":
    unittest.main()
