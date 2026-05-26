#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
铁律量化 · StockTV API桥接脚本 [B4]
=====================================
作为东方财富[9]资金流向的第四备源。
一套接口覆盖A股/港股/美股多市场。

调用方式：
    python stock_data_fetcher_stocktv.py fund_flow --code 000001 --days 5

API密钥：从环境变量 STOCKTV_APIKEY 读取
"""

import argparse
import json
import os
import sys


def safe_output(obj):
    """JSON输出到stdout (UTF-8)"""
    text = json.dumps(obj, ensure_ascii=False, default=str)
    sys.stdout.buffer.write(text.encode("utf-8"))
    sys.stdout.buffer.write(b"\n")


def get_apikey():
    """从环境变量读取API密钥"""
    key = os.environ.get("STOCKTV_APIKEY", "")
    if not key:
        print(json.dumps({"error": "STOCKTV_APIKEY 环境变量未设置"}), file=sys.stderr)
        sys.exit(1)
    return key


def do_fund_flow(code, days=5):
    """
    个股资金流向日K线 — StockTV API

    目标输出字段：
        Date, MainNetInflow, SuperLargeIn, LargeIn, SmallIn
    """
    apikey = get_apikey()

    try:
        import requests
    except ImportError:
        print(json.dumps({"error": "requests not installed"}), file=sys.stderr)
        sys.exit(1)

    # StockTV API - 个股资金流向
    # A股代码格式: 纯数字，不区分市场后缀
    url = "https://api.stocktv.com/v1/cn/stock/fund_flow"

    params = {
        "apikey": apikey,
        "symbol": code,
        "limit": days,
    }

    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()

        if not data or data.get("status") != "ok":
            safe_output([{"error": str(data.get("message", "api error"))}])
            return

        rows = data.get("data") or data.get("result") or []
        if isinstance(rows, dict):
            rows = [rows]
        if not isinstance(rows, list):
            safe_output([])
            return

        result = []
        for row in rows[-days:]:
            result.append({
                "Date": str(row.get("date") or row.get("trade_date") or ""),
                "MainNetInflow": float(row.get("main_net_inflow") or row.get("net_flow") or 0),
                "SuperLargeIn": float(row.get("super_large_in") or row.get("huge_net") or 0),
                "LargeIn": float(row.get("large_in") or row.get("big_net") or 0),
                "SmallIn": float(row.get("small_in") or row.get("retail_net") or 0),
            })

        safe_output(result)

    except requests.RequestException as e:
        safe_output([{"error": f"request failed: {str(e)}"}])
    except (ValueError, TypeError, KeyError) as e:
        safe_output([{"error": f"parse failed: {str(e)}"}])


def main():
    parser = argparse.ArgumentParser(description="StockTV桥接")
    parser.add_argument("action", choices=["fund_flow"])
    parser.add_argument("--code", type=str, required=True, help="股票代码")
    parser.add_argument("--days", type=int, default=5, help="返回天数")
    args = parser.parse_args()

    if args.action == "fund_flow":
        do_fund_flow(args.code, args.days)


if __name__ == "__main__":
    main()
