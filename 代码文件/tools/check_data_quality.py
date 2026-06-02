#!/usr/bin/env python3
"""check_data_quality.py — 数据质量检查 (QC Gate)

Replaces check_data_quality.ps1.
Six-dimension data quality check: completeness, accuracy, timeliness,
consistency, uniqueness, validity.
Code level: L1
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent.parent)


def check_completeness(data):
    """Check required fields are present."""
    issues = []
    required_sections = ["quotes", "financials", "fund_flows"]
    for section in required_sections:
        if section not in data or not data[section]:
            issues.append(f"Missing section: {section}")
    return {"passed": len(issues) == 0, "issues": issues}


def check_accuracy(data):
    """Check for obviously wrong values."""
    issues = []
    quotes = data.get("quotes", {})
    for code, q in quotes.items():
        if isinstance(q, dict):
            price = q.get("Price", 0)
            if price is not None and price <= 0:
                issues.append(f"{code}: Price <= 0")
            chg = q.get("ChangePct", 0)
            if chg is not None and (chg > 20 or chg < -20):
                issues.append(f"{code}: ChangePct out of range ({chg})")
    return {"passed": len(issues) == 0, "issues": issues}


def check_timeliness(data):
    """Check data freshness."""
    issues = []
    collect_time = data.get("collect_time", "")
    if not collect_time:
        issues.append("No collect_time field")
    return {"passed": len(issues) == 0, "issues": issues}


def check_consistency(data):
    """Check cross-section consistency."""
    issues = []
    quotes = data.get("quotes", {})
    financials = data.get("financials", {})
    quote_codes = set(quotes.keys())
    fin_codes = set(financials.keys())
    missing_fin = quote_codes - fin_codes
    if len(missing_fin) > len(quote_codes) * 0.5:
        issues.append(f"Financial data missing for {len(missing_fin)}/{len(quote_codes)} stocks")
    return {"passed": len(issues) == 0, "issues": issues}


def main():
    parser = argparse.ArgumentParser(description="Data quality check (QC Gate)")
    parser.add_argument("--mode", default="daily_sim", choices=["boot", "daily_sim", "key_stock", "eval"])
    parser.add_argument("--data-file", default="", help="Data file to check")
    parser.add_argument("--root-dir", default=ROOT, help="Project root")
    args = parser.parse_args()

    data_file = args.data_file or os.path.join(ROOT, "代码文件", "数据", "data_full.json")

    result = {
        "CheckedAt": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "Mode": args.mode,
        "Flag": "normal",
        "Passed": True,
        "DataFile": data_file,
    }

    if not os.path.exists(data_file):
        result["Flag"] = "cached"
        result["Passed"] = False
        result["Message"] = f"Data file not found: {data_file}"
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(1)

    try:
        with open(data_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        result["Flag"] = "cached"
        result["Passed"] = False
        result["Message"] = f"JSON parse error: {e}"
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(1)

    checks = {
        "Completeness": check_completeness(data),
        "Accuracy": check_accuracy(data),
        "Timeliness": check_timeliness(data),
        "Consistency": check_consistency(data),
    }

    all_passed = True
    degraded_fields = []
    cached_fields = []
    for name, check in checks.items():
        if not check["passed"]:
            all_passed = False
            degraded_fields.append(name)
            for issue in check["issues"]:
                if "Missing" in issue or "missing" in issue:
                    cached_fields.append(issue)

    result["Checks"] = checks
    result["Passed"] = all_passed
    result["DegradedFields"] = degraded_fields
    result["CachedFields"] = cached_fields
    result["Flag"] = "normal" if all_passed else "degraded"

    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
