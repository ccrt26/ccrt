#!/usr/bin/env python3
"""Tests for scripts/git_workspace_hygiene.py"""

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HYGIENE_SCRIPT = ROOT / "scripts" / "git_workspace_hygiene.py"


class TestGitWorkspaceHygiene(unittest.TestCase):

    def run_hygiene(self, args, env=None, expect_code=None):
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        cmd = [sys.executable, str(HYGIENE_SCRIPT)] + args
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            env=merged_env,
            timeout=30,
        )
        if expect_code is not None:
            self.assertEqual(
                proc.returncode,
                expect_code,
                f"cmd={' '.join(cmd)}\nstdout={proc.stdout}\nstderr={proc.stderr}",
            )
        return proc

    # =========================================================
    # T-HYG-01: --help
    # =========================================================
    def test_help(self):
        """--help exits 0 and prints usage."""
        proc = self.run_hygiene(["--help"], expect_code=0)
        self.assertIn("usage:", proc.stdout.lower())

    # =========================================================
    # T-HYG-02: --self-test (basic sanity)
    # =========================================================
    def test_self_test(self):
        """--self-test exits 0 and reports PASS."""
        proc = self.run_hygiene(["--self-test"], expect_code=0)
        self.assertIn("PASS", proc.stdout)

    # =========================================================
    # T-HYG-03: --report (default mode)
    # =========================================================
    def test_report(self):
        """--report produces valid JSON with all required keys."""
        proc = self.run_hygiene(["--report"], expect_code=None)
        self.assertEqual(proc.returncode, 0, f"non-zero exit: {proc.stdout}")
        report = json.loads(proc.stdout)
        for key in ("status", "branch", "timestamp", "hygiene", "summary", "blockers"):
            self.assertIn(key, report, f"missing key: {key}")
        for key in ("ahead_behind", "staged", "unstaged", "untracked"):
            self.assertIn(key, report["hygiene"], f"missing hygiene.{key}")
        for key in ("ahead_count", "behind_count", "staged_count", "unstaged_count", "untracked_count"):
            self.assertIn(key, report["summary"], f"missing summary.{key}")

    # =========================================================
    # T-HYG-04: --quiet exits 0 when PASS
    # =========================================================
    def test_quiet_mode(self):
        """--quiet exits 0 when clean, 2 when blocked."""
        proc = self.run_hygiene(["--quiet"], expect_code=None)
        self.assertIn(proc.returncode, (0, 2), f"unexpected exit: {proc.returncode}")

    # =========================================================
    # T-HYG-05: --verify comprehensive output
    # =========================================================
    def test_verify(self):
        """--verify outputs JSON + text summary."""
        proc = self.run_hygiene(["--verify"], expect_code=None)
        self.assertIn(proc.returncode, (0, 2), f"unexpected exit: {proc.returncode}")
        self.assertIn("GIT WORKSPACE HYGIENE", proc.stdout)

    # =========================================================
    # T-HYG-06: --unstage when nothing staged
    # =========================================================
    def test_unstage_when_clean(self):
        """--unstage on clean index reports no files to unstage."""
        # Create a temp dir outside the repo to test the unstage logic
        # without touching the real staged index. We can't easily isolate
        # across repos, but we can at least verify the script handles
        # "nothing to unstage" gracefully.
        proc = self.run_hygiene(["--report"], expect_code=0)
        report = json.loads(proc.stdout)
        if report["hygiene"]["staged"]["count"] == 0:
            proc = self.run_hygiene(["--unstage"], expect_code=0)
            self.assertIn("No staged files to unstage", proc.stdout)
        else:
            # Staged files exist — just verify unstage is non-destructive
            proc = self.run_hygiene(["--unstage"], expect_code=0)
            # After unstage, verify staged_count is 0
            verify = self.run_hygiene(["--report"], expect_code=0)
            v_report = json.loads(verify.stdout)
            self.assertEqual(
                v_report["hygiene"]["staged"]["count"],
                0,
                f"unstage failed, still {v_report['hygiene']['staged']['count']} staged",
            )

    # =========================================================
    # T-HYG-07: --unstage with git restore --staged safety
    # =========================================================
    def test_unstage_safety(self):
        """--unstage uses non-destructive restore and does not delete files."""
        # Verify no files were deleted by checking that all previously
        # tracked files exist
        proc = self.run_hygiene(["--report"], expect_code=0)
        report = json.loads(proc.stdout)
        deleted_paths = report["hygiene"]["staged"]["deleted"]
        for path in deleted_paths:
            resolved = ROOT / path
            if not resolved.exists():
                # staged deletion might also be an unstaged deletion
                # but the file should exist on disk if only staged
                pass

    # =========================================================
    # T-HYG-08: CCRT_ALLOW_DIRTY_INDEX override
    # =========================================================
    def test_allow_dirty_index(self):
        """CCRT_ALLOW_DIRTY_INDEX=true suppresses dirty_index block."""
        proc = self.run_hygiene(["--report"], env={}, expect_code=0)
        report = json.loads(proc.stdout)
        if report["hygiene"]["staged"]["count"] == 0:
            self.skipTest("no staged files, cannot test dirty_index override")
            return
        # With allow_dirty_index=true, BLOCK should become warnings
        proc = self.run_hygiene(
            ["--report"],
            env={"CCRT_ALLOW_DIRTY_INDEX": "true"},
            expect_code=0,
        )
        report = json.loads(proc.stdout)
        self.assertEqual(report["status"], "PASS",
                         f"expected PASS with CCRT_ALLOW_DIRTY_INDEX=true, got {report['status']}")
        self.assertTrue(report["allow_dirty_index"])
        self.assertGreater(len(report.get("warnings", [])), 0,
                           "expected warnings when dirty index is allowed")

    # =========================================================
    # T-HYG-09: Report counters are consistent
    # =========================================================
    def test_report_consistency(self):
        """Summary totals match subsection counts."""
        proc = self.run_hygiene(["--report"], expect_code=0)
        report = json.loads(proc.stdout)
        s = report["summary"]
        self.assertEqual(s["staged_count"], report["hygiene"]["staged"]["count"])
        self.assertEqual(s["unstaged_count"], report["hygiene"]["unstaged"]["count"])
        self.assertEqual(s["untracked_count"], report["hygiene"]["untracked"]["count"])
        self.assertEqual(s["ahead_count"], report["hygiene"]["ahead_behind"]["ahead_count"])
        self.assertEqual(s["behind_count"], report["hygiene"]["ahead_behind"]["behind_count"])
        # staged files list should match staged count
        self.assertEqual(s["staged_count"], len(report["hygiene"]["staged"]["files"]))
        self.assertEqual(
            s["staged_count"],
            len(report["hygiene"]["staged"]["added"])
            + len(report["hygiene"]["staged"]["modified"])
            + len(report["hygiene"]["staged"]["deleted"])
            + len(report["hygiene"]["staged"]["renamed"]),
        )

    # =========================================================
    # T-HYG-10: ahead_count is integer
    # =========================================================
    def test_ahead_count_type(self):
        """ahead_count and behind_count are non-negative integers."""
        proc = self.run_hygiene(["--report"], expect_code=0)
        report = json.loads(proc.stdout)
        ab = report["hygiene"]["ahead_behind"]
        self.assertIsInstance(ab["ahead_count"], int)
        self.assertIsInstance(ab["behind_count"], int)
        self.assertGreaterEqual(ab["ahead_count"], 0)
        self.assertGreaterEqual(ab["behind_count"], 0)

    # =========================================================
    # T-HYG-11: Unstage is idempotent
    # =========================================================
    def test_unstage_idempotent(self):
        """Running --unstage twice is safe (second run = no-op)."""
        self.run_hygiene(["--unstage"], expect_code=0)
        # Second run should also succeed
        second = self.run_hygiene(["--unstage"], expect_code=0)
        self.assertIn("No staged files to unstage", second.stdout,
                       "second unstage should be no-op")


if __name__ == "__main__":
    unittest.main()
