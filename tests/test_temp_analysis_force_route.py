#!/usr/bin/env python3
"""Tests for temporary-analysis force-route gate."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_temp_analysis_force_route import classify_request, audit_route_record, load_json

POLICY = load_json(ROOT / "00_项目地基/05_流程与角色/temp_analysis_force_route_policy_v0.1.json")


class TestTemporaryAnalysisForceRoute(unittest.TestCase):
    def test_explicit_temp_analysis_routes(self):
        result = classify_request("启动临时分析：东睦股份 600114 现在怎么看", POLICY)
        self.assertEqual(result["decision"], "TEMP_ANALYSIS_REQUIRED")
        self.assertTrue(result["d07_v1_2_required"])
        self.assertTrue(result["lishi_integrated_by_default"])

    def test_today_volume_price_routes(self):
        result = classify_request("看一下今天东睦股份的量价，分析情况", POLICY)
        self.assertEqual(result["decision"], "TEMP_ANALYSIS_REQUIRED")

    def test_chase_or_sell_routes(self):
        for text in ["东睦股份现在能不能追", "东睦股份今天要不要卖", "600114 破位怎么办"]:
            result = classify_request(text, POLICY)
            self.assertEqual(result["decision"], "TEMP_ANALYSIS_REQUIRED", text)

    def test_long_form_deep_analysis_not_forced_without_intraday_terms(self):
        result = classify_request("请写东睦股份长期深度分析报告", POLICY)
        self.assertEqual(result["decision"], "NOT_TEMP_ANALYSIS")

    def test_intraday_natural_language_routes(self):
        cases = [
            "东睦股份今天放量上涨怎么看",
            "600114 今天放量滞涨怎么办",
            "东睦股份高开低走怎么看",
            "东睦股份拉升后承接怎么样",
            "东睦股份现在换手和成交量怎么样",
            "600114 今天盘口强不强",
        ]
        for text in cases:
            result = classify_request(text, POLICY)
            self.assertEqual(result["decision"], "TEMP_ANALYSIS_REQUIRED", text)

    def test_fake_artifact_paths_block(self):
        record = {
            "request": "东睦股份今天放量上涨怎么看",
            "route_decision": "TEMP_ANALYSIS_REQUIRED",
            "direct_role_answer": False,
            "d07_version": "D07_v1.2",
            "lishi_integrated": True,
            "backend_artifacts": {
                "brief_path": "/private/tmp/nonexistent_brief.json",
                "gate_overall": "PASS",
                "rendered_output_path": "/private/tmp/nonexistent_render.txt"
            }
        }
        overall, findings, _ = audit_route_record(record, POLICY)
        self.assertEqual(overall, "BLOCK")
        checks = {f["check"] for f in findings}
        self.assertIn("brief_path_exists", checks)
        self.assertIn("rendered_output_path_exists", checks)

    def test_valid_audit_record_passes(self):
        record = {
            "request": "看一下今天东睦股份的量价，分析情况",
            "route_decision": "TEMP_ANALYSIS_REQUIRED",
            "direct_role_answer": False,
            "d07_version": "D07_v1.2",
            "lishi_integrated": True,
            "backend_artifacts": {
                "brief_path": "临时分析/sidecar/temporary_analysis_trial_brief_600114_20260616_demo.json",
                "gate_overall": "PASS",
                "rendered_output_path": "临时分析/sidecar/temporary_analysis_rendered_600114_20260616_demo.txt"
            }
        }
        overall, findings, classified = audit_route_record(record, POLICY)
        self.assertEqual(overall, "PASS", findings)
        self.assertEqual(classified["decision"], "TEMP_ANALYSIS_REQUIRED")

    def test_missing_backend_artifacts_blocks(self):
        record = {
            "request": "看一下今天东睦股份的量价，分析情况",
            "route_decision": "TEMP_ANALYSIS_REQUIRED",
            "direct_role_answer": True,
            "d07_version": "D07_v1.2",
            "lishi_integrated": False,
            "backend_artifacts": {"gate_overall": "PASS"}
        }
        overall, findings, _ = audit_route_record(record, POLICY)
        self.assertEqual(overall, "BLOCK")
        checks = {f["check"] for f in findings}
        self.assertIn("direct_role_answer", checks)
        self.assertIn("lishi_integrated", checks)
        self.assertIn("brief_path", checks)
        self.assertIn("rendered_output_path", checks)

    def test_cli_audit_blocks_bad_record(self):
        bad = {
            "request": "东睦股份现在能不能追",
            "route_decision": "TEMP_ANALYSIS_REQUIRED",
            "direct_role_answer": True,
            "d07_version": "D07_v1.2",
            "lishi_integrated": True,
            "backend_artifacts": {"gate_overall": "PASS"}
        }
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad.json"
            p.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
            proc = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/check_temp_analysis_force_route.py"),
                    "--audit-json",
                    str(p),
                    "--json"
                ],
                cwd=str(ROOT),
                text=True,
                capture_output=True
            )
            self.assertEqual(proc.returncode, 2)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["overall"], "BLOCK")


if __name__ == "__main__":
    unittest.main()
