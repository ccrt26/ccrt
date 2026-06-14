#!/usr/bin/env python3
"""
第1阶段: Baseline 当前有效基线解析器。

根据 code/name/date 从 baseline_registry.json 查询当前唯一有效 baseline。

用法:
  python3 scripts/resolve_current_baseline.py --code 600114 --name 东睦股份 --date 20260602
  python3 scripts/resolve_current_baseline.py --code 600114 --name 东睦股份 --date 20260602 --json
  python3 scripts/resolve_current_baseline.py --all --date 20260602

退出码:
  0 = 查询成功且每只股票唯一有效 baseline
  1 = 脚本异常
  2 = 无有效 baseline 或多有效 baseline
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
PIGEON_CONFIG = PROJECT_ROOT / "代码文件" / "信鸽信息采集" / "pigeon_config.json"
REPORT_DIR = PROJECT_ROOT / "重点股票" / "股票报告"


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_date(date_str):
    d = date_str.replace("-", "")
    if len(d) != 8:
        raise ValueError(f"日期格式非法: {date_str}")
    return datetime.strptime(d, "%Y%m%d").date()


def find_effective(entries, code, td):
    """找 date 当天有效 baseline 列表（0/1/多）"""
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
    return matched


def get_stock_pool():
    stocks = []
    if PIGEON_CONFIG.exists():
        try:
            cfg = load_json(PIGEON_CONFIG)
            ss = cfg.get("target_stocks", []) or cfg.get("stocks", [])
            for s in ss:
                code = str(s.get("code") or s.get("Code", ""))
                name = s.get("name") or s.get("Name", "")
                if code and name:
                    stocks.append((code, name))
        except Exception:
            pass
    if not stocks and REPORT_DIR.exists():
        for subdir in sorted(REPORT_DIR.iterdir()):
            if not subdir.is_dir():
                continue
            m = re.match(r'(.+)\((\d{6})\)', subdir.name)
            if m:
                stocks.append((m.group(2), m.group(1)))
    return stocks


def resolve_one(code, name, trade_date_str, entries):
    td = parse_date(trade_date_str)
    matched = find_effective(entries, code, td)

    if len(matched) == 0:
        return {"stock_code": code, "stock_name": name, "trade_date": trade_date_str,
                "result": "BLOCK", "reason": "无有效基线", "baseline_id": None,
                "baseline_file": None, "baseline_date": None, "valid_until": None,
                "status": None, "key_fields": {}}

    if len(matched) > 1:
        deep_matched = [e for e in matched if e.get("source_deep_report_path")]
        if len(deep_matched) == 1:
            matched = deep_matched
        elif len(deep_matched) > 1:
            ids = [e["baseline_id"] for e in deep_matched]
            return {"stock_code": code, "stock_name": name, "trade_date": trade_date_str,
                    "result": "BLOCK", "reason": f"多有效深度基线: {ids}", "baseline_id": None,
                    "baseline_file": None, "baseline_date": None, "valid_until": None,
                    "status": None, "key_fields": {}}
        else:
            ids = [e["baseline_id"] for e in matched]
            return {"stock_code": code, "stock_name": name, "trade_date": trade_date_str,
                    "result": "BLOCK", "reason": f"多有效基线: {ids}", "baseline_id": None,
                    "baseline_file": None, "baseline_date": None, "valid_until": None,
                    "status": None, "key_fields": {}}

    bl = matched[0]
    kf = bl.get("key_fields", {})
    return {
        "stock_code": code,
        "stock_name": name,
        "trade_date": trade_date_str,
        "result": "PASS",
        "reason": "",
        "baseline_id": bl["baseline_id"],
        "baseline_file": bl.get("baseline_file", ""),
        "baseline_date": bl.get("baseline_date", ""),
        "valid_until": bl.get("valid_until", ""),
        "status": bl.get("status", ""),
        "key_fields": {
            "key_support_price": kf.get("key_support_price"),
            "key_pressure_price": kf.get("key_pressure_price"),
            "stop_loss_price": kf.get("stop_loss_price"),
        },
        "core_thesis": bl.get("core_thesis", ""),
        "overall_risk_level": bl.get("overall_risk_level", ""),
    }


def format_text(res):
    lines = []
    lines.append(f"{'='*60}")
    lines.append(f" {res['stock_name']}({res['stock_code']}) | {res['trade_date']}")
    lines.append(f"{'='*60}")
    if res["result"] == "PASS":
        lines.append(f"  结果:        ✅ PASS")
        lines.append(f"  baseline_id: {res['baseline_id']}")
        lines.append(f"  基线文件:    {res['baseline_file']}")
        lines.append(f"  基线日期:    {res['baseline_date']}")
        lines.append(f"  有效期至:    {res['valid_until']}")
        lines.append(f"  状态:        {res['status']}")
        kf = res.get("key_fields", {})
        lines.append(f"  支撑价:      {kf.get('key_support_price', 'N/A')}")
        lines.append(f"  压力价:      {kf.get('key_pressure_price', 'N/A')}")
        lines.append(f"  止损价:      {kf.get('stop_loss_price', 'N/A')}")
        if res.get("core_thesis"):
            lines.append(f"  核心逻辑:    {res['core_thesis'][:80]}")
        if res.get("overall_risk_level"):
            lines.append(f"  风险等级:    {res['overall_risk_level']}")
    else:
        lines.append(f"  结果: ❌ BLOCK")
        lines.append(f"  原因: {res.get('reason', '')}")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="当前有效基线解析器")
    parser.add_argument("--code", help="股票代码")
    parser.add_argument("--name", help="股票名称")
    parser.add_argument("--date", required=True, help="交易日期 YYYYMMDD 或 YYYY-MM-DD")
    parser.add_argument("--all", action="store_true", help="查询全部重点股票")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    args = parser.parse_args()

    if not REGISTRY_PATH.exists():
        print(f"ERROR: 注册表不存在: {REGISTRY_PATH}", file=sys.stderr)
        print("请先运行 python3 scripts/check_baseline_authority.py --rebuild-registry", file=sys.stderr)
        return 1

    registry = load_json(REGISTRY_PATH)
    entries = registry.get("entries", [])

    stocks = []
    if args.all:
        stocks = get_stock_pool()
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
        res = resolve_one(code, name, args.date, entries)
        results.append(res)
        if res["result"] != "PASS":
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
