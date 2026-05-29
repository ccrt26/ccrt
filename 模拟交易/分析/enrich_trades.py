#!/usr/bin/env python3
"""enrich_trades.py — 交易×事件×情绪三维数据联动 v1.0

Post-process batch: enriches transactions with 信鸽 event data (±3 day window)
and placeholder for 山猫 macro sentiment annotations.

Usage: python3 enrich_trades.py [--date YYYYMMDD]
Code level: L0
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = str(SCRIPT_DIR.parent.parent)


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def parse_date(date_str):
    return datetime.strptime(date_str, "%Y%m%d")


def load_events_db(root_dir):
    """Load 信鸽 events database."""
    events_path = os.path.join(root_dir, "重点股票", "消息面数据", "events_db.json")
    if not os.path.exists(events_path):
        print(f"  WARNING: events_db.json not found at {events_path}")
        return {}
    try:
        return load_json(events_path)
    except Exception as e:
        print(f"  WARNING: events_db.json parse error: {e}")
        return {}


def find_events_for_trade(events_db, code, trade_date_str, window_days=3):
    """Find events within ±window_days of trade date for a given stock."""
    trade_dt = parse_date(trade_date_str)
    start_dt = trade_dt - timedelta(days=window_days)
    end_dt = trade_dt + timedelta(days=window_days)

    matched = []
    # events_db structure: { "events": [ { "code": "...", "date": "...", ... } ] }
    events_list = events_db.get("events", []) if isinstance(events_db, dict) else events_db
    if not isinstance(events_list, list):
        return matched

    for evt in events_list:
        evt_code = str(evt.get("code", "")).zfill(6)
        search_code = str(code).zfill(6)
        if evt_code != search_code:
            continue
        evt_date = evt.get("date", "")
        if not evt_date:
            continue
        try:
            evt_dt = parse_date(evt_date)
        except ValueError:
            continue
        if start_dt <= evt_dt <= end_dt:
            impact = evt.get("impact_score", 0)
            if isinstance(impact, (int, float)) and impact >= 2:
                matched.append({
                    "date": evt_date,
                    "category": evt.get("category", ""),
                    "impact_score": impact,
                    "direction": evt.get("direction", ""),
                    "summary": evt.get("summary", evt.get("title", "")),
                })
            elif evt.get("p0", False):
                matched.append({
                    "date": evt_date,
                    "category": evt.get("category", "P0"),
                    "impact_score": impact,
                    "direction": evt.get("direction", ""),
                    "summary": evt.get("summary", evt.get("title", "")),
                    "p0": True,
                })

    # deduplicate: same date + category
    seen = set()
    deduped = []
    for m in matched:
        key = (m["date"], m["category"])
        if key not in seen:
            seen.add(key)
            deduped.append(m)
    return deduped


def load_existing_context(output_path):
    """Load existing trade_context.json for incremental update."""
    if os.path.exists(output_path):
        try:
            return load_json(output_path)
        except Exception:
            pass
    return {"generated_at": "", "trades": []}


def main():
    parser = argparse.ArgumentParser(description="Enrich trades with event & macro context")
    parser.add_argument("--date", default=datetime.now().strftime("%Y%m%d"), help="Run date")
    parser.add_argument("--root-dir", default=ROOT, help="Project root directory")
    args = parser.parse_args()

    root_dir = args.root_dir
    canon_base = os.path.join(root_dir, "历史数据")
    txn_file = os.path.join(canon_base, "00_核心交易", "transactions.csv")
    output_path = os.path.join(root_dir, "模拟交易", "分析", "trade_context.json")
    existing_context_path = os.path.join(root_dir, "模拟交易", "分析", "macro_annotations.json")

    if not os.path.exists(txn_file):
        print("transactions.csv not found, nothing to enrich")
        sys.exit(0)

    # Load event data
    print("加载事件数据库...")
    events_db = load_events_db(root_dir)

    # Load macro annotations (山猫 manual, placeholder)
    macro_annotations = {}
    if os.path.exists(existing_context_path):
        try:
            macro_annotations = load_json(existing_context_path)
        except Exception:
            pass

    # Parse transactions
    print("解析交易流水...")
    trades = []
    with open(txn_file, "r", encoding="utf-8") as f:
        lines = f.read().strip().split("\n")
    if len(lines) < 2:
        print("No transactions to enrich")
        sys.exit(0)

    header = lines[0].split(",")
    for line in lines[1:]:
        parts = line.split(",")
        if len(parts) < 5:
            continue
        trade = {
            "date": parts[0],
            "code": parts[1],
            "name": parts[2],
            "action": parts[3],
            "price": parts[4],
            "shares": parts[5] if len(parts) > 5 else "",
            "reason": parts[10] if len(parts) > 10 else "",
        }
        # Enrich with events
        events = find_events_for_trade(events_db, trade["code"], trade["date"])
        trade["events_window"] = {
            "start": (parse_date(trade["date"]) - timedelta(days=3)).strftime("%Y%m%d"),
            "end": (parse_date(trade["date"]) + timedelta(days=3)).strftime("%Y%m%d"),
            "events": events,
        }
        # Macro context (placeholder)
        macro_key = trade["date"]
        trade["macro_context"] = macro_annotations.get(macro_key, {
            "market_sentiment": None,
            "csi300_direction": None,
            "annotated_by": None,
            "annotated_at": None,
        })
        trades.append(trade)

    output = {
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "trade_count": len(trades),
        "trades": trades,
    }

    save_json(output_path, output)
    print(f"trade_context.json written: {len(trades)} trades enriched, {output_path}")

    # Summary
    trades_with_events = sum(1 for t in trades if t["events_window"]["events"])
    print(f"  含事件关联: {trades_with_events}/{len(trades)}")


if __name__ == "__main__":
    main()
