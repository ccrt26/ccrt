#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
铁律量化 · baostock数据桥接脚本
=================================
通过 baostock 免费库获取A股历史数据，作为数据源[14]。
覆盖：分红除权/宏观经济/业绩预告快报/K线/财务备源
输出 JSON 到 stdout (UTF-8)，供 PowerShell 端 ConvertFrom-Json 消费。

调用方式：
    python stock_data_fetcher_baostock.py <action> [--param value ...]

支持的操作：
    dividend          -- 分红除权 (Phase 1)
    adjust_factor     -- 复权因子 (Phase 1)
    macro_deposit_rate   -- 存款利率 (Phase 2)
    macro_loan_rate      -- 贷款利率 (Phase 2)
    macro_rrr            -- 准备金率 (Phase 2)
    macro_money_supply   -- 货币供应量 (Phase 2)
    forecast          -- 业绩预告 (Phase 3)
    express           -- 业绩快报 (Phase 3)
    kline             -- K线数据 (Phase 4)
    financial_profit  -- 季频盈利 (Phase 4)
    financial_growth  -- 季频成长 (Phase 4)
    financial_balance -- 季频偿债 (Phase 4)
    financial_cashflow-- 季频现金流 (Phase 4)
    financial_dupont  -- 杜邦分析 (Phase 4)
    stock_basic       -- 股票基本信息
    trade_dates       -- 交易日历

