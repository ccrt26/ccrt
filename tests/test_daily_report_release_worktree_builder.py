#!/usr/bin/env python3
"""
test_daily_report_release_worktree_builder.py — Tests for clean release worktree builder.

Verifies:
A. parse_status_paths extracts correct paths from git status text
B. changed_release_files filters unrelated files
C. copy_release_files rejects DELETE_NOT_ALLOWED
D. RELEASE_ALLOWED_FILES matches RELEASE_ALLOWED_PATTERNS in scope gate
"""
import json
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts" / "build_daily_report_release_worktree.py"
SCOPE_GATE = ROOT / "scripts" / "check_daily_report_release_scope.py"


def _get_builder_module():
    """Import builder module with sys.path hack."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("builder", str(BUILDER))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestParseStatusPaths(unittest.TestCase):
    """A: parse_status_paths extracts correct paths."""

    def test_parse_simple_modified(self):
        """Parse ' M path/to/file.py' → 'path/to/file.py'."""
        mod = _get_builder_module()
        result = mod.parse_status_paths(" M path/to/file.py\n")
        self.assertEqual(result, ["path/to/file.py"])

    def test_parse_untracked(self):
        """Parse '?? new_file.py' → 'new_file.py'."""
        mod = _get_builder_module()
        result = mod.parse_status_paths("?? new_file.py\n")
        self.assertEqual(result, ["new_file.py"])

    def test_parse_multiple_lines(self):
        """Parse multiple lines returns all paths."""
        mod = _get_builder_module()
        text = " M scripts/run_daily_report_html_only.py\n?? tests/test_new.py\n M docs/keystock-dashboard/app.js\n"
        result = mod.parse_status_paths(text)
        self.assertEqual(len(result), 3)
        self.assertIn("scripts/run_daily_report_html_only.py", result)
        self.assertIn("tests/test_new.py", result)
        self.assertIn("docs/keystock-dashboard/app.js", result)

    def test_parse_empty(self):
        """Parse empty string returns empty list."""
        mod = _get_builder_module()
        result = mod.parse_status_paths("")
        self.assertEqual(result, [])

    def test_parse_staged(self):
        """Parse 'M  path/file.py' (staged) → 'path/file.py'."""
        mod = _get_builder_module()
        result = mod.parse_status_paths("M  path/file.py\n")
        self.assertEqual(result, ["path/file.py"])

    def test_parse_renamed(self):
        """Parse 'R  old.py new.py' → """
        mod = _get_builder_module()
        result = mod.parse_status_paths("R  old.py new.py\n")
        self.assertEqual(result, ["old.py new.py"])  # git porcelain R format: "R  old→new"


class TestChangedReleaseFiles(unittest.TestCase):
    """B: changed_release_files filters to allowed list only."""

    def test_filters_allowed(self):
        """Only RELEASE_ALLOWED files should be returned from mixed status."""
        mod = _get_builder_module()
        # Simulate git status output with a mix of allowed and unrelated
        status_lines = (
            " M scripts/run_daily_report_html_only.py\n"
            " M docs/keystock-dashboard/app.js\n"
            "?? tests/test_daily_report_release_scope.py\n"
        )
        # monkeypatch subprocess.run for testing
        import subprocess
        original_run = subprocess.run

        def fake_run(cmd, **kwargs):
            class FakeProc:
                returncode = 0
                stdout = status_lines
                stderr = ""
            return FakeProc()

        subprocess.run = fake_run
        try:
            files = mod.changed_release_files(root=str(ROOT))
        finally:
            subprocess.run = original_run

        self.assertIn("scripts/run_daily_report_html_only.py", files)
        self.assertIn("tests/test_daily_report_release_scope.py", files)
        self.assertNotIn("docs/keystock-dashboard/app.js", files)
        self.assertEqual(len(files), 2)


class TestDeleteNotAllowed(unittest.TestCase):
    """C: copy_release_files rejects DELETE state."""

    def test_delete_raise(self):
        """copy_release_files must raise SystemExit when source file does not exist."""
        mod = _get_builder_module()
        tmpdir = tempfile.mkdtemp()
        try:
            # Try to copy a file that doesn't exist in source
            with self.assertRaises(SystemExit) as ctx:
                mod.copy_release_files(
                    ["scripts/nonexistent_file.py"],
                    tmpdir,
                )
            self.assertIn("DELETE_NOT_ALLOWED", str(ctx.exception))
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestJsonOutputContract(unittest.TestCase):
    """JSON output contract tests for --json mode."""

    def test_log_writes_to_stderr(self):
        """log() must write to stderr, not stdout."""
        mod = _get_builder_module()
        import io
        import contextlib

        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            mod.log("hello")

        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("[INFO] hello", stderr.getvalue())

    def test_run_scope_gate_appends_evidence_flag(self):
        """run_scope_gate with allow_generated_evidence=True must pass --allow-generated-evidence."""
        mod = _get_builder_module()
        calls = []

        original_run = mod._subprocess.run

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            class FakeProc:
                returncode = 0
                stdout = '{"overall":"PASS"}'
                stderr = ""
            return FakeProc()

        mod._subprocess.run = fake_run
        try:
            tmpdir = tempfile.mkdtemp()
            scope_dir = Path(tmpdir) / "scripts"
            scope_dir.mkdir(parents=True, exist_ok=True)
            (scope_dir / "check_daily_report_release_scope.py").write_text("x", encoding="utf-8")
            mod.run_scope_gate(tmpdir, allow_generated_evidence=True)
        finally:
            mod._subprocess.run = original_run
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

        self.assertIn("--allow-generated-evidence", calls[0])

    def test_run_scope_gate_no_flag_by_default(self):
        """run_scope_gate default must NOT pass --allow-generated-evidence."""
        mod = _get_builder_module()
        calls = []

        original_run = mod._subprocess.run

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            class FakeProc:
                returncode = 0
                stdout = '{"overall":"PASS"}'
                stderr = ""
            return FakeProc()

        mod._subprocess.run = fake_run
        try:
            tmpdir = tempfile.mkdtemp()
            scope_dir = Path(tmpdir) / "scripts"
            scope_dir.mkdir(parents=True, exist_ok=True)
            (scope_dir / "check_daily_report_release_scope.py").write_text("x", encoding="utf-8")
            mod.run_scope_gate(tmpdir, allow_generated_evidence=False)
        finally:
            mod._subprocess.run = original_run
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

        self.assertNotIn("--allow-generated-evidence", calls[0])


class TestAllowedFileListMatchesScopeGate(unittest.TestCase):
    """D: RELEASE_ALLOWED_FILES must match RELEASE_ALLOWED_PATTERNS exactly."""

    def test_lists_are_identical(self):
        """Both scripts must have identical release allowed file sets."""
        # Import builder
        import importlib.util
        spec = importlib.util.spec_from_file_location("builder", str(BUILDER))
        builder_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder_mod)

        # Import scope gate
        spec2 = importlib.util.spec_from_file_location("scope_gate", str(SCOPE_GATE))
        scope_mod = importlib.util.module_from_spec(spec2)
        spec2.loader.exec_module(scope_mod)

        builder_files = set(builder_mod.RELEASE_ALLOWED_FILES)
        scope_patterns = set(scope_mod.RELEASE_ALLOWED_PATTERNS)

        # Both sets must be identical
        self.assertEqual(
            builder_files, scope_patterns,
            f"RELEASE_ALLOWED mismatch. "
            f"Builder has {builder_files - scope_patterns}, "
            f"Scope has {scope_patterns - builder_files}"
        )


if __name__ == "__main__":
    unittest.main()
