#!/usr/bin/env python3
"""benchmark_data.py — 获取沪深300和申万行业指数收益数据。

数据源优先级:
  1. index_kline/{index_id}.json (本地缓存, 新浪K线[2])
  2. data_full.json 市场平均涨跌幅 (近似兜底)
  3. 不可用 → 显式返回 None, 调用方标记 unavailable

Code level: L1
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent.parent)
CACHE_DIR = os.path.join(ROOT, "代码文件", "数据")
INDEX_CACHE_DIR = os.path.join(CACHE_DIR, "index_kline")

BENCHMARK_CODES = {
    "hs300": {"code": "sh000300", "name": "沪深300", "source": "[2]", "cache_file": "hs300.json"},
    "csi500": {"code": "sh000905", "name": "中证500", "source": "[2]", "cache_file": "csi500.json"},
    "csi1000": {"code": "sh000852", "name": "中证1000", "source": "[2]", "cache_file": "csi1000.json"},
}

SECTOR_INDEX_MAP = {
    "计算机": "BK0476", "电子": "BK0477", "医药生物": "BK0465",
    "食品饮料": "BK0438", "银行": "BK0439", "非银金融": "BK0440",
    "房地产": "BK0441", "汽车": "BK0442", "机械设备": "BK0474",
    "电力设备": "BK0475", "通信": "BK0478", "传媒": "BK0479",
    "有色金属": "BK0447", "化工": "BK0444", "国防军工": "BK0480",
}


def _norm(date_str):
    """Normalize date to both YYYYMMDD and YYYY-MM-DD formats."""
    clean = date_str.replace("-", "").strip()
    return clean, f"{clean[:4]}-{clean[4:6]}-{clean[6:]}"


def get_benchmark_return(benchmark_id, target_date_str):
    """获取指定基准在指定日期的日收益率。

    优先级: index_kline缓存 → data_full市场均值(标记fallback) → None

    Args:
        benchmark_id: "hs300" / "csi500" / "csi1000"
        target_date_str: "YYYYMMDD" or "YYYY-MM-DD"

    Returns:
        (return_pct, source_label) or (None, None)
    """
    cfg = BENCHMARK_CODES.get(benchmark_id)
    if not cfg:
        return None, None

    date_compact, date_formatted = _norm(target_date_str)

    # Priority 1: index_kline local cache
    cache_file = os.path.join(INDEX_CACHE_DIR, cfg["cache_file"])
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            for i, bar in enumerate(data):
                bar_date = bar.get("date", "")
                if bar_date in (date_compact, date_formatted):
                    if i > 0:
                        prev = data[i - 1].get("close", 0)
                        curr = bar.get("close", 0)
                        if prev and prev != 0:
                            return round((curr - prev) / prev * 100, 2), cfg["source"]
                    return None, cfg["source"]
        except (json.JSONDecodeError, OSError, KeyError):
            pass

    # Priority 2: fallback to data_full market average
    data_file = os.path.join(CACHE_DIR, "data_full.json")
    if os.path.exists(data_file):
        try:
            with open(data_file, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except (json.JSONDecodeError, OSError):
            raw = None
        if raw:
            stocks = raw.get("Stocks", [])
            changes = [s.get("ChangePct", 0) for s in stocks if s.get("ChangePct") is not None]
            if changes:
                return round(sum(changes) / len(changes), 2), "fallback_market_avg"

    return None, None


def get_sector_return(sector_name, target_date_str):
    """获取申万行业指数日收益率。当前无独立行业指数缓存，返回None。"""
    return None


def get_market_avg_return(date_str):
    """获取全A股平均涨跌幅（从data_full.json中计算）。"""
    data_file = os.path.join(CACHE_DIR, "data_full.json")
    if not os.path.exists(data_file):
        return None
    try:
        with open(data_file, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    stocks = raw.get("Stocks", [])
    changes = [s.get("ChangePct", 0) for s in stocks if s.get("ChangePct") is not None]
    if not changes:
        return None
    return round(sum(changes) / len(changes), 2)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="基准数据查询")
    parser.add_argument("--benchmark", default="hs300", choices=list(BENCHMARK_CODES.keys()))
    parser.add_argument("--date", required=True, help="日期 YYYYMMDD or YYYY-MM-DD")
    args = parser.parse_args()

    ret, source = get_benchmark_return(args.benchmark, args.date)
    if ret is not None:
        src_label = source if source != "fallback_market_avg" else f"{source} (非指数真实值)"
        print(f"{BENCHMARK_CODES[args.benchmark]['name']} {args.date} 收益: {ret}% [来源: {src_label}]")
        if source == "fallback_market_avg":
            print("WARN: 使用市场均值兜底，非真实指数收益。建议运行 index_kline_fetcher.py")
            sys.exit(1)
    else:
        print(f"WARN: {BENCHMARK_CODES[args.benchmark]['name']} {args.date} 数据不可用")
        print("      建议: 运行 python3 代码文件/数据/index_kline_fetcher.py --index hs300")
        sys.exit(1)


if __name__ == "__main__":
    main()
