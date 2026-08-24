from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from llama_swap.wrapper import LlamaSwap, _running_model_ids


class LlamaSwapWrapperTests(unittest.TestCase):
    def test_running_model_ids_accept_current_response_shape(self) -> None:
        self.assertEqual(
            _running_model_ids({"running": ["test-a", "test-b"]}),
            ["test-a", "test-b"],
        )

    def test_running_model_ids_accept_legacy_response_shape(self) -> None:
        self.assertEqual(
            _running_model_ids([{"id": "test-a"}, {"id": "test-b"}]),
            ["test-a", "test-b"],
        )

    def test_build_args_match_current_binary_flags(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "llama-swap.yaml"
            config.write_text("models: {}\n", encoding="utf-8")
            swap = LlamaSwap(
                config_path=config,
                listen="127.0.0.1:8081",
                watch_config=True,
            )
            with patch("llama_swap.wrapper.ensure_binary", return_value=Path("/bin/llama-swap")):
                args = swap._build_args()

        self.assertEqual(
            args,
            [
                "/bin/llama-swap",
                "--config",
                str(config),
                "--listen",
                "127.0.0.1:8081",
                "--watch-config",
            ],
        )
        self.assertNotIn("--log-level", args)


if __name__ == "__main__":
    unittest.main()
