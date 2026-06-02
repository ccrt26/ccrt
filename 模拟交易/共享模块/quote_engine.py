#!/usr/bin/env python3
"""quote_engine.py — 行情获取共享模块 (1+2 architecture)

Replaces quote_engine.ps1.
Tier 1: 腾讯行情[1] → Tier 2: 新浪行情[1B] → Tier 3: 缓存[C]
Shared by both sim trading tracks.
Code level: L1
"""
import json
import os
import re
import urllib.request


def fetch_tencent_quotes(codes):
    """Tier 1: 腾讯行情API [1]. Returns dict {code: {Price, Name, ...}}."""
    qt_codes = ",".join(codes)
    url = f"https://qt.gtimg.cn/q={qt_codes}"
    result = {}
    try:
        req = urllib.request.Request(url)
        raw = urllib.request.urlopen(req, timeout=10).read()
        text = raw.decode("gbk", errors="replace")
        for segment in text.split(";"):
            m = re.search(r'"(.*)"', segment)
            if not m:
                continue
            parts = m.group(1).split("~")
            if len(parts) < 45:
                continue
            code = parts[2]
            try:
                result[code] = {
                    "OpenPrice": float(parts[5]) if parts[5] else 0,
                    "Price": float(parts[3]) if parts[3] else 0,
                    "ChangePct": float(parts[32]) if parts[32] else 999,
                    "High": float(parts[33]) if parts[33] else 0,
                    "Low": float(parts[34]) if parts[34] else 0,
                    "PrevClose": float(parts[4]) if parts[4] else 0,
                    "TurnoverRate": float(parts[38]) if parts[38] else 0,
                    "Name": parts[1],
                    "DataSource": "[1]",
                }
            except (ValueError, IndexError):
                pass
    except Exception as e:
        print(f"  WARNING: 腾讯行情[1]异常: {e}")
    return result


def fetch_sina_quotes(codes):
    """Tier 2: 新浪行情API [1B]. Returns dict {code: {Price, Name, ...}}."""
    qt_codes = ",".join(codes)
    url = f"https://hq.sinajs.cn/list={qt_codes}"
    result = {}
    try:
        req = urllib.request.Request(url, headers={"Referer": "https://finance.sina.com.cn"})
        raw = urllib.request.urlopen(req, timeout=10).read()
        text = raw.decode("gbk", errors="replace")
        for segment in text.split(";"):
            segment = segment.strip()
            if not segment:
                continue
            m = re.search(r'var hq_str_(\w+)="(.*)"', segment)
            if not m:
                continue
            full_code = m.group(1)
            parts = m.group(2).split(",")
            if len(parts) < 32:
                continue
            code = re.sub(r'^(sh|sz|bj)', '', full_code)
            try:
                open_p = float(parts[1]) if parts[1] else 0
                now_p = float(parts[3]) if parts[3] else 0
                prev_close = float(parts[2]) if parts[2] else 0
                chg_p = round((now_p / prev_close - 1) * 100, 2) if prev_close > 0 else 999
                result[code] = {
                    "OpenPrice": open_p,
                    "Price": now_p,
                    "ChangePct": chg_p,
                    "High": 0,
                    "Low": 0,
                    "PrevClose": prev_close,
                    "TurnoverRate": 0,
                    "Name": parts[0],
                    "DataSource": "[1B]",
                }
            except (ValueError, IndexError):
                pass
    except Exception as e:
        print(f"  WARNING: 新浪行情[1B]异常: {e}")
    return result


def load_cache_quotes(codes, stock_map, cache_file):
    """Tier 3: 缓存兜底[C]."""
    result = {}
    if not cache_file or not os.path.exists(cache_file):
        return result
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            cache = json.load(f)
        for code in stock_map:
            if code in cache and cache[code].get("Price", 0) > 0:
                p = cache[code]["Price"]
                result[code] = {
                    "OpenPrice": p,
                    "Price": p,
                    "ChangePct": 0,
                    "High": p,
                    "Low": p,
                    "TurnoverRate": 0,
                    "Name": stock_map[code]["Name"],
                    "DataSource": "[C]",
                    "PrevClose": p,
                }
    except Exception as e:
        print(f"  WARNING: 缓存[C]读取失败: {e}")
    return result


