import unittest
from pathlib import Path
from unittest.mock import patch

from llama_swap import bin, cli


class EnsureVersionTests(unittest.TestCase):
    def test_cli_installs_supported_default_release(self):
        with patch.object(cli, "install_binary", return_value=Path("/tmp/mock")) as install:
            self.assertEqual(cli.cmd_ensure([]), 0)
        self.assertEqual(install.call_args.kwargs["version"], bin.DEFAULT_VERSION)

    def test_explicit_version_is_preserved(self):
        with patch.object(cli, "install_binary", return_value=Path("/tmp/mock")) as install:
            self.assertEqual(cli.cmd_ensure(["--version", "v263"]), 0)
        self.assertEqual(install.call_args.kwargs["version"], "v263")
