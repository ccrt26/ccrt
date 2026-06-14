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
        """When run from the repo (has upstream), should return ALREADY_SYNCED with safety flags."""
        with tempfile.TemporaryDirectory(dir="/private/tmp") as td_str:
            td = Path(td_str)
            arc = td / "arc.json"
            arc.write_text(json.dumps({
                "artifact_type": "archive_record",
                "result": "CLOSED",
                "archive_completed": True,
            }), encoding="utf-8")
            proc = self.run_py([
                "scripts/github_sync_after_archive.py",
                "--archive-record", str(arc),
                "--run-id", "UT-GSYNC-REPO",
                "--output-dir", str(td),
            ], env={"GITHUB_SYNC_NO_PUSH": "1", "GITHUB_SYNC_SKIP_FETCH": "1"})
            data = json.loads(proc.stdout)
            self.assertIn(data.get("result"), {"ALREADY_SYNCED", "PUSHED"})
            self.assertTrue(data.get("github_sync_completed", False))
            self.assertTrue(data.get("push_completed", False))
            self.assertIn("github_sync_record", data)
            saved_path = Path(data["github_sync_record"])
            self.assertTrue(saved_path.exists())
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

if __name__ == "__main__":
    unittest.main()
