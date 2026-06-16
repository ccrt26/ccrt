#!/usr/bin/env python3
"""
test_daily_release_gate_contract.py — Release gate contract tests

Tests that check_daily_release_gate.py:
1. --active-only mode includes P0-H D07 check
2. D07 BLOCK -> release gate BLOCK
3. P0-F accepts "持有待涨" prefix
4. "贬破" never appears in report templates
"""
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class TestReleaseGateContract(unittest.TestCase):

    def test_active_only_includes_d07(self):
        """P0-H must be in active-only mode output."""
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "check_daily_release_gate.py"),
             "--date", "20260616", "--active-only"],
            capture_output=True, text=True, timeout=120, cwd=str(ROOT)
        )
        combined = result.stdout + result.stderr
        self.assertIn("P0-H", combined, "P0-H D07 check must be in active-only mode")

    def test_d07_block_causes_release_gate_block(self):
        """D07 BLOCK means release gate exit != 0."""
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "check_daily_release_gate.py"),
             "--date", "20260616", "--active-only"],
            capture_output=True, text=True, timeout=120, cwd=str(ROOT)
        )
        # If D07 is BLOCK (which it is as of 20260616 without analysis fix),
        # the release gate must exit non-zero
        d07_result = subprocess.run(
            [sys.executable, str(SCRIPTS / "check_daily_d07_v12_contract.py"),
             "--date", "20260616", "--code", "600114", "--name", "东睦股份"],
            capture_output=True, text=True, timeout=60, cwd=str(ROOT)
        )
        if d07_result.returncode != 0:
            # D07 is BLOCK -> release gate must also be BLOCK
            self.assertNotEqual(result.returncode, 0,
                                "release gate must BLOCK when D07 BLOCKs")

    def test_no_贬破_in_template(self):
        """Report template must not contain 贬破."""
        source = (SCRIPTS / "run_daily_report_html_only.py").read_text(encoding="utf-8")
        self.assertNotIn("贬破", source, "模板中不得出现贬破")

    def test_持有待涨_in_template(self):
        """Report template uses 持有待涨 for held stocks."""
        source = (SCRIPTS / "run_daily_report_html_only.py").read_text(encoding="utf-8")
        self.assertIn("持有待涨", source, "模板应使用持有待涨作为动作枚举")

    def test_closure_blocks_on_release_gate_failure(self):
        """Closure must BLOCK when release gate BLOCKs."""
        # Run closure
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "verify_daily_production_closure.py"),
             "--date", "20260616"],
            capture_output=True, text=True, timeout=120, cwd=str(ROOT)
        )
        # Check if release gate is failing
        rg_result = subprocess.run(
            [sys.executable, str(SCRIPTS / "check_daily_release_gate.py"),
             "--date", "20260616", "--active-only"],
            capture_output=True, text=True, timeout=120, cwd=str(ROOT)
        )
        if rg_result.returncode != 0:
            # If release gate fails, closure must also fail
            self.assertIn("release gate", result.stdout + result.stderr,
                          "closure must mention release gate BLOCK")
            # exit code is 2 for BLOCK
            self.assertNotEqual(result.returncode, 0)

    def test_d07_pass_does_not_false_block_release_gate(self):
        """If D07 PASSes, release gate must not BLOCK on P0-H."""
        # Check D07 result first
        d07_result = subprocess.run(
            [sys.executable, str(SCRIPTS / "check_daily_d07_v12_contract.py"),
             "--date", "20260616", "--code", "600114", "--name", "东睦股份"],
            capture_output=True, text=True, timeout=60, cwd=str(ROOT)
        )
        if d07_result.returncode == 0:
            # D07 PASS: release gate must not BLOCK on P0-H
            rg_result = subprocess.run(
                [sys.executable, str(SCRIPTS / "check_daily_release_gate.py"),
                 "--date", "20260616", "--active-only"],
                capture_output=True, text=True, timeout=120, cwd=str(ROOT)
            )
            output = rg_result.stdout + rg_result.stderr
            # P0-H may appear as PASS line (✅); should not appear as FAIL (❌ P0-H)
            self.assertNotIn("❌ P0-H", output,
                             "release gate should not BLOCK on P0-H when D07 passes")
            self.assertNotIn("P0-H: BLOCK", output,
                             "release gate should not BLOCK on P0-H when D07 passes")


if __name__ == "__main__":
    unittest.main()
