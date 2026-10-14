from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SHA = "1" * 40
ZERO = "0" * 40


class PushGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        gh = self.directory / "gh"
        gh.write_text('''#!/bin/bash
printf '%s\\n' "$*" >> "$CALL_LOG"
if [ "${GH_FAIL:-}" = 1 ]; then exit 1; fi
if [ "$1" = repo ]; then echo fork/project; exit 0; fi
case "$3" in
  merged) echo MERGED ;;
  missing) exit 1 ;;
  *) echo OPEN ;;
esac
''')
        gh.chmod(0o755)
        self.env = {**os.environ, "PATH": f"{self.directory}:/usr/bin:/bin", "CALL_LOG": str(self.directory / "calls")}

    def run_guard(self, refs: list[tuple[str, str]], **env: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["/bin/bash", str(ROOT / "scripts/check-branch-not-merged.sh"), "fork", "git@github.com:fork/project.git"],
            input="".join(f"refs/heads/local {sha} {ref} {SHA}\n" for ref, sha in refs),
            text=True, capture_output=True, env={**self.env, **env}, cwd=self.directory,
        )

    def test_checks_destination_branch_and_remote(self) -> None:
        result = self.run_guard([("refs/heads/merged", SHA)])
        self.assertEqual(result.returncode, 1, result.stderr)
        calls = (self.directory / "calls").read_text()
        self.assertIn("repo view git@github.com:fork/project.git", calls)
        self.assertIn("pr view merged --repo fork/project", calls)

    def test_checks_every_pushed_branch(self) -> None:
        result = self.run_guard([("refs/heads/open", SHA), ("refs/heads/merged", SHA)])
        self.assertEqual(result.returncode, 1, result.stderr)

    def test_allows_open_missing_tags_and_deletions(self) -> None:
        result = self.run_guard([
            ("refs/heads/open", SHA), ("refs/heads/missing", SHA),
            ("refs/tags/merged", SHA), ("refs/heads/merged", ZERO),
        ])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("pr view merged", (self.directory / "calls").read_text())

    def test_query_failure_does_not_block_push(self) -> None:
        self.assertEqual(self.run_guard([("refs/heads/merged", SHA)], GH_FAIL="1").returncode, 0)

    def test_installer_preserves_existing_hook(self) -> None:
        subprocess.run(["git", "init", "-q", str(self.directory)], check=True)
        hook = self.directory / ".git/hooks/pre-push"
        hook.write_text("existing hook\n")
        result = subprocess.run(
            ["/bin/bash", str(ROOT / "scripts/install-hooks.sh")], cwd=self.directory,
            text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(hook.read_text(), "existing hook\n")

    def test_installed_hook_blocks_second_ref_in_real_push(self) -> None:
        def git(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run(["git", *args], cwd=self.directory, env=self.env,
                                  capture_output=True, text=True, check=True)

        git("init", "-q")
        git("config", "user.name", "Test")
        git("config", "user.email", "test@example.com")
        scripts = self.directory / "scripts"
        scripts.mkdir()
        import shutil
        shutil.copy2(ROOT / "scripts/check-branch-not-merged.sh", scripts)
        git("add", "scripts")
        git("commit", "-qm", "Initial")
        remote = self.directory / "remote.git"
        git("init", "--bare", "-q", str(remote))
        pre_commit = self.directory / "pre-commit"
        pre_commit.write_text("#!/bin/bash\nexit 0\n")
        pre_commit.chmod(0o755)
        for _ in range(2):  # installation is idempotent
            subprocess.run(["/bin/bash", str(ROOT / "scripts/install-hooks.sh")],
                           cwd=self.directory, env=self.env, check=True, capture_output=True)
        result = subprocess.run(
            ["git", "push", str(remote), "HEAD:refs/heads/open", "HEAD:refs/heads/merged"],
            cwd=self.directory, env=self.env, capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("already merged", result.stderr)
        self.assertEqual(git("--git-dir", str(remote), "for-each-ref").stdout, "")
