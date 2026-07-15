from __future__ import annotations

import os
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN_SERVER = ROOT / "run-server.py"


def load_run_server() -> types.ModuleType:
    """Exec run-server.py against the current environment and return its module.

    run-server.py captures PROFILE / MODEL_SLUG into module globals at load
    time; MODEL_FILE is read live by the detectors. Backend imports are lazy
    (inside main()), so this never pulls in pydantic or a backend.
    """
    module = types.ModuleType("run_server_under_test")
    module.__file__ = str(RUN_SERVER)
    sys.modules[module.__name__] = module
    code = compile(RUN_SERVER.read_text(), str(RUN_SERVER), "exec")
    exec(code, module.__dict__)  # noqa: S102 - intentional exec for test harness
    return module


class RunServerDispatchTests(unittest.TestCase):
    _ENV_KEYS = ("PROFILE", "MODEL_SLUG", "MODEL_FILE")

    def setUp(self) -> None:
        self._snapshot = dict(os.environ)
        for key in self._ENV_KEYS:
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._snapshot)

    def _select(self, **env: str) -> str:
        for key in self._ENV_KEYS:
            os.environ.pop(key, None)
        os.environ.update(env)
        return load_run_server().select_backend()

    def test_mlx_profile_selects_mlx_backend(self) -> None:
        self.assertEqual(self._select(PROFILE="mlx-bonsai"), "mlx")

    def test_mlx_slug_selects_mlx_backend(self) -> None:
        self.assertEqual(
            self._select(PROFILE="auto", MODEL_SLUG="ternary-bonsai-27b-mlx-2bit"),
            "mlx",
        )

    def test_mlx_model_file_selects_mlx_backend(self) -> None:
        self.assertEqual(
            self._select(PROFILE="auto", MODEL_FILE="Ternary-Bonsai-27B-MLX-2bit"),
            "mlx",
        )

    def test_transformers_profile_not_intercepted_by_mlx(self) -> None:
        self.assertEqual(
            self._select(PROFILE="qwen2.5-coder-transformers"),
            "transformers",
        )

    def test_generic_auto_falls_through_to_llama(self) -> None:
        self.assertEqual(self._select(PROFILE="auto"), "llama")


if __name__ == "__main__":
    unittest.main()
