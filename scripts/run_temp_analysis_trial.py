#!/usr/bin/env python3
"""Run one temporary-analysis trial and produce a post-evaluation record."""

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from generate_temp_analysis_brief import generate_brief, write_json
from check_temp_analysis_brief_gate import check_brief, load_json, DEFAULT_SCHEMA, DEFAULT_CONTRACT


def now_cst():
    return datetime.now(timezone(timedelta(hours=8))).replace(microsecond=0).isoformat()


def evaluate_trial(context, brief, gate_overall, gate_findings):
    expected = context.get("post_eval", {}) if isinstance(context.get("post_eval"), dict) else {}
    observed_close_state = expected.get("observed_close_state", "pending")
    expected_bias = expected.get("expected_action_bias", brief.get("action_bias"))

    matched = brief.get("action_bias") == expected_bias
    if gate_overall != "PASS":
        eval_result = "BLOCK"
    elif observed_close_state == "pending":
        eval_result = "PENDING"
    elif matched:
        eval_result = "PASS"
    else:
        eval_result = "WARN"

    return {
        "scene": "临时分析",
        "trial_id": context.get("trial_id", ""),
        "stock_code": brief.get("stock_code", ""),
        "stock_name": brief.get("stock_name", ""),
        "brief_action_bias": brief.get("action_bias", ""),
        "brief_intraday_state": brief.get("intraday_state", ""),
        "brief_conclusion_strength": brief.get("conclusion_strength", ""),
        "gate_overall": gate_overall,
        "gate_findings": gate_findings,
        "observed_close_state": observed_close_state,
        "expected_action_bias": expected_bias,
        "action_bias_matched_expectation": matched,
        "eval_result": eval_result,
        "review_points": [
            "收盘后核对触发条件是否真实发生",
            "T+1 核对盘中判断是否延续或被证伪",
            "T+3 核对动作是否降低风险或错过机会"
        ],
        "non_goals_confirmed": {
            "no_trade_execution": True,
            "no_daily_report_write": True,
            "no_deep_baseline_recalc": True
        },
        "generated_at": now_cst()
    }


def main():
    parser = argparse.ArgumentParser(description="Run temporary-analysis trial")
    parser.add_argument("--context", required=True)
    parser.add_argument("--brief-output", required=True)
    parser.add_argument("--eval-output", required=True)
    args = parser.parse_args()

    try:
        context = load_json(args.context)
        brief = generate_brief(context)
        brief_path = write_json(args.brief_output, brief)

        schema = load_json(DEFAULT_SCHEMA)
        contract = load_json(DEFAULT_CONTRACT)
        gate_overall, gate_findings = check_brief(brief, schema, contract)

        eval_payload = evaluate_trial(context, brief, gate_overall, gate_findings)
        eval_path = write_json(args.eval_output, eval_payload)

        system_status = "PASS" if gate_overall == "PASS" and eval_payload["eval_result"] in {"PASS", "PENDING", "WARN"} else "BLOCK"
        print(json.dumps({
            "status": system_status,
            "brief_output": str(brief_path),
            "eval_output": str(eval_path),
            "gate_overall": gate_overall,
            "eval_result": eval_payload["eval_result"]
        }, ensure_ascii=False, indent=2))
        return 0 if system_status == "PASS" else 2
    except Exception as exc:
        print(json.dumps({
            "status": "BLOCK",
            "error_type": type(exc).__name__,
            "error": str(exc)
        }, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
