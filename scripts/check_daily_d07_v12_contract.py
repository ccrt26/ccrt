#!/usr/bin/env python3
"""P0-J: Daily D07_v1.2 contract gate.

This gate checks that a daily report sidecar carries the current v3.6.3
unified-interpretation fields, and validates the embedded raw interpretation
object with the project D07 validator.
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "重点股票" / "股票报告"
VALIDATOR = ROOT / "统一解读" / "validate_interpretation.py"
PIGEON_CFG = ROOT / "代码文件" / "信鸽信息采集" / "pigeon_config.json"

REQUIRED_TOP_LEVEL = [
    "framework_version",
    "logic_version",
    "interpretation_id",
    "conclusion_strength",
    "hypotheses",
    "evidence_gap_requests",
    "rule_refs",
    "knowledge_refs",
    "d07_interpretation",
    "unified_interpretation",
]

REQUIRED_ROLES = [
    "山猫_宏观",
    "信鸽_事件",
    "玉夜_数据",
    "流金_风控",
    "青山_信号",
    "腰子_整合",
]


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def date_compact(value):
    return value.replace("-", "")


def stock_pool():
    if PIGEON_CFG.exists():
        cfg = load_json(PIGEON_CFG)
        rows = []
        for item in cfg.get("target_stocks", []):
            code = str(item.get("code", ""))
            name = item.get("name", "")
            if code and name:
                rows.append((code, name))
        if rows:
            return rows
    rows = []
    for subdir in sorted(REPORT_DIR.glob("*(*)")):
        if not subdir.is_dir():
            continue
        text = subdir.name
        if "(" not in text or ")" not in text:
            continue
        name = text.rsplit("(", 1)[0]
        code = text.rsplit("(", 1)[1].rstrip(")")
        rows.append((code, name))
    return rows


def find_report(code, name, date_str):
    subdir = REPORT_DIR / f"{name}({code})"
    return subdir / f"{name}({code})日报_{date_str}.json"


def validate_d07_object(obj):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
        json.dump(obj, tmp, ensure_ascii=False)
        tmp_path = Path(tmp.name)
    try:
        proc = subprocess.run(
            [sys.executable, str(VALIDATOR), str(tmp_path), "--json"],
            cwd=str(ROOT),
            text=True,
            capture_output=True,
            timeout=60,
        )
        try:
            payload = json.loads(proc.stdout) if proc.stdout else {}
        except json.JSONDecodeError:
            payload = {"parse_error": proc.stdout}
        return proc.returncode, payload, proc.stderr.strip()
    finally:
        tmp_path.unlink(missing_ok=True)


def check_one(code, name, date_str):
    issues = []
    warns = []
    path = find_report(code, name, date_str)
    if not path.exists():
        return [f"日报sidecar不存在: {path}"], warns

    data = load_json(path)
    for field in REQUIRED_TOP_LEVEL:
        if field not in data:
            issues.append(f"缺少D07字段: {field}")

    if data.get("framework_version") != "D07_v1.2":
        issues.append(f"framework_version不是D07_v1.2: {data.get('framework_version')}")
    if "v3.6.3" not in str(data.get("logic_version", "")):
        issues.append(f"logic_version未指向v3.6.3: {data.get('logic_version')}")

    d07 = data.get("d07_interpretation")
    if isinstance(d07, dict):
        if d07.get("interpretation_id") != data.get("interpretation_id"):
            issues.append("top-level interpretation_id 与 d07_interpretation 不一致")
        if d07.get("framework_version") != "D07_v1.2":
            issues.append("d07_interpretation.framework_version 不是 D07_v1.2")
        rc, payload, stderr = validate_d07_object(d07)
        overall = payload.get("overall", "UNKNOWN")
        if rc == 2 or overall == "BLOCK":
            issues.append(f"d07_interpretation validator BLOCK: {payload.get('schema_validation', {})}")
        elif rc != 0 or overall not in ("PASS", "WARN"):
            issues.append(f"d07_interpretation validator异常: rc={rc} overall={overall} stderr={stderr}")
        elif overall == "WARN":
            warns.append("d07_interpretation validator WARN")
    elif "d07_interpretation" in data:
        issues.append("d07_interpretation 非dict")

    role_data = data.get("role_interpretations", {})
    if not isinstance(role_data, dict):
        issues.append("role_interpretations 非dict")
    else:
        for role in REQUIRED_ROLES:
            item = role_data.get(role)
            if not isinstance(item, dict):
                issues.append(f"role_interpretations 缺少或非dict: {role}")
            elif not item.get("职责") or not item.get("解读") or not item.get("结论"):
                issues.append(f"role_interpretations.{role} 缺职责/解读/结论")
        discussion = role_data.get("daily_discussion")
        if not isinstance(discussion, dict) or discussion.get("status") != "materialized":
            issues.append("daily_discussion 未物化为 materialized")

    gaps = data.get("evidence_gap_requests", [])
    degraded = data.get("degraded_items", [])
    if any("margin_detail" in str(item) for item in degraded):
        if not any(g.get("gap_type") == "field_missing" and g.get("status") == "open" for g in gaps if isinstance(g, dict)):
            issues.append("融资降级已声明，但 evidence_gap_requests 未登记 open field_missing")
        if data.get("conclusion_strength") == "可定性":
            issues.append("存在融资缺口时 conclusion_strength 不得为可定性")

    return issues, warns


def main():
    parser = argparse.ArgumentParser(description="P0-J: Daily D07_v1.2 contract gate")
    parser.add_argument("--date", required=True, help="YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--code", default="")
    parser.add_argument("--name", default="")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    dc = date_compact(args.date)
    targets = []
    if args.all:
        targets = stock_pool()
    elif args.code:
        name = args.name
        if not name:
            for c, n in stock_pool():
                if c == args.code:
                    name = n
                    break
        if not name:
            print(f"DAILY_D07_V12_CONTRACT: BLOCK\n- 股票名称缺失: {args.code}")
            return 2
        targets = [(args.code, name)]
    else:
        parser.error("需要 --code 或 --all")

    all_issues = []
    all_warns = []
    for code, name in targets:
        issues, warns = check_one(code, name, dc)
        label = f"{name}({code})"
        if issues:
            all_issues.extend([f"{label}: {item}" for item in issues])
        all_warns.extend([f"{label}: {item}" for item in warns])

    if all_issues:
        print("DAILY_D07_V12_CONTRACT: BLOCK")
        for item in all_issues:
            print(f"- {item}")
        for item in all_warns:
            print(f"- WARN: {item}")
        return 2

    print("DAILY_D07_V12_CONTRACT: PASS")
    for item in all_warns:
        print(f"- WARN: {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
