from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from lm_launcher import pi_run


class PiRunTests(unittest.TestCase):
    def test_run_dir_is_private_self_ignoring_and_removed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            subprocess.run(["git", "init", "-q", str(workspace)], check=True)
            run = pi_run.RunContext(run_id="r1", workspace=workspace, records_root=workspace / "records")
            before = pi_run.untracked_files(workspace)
            tmpdir = pi_run.prepare_run_dir(run)
            (tmpdir / "rows.ndjson").write_text("{}\n")
            self.assertEqual(tmpdir.stat().st_mode & 0o777, 0o700)
            # git never shows the run folder.
            self.assertEqual(pi_run.untracked_files(workspace), before)
            env = pi_run.run_environment(run)
            self.assertEqual(env["TMPDIR"], str(tmpdir))
            self.assertEqual(env["LM_BASED_TRAJECTORY"], str(workspace / "records" / "r1" / "trajectory.jsonl"))
            pi_run.cleanup_run(run)
            self.assertFalse((workspace / pi_run.RUN_DIR_NAME).exists())

    def test_keep_and_concurrent_runs_survive_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            kept = pi_run.RunContext(run_id="keep", workspace=workspace, keep=True)
            other = pi_run.RunContext(run_id="other", workspace=workspace)
            mine = pi_run.RunContext(run_id="mine", workspace=workspace)
            for run in (kept, other, mine):
                pi_run.prepare_run_dir(run)
            pi_run.cleanup_run(kept)
            pi_run.cleanup_run(mine)
            self.assertTrue(kept.run_dir.exists())
            self.assertTrue(other.run_dir.exists())
            self.assertFalse(mine.run_dir.exists())
            self.assertNotIn("LM_BASED_TRAJECTORY", pi_run.run_environment(pi_run.RunContext("x", workspace, trajectory=False)))

    def test_report_lists_new_untracked_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            subprocess.run(["git", "init", "-q", str(workspace)], check=True)
            run = pi_run.RunContext(run_id="r", workspace=workspace, records_root=workspace / ".records")
            (workspace / ".gitignore").write_text(".records/\n")
            before = pi_run.untracked_files(workspace)
            (workspace / "work-log.md").write_text("notes")
            self.assertEqual(pi_run.report_run(run, before), ["work-log.md"])
            self.assertEqual(pi_run.report_run(run, None), [])
            self.assertIsNone(pi_run.untracked_files(Path("/nonexistent-dir")))

    def test_run_child_returns_exit_status(self) -> None:
        self.assertEqual(pi_run.run_child([sys.executable, "-c", "raise SystemExit(7)"]), 7)


if __name__ == "__main__":
    unittest.main()
