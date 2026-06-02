#!/usr/bin/env python3
"""build_kline_cache.py — 从 data_full.json 提取K线数据，归档为独立缓存。

每条K线包含日期字段，支持至少120个交易日。
输出: 代码文件/数据/kline_cache/{code}.json

用法:
    python3 build_kline_cache.py                 # 构建全量
    python3 build_kline_cache.py --code 600114   # 单只股票

Code level: L1
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent.parent)
DATA_DIR = os.path.join(ROOT, "代码文件", "数据")
DATA_FULL = os.path.join(DATA_DIR, "data_full.json")
KLINE_CACHE_DIR = os.path.join(DATA_DIR, "kline_cache")
HOLIDAY_FILE = os.path.join(ROOT, "每日荐股", "运营记录", "holidays_2026.csv")


def load_holidays():
    holidays = set()
    if not os.path.exists(HOLIDAY_FILE):
        return holidays
    try:
        with open(HOLIDAY_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 2 and parts[0] == "holiday":
                    holidays.add(parts[1])
    except OSError:
        pass
    return holidays


def build_date_index(kclose_len, collect_time_str, holidays):
    """从KClose数组长度和采集时间推导日期索引。

    从collect_time的最近交易日开始，往前推算。
    """
    if collect_time_str:
        collect_dt = datetime.strptime(collect_time_str[:10], "%Y-%m-%d")
    else:
        collect_dt = datetime.now()

    while collect_dt.weekday() >= 5 or collect_dt.strftime("%Y-%m-%d") in holidays:
        collect_dt -= timedelta(days=1)

    dates = []
    d = collect_dt
    while len(dates) < kclose_len:
        if d.weekday() < 5 and d.strftime("%Y-%m-%d") not in holidays:
            dates.append(d.strftime("%Y-%m-%d"))
        d -= timedelta(days=1)
    return list(reversed(dates))


def build_kline_cache(target_code=None):
    os.makedirs(KLINE_CACHE_DIR, exist_ok=True)

    if not os.path.exists(DATA_FULL):
        print("ERROR: data_full.json 不存在")
        return 0

    with open(DATA_FULL, "r", encoding="utf-8") as f:
        raw = json.load(f)

    stocks = raw.get("Stocks", [])
    meta = raw.get("_Meta", {})
    collect_time = meta.get("collect_time", "")
    holidays = load_holidays()

    built = 0
    for s in stocks:
        code = s.get("Code", "")
        if target_code and code != target_code:
            continue

        kclose = s.get("KClose", [])
        kopen = s.get("KOpen", [])
        khigh = s.get("KHigh", [])
        klow = s.get("KLow", [])
        kvol = s.get("KVolume", [])

        if not kclose:
            continue

        dates = build_date_index(len(kclose), collect_time, holidays)

        bars = []
        for i in range(len(kclose)):
            bars.append({
                "date": dates[i] if i < len(dates) else "",
                "open": kopen[i] if i < len(kopen) else None,
                "high": khigh[i] if i < len(khigh) else None,
                "low": klow[i] if i < len(klow) else None,
                "close": kclose[i],
                "volume": kvol[i] if i < len(kvol) else None,
            })

        fpath = os.path.join(KLINE_CACHE_DIR, f"{code}.json")
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(bars, f, ensure_ascii=False)
        built += 1

    print(f"K线缓存已构建: {built} 只股票 → {KLINE_CACHE_DIR}/")
    return built


def main():
    parser = argparse.ArgumentParser(description="K线缓存构建")
    parser.add_argument("--code", help="仅构建指定股票")
    args = parser.parse_args()

    build_kline_cache(target_code=args.code)


if __name__ == "__main__":
    main()
