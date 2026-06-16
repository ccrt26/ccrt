"""Tests for git_autosweep index hygiene — isolated temp git repos, no real working-tree modification.

All tests create a throwaway git repo, verify failure-path index cleanup,
and tear down without touching the real project working tree.
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# The module uses Chinese characters in its filesystem path; Python 3 on macOS handles this.
import 代码文件.tools.git_autosweep as _gas


def _init_repo(path):
    """Initialise a minimal git repo at *path* with one initial commit."""
    subprocess.run(["git", "init"], cwd=path, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test"], cwd=path, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, capture_output=True)
    (path / "README.md").write_text("# test repo")
    subprocess.run(["git", "add", "."], cwd=path, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=path, capture_output=True)


def _install_failing_hook(path):
    """Install a pre-commit hook that always fails."""
    hooks = path / ".git" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    hook = hooks / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 1")
    hook.chmod(0o755)


def _count_staged(path):
    """Return number of files in the staging area."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=path, capture_output=True, text=True
    )
    out = result.stdout.strip()
    return 0 if not out else len(out.split("\n"))


class TestGitAutosweepIndexHygiene(unittest.TestCase):
    """Verify that failure paths do not leave stale index entries."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.repo = Path(self.td.name)
        _init_repo(self.repo)
        # Route git operations to the isolated test repo
        self._saved_test_repo = _gas._TEST_REPO
        _gas._TEST_REPO = self.repo

    def tearDown(self):
        _gas._TEST_REPO = self._saved_test_repo
        self.td.cleanup()

    # ----------------------------------------------------------------
    # commit_auto_files
    # ----------------------------------------------------------------
    def test_commit_auto_files_cleans_index_on_commit_failure(self):
        """When commit fails (pre-commit hook), staged_count must be 0."""
        _install_failing_hook(self.repo)
        (self.repo / "data.txt").write_text("test data")

        result = _gas.commit_auto_files(["data.txt"], dry_run=False)
        self.assertEqual(result, [])  # commit failed
        self.assertEqual(_count_staged(self.repo), 0)

    def test_commit_auto_files_no_staging_when_no_files(self):
        """Empty files list must not stage anything."""
        result = _gas.commit_auto_files([], dry_run=False)
        self.assertEqual(result, [])
        self.assertEqual(_count_staged(self.repo), 0)

    def test_commit_auto_files_report_only_no_staging(self):
        """dry_run=True must not stage any files."""
        (self.repo / "report.txt").write_text("report only")

        result = _gas.commit_auto_files(["report.txt"], dry_run=True)
        self.assertNotEqual(result, [])  # returns dry-run placeholder
        self.assertEqual(_count_staged(self.repo), 0)

    # ----------------------------------------------------------------
    # unstage_files helper
    # ----------------------------------------------------------------
    def test_unstage_files_clean_when_nothing_staged(self):
        """unstage_files on non-staged files must be a safe no-op."""
        (self.repo / "clean.txt").write_text("nothing staged")
        before = _count_staged(self.repo)
        _gas.unstage_files(["clean.txt"])
        self.assertEqual(_count_staged(self.repo), before)

    def test_unstage_files_removes_staged(self):
        """unstage_files must remove previously staged files."""
        (self.repo / "staged.txt").write_text("will unstage")
        subprocess.run(["git", "add", "staged.txt"], cwd=self.repo, capture_output=True)
        self.assertGreater(_count_staged(self.repo), 0)

        _gas.unstage_files(["staged.txt"])
        self.assertEqual(_count_staged(self.repo), 0)


if __name__ == "__main__":
    unittest.main()
