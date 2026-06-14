#!/usr/bin/env python3
"""DQ issue classifier -- 细化 DQ-W7/DQ-W9 的阻断/非阻断展示。"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "configs" / "data_quality_issue_policy.json"

def _load_policy() -> dict:
    if POLICY_PATH.exists():
        return json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    return {"policies": {}}

def _classify_issue(issue: dict, report: dict, policies: dict) -> dict:
    issue_id = issue.get("id", "")
    policy = policies.get(issue_id, {})
    classified = dict(issue)

    if issue_id == "DQ-W7":
        classified["category"] = policy.get("category", "price_statistical_outlier")
        classified["display_level"] = policy.get("display_level", "WARN_NON_BLOCKING")
        classified["release_blocking"] = False
        classified["action"] = policy.get("action", "REVIEW_ONLY")
        classified["explain"] = policy.get("reason", "价格统计离群提示，不代表数据链不可用。")
        return classified

    if issue_id == "DQ-W9":
        required_missing = int(report.get("required_missing", 0) or 0)
        optional_missing = int(report.get("optional_missing", 0) or 0)
        missing_fields = int(report.get("metrics", {}).get("missing_fields", 0) or 0)
        classified["category"] = policy.get("category", "field_applicability_gap")
        classified["required_missing"] = required_missing
        classified["optional_missing"] = optional_missing if optional_missing else missing_fields
        classified["release_blocking"] = required_missing > 0
        classified["display_level"] = "BLOCKING_REQUIRED_GAP" if required_missing > 0 else policy.get("display_level", "WARN_NON_BLOCKING")
        classified["action"] = "FIX_REQUIRED_FIELDS" if required_missing > 0 else policy.get("action", "OPTIONAL_GAP_TRACKING")
        classified["explain"] = "存在必填字段缺失，必须阻断。" if required_missing > 0 else policy.get("reason", "可选字段缺失，仅作为质量观察项。")
        return classified

    classified["category"] = policy.get("category", "generic_quality_warning")
    classified["display_level"] = policy.get("display_level", issue.get("severity", "WARN"))
    classified["release_blocking"] = issue.get("severity") == "FAIL"
    classified["action"] = policy.get("action", "TRACK")
    return classified

def classify_report(report: dict, target_date: str = "") -> dict:
    policy = _load_policy()
    policies = policy.get("policies", {})
    issues = report.get("issues", [])
    classified_issues = [_classify_issue(i, report, policies) for i in issues]
    blocking = [i for i in classified_issues if i.get("release_blocking") is True]
    non_blocking = [i for i in classified_issues if i.get("release_blocking") is not True]
    report["target_date"] = target_date or report.get("target_date", "")
    report["issues"] = classified_issues
    report["issue_classification_version"] = policy.get("version", "1.0")
    report["issue_summary"] = {
        "total_issues": len(classified_issues),
        "blocking_issues": len(blocking),
        "non_blocking_warnings": len(non_blocking),
        "warn_non_blocking_ids": [i.get("id") for i in non_blocking],
        "blocking_ids": [i.get("id") for i in blocking],
        "required_missing": int(report.get("required_missing", 0) or 0),
        "optional_missing": int(report.get("optional_missing", 0) or 0),
        "not_applicable_fields": int(report.get("metrics", {}).get("not_applicable_fields", 0) or 0),
    }
    report["release_blocking"] = bool(blocking) or bool(report.get("blocked"))
    report["display_overall"] = "BLOCK" if report["release_blocking"] else "WARN_NON_BLOCKING" if classified_issues else "PASS"
    report["overall_gate"] = "BLOCK" if report["release_blocking"] else "PASS_WITH_NON_BLOCKING_WARNINGS" if classified_issues else "PASS"
    return report
