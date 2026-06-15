#!/usr/bin/env python3
"""Unit tests for TemporaryAnalysisBrief gate."""

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_temp_analysis_brief_gate import check_brief, load_json

SCHEMA = load_json(ROOT / "00_项目地基/03_报告对象/temporary_analysis_brief_v0.1.schema.json")
CONTRACT = load_json(ROOT / "00_项目地基/05_流程与角色/temp_analysis_scene_contract_v0.1.json")
SAMPLE = load_json(ROOT / "临时分析/样例/temporary_analysis_breakdown_weakness_600114_20260616.json")


class TestTemporaryAnalysisBriefGate(unittest.TestCase):
    def test_existing_samples_pass(self):
        for path in sorted((ROOT / "临时分析/样例").glob("temporary_analysis_*_600114_20260616.json")):
            data = load_json(path)
            overall, findings = check_brief(data, SCHEMA, CONTRACT)
            self.assertEqual(overall, "PASS", f"{path}: {findings}")

    def test_invalid_stock_code_blocks(self):
        data = copy.deepcopy(SAMPLE)
        data["stock_code"] = "ABC"
        overall, findings = check_brief(data, SCHEMA, CONTRACT)
        self.assertEqual(overall, "BLOCK")
        self.assertTrue(any(f["check"] == "stock_code" for f in findings), findings)

    def test_missing_stock_code_blocks(self):
        data = copy.deepcopy(SAMPLE)
        data["stock_code"] = ""
        overall, findings = check_brief(data, SCHEMA, CONTRACT)
        self.assertEqual(overall, "BLOCK")
        self.assertTrue(any(f["check"] == "stock_code" for f in findings), findings)

    def test_empty_stock_name_blocks(self):
        data = copy.deepcopy(SAMPLE)
        data["stock_name"] = " "
        overall, findings = check_brief(data, SCHEMA, CONTRACT)
        self.assertEqual(overall, "BLOCK")
        self.assertTrue(any(f["check"] == "stock_name" for f in findings), findings)

    def test_missing_counter_hypothesis_blocks(self):
        data = copy.deepcopy(SAMPLE)
        data["hypotheses"] = [h for h in data["hypotheses"] if h["type"] != "counter"]
        overall, findings = check_brief(data, SCHEMA, CONTRACT)
        self.assertEqual(overall, "BLOCK")
        self.assertTrue(any(f["check"] == "counter_hypothesis" for f in findings), findings)

    def test_strong_action_without_lishi_blocks(self):
        data = copy.deepcopy(SAMPLE)
        data["method_review"]["result"] = "NOT_REQUIRED"
        overall, findings = check_brief(data, SCHEMA, CONTRACT)
        self.assertEqual(overall, "BLOCK")
        self.assertTrue(any(f["check"] == "lishi_required" for f in findings), findings)

    def test_missing_event_context_requires_gap(self):
        data = load_json(ROOT / "临时分析/样例/temporary_analysis_false_breakout_600114_20260616.json")
        data = copy.deepcopy(data)
        data["evidence_gap_requests"] = []
        overall, findings = check_brief(data, SCHEMA, CONTRACT)
        self.assertEqual(overall, "BLOCK")
        self.assertTrue(any(f["check"] == "event_gap" for f in findings), findings)

    def test_current_quote_missing_degrades(self):
        data = copy.deepcopy(SAMPLE)
        data["data_quality"]["current_quote"] = "missing"
        data["action_bias"] = "REDUCE"
        overall, findings = check_brief(data, SCHEMA, CONTRACT)
        self.assertEqual(overall, "BLOCK")
        self.assertTrue(any(f["check"] == "degrade_current_quote" for f in findings), findings)

    def test_lishi_forbidden_expression_blocks(self):
        data = copy.deepcopy(SAMPLE)
        data["method_review"]["calibration_note"] = "砺石建议买入"
        overall, findings = check_brief(data, SCHEMA, CONTRACT)
        self.assertEqual(overall, "BLOCK")
        self.assertTrue(any(f["check"] == "lishi_forbidden_expression" for f in findings), findings)

    def test_hypotheses_non_array_blocks_without_exception(self):
        data = copy.deepcopy(SAMPLE)
        data["hypotheses"] = "bad"
        overall, findings = check_brief(data, SCHEMA, CONTRACT)
        self.assertEqual(overall, "BLOCK")
        self.assertTrue(any(f["check"] == "hypotheses_type" for f in findings), findings)

    def test_trigger_actions_non_array_blocks_without_exception(self):
        data = copy.deepcopy(SAMPLE)
        data["trigger_actions"] = "bad"
        overall, findings = check_brief(data, SCHEMA, CONTRACT)
        self.assertEqual(overall, "BLOCK")
        self.assertTrue(any(f["check"] == "trigger_actions_type" for f in findings), findings)

    def test_method_review_non_object_blocks_without_exception(self):
        data = copy.deepcopy(SAMPLE)
        data["method_review"] = "bad"
        overall, findings = check_brief(data, SCHEMA, CONTRACT)
        self.assertEqual(overall, "BLOCK")
        self.assertTrue(any(f["check"] == "method_review_type" for f in findings), findings)

    def test_cli_missing_input_returns_json_block(self):
        proc = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/check_temp_analysis_brief_gate.py"),
                "--input",
                "/private/tmp/nonexistent_temp_analysis.json",
                "--json",
            ],
            cwd=str(ROOT),
            text=True,
            capture_output=True,
        )
        self.assertEqual(proc.returncode, 2, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["overall"], "BLOCK")
        self.assertIn("results", payload)


if __name__ == "__main__":
    unittest.main()
