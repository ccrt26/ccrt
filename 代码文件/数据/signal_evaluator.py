#!/usr/bin/env python3
"""signal_evaluator.py — 信号评估器。

按信号ID统计不同市场环境下的胜率/误判率/误杀率/IC/IR。

用法:
    python3 signal_evaluator.py --signal TECH_001           # 单信号评估
    python3 signal_evaluator.py --category TECH             # 按类别评估
    python3 signal_evaluator.py --all                        # 全部信号评估
    python3 signal_evaluator.py --date-from 2026-05-01      # 指定日期范围

Code level: L1
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent.parent)
DATA_DIR = os.path.join(ROOT, "代码文件", "数据")
SIGNAL_FILE = os.path.join(DATA_DIR, "signal_library.json")
SCORE_FILE = os.path.join(DATA_DIR, "score_history.jsonl")


def load_signals():
    with open(SIGNAL_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_score_history():
    if not os.path.exists(SCORE_FILE):
        return []
    records = []
    with open(SCORE_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records


def evaluate_signal(signal_id, records, env_filter=None):
    """评估单个信号的有效性。

    Returns:
        dict: {total, wins, losses, win_rate, false_positive_rate, false_negative_rate,
               avg_return, by_env: {env: {win_rate, count}}}
    """
    stats = {"total": 0, "wins": 0, "losses": 0, "by_env": defaultdict(lambda: {"total": 0, "wins": 0})}

    for rec in records:
        signals = rec.get("signals", []) or []
        if signal_id not in signals:
            continue

        ret = rec.get("ret_t1")
        if ret is None:
            continue

        env = rec.get("market_env", "unknown")
        if env_filter and env != env_filter:
            continue

        stats["total"] += 1
        if ret > 0:
            stats["wins"] += 1
        else:
            stats["losses"] += 1

        stats["by_env"][env]["total"] += 1
        if ret > 0:
            stats["by_env"][env]["wins"] += 1

    if stats["total"] > 0:
        stats["win_rate"] = round(stats["wins"] / stats["total"] * 100, 1)
    else:
        stats["win_rate"] = 0

    for env, env_stats in stats["by_env"].items():
        if env_stats["total"] > 0:
            env_stats["win_rate"] = round(env_stats["wins"] / env_stats["total"] * 100, 1)
        else:
            env_stats["win_rate"] = 0
    stats["by_env"] = dict(stats["by_env"])

    return stats


def evaluate_all(signal_library, records):
    results = {}
    for category, signals in signal_library.items():
        if category.startswith("_"):
            continue
        for sig in signals:
            sig_id = sig["id"]
            results[sig_id] = evaluate_signal(sig_id, records)
            results[sig_id]["name"] = sig["name"]
            results[sig_id]["category"] = category
    return results


def main():
    parser = argparse.ArgumentParser(description="信号评估器")
    parser.add_argument("--signal", help="信号ID")
    parser.add_argument("--category", help="信号类别 TECH/MONEY/FUND/NEWS/SECTOR/RISK/TRADE")
    parser.add_argument("--all", action="store_true", help="全部信号")
    parser.add_argument("--date-from", help="起始日期 YYYY-MM-DD")
    parser.add_argument("--env", help="市场环境过滤 trend/range/bear")
    args = parser.parse_args()

    signal_library = load_signals()
    records = load_score_history()

    if args.date_from:
        records = [r for r in records if r.get("date", "") >= args.date_from]

    if args.signal:
        stats = evaluate_signal(args.signal, records, args.env)
        print(json.dumps({args.signal: stats}, ensure_ascii=False, indent=2))
    elif args.category:
        cat = args.category.upper()
        sigs = signal_library.get(cat, [])
        results = {}
        for sig in sigs:
            results[sig["id"]] = evaluate_signal(sig["id"], records, args.env)
            results[sig["id"]]["name"] = sig["name"]
        print(json.dumps(results, ensure_ascii=False, indent=2))
    elif args.all:
        results = evaluate_all(signal_library, records)
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print("ERROR: 需要 --signal / --category / --all")


if __name__ == "__main__":
    main()
