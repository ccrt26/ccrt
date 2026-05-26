#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
铁律量化 · 迪雅数据桥接脚本 [B1]
=====================================
作为东方财富[9]资金流向的第一备源。
接口结构高度相似必盈API，迁移成本最低。

调用方式：
    python stock_data_fetcher_diya.py fund_flow --code 000001 --days 5

API密钥：从环境变量 DIYA_LICENCE 读取
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


def get_licence():
    """从环境变量读取API密钥"""
    key = os.environ.get("DIYA_LICENCE", "")
    if not key:
        print(json.dumps({"error": "DIYA_LICENCE 环境变量未设置"}), file=sys.stderr)
        sys.exit(1)
    return key


def do_fund_flow(code, days=5):
    """
    个股资金流向日K线 — 迪雅数据
    接口结构类似必盈 hsstock/fund/flow/{code}/{licence}

    目标输出字段：
        Date, MainNetInflow, SuperLargeIn, LargeIn, SmallIn
    """
    licence = get_licence()

    try:
        import requests
    except ImportError:
        print(json.dumps({"error": "requests not installed"}), file=sys.stderr)
        sys.exit(1)

    # 迪雅数据API (接口结构与必盈高度相似)
    market = "sh" if code.startswith("6") else "sz"
    url = f"https://api.diyadata.com/hsstock/fund/flow/{market}/{code}/{licence}"

    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()

        if not data or data.get("error"):
            safe_output([{"error": str(data.get("error", "empty response"))}])
            return

        # 提取资金流数据行
        rows = data.get("data") or data.get("klines") or data.get("rows") or data
        if isinstance(rows, dict):
            rows = [rows]
        if not isinstance(rows, list):
            safe_output([])
            return

        result = []
        for row in rows[-days:]:
            result.append({
                "Date": str(row.get("date") or row.get("trade_date") or ""),
                "MainNetInflow": float(row.get("main_net_inflow") or row.get("zljlr") or 0),
                "SuperLargeIn": float(row.get("super_large") or row.get("cdd") or 0),
                "LargeIn": float(row.get("large") or row.get("dd") or 0),
                "SmallIn": float(row.get("small") or row.get("xd") or 0),
            })

        safe_output(result)

    except requests.RequestException as e:
        safe_output([{"error": f"request failed: {str(e)}"}])
    except (ValueError, TypeError, KeyError) as e:
        safe_output([{"error": f"parse failed: {str(e)}"}])


def main():
    parser = argparse.ArgumentParser(description="迪雅数据桥接")
    parser.add_argument("action", choices=["fund_flow"])
    parser.add_argument("--code", type=str, required=True, help="股票代码")
    parser.add_argument("--days", type=int, default=5, help="返回天数")
    args = parser.parse_args()

    if args.action == "fund_flow":
        do_fund_flow(args.code, args.days)


if __name__ == "__main__":
    main()
