"""Tests for git_autosweep index hygiene — isolated temp git repos, no real working-tree modification.

All tests create a throwaway git repo, verify failure-path index cleanup,
and tear down without touching the real project working tree.

Covers:
- auto file commit: index cleanup on failure, no staging on empty, dry-run safety
- unstage_files helper: no-op on clean, removes staged
- three-way classification: auto/pipeline/protected
- pipeline files without token → exit 2
- output fields include workspace_dirty_before/after, exit_policy, protected_files
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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


def _make_pipeline_token(repo):
    """Create a valid pipeline_active.json in the test repo so token checks pass."""
    tok_dir = repo / ".claude"
    tok_dir.mkdir(parents=True, exist_ok=True)
    (tok_dir / "pipeline_active.json").write_text(json.dumps({
        "active": True,
        "executor": "红结",
        "run_id": "UT-TOKEN",
    }))


class TestGitAutosweepIndexHygiene(unittest.TestCase):
    """Verify that failure paths do not leave stale index entries."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.repo = Path(self.td.name)
        _init_repo(self.repo)
        self._saved_test_repo = _gas._TEST_REPO
        _gas._TEST_REPO = self.repo
        self._saved_token_path = _gas.PIPELINE_TOKEN
        _gas.PIPELINE_TOKEN = self.repo / ".claude" / "pipeline_active.json"

    def tearDown(self):
        _gas._TEST_REPO = self._saved_test_repo
        _gas.PIPELINE_TOKEN = self._saved_token_path
        self.td.cleanup()

    # ----------------------------------------------------------------
    # commit_code_files
    # ----------------------------------------------------------------
    def test_commit_code_files_cleans_index_on_commit_failure(self):
        """When commit fails (pre-commit hook), staged_count must be 0."""
        _install_failing_hook(self.repo)
        _make_pipeline_token(self.repo)
        (self.repo / "scripts").mkdir(parents=True, exist_ok=True)
        (self.repo / "scripts/test.py").write_text("test data")
        result = _gas.commit_code_files(["scripts/test.py"], "protected", dry_run=False)
        self.assertEqual(result, [])  # commit failed
        self.assertEqual(_count_staged(self.repo), 0)

    def test_commit_code_files_no_staging_when_no_files(self):
        """Empty files list must not stage anything."""
        result = _gas.commit_code_files([], "pipeline", dry_run=False)
        self.assertEqual(result, [])
        self.assertEqual(_count_staged(self.repo), 0)

    def test_commit_code_files_report_only_no_staging(self):
        """dry_run=True must not stage any files."""
        _make_pipeline_token(self.repo)
        (self.repo / "scripts").mkdir(parents=True, exist_ok=True)
        (self.repo / "scripts/test.py").write_text("report only")
        result = _gas.commit_code_files(["scripts/test.py"], "protected", dry_run=True)
        self.assertNotEqual(result, [])  # returns dry-run placeholder
        self.assertEqual(_count_staged(self.repo), 0)

    def test_commit_code_files_needs_token(self):
        """Without pipeline token, commit_code_files returns empty."""
        (self.repo / "scripts").mkdir(parents=True, exist_ok=True)
        (self.repo / "scripts/test.py").write_text("no token")
        result = _gas.commit_code_files(["scripts/test.py"], "protected", dry_run=False)
        self.assertEqual(result, [])
        self.assertEqual(_count_staged(self.repo), 0)

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


