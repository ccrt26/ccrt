#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
铁律量化 · 麦蕊智数桥接脚本 [B2]
=====================================
作为东方财富[9]资金流向的第二备源。
Python SDK完善，批量拉取稳定。

调用方式：
    python stock_data_fetcher_mairei.py fund_flow --code 000001 --days 5

API密钥：从环境变量 MAIREI_TOKEN 读取
官网：https://www.mairuiapi.com
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


def get_token():
    """从环境变量读取API Token"""
    key = os.environ.get("MAIREI_TOKEN", "")
    if not key:
        print(json.dumps({"error": "MAIREI_TOKEN 环境变量未设置"}), file=sys.stderr)
        sys.exit(1)
    return key


def do_fund_flow(code, days=5):
    """
    个股资金流向日K线 — 麦蕊智数
    官网: https://www.mairuiapi.com/shares_data

    目标输出字段：
        Date, MainNetInflow, SuperLargeIn, LargeIn, SmallIn
    """
    token = get_token()

    try:
        import requests
    except ImportError:
        print(json.dumps({"error": "requests not installed"}), file=sys.stderr)
        sys.exit(1)

    # 麦蕊智数 API - 资金流向接口
    # 参考: https://www.mairuiapi.com/shares_data
    url = "https://api.mairuiapi.com/v1/stock/fund_flow"

    params = {
        "token": token,
        "code": code,
        "days": days,
    }

    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()

        if not data or data.get("code") != 200:
            safe_output([{"error": str(data.get("msg", "api error"))}])
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
                "Date": str(row.get("trade_date") or row.get("date") or ""),
                "MainNetInflow": float(row.get("main_net_flow") or row.get("main_net_inflow") or row.get("zljlr") or 0),
                "SuperLargeIn": float(row.get("huge_order_flow") or row.get("super_large_in") or row.get("cdd") or 0),
                "LargeIn": float(row.get("big_order_flow") or row.get("large_in") or row.get("dd") or 0),
                "SmallIn": float(row.get("small_order_flow") or row.get("small_in") or row.get("xd") or 0),
            })

        safe_output(result)

    except requests.RequestException as e:
        safe_output([{"error": f"request failed: {str(e)}"}])
    except (ValueError, TypeError, KeyError) as e:
        safe_output([{"error": f"parse failed: {str(e)}"}])


def main():
    parser = argparse.ArgumentParser(description="麦蕊智数桥接")
    parser.add_argument("action", choices=["fund_flow"])
    parser.add_argument("--code", type=str, required=True, help="股票代码")
    parser.add_argument("--days", type=int, default=5, help="返回天数")
    args = parser.parse_args()

    if args.action == "fund_flow":
        do_fund_flow(args.code, args.days)


if __name__ == "__main__":
    main()
