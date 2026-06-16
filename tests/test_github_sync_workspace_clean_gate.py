#!/usr/bin/env python3
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
    arc.write_text(json.dumps({"artifact_type": "archive_record", "result": "CLOSED", "archive_completed": True}), encoding="utf-8")
    return td, repo, arc

class TestGithubSyncWorkspaceCleanGate(unittest.TestCase):
    def test_dirty_workspace_is_committed_not_reported_already_synced(self):
        _, repo, arc = make_repo()
        (repo / "new_output.txt").write_text("needs sync\n", encoding="utf-8")
        result = MOD.sync(str(arc), "UT-DIRTY-SYNC", str(repo), cwd=str(repo))
        self.assertEqual(result["result"], "PUSHED", result)
        self.assertTrue(result["commit_created"])
        self.assertTrue(result["github_sync_completed"])
        status = run(["git", "status", "--porcelain"], repo)
        self.assertEqual(status.stdout.strip(), "")

    def test_no_push_cannot_claim_push_completed(self):
        _, repo, arc = make_repo()
        old = os.environ.get("GITHUB_SYNC_NO_PUSH")
        os.environ["GITHUB_SYNC_NO_PUSH"] = "1"
        try:
            result = MOD.sync(str(arc), "UT-NO-PUSH", str(repo), cwd=str(repo))
        finally:
            if old is None:
                os.environ.pop("GITHUB_SYNC_NO_PUSH", None)
            else:
                os.environ["GITHUB_SYNC_NO_PUSH"] = old
        self.assertEqual(result["result"], "DRY_RUN", result)
        self.assertFalse(result["push_completed"])
        self.assertFalse(result["github_sync_completed"])

if __name__ == "__main__":
    unittest.main()
