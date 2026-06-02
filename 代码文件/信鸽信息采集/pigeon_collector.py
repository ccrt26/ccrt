#!/usr/bin/env python3
"""信鸽信息采集主控

Replaces pigeon_collector.ps1. macOS compatible.
每日15:30触发，节假日自动跳过。
采集流程: baostock→cninfo→东财研报→五层过滤→输出→缓存
Code level: L1
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent.parent)
SCRIPT_DIR = os.path.join(ROOT, "代码文件", "信鸽信息采集")
CONFIG_PATH = os.path.join(SCRIPT_DIR, "pigeon_config.json")

# Import local modules
sys.path.insert(0, SCRIPT_DIR)
from pigeon_cninfo import fetch_announcements, fetch_announcements_backup
from pigeon_filter import pigeon_filter
from pigeon_output import export_events, update_cache


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_existing_events(stock_code, db_path):
    """近3日已入库事件（用于去重）"""
    if not os.path.exists(db_path):
        return []
    try:
        with open(db_path, "r", encoding="utf-8") as f:
            all_events = json.load(f)
        cutoff = (date.today() - timedelta(days=3)).isoformat()
        return [e for e in all_events if e.get("code") == stock_code and e.get("fetch_date", "") >= cutoff]
    except Exception:
        return []


def fetch_baostock_forecast(stock_code, stock_name, start_date, end_date):
    """baostock[14] 业绩预告/快报"""
    market = "sh" if stock_code.startswith("6") else "sz"
    baostock_code = f"{market}.{stock_code}"
    baostock_script = os.path.join(ROOT, "代码文件", "每日荐股", "scripts",
                                   "stock_data_fetcher_baostock.py")
    results = []

    if not os.path.exists(baostock_script):
        print("  baostock bridge not found, skipping")
        return results

    for action, label in [("forecast", "业绩预告"), ("express", "业绩快报")]:
        try:
            proc = subprocess.run(
                [sys.executable, baostock_script, action,
                 "--code", baostock_code, "--start", start_date, "--end", end_date],
                capture_output=True, text=True, timeout=30, cwd=ROOT
            )
            if proc.returncode == 0 and proc.stdout.strip():
                data = json.loads(proc.stdout.strip().split("\n")[-1])
                if isinstance(data, list):
                    for item in data:
                        if action == "forecast" and item.get("forecastType"):
                            results.append({
                                "title": f"{stock_name} 业绩预告: {item['forecastType']} {item.get('profitRange', '')}",
                                "publish_time": item.get("forecastDate", end_date),
                                "sec_name": stock_name, "sec_code": stock_code,
                                "source": "baostock", "source_type": "primary",
                            })
                        elif action == "express" and item.get("expressDate"):
                            results.append({
                                "title": f"{stock_name} 业绩快报: 营收{item.get('operateIncome', '')} 净利{item.get('netProfit', '')}",
                                "publish_time": item.get("expressDate", end_date),
                                "sec_name": stock_name, "sec_code": stock_code,
                                "source": "baostock", "source_type": "primary",
                            })
        except Exception as e:
            print(f"  baostock {action} error: {e}")

    return results


def main():
    parser = argparse.ArgumentParser(description="信鸽信息采集")
    parser.add_argument("--stocks", nargs="*", default=[], help="Target stock codes")
    parser.add_argument("--date", default=None, help="Target date YYYY-MM-DD")
    parser.add_argument("--skip-filter", action="store_true")
    parser.add_argument("--output", default=None, help="Output directory")
    args = parser.parse_args()

    config = load_config()

    target_date = args.date or date.today().isoformat()
    lookback = config.get("api", {}).get("lookback_days", 7)
    start_date_dt = datetime.strptime(target_date, "%Y-%m-%d") - timedelta(days=lookback)
    start_date = start_date_dt.strftime("%Y-%m-%d")
    output_dir = args.output or config.get("output", {}).get("base_dir", "重点股票/消息面数据")

    # Holiday check
    schedule = config.get("schedule", {})
    if schedule.get("skip_holidays"):
        holidays_file = os.path.join(ROOT, schedule.get("holidays_file", ""))
        if os.path.exists(holidays_file):
            with open(holidays_file, "r", encoding="utf-8") as f:
                if target_date in f.read():
                    today_str = date.today().isoformat()
                    if target_date == today_str:
                        print(f"[pigeon] Today ({target_date}) is a holiday, skipping.")
                        return 0

    # Target stocks
    stocks = args.stocks if args.stocks else [s["code"] for s in config.get("target_stocks", [])]
    if not stocks:
        print("[pigeon] No target stocks configured.")
        return 0

    print("=" * 60)
    print(f"[pigeon] 信鸽信息采集启动")
    print(f"[pigeon] 日期: {target_date} | 回溯: {start_date} | 目标: {len(stocks)}只")
    print("=" * 60)

    all_results = {}
    total_raw = 0
    source_status = {}
    db_path = os.path.join(ROOT, output_dir, "events_db.json")

    for code in stocks:
        stock_info = next((s for s in config.get("target_stocks", []) if s.get("code") == code), None)
        if not stock_info:
            print(f"[pigeon] {code}: not in target_stocks config, skipping")
            continue
        name = stock_info.get("name", code)

        print(f"\n--- [{code} {name}] ---")
        raw_messages = []

        # Step 1: baostock forecast/express
        print("[Step 1] baostock[14] forecast/express...")
        try:
            baostock_results = fetch_baostock_forecast(code, name, start_date, target_date)
            if baostock_results:
                raw_messages.extend(baostock_results)
                print(f"  forecast: {len(baostock_results)} items")
            else:
                print("  forecast: 0 items")
        except Exception as e:
            print(f"  baostock failed: {e}")
            source_status["baostock"] = "failed"

        # Step 2: cninfo announcements
        print("[Step 2] cninfo[16] announcements...")
        try:
            cninfo_results = fetch_announcements(code, name, start_date, target_date)
            if cninfo_results:
                raw_messages.extend(cninfo_results)
                print(f"  cninfo: {len(cninfo_results)} items")
                source_status["cninfo"] = "ok"
            else:
                print("  cninfo: 0 items or failed")
                source_status["cninfo"] = "empty"
                # Step 4: backup
                print("[Step 4] china-stock-mcp[17] backup...")
                mcp_results = fetch_announcements_backup(code, name)
                if mcp_results:
                    raw_messages.extend(mcp_results)
                    print(f"  mcp: {len(mcp_results)} items")
                    source_status["mcp"] = "ok"
                else:
                    print("  mcp: no data (cache only)")
                    source_status["mcp"] = "empty"
        except Exception as e:
            print(f"  cninfo failed: {e}")
            source_status["cninfo"] = "failed"

        total_raw += len(raw_messages)
        print(f"  >> raw total: {len(raw_messages)} messages")

        # Five-layer filter
        if args.skip_filter:
            print("[filter] SKIPPED [SkipFilter mode]")
            all_results[code] = {
                "events": raw_messages,
                "stats": {"L1_in": len(raw_messages), "L1_out": len(raw_messages),
                          "L2_in": 0, "L2_out": 0, "L3_in": 0, "L3_out": 0,
                          "L4_in": 0, "L4_out": len(raw_messages)},
            }
        elif not raw_messages:
            print(f"[filter] {code}: 0 messages, skipping filter")
            all_results[code] = {
                "events": [],
                "stats": {"L1_in": 0, "L1_out": 0, "L2_in": 0, "L2_out": 0,
                          "L3_in": 0, "L3_out": 0, "L4_in": 0, "L4_out": 0},
            }
        else:
            existing = get_existing_events(code, db_path)
            all_results[code] = pigeon_filter(raw_messages, code, name, existing)

    # Summary
    print(f"\n{'=' * 60}")
    print("[pigeon] 采集完成 — 汇总统计")
    print("=" * 60)

    total_filtered = 0
    for code in stocks:
        result = all_results.get(code, {})
        if result and result.get("stats"):
            s = result["stats"]
            total_filtered += s.get("L4_out", 0)
            print(f"  {code}: {s['L1_in']} raw -> {s['L4_out']} filtered")

    # Write output
    print(f"\n[pigeon] Writing output...")
    out_result = export_events(all_results, {}, output_dir, db_path)
    update_cache(out_result, os.path.join(output_dir, "cache"))

    print(f"\n{'=' * 60}")
    print(f"[pigeon] 完成: {total_raw} raw -> {total_filtered}入库")
    print(f"[pigeon] 输出: {out_result['date_file']}")
    print(f"[pigeon] 数据库: {out_result['db_file']}")
    print("=" * 60)

    # Exit code
    if source_status.get("cninfo") == "failed" and source_status.get("mcp") == "empty":
        return 2
    elif total_filtered > 0:
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
