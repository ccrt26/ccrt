#!/usr/bin/env python3
"""
materialize_daily_authoritative_cache.py — v1.0
从 data_full.json 派生补齐 kline_cache / fund_flow_cache（L1 当日权威组成之一）。
data_full.json + kline_cache + fund_flow_cache 共同组成 L1 当日权威。
data_full.json 是 L1 当日权威组成之一，不是单一权威源。详情见 D04_权威源决策表。

用法:
  python3 scripts/materialize_daily_authoritative_cache.py --date 20260604

约定:
  kline_cache 字段: date, open, high, low, close, volume
  fund_flow_cache 字段: date, source, raw_unit, display_unit,
    super_large_net, large_net, medium_net, small_net, main_force_net,
    super_large_display, large_display, medium_display, small_display, main_force_display

退出码:
  0 = PASS
  2 = BLOCK
"""
import argparse, json, os, sys
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent)
DATA_FULL = os.path.join(ROOT, "代码文件", "数据", "data_full.json")
KLINE_DIR = os.path.join(ROOT, "代码文件", "数据", "kline_cache")
FUND_FLOW_DIR = os.path.join(ROOT, "代码文件", "数据", "fund_flow_cache")
PIGEON_CFG = os.path.join(ROOT, "代码文件", "信鸽信息采集", "pigeon_config.json")


def log(msg, level="INFO"):
    print(f"[{level}] {msg}")


def to_f(v):
    """Safely convert to float."""
    return round(float(v or 0), 2)


def disp(v):
    """Format float to display string like +123万 or -123万."""
    return f"{v:+.0f}万"