数据源：[14] baostock (baostock.com) — 免费、无需注册
"""
import argparse
import json
import os
import sys
import time
import pandas as pd


# ============================================================
# 会话管理 (30min超时 + 最多1次重试)
# ============================================================
MAX_RETRIES = 1
RATE_LIMIT_SEC = 0.5
_last_call_time = 0.0


def rate_limit():
    """强制调用间隔 >= 0.5s"""
    global _last_call_time
    elapsed = time.time() - _last_call_time
    if elapsed < RATE_LIMIT_SEC:
        time.sleep(RATE_LIMIT_SEC - elapsed)
    _last_call_time = time.time()


def bs_login():
    """登录 baostock（抑制库自身的 stdout 输出），返回 bs 模块"""
    import baostock as bs
    rate_limit()
    with open(os.devnull, 'w') as devnull:
        old_stdout = sys.stdout
        sys.stdout = devnull
        try:
            lg = bs.login()
        finally:
            sys.stdout = old_stdout
    if lg.error_code != '0':
        raise ConnectionError(f"baostock login failed: {lg.error_msg}")
    return bs


def bs_logout(bs):
    """登出 baostock（抑制库自身的 stdout 输出）"""
    with open(os.devnull, 'w') as devnull:
        old_stdout = sys.stdout
        sys.stdout = devnull
        try:
            bs.logout()
        finally:
            sys.stdout = old_stdout


def safe_json(obj):
    """将 DataFrame/list/dict 转为 JSON，处理 NaN/NaT，强制 UTF-8"""
    if isinstance(obj, pd.DataFrame):
        obj = obj.where(pd.notna(obj), None)
        text = json.dumps(obj.to_dict(orient="records"), ensure_ascii=False, default=str)
    elif isinstance(obj, pd.Series):
        obj = obj.where(pd.notna(obj), None)
        text = json.dumps(obj.to_list(), ensure_ascii=False, default=str)
    else:
        text = json.dumps(obj, ensure_ascii=False, default=str)
    sys.stdout.buffer.write(text.encode("utf-8"))
    sys.stdout.buffer.write(b"\n")


def run_with_retry(fn, *args, **kwargs):
    """执行 baostock 查询，会话超时自动重连（最多1次）"""
    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        bs = None
        try:
            bs = bs_login()
            result = fn(bs, *args, **kwargs)
            bs_logout(bs)
            return result
        except Exception as e:
            last_error = e
            try:
                if bs is not None:
                    bs_logout(bs)
            except Exception:
                pass
            if attempt < MAX_RETRIES:
                time.sleep(1.0)
    raise last_error


def get_data(rs):
    """安全地从 baostock ResultSet 提取 DataFrame"""
    if rs is None:
        return None
    if rs.error_code != '0':
        raise RuntimeError(f"baostock query error: {rs.error_msg} (code={rs.error_code})")
    data = []
    while rs.next():
        data.append(rs.get_row_data())
    if not data:
        return None
    return pd.DataFrame(data, columns=rs.fields)


# ============================================================
# Phase 1: 分红除权 + 复权因子
# ============================================================

def do_dividend(code, start="2010-01-01", end="2030-12-31"):
    """分红除权数据 — query_dividend_data() 覆盖1990年至今"""
    def _query(bs):
        rs = bs.query_dividend_data(code=code, year=None, yearType="report")
        if rs is None or rs.error_code != '0':
            rs = bs.query_dividend_data(code=code, year=None, yearType="operate")
        df = get_data(rs)
        if df is not None and len(df) > 0:
            if start:
                df = df[df.iloc[:, 0].astype(str) >= start]
            if end:
                df = df[df.iloc[:, 0].astype(str) <= end]
        return df
    result = run_with_retry(_query)
    if result is None or len(result) == 0:
        safe_json({"error": "no dividend data", "source": "baostock[14]", "code": code})
        return
    safe_json(result)


def do_adjust_factor(code, start="2010-01-01", end="2030-12-31"):
    """复权因子查询 — query_adjust_factor()"""
    def _query(bs):
        rs = bs.query_adjust_factor(code=code, start_date=start, end_date=end)
        return get_data(rs)
    result = run_with_retry(_query)
    if result is None or len(result) == 0:
        safe_json({"error": "no adjust_factor data", "source": "baostock[14]", "code": code})
        return
    safe_json(result)


# ============================================================
# Phase 2: 宏观经济 (5接口)
# ============================================================

def do_macro_deposit_rate(start="1990-01-01", end="2030-12-31"):
    """存款利率 — query_deposit_rate_data() 覆盖1990年至今（无参数，返回全量后过滤）"""
    def _query(bs):
        rs = bs.query_deposit_rate_data()
        df = get_data(rs)
        if df is not None and len(df) > 0 and len(df.columns) > 0:
            date_col = df.columns[0]
            filtered = df[(df[date_col].astype(str) >= start) & (df[date_col].astype(str) <= end)]
            if len(filtered) == 0:
                # 存款利率2015年后未调整，返回最近3条
                return df.tail(3)
            return filtered
        return df
    result = run_with_retry(_query)
    if result is None or len(result) == 0:
        safe_json({"error": "no deposit_rate data in range", "source": "baostock[14]"})
        return
    safe_json(result)


def do_macro_loan_rate(start="1990-01-01", end="2030-12-31"):
    """贷款利率 — query_loan_rate_data() 覆盖1990年至今（无参数，返回全量后过滤）"""
    def _query(bs):
        rs = bs.query_loan_rate_data()
        df = get_data(rs)
        if df is not None and len(df) > 0 and len(df.columns) > 0:
            date_col = df.columns[0]
            filtered = df[(df[date_col].astype(str) >= start) & (df[date_col].astype(str) <= end)]
            return filtered if len(filtered) > 0 else df.tail(3)
        return df
    result = run_with_retry(_query)
    if result is None or len(result) == 0:
        safe_json({"error": "no loan_rate data", "source": "baostock[14]"})
        return
    safe_json(result)


def do_macro_rrr(start="1999-01-01", end="2030-12-31"):
    """准备金率 — query_required_reserve_ratio_data() 覆盖1999年至今（无参数，返回全量后过滤）"""
    def _query(bs):
        rs = bs.query_required_reserve_ratio_data()
        df = get_data(rs)
        if df is not None and len(df) > 0 and len(df.columns) > 0:
            date_col = df.columns[0]
            filtered = df[(df[date_col].astype(str) >= start) & (df[date_col].astype(str) <= end)]
            return filtered if len(filtered) > 0 else df.tail(3)
        return df
    result = run_with_retry(_query)
    if result is None or len(result) == 0:
        safe_json({"error": "no rrr data", "source": "baostock[14]"})
        return
    safe_json(result)


def do_macro_money_supply(freq="month", start="2010-01-01", end="2030-12-31"):
    """货币供应量 — 月度/年度（无参数，返回全量后过滤）"""
    def _query(bs):
        if freq == "year":
            rs = bs.query_money_supply_data_year()
        else:
            rs = bs.query_money_supply_data_month()
        df = get_data(rs)
        if df is not None and len(df) > 0 and len(df.columns) > 0:
            date_col = df.columns[0]
            df = df[(df[date_col].astype(str) >= start) & (df[date_col].astype(str) <= end)]
        return df
    result = run_with_retry(_query)
    if result is None or len(result) == 0:
        safe_json({"error": f"no money_supply ({freq}) data", "source": "baostock[14]"})
        return
    safe_json(result)


# ============================================================
# Phase 3: 业绩预告 + 业绩快报
# ============================================================

def do_forecast(code, year=2026, quarter=2):
    """业绩预告 — query_forcast_report() 覆盖2003年至今"""
    def _query(bs):
        rs = bs.query_forecast_report(code=code, year=year, quarter=quarter)
        return get_data(rs)
    result = run_with_retry(_query)
    if result is None or len(result) == 0:
        safe_json({"error": f"no forecast data for {code} {year}Q{quarter}", "source": "baostock[14]"})
        return
    safe_json(result)


def do_express(code, year=2026, quarter=1):
    """业绩快报 — query_performance_express_report() 覆盖2006年至今"""
    def _query(bs):
        rs = bs.query_performance_express_report(code=code, year=year, quarter=quarter)
        return get_data(rs)
    result = run_with_retry(_query)
    if result is None or len(result) == 0:
        safe_json({"error": f"no express report for {code} {year}Q{quarter}", "source": "baostock[14]"})
        return
    safe_json(result)


# ============================================================
# Phase 4: K线 + 财务备源增强
# ============================================================

def do_kline(code, freq="d", start="2020-01-01", end="2030-12-31", adjust="2"):
    """
    K线数据 — query_history_k_data_plus()
    freq: d(日)/w(周)/m(月)/5/15/30/60(分钟)
    adjust: 1(前复权)/2(后复权)/3(不复权)
    返回字段: date,code,open,high,low,close,preclose,volume,amount,
              adjustflag,turn,tradestatus,pctChg,peTTM,pbMRQ,psTTM,pcfNcfTTM,isST
    """
    fields = "date,code,open,high,low,close,preclose,volume,amount,adjustflag,turn,tradestatus,pctChg,peTTM,pbMRQ,psTTM,pcfNcfTTM,isST"

    def _query(bs):
        rs = bs.query_history_k_data_plus(
            code=code, fields=fields,
            start_date=start, end_date=end,
            frequency=freq, adjustflag=adjust
        )
        return get_data(rs)
    result = run_with_retry(_query)
    if result is None or len(result) == 0:
        safe_json({"error": f"no kline data for {code}", "source": "baostock[14]", "code": code})
        return
    safe_json(result)


def do_financial_profit(code, year=2025, quarter=4):
    """季频盈利能力 — query_profit_data() 含ROE/净利率/毛利率/EPS等"""
    def _query(bs):
        rs = bs.query_profit_data(code=code, year=year, quarter=quarter)
        return get_data(rs)
    result = run_with_retry(_query)
    if result is None or len(result) == 0:
        safe_json({"error": f"no profit data for {code} {year}Q{quarter}", "source": "baostock[14]"})
        return
    safe_json(result)


def do_financial_growth(code, year=2025, quarter=4):
    """季频成长能力 — query_growth_data() 营收/利润同比增长率"""
    def _query(bs):
        rs = bs.query_growth_data(code=code, year=year, quarter=quarter)
        return get_data(rs)
    result = run_with_retry(_query)
    if result is None or len(result) == 0:
        safe_json({"error": f"no growth data for {code} {year}Q{quarter}", "source": "baostock[14]"})
        return
    safe_json(result)


def do_financial_balance(code, year=2025, quarter=4):
    """季频偿债能力 — query_balance_data() 流动比率/速动比率"""
    def _query(bs):
        rs = bs.query_balance_data(code=code, year=year, quarter=quarter)
        return get_data(rs)
    result = run_with_retry(_query)
    if result is None or len(result) == 0:
        safe_json({"error": f"no balance data for {code} {year}Q{quarter}", "source": "baostock[14]"})
        return
    safe_json(result)


def do_financial_cashflow(code, year=2025, quarter=4):
    """季频现金流量 — query_cash_flow_data()"""
    def _query(bs):
        rs = bs.query_cash_flow_data(code=code, year=year, quarter=quarter)
        return get_data(rs)
    result = run_with_retry(_query)
    if result is None or len(result) == 0:
        safe_json({"error": f"no cashflow data for {code} {year}Q{quarter}", "source": "baostock[14]"})
        return
    safe_json(result)


def do_financial_dupont(code, year=2025, quarter=4):
    """季频杜邦分析 — query_dupont_data() ROE三因子拆解"""
    def _query(bs):
        rs = bs.query_dupont_data(code=code, year=year, quarter=quarter)
        return get_data(rs)
    result = run_with_retry(_query)
    if result is None or len(result) == 0:
        safe_json({"error": f"no dupont data for {code} {year}Q{quarter}", "source": "baostock[14]"})
        return
    safe_json(result)


# ============================================================
# 辅助: 股票基本信息 + 交易日历
# ============================================================

def do_stock_basic(code):
    """股票基本信息 — query_stock_basic()"""
    def _query(bs):
        rs = bs.query_stock_basic(code=code)
        return get_data(rs)
    result = run_with_retry(_query)
    if result is None or len(result) == 0:
        safe_json({"error": f"no stock_basic data for {code}", "source": "baostock[14]"})
        return
    safe_json(result)


def do_trade_dates(start="2026-01-01", end="2026-12-31"):
    """交易日历 — query_trade_dates()"""
    def _query(bs):
        rs = bs.query_trade_dates(start_date=start, end_date=end)
        return get_data(rs)
    result = run_with_retry(_query)
    if result is None or len(result) == 0:
        safe_json({"error": "no trade_dates data", "source": "baostock[14]"})
        return
    safe_json(result)


# ============================================================
# 主入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="baostock数据桥接 [14]")
    parser.add_argument("action", choices=[
        "dividend", "adjust_factor",
        "macro_deposit_rate", "macro_loan_rate", "macro_rrr",
        "macro_money_supply",
        "forecast", "express",
        "kline",
        "financial_profit", "financial_growth", "financial_balance",
        "financial_cashflow", "financial_dupont",
        "stock_basic", "trade_dates",
    ], help="操作类型")
    parser.add_argument("--code", type=str, default="", help="股票代码 (e.g. sh.600519)")
    parser.add_argument("--start", type=str, default="", help="起始日期 (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default="", help="结束日期 (YYYY-MM-DD)")
    parser.add_argument("--freq", type=str, default="d", help="K线频率 (d/w/m/5/15/30/60)")
    parser.add_argument("--adjust", type=str, default="2", help="复权方式 (1前/2后/3不)")
    parser.add_argument("--year", type=int, default=2026, help="财年")
    parser.add_argument("--quarter", type=int, default=1, help="财报季度(1-4)")

    args = parser.parse_args()

    try:
        import baostock as bs
    except ImportError:
        print(json.dumps({"error": "baostock not installed; pip install baostock"}))
        sys.exit(1)

    # --- 日期默认值 ---
    start = args.start if args.start else "2010-01-01"
    end = args.end if args.end else "2030-12-31"

    try:
        if args.action == "dividend":
            if not args.code:
                print(json.dumps({"error": "--code is required"})); sys.exit(1)
            do_dividend(code=args.code, start=start, end=end)

        elif args.action == "adjust_factor":
            if not args.code:
                print(json.dumps({"error": "--code is required"})); sys.exit(1)
            do_adjust_factor(code=args.code, start=start, end=end)

        elif args.action == "macro_deposit_rate":
            do_macro_deposit_rate(start=start, end=end)

        elif args.action == "macro_loan_rate":
            do_macro_loan_rate(start=start, end=end)

        elif args.action == "macro_rrr":
            do_macro_rrr(start=start, end=end)

        elif args.action == "macro_money_supply":
            do_macro_money_supply(freq=args.freq if args.freq in ("month","year") else "month",
                                  start=start, end=end)

        elif args.action == "forecast":
            if not args.code:
                print(json.dumps({"error": "--code is required"})); sys.exit(1)
            do_forecast(code=args.code, year=args.year, quarter=args.quarter)

        elif args.action == "express":
            if not args.code:
                print(json.dumps({"error": "--code is required"})); sys.exit(1)
            do_express(code=args.code, year=args.year, quarter=args.quarter)

        elif args.action == "kline":
            if not args.code:
                print(json.dumps({"error": "--code is required"})); sys.exit(1)
            do_kline(code=args.code, freq=args.freq, start=start, end=end, adjust=args.adjust)

        elif args.action == "financial_profit":
            if not args.code:
                print(json.dumps({"error": "--code is required"})); sys.exit(1)
            do_financial_profit(code=args.code, year=args.year, quarter=args.quarter)

        elif args.action == "financial_growth":
            if not args.code:
                print(json.dumps({"error": "--code is required"})); sys.exit(1)
            do_financial_growth(code=args.code, year=args.year, quarter=args.quarter)

        elif args.action == "financial_balance":
            if not args.code:
                print(json.dumps({"error": "--code is required"})); sys.exit(1)
            do_financial_balance(code=args.code, year=args.year, quarter=args.quarter)

        elif args.action == "financial_cashflow":
            if not args.code:
                print(json.dumps({"error": "--code is required"})); sys.exit(1)
            do_financial_cashflow(code=args.code, year=args.year, quarter=args.quarter)

        elif args.action == "financial_dupont":
            if not args.code:
                print(json.dumps({"error": "--code is required"})); sys.exit(1)
            do_financial_dupont(code=args.code, year=args.year, quarter=args.quarter)

        elif args.action == "stock_basic":
            if not args.code:
                print(json.dumps({"error": "--code is required"})); sys.exit(1)
            do_stock_basic(code=args.code)

        elif args.action == "trade_dates":
            do_trade_dates(start=start, end=end)

    except Exception as e:
        print(json.dumps({"error": f"baostock bridge error: {str(e)}", "source": "baostock[14]"}))
        sys.exit(1)


if __name__ == "__main__":
    main()
