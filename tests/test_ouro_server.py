from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class OuroPathTests(unittest.TestCase):
    def test_override_paths_survive_chdir(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            checkout = root / "ouro"
            checkout.mkdir()
            (checkout / "server.py").write_text("")
            for override in ("ouro", "~/ouro", str(checkout)):
                with self.subTest(override=override):
                    result = subprocess.run(
                        [sys.executable, "-c", '''
from unittest.mock import patch
from lm_launcher import ouro_server as server
with patch.object(server.os, "execv") as execute:
    root = server.ouro_repo_root()
    server.main()
    binary, argv = execute.call_args.args
    assert binary == str(root / ".venv/bin/python")
    assert server.Path(binary).is_absolute()
    assert server.Path(argv[1]).is_file(), argv[1]
'''], cwd=root, capture_output=True, text=True,
                        env={**os.environ, "HOME": str(root), "PYTHONPATH": str(ROOT), "OURO_REPO_ROOT": override},
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
