#!/usr/bin/env python3
"""
test_daily_report_single_authority.py — Single-authority contract tests

Tests that:
1. --write is deprecated (exits non-zero, no formal write)
2. --promote internally runs release gate
3. generate_one() requires staging_dir (no direct formal write)
4. check_daily_release_gate.py has P0-H D07
5. No "贬破" in report template
"""
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class TestSingleAuthority(unittest.TestCase):

    def test_write_is_deprecated(self):
        """--write must exit non-zero with deprecation message."""
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "run_daily_report_html_only.py"),
             "--date", "20260616", "--write"],
            capture_output=True, text=True, timeout=30, cwd=str(ROOT)
        )
        self.assertNotEqual(result.returncode, 0,
                            "--write must exit non-zero")
        self.assertIn("deprecated", (result.stdout + result.stderr).lower(),
                      "--write must output deprecation message")

    def test_write_deprecated_in_source(self):
        """Source code must reject --write for direct formal write."""
        source = (SCRIPTS / "run_daily_report_html_only.py").read_text(encoding="utf-8")
        self.assertIn("--write deprecated", source,
                      "source must contain deprecation warning")

    def test_promote_has_release_gate(self):
        """--promote branch must reference check_daily_release_gate.py."""
        source = (SCRIPTS / "run_daily_report_html_only.py").read_text(encoding="utf-8")
        self.assertIn("check_daily_release_gate.py", source,
                      "--promote must call check_daily_release_gate")

    def test_generate_one_requires_staging(self):
        """generate_one() must require staging_dir, not write to REPORT_DIR directly."""
        source = (SCRIPTS / "run_daily_report_html_only.py").read_text(encoding="utf-8")
        # Must error out if staging_dir is None
        self.assertIn("staging_dir required", source,
                      "generate_one must reject missing staging_dir")
        self.assertNotIn("out_dir = REPORT_DIR", source,
                         "generate_one must not fall back to REPORT_DIR")

    def test_release_gate_has_d07(self):
        """check_daily_release_gate.py must include P0-H and d07 contract."""
        source = (SCRIPTS / "check_daily_release_gate.py").read_text(encoding="utf-8")
        self.assertIn("P0-H", source,
                      "release gate must include P0-H")
        self.assertIn("check_daily_d07_v12_contract.py", source,
                      "release gate must call D07 contract checker")

    def test_no_bad_terms(self):
        """Report template must not contain 贬破."""
        source = (SCRIPTS / "run_daily_report_html_only.py").read_text(encoding="utf-8")
        self.assertNotIn("贬破", source,
                         "模板中不得出现贬破")

    def test_promote_blocks_on_release_gate_failure(self):
        """--promote with D07 BLOCK must fail and not promote. (conditional on D07 status)"""
        # Check D07 status first
        d07_result = subprocess.run(
            [sys.executable, str(SCRIPTS / "check_daily_d07_v12_contract.py"),
             "--date", "20260616", "--code", "600114", "--name", "东睦股份"],
            capture_output=True, text=True, timeout=60, cwd=str(ROOT)
        )
        if d07_result.returncode == 0:
            self.skipTest("D07 PASS: promote gate should pass; test only valid when D07 BLOCKs")

        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "run_daily_report_html_only.py"),
             "--date", "20260616",
             "--staging-dir", str(ROOT / "运行产物" / "daily_report_build" / "20260616"),
             "--promote"],
            capture_output=True, text=True, timeout=120, cwd=str(ROOT)
        )
        # D07 is BLOCK, so promote must fail
        combined = (result.stdout + result.stderr).lower()
        self.assertIn("block", combined,
                      "promote should BLOCK when release gate fails")
        self.assertIn("release_gate", combined,
                      "failed gate list must include release_gate")
        if result.returncode == 0:
            # If somehow it doesn't fail, check output for promoted_files
            import json
            try:
                data = json.loads(result.stdout)
                if data.get("promoted_files"):
                    self.fail(f"promote succeeded despite D07 BLOCK: {data['promoted_files']}")
            except json.JSONDecodeError:
                pass  # output should have error message

    def test_closure_blocks_on_release_gate_failure(self):
        """Closure must BLOCK when release gate BLOCKs. (conditional on release gate status)"""
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "verify_daily_production_closure.py"),
             "--date", "20260616"],
            capture_output=True, text=True, timeout=120, cwd=str(ROOT)
        )
        import json
        try:
            data = json.loads(result.stdout)
        except (json.JSONDecodeError, ValueError):
            self.fail(f"closure output not JSON: {result.stdout[:200]}")
        # If release gate has failed (non-zero), verify closure also BLOCKs
        rg_result = subprocess.run(
            [sys.executable, str(SCRIPTS / "check_daily_release_gate.py"),
             "--date", "20260616", "--active-only"],
            capture_output=True, text=True, timeout=120, cwd=str(ROOT)
        )
        if rg_result.returncode != 0:
            self.assertEqual(data["overall"], "BLOCK",
                             "closure must BLOCK when release gate BLOCKs")
            has_release = any("release gate" in f for f in data.get("findings", []))
            self.assertTrue(has_release,
                            "closure findings must mention release gate")


if __name__ == "__main__":
    unittest.main()
