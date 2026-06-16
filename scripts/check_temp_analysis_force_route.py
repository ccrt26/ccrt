#!/usr/bin/env python3
"""Force-route gate for temporary-analysis requests."""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "00_项目地基/05_流程与角色/temp_analysis_force_route_policy_v0.1.json"


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def issue(result, check, detail):
    return {"result": result, "check": check, "detail": detail}


def normalize(text):
    return re.sub(r"\s+", "", text or "")


def contains_any(text, terms):
    return [term for term in terms if term and term in text]


def stock_name_suffix_hits(text, suffixes):
    hits = []
    for suffix in suffixes:
        if suffix and re.search(r"[\\u4e00-\\u9fff]{2,8}" + re.escape(suffix), text):
            hits.append(suffix)
    return hits


def classify_request(text, policy):
    raw = text or ""
    compact = normalize(raw)
    hits = contains_any(compact, policy.get("force_route_when_any", []))
    composite_hits = []

    for rule in policy.get("composite_route_rules", []):
        time_hits = contains_any(compact, rule.get("time_terms_any", []))
        market_hits = contains_any(compact, rule.get("market_terms_any", []))
        if time_hits and market_hits:
            composite_hits.append({"time_terms": time_hits, "market_terms": market_hits})

    stock_rule = policy.get("stock_context_route_rule", {})
    stock_code_pattern = stock_rule.get("stock_code_pattern", r"(?<!\\d)\\d{6}(?!\\d)")
    stock_code_hits = re.findall(stock_code_pattern, raw)
    stock_name_hits = stock_name_suffix_hits(compact, stock_rule.get("stock_name_suffix_any", []))
    stock_market_hits = contains_any(compact, stock_rule.get("market_terms_any", []))
    stock_context_hits = {
        "stock_code_hits": stock_code_hits,
        "stock_name_suffix_hits": stock_name_hits,
        "market_terms": stock_market_hits,
    }
    stock_context_required = bool((stock_code_hits or stock_name_hits) and stock_market_hits)

    decision = "TEMP_ANALYSIS_REQUIRED" if hits or composite_hits or stock_context_required else "NOT_TEMP_ANALYSIS"

    return {
        "decision": decision,
        "trigger_hits": hits,
        "composite_hits": composite_hits,
        "stock_context_hits": stock_context_hits,
        "stock_code_hits": stock_code_hits,
        "required_backend_chain": policy.get("required_backend_chain", []) if decision == "TEMP_ANALYSIS_REQUIRED" else [],
        "d07_v1_2_required": decision == "TEMP_ANALYSIS_REQUIRED",
        "lishi_integrated_by_default": bool(policy.get("lishi_rule", {}).get("integrated_by_default")) if decision == "TEMP_ANALYSIS_REQUIRED" else False
    }


def audit_route_record(record, policy):
    findings = []
    request = record.get("request", "")
    classified = classify_request(request, policy)

    if classified["decision"] != "TEMP_ANALYSIS_REQUIRED":
        findings.append(issue("PASS", "route_not_required", "request is not classified as temporary analysis"))
        return "PASS", findings, classified

    if record.get("route_decision") != "TEMP_ANALYSIS_REQUIRED":
        findings.append(issue("BLOCK", "route_decision", "temporary-analysis request must route to TEMP_ANALYSIS_REQUIRED"))

    if record.get("direct_role_answer") is not False:
        findings.append(issue("BLOCK", "direct_role_answer", "role must not answer directly with personal logic"))

    if record.get("d07_version") != "D07_v1.2":
        findings.append(issue("BLOCK", "d07_version", "temporary analysis must use D07_v1.2"))

    if record.get("lishi_integrated") is not True:
        findings.append(issue("BLOCK", "lishi_integrated", "D07_v1.2 must include LISHI calibration by default"))

    artifacts = record.get("backend_artifacts", {})
    if not isinstance(artifacts, dict):
        findings.append(issue("BLOCK", "backend_artifacts", "backend_artifacts must be an object"))
        artifacts = {}

    required_artifact_fields = {
        "brief_path": "TemporaryAnalysisBrief artifact is required",
        "rendered_output_path": "renderer output artifact is required",
    }
    for field, detail in required_artifact_fields.items():
        value = artifacts.get(field)
        if not isinstance(value, str) or not value.strip():
            findings.append(issue("BLOCK", field, detail))
            continue
        artifact_path = Path(value)
        if not artifact_path.is_absolute():
            artifact_path = ROOT / artifact_path
        if not artifact_path.exists():
            findings.append(issue("BLOCK", field + "_exists", f"{detail}; path does not exist: {value}"))

    if artifacts.get("gate_overall") != "PASS":
        findings.append(issue("BLOCK", "gate_overall", "TemporaryAnalysisBrief gate must PASS before frontend response"))

    if not findings:
        findings.append(issue("PASS", "force_route_audit", "temporary-analysis request used required chain"))

    overall = "BLOCK" if any(f["result"] == "BLOCK" for f in findings) else "PASS"
    return overall, findings, classified


def main():
    parser = argparse.ArgumentParser(description="Check temporary-analysis force-route policy")
    parser.add_argument("--request", default="")
    parser.add_argument("--audit-json", default="")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        policy = load_json(args.policy)
        if args.audit_json:
            record = load_json(args.audit_json)
            overall, findings, classified = audit_route_record(record, policy)
            payload = {"overall": overall, "classified": classified, "findings": findings}
            rc = 0 if overall == "PASS" else 2
        else:
            classified = classify_request(args.request, policy)
            payload = {"overall": "PASS", "classified": classified}
            rc = 0
    except Exception as exc:
        payload = {"overall": "BLOCK", "findings": [issue("BLOCK", "exception", f"{type(exc).__name__}: {exc}")]}
        rc = 2

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(payload.get("overall", "BLOCK"))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
