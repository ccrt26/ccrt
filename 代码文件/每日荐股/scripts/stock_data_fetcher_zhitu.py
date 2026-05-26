#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
铁律量化 · 智兔数服桥接脚本 [B3]
=====================================
作为东方财富[9]资金流向的第三备源。
免费额度最大(1000次/天)，无需注册即可测试。

调用方式：
    python stock_data_fetcher_zhitu.py fund_flow --code 000001 --days 5

API Token：从环境变量 ZHITU_TOKEN 读取（未设置时使用免费测试Token）
官网：https://www.zhituapi.com
接口：/hs/history/transaction/{code} — 逐日资金流向（大/中/小单成交额）
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta


def safe_output(obj):
    """JSON输出到stdout (UTF-8)"""
    text = json.dumps(obj, ensure_ascii=False, default=str)
    sys.stdout.buffer.write(text.encode("utf-8"))
    sys.stdout.buffer.write(b"\n")


def get_token():
    """从环境变量读取API Token，未设置时使用测试Token"""
    key = os.environ.get("ZHITU_TOKEN", "")
    if not key:
        key = "ZHITU_TOKEN_LIMIT_TEST"
    return key


def do_fund_flow(code, days=5):
    """
    个股资金流向日K线 — 智兔数服
    接口: /hs/history/transaction/{code}

    字段映射 (智兔 → 东方财富):
      SuperLargeIn = 主买特大单成交额 - 被动买特大单成交额 (zmbtdcje - bdmbtdcje)
      LargeIn      = 主买大单成交额 - 被动买大单成交额 (zmbddcje - bdmbddcje)
      MainNetInflow = SuperLargeIn + LargeIn
      SmallIn      = 主买小单成交额 - 被动买小单成交额 (zmbxdcje - bdmbxdcje)
    """
    token = get_token()

    try:
        import requests
    except ImportError:
        print(json.dumps({"error": "requests not installed"}), file=sys.stderr)
        sys.exit(1)

    # 日期范围（拉宽窗口以覆盖非交易日）
    et = datetime.now().strftime("%Y%m%d")
    st = (datetime.now() - timedelta(days=days * 3)).strftime("%Y%m%d")

    url = f"https://api.zhituapi.com/hs/history/transaction/{code}"

    params = {
        "token": token,
        "st": st,
        "et": et,
        "lt": days + 5,
    }

    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()

        if not isinstance(data, list):
            safe_output([{"error": f"unexpected response type: {type(data).__name__}"}])
            return

        if len(data) == 0:
            safe_output([])
            return

        # 检查错误响应
        if isinstance(data[0], dict) and data[0].get("error"):
            safe_output([{"error": str(data[0].get("error"))}])
            return

        result = []
        for row in data[-days:]:
            t = str(row.get("t", ""))
            date = t[:10] if " " in t else t  # "2026-05-25 00:00:00" → "2026-05-25"

            # 主动买入 - 被动买入 = 净流入
            super_large_in = float(row.get("zmbtdcje", 0)) - float(row.get("bdmbtdcje", 0))
            large_in = float(row.get("zmbddcje", 0)) - float(row.get("bdmbddcje", 0))
            small_in = float(row.get("zmbxdcje", 0)) - float(row.get("bdmbxdcje", 0))
            main_net = super_large_in + large_in

            result.append({
                "Date": date,
                "MainNetInflow": main_net,
                "SuperLargeIn": super_large_in,
                "LargeIn": large_in,
                "SmallIn": small_in,
            })

        safe_output(result)

    except requests.RequestException as e:
        safe_output([{"error": f"request failed: {str(e)}"}])
    except (ValueError, TypeError, KeyError) as e:
        safe_output([{"error": f"parse failed: {str(e)}"}])


def main():
    parser = argparse.ArgumentParser(description="智兔数服桥接")
    parser.add_argument("action", choices=["fund_flow"])
    parser.add_argument("--code", type=str, required=True, help="股票代码")
    parser.add_argument("--days", type=int, default=5, help="返回天数")
    args = parser.parse_args()

    if args.action == "fund_flow":
        do_fund_flow(args.code, args.days)


if __name__ == "__main__":
    main()
