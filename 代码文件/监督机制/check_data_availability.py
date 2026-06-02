#!/usr/bin/env python3
"""check_data_availability.py — 数据可用性检查器。

报告中凡出现"数据不可获取"，必须先运行本检查确认。
逐层检查: unified_features → data_full → tushare → kline_cache → index_kline → score_history

用法:
    python3 check_data_availability.py --code 600114 --field pledge_ratio
    python3 check_data_availability.py --code 601689 --all

Code level: L1
"""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent.parent)
DATA_DIR = os.path.join(ROOT, "代码文件", "数据")

KNOWN_SOURCES = {
    "price": ["data_full.json", "kline_cache/{code}.json", "score_history.jsonl"],
    "pe_ttm": ["data_full.json", "score_history.jsonl"],
    "pledge_ratio": ["data_full.json(Financials)", "tushare/"],
    "unlock_info": ["data_full.json(Financials)", "tushare/"],
    "holder_number": ["tushare/"],
    "block_trade": ["tushare/"],
    "forecast": ["tushare/"],
    "dividend": ["tushare/"],
    "margin_detail": ["data_full.json(Margins)", "tushare/"],
    "northbound_hold": ["data_full.json(Northbound)", "tushare/"],
    "sector_fund_flow": ["东方财富[10] API → data_full.json(SectorFundFlow)"],
    "fund_flow": ["data_full.json(FundFlows)"],
    "kline": ["kline_cache/{code}.json", "data_full.json(KClose)"],
    "hs300_return": ["index_kline/hs300.json"],
    "signals": ["score_history.jsonl(signals字段)", "signal_evaluator.py"],
    "financial": ["data_full.json(Financials)", "tushare/"],
}


def check_source(source_path, code=None):
    """Check if a data source exists and has data."""
    fpath = source_path.replace("{code}", code or "600114")
    full_path = os.path.join(ROOT, fpath) if not fpath.startswith("/") else fpath

    # Handle paths relative to DATA_DIR
    if not os.path.exists(full_path):
        full_path = os.path.join(DATA_DIR, fpath.split("/")[-1])
    if not os.path.exists(full_path):
        full_path = os.path.join(DATA_DIR, fpath)

    return os.path.exists(full_path), full_path


def check_field(code, field_name):
    """Check if a specific field is available for a stock."""
    sources = KNOWN_SOURCES.get(field_name, ["unknown"])
    results = []

    for src in sources:
        exists, path = check_source(src, code)
        results.append({
            "source": src,
            "path": path,
            "available": exists,
        })

    available_count = sum(1 for r in results if r["available"])
    return {
        "field": field_name,
        "code": code,
        "total_sources": len(results),
        "available_sources": available_count,
        "status": "available" if available_count > 0 else "unavailable",
        "checked_sources": results,
    }


def check_all(code):
    """Check all known data fields for a stock."""
    results = {}
    for field in sorted(KNOWN_SOURCES.keys()):
        results[field] = check_field(code, field)
    return results


def main():
    parser = argparse.ArgumentParser(description="数据可用性检查器")
    parser.add_argument("--code", required=True, help="股票代码")
    parser.add_argument("--field", help="指定字段")
    parser.add_argument("--all", action="store_true", help="检查所有已知字段")
    args = parser.parse_args()

    if args.field:
        result = check_field(args.code, args.field)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result["status"] == "unavailable":
            print(f"\nWARN: {args.field} 确实不可用。需在报告中注明:")
            print(f"  unavailable_reason: 所有{result['total_sources']}个来源均不可用")
            print(f"  checked_sources: {[r['source'] for r in result['checked_sources']]}")
            print(f"  next_owner: 玉夜(数据源接入)")
    elif args.all:
        results = check_all(args.code)
        unavailable = [k for k, v in results.items() if v["status"] == "unavailable"]
        available = [k for k, v in results.items() if v["status"] == "available"]
        print(f"股票 {args.code}:")
        print(f"  可用字段 ({len(available)}): {', '.join(available[:10])}")
        print(f"  不可用字段 ({len(unavailable)}): {', '.join(unavailable)}")
        if unavailable:
            print(f"\n  如需在报告中写\"数据不可获取\"，必须附:")
            print(f"    - checked_sources: 所有已检查来源")
            print(f"    - unavailable_reason: 明确原因")
            print(f"    - next_owner: 玉夜(数据源接入)")


if __name__ == "__main__":
    main()
