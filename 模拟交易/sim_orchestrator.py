#!/usr/bin/env python3
"""sim_orchestrator.py — 模拟交易统一调度器 v1.1

Replaces sim_orchestrator.ps1.
Unified orchestrator for Key Stock + Daily Pick sim trading tracks.
Merges positions, snapshots, and performance views.
Code level: L1
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = str(SCRIPT_DIR.parent)


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Sim Trading Unified Orchestrator")
    parser.add_argument("--date", default=datetime.now().strftime("%Y%m%d"), help="Trading date (yyyyMMdd)")
    parser.add_argument("--root-dir", default=ROOT, help="Project root directory")
    parser.add_argument("--dry-run", action="store_true", help="Dry run mode")
    parser.add_argument("--force", action="store_true", help="Bypass time checks")
    args = parser.parse_args()

    date_str = args.date
    root_dir = args.root_dir
    sim_dir = os.path.join(root_dir, "模拟交易")
    canon_base = os.path.join(root_dir, "历史数据")
    log_dir = os.path.join(sim_dir, "日志")

    if not args.dry_run:
        os.makedirs(log_dir, exist_ok=True)

    log_lines = []

    def log(msg, level="INFO"):
        line = f"[ORCH][{level}] {msg}"
        log_lines.append(line)
        print(line)

    log(f"===== 模拟交易统一调度器 v1.1 | Date {date_str} =====")

    # ── Step 1: Check Yaozi instructions ────────────────
    instruction_file = os.path.join(sim_dir, "交易决策", f"交易指令_{date_str}.json")
    has_instructions = os.path.exists(instruction_file)
    if has_instructions:
        log(f"腰子指令已就绪: {instruction_file}")
    else:
        log("无腰子指令，使用纯自动模式")

    total_capital = 1000000
    key_stock_ratio = 0.60
    daily_rec_ratio = 0.40
    log(f"统一资金池: {total_capital} (Key Stock: {key_stock_ratio} | Daily Rec: {daily_rec_ratio})")

    # ── Step 2: Run Key Stock track ─────────────────────
    log("")
    log("=== 赛道1: 重点股票 ===")
    key_stock_engine = os.path.join(sim_dir, "交易引擎", "sim_trading.py")
    key_stock_args = [sys.executable, key_stock_engine, "--date", date_str, "--root-dir", root_dir]
    if args.force:
        key_stock_args.append("--force")
    if args.dry_run:
        key_stock_args.append("--dry-run")
    if has_instructions:
        key_stock_args.extend(["--instruction-file", instruction_file])

    try:
        result = subprocess.run(key_stock_args, capture_output=False, cwd=root_dir)
        if result.returncode != 0:
            log(f"重点股票引擎退出码: {result.returncode}", "ERROR")
        else:
            log("重点股票引擎完成")
    except Exception as e:
        log(f"重点股票引擎异常: {e}", "ERROR")

    # ── Step 3: Run Daily Pick track ────────────────────
    log("")
    log("=== 赛道2: 每日荐股 ===")
    daily_engine = os.path.join(sim_dir, "每日荐股赛道", "交易引擎", "sim_trading_daily.py")
    if os.path.exists(daily_engine):
        daily_args = [sys.executable, daily_engine, "--date", date_str, "--root-dir", root_dir]
        if args.force:
            daily_args.append("--force")
        if args.dry_run:
            daily_args.append("--dry-run")
        if has_instructions:
            daily_args.extend(["--instruction-file", instruction_file])

        try:
            result = subprocess.run(daily_args, capture_output=False, cwd=root_dir)
            if result.returncode != 0:
                log(f"每日荐股引擎退出码: {result.returncode}", "ERROR")
            else:
                log("每日荐股引擎完成")
        except Exception as e:
            log(f"每日荐股引擎异常: {e}", "ERROR")
    else:
        log("每日荐股交易引擎脚本不存在，跳过", "WARN")

    # ── Step 4: Merge positions ─────────────────────────
    log("")
    log("=== 合并持仓视图 ===")
    key_positions_file = os.path.join(canon_base, "00_核心交易", "positions.json")
    daily_positions_file = os.path.join(sim_dir, "每日荐股赛道", "持仓记录", "positions_daily.json")

    merged_cash = 0
    merged_value = 0
    merged_stock_value = 0
    all_positions = []

    # Key stock positions
    if os.path.exists(key_positions_file):
        try:
            key_pos = load_json(key_positions_file)
            merged_cash += key_pos.get("Cash", 0)
            merged_value += key_pos.get("TotalValue", 0)
            for code, p in key_pos.get("Positions", {}).items():
                if p.get("Shares", 0) > 0:
                    merged_stock_value += p.get("CurrentPrice", 0) * p.get("Shares", 0)
                    all_positions.append({
                        "Code": code, "Name": p.get("Name", ""),
                        "Shares": p.get("Shares", 0), "AvgCost": p.get("AvgCost", 0),
                        "CurrentPrice": p.get("CurrentPrice", 0),
                        "UnrealizedPnL": p.get("UnrealizedPnL", 0),
                        "UnrealizedPnLPct": p.get("UnrealizedPnLPct", 0),
                        "Track": "重点股票", "EntryScore": p.get("EntryScore"),
                    })
        except Exception as e:
            log(f"重点股票持仓读取失败: {e}", "WARN")

    # Daily pick positions
    if os.path.exists(daily_positions_file):
        try:
            daily_pos = load_json(daily_positions_file)
            merged_cash += daily_pos.get("Cash", 0)
            merged_value += daily_pos.get("TotalValue", 0)
            for code, p in daily_pos.get("Positions", {}).items():
                if p.get("Shares", 0) > 0:
                    merged_stock_value += p.get("CurrentPrice", 0) * p.get("Shares", 0)
                    all_positions.append({
                        "Code": code, "Name": p.get("Name", ""),
                        "Shares": p.get("Shares", 0), "AvgCost": p.get("AvgCost", 0),
                        "CurrentPrice": p.get("CurrentPrice", 0),
                        "UnrealizedPnL": p.get("UnrealizedPnL", 0),
                        "UnrealizedPnLPct": p.get("UnrealizedPnLPct", 0),
                        "Track": "每日荐股", "EntryScore": p.get("EntryScore"),
                    })
        except Exception as e:
            log(f"每日荐股持仓读取失败: {e}", "WARN")

    # ── Step 5: Output merged snapshot ──────────────────
    all_positions.sort(key=lambda p: -(p.get("UnrealizedPnLPct", 0) or 0))
    merged_snapshot = {
        "Date": date_str,
        "GeneratedAt": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "TotalValue": round(merged_value, 2),
        "Cash": round(merged_cash, 2),
        "StockValue": round(merged_stock_value, 2),
        "PositionCount": len(all_positions),
        "Tracks": {
            "KeyStock": sum(1 for p in all_positions if p["Track"] == "重点股票"),
            "DailyRec": sum(1 for p in all_positions if p["Track"] == "每日荐股"),
        },
        "Positions": all_positions,
    }

    merged_snapshot_file = os.path.join(canon_base, "01_交易快照", f"unified_snapshot_{date_str}.json")
    if not args.dry_run:
        save_json(merged_snapshot_file, merged_snapshot)
        log(f"合并快照已写入: {merged_snapshot_file}")

    # ── Step 6: Console summary ─────────────────────────
    log("")
    log(f"===== 统一调度器 日报 {date_str} =====")
    log(f"合并净值: {merged_value:,.2f}")
    log(f"现金: {merged_cash:,.2f} | 持仓市值: {merged_stock_value:,.2f}")
    key_count = sum(1 for p in all_positions if p["Track"] == "重点股票")
    daily_count = sum(1 for p in all_positions if p["Track"] == "每日荐股")
    log(f"持仓数: {len(all_positions)} 只 (重点: {key_count} | 荐股: {daily_count})")
    if merged_value > 0:
        log(f"仓位: {merged_stock_value / merged_value * 100:.1f}%")

    if all_positions:
        log("")
        for p in all_positions:
            sign = "+" if (p.get("UnrealizedPnLPct", 0) or 0) >= 0 else ""
            track_tag = "[K]" if p["Track"] == "重点股票" else "[D]"
            log(f"  {track_tag} {p['Name']} {p['Shares']}股 成本{p['AvgCost']} 现价{p['CurrentPrice']} 浮动{sign}{p.get('UnrealizedPnLPct', 0)}%")

    log("===== END =====")

    if not args.dry_run:
        log_content = "\n".join(log_lines)
        log_path = os.path.join(log_dir, f"orchestrator_{date_str}.log")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(log_content)
        log("[DONE]")


if __name__ == "__main__":
    main()