def load_pool():
    """Read dynamic stock pool from pigeon_config.json."""
    if not os.path.exists(PIGEON_CFG):
        return []
    try:
        with open(PIGEON_CFG, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return [(str(s.get("code", "")), s.get("name", "")) for s in cfg.get("target_stocks", []) if s.get("code") and s.get("name")]
    except Exception:
        return []


def get_stock_kline(dfull, code):
    """Find stock in data_full.Stocks by code. Returns dict or None."""
    for s in dfull.get("Stocks", []):
        c = str(s.get("Code") or s.get("code", ""))
        if c == code:
            return s
    return None


def check_kline_date(s, target_date, date_dash):
    """Check if stock has target date in KDate. Returns (index, close) or (None,None)."""
    kd = s.get("KDate") or []
    if date_dash in kd:
        idx = kd.index(date_dash)
        return idx, (s.get("KClose") or [None] * len(kd))[idx]
    # Also try compact YYYYMMDD format
    for idx, d in enumerate(kd):
        if d.replace("-", "") == target_date:
            return idx, (s.get("KClose") or [None] * len(kd))[idx]
    return None, None


def upsert_kline(code, name, date_str, s):
    """Upsert kline_cache/{code}.json from data_full stock data."""
    date_dash = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
    idx, close_val = check_kline_date(s, date_str, date_dash)
    if idx is None:
        log(f"  KLINE_UPSERT SKIP: {code} {name} — 缺{date_dash}", "WARN")
        return False

    row = {
        "date": date_dash,
        "open": to_f((s.get("KOpen") or [None] * len(s.get("KDate", [])))[idx]),
        "high": to_f((s.get("KHigh") or [None] * len(s.get("KDate", [])))[idx]),
        "low": to_f((s.get("KLow") or [None] * len(s.get("KDate", [])))[idx]),
        "close": to_f((s.get("KClose") or [None] * len(s.get("KDate", [])))[idx]),
        "volume": int((s.get("KVolume") or [None] * len(s.get("KDate", [])))[idx] or 0),
    }

    path = os.path.join(KLINE_DIR, f"{code}.json")
    existing = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            existing = json.load(f)

    # Remove any existing entry for the same date
    existing = [r for r in existing if r.get("date") != date_dash]
    existing.append(row)
    # Keep sorted by date
    existing.sort(key=lambda r: r.get("date", ""))

    os.makedirs(KLINE_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    log(f"  KLINE_UPSERT PASS: {code} {name} — {date_dash} close={row['close']} ({len(existing)}条)")
    return True


def upsert_fund_flow(code, name, date_str, flows):
    """Upsert fund_flow_cache/{code}.json from data_full FundFlows raw fields."""
    frows = flows.get(code, [])
    if not frows:
        log(f"  FUND_FLOW_UPSERT SKIP: {code} {name} — FundFlows 无此股票", "WARN")
        return False

    target_row = None
    for row in frows:
        d = str(row.get("trade_date") or row.get("date", "")).replace("-", "")
        if d == date_str:
            target_row = row
            break

    if target_row is None:
        log(f"  FUND_FLOW_UPSERT SKIP: {code} {name} — 缺{date_str}", "WARN")
        return False

    # Map raw Tushare fields → standard 5-field format
    sl = round(to_f(target_row.get("buy_elg_amount", 0)) - to_f(target_row.get("sell_elg_amount", 0)), 2)
    ln = round(to_f(target_row.get("buy_lg_amount", 0)) - to_f(target_row.get("sell_lg_amount", 0)), 2)
    mn = round(to_f(target_row.get("buy_md_amount", 0)) - to_f(target_row.get("sell_md_amount", 0)), 2)
    sn = round(to_f(target_row.get("buy_sm_amount", 0)) - to_f(target_row.get("sell_sm_amount", 0)), 2)
    mf = round(to_f(target_row.get("net_mf_amount", 0)), 2)

    result = {
        "date": date_str,
        "source": "data_full.json.FundFlows",
        "raw_unit": "万元",
        "display_unit": "万元",
        "super_large_net": sl,
        "large_net": ln,
        "medium_net": mn,
        "small_net": sn,
        "main_force_net": mf,
        "super_large_display": disp(sl),
        "large_display": disp(ln),
        "medium_display": disp(mn),
        "small_display": disp(sn),
        "main_force_display": disp(mf),
        "source_trace": "Tushare Pro moneyflow via data_full.json.权威派生",
        "collected_at": "",
    }

    path = os.path.join(FUND_FLOW_DIR, f"{code}.json")
    existing = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            existing = json.load(f)

    # Remove any existing entry for the same date
    existing = [r for r in existing if str(r.get("date", "")) != date_str]
    existing.append(result)
    existing.sort(key=lambda r: str(r.get("date", "")))

    os.makedirs(FUND_FLOW_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    log(f"  FUND_FLOW_UPSERT PASS: {code} {name} — {date_str} main_force={result['main_force_display']} ({len(existing)}条)")
    return True


def main():
    ap = argparse.ArgumentParser(description="从 data_full.json 权威源派生补齐 K线和资金流缓存")
    ap.add_argument("--date", required=True, help="交易日 YYYYMMDD")
    args = ap.parse_args()
    date_str = args.date

    if not os.path.exists(DATA_FULL):
        log(f"DATA_FULL_NOT_FOUND: {DATA_FULL}", "BLOCK")
        sys.exit(2)

    try:
        with open(DATA_FULL, "r", encoding="utf-8-sig") as f:
            dfull = json.load(f)
    except Exception as e:
        log(f"DATA_FULL_PARSE_FAIL: {e}", "BLOCK")
        sys.exit(2)

    pool = load_pool()
    if not pool:
        # Fall back to FundFlows keys
        pool = [(c, "") for c in dfull.get("FundFlows", {}).keys()]
        log(f"POOL: {len(pool)} stocks from FundFlows keys (pigeon_config unavailable)")

    flows = dfull.get("FundFlows", {})

    kline_pass = 0
    kline_fail = 0
    ff_pass = 0
    ff_fail = 0

    for code, name in pool:
        log(f"{code} {name or ''}:")
        s = get_stock_kline(dfull, code)
        if s:
            if upsert_kline(code, name or code, date_str, s):
                kline_pass += 1
            else:
                kline_fail += 1
        else:
            log(f"  KLINE_UPSERT SKIP: {code} — 不在 data_full.Stocks 中", "WARN")
            kline_fail += 1

        if upsert_fund_flow(code, name or code, date_str, flows):
            ff_pass += 1
        else:
            ff_fail += 1

    print()
    log(f"=== SUMMARY ===")
    log(f"KLINE:       {kline_pass} PASS | {kline_fail} FAIL")
    log(f"FUND_FLOW:   {ff_pass} PASS | {ff_fail} FAIL")

    if kline_fail > 0 or ff_fail > 0:
        log("部分股票缓存补齐失败，请检查上表", "BLOCK")
        sys.exit(2)
    log("ALL_CACHE_MATERIALIZED")
    sys.exit(0)


if __name__ == "__main__":
    main()
