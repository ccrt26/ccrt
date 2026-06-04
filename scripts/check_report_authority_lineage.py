#!/usr/bin/env python3
"""
第5阶段：报告权威继承检查闸门

检查当前日报是否混用旧深度分析 ID、旧日报、系统附录或非权威 baseline。

检查项：
  1. baseline_id 是否等于 resolve_current_baseline.py 返回的当前有效基线
  2. 是否出现 deep_* 旧格式 baseline ID
  3. 是否将深度分析/系统附录/旧日报标记为 baseline/行情/资金/板块的权威源

用法:
  python3 scripts/check_report_authority_lineage.py --code 600114 --name 东睦股份 --date 20260602
  python3 scripts/check_report_authority_lineage.py --all --date 20260602
  python3 scripts/check_report_authority_lineage.py --code 600114 --name 东睦股份 --date 20260602 --json

退出码:
  0 = PASS
  1 = 脚本异常
  2 = 任一 BLOCK
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = PROJECT_ROOT / "00_项目地基" / "02_权威注册表" / "baseline_registry.json"
REPORT_DIR = PROJECT_ROOT / "重点股票" / "股票报告"
PIGEON_CONFIG = PROJECT_ROOT / "代码文件" / "信鸽信息采集" / "pigeon_config.json"


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_text(path):
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def get_stock_pool():
    if not PIGEON_CONFIG.exists():
        return []
    try:
        cfg = load_json(PIGEON_CONFIG)
    except Exception:
        return []
    stocks = cfg.get("target_stocks", []) or cfg.get("stocks", [])
    result = []
    for s in stocks:
        code = str(s.get("code") or s.get("Code", ""))
        name = s.get("name") or s.get("Name", "")
        if code and name:
            result.append((code, name))
    return result


def get_stock_pool_from_reports():
    stocks = []
    if not REPORT_DIR.exists():
        return stocks
    for subdir in sorted(REPORT_DIR.iterdir()):
        if not subdir.is_dir():
            continue
        m = re.match(r'(.+)\((\d{6})\)', subdir.name)
        if m:
            stocks.append((m.group(2), m.group(1)))
    return stocks


def find_report_file(code, name, date_compact, ext):
    subdir = REPORT_DIR / f"{name}({code})"
    return subdir / f"{name}({code})日报_{date_compact}{ext}"


def make_check(check_id, field, status, expected, actual, source, message):
    return {
        "check_id": check_id,
        "field": field,
        "status": status,
        "expected": expected,
        "actual": actual,
        "source": source,
        "message": message,
    }


# Resolve current baseline
def resolve_baseline(entries, code, trade_date):
    td = datetime.strptime(trade_date.replace("-", ""), "%Y%m%d").date()
    matched = []
    for entry in entries:
        if entry.get("stock_code") != code:
            continue
        if entry.get("status") == "deprecated":
            continue
        bd_s = entry.get("baseline_date", "")
        vu_s = entry.get("valid_until", "")
        try:
            bd = datetime.strptime(bd_s, "%Y-%m-%d").date() if bd_s else None
            vu = datetime.strptime(vu_s, "%Y-%m-%d").date() if vu_s else None
        except ValueError:
            continue
        if bd and bd > td:
            continue
        if vu and vu < td:
            continue
        matched.append(entry)
    if len(matched) == 1:
        return matched[0]["baseline_id"]
    return None


# Check for old deep_* pattern
DEEP_PATTERN = re.compile(r'\d{6}_deep_\d{8}_v?[\d.]+')


def check_one(code, name, trade_date_str, entries):
    result = {
        "stock_code": code,
        "stock_name": name,
        "trade_date": trade_date_str,
        "result": "PASS",
        "checks": [],
    }
    dc = trade_date_str.replace("-", "")

    sidecar_path = find_report_file(code, name, dc, ".json")
    md_path = find_report_file(code, name, dc, ".md")

    if not sidecar_path.exists() or not md_path.exists():
        result["result"] = "BLOCK"
        result["checks"].append(make_check("FILE", "all", "BLOCK", "日报文件应存在", "缺失",
                                            f"sidecar 或 MD 不存在"))
        return result

    sidecar = load_json(sidecar_path)
    md_text = load_text(md_path)

    # C1: baseline_id = registry
    sc_bid = sidecar.get("baseline_id", "")
    expected_bid = resolve_baseline(entries, code, trade_date_str)

    if expected_bid:
        # Check sidecar baseline_id
        if not sc_bid:
            result["result"] = "BLOCK"
            result["checks"].append(make_check("C1", "baseline_id", "BLOCK",
                                                expected_bid, "(缺失)", "sidecar",
                                                f"sidecar baseline_id 缺失，应={expected_bid}"))
        elif sc_bid != expected_bid:
            result["result"] = "BLOCK"
            result["checks"].append(make_check("C1", "baseline_id", "BLOCK",
                                                expected_bid, sc_bid, "sidecar",
                                                f"sidecar baseline_id={sc_bid} ≠ registry={expected_bid}"))

        # Check MD baseline_id
        md_bid_match = re.search(r'baseline_id[：:]\s*([^\s\|\)\]\*,\n]+)', md_text)
        if not md_bid_match:
            result["result"] = "BLOCK"
            result["checks"].append(make_check("C1-MD", "baseline_id", "BLOCK",
                                                expected_bid, "(缺失)", "MD",
                                                f"MD 未找到 baseline_id 声明"))
        else:
            md_bid = md_bid_match.group(1).strip()
            if md_bid != expected_bid:
                result["result"] = "BLOCK"
                result["checks"].append(make_check("C1-MD", "baseline_id", "BLOCK",
                                                    expected_bid, md_bid, "MD",
                                                    f"MD baseline_id={md_bid} ≠ registry={expected_bid}"))

        # PASS 判定：sidecar 和 MD 均通过时才算 PASS
        has_sidecar_pass = sc_bid and sc_bid == expected_bid
        has_md_pass = md_bid_match and md_bid_match.group(1).strip() == expected_bid
        if has_sidecar_pass and has_md_pass:
            result["checks"].append(make_check("C1", "baseline_id", "PASS",
                                                expected_bid, sc_bid, "sidecar",
                                                "sidecar与MD均正确"))
        elif has_sidecar_pass and not has_md_pass:
            pass  # BLOCK已由MD检查产生
        elif not has_sidecar_pass and has_md_pass:
            pass  # BLOCK已由sidecar检查产生
    else:
        result["result"] = "BLOCK"
        result["checks"].append(make_check("C1", "baseline_id", "BLOCK",
                                            "有效基线", "无", "registry",
                                            f"注册表中 {trade_date_str} 无有效基线"))

    # C2: deep_* format check
    md_old = DEEP_PATTERN.findall(md_text)
    sc_text = json.dumps(sidecar, ensure_ascii=False)
    sc_old = DEEP_PATTERN.findall(sc_text)

    combined_old = list(set(md_old + sc_old))
    if combined_old:
        result["result"] = "BLOCK"
        result["checks"].append(make_check("C2", "deep_pattern", "BLOCK",
                                            "无旧 deep_* 格式", "; ".join(combined_old), "MD/sidecar",
                                            f"日报内出现旧 deep_* baseline ID 格式: {combined_old}"))
    else:
        result["checks"].append(make_check("C2", "deep_pattern", "PASS",
                                            "无旧格式", "无", "MD/sidecar", ""))

    # C3: Forbidden authority source check
    forbidden_tells = [
        ("深度分析正文", r'深度分析[^。]*权威|深度分析[^。]*唯一[^。]*来源|以深度分析为准'),
        ("系统附录", r'系统附录[^。]*权威|系统附录[^。]*来源'),
        ("旧日报", r'旧日报[^。]*权威|历史日报[^。]*依据|昨日日报[^。]*来源'),
    ]
    combined_text = md_text[:5000] + "\n" + sc_text[:5000]

    c3_issues = []
    for name, pat in forbidden_tells:
        if re.search(pat, combined_text):
            c3_issues.append(f"将{name}标记为权威源")

    if c3_issues:
        result["result"] = "BLOCK"
        result["checks"].append(make_check("C3", "forbidden_authority", "BLOCK",
                                            "不得使用深度分析/旧日报/系统附录作为权威源",
                                            "; ".join(c3_issues), "MD/sidecar",
                                            f"日报内禁止引用: {'; '.join(c3_issues)}"))
    else:
        result["checks"].append(make_check("C3", "forbidden_authority", "PASS",
                                            "无禁用权威引用", "无", "MD/sidecar", ""))

    return result


def format_text(result):
    lines = []
    lines.append(f"{'='*60}")
    lines.append(f" {result['stock_name']}({result['stock_code']}) | {result['trade_date']}")
    lines.append(f"{'='*60}")
    lines.append(f"  总结果: {result['result']}")
    lines.append("")
    for chk in result.get("checks", []):
        icon = {"PASS": "✅", "BLOCK": "❌"}.get(chk["status"], "❓")
        lines.append(f"  {icon} {chk['check_id']} {chk['field']}: {chk['status']}")
        if chk.get("expected") or chk.get("actual"):
            lines.append(f"     预期={chk['expected'][:50]} | 实际={chk['actual'][:50]}")
        if chk.get("message"):
            lines.append(f"     消息: {chk['message']}")
    pass_c = sum(1 for c in result["checks"] if c["status"] == "PASS")
    block_c = sum(1 for c in result["checks"] if c["status"] == "BLOCK")
    lines.append(f"\n  明细: ✅PASS={pass_c} ❌BLOCK={block_c} / TOTAL={len(result['checks'])}")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="第5阶段：报告权威继承检查闸门")
    parser.add_argument("--code", help="股票代码")
    parser.add_argument("--name", help="股票名称")
    parser.add_argument("--date", required=True, help="交易日期 YYYYMMDD 或 YYYY-MM-DD")
    parser.add_argument("--all", action="store_true", help="检查全部重点股票")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    args = parser.parse_args()

    if not REGISTRY_PATH.exists():
        print("ERROR: baseline_registry.json 不存在。请先运行 --rebuild-registry")
        return 1
    registry = load_json(REGISTRY_PATH)
    entries = registry.get("entries", [])

    stocks = []
    if args.all:
        stocks = get_stock_pool()
        if not stocks:
            stocks = get_stock_pool_from_reports()
        if not stocks:
            print("ERROR: 无法获取股票池", file=sys.stderr)
            return 1
    elif args.code and args.name:
        stocks = [(args.code, args.name)]
    else:
        parser.error("需要 --code --name 或 --all")

    results = []
    all_pass = True
    for code, name in stocks:
        res = check_one(code, name, args.date, entries)
        results.append(res)
        if res["result"] == "BLOCK":
            all_pass = False

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for r in results:
            print(format_text(r))
        pass_c = sum(1 for r in results if r["result"] == "PASS")
        block_c = sum(1 for r in results if r["result"] == "BLOCK")
        print(f"{'='*60}")
        print(f"  PASS: {pass_c} | BLOCK: {block_c} | TOTAL: {len(results)}")
        print(f"{'='*60}")

    return 0 if all_pass else 2


if __name__ == "__main__":
    sys.exit(main())
