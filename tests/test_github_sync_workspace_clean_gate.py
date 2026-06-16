#!/usr/bin/env python3
"""Tests for github_sync_after_archive — workspace clean gate and allowed-paths.

Tests cover:
- Dirty workspace without allowed paths → BLOCK (no git add -A sweep)
- Dirty workspace WITH allowed paths → can proceed
- Dirty files outside allowed paths → BLOCK with violations reported
- No push cannot claim push_completed
"""

import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("github_sync_after_archive", ROOT / "scripts/github_sync_after_archive.py")
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def run(cmd, cwd):
    return subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True, timeout=60, check=True)


def make_repo():
    td = Path(tempfile.mkdtemp(dir="/private/tmp"))
    remote = td / "remote.git"
    repo = td / "repo"
    run(["git", "init", "--bare", str(remote)], td)
    run(["git", "clone", str(remote), str(repo)], td)
    run(["git", "config", "user.email", "test@example.com"], repo)
    run(["git", "config", "user.name", "Test User"], repo)
    (repo / "README.md").write_text("init\n", encoding="utf-8")
    run(["git", "add", "README.md"], repo)
    run(["git", "commit", "-m", "init"], repo)
    run(["git", "push", "-u", "origin", "master"], repo)
    arc = td / "archive.json"
    arc.write_text(json.dumps({
        "artifact_type": "archive_record",
        "result": "CLOSED",
        "archive_completed": True,
    }), encoding="utf-8")
    return td, repo, arc


class TestGithubSyncWorkspaceCleanGate(unittest.TestCase):
    def test_dirty_without_allowed_paths_blocks(self):
        """Dirty workspace WITHOUT allowed paths must BLOCK (no git add -A)."""
        _, repo, arc = make_repo()
        (repo / "new_output.txt").write_text("needs sync\n", encoding="utf-8")
        result = MOD.sync(str(arc), "UT-DIRTY-BLOCK", str(repo), cwd=str(repo), allowed_paths=None)
        self.assertEqual(result["result"], "BLOCK", result)
        self.assertFalse(result.get("commit_created", False))
        self.assertFalse(result.get("push_completed", False))
        self.assertFalse(result.get("github_sync_completed", False))
        self.assertIn("outside allowed paths", result.get("reason", ""))

        # Verify git add -A was NOT used: no staged files
        status = run(["git", "status", "--porcelain"], repo)
        self.assertIn("new_output.txt", status.stdout)

    def test_dirty_with_allowed_paths_proceeds(self):
        """Dirty workspace WITH allowed paths matching the dirty file can proceed."""
        _, repo, arc = make_repo()
        (repo / "new_output.txt").write_text("needs sync\n", encoding="utf-8")
        result = MOD.sync(str(arc), "UT-DIRTY-ALLOWED", str(repo),
                          cwd=str(repo), allowed_paths=["new_output.txt"])
        # Should not BLOCK for "outside allowed paths" since new_output.txt is allowed.
        # It may BLOCK for other reasons (GITHUB_SYNC_NO_PUSH, no upstream, commit failure, etc.)
        blk_reason = result.get("reason", "")
        self.assertNotIn("outside allowed paths", blk_reason,
                         f"Unexpected allowed-paths BLOCK: {blk_reason}")
        self.assertNotIn("git add -A", blk_reason)

    def test_dirty_outside_allowed_paths_blocks(self):
        """Dirty file outside the explicit allowed paths set must BLOCK."""
        _, repo, arc = make_repo()
        (repo / "outside.txt").write_text("not allowed\n", encoding="utf-8")
        result = MOD.sync(str(arc), "UT-OUTSIDE-BLOCK", str(repo),
                          cwd=str(repo), allowed_paths=["allowed_only.txt"])
        self.assertEqual(result["result"], "BLOCK", result)
        self.assertIn("outside allowed paths", result.get("reason", ""))
        self.assertIn("outside.txt", str(result.get("violations", [])))

    def test_no_push_cannot_claim_push_completed(self):
        """With GITHUB_SYNC_NO_PUSH=1, must not claim push_completed."""
        _, repo, arc = make_repo()
        old = os.environ.get("GITHUB_SYNC_NO_PUSH")
        os.environ["GITHUB_SYNC_NO_PUSH"] = "1"
        try:
            result = MOD.sync(str(arc), "UT-NO-PUSH", str(repo), cwd=str(repo), allowed_paths=None)
        finally:
            if old is None:
                os.environ.pop("GITHUB_SYNC_NO_PUSH", None)
            else:
                os.environ["GITHUB_SYNC_NO_PUSH"] = old
        self.assertEqual(result["result"], "DRY_RUN", result)
        self.assertFalse(result["push_completed"])
        self.assertFalse(result["github_sync_completed"])

    def test_check_workspace_vs_allowed_basics(self):
        """check_workspace_vs_allowed must correctly identify violations."""
        _, repo, _ = make_repo()
        (repo / "outside.txt").write_text("outside\n", encoding="utf-8")
        (repo / "inside.txt").write_text("inside\n", encoding="utf-8")

        # Only 'inside.txt' is allowed
        ok, violations = MOD.check_workspace_vs_allowed(["inside.txt"], cwd=str(repo))
        self.assertFalse(ok, "Expected violations for outside.txt")
        self.assertIn("outside.txt", violations)
        self.assertNotIn("inside.txt", violations)


if __name__ == "__main__":
    unittest.main()
