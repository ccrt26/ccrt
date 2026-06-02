#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
铁律量化 · Tushare Pro 数据桥接脚本
=====================================
通过 Tushare Pro SDK 获取A股数据，作为新数据源[tushare]。
第一梯队：hk_hold(北向)/pledge(质押)/share_float(解禁)/holder_number(股东人数)
第二梯队(预留)：daily/kline/financial/moneyflow/margin
输出 JSON 到 stdout (UTF-8)，供 PowerShell 端 ConvertFrom-Json 消费。

调用方式：
    python stock_data_fetcher_tushare.py <action> [--code CODE] [--start DATE] [--end DATE]

支持的操作：
    hk_hold          -- 沪深股通持股明细 (第一梯队)
    pledge           -- 股权质押明细 (第一梯队)
    share_float      -- 限售股解禁 (第一梯队,需3000积分)
    holder_number    -- 股东人数 (第一梯队)
    daily            -- 日线行情 (第二梯队预留)
    kline            -- 复权K线 (第二梯队预留)
    financial        -- 财务指标 (第二梯队预留)
    moneyflow        -- 个股资金流向 (第二梯队预留)
    margin           -- 融资融券明细 (第二梯队预留)

数据源：[tushare] Tushare Pro — 2000积分档 (200次/分, 100,000次/天/API)
"""
import argparse
import json
import os
import sys
import time


RATE_LIMIT_SEC = 0.35
MAX_RETRIES = 2
RETRY_BACKOFF = 1.0
_last_call_time = 0.0


def rate_limit():
    global _last_call_time
    elapsed = time.time() - _last_call_time
    if elapsed < RATE_LIMIT_SEC:
        time.sleep(RATE_LIMIT_SEC - elapsed)
    _last_call_time = time.time()


def get_pro():
    token = os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        raise RuntimeError("TUSHARE_TOKEN not set in environment")
    import tushare as ts
    ts.set_token(token)
    return ts.pro_api()


def safe_json(obj):
    if hasattr(obj, "where"):
        import pandas as pd
        obj = obj.where(pd.notna(obj), None)
        text = json.dumps(obj.to_dict(orient="records"), ensure_ascii=False, default=str)
    else:
        text = json.dumps(obj, ensure_ascii=False, default=str)
    sys.stdout.buffer.write(text.encode("utf-8"))
    sys.stdout.buffer.write(b"\n")


def _to_tushare_code(code):
    """内部格式 → Tushare格式: sz000001 → 000001.SZ"""
    code = code.lower().replace(".", "")
    if code.startswith("sh"):
        return code[2:] + ".SH"
    elif code.startswith("sz"):
        return code[2:] + ".SZ"
    elif len(code) == 6:
        if code.startswith(("6", "9")):
            return code + ".SH"
        else:
            return code + ".SZ"
    return code.upper()


def _from_tushare_code(ts_code):
    """Tushare格式 → 内部格式: 000001.SZ → sz000001"""
    parts = ts_code.split(".")
    if len(parts) == 2:
        return parts[1].lower() + parts[0]
    return ts_code.lower()


def _run_with_retry(fn):
    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            rate_limit()
            return fn()
        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF * (attempt + 1))
    raise last_error


# ============================================================
# 第一梯队
# ============================================================

def do_hk_hold(code, start="", end="", exchange=""):
    """沪深股通持股明细 — pro.hk_hold()"""
    ts_code = _to_tushare_code(code)
    pro = get_pro()
    def _q():
        if exchange:
            return pro.hk_hold(trade_date=end.replace("-", "") if end else "",
                               exchange=exchange, start_date=start.replace("-", "") if start else "",
                               end_date=end.replace("-", "") if end else "")
        if ts_code.endswith(".SH"):
            ex = "SH"
        elif ts_code.endswith(".SZ"):
            ex = "SZ"
        else:
            ex = ""
        result = pro.hk_hold(ts_code=ts_code, start_date=start.replace("-", "") if start else "",
                             end_date=end.replace("-", "") if end else "")
        return result
    df = _run_with_retry(_q)
    if df is None or len(df) == 0:
        safe_json({"error": "no hk_hold data", "source": "tushare", "code": code})
        return
    safe_json(df)


def do_pledge(code, start="", end=""):
    """股权质押明细 — pro.pledge_detail()"""
    ts_code = _to_tushare_code(code)
    pro = get_pro()
    def _q():
        return pro.pledge_detail(ts_code=ts_code)
    df = _run_with_retry(_q)
    if df is None or len(df) == 0:
        safe_json({"error": "no pledge data", "source": "tushare", "code": code})
        return
    safe_json(df)


def do_share_float(code, start="", end=""):
    """限售股解禁 — pro.share_float() [需3000积分]"""
    ts_code = _to_tushare_code(code)
    pro = get_pro()
    def _q():
        return pro.share_float(ts_code=ts_code, start_date=start.replace("-", "") if start else "",
                               end_date=end.replace("-", "") if end else "")
    df = _run_with_retry(_q)
    if df is None or len(df) == 0:
        safe_json({"error": "no share_float data", "source": "tushare", "code": code,
                   "note": "requires 3000+ points"})
        return
    safe_json(df)


def do_holder_number(code, start="", end=""):
    """股东人数 — pro.stk_holdernumber()"""
    ts_code = _to_tushare_code(code)
    pro = get_pro()
    def _q():
        return pro.stk_holdernumber(ts_code=ts_code, start_date=start.replace("-", "") if start else "",
                                    end_date=end.replace("-", "") if end else "")
    df = _run_with_retry(_q)
    if df is None or len(df) == 0:
        safe_json({"error": "no holder_number data", "source": "tushare", "code": code})
        return
    safe_json(df)


# ============================================================
# 第二梯队（预留）
# ============================================================

def do_daily(code, start="", end=""):
    """日线行情 — pro.daily()"""
    ts_code = _to_tushare_code(code)
    pro = get_pro()
    def _q():
        return pro.daily(ts_code=ts_code, start_date=start.replace("-", "") if start else "",
                         end_date=end.replace("-", "") if end else "")
    df = _run_with_retry(_q)
    if df is None or len(df) == 0:
        safe_json({"error": "no daily data", "source": "tushare", "code": code})
        return
    safe_json(df)


def do_kline(code, start="", end="", freq="D", adj="qfq"):
    """复权K线 — pro.pro_bar() 或 ts.pro_bar()"""
    ts_code = _to_tushare_code(code)
    import tushare as ts
    pro = get_pro()
    def _q():
        return ts.pro_bar(ts_code=ts_code, start_date=start.replace("-", "") if start else "",
                          end_date=end.replace("-", "") if end else "", freq=freq, adj=adj)
    df = _run_with_retry(_q)
    if df is None or len(df) == 0:
        safe_json({"error": "no kline data", "source": "tushare", "code": code})
        return
    safe_json(df)


def do_financial(code, start="", end=""):
    """财务指标 — pro.fina_indicator()"""
    ts_code = _to_tushare_code(code)
    pro = get_pro()
    def _q():
        return pro.fina_indicator(ts_code=ts_code, start_date=start.replace("-", "") if start else "",
                                  end_date=end.replace("-", "") if end else "")
    df = _run_with_retry(_q)
    if df is None or len(df) == 0:
        safe_json({"error": "no financial data", "source": "tushare", "code": code})
        return
    safe_json(df)


def do_moneyflow(code, start="", end=""):
    """个股资金流向 — pro.moneyflow()"""
    ts_code = _to_tushare_code(code)
    pro = get_pro()
    def _q():
        return pro.moneyflow(ts_code=ts_code, start_date=start.replace("-", "") if start else "",
                             end_date=end.replace("-", "") if end else "")
    df = _run_with_retry(_q)
    if df is None or len(df) == 0:
        safe_json({"error": "no moneyflow data", "source": "tushare", "code": code})
        return
    safe_json(df)


def do_margin(code, start="", end=""):
    """融资融券明细 — pro.margin_detail()"""
    ts_code = _to_tushare_code(code)
    pro = get_pro()
    def _q():
        return pro.margin_detail(ts_code=ts_code, start_date=start.replace("-", "") if start else "",
                                 end_date=end.replace("-", "") if end else "")
    df = _run_with_retry(_q)
    if df is None or len(df) == 0:
        safe_json({"error": "no margin data", "source": "tushare", "code": code})
        return
    safe_json(df)


def do_pledge_stat(code, start="", end=""):
    """股权质押统计 — pro.pledge_stat()"""
    ts_code = _to_tushare_code(code)
    pro = get_pro()
    def _q():
        return pro.pledge_stat(ts_code=ts_code)
    df = _run_with_retry(_q)
    if df is None or len(df) == 0:
        safe_json({"error": "no pledge_stat data", "source": "tushare", "code": code})
        return
    safe_json(df)


def do_top_list(code, start="", end=""):
    """龙虎榜明细 — pro.top_list() [需trade_date,非ts_code]"""
    pro = get_pro()
    trade_date = end.replace("-", "") if end else (start.replace("-", "") if start else "")
    def _q():
        return pro.top_list(trade_date=trade_date)
    df = _run_with_retry(_q)
    if df is None or len(df) == 0:
        safe_json({"error": "no top_list data", "source": "tushare", "trade_date": trade_date})
        return
    if code:
        ts_code = _to_tushare_code(code)
        df = df[df["ts_code"] == ts_code]
    safe_json(df)


def do_dividend(code, start="", end=""):
    """分红送股 — pro.dividend()"""
    ts_code = _to_tushare_code(code)
    pro = get_pro()
    def _q():
        return pro.dividend(ts_code=ts_code, start_date=start.replace("-", "") if start else "",
                            end_date=end.replace("-", "") if end else "")
    df = _run_with_retry(_q)
    if df is None or len(df) == 0:
        safe_json({"error": "no dividend data", "source": "tushare", "code": code})
        return
    safe_json(df)


# ============================================================
# CLI 入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Tushare Pro 数据桥接")
    parser.add_argument("action", choices=[
        "hk_hold", "pledge", "pledge_stat", "share_float", "holder_number",
        "daily", "kline", "financial", "moneyflow", "margin", "top_list", "dividend",
    ], help="操作类型")
    parser.add_argument("--code", type=str, default="", help="股票代码 (e.g. sh600519或600519)")
    parser.add_argument("--start", type=str, default="", help="起始日期 (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default="", help="结束日期 (YYYY-MM-DD)")
    parser.add_argument("--freq", type=str, default="D", help="K线频率 (D/W/M/60/30/15/5)")
    parser.add_argument("--adj", type=str, default="qfq", help="复权方式 (qfq前/hfq后/None不)")

    args = parser.parse_args()

    try:
        import tushare as ts
    except ImportError:
        print(json.dumps({"error": "tushare not installed; pip install tushare"}))
        sys.exit(1)

    try:
        if args.action == "hk_hold":
            if not args.code:
                print(json.dumps({"error": "--code is required"})); sys.exit(1)
            do_hk_hold(code=args.code, start=args.start, end=args.end)

        elif args.action == "pledge":
            if not args.code:
                print(json.dumps({"error": "--code is required"})); sys.exit(1)
            do_pledge(code=args.code, start=args.start, end=args.end)

        elif args.action == "pledge_stat":
            if not args.code:
                print(json.dumps({"error": "--code is required"})); sys.exit(1)
            do_pledge_stat(code=args.code, start=args.start, end=args.end)

        elif args.action == "share_float":
            if not args.code:
                print(json.dumps({"error": "--code is required"})); sys.exit(1)
            do_share_float(code=args.code, start=args.start, end=args.end)

        elif args.action == "holder_number":
            if not args.code:
                print(json.dumps({"error": "--code is required"})); sys.exit(1)
            do_holder_number(code=args.code, start=args.start, end=args.end)

        elif args.action == "daily":
            if not args.code:
                print(json.dumps({"error": "--code is required"})); sys.exit(1)
            do_daily(code=args.code, start=args.start, end=args.end)

        elif args.action == "kline":
            if not args.code:
                print(json.dumps({"error": "--code is required"})); sys.exit(1)
            do_kline(code=args.code, start=args.start, end=args.end, freq=args.freq, adj=args.adj)

        elif args.action == "financial":
            if not args.code:
                print(json.dumps({"error": "--code is required"})); sys.exit(1)
            do_financial(code=args.code, start=args.start, end=args.end)

        elif args.action == "moneyflow":
            if not args.code:
                print(json.dumps({"error": "--code is required"})); sys.exit(1)
            do_moneyflow(code=args.code, start=args.start, end=args.end)

        elif args.action == "margin":
            if not args.code:
                print(json.dumps({"error": "--code is required"})); sys.exit(1)
            do_margin(code=args.code, start=args.start, end=args.end)

        elif args.action == "top_list":
            do_top_list(code=args.code, start=args.start, end=args.end)

        elif args.action == "dividend":
            if not args.code:
                print(json.dumps({"error": "--code is required"})); sys.exit(1)
            do_dividend(code=args.code, start=args.start, end=args.end)

    except Exception as e:
        print(json.dumps({"error": f"tushare bridge error: {str(e)}", "source": "tushare"}))
        sys.exit(1)


if __name__ == "__main__":
    main()
