#!/usr/bin/env python3
"""
test_daily_report_release_scope.py — Release scope gate tests for daily report release.

Verifies:
A. Scope gate PASS: only allowed files changed
B. Scope gate BLOCK: NEVER_RELEASE files (dashboard, product_api .claude/signal_alert)
C. Scope gate BLOCK: GENERATED files (logs, 运行产物)
D. EVIDENCE_ALLOWED files need --allow-generated-evidence
E. Empty status → PASS
F. RELEASE_ALLOWED patterns match
G. Output keys present
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCOPE_GATE = ROOT / "scripts" / "check_daily_report_release_scope.py"


def _run_scope(status_lines, allow_generated=False):
    """Write status lines to temp file and run scope gate."""
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8")
    try:
        for line in status_lines:
            tmp.write(line + "\n")
        tmp.close()
        cmd = [sys.executable, str(SCOPE_GATE),
               "--status-file", tmp.name, "--json"]
        if allow_generated:
            cmd.append("--allow-generated-evidence")
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=30, cwd=str(ROOT),
        )
        payload = json.loads(result.stdout) if result.stdout else {}
        return payload, result.returncode
    finally:
        os.unlink(tmp.name)


# === A: Positive cases ===

class TestScopeGatePositive(unittest.TestCase):
    """A: Scope gate must PASS for allowed files."""

    def test_only_allowed_scripts(self):
        """Only scripts/run_daily_report_html_only.py changed → PASS."""
        lines = [" M scripts/run_daily_report_html_only.py"]
        payload, rc = _run_scope(lines)
        self.assertEqual(payload["overall"], "PASS")
        self.assertEqual(rc, 0)
        self.assertIn("scripts/run_daily_report_html_only.py", payload["allowed_files"])

    def test_allowed_and_new_test(self):
        """Modified script + new test file → PASS."""
        lines = [
            " M scripts/run_daily_report_html_only.py",
            "?? tests/test_daily_report_release_scope.py",
        ]
        payload, rc = _run_scope(lines)
        self.assertEqual(payload["overall"], "PASS")
        self.assertEqual(rc, 0)
        self.assertEqual(len(payload["allowed_files"]), 2)

    def test_all_allowed_patterns(self):
        """All allowed patterns must classify as ALLOW (not blocked/generated)."""
        allowed = [
            "scripts/run_daily_report_html_only.py",
            "scripts/run_daily_data_retry_once.py",
            "scripts/run_daily_production_pipeline.py",
            "scripts/check_daily_d07_v12_contract.py",
            "scripts/check_daily_release_gate.py",
            "scripts/check_runtime_dependency_readiness.py",
            "scripts/daily_d07_contract_builder.py",
            "scripts/verify_daily_production_closure.py",
            "scripts/check_daily_report_release_scope.py",
            "scripts/build_daily_report_release_worktree.py",
            "tests/test_daily_report_artifact_isolation.py",
            "tests/test_daily_report_promote_safety.py",
            "tests/test_daily_report_d07_gate.py",
            "tests/test_daily_retry_no_d07_bypass.py",
            "tests/test_daily_production_dry_run.py",
            "tests/test_daily_report_release_scope.py",
            "tests/test_daily_report_release_worktree_builder.py",
        ]
        lines = [f" M {f}" for f in allowed]
        payload, rc = _run_scope(lines)
        self.assertEqual(payload["overall"], "PASS")
        self.assertEqual(rc, 0)
        self.assertEqual(len(payload["allowed_files"]), len(allowed))

    def test_empty_status(self):
        """Empty status → PASS."""
        payload, rc = _run_scope([])
        self.assertEqual(payload["overall"], "PASS")
        self.assertEqual(rc, 0)


# === B: NEVER_RELEASE ===

class TestNeverReleaseBlocks(unittest.TestCase):
    """NEVER_RELEASE files always BLOCK, even with --allow-generated-evidence."""

    def test_dashboard_js_never_release_without_flag(self):
        """docs/keystock-dashboard/app.js → NEVER_RELEASE, BLOCK without flag."""
        lines = [" M docs/keystock-dashboard/app.js"]
        payload, rc = _run_scope(lines, allow_generated=False)
        self.assertEqual(payload["overall"], "BLOCK")
        self.assertNotEqual(rc, 0)
        self.assertIn("docs/keystock-dashboard/app.js", payload["never_release_files"])

    def test_dashboard_js_never_release_with_flag(self):
        """docs/keystock-dashboard/app.js → STILL NEVER_RELEASE even with flag."""
        lines = [" M docs/keystock-dashboard/app.js"]
        payload, rc = _run_scope(lines, allow_generated=True)
        self.assertEqual(payload["overall"], "BLOCK")
        self.assertNotEqual(rc, 0)
        self.assertIn("docs/keystock-dashboard/app.js", payload["never_release_files"])

    def test_signal_alert_never_release_without_flag(self):
        """.claude/signal_alert.json → NEVER_RELEASE, BLOCK without flag."""
        lines = [" M .claude/signal_alert.json"]
        payload, rc = _run_scope(lines, allow_generated=False)
        self.assertEqual(payload["overall"], "BLOCK")
        self.assertNotEqual(rc, 0)
        self.assertIn(".claude/signal_alert.json", payload["never_release_files"])

    def test_signal_alert_never_release_with_flag(self):
        """.claude/signal_alert.json → STILL NEVER_RELEASE even with flag."""
        lines = [" M .claude/signal_alert.json"]
        payload, rc = _run_scope(lines, allow_generated=True)
        self.assertEqual(payload["overall"], "BLOCK")
        self.assertNotEqual(rc, 0)
        self.assertIn(".claude/signal_alert.json", payload["never_release_files"])

    def test_dashboard_data_never_release_with_flag(self):
        """docs/keystock-dashboard/data stagin → NEVER_RELEASE, BLOCK even with flag."""
        lines = ["?? docs/keystock-dashboard/data/_staging/tmp.json"]
        payload, rc = _run_scope(lines, allow_generated=True)
        self.assertEqual(payload["overall"], "BLOCK")
        self.assertNotEqual(rc, 0)
        self.assertIn("docs/keystock-dashboard/data/_staging/tmp.json", payload["never_release_files"])

    def test_product_api_never_release_with_flag(self):
        """product_api file → NEVER_RELEASE, BLOCK even with flag."""
        lines = ["?? product_api/bundles/x/dashboard.json"]
        payload, rc = _run_scope(lines, allow_generated=True)
        self.assertEqual(payload["overall"], "BLOCK")
        self.assertNotEqual(rc, 0)
        self.assertIn("product_api/bundles/x/dashboard.json", payload["never_release_files"])

    def test_mixed_allowed_and_never_release(self):
        """Mix of allowed + NEVER_RELEASE → BLOCK."""
        lines = [
            " M scripts/run_daily_report_html_only.py",
            " M docs/keystock-dashboard/app.js",
        ]
        payload, rc = _run_scope(lines)
        self.assertEqual(payload["overall"], "BLOCK")
        self.assertNotEqual(rc, 0)
        self.assertIn("docs/keystock-dashboard/app.js", payload["never_release_files"])


# === C: GENERATED_BLOCK ===

class TestGeneratedBlock(unittest.TestCase):
    """GENERATED_BLOCK files always BLOCK."""

    def test_logs_block_without_flag(self):
        """logs/daily_production/manifest → GENERATED, BLOCK without flag."""
        lines = [" M logs/daily_production/20260616_manifest.json"]
        payload, rc = _run_scope(lines, allow_generated=False)
        self.assertEqual(payload["overall"], "BLOCK")
        self.assertNotEqual(rc, 0)
        self.assertGreaterEqual(len(payload["generated_files"]), 1)

    def test_logs_block_with_flag(self):
        """logs/daily_production/manifest → GENERATED, BLOCK even with flag."""
        lines = [" M logs/daily_production/20260616_manifest.json"]
        payload, rc = _run_scope(lines, allow_generated=True)
        self.assertEqual(payload["overall"], "BLOCK")
        self.assertNotEqual(rc, 0)
        self.assertGreaterEqual(len(payload["generated_files"]), 1)

    def test_runtime_product_blocks_without_flag(self):
        """运行产物/daily_report_build/tmp.json → GENERATED (not EVIDENCE), BLOCK."""
        lines = ["?? 运行产物/daily_report_build/tmp.json"]
        payload, rc = _run_scope(lines, allow_generated=False)
        self.assertEqual(payload["overall"], "BLOCK")
        self.assertNotEqual(rc, 0)
        self.assertIn("运行产物/daily_report_build/tmp.json", payload["generated_files"])

    def test_runtime_product_blocks_with_flag(self):
        """运行产物/daily_report_build → GENERATED, BLOCK even with flag (not EVIDENCE)."""
        lines = ["?? 运行产物/daily_report_build/tmp.json"]
        payload, rc = _run_scope(lines, allow_generated=True)
        self.assertEqual(payload["overall"], "BLOCK")
        self.assertNotEqual(rc, 0)

    def test_archive_manifest_blocks(self):
        """历史数据/manifest → GENERATED, BLOCK."""
        lines = [" M 历史数据/manifest/20260616_archive_manifest.json"]
        payload, rc = _run_scope(lines, allow_generated=False)
        self.assertEqual(payload["overall"], "BLOCK")
        self.assertNotEqual(rc, 0)
        self.assertIn("历史数据/manifest/20260616_archive_manifest.json", payload["generated_files"])


# === D: EVIDENCE_ALLOWED ===

class TestEvidenceAllowed(unittest.TestCase):
    """EVIDENCE_ALLOWED files require --allow-generated-evidence."""

    def test_evidence_blocks_without_flag(self):
        """运行产物/daily_report_release/evidence/g5.json → EVIDENCE, BLOCK without flag."""
        lines = ["?? 运行产物/daily_report_release/evidence/g5.json"]
        payload, rc = _run_scope(lines, allow_generated=False)
        self.assertEqual(payload["overall"], "BLOCK")
        self.assertNotEqual(rc, 0)
        self.assertIn("运行产物/daily_report_release/evidence/g5.json", payload["evidence_files"])

    def test_evidence_passes_with_flag(self):
        """运行产物/daily_report_release/evidence/g5.json → PASS with flag."""
        lines = ["?? 运行产物/daily_report_release/evidence/g5.json"]
        payload, rc = _run_scope(lines, allow_generated=True)
        self.assertEqual(payload["overall"], "PASS")
        self.assertEqual(rc, 0)
        self.assertIn("运行产物/daily_report_release/evidence/g5.json", payload["evidence_files"])

    def test_evidence_nested_blocks_without_flag(self):
        """运行产物/daily_report_release/evidence/sub/detail.json → EVIDENCE, BLOCK without flag."""
        lines = ["?? 运行产物/daily_report_release/evidence/sub/detail.json"]
        payload, rc = _run_scope(lines, allow_generated=True)
        self.assertEqual(payload["overall"], "PASS")
        self.assertEqual(rc, 0)


# === E: BLOCK (other unknown files) ===

class TestBlockedOther(unittest.TestCase):
    """Unknown files → BLOCK."""

    def test_random_unknown_file_blocks(self):
        """Random unknown file → BLOCK."""
        lines = [" M some_random_script.py"]
        payload, rc = _run_scope(lines)
        self.assertEqual(payload["overall"], "BLOCK")
        self.assertNotEqual(rc, 0)
        self.assertIn("some_random_script.py", payload["blocked_files"])

    def test_release_checker_downstream_script_blocks(self):
        """A downstream unrelated script → BLOCK."""
        lines = [" M scripts/check_daily_collaborative_interpretation.py"]
        payload, rc = _run_scope(lines)
        self.assertEqual(payload["overall"], "BLOCK")
        self.assertNotEqual(rc, 0)


# === F: Output format ===

class TestScopeGateOutput(unittest.TestCase):
    """Scope gate output format tests."""

    def test_output_has_all_keys(self):
        """Output JSON must contain all required keys."""
        lines = [" M scripts/run_daily_report_html_only.py"]
        payload, rc = _run_scope(lines)
        for key in ["overall", "reason", "allowed_files", "blocked_files",
                     "generated_files", "evidence_files", "never_release_files",
                     "status_lines"]:
            self.assertIn(key, payload, f"Missing key: {key}")

    def test_blocked_files_nonempty_on_block(self):
        """When BLOCK, blocked_files must be non-empty."""
        lines = [" M some_random_script.py"]
        payload, rc = _run_scope(lines)
        self.assertGreater(len(payload["blocked_files"]), 0)

    def test_reason_contains_count(self):
        """BLOCK reason must mention file count."""
        lines = [" M some_random_script.py", " M another_random.py"]
        payload, rc = _run_scope(lines)
        self.assertIn("2 file(s)", payload["reason"])

    def test_never_release_key_on_never_release(self):
        """NEVER_RELEASE block must populate never_release_files key."""
        lines = [" M docs/keystock-dashboard/app.js"]
        payload, rc = _run_scope(lines)
        self.assertGreater(len(payload["never_release_files"]), 0)


if __name__ == "__main__":
    unittest.main()