def get_quote_map(stock_list, cache_file="", sim_dir=""):
    """Fetch quotes for a list of stocks with 1+2 fallback.

    Args:
        stock_list: list of dicts with Code, Market keys
        cache_file: path to quotes cache JSON
        sim_dir: sim trading directory

    Returns:
        dict with Quotes (dict) and Source (str)
    """
    qt_codes = [f"{s['Market']}{s['Code']}" for s in stock_list]
    stock_map = {s["Code"]: s for s in stock_list}

    result = fetch_tencent_quotes(qt_codes)
    source = "腾讯行情[1]" if result else ""

    if not result:
        print("  腾讯行情[1]不可用，尝试新浪行情[1B]...")
        result = fetch_sina_quotes(qt_codes)
        source = "新浪行情[1B]" if result else ""

    if not result:
        print("  行情API均不可用，尝试缓存[C]...")
        result = load_cache_quotes(qt_codes, stock_map, cache_file)
        source = "缓存[C]" if result else ""

    if source:
        print(f"  [行情] 数据来源: {source} ({len(result)}只)")
    else:
        print("  [行情] 所有行情源均无数据")

    return {"Quotes": result, "Source": source}


def get_benchmark_value(code="sh000300"):
    """Fetch benchmark (HS300) quote."""
    try:
        req = urllib.request.Request(f"https://qt.gtimg.cn/q={code}")
        raw = urllib.request.urlopen(req, timeout=10).read()
        text = raw.decode("gbk", errors="replace")
        m = re.search(r'"(.*)"', text)
        if not m:
            return None
        parts = m.group(1).split("~")
        if len(parts) < 6:
            return None
        price = float(parts[3])
        prev_close = float(parts[4])
        chg_pct = round((price / prev_close - 1) * 100, 2) if prev_close > 0 else 0
        turnover = float(parts[37]) if len(parts) > 37 and parts[37] else 0
        return {
            "Price": price,
            "Open": float(parts[5]) if parts[5] else 0,
            "ChangePct": chg_pct,
            "Turnover": turnover,
        }
    except Exception:
        return None


def get_quote_map_with_retry(stock_list, cache_file="", sim_dir="", deadline_str="09:45"):
    """Fetch quotes with backoff retry until deadline. v1.7

    Retry strategy:
      attempt 1: 腾讯[1] → attempt 2: 新浪[1B]
      → wait 15s → attempt 3: 腾讯[1] → attempt 4: 新浪[1B]
      → wait 30s → attempt 5+: alternate every 60s
      → hit deadline → load_cache[C] fallback

    Args:
        stock_list: list of dicts with Code, Market keys
        cache_file: path to quotes cache JSON
        sim_dir: sim trading directory
        deadline_str: deadline time string (HH:MM), default "09:45"

    Returns:
        dict with Quotes (dict) and Source (str)
    """
    from datetime import datetime as _dt

    deadline = _dt.strptime(_dt.now().strftime("%Y%m%d") + deadline_str, "%Y%m%d%H:%M")
    now = _dt.now()
    if now > deadline:
        deadline = _dt(now.year, now.month, now.day, 23, 59)  # past deadline today, set to EOD

    retry_count = 0
    delays = [0, 0, 15, 30]  # delay before attempts 0,1,2,3 (seconds)
    # attempts 0,1: immediate; 2: 15s; 3: 30s; 4+: 60s

    while True:
        delay = delays[retry_count] if retry_count < len(delays) else 60
        if delay > 0:
            remaining = (deadline - _dt.now()).total_seconds()
            if remaining <= 0:
                break
            actual_wait = min(delay, max(remaining - 1, 1))
            import time as _time
            _time.sleep(actual_wait)

        now = _dt.now()
        if now > deadline:
            break

        # alternate between tencent and sina
        if retry_count % 2 == 0:
            print(f"  [重试-{retry_count}] 尝试腾讯行情[1]...")
            result = fetch_tencent_quotes(
                [f"{s['Market']}{s['Code']}" for s in stock_list])
            if result:
                suffix = f"-retry{retry_count}" if retry_count > 0 else ""
                return {"Quotes": result, "Source": f"腾讯行情[1]{suffix}"}
        else:
            print(f"  [重试-{retry_count}] 尝试新浪行情[1B]...")
            result = fetch_sina_quotes(
                [f"{s['Market']}{s['Code']}" for s in stock_list])
            if result:
                return {"Quotes": result, "Source": f"新浪行情[1B]-retry{retry_count}"}

        retry_count += 1

    # All retries exhausted or deadline reached → cache fallback
    print("  [行情] 重试耗尽/超deadline，降级至缓存[C]...")
    stock_map = {s["Code"]: s for s in stock_list}
    result = load_cache_quotes(
        [f"{s['Market']}{s['Code']}" for s in stock_list], stock_map, cache_file)
    return {"Quotes": result, "Source": "缓存[C]"} if result else {"Quotes": {}, "Source": ""}


def save_quote_cache(quotes, cache_file):
    """Save quotes to cache file."""
    if not cache_file:
        return
    cache_obj = {}
    for code, q in quotes.items():
        cache_obj[code] = {"Price": q.get("Price", 0), "Name": q.get("Name", "")}
    os.makedirs(os.path.dirname(cache_file) if os.path.dirname(cache_file) else ".", exist_ok=True)
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(cache_obj, f, ensure_ascii=False, indent=2)
