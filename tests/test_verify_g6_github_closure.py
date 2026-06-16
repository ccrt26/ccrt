#!/usr/bin/env python3
"""Tests for verify_g6_github_closure.py — full closure verification.

Tests cover:
- Complete closure → PASS
- Dirty workspace → BLOCK
- Ahead commits → BLOCK
- Missing push_completed → BLOCK
- Missing github_sync_completed → BLOCK
- Archive record without archive_completed → BLOCK
"""

import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_g6_github_closure", ROOT / "scripts/verify_g6_github_closure.py"
)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def run(cmd, cwd=None):
    return subprocess.run(
        cmd, cwd=str(cwd) if cwd else None, text=True, capture_output=True,
        timeout=60, check=True,
    )


def esc(text):
    """Small helper: avoid non-ASCII noise in subprocess calls."""
    return text.encode("utf-8").decode("utf-8")


def make_closure_repo():
    """Create an isolated repo with valid archive and sync records.

    Returns: (td, repo, archive_path, sync_path)
    """
    td = Path(tempfile.mkdtemp(dir="/private/tmp"))
    remote = td / "remote.git"
    repo = td / "repo"
    run(["git", "init", "--bare", str(remote)])
    run(["git", "clone", str(remote), str(repo)])
    run(["git", "-C", str(repo), "config", "user.email", "test@test.com"])
    run(["git", "-C", str(repo), "config", "user.name", "Test"])
    (repo / "README.md").write_text("init\n", encoding="utf-8")
    run(["git", "-C", str(repo), "add", "README.md"])
    run(["git", "-C", str(repo), "commit", "-m", "init"])
    run(["git", "-C", str(repo), "push", "-u", "origin", "master"])

    head = run(["git", "-C", str(repo), "rev-parse", "HEAD"]).stdout.strip()

    # Archive record
    archive_path = td / "archive.json"
    archive_path.write_text(json.dumps({
        "task_id": "UT-VERIFY-CLOSURE",
        "artifact_type": "archive_record",
        "result": "CLOSED",
        "archive_completed": True,
        "generated_at": "2026-06-16T00:00:00+00:00",
    }, ensure_ascii=False), encoding="utf-8")

    # Sync record (outside repo)
    sync_path = td / "sync.json"
    sync_path.write_text(json.dumps({
        "artifact_type": "github_sync_record",
        "run_id": "UT-VERIFY-CLOSURE",
        "archive_record": str(archive_path.resolve()),
        "branch": "master",
        "upstream": "origin/master",
        "archive_valid": True,
        "commit_created": False,
        "push_completed": True,
        "github_sync_completed": True,
        "before_head": head,
        "after_head": head,
        "result": "ALREADY_SYNCED",
        "pushed_to": "origin/master",
        "tag_completed": False,
        "merge_completed": False,
    }, ensure_ascii=False), encoding="utf-8")

    return td, repo, archive_path, sync_path