class TestGitAutosweepPipelineClassification(unittest.TestCase):
    """Verify three-way classification: auto/pipeline/protected."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.repo = Path(self.td.name)
        _init_repo(self.repo)
        self._saved_test_repo = _gas._TEST_REPO
        _gas._TEST_REPO = self.repo

    def tearDown(self):
        _gas._TEST_REPO = self._saved_test_repo
        self.td.cleanup()

    def test_scripts_py_is_protected(self):
        """scripts/*.py must be classified as protected, not pipeline or auto."""
        auto, pipeline, protected = _gas.classify_files(["scripts/pipeline_engine.py"])
        self.assertIn("scripts/pipeline_engine.py", protected)
        self.assertNotIn("scripts/pipeline_engine.py", auto)
        self.assertNotIn("scripts/pipeline_engine.py", pipeline)

    def test_tests_py_is_protected(self):
        """tests/*.py must be classified as protected."""
        auto, pipeline, protected = _gas.classify_files(["tests/test_something.py"])
        self.assertIn("tests/test_something.py", protected)
        self.assertNotIn("tests/test_something.py", pipeline)

    def test_github_workflow_is_protected(self):
        """.github/workflows/*.yml must be classified as protected."""
        auto, pipeline, protected = _gas.classify_files([".github/workflows/test.yml"])
        self.assertIn(".github/workflows/test.yml", protected)

    def test_codefile_py_is_pipeline(self):
        """代码文件/*.py must be classified as pipeline."""
        auto, pipeline, protected = _gas.classify_files(["代码文件/tools/git_autosweep.py"])
        self.assertIn("代码文件/tools/git_autosweep.py", pipeline)

    def test_data_csv_is_auto(self):
        """Data files not under pipeline/protected dirs stay auto."""
        auto, pipeline, protected = _gas.classify_files(["data/report.csv"])
        self.assertIn("data/report.csv", auto)

    def test_runtime_json_is_auto(self):
        """运行产物/*.json must be auto."""
        auto, pipeline, protected = _gas.classify_files(["运行产物/sample.json"])
        self.assertIn("运行产物/sample.json", auto)

    def test_codefile_json_is_pipeline(self):
        """代码文件/*.json must be pipeline (PIPELINE_EXTENSIONS includes .json)."""
        auto, pipeline, protected = _gas.classify_files(["代码文件/settings.json"])
        self.assertIn("代码文件/settings.json", pipeline)

    def test_scripts_non_py_file_also_protected(self):
        """scripts/*.yaml or any extension is protected (PROTECTED_DIRS all extensions)."""
        auto, pipeline, protected = _gas.classify_files(["scripts/config.yaml"])
        self.assertIn("scripts/config.yaml", protected)


class TestGitAutosweepOutputExitCodes(unittest.TestCase):
    """Verify exit codes and output fields for --commit --push scenarios."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.repo = Path(self.td.name)
        _init_repo(self.repo)
        self._saved_test_repo = _gas._TEST_REPO
        _gas._TEST_REPO = self.repo
        self._saved_token = _gas.PIPELINE_TOKEN
        _gas.PIPELINE_TOKEN = self.repo / ".claude" / "pipeline_active.json"

    def tearDown(self):
        _gas._TEST_REPO = self._saved_test_repo
        _gas.PIPELINE_TOKEN = self._saved_token
        self.td.cleanup()

    def test_clean_workspace_returns_0_no_changes(self):
        """No changed files → exit 0, exit_policy=no_changes."""
        with patch.object(sys, "argv", ["git_autosweep.py"]):
            try:
                _gas.main()
            except SystemExit as e:
                self.fail(f"Unexpected exit: {e.code}")

    def test_pipeline_without_token_exits_2(self):
        """Pipeline files without token → exit 2 (via main)."""
        (self.repo / "代码文件").mkdir(parents=True, exist_ok=True)
        (self.repo / "代码文件" / "test_script.py").write_text("x=1")
        if _gas.PIPELINE_TOKEN.exists():
            _gas.PIPELINE_TOKEN.unlink()
        with patch.object(sys, "argv", ["git_autosweep.py", "--commit", "--push"]):
            with self.assertRaises(SystemExit) as ctx:
                _gas.main()
            self.assertEqual(ctx.exception.code, 2)

    def test_protected_without_token_exits_2(self):
        """Protected files without token → exit 2."""
        (self.repo / "scripts").mkdir(parents=True, exist_ok=True)
        (self.repo / "scripts" / "test_script.py").write_text("x=1")
        if _gas.PIPELINE_TOKEN.exists():
            _gas.PIPELINE_TOKEN.unlink()
        with patch.object(sys, "argv", ["git_autosweep.py", "--commit", "--push"]):
            with self.assertRaises(SystemExit) as ctx:
                _gas.main()
            self.assertEqual(ctx.exception.code, 2)

    def test_report_only_has_workspace_dirty_fields(self):
        """Report-only output must have workspace_dirty_before/after and exit_policy."""
        (self.repo / "data.txt").write_text("test")
        captured = []
        with patch.object(sys, "argv", ["git_autosweep.py"]):
            with patch.object(sys.stdout, "write") as mock_write:
                mock_write.side_effect = lambda s: captured.append(s)
                try:
                    _gas.main()
                except SystemExit:
                    pass
        all_text = "".join(captured)
        for line in all_text.split("\n"):
            if line.strip().startswith("{"):
                data = json.loads(line)
                self.assertIn("workspace_dirty_before", data)
                self.assertIn("workspace_dirty_after", data)
                self.assertIn("exit_policy", data)
                self.assertIn("protected_files", data)
                self.assertIn("pipeline_files", data)
                self.assertIn("auto_files", data)
                self.assertEqual(data["exit_policy"], "report_only")
                break
        else:
            self.fail("No JSON output found in report-only mode")

    def test_report_only_shows_protected_files(self):
        """Report-only mode shows protected_files in JSON output."""
        (self.repo / "scripts").mkdir(parents=True, exist_ok=True)
        (self.repo / "scripts" / "test.py").write_text("protected")
        captured = []
        with patch.object(sys, "argv", ["git_autosweep.py"]):
            with patch.object(sys.stdout, "write") as mock_write:
                mock_write.side_effect = lambda s: captured.append(s)
                try:
                    _gas.main()
                except SystemExit:
                    pass
        all_text = "".join(captured)
        has_protected = False
        for line in all_text.split("\n"):
            if line.strip().startswith("{"):
                data = json.loads(line)
                has_protected = True
                self.assertEqual(data.get("protected_files"), 1,
                                 f"Expected protected_files=1, got {data}")
                break
        self.assertTrue(has_protected, "No JSON output with protected_files")
        self.assertIn("protected", all_text)


if __name__ == "__main__":
    unittest.main()
