#!/usr/bin/env python3
"""Tests for ccrt_user_report_normalizer.py"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ccrt_user_report_normalizer.py"


class TestUserReportNormalizer(unittest.TestCase):
    def run_py(self, args, env=None, expect_code=0):
        merged = os.environ.copy()
        if env:
            merged.update(env)
        proc = subprocess.run(
            [sys.executable] + args,
            cwd=str(ROOT),
            text=True,
            capture_output=True,
            env=merged,
            timeout=30,
        )
        self.assertEqual(proc.returncode, expect_code, proc.stdout + proc.stderr)
        return json.loads(proc.stdout) if proc.stdout else {}

    def test_self_test(self):
        data = self.run_py([str(SCRIPT), "--self-test"])
        self.assertEqual(data["self_test"], "PASS")

    def test_complete_g6_complete(self):
        """G6_COMPLETE status maps to COMPLETE user state."""
        with tempfile.TemporaryDirectory(dir="/private/tmp") as td_str:
            td = Path(td_str)
            ev = td / "ev.json"
            ev.write_text(json.dumps({
                "task_id": "UT-COMPLETE",
                "status": "G6_COMPLETE",
                "archive_completed": True,
                "github_sync_completed": True,
                "push_completed": True,
                "result": "G6_COMPLETE",
                "issues": [],
            }), encoding="utf-8")
            data = self.run_py([str(SCRIPT), "--evidence", str(ev)])
            self.assertEqual(data["user_visible_status"], "COMPLETE")
            self.assertIn("已归档", data["user_visible_message"])
            self.assertIn("已提交 GitHub", data["user_visible_message"])
            self.assertTrue(data["internal_stage_evidence_hidden_from_user"])

    def test_auto_repairing_waiting_signoff(self):
        """WAITING_ROLE_SIGNOFF maps to AUTO_REPAIRING."""
        with tempfile.TemporaryDirectory(dir="/private/tmp") as td_str:
            td = Path(td_str)
            ev = td / "ev.json"
            ev.write_text(json.dumps({
                "task_id": "UT-REPAIR",
                "status": "WAITING_ROLE_SIGNOFF",
                "issues": ["missing_actual_actor"],
            }), encoding="utf-8")
            data = self.run_py([str(SCRIPT), "--evidence", str(ev)])
            self.assertEqual(data["user_visible_status"], "AUTO_REPAIRING")
            self.assertIn("自动修复", data["user_visible_message"])

    def test_block_archive_without_github_sync(self):
        """Archive without github sync maps to BLOCK."""
        with tempfile.TemporaryDirectory(dir="/private/tmp") as td_str:
            td = Path(td_str)
            ev = td / "ev.json"
            ev.write_text(json.dumps({
                "task_id": "UT-BLOCK1",
                "status": "ARCHIVED",
                "archive_completed": True,
                "github_sync_completed": False,
                "push_completed": False,
                "result": "ARCHIVED",
                "issues": [],
            }), encoding="utf-8")
            data = self.run_py([str(SCRIPT), "--evidence", str(ev)])
            self.assertEqual(data["user_visible_status"], "BLOCK")

    def test_block_no_upstream(self):
        """No upstream reason maps to BLOCK."""
        with tempfile.TemporaryDirectory(dir="/private/tmp") as td_str:
            td = Path(td_str)
            ev = td / "ev.json"
            ev.write_text(json.dumps({
                "task_id": "UT-BLOCK2",
                "status": "BLOCK",
                "reason": "no upstream configured for branch master",
                "issues": [],
                "result": "",
            }), encoding="utf-8")
            data = self.run_py([str(SCRIPT), "--evidence", str(ev)])
            self.assertEqual(data["user_visible_status"], "BLOCK")
            self.assertIn("no upstream", data["user_visible_message"].lower())

    def test_internal_fields_do_not_block_when_message_clean(self):
        """Internal fields (forbidden_claims, candidate_only) must not trigger BLOCK
        when user_visible_message is clean."""
        with tempfile.TemporaryDirectory(dir="/private/tmp") as td_str:
            td = Path(td_str)
            ev = td / "ev.json"
            ev.write_text(json.dumps({
                "status": "WAITING_ROLE_SIGNOFF",
                "user_visible_message": "发现问题，系统已打回对应环节自动修复，无需用户处理。",
                "forbidden_claims": ["role_signed_by_orchestrator"],
                "candidate_only": True,
            }), encoding="utf-8")
            data = self.run_py([str(SCRIPT), "--evidence", str(ev)])
            self.assertEqual(data["user_visible_status"], "AUTO_REPAIRING")

    def test_forbidden_phrase_in_user_visible_message_blocks(self):
        """If user_visible_message contains a forbidden phrase, must BLOCK."""
        with tempfile.TemporaryDirectory(dir="/private/tmp") as td_str:
            td = Path(td_str)
            ev = td / "ev.json"
            ev.write_text(json.dumps({
                "status": "G6_COMPLETE",
                "archive_completed": True,
                "github_sync_completed": True,
                "push_completed": True,
                "user_visible_message": "本输出只是 G4 自检候选，不是 G5 PASS",
            }), encoding="utf-8")
            data = self.run_py([str(SCRIPT), "--evidence", str(ev)])
            self.assertEqual(data["user_visible_status"], "BLOCK")
            self.assertIn("话术泄漏", data["user_visible_message"])

    def test_complete_with_archive_record_reference(self):
        """COMPLETE detection via archive_record reference."""
        with tempfile.TemporaryDirectory(dir="/private/tmp") as td_str:
            td = Path(td_str)
            arc = td / "arc.json"
            arc.write_text(json.dumps({
                "artifact_type": "archive_record",
                "result": "CLOSED",
                "archive_completed": True,
            }), encoding="utf-8")
            ev = td / "ev.json"
            ev.write_text(json.dumps({
                "task_id": "UT-COMPLETE2",
                "status": "G6_COMPLETE",
                "archive_record": str(arc),
                "archive_completed": True,
                "github_sync_completed": True,
                "push_completed": True,
                "result": "G6_COMPLETE",
                "issues": [],
            }), encoding="utf-8")
            data = self.run_py([str(SCRIPT), "--evidence", str(ev)])
            self.assertEqual(data["user_visible_status"], "COMPLETE")

    def test_forbidden_phrases_not_in_output(self):
        """The user_visible_message must not contain any forbidden phrases."""
        forbidden = [
            "本输出只是", "不是 G5 PASS", "不是 G6 PASS",
            "等待复查", "等待 G6", "等待归档",
            "未 tag", "未 merge", "未 push",
        ]
        with tempfile.TemporaryDirectory(dir="/private/tmp") as td_str:
            td = Path(td_str)
            ev = td / "ev.json"
            ev.write_text(json.dumps({
                "task_id": "UT-FORBID", "status": "G6_COMPLETE",
                "archive_completed": True, "github_sync_completed": True,
                "push_completed": True, "result": "G6_COMPLETE", "issues": [],
            }), encoding="utf-8")
            data = self.run_py([str(SCRIPT), "--evidence", str(ev)])
            msg = data.get("user_visible_message", "")
            for phrase in forbidden:
                self.assertNotIn(phrase, msg)


if __name__ == "__main__":
    unittest.main()
