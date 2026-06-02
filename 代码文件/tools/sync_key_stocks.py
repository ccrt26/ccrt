#!/usr/bin/env python3
"""sync_key_stocks.py — 从 pigeon_config.json 同步 key_stocks.json

单一权威源: pigeon_config.json (target_stocks)
派生文件: key_stocks.json (纯名单, 机器可读, 不可人工编辑)

用法: python3 sync_key_stocks.py [--check]
  --check  仅检查一致性，不写入 (exit 0=一致, 1=不一致)
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
PIGEON_CONFIG = ROOT / "代码文件" / "信鸽信息采集" / "pigeon_config.json"
KEY_STOCKS = ROOT / "代码文件" / "数据" / "key_stocks.json"

BOARD_MAP = {
    "sh": {"60": "main", "68": "main"},
    "sz": {"00": "main", "30": "chiNext", "00": "main"},
}


def infer_board(market, code):
    """Infer board from market and code prefix."""
    if market == "sh":
        return "main"
    if market == "sz":
        if code.startswith("30"):
            return "chiNext"
        return "main"
    return "main"


def load_pigeon_stocks():
    with open(PIGEON_CONFIG, "r", encoding="utf-8") as f:
        data = json.load(f)
    stocks = data.get("target_stocks", data)
    result = {}
    for s in stocks:
        result[s["code"]] = {
            "code": s["code"],
            "name": s["name"],
            "market": s.get("market", ""),
            "board": infer_board(s.get("market", ""), s["code"]),
        }
    return result


def load_key_stocks():
    if not KEY_STOCKS.exists():
        return {}
    with open(KEY_STOCKS, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {s["code"]: s for s in data.get("stocks", [])}


def check_consistency():
    """Returns (is_consistent, pigeon_codes, key_codes)."""
    pigeon = set(load_pigeon_stocks().keys())
    key = set(load_key_stocks().keys()) if KEY_STOCKS.exists() else set()
    return pigeon == key, pigeon, key


def sync():
    """Generate key_stocks.json from pigeon_config.json."""
    stocks = load_pigeon_stocks()
    stock_list = sorted(stocks.values(), key=lambda s: s["code"])
    output = {
        "version": "1.0",
        "last_updated": "",
        "description": "重点股票核心观察池——由 sync_key_stocks.py 从 pigeon_config.json 自动生成，请勿手动编辑",
        "stocks": stock_list,
    }
    os.makedirs(KEY_STOCKS.parent, exist_ok=True)
    with open(KEY_STOCKS, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    return len(stock_list)


if __name__ == "__main__":
    if "--check" in sys.argv:
        ok, pigeon, key = check_consistency()
        if ok:
            print(f"PASS: pigeon_config({len(pigeon)}只) == key_stocks({len(key)}只)")
            sys.exit(0)
        else:
            only_pigeon = pigeon - key
            only_key = key - pigeon
            if only_pigeon:
                print(f"FAIL: key_stocks 缺少: {only_pigeon}")
            if only_key:
                print(f"FAIL: key_stocks 多余: {only_key}")
            print("请运行: python3 代码文件/tools/sync_key_stocks.py")
            sys.exit(1)
    else:
        n = sync()
        print(f"key_stocks.json 已同步: {n}只 (来源: pigeon_config.json)")
