#!/usr/bin/env python3
"""批量数据采集 — 行情/K线/资金流/财务/板块

Replaces batch_data_collector.ps1. macOS compatible.
Input: dynamic_pool.json → Output: data_full.json (engine-compatible format)
Code level: L1
v2.0: 数据本地优先 — CachedDataSource集成, Tushare本地→PS缓存→管线快照→API→过期兜底
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))
from config_loader import detect_root
from cached_data_source import CachedDataSource

ROOT = detect_root()
DATA_DIR = os.path.join(ROOT, "代码文件", "数据")
SCRIPTS_DIR = os.path.join(ROOT, "代码文件", "每日荐股", "scripts")

# 全局缓存实例
_cache = CachedDataSource()


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def collect_quotes(codes):
    """批量行情 — 腾讯API [1]"""
    print(f"\n[1/5] 批量行情 — {len(codes)} stocks...")
    market_codes = ["sh" + c if c.startswith(("6", "9")) else "sz" + c for c in codes]
    result = {}
    for i in range(0, len(market_codes), 50):
        batch = market_codes[i:i + 50]
        url = "http://qt.gtimg.cn/q=" + ",".join(batch)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                text = resp.read().decode("gbk", errors="replace")
            for line in text.strip().split("\n"):
                if "=" not in line:
                    continue
                line = line.replace("var hq_str_", "")
                parts = line.split('="')
                if len(parts) < 2:
                    continue
                key = parts[0]
                vals = parts[1].strip('";').split("~")
                code = key[4:]  # v_sh600114 → 600114
                if len(vals) >= 35:
                    # 腾讯时间戳: vals[30] = "20260529161408" → trade_date + trade_time
                    ts = vals[30] if len(vals) > 30 and vals[30].isdigit() and len(vals[30]) == 14 else ""
                    quote_time = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]} {ts[8:10]}:{ts[10:12]}:{ts[12:14]}" if ts else ""
                    result[code] = {
                        "Price": float(vals[3]) if vals[3] else 0,
                        "PrevClose": float(vals[4]) if vals[4] else 0,
                        "Open": float(vals[5]) if vals[5] else 0,
                        "Volume": int(vals[6]) if vals[6] else 0,
                        "ChangePct": float(vals[32]) if vals[32] else 0,
                        "TurnoverRate": float(vals[38]) if len(vals) > 38 and vals[38] else 0,
                        "Amplitude": float(vals[43]) if len(vals) > 43 and vals[43] else 0,
                        "PE": float(vals[39]) if len(vals) > 39 and vals[39] else 0,
                        "MktCap": float(vals[45]) if len(vals) > 45 and vals[45] else 0,
                        "High": float(vals[33]) if vals[33] else 0,
                        "Low": float(vals[34]) if vals[34] else 0,
                        "QuoteTime": quote_time,
                    }
        except Exception as e:
            print(f"  Tencent API error: {e}")
        if i + 50 < len(market_codes):
            time.sleep(0.3)
    print(f"  成功: {len(result)}/{len(codes)}")
    return result


def collect_klines(codes, count=60):
    """K线数据 — Tushare本地优先 → 新浪API[2]降级"""
    print(f"\n[2/5] K线数据({count}日) — {len(codes)} stocks...")
    result = {}
    api_codes = []
    for code in codes:
        cached = _cache.get_kline(code, days=count)
        if cached["data"] and cached["freshness"] == "fresh":
            result[code] = cached["data"]
        else:
            api_codes.append(code)
    print(f"  Tushare本地命中: {len(result)}/{len(codes)}")
    if not api_codes:
        return result
    print(f"  需API获取: {len(api_codes)} stocks...")
    for code in api_codes:
        prefix = "sh" if code.startswith(("6", "9")) else "sz"
        url = (f"https://quotes.sina.cn/cn/api/jsonp_v2.php/"
               f"data/CN_MarketDataService.getKLineData?"
               f"symbol={prefix}{code}&scale=240&ma=no&datalen={count}")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                text = resp.read().decode("utf-8", errors="replace")
            match = re.search(r"\((\[.*\])\)", text, re.DOTALL)
            if match:
                data = json.loads(match.group(1))
                result[code] = [{
                    "day": d["day"], "open": float(d["open"]),
                    "high": float(d["high"]), "low": float(d["low"]),
                    "close": float(d["close"]), "volume": int(d["volume"])
                } for d in data]
        except Exception as e:
            print(f"  {code}: Sina kline failed ({e})")
        time.sleep(0.3)
    print(f"  成功: {len(result)}/{len(codes)}")
    return result


def collect_financials(codes):
    """财务数据 — Tushare本地优先 → THS降级"""
    print(f"\n[3/5] 财务数据 — {len(codes)} stocks...")
    result = {}
    api_codes = []
    for code in codes:
        cached = _cache.get_financial(code)
        if cached["data"] and cached["freshness"] == "fresh":
            result[code] = cached["data"]
        else:
            api_codes.append(code)
    print(f"  Tushare本地命中: {len(result)}/{len(codes)}")
    if not api_codes:
        return result
    print(f"  需API获取: {len(api_codes)} stocks...")
    ths_script = os.path.join(SCRIPTS_DIR, "stock_data_fetcher_ths.py")
    if not os.path.exists(ths_script):
        print("  THS fetcher not found, skipping remaining financials")
        return result
    for code in api_codes:
        try:
            import subprocess
            proc = subprocess.run(
                [sys.executable, ths_script, "financial", "--code", code, "--quarters", "4"],
                capture_output=True, text=True, timeout=30
            )
            if proc.returncode == 0 and proc.stdout.strip():
                result[code] = json.loads(proc.stdout.strip().split("\n")[-1])
        except Exception:
            pass
        time.sleep(0.35)
    print(f"  成功: {len(result)}/{len(codes)}")
    return result


def collect_fund_flows(codes):
    """资金流向 — Tushare本地优先 → THS降级"""
    print(f"\n[4/6] 资金流向 — {len(codes)} stocks...")
    result = {}
    api_codes = []
    for code in codes:
        cached = _cache.get_moneyflow(code)
        if cached["data"] and cached["freshness"] == "fresh":
            result[code] = cached["data"]
        else:
            api_codes.append(code)
    print(f"  Tushare本地命中: {len(result)}/{len(codes)}")
    if not api_codes:
        return result
    print(f"  需API获取: {len(api_codes)} stocks...")
    ths_script = os.path.join(SCRIPTS_DIR, "stock_data_fetcher_ths.py")
    if not os.path.exists(ths_script):
        print("  THS fetcher not found, skipping remaining fund flows")
        return result
    for code in api_codes:
        try:
            import subprocess
            proc = subprocess.run(
                [sys.executable, ths_script, "stock_fund_flow", "--code", code],
                capture_output=True, text=True, timeout=30
            )
            if proc.returncode == 0 and proc.stdout.strip():
                result[code] = json.loads(proc.stdout.strip().split("\n")[-1])
        except Exception:
            pass
        time.sleep(0.35)
    print(f"  成功: {len(result)}/{len(codes)}")
    return result


def collect_margins(codes):
    """融资融券 — Tushare本地优先"""
    print(f"\n[5/6] 融资融券 — {len(codes)} stocks...")
    result = {}
    for code in codes:
        cached = _cache.get_margin(code)
        if cached["data"] and cached["freshness"] == "fresh":
            result[code] = cached["data"]
    print(f"  Tushare本地命中: {len(result)}/{len(codes)}")
    if len(result) < len(codes):
        print(f"  缺失: {len(codes) - len(result)} stocks (无本地缓存)")
    return result


def collect_sectors():
    """板块数据 — 尝试THS, 失败静默"""
    print("\n[6/6] 板块数据...")
    result = {}
    ths_script = os.path.join(SCRIPTS_DIR, "stock_data_fetcher_ths.py")
    if not os.path.exists(ths_script):
        print("  THS fetcher not found, skipping sectors")
        return result
    try:
        import subprocess
        for action in ["sector_ranking", "sector_fund_flow"]:
            proc = subprocess.run(
                [sys.executable, ths_script, action, "--top", "30"],
                capture_output=True, text=True, timeout=30
            )
            if proc.returncode == 0 and proc.stdout.strip():
                result[action] = json.loads(proc.stdout.strip().split("\n")[-1])
    except Exception as e:
        print(f"  Sector collection failed: {e}")
    print(f"  板块数据: {'OK' if result else 'FAILED (non-blocking)'}")
    return result


def main():
    parser = argparse.ArgumentParser(description="Batch data collector")
    parser.add_argument("--pool", default="", help="Dynamic pool JSON path")
    parser.add_argument("--output", default="", help="Output data_full.json path")
    parser.add_argument("--skip-kline", action="store_true")
    parser.add_argument("--date", default="", help="Target date: YYYYMMDD or YYYY-MM-DD (falls back to env DAILY_TARGET_DATE, then K-line detection)")
    args = parser.parse_args()

    # Resolve --date: CLI arg > env DAILY_TARGET_DATE > empty (K-line detection later)
    date_arg = args.date or os.environ.get("DAILY_TARGET_DATE", "")
    date_compact = ""
    date_source = "kline_detection"  # tracks which source was effectively used
    if date_arg:
        date_compact = date_arg.replace("-", "")
        if len(date_compact) == 8 and date_compact.isdigit():
            if args.date:
                date_source = "cli_arg"
            else:
                date_source = "env_DAILY_TARGET_DATE"
        else:
            if args.date:
                print(f"ERROR: --date={args.date} is not valid YYYYMMDD or YYYY-MM-DD format")
                sys.exit(1)
            print(f"WARNING: DAILY_TARGET_DATE={date_arg} not YYYYMMDD/YYYY-MM-DD, ignoring")
            date_compact = ""
            # date_source stays "kline_detection" — invalid env was ignored

    pool_file = args.pool or os.path.join(DATA_DIR, "dynamic_pool.json")
    output_file = args.output or os.path.join(DATA_DIR, "data_full.json")

    if not os.path.exists(pool_file):
        print(f"ERROR: Dynamic pool file not found: {pool_file}")
        sys.exit(1)

    pool = load_json(pool_file)
    pool_stocks = pool.get("Stocks", pool.get("stocks", []))
    if not pool_stocks:
        print("ERROR: Dynamic pool is empty")
        sys.exit(1)

    codes = [s.get("Code", s.get("code", "")) for s in pool_stocks]
    print(f"Dynamic pool: {len(codes)} stocks, starting data collection")

    start_time = time.time()

    # Core data (always collected)
    quotes = collect_quotes(codes)
    klines = {} if args.skip_kline else collect_klines(codes)

    # Optional data (non-blocking)
    financials = collect_financials(codes)
    fund_flows = collect_fund_flows(codes)
    margins = collect_margins(codes)
    sectors = collect_sectors()

    # Assemble engine-compatible format: {"Stocks": [...]}
    engine_stocks = []
    for s in pool_stocks:
        code = s.get("Code", s.get("code", ""))
        entry = {
            "Code": code,
            "Name": s.get("Name", s.get("name", "")),
            "Industry": s.get("Industry", s.get("industry", "")),
        }
        # Merge quote data directly
        if code in quotes:
            entry.update(quotes[code])
        # Merge K-line as KClose/KOpen/KHigh/KLow/KVolume + KDate arrays
        if code in klines:
            kl = klines[code]
            entry["KDate"] = [d.get("day", d.get("trade_date", "")) for d in kl]
            entry["KClose"] = [d["close"] for d in kl]
            entry["KOpen"] = [d["open"] for d in kl]
            entry["KHigh"] = [d["high"] for d in kl]
            entry["KLow"] = [d["low"] for d in kl]
            entry["KVolume"] = [d["volume"] for d in kl]
        engine_stocks.append(entry)

    # 从K线数据推导 trade_date（取最后一根K线的日期）；
    # 当显式 --date 提供时优先使用，K线推导作为 fallback
    trade_date = ""
    if date_compact:
        trade_date = f"{date_compact[:4]}-{date_compact[4:6]}-{date_compact[6:8]}"
    for s in engine_stocks:
        kdate = s.get("KDate", [])
        if kdate and kdate[-1]:
            k_trade_date = kdate[-1].replace("-", "") if "-" in str(kdate[-1]) else str(kdate[-1])
            if len(k_trade_date) == 8:
                trade_date = trade_date or f"{k_trade_date[:4]}-{k_trade_date[4:6]}-{k_trade_date[6:8]}"
            break

    output = {
        "Stocks": engine_stocks,
        "_Meta": {
            "collect_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "collection_completed_at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
            "trade_date": trade_date,
            "target_date": f"{date_compact[:4]}-{date_compact[4:6]}-{date_compact[6:8]}" if date_compact else "",
            "data_date": f"{date_compact[:4]}-{date_compact[4:6]}-{date_compact[6:8]}" if date_compact else trade_date,
            "stock_count": len(codes),
            "date_source": date_source,
            "quotes_source": "tencent[1]" if args.skip_kline else "tushare-local+tencent[1]",
            "kline_source": "tushare-local+sina[2]",
            "financial_source": "tushare-local+ths",
            "fundflow_source": "tushare-local+ths",
            "cache_stats": _cache.stats,
            "collector": "batch_data_collector.py",
            "categories_collected": ["quotes", "kline", "financials", "fundflow", "margins", "sectors"],
            "runtime_platform": "macOS" if sys.platform == "darwin" else sys.platform,
        },
        "Financials": financials,
        "FundFlows": fund_flows,
        "Margins": margins,
        "Sectors": sectors,
    }

    save_json(output_file, output)
    elapsed = time.time() - start_time
    print(f"\nData collection complete: {output_file} ({elapsed:.1f}s)")
    print(f"  Stocks: {len(engine_stocks)}, with quotes: {sum(1 for s in engine_stocks if s.get('Price'))}, with K-line: {sum(1 for s in engine_stocks if s.get('KClose'))}")


if __name__ == "__main__":
    main()
