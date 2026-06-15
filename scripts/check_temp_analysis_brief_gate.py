#!/usr/bin/env python3
"""TemporaryAnalysisBrief gate.

Validates 临时分析 TemporaryAnalysisBrief JSON objects without external
dependencies. Exit codes: 0=PASS, 1=WARN, 2=BLOCK.
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "00_项目地基/05_流程与角色/temp_analysis_scene_contract_v0.1.json"
DEFAULT_SCHEMA = ROOT / "00_项目地基/03_报告对象/temporary_analysis_brief_v0.1.schema.json"

STRONG_ACTIONS = {"REDUCE", "EXIT", "CONDITIONAL_ADD", "T_CONDITION"}


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def issue(result, check, detail):
    return {"result": result, "check": check, "detail": detail}


def block_payload(check, detail):
    return {"overall": "BLOCK", "results": [], "findings": [issue("BLOCK", check, detail)]}


def required_fields_from_schema(schema):
    if not isinstance(schema, dict):
        return set()
    return set(schema.get("required", []))


def enum_from_schema(schema, field):
    if not isinstance(schema, dict):
        return set()
    props = schema.get("properties", {})
    if not isinstance(props, dict):
        return set()
    field_schema = props.get(field, {})
    if not isinstance(field_schema, dict):
        return set()
    return set(field_schema.get("enum", []))


def ensure_object(value, check_name, findings):
    if isinstance(value, dict):
        return value
    findings.append(issue("BLOCK", check_name, f"expected object, got {type(value).__name__}"))
    return {}


def ensure_array(value, check_name, findings):
    if isinstance(value, list):
        return value
    findings.append(issue("BLOCK", check_name, f"expected array, got {type(value).__name__}"))
    return []


def check_brief(data, schema, contract):
    findings = []

    if not isinstance(data, dict):
        return "BLOCK", [issue("BLOCK", "root_type", f"expected object, got {type(data).__name__}")]

    required = required_fields_from_schema(schema)
    missing = sorted(required - set(data))
    if missing:
        findings.append(issue("BLOCK", "required_fields", f"missing={missing}"))
        return "BLOCK", findings

    if data.get("scene") != "临时分析":
        findings.append(issue("BLOCK", "scene", "scene must be 临时分析"))
    if data.get("framework_version") != "D07_v1.2":
        findings.append(issue("BLOCK", "framework_version", "framework_version must be D07_v1.2"))

    stock_code = data.get("stock_code")
    if not isinstance(stock_code, str) or not re.fullmatch(r"[0-9]{6}", stock_code):
        findings.append(issue("BLOCK", "stock_code", "stock_code must be six digits"))

    stock_name = data.get("stock_name")
    if not isinstance(stock_name, str) or not stock_name.strip():
        findings.append(issue("BLOCK", "stock_name", "stock_name must be non-empty"))

    state_enum = set(contract.get("intraday_state_enum", [])) if isinstance(contract, dict) else set()
    state_enum = state_enum or enum_from_schema(schema, "intraday_state")
    action_enum = set(contract.get("action_bias_enum", [])) if isinstance(contract, dict) else set()
    action_enum = action_enum or enum_from_schema(schema, "action_bias")

    if data.get("intraday_state") not in state_enum:
        findings.append(issue("BLOCK", "intraday_state", f"invalid={data.get('intraday_state')}"))
    if data.get("action_bias") not in action_enum:
        findings.append(issue("BLOCK", "action_bias", f"invalid={data.get('action_bias')}"))

    d07_req = contract.get("d07_v1_2_requirements", {}) if isinstance(contract, dict) else {}
    min_hypotheses = int(d07_req.get("min_hypotheses", 2))
    hypotheses = ensure_array(data.get("hypotheses"), "hypotheses_type", findings)
    hypothesis_objects = []
    for idx, item in enumerate(hypotheses):
        if isinstance(item, dict):
            hypothesis_objects.append(item)
        else:
            findings.append(issue("BLOCK", "hypotheses_item_type", f"hypotheses[{idx}] expected object, got {type(item).__name__}"))

    if len(hypothesis_objects) < min_hypotheses:
        findings.append(issue("BLOCK", "hypotheses", f"hypotheses must contain at least {min_hypotheses} object items"))
    if not any(h.get("type") == "counter" for h in hypothesis_objects):
        findings.append(issue("BLOCK", "counter_hypothesis", "hypotheses must contain a counter hypothesis"))

    counter_evidence = ensure_array(data.get("counter_evidence"), "counter_evidence_type", findings)
    counter_objects = [item for item in counter_evidence if isinstance(item, dict)]
    if len(counter_objects) != len(counter_evidence):
        findings.append(issue("BLOCK", "counter_evidence_item_type", "counter_evidence items must be objects"))
    if not counter_objects:
        findings.append(issue("BLOCK", "counter_evidence", "counter_evidence must not be empty"))

    evidence_gaps = ensure_array(data.get("evidence_gap_requests"), "evidence_gap_requests_type", findings)
    gap_objects = []
    for idx, item in enumerate(evidence_gaps):
        if isinstance(item, dict):
            gap_objects.append(item)
        else:
            findings.append(issue("BLOCK", "evidence_gap_item_type", f"evidence_gap_requests[{idx}] expected object, got {type(item).__name__}"))

    data_quality = ensure_object(data.get("data_quality"), "data_quality_type", findings)
    if data_quality.get("current_quote") == "missing":
        if data.get("action_bias") not in {"WATCH", "NEUTRAL"}:
            findings.append(issue("BLOCK", "degrade_current_quote", "missing current_quote allows only WATCH/NEUTRAL"))
        if data.get("conclusion_strength") != "数据不足":
            findings.append(issue("BLOCK", "degrade_current_quote_strength", "missing current_quote requires 数据不足"))

    for field in ("market_context", "baseline_context"):
        if data_quality.get(field) == "missing" and data.get("action_bias") not in {"WATCH", "NEUTRAL"}:
            findings.append(issue("BLOCK", f"degrade_{field}", f"missing {field} allows only WATCH/NEUTRAL"))

    if data_quality.get("event_context") == "missing":
        open_gaps = [g for g in gap_objects if g.get("status") == "open"]
        if not open_gaps:
            findings.append(issue("BLOCK", "event_gap", "missing event_context requires open evidence_gap_requests"))

    action = data.get("action_bias")
    trigger_actions = ensure_array(data.get("trigger_actions"), "trigger_actions_type", findings)
    trigger_objects = []
    for idx, item in enumerate(trigger_actions):
        if isinstance(item, dict):
            trigger_objects.append(item)
        else:
            findings.append(issue("BLOCK", "trigger_actions_item_type", f"trigger_actions[{idx}] expected object, got {type(item).__name__}"))

    if action in STRONG_ACTIONS:
        if not trigger_objects:
            findings.append(issue("BLOCK", "strong_action_trigger", "strong action requires trigger_actions"))
        required_fields = contract.get("strong_action_required_fields", []) if isinstance(contract, dict) else []
        for idx, item in enumerate(trigger_objects):
            for field in required_fields:
                field_map = {"trigger_condition": "condition", "position_boundary": "position_boundary"}
                mapped = field_map.get(field, field)
                if not item.get(mapped):
                    findings.append(issue("BLOCK", "strong_action_fields", f"trigger_actions[{idx}] missing {mapped}"))

    method_review = ensure_object(data.get("method_review"), "method_review_type", findings)
    if action in STRONG_ACTIONS:
        mr_result = method_review.get("result")
        if mr_result in ("NOT_REQUIRED", "", None):
            findings.append(issue("BLOCK", "lishi_required", "strong action requires LISHI method_review"))

    if data_quality.get("user_position_context") == "missing":
        combined = json.dumps(trigger_objects, ensure_ascii=False)
        banned = ["1/2仓", "半仓", "三成", "30%", "50%", "70%", "满仓"]
        hits = [b for b in banned if b in combined]
        if hits:
            findings.append(issue("BLOCK", "position_ratio_without_context", f"position ratio without context: {hits}"))

    if method_review.get("role_code") != "LISHI":
        findings.append(issue("BLOCK", "lishi_role_code", "method_review.role_code must be LISHI"))

    lishi_rules = contract.get("lishi_method_review", {}) if isinstance(contract, dict) else {}
    forbidden = lishi_rules.get("forbidden_expressions", [])
    lishi_text = json.dumps(method_review, ensure_ascii=False)
    hits = [word for word in forbidden if word and word in lishi_text]
    if hits:
        findings.append(issue("BLOCK", "lishi_forbidden_expression", f"LISHI text contains forbidden expressions: {hits}"))

    non_goals = ensure_object(data.get("non_goals_confirmed"), "non_goals_type", findings)
    for field in ("no_daily_report", "no_deep_baseline_recalc", "no_trade_executor_write"):
        if non_goals.get(field) is not True:
            findings.append(issue("BLOCK", "non_goals", f"{field} must be true"))

    eval_hook = ensure_object(data.get("eval_hook"), "eval_hook_type", findings)
    for field in ("close_check", "t1_check", "t3_check"):
        if not eval_hook.get(field):
            findings.append(issue("BLOCK", "eval_hook", f"{field} required"))

    results = {f["result"] for f in findings}
    if "BLOCK" in results:
        return "BLOCK", findings
    if "WARN" in results:
        return "WARN", findings
    findings.append(issue("PASS", "temporary_analysis_gate", "all checks passed"))
    return "PASS", findings


def iter_targets(args):
    if args.input:
        return [Path(args.input)]
    sample_dir = Path(args.sample_dir)
    return sorted(sample_dir.glob("temporary_analysis_*.json"))


def print_payload(payload, as_json):
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"TEMP_ANALYSIS_GATE: {payload.get('overall', 'BLOCK')}")
        for finding in payload.get("findings", []):
            print(f"- [{finding['result']}] {finding['check']}: {finding['detail']}")
        for item in payload.get("results", []):
            print(f"- {item['path']}: {item['overall']}")
            for finding in item["findings"]:
                print(f"  [{finding['result']}] {finding['check']}: {finding['detail']}")


def main():
    parser = argparse.ArgumentParser(description="TemporaryAnalysisBrief gate")
    parser.add_argument("--input", default="", help="single TemporaryAnalysisBrief JSON")
    parser.add_argument("--sample-dir", default="临时分析/样例", help="directory of sample JSON files")
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA))
    parser.add_argument("--contract", default=str(DEFAULT_CONTRACT))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        schema = load_json(args.schema)
        contract = load_json(args.contract)
    except Exception as exc:
        payload = block_payload("config_load", f"{type(exc).__name__}: {exc}")
        print_payload(payload, args.json)
        return 2

    targets = iter_targets(args)
    if not targets:
        payload = block_payload("input", "no input files found")
        print_payload(payload, args.json)
        return 2

    results = []
    for target in targets:
        try:
            data = load_json(target)
        except Exception as exc:
            results.append({
                "path": str(target),
                "overall": "BLOCK",
                "findings": [issue("BLOCK", "input_load", f"{type(exc).__name__}: {exc}")]
            })
            continue
        overall, findings = check_brief(data, schema, contract)
        results.append({"path": str(target), "overall": overall, "findings": findings})

    if any(r["overall"] == "BLOCK" for r in results):
        overall = "BLOCK"
    elif any(r["overall"] == "WARN" for r in results):
        overall = "WARN"
    else:
        overall = "PASS"

    payload = {"overall": overall, "results": results}
    print_payload(payload, args.json)
    return 0 if overall == "PASS" else (1 if overall == "WARN" else 2)


if __name__ == "__main__":
    raise SystemExit(main())
