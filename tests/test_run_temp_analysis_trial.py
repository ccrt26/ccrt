#!/usr/bin/env python3
"""Unit tests for temporary-analysis trial runner."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_temp_analysis_trial import evaluate_trial


def base_context():
    return {
        "trial_id": "trial-600114-20260616-demo",
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
        "user_position_context": {"has_position": True},
        "post_eval": {
            "observed_close_state": "closed_in_range",
            "expected_action_bias": "HOLD"
        }
    }


class TestRunTemporaryAnalysisTrial(unittest.TestCase):
    def test_evaluate_trial_pass_when_bias_matches(self):
        context = base_context()
        brief = {
            "stock_code": "600114",
            "stock_name": "东睦股份",
            "action_bias": "HOLD",
            "intraday_state": "normal_fluctuation",
            "conclusion_strength": "倾向判断"
        }
        payload = evaluate_trial(context, brief, "PASS", [])
        self.assertEqual(payload["eval_result"], "PASS")
        self.assertTrue(payload["action_bias_matched_expectation"])
        self.assertTrue(payload["non_goals_confirmed"]["no_trade_execution"])

    def test_evaluate_trial_warn_when_bias_mismatch(self):
        context = base_context()
        brief = {
            "stock_code": "600114",
            "stock_name": "东睦股份",
            "action_bias": "WATCH",
            "intraday_state": "event_driven",
            "conclusion_strength": "风险假设"
        }
        payload = evaluate_trial(context, brief, "PASS", [])
        self.assertEqual(payload["eval_result"], "WARN")
        self.assertFalse(payload["action_bias_matched_expectation"])

    def test_cli_trial_generates_brief_and_eval(self):
        with tempfile.TemporaryDirectory() as td:
            context_path = Path(td) / "context.json"
            brief_path = Path(td) / "brief.json"
            eval_path = Path(td) / "eval.json"
            context_path.write_text(json.dumps(base_context(), ensure_ascii=False), encoding="utf-8")

            proc = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/run_temp_analysis_trial.py"),
                    "--context",
                    str(context_path),
                    "--brief-output",
                    str(brief_path),
                    "--eval-output",
                    str(eval_path)
                ],
                cwd=str(ROOT),
                text=True,
                capture_output=True
            )

            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
            self.assertTrue(brief_path.exists())
            self.assertTrue(eval_path.exists())

            payload = json.loads(proc.stdout)
            self.assertEqual(payload["status"], "PASS")

            eval_payload = json.loads(eval_path.read_text(encoding="utf-8"))
            self.assertEqual(eval_payload["scene"], "临时分析")
            self.assertEqual(eval_payload["gate_overall"], "PASS")

    def test_cli_warn_eval_is_successful_system_run(self):
        context = base_context()
        context["post_eval"]["expected_action_bias"] = "WATCH"

        with tempfile.TemporaryDirectory() as td:
            context_path = Path(td) / "context.json"
            brief_path = Path(td) / "brief.json"
            eval_path = Path(td) / "eval.json"
            context_path.write_text(json.dumps(context, ensure_ascii=False), encoding="utf-8")

            proc = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/run_temp_analysis_trial.py"),
                    "--context",
                    str(context_path),
                    "--brief-output",
                    str(brief_path),
                    "--eval-output",
                    str(eval_path)
                ],
                cwd=str(ROOT),
                text=True,
                capture_output=True
            )

            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["status"], "PASS")
            self.assertEqual(payload["eval_result"], "WARN")
            self.assertTrue(brief_path.exists())
            self.assertTrue(eval_path.exists())

    def test_cli_rejects_bad_identity(self):
        context = base_context()
        context["stock_code"] = "ABC"

        with tempfile.TemporaryDirectory() as td:
            context_path = Path(td) / "context.json"
            brief_path = Path(td) / "brief.json"
            eval_path = Path(td) / "eval.json"
            context_path.write_text(json.dumps(context, ensure_ascii=False), encoding="utf-8")

            proc = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/run_temp_analysis_trial.py"),
                    "--context",
                    str(context_path),
                    "--brief-output",
                    str(brief_path),
                    "--eval-output",
                    str(eval_path)
                ],
                cwd=str(ROOT),
                text=True,
                capture_output=True
            )

            self.assertEqual(proc.returncode, 2)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["status"], "BLOCK")
            self.assertFalse(brief_path.exists())
            self.assertFalse(eval_path.exists())


if __name__ == "__main__":
    unittest.main()
