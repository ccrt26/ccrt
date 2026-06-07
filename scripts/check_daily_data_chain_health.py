#!/usr/bin/env python3
"""check_daily_data_chain_health.py — 每日数据链健康检查（只读）

检查 data_full / data_scored / data_final 可解析，且每只目标股票
在 kline_cache / fund_flow_cache / daily_basic / moneyflow 中有当日期数据。

Usage:
    python3 scripts/check_daily_data_chain_health.py --date YYYYMMDD
Exit: 0 = PASS, 2 = BLOCK

Code level: L0
"""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "代码文件" / "数据"

# 可选股票来源
PIGEON_CONFIG = ROOT / "代码文件" / "信鸽信息采集" / "pigeon_config.json"


def check_json(path, label=""):
    """标准 json.load 检查（utf-8-sig）；返回 (ok, err_msg)"""
    if not os.path.exists(path):
        return False, f"{label} 文件不存在: {path}"
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            json.load(f)
        return True, ""
    except (json.JSONDecodeError, ValueError) as e:
        return False, f"{label} 非法 JSON: {e}"


def get_date_str(row, *fields):
    """从行记录中依次尝试指定字段，返回标准化的 8 位日期串。"""
    for field in fields:
        val = row.get(field)
        if val:
            s = str(val).replace("-", "").replace(" ", "").replace("/", "")
            if len(s) >= 8 and s[:8].isdigit():
                return s[:8]
    return ""


def main():
    parser = argparse.ArgumentParser(description="数据链健康检查")
    parser.add_argument("--date", required=True, help="目标日期 YYYYMMDD")
    args = parser.parse_args()
    date_raw = args.date

    failures = []
    # ── 检查1：三个核心 JSON（utf-8-sig）──
    for name in ("data_full.json", "data_scored.json", "data_final.json"):
        path = os.path.join(DATA_DIR, name)
        ok, err = check_json(path, name)
        if not ok:
            failures.append(err)

    # ── 检查2：读取 target_stocks ──
    target_stocks = []
    if os.path.exists(PIGEON_CONFIG):
        try:
            with open(PIGEON_CONFIG, "r", encoding="utf-8-sig") as f:
                cfg = json.load(f)
            target_stocks = cfg.get("target_stocks", [])
        except (json.JSONDecodeError, ValueError):
            failures.append("pigeon_config.json 非法 JSON")

    # 从每只 dict 中提取 code（只取字符串 code）
    target_codes = []
    for s in target_stocks:
        code = str(s.get("code") or s.get("Code") or "")
        if code.strip():
            target_codes.append(code.strip())

    if not target_codes:
        failures.append("target_stocks 为空（无法检查缓存存在性）")

    # ── 检查3：每只 target_stock 的缓存文件 ──
    missing_kline = []
    missing_fundflow = []
    missing_daily_basic = []
    missing_moneyflow = []

    for code in target_codes:
        # kline_cache: 识别 date / day / trade_date
        kline_path = DATA_DIR / "kline_cache" / f"{code}.json"
        if os.path.exists(kline_path):
            try:
                with open(kline_path, "r", encoding="utf-8-sig") as f:
                    kd = json.load(f)
                days = kd if isinstance(kd, list) else kd.get("data", kd.get("klines", []))
                days = days if isinstance(days, list) else [days]
                has_date = any(
                    get_date_str(d, "date", "day", "trade_date") == date_raw
                    for d in days
                )
                if not has_date:
                    missing_kline.append(code)
            except Exception:
                failures.append(f"kline_cache/{code}.json 读取失败")
        else:
            missing_kline.append(code)

        # fund_flow_cache: 识别 date / trade_date
        ff_path = DATA_DIR / "fund_flow_cache" / f"{code}.json"
        if os.path.exists(ff_path):
            try:
                with open(ff_path, "r", encoding="utf-8-sig") as f:
                    fd = json.load(f)
                items = fd if isinstance(fd, list) else fd.get("data", fd.get("fund_flows", []))
                items = items if isinstance(items, list) else [items]
                has_date = any(
                    get_date_str(d, "date", "trade_date") == date_raw
                    for d in items
                )
                if not has_date:
                    missing_fundflow.append(code)
            except Exception:
                failures.append(f"fund_flow_cache/{code}.json 读取失败")
        else:
            missing_fundflow.append(code)

        # daily_basic: 识别 trade_date / date
        db_path = DATA_DIR / "tushare" / "daily_basic" / f"{code}.json"
        if os.path.exists(db_path):
            try:
                with open(db_path, "r", encoding="utf-8-sig") as f:
                    bd = json.load(f)
                items = bd if isinstance(bd, list) else bd.get("data", bd.get("items", []))
                items = items if isinstance(items, list) else [items]
                has_date = any(
                    get_date_str(d, "trade_date", "date") == date_raw
                    for d in items
                )
                if not has_date:
                    missing_daily_basic.append(code)
            except Exception:
                failures.append(f"tushare/daily_basic/{code}.json 读取失败")
        else:
            missing_daily_basic.append(code)

        # moneyflow: 识别 trade_date / date
        mf_path = DATA_DIR / "tushare" / "moneyflow" / f"{code}.json"
        if os.path.exists(mf_path):
            try:
                with open(mf_path, "r", encoding="utf-8-sig") as f:
                    md = json.load(f)
                items = md if isinstance(md, list) else md.get("data", md.get("items", []))
                items = items if isinstance(items, list) else [items]
                has_date = any(
                    get_date_str(d, "trade_date", "date") == date_raw
                    for d in items
                )
                if not has_date:
                    missing_moneyflow.append(code)
            except Exception:
                failures.append(f"tushare/moneyflow/{code}.json 读取失败")
        else:
            missing_moneyflow.append(code)

    # ── 输出（简洁，只列 code）──
    has_block = bool(failures) or bool(missing_kline) or bool(missing_fundflow) \
        or bool(missing_daily_basic) or bool(missing_moneyflow)

    if failures:
        for f in failures:
            print(f"BLOCK: {f}")

    if missing_kline:
        print(f"BLOCK: kline_cache missing: {','.join(missing_kline)}")

    if missing_fundflow:
        print(f"BLOCK: fund_flow_cache missing: {','.join(missing_fundflow)}")

    if missing_daily_basic:
        print(f"BLOCK: tushare/daily_basic missing: {','.join(missing_daily_basic)}")

    if missing_moneyflow:
        print(f"BLOCK: tushare/moneyflow missing: {','.join(missing_moneyflow)}")

    if not has_block:
        print(f"PASS: 数据链健康 {date_raw} target={len(target_codes)}")
        sys.exit(0)
    else:
        sys.exit(2)


if __name__ == "__main__":
    main()
