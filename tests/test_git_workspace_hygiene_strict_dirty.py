#!/usr/bin/env python3
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def run(cmd, cwd, env=None, check=True):
    merged = os.environ.copy()
    if env:
        merged.update(env)
    proc = subprocess.run(cmd, cwd=str(cwd), env=merged, text=True, capture_output=True, timeout=60)
    if check and proc.returncode != 0:
        raise AssertionError(proc.stderr or proc.stdout)
    return proc

def make_repo():
    repo = Path(tempfile.mkdtemp(dir="/private/tmp"))
    run(["git", "init", "-b", "master"], repo)
    run(["git", "config", "user.email", "test@example.com"], repo)
    run(["git", "config", "user.name", "Test User"], repo)
    (repo / "tracked.txt").write_text("v1\n", encoding="utf-8")
    run(["git", "add", "tracked.txt"], repo)
    run(["git", "commit", "-m", "init"], repo)
    return repo

class TestGitWorkspaceHygieneStrictDirty(unittest.TestCase):
    def run_hygiene(self, repo):
        return run(
            ["python3", str(ROOT / "scripts/git_workspace_hygiene.py"), "--quiet"],
            ROOT,
            env={"CCRT_GIT_ROOT": str(repo)},
            check=False,
        )

    def test_unstaged_tracked_change_blocks(self):
        repo = make_repo()
        (repo / "tracked.txt").write_text("v2\n", encoding="utf-8")
        proc = self.run_hygiene(repo)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("dirty_worktree", proc.stdout)

    def test_untracked_file_blocks(self):
        repo = make_repo()
        (repo / "new.txt").write_text("new\n", encoding="utf-8")
        proc = self.run_hygiene(repo)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("untracked_files", proc.stdout)

    def test_clean_workspace_passes(self):
        repo = make_repo()
        proc = self.run_hygiene(repo)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("PASS", proc.stdout)

if __name__ == "__main__":
    unittest.main()
