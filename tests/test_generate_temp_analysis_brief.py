#!/usr/bin/env python3
"""Unit tests for TemporaryAnalysisBrief generator."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from generate_temp_analysis_brief import generate_brief


def base_context():
    return {
        "stock_code": "600114",
        "stock_name": "东睦股份",
        "query_time": "2026-06-16T10:12:00+08:00",
        "current_quote": {
            "change_pct": 0.8,
            "volume_ratio": 1.1,
            "intraday_vwap": "39.20",
            "intraday_reference": "分时均价线",
            "above_reference": True,
            "below_key_level": False,
            "reclaimed_key_level": False
        },
        "market_context": {"index_state": "neutral", "sector_state": "neutral"},
        "baseline_context": {"confirm_above": "40.00", "invalidate_below": "38.80"},
        "user_position_context": {"has_position": True}
    }


class TestGenerateTemporaryAnalysisBrief(unittest.TestCase):
    def test_normal_context_generates_hold(self):
        brief = generate_brief(base_context())
        self.assertEqual(brief["scene"], "临时分析")
        self.assertEqual(brief["framework_version"], "D07_v1.2")
        self.assertEqual(brief["intraday_state"], "normal_fluctuation")
        self.assertEqual(brief["action_bias"], "HOLD")
        self.assertTrue(brief["non_goals_confirmed"]["no_trade_executor_write"])

    def test_breakdown_with_position_generates_reduce(self):
        ctx = base_context()
        ctx["current_quote"]["below_key_level"] = True
        ctx["current_quote"]["reclaimed_key_level"] = False
        brief = generate_brief(ctx)
        self.assertEqual(brief["intraday_state"], "breakdown_weakness")
        self.assertEqual(brief["action_bias"], "REDUCE")
        self.assertEqual(brief["method_review"]["role_code"], "LISHI")
        self.assertEqual(brief["method_review"]["result"], "PASS")

    def test_missing_quote_degrades_to_neutral(self):
        ctx = base_context()
        ctx.pop("current_quote")
        brief = generate_brief(ctx)
        self.assertEqual(brief["intraday_state"], "data_insufficient")
        self.assertEqual(brief["action_bias"], "NEUTRAL")
        self.assertEqual(brief["conclusion_strength"], "数据不足")
        self.assertTrue(brief["evidence_gap_requests"])

    def test_missing_stock_code_rejected(self):
        ctx = base_context()
        ctx.pop("stock_code")
        with self.assertRaises(ValueError):
            generate_brief(ctx)

    def test_invalid_stock_code_rejected(self):
        ctx = base_context()
        ctx["stock_code"] = "ABC"
        with self.assertRaises(ValueError):
            generate_brief(ctx)

    def test_empty_stock_name_rejected(self):
        ctx = base_context()
        ctx["stock_name"] = " "
        with self.assertRaises(ValueError):
            generate_brief(ctx)

    def test_cli_generates_and_passes_gate(self):
        ctx = base_context()
        with tempfile.TemporaryDirectory() as td:
            input_path = Path(td) / "ctx.json"
            output_path = Path(td) / "brief.json"
            input_path.write_text(json.dumps(ctx, ensure_ascii=False), encoding="utf-8")
            proc = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/generate_temp_analysis_brief.py"),
                    "--input",
                    str(input_path),
                    "--output",
                    str(output_path),
                ],
                cwd=str(ROOT),
                text=True,
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
            self.assertTrue(output_path.exists())
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
