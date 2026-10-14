"""Repo-wide guards for failures that have recurred in this repo's history.

Each check names the regression it prevents so a failure explains itself.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Absolute home-directory paths. Sidecar launcher paths pointing at an old
# checkout (/Users/.../d/qwen) were fixed twice and came back; docs linked to
# files that only existed on one machine.
HOME_PATH = re.compile(r"/Users/(?!example/)[^/\s\"'`)<]+/")  # <name> placeholders are fine
# Citations into a local llama.cpp checkout, kept because their line anchors
# have no stable upstream URL.
HOME_PATH_ALLOWED = {
    "docs/llama-server-cache-architecture-explainer.md": "/d/llama.cpp/",
}

# bash 4+ features. macOS runs scripts under /bin/bash 3.2; `mapfile` crashed
# support/model-service on startup (c8a7a0c).
BASH4_FEATURES = {
    "mapfile": re.compile(r"\bmapfile\b"),
    "readarray": re.compile(r"\breadarray\b"),
    "associative array": re.compile(r"\b(?:declare|local|typeset)\s+-[a-zA-Z]*A"),
    "case modification": re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*(?:,,?|\^\^?)\}"),
    "coproc": re.compile(r"\bcoproc\b"),
    "&>> redirect": re.compile(r"&>>"),
}


def tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True
    ).stdout.decode()
    return [ROOT / name for name in out.split("\0") if name]


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
        return None


def first_line(path: Path) -> str:
    text = read_text(path)
    return text.splitlines()[0] if text else ""


class RepoHygieneTests(unittest.TestCase):
    def test_no_absolute_home_paths(self) -> None:
        problems = []
        for path in tracked_files():
            rel = path.relative_to(ROOT).as_posix()
            if rel.startswith("tests/"):
                continue  # fixtures use literal paths as inputs
            text = read_text(path)
            if text is None:
                continue
            allowed = HOME_PATH_ALLOWED.get(rel)
            for number, line in enumerate(text.splitlines(), 1):
                for match in HOME_PATH.finditer(line):
                    rest = line[match.start():]
                    if allowed and allowed in rest.split(")", 1)[0]:
                        continue
                    problems.append(f"{rel}:{number}: {rest[:80]}")
        self.assertEqual(
            problems,
            [],
            "absolute home paths break on other machines and checkouts; use "
            "repo-relative paths (sidecars: launcher.script = \"run-server.py\")",
        )

    def test_uv_scripts_target_the_project_python(self) -> None:
        # Entry scripts drifted back to `--python 3.11` pins three times
        # (f13dbc9, f7c8e85, e9f0e8d; download_model.py again in #1/#5).
        project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["requires-python"]
        problems = []
        for path in tracked_files():
            shebang = first_line(path)
            if not shebang.startswith("#!/usr/bin/env -S uv run"):
                continue
            rel = path.relative_to(ROOT).as_posix()
            text = read_text(path) or ""
            pinned = re.search(r"--python\s+(\S+)", shebang)
            if pinned and pinned.group(1) != project:
                problems.append(f"{rel}: shebang pins --python {pinned.group(1)}, project is {project}")
            inline = re.search(r'^# requires-python = "([^"]+)"', text, re.MULTILINE)
            if "--script" in shebang:
                if not inline or inline.group(1) != project:
                    found = inline.group(1) if inline else "none"
                    problems.append(f"{rel}: inline requires-python {found}, project is {project}")
            elif "# /// script" in text:
                problems.append(f"{rel}: has a PEP 723 block but runs in the project env (no --script)")
        self.assertEqual(problems, [])

    def test_shell_scripts_run_on_macos_bash_3_2(self) -> None:
        problems = []
        for path in tracked_files():
            rel = path.relative_to(ROOT).as_posix()
            shebang = first_line(path)
            if not (rel.endswith(".sh") or re.match(r"#!.*\b(ba)?sh\b", shebang)):
                continue
            for number, line in enumerate((read_text(path) or "").splitlines(), 1):
                code = line.split(" #", 1)[0]
                if code.lstrip().startswith("#"):
                    continue
                for name, pattern in BASH4_FEATURES.items():
                    if pattern.search(code):
                        problems.append(f"{rel}:{number}: {name} needs bash 4+: {line.strip()}")
        self.assertEqual(problems, [], "macOS /bin/bash is 3.2")

    def test_generated_and_local_state_is_gitignored(self) -> None:
        # llama-swap.yaml (e6bd059) and a model snapshot dir (cd63e45) were
        # added to .gitignore only after showing up as untracked files.
        paths = [
            "clawrouter.json",
            "llama-swap.yaml",
            ".env",
            ".runtime/pi/agent/settings.json",
            "runs/20260101T000000Z-example/llama-server.log",
            "artifacts/Example-Q4_K_M.gguf",
            "support/pi/node_modules",  # a dir after npm ci, or a symlink in worktrees
        ]
        def ignored(path: str) -> bool:
            # One path per call: a single unusual path (say, behind a symlink) makes
            # git abort the whole batch.
            check = ["git", "check-ignore", "-q", "--no-index", path]
            return subprocess.run(check, cwd=ROOT, capture_output=True).returncode == 0

        self.assertEqual([path for path in paths if not ignored(path)], [])


    def test_pi_extensions_match_extension_dirs(self) -> None:
        # An extension directory that pi-local does not load (or a loaded path
        # that no longer exists) only shows up as a missing tool in a session.
        from lm_launcher.pi_bootstrap import PI_DIR, PI_EXTENSIONS

        on_disk = {path.parent.name for path in (PI_DIR / "extensions").glob("*/index.ts")}
        loaded = {path.parent.name for path in PI_EXTENSIONS}
        self.assertEqual(loaded, on_disk)

class SidecarValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        spec = importlib.util.spec_from_file_location("route_config", ROOT / "route-config.py")
        self.route_config = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = self.route_config  # dataclasses look up their module
        spec.loader.exec_module(self.route_config)

    def record(self, script: str) -> dict:
        return {
            "_index_path": "models/Example.gguf.json",
            "schema_version": 1,
            "artifact": {"filename": "Example.gguf"},
            "model": {"slug": "example"},
            "launcher": {"profile": "generic", "script": script},
        }

    def test_launcher_script_must_be_repo_relative(self) -> None:
        issues = self.route_config.validate_records([self.record("/Users/someone/d/qwen/run-server.py")])
        self.assertIn("error", [issue.severity for issue in issues])
        issues = self.route_config.validate_records([self.record("run-server.py")])
        self.assertNotIn("error", [issue.severity for issue in issues])


if __name__ == "__main__":
    unittest.main()
