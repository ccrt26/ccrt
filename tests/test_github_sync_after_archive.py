import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestGitHubSyncAfterArchive(unittest.TestCase):
    def run_py(self, args, env=None, expect_code=0, cwd=None):
        merged = os.environ.copy()
        if env:
            merged.update(env)
        proc = subprocess.run(
            [sys.executable] + args,
            cwd=cwd or str(ROOT),
            text=True,
            capture_output=True,
            env=merged,
            timeout=60,
        )
        if expect_code is not None:
            self.assertEqual(proc.returncode, expect_code, proc.stdout + proc.stderr)
        return proc

    def test_self_test(self):
        proc = self.run_py(["scripts/github_sync_after_archive.py", "--self-test"])
        data = json.loads(proc.stdout)
        self.assertEqual(data["self_test"], "PASS")

    def test_missing_archive_record_blocks(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp") as td_str:
            td = Path(td_str)
            proc = self.run_py([
                "scripts/github_sync_after_archive.py",
                "--archive-record", str(td / "nonexistent.json"),
                "--run-id", "UT-GSYNC-MISSING",
                "--output-dir", str(td),
            ], expect_code=2)
            data = json.loads(proc.stdout)
            self.assertEqual(data["result"], "BLOCK")

    def test_invalid_artifact_type_blocks(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp") as td_str:
            td = Path(td_str)
            arc = td / "bad_arc.json"
            arc.write_text(json.dumps({
                "artifact_type": "something_else",
                "result": "CLOSED",
                "archive_completed": True,
            }), encoding="utf-8")
            proc = self.run_py([
                "scripts/github_sync_after_archive.py",
                "--archive-record", str(arc),
                "--run-id", "UT-GSYNC-BADTYPE",
                "--output-dir", str(td),
            ], expect_code=2)
            data = json.loads(proc.stdout)
            self.assertEqual(data["result"], "BLOCK")

    def test_not_closed_blocks(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp") as td_str:
            td = Path(td_str)
            arc = td / "bad_arc.json"
            arc.write_text(json.dumps({
                "artifact_type": "archive_record",
                "result": "BLOCK",
                "archive_completed": False,
            }), encoding="utf-8")
            proc = self.run_py([
                "scripts/github_sync_after_archive.py",
                "--archive-record", str(arc),
                "--run-id", "UT-GSYNC-NOTCLOSED",
                "--output-dir", str(td),
            ], expect_code=2)
            data = json.loads(proc.stdout)
            self.assertEqual(data["result"], "BLOCK")

    def test_archive_not_completed_blocks(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp") as td_str:
            td = Path(td_str)
            arc = td / "bad_arc.json"
            arc.write_text(json.dumps({
                "artifact_type": "archive_record",
                "result": "CLOSED",
                "archive_completed": False,
            }), encoding="utf-8")
            proc = self.run_py([
                "scripts/github_sync_after_archive.py",
                "--archive-record", str(arc),
                "--run-id", "UT-GSYNC-NOTCOMPLETE",
                "--output-dir", str(td),
            ], expect_code=2)
            data = json.loads(proc.stdout)
            self.assertEqual(data["result"], "BLOCK")

    def test_already_synced_from_repo(self):
        """When run from the repo (has upstream), should return DRY_RUN with safety flags for clean workspace."""
        with tempfile.TemporaryDirectory(dir="/private/tmp") as td_str:
            td = Path(td_str)
            arc = td / "arc.json"
            arc.write_text(json.dumps({
                "artifact_type": "archive_record",
                "result": "CLOSED",
                "archive_completed": True,
            }), encoding="utf-8")
            proc = self.run_py([
                str(ROOT / "scripts/github_sync_after_archive.py"),
                "--archive-record", str(arc),
                "--run-id", "UT-GSYNC-REPO",
                "--output-dir", str(td),
            ], env={
                "GITHUB_SYNC_NO_PUSH": "1",
                "GITHUB_SYNC_SKIP_FETCH": "1",
                "GITHUB_SYNC_SKIP_FORBIDDEN": "1",
            }, expect_code=None)  # exit 2 (BLOCK) when workspace dirty, exit 0 (DRY_RUN) when clean
            data = json.loads(proc.stdout)
            self.assertIn(data.get("result"), {"BLOCK", "DRY_RUN"},
                "BLOCK if workspace dirty (unstaged/untracked); DRY_RUN in clean workspace")
            self.assertFalse(data.get("github_sync_completed", True))
            self.assertFalse(data.get("push_completed", True))
            self.assertIn("github_sync_record", data)
            saved_path = Path(data["github_sync_record"])
            saved = json.loads(saved_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["artifact_type"], "github_sync_record")

    def test_dry_run_valid(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp") as td_str:
            td = Path(td_str)
            arc = td / "valid_arc.json"
            arc.write_text(json.dumps({
                "artifact_type": "archive_record",
                "result": "CLOSED",
                "archive_completed": True,
            }), encoding="utf-8")
            proc = self.run_py([
                "scripts/github_sync_after_archive.py",
                "--archive-record", str(arc),
                "--run-id", "UT-GSYNC-DRY",
                "--output-dir", str(td),
                "--dry-run",
            ])
            data = json.loads(proc.stdout)
            self.assertEqual(data["result"], "DRY_RUN")
            self.assertTrue(data["archive_valid"])

    def test_self_test_does_not_pollute_index(self):
        """Verify --self-test never changes the real project's git staged count."""
        # Record initial staged count
        proc_before = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=30,
        )
        before_lines = [l for l in proc_before.stdout.splitlines() if l.strip()]
        before_count = len(before_lines)

        # Run --self-test
        proc = self.run_py(["scripts/github_sync_after_archive.py", "--self-test"])
        data = json.loads(proc.stdout)
        self.assertEqual(data["self_test"], "PASS")

        # Record staged count after
        proc_after = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=30,
        )
        after_lines = [l for l in proc_after.stdout.splitlines() if l.strip()]
        after_count = len(after_lines)

        self.assertEqual(
            before_count, after_count,
            f"--self-test changed staged count from {before_count} to {after_count}. "
            f"Before: {before_lines}, After: {after_lines}",
        )

if __name__ == "__main__":
    unittest.main()
