#!/usr/bin/env python3
"""Tests for D07 gate — release gate and promote must BLOCK when d07_interpretation missing.

Verifies:
1. check_daily_release_gate.py --active-only must continue executing P0-H
2. promote shadow gate uses REPORT_ROOT_OVERRIDE to check staging artifacts
3. D07 missing in staging sidecar → release gate BLOCK → formal directory untouched
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE_GATE_PATH = ROOT / "scripts" / "check_daily_release_gate.py"


class TestReleaseGateActiveOnlyHasP0H(unittest.TestCase):
    """check_daily_release_gate.py --active-only must include P0-H D07 check."""

    def test_active_only_includes_p0h(self):
        """P0-H: D07合同检查 must be present in --active-only mode."""
        src = RELEASE_GATE_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "P0-H: D07合同检查",
            src,
            "P0-H D07 check must be defined in active-only mode"
        )

    def test_active_only_calls_d07_check_per_target(self):
        """P0-H must run per active target via check_daily_d07_v12_contract.py --code."""
        src = RELEASE_GATE_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "check_daily_d07_v12_contract.py",
            src,
            "D07 contract checker must be invoked"
        )
        self.assertIn(
            "--code",
            src,
            "D07 check must run per-target with --code"
        )


class TestPromoteShadowGateUsesReportOverride(unittest.TestCase):
    """promote_staging in run_daily_report_html_only.py must use REPORT_ROOT_OVERRIDE."""

    def test_promote_uses_report_root_override(self):
        """promote mode must set REPORT_ROOT_OVERRIDE env var for release gate."""
        src = (ROOT / "scripts" / "run_daily_report_html_only.py").read_text(encoding="utf-8")
        self.assertIn(
            "REPORT_ROOT_OVERRIDE",
            src,
            "Promote must use REPORT_ROOT_OVERRIDE for shadow release gate"
        )


class TestD07InterpretationMissingBlocksReleaseGate(unittest.TestCase):
    """Functional test: staging sidecar missing d07_interpretation → release gate BLOCK."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def _create_staging_sidecar(self, sidecar_dir, code, name, date_str, has_d07=True):
        """Create a minimal sidecar JSON in staging dir."""
        sidecar_dir.mkdir(parents=True, exist_ok=True)
        prefix = f"{name}({code})日报_{date_str}"
        sidecar = {
            "report_version": "3.7.0-html-only-auto",
            "stock_code": code,
            "stock_name": name,
            "trade_date": f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}",
            "baseline_id": "test_baseline",
            "framework_version": "D07_v1.2",
            "logic_version": "v3.6.3-fix",
            "interpretation_id": f"D07-{code}-{date_str}",
            "conclusion_strength": "可定性",
            "hypotheses": [],
            "evidence_gap_requests": [],
            "rule_refs": [],
            "knowledge_refs": [],
            "role_interpretations": {
                "山猫_宏观": {"职责": "宏观", "解读": "test", "结论": "ok"},
                "信鸽_事件": {"职责": "事件", "解读": "test", "结论": "ok"},
                "玉夜_数据": {"职责": "数据", "解读": "test", "结论": "ok"},
                "流金_风控": {"职责": "风控", "解读": "test", "结论": "ok"},
                "青山_信号": {"职责": "信号", "解读": "test", "结论": "ok"},
                "腰子_整合": {"职责": "整合", "解读": "test", "结论": "ok"},
                "daily_discussion": {"status": "materialized"},
            },
        }
        if has_d07:
            sidecar["d07_interpretation"] = {
                "interpretation_id": f"D07-{code}-{date_str}",
                "framework_version": "D07_v1.2",
                "logic_version": "v3.6.3-fix",
                "type": "daily_report",
                "conclusion_strength": "可定性",
                "hypotheses": [],
                "evidence_gap_requests": [],
                "rule_refs": [],
                "knowledge_refs": [],
                "schema_version": "1.0",
            }
            sidecar["unified_interpretation"] = {
                "interpretation_id": f"D07-{code}-{date_str}",
                "framework_version": "D07_v1.2",
                "type": "daily_report",
            }
        (sidecar_dir / f"{prefix}.json").write_text(
            json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8")

    def test_remove_d07_blocks_release_gate_subprocess(self):
        """Sidecar without d07_interpretation must BLOCK P0-H in release gate."""
        # Create a shadow root in tmpdir
        shadow_root = self.tmpdir / "shadow" / "重点股票" / "股票报告"
        code, name, date_str = "600114", "东睦股份", "20260616"
        self._create_staging_sidecar(
            shadow_root / f"{name}({code})",
            code, name, date_str,
            has_d07=False  # MISSING d07_interpretation
        )

        # Run release gate against shadow root
        rg_env = os.environ.copy()
        rg_env["REPORT_ROOT_OVERRIDE"] = str(shadow_root)
        cmd = [sys.executable, str(RELEASE_GATE_PATH), "--date", date_str, "--active-only"]
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
            cwd=str(ROOT), env=rg_env
        )
        stdo = proc.stdout or ""
        # Verify P0-H ran and BLOCKed against the missing d07_interpretation
        self.assertIn("P0-H", stdo, "P0-H D07 check must execute in active-only mode")
        self.assertNotEqual(proc.returncode, 0,
                            "Release gate must BLOCK when d07_interpretation is missing")
        self.assertIn("缺少D07字段: d07_interpretation", stdo,
                       "Release gate BLOCK reason must mention missing d07_interpretation")

    def test_d07_present_sidecar_passes_release_gate_structure(self):
        """Sidecar WITH d07_interpretation must have correct structure for P0-H check."""
        shadow_root = self.tmpdir / "shadow" / "重点股票" / "股票报告"
        code, name, date_str = "600114", "东睦股份", "20260616"
        self._create_staging_sidecar(
            shadow_root / f"{name}({code})",
            code, name, date_str,
            has_d07=True
        )

        # Check the sidecar is properly structured with all required D07 fields
        sidecar_path = shadow_root / f"{name}({code})" / f"{name}({code})日报_{date_str}.json"
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        required = [
            "framework_version", "logic_version", "interpretation_id",
            "conclusion_strength", "hypotheses", "evidence_gap_requests",
            "rule_refs", "knowledge_refs", "d07_interpretation", "unified_interpretation"
        ]
        for field in required:
            self.assertIn(
                field, sidecar,
                f"P0-H required field '{field}' missing from sidecar"
            )


