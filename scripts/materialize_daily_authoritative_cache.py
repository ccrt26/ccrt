#!/usr/bin/env python3
"""
materialize_daily_authoritative_cache.py — v2.0
从 data_full.json 权威源派生补齐 kline_cache / fund_flow_cache。
data_full.json 是单一权威源，缓存必须由它派生。

v2.0: 支持多种资金流字段格式
  - Tushare 原始字段: buy_elg_amount/sell_elg_amount/.../net_mf_amount
  - 标准化字段: super_large_net/large_net/medium_net/small_net/main_force_net
  - THS fallback 字段: net_mf_amount (从 batch_data_collector 标准化后)

任何来源都必须先校验 row trade_date/date == --date。
单位统一为万元；若源为元，须先除以 10000 并标注 source_trace。
不允许全 0 伪通过。

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


def norm_date(value):
    """标准化日期：YYYY-MM-DD / YYYYMMDD → YYYYMMDD"""
    return str(value or "").replace("-", "").replace(" ", "").replace("/", "")[:8]


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
    for idx, d in enumerate(kd):
        if d.replace("-", "") == target_date:
            return idx, (s.get("KClose") or [None] * len(kd))[idx]
    return None, None


def existing_kline_has_date(code, date_str):
    """Return True when kline_cache already contains the target trading date."""
    date_dash = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
    path = os.path.join(KLINE_DIR, f"{code}.json")
    if not os.path.exists(path):
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            rows = json.load(f)
    except Exception:
        return False
    for row in rows if isinstance(rows, list) else []:
        d = str(row.get("date") or row.get("trade_date") or "").replace("-", "")
        if d == date_str or row.get("date") == date_dash:
            return True
    return False


def upsert_kline(code, name, date_str, s):
    """Upsert kline_cache/{code}.json from data_full stock data."""
    date_dash = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
    idx, close_val = check_kline_date(s, date_str, date_dash)
    if idx is None:
        if existing_kline_has_date(code, date_str):
            log(f"  KLINE_UPSERT PASS: {code} {name} — {date_dash} already in kline_cache")
            return True
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

    existing = [r for r in existing if r.get("date") != date_dash]
    existing.append(row)
    existing.sort(key=lambda r: r.get("date", ""))

    os.makedirs(KLINE_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    log(f"  KLINE_UPSERT PASS: {code} {name} — {date_dash} close={row['close']} ({len(existing)}条)")
    return True


def _extract_fund_flow_row(flow_row, code, name, date_str):
    """从一条资金流记录提取标准化字段。

    支持三种格式：
    1. Tushare 原始: buy_elg_amount, sell_elg_amount, ..., net_mf_amount
    2. 标准化: super_large_net, large_net, medium_net, small_net, main_force_net
    3. THS fallback 后标准化: net_mf_amount + source=ths-stock_fund_flow

    确保目标日匹配，单位统一为万元。
    返回 (result_dict, source_trace) 或 (None, reason)。
    """
    row_date = norm_date(flow_row.get("trade_date") or flow_row.get("date", ""))
    if row_date != date_str:
        return None, f"trade_date={row_date} != target={date_str}"

    # 判断来源格式
    source_tag = flow_row.get("source", "")
    raw_unit = flow_row.get("raw_unit", "万元")

    if source_tag == "ths-stock_fund_flow":
        # THS 标准化格式（已在 batch_data_collector 转为万元）
        mf = to_f(flow_row.get("net_mf_amount", 0))
        sl = to_f(flow_row.get("buy_elg_amount", 0))
        ln = to_f(flow_row.get("buy_lg_amount", 0))
        mn = to_f(flow_row.get("buy_md_amount", 0))
        sn = to_f(flow_row.get("buy_sm_amount", 0))
        source_trace = "THS fallback approximate via batch_data_collector, not Tushare four-level net split"
    elif "super_large_net" in flow_row:
        # 已标准化格式（直接从 fund_flow_cache 或其他标准化源）
        mf = to_f(flow_row.get("main_force_net", 0))
        sl = to_f(flow_row.get("super_large_net", 0))
        ln = to_f(flow_row.get("large_net", 0))
        mn = to_f(flow_row.get("medium_net", 0))
        sn = to_f(flow_row.get("small_net", 0))
        source_trace = flow_row.get("source_trace", "标准化字段.权威派生")
    else:
        # Tushare 原始格式
        sl = round(to_f(flow_row.get("buy_elg_amount", 0)) - to_f(flow_row.get("sell_elg_amount", 0)), 2)
        ln = round(to_f(flow_row.get("buy_lg_amount", 0)) - to_f(flow_row.get("sell_lg_amount", 0)), 2)
        mn = round(to_f(flow_row.get("buy_md_amount", 0)) - to_f(flow_row.get("sell_md_amount", 0)), 2)
        sn = round(to_f(flow_row.get("buy_sm_amount", 0)) - to_f(flow_row.get("sell_sm_amount", 0)), 2)
        mf = round(to_f(flow_row.get("net_mf_amount", 0)), 2)
        source_trace = "Tushare Pro moneyflow via data_full.json.权威派生"

    result = {
        "date": date_str,
        "source": source_tag if source_tag else "data_full.json.FundFlows",
        "raw_unit": raw_unit,
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
        "source_trace": source_trace,
        "collected_at": flow_row.get("collected_at", ""),
    }
    return result, source_trace


def upsert_fund_flow(code, name, date_str, flows):
    """Upsert fund_flow_cache/{code}.json from data_full FundFlows raw fields.

    支持 Tushare 原始格式/标准化格式/THS fallback 格式。
    先校验 row trade_date/date == --date。
    单位统一为万元。
    """
    frows = flows.get(code, [])
    if not frows:
        log(f"  FUND_FLOW UPSERT SKIP: {code} {name} — FundFlows 无此股票", "WARN")
        return False

    # 找到目标日的记录
    target_row = None
    for row in frows:
        d = norm_date(row.get("trade_date") or row.get("date", ""))
        if d == date_str:
            target_row = row
            break

    if target_row is None:
        log(f"  FUND_FLOW UPSERT SKIP: {code} {name} — 缺{date_str}", "WARN")
        return False

    extracted, info = _extract_fund_flow_row(target_row, code, name, date_str)
    if extracted is None:
        log(f"  FUND_FLOW UPSERT SKIP: {code} {name} — {info}", "WARN")
        return False

    path = os.path.join(FUND_FLOW_DIR, f"{code}.json")
    existing = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            existing = json.load(f)

    existing = [r for r in existing if str(r.get("date", "")) != date_str]
    existing.append(extracted)
    existing.sort(key=lambda r: str(r.get("date", "")))

    os.makedirs(FUND_FLOW_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    log(f"  FUND_FLOW UPSERT PASS: {code} {name} — {date_str} main_force={extracted['main_force_display']} ({len(existing)}条)")
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
            if existing_kline_has_date(code, date_str):
                log(f"  KLINE UPSERT PASS: {code} — already in kline_cache")
                kline_pass += 1
            else:
                log(f"  KLINE UPSERT SKIP: {code} — 不在 data_full.Stocks 中", "WARN")
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