class TestVerifyG6GitHubClosure(unittest.TestCase):

    def test_full_closure_pass(self):
        """Complete closure with clean repo must return PASS."""
        td, repo, archive_path, sync_path = make_closure_repo()
        result = MOD.verify(str(archive_path), str(sync_path), cwd=str(repo))
        self.assertEqual(result["status"], "PASS", result)
        self.assertTrue(result["archive_completed"])
        self.assertTrue(result["github_sync_completed"])
        self.assertTrue(result["push_completed"])
        self.assertTrue(result["git_status_clean"])
        self.assertEqual(result["ahead_count"], "0")
        self.assertEqual(result["behind_count"], "0")
        self.assertTrue(result["head_equals_upstream"])
        # All 12 checks must pass
        for key, val in result.get("checks", {}).items():
            self.assertTrue(val, f"Check {key} must be True on PASS")

    def test_dirty_workspace_blocks(self):
        """Dirty git status must BLOCK."""
        td, repo, archive_path, sync_path = make_closure_repo()
        (repo / "dirty.txt").write_text("uncommitted\n", encoding="utf-8")
        result = MOD.verify(str(archive_path), str(sync_path), cwd=str(repo))
        self.assertEqual(result["status"], "BLOCK")
        self.assertIn("not clean", result.get("reason", ""))
        self.assertFalse(result["git_status_clean"])

    def test_ahead_commits_blocks(self):
        """Local commits not on remote must BLOCK."""
        td, repo, archive_path, sync_path = make_closure_repo()
        (repo / "extra.txt").write_text("extra commit\n", encoding="utf-8")
        run(["git", "-C", str(repo), "add", "extra.txt"])
        run(["git", "-C", str(repo), "commit", "-m", "extra ahead commit"])
        # Do NOT push — repo is now ahead
        result = MOD.verify(str(archive_path), str(sync_path), cwd=str(repo))
        self.assertEqual(result["status"], "BLOCK", result)
        self.assertNotEqual(result["ahead_count"], "0")

    def test_missing_push_completed_blocks(self):
        """github_sync_record with push_completed=false must BLOCK."""
        td, repo, archive_path, sync_path = make_closure_repo()
        # Overwrite sync record with false push_completed
        head = run(["git", "-C", str(repo), "rev-parse", "HEAD"]).stdout.strip()
        sync_path.write_text(json.dumps({
            "artifact_type": "github_sync_record",
            "run_id": "UT-NO-PUSH",
            "archive_record": str(archive_path.resolve()),
            "push_completed": False,
            "github_sync_completed": True,
            "branch": "master",
            "before_head": head,
            "after_head": head,
        }, ensure_ascii=False), encoding="utf-8")
        result = MOD.verify(str(archive_path), str(sync_path), cwd=str(repo))
        self.assertEqual(result["status"], "BLOCK")
        self.assertFalse(result["push_completed"])

    def test_missing_sync_completed_blocks(self):
        """github_sync_record with github_sync_completed=false must BLOCK."""
        td, repo, archive_path, sync_path = make_closure_repo()
        head = run(["git", "-C", str(repo), "rev-parse", "HEAD"]).stdout.strip()
        sync_path.write_text(json.dumps({
            "artifact_type": "github_sync_record",
            "run_id": "UT-NO-SYNC",
            "archive_record": str(archive_path.resolve()),
            "push_completed": True,
            "github_sync_completed": False,
            "branch": "master",
            "before_head": head,
            "after_head": head,
        }, ensure_ascii=False), encoding="utf-8")
        result = MOD.verify(str(archive_path), str(sync_path), cwd=str(repo))
        self.assertEqual(result["status"], "BLOCK")
        self.assertFalse(result["github_sync_completed"])

    def test_no_archive_completed_blocks(self):
        """Archive record without archive_completed=true must BLOCK."""
        td, repo, archive_path, sync_path = make_closure_repo()
        # Overwrite archive — missing archive_completed field
        archive_path.write_text(json.dumps({
            "artifact_type": "archive_record",
            "result": "CLOSED",
        }, ensure_ascii=False), encoding="utf-8")
        result = MOD.verify(str(archive_path), str(sync_path), cwd=str(repo))
        self.assertEqual(result["status"], "BLOCK")
        self.assertFalse(result["archive_completed"])

    def test_missing_archive_record_blocks(self):
        """Non-existent archive record file must BLOCK."""
        td, repo, _, sync_path = make_closure_repo()
        result = MOD.verify(str(td / "nonexistent.json"), str(sync_path), cwd=str(repo))
        self.assertEqual(result["status"], "BLOCK")

    def test_archive_record_ref_mismatch_blocks(self):
        """github_sync_record.archive_record pointing to a different file must BLOCK."""
        td, repo, archive_path, sync_path = make_closure_repo()
        other_arc = td / "other_archive.json"
        other_arc.write_text(json.dumps({
            "artifact_type": "archive_record",
            "result": "CLOSED",
            "archive_completed": True,
        }), encoding="utf-8")
        # sync record points to archive_path, but we pass other_arc as --archive-record
        result = MOD.verify(str(other_arc), str(sync_path), cwd=str(repo))
        self.assertEqual(result["status"], "BLOCK")
        self.assertIn("ref mismatch", result.get("reason", ""))


if __name__ == "__main__":
    unittest.main()