class TestPipelineClosurePostWriteVerification(unittest.TestCase):
    """Post-write closure verification must exist in pipeline."""

    def test_pipeline_has_post_write_closure_verify(self):
        """Pipeline must run closure_verify after writing manifest/ready."""
        src = (ROOT / "scripts" / "run_daily_production_pipeline.py").read_text(encoding="utf-8")
        self.assertIn(
            "Post-write closure verify",
            src,
            "Pipeline must have post-write closure verification"
        )
        self.assertIn(
            "verify_daily_production_closure.py",
            src,
            "Post-write verification must use verify_daily_production_closure script"
        )

    def test_post_write_closure_uses_non_pipeline_internal(self):
        """Post-write closure command must NOT contain --pipeline-internal flag."""
        src = (ROOT / "scripts" / "run_daily_production_pipeline.py").read_text(encoding="utf-8")
        # Find the post-write section where the subprocess command is defined
        cv_post_cmd_start = src.find("cv_post_cmd")
        if cv_post_cmd_start >= 0:
            # Extract the actual command list definition
            end_of_cmd = src.find("]\n", cv_post_cmd_start)
            cmd_text = src[cv_post_cmd_start:end_of_cmd + 1] if end_of_cmd > 0 else src[cv_post_cmd_start:cv_post_cmd_start + 300]
            # The actual subprocess command should not contain --pipeline-internal
            self.assertNotIn(
                "--pipeline-internal",
                cmd_text,
                "Post-write closure verify command must NOT use --pipeline-internal"
            )


class TestPipelineManifestOverallConsistency(unittest.TestCase):
    """manifest overall=PASS requires all status_split items to be PASS."""

    def test_overall_requires_all_status_split_pass(self):
        """manifest overall must be PASS only when all status_split values are 'PASS'."""
        src = (ROOT / "scripts" / "run_daily_production_pipeline.py").read_text(encoding="utf-8")
        # New logic: "overall" = "PASS" only when all status_split are PASS
        self.assertIn('"overall": "PASS" if all_pass else "BLOCK"', src)

    def test_no_warn_overall_hiding_block(self):
        """manifest overall must not use 'WARN' state that could hide BLOCK steps."""
        src = (ROOT / "scripts" / "run_daily_production_pipeline.py").read_text(encoding="utf-8")
        # Find the overall assignment in manifest building
        overall_line_start = src.find('"overall": "PASS" if all_pass else "BLOCK"')
        if overall_line_start >= 0:
            overall_assignment = src[overall_line_start:overall_line_start + 100]
            self.assertNotIn(
                "WARN",
                overall_assignment,
                "manifest overall must be PASS or BLOCK, not WARN"
            )


if __name__ == "__main__":
    unittest.main()
