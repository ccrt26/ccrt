#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
铁律量化 · 同花顺(THS)数据桥接脚本
=====================================
通过 akshare 调用同花顺 THS 接口，作为东方财富 API 的备份数据源。
输出 JSON 到 stdout，供 PowerShell 端 ConvertFrom-Json 消费。

调用方式：
    python stock_data_fetcher_ths.py <action> [--param value ...]

支持的操作：
    sector_ranking   -- 行业排名（替代 东方财富[7]）
    sector_kline     -- 行业K线（替代 东方财富板块K线）
    sector_fund_flow -- 行业资金流向（替代 东方财富[10]）
    sector_list      -- 行业列表（获取THS行业名称与代码）
    financial        -- 财务数据（替代 东方财富[3]）

数据源固定：akshare (同花顺 THS) / akshare==1.18.63
"""
import argparse
import json
import sys
import pandas as pd

AKSHARE_MIN_VERSION = "1.18.63"


def check_akshare_version():
    """确保 akshare 版本符合要求"""
    try:
        import akshare as ak
        if ak.__version__ < AKSHARE_MIN_VERSION:
            err = {"error": f"akshare>={AKSHARE_MIN_VERSION} required, got {ak.__version__}"}
            print(json.dumps(err), file=sys.stderr)
            sys.exit(1)
    except ImportError:
        print(json.dumps({"error": "akshare not installed"}), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"error": f"version check failed: {str(e)}"}), file=sys.stderr)
        sys.exit(1)


def safe_json(obj):
    """将 DataFrame 或 list 转换为 JSON，处理 NaN/NaT 等不可序列化值，强制 UTF-8 输出"""
    if isinstance(obj, pd.DataFrame):
        obj = obj.where(pd.notna(obj), None)
        text = json.dumps(obj.to_dict(orient="records"), ensure_ascii=False, default=str)
    elif isinstance(obj, pd.Series):
        obj = obj.where(pd.notna(obj), None)
        text = json.dumps(obj.to_list(), ensure_ascii=False, default=str)
    else:
        text = json.dumps(obj, ensure_ascii=False, default=str)
    # 强制 UTF-8 输出（解决 Windows 重定向到文件时的编码问题）
    sys.stdout.buffer.write(text.encode("utf-8"))
    sys.stdout.buffer.write(b"\n")


def do_sector_ranking(top=30):
    """
    行业排名 — 同花顺行业板块实时行情
    输出字段与 Get-SectorData 对齐：
      SectorCode, SectorName, Index, ChangePct, Turnover(成交额亿)
    """
    import akshare as ak
    df = ak.stock_board_industry_summary_ths()
    if df is None or df.empty:
        print(json.dumps({"error": "no data"}))
        return

    # THS 返回12列：序号, 名称, 涨跌幅, 总成交额, 总成交额, 主力净流入, 上涨家数, 下跌家数, 领涨值, 领涨股, 领涨股-代码, 领涨股-涨跌幅
    # 注：领涨值是领涨股的当前价/指数值，不是百分比
    col_names = ["Rank", "SectorName", "ChangePct", "TotalAmount", "DealAmount",
                 "MainInflow", "UpCount", "DownCount", "LeadValue", "LeadStock", "LeadCode", "LeadPct"]
    df.columns = col_names
    df["SectorCode"] = ""  # THS 使用数字代码，此字段留空由 PowerShell 侧补充
    # Index 取领涨值或总成交额作为参考指数
    df["Index"] = pd.to_numeric(df["LeadValue"], errors="coerce").fillna(0)
    df["Turnover"] = pd.to_numeric(df["TotalAmount"], errors="coerce").fillna(0)

    result = df.head(top).to_dict(orient="records")
    safe_json(result)


def do_sector_kline(name, days=60):
    """
    行业K线 — 同花顺行业板块指数日K线
    输出字段：close, volume, date, open, high, low

    参数：
      name: 行业名称（如 "半导体"）
      days: 获取的天数（默认60）
    """
    import akshare as ak
    from datetime import datetime, timedelta

    end = datetime.now()
    start = end - timedelta(days=days * 2)  # 多取一些确保够天数
    start_str = start.strftime("%Y%m%d")
    end_str = end.strftime("%Y%m%d")

    df = ak.stock_board_industry_index_ths(symbol=name, start_date=start_str, end_date=end_str)
    if df is None or df.empty:
        print(json.dumps({"error": f"no data for sector: {name}"}))
        return

    # 列名：日期, 开盘价, 最高价, 最低价, 收盘价, 成交量, 成交额
    df.columns = ["date", "open", "high", "low", "close", "volume", "amount"]
    # 取最近 days 条
    df = df.tail(days)

    result = []
    for _, row in df.iterrows():
        entry = {
            "date": str(row["date"]),
            "open": float(row["open"]) if pd.notna(row["open"]) else 0,
            "high": float(row["high"]) if pd.notna(row["high"]) else 0,
            "low": float(row["low"]) if pd.notna(row["low"]) else 0,
            "close": float(row["close"]) if pd.notna(row["close"]) else 0,
            "volume": int(row["volume"]) if pd.notna(row["volume"]) else 0,
        }
        result.append(entry)

    safe_json(result)


def do_sector_list():
    """
    行业列表 — 获取同花顺全部分行业名称与代码
    输出：SectorName, SectorCode
    """
    import akshare as ak
    df = ak.stock_board_industry_name_ths()
    if df is None or df.empty:
        print(json.dumps({"error": "no data"}))
        return

    result = []
    for _, row in df.iterrows():
        result.append({
            "SectorName": str(row["name"]),
            "SectorCode": str(row["code"]),
        })
    safe_json(result)


def do_sector_fund_flow(top=30, period="即时"):
    """
    行业资金流向 — 同花顺行业资金流向
    输出字段与 Get-SectorFundFlow 对齐：
      SectorCode, SectorName, NetInflow, MainInflow, ChangePct, TurnRate

    period: "即时", "3日主力", "5日主力", "10日主力", "20日主力"
    """
    import akshare as ak
    df = ak.stock_fund_flow_industry(symbol=period)
    if df is None or df.empty:
        print(json.dumps({"error": "no data"}))
        return

    # 列名：序号, 行业, 行业指数, 行业-涨跌幅, 主力资金, 主力资金, 主力资金, 公司家数, 领涨股, 领涨股-涨跌幅, 目前
    df.columns = ["Rank", "SectorName", "Index", "ChangePct",
                   "MainInflow", "MF2", "MF3", "CompanyCount", "LeadStock", "LeadPct", "Current"]
    df["SectorCode"] = ""
    df["NetInflow"] = pd.to_numeric(df["MainInflow"], errors="coerce").fillna(0)
    df["MainInflow"] = pd.to_numeric(df["MainInflow"], errors="coerce").fillna(0)
    df["TurnRate"] = 0.0

    result = df.head(top).to_dict(orient="records")
    safe_json(result)


def do_financial(code, quarters=4):
    """
    财务数据 — 同花顺个股财务摘要
    输出字段与 Get-StockFinancial 对齐关键字段：
      BASIC_EPS(基本每股收益), WEIGHTAVG_ROE(净资产收益率),
      TOTAL_OPERATE_INCOME(营业总收入), PARENT_NETPROFIT(净利润)
    """
    import akshare as ak

    df = ak.stock_financial_abstract_ths(symbol=code)
    if df is None or df.empty:
        print(json.dumps({"error": f"no financial data for {code}"}))
        return

    # 列名：报告期, 净利润, 净利润同比增长, 扣非净利润, 扣非净利润同比增长,
    #       营业总收入, 营业总收入同比增长, 基本每股收益, 每股净资产,
    #       每股资本公积金, 每股未分配利润, 每股经营现金流, 销售净利率,
    #       销售毛利率, 净资产收益率, 净资产收益率-摊薄, 营业周期, ...
    df.columns = [
        "REPORT_DATE", "PARENT_NETPROFIT", "NETPROFIT_YOY",
        "DEDUCTED_NETPROFIT", "DEDUCTED_YOY",
        "TOTAL_OPERATE_INCOME", "REVENUE_YOY",
        "BASIC_EPS", "BPS", "CAPITAL_RESERVE", "RETAINED_EARNINGS",
        "CFPS", "NETPROFIT_MARGIN", "GROSS_MARGIN", "WEIGHTAVG_ROE",
        "ROE_DILUTED",
    ] + [f"COL_{i}" for i in range(len(df.columns) - 16)]

    # 取最近 quarters 条（THS 返回按时间升序，取最后几条）
    df = df.tail(quarters).reset_index(drop=True)

    # 清理数值字段：THS 返回含中文单位，需转换为纯数值
    # 亿元→元, 万元→元, %→小数, 元→移除
    def clean_num(val):
        if val is None:
            return 0.0
        val_str = str(val).replace(",", "").strip()
        if val_str in ("False", "True", "-", ""):
            return 0.0
        multiplier = 1.0
        if "亿" in val_str:
            multiplier = 1e8
            val_str = val_str.replace("亿", "")
        elif "万" in val_str:
            multiplier = 1e4
            val_str = val_str.replace("万", "")
        if "元" in val_str:
            val_str = val_str.replace("元", "")
        if val_str.endswith("%"):
            multiplier *= 0.01
            val_str = val_str[:-1]
        try:
            return float(val_str) * multiplier
        except (ValueError, TypeError):
            return 0.0

    result = []
    for _, row in df.iterrows():
        entry = {}
        for col in df.columns:
            if col.startswith("COL_"):
                continue
            entry[col] = clean_num(row.get(col))
        # 确保核心字段存在
        entry["REPORT_DATE"] = str(row.get("REPORT_DATE", ""))
        result.append(entry)

    safe_json(result)


def main():
    parser = argparse.ArgumentParser(description="同花顺(THS)数据桥接")
    parser.add_argument("action", choices=[
        "sector_ranking", "sector_kline", "sector_fund_flow",
        "sector_list", "financial"
    ], help="操作类型")
    parser.add_argument("--top", type=int, default=30, help="返回条数（默认30）")
    parser.add_argument("--name", type=str, default="", help="行业名称（sector_kline 用）")
    parser.add_argument("--code", type=str, default="", help="股票代码（financial 用）")
    parser.add_argument("--days", type=int, default=60, help="K线天数（默认60）")
    parser.add_argument("--quarters", type=int, default=4, help="财务季度数（默认4）")
    parser.add_argument("--period", type=str, default="即时", help="资金流周期 默认即时")

    args = parser.parse_args()

    check_akshare_version()

    try:
        if args.action == "sector_ranking":
            do_sector_ranking(top=args.top)
        elif args.action == "sector_kline":
            if not args.name:
                print(json.dumps({"error": "--name is required for sector_kline"}))
                sys.exit(1)
            do_sector_kline(name=args.name, days=args.days)
        elif args.action == "sector_fund_flow":
            do_sector_fund_flow(top=args.top, period=args.period)
        elif args.action == "sector_list":
            do_sector_list()
        elif args.action == "financial":
            if not args.code:
                print(json.dumps({"error": "--code is required for financial"}))
                sys.exit(1)
            do_financial(code=args.code, quarters=args.quarters)
    except Exception as e:
        print(json.dumps({"error": f"THS bridge error: {str(e)}"}))
        sys.exit(1)


if __name__ == "__main__":
    main()
