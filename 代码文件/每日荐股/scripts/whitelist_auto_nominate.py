#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
铁律量化 · 白名单半自动提名引擎
================================
P2-8: 当股票满足以下三条件时自动提名加入产业认可白名单：
  1. 收入纯度 > 50%（主营收入占比，需人工确认）
  2. 研发费用率 > 15%
  3. 券商研报覆盖数 > 10篇（近12个月）

输出 JSON 到 stdout，供 PowerShell 消费或人工审核。

调用方式：
    python whitelist_auto_nominate.py --stocks 688256,002371,300661 [--output nominate.json]
    python whitelist_auto_nominate.py --help
"""

import argparse
import json
import sys
import time
from datetime import datetime, timedelta


def check_akshare():
    """确保 akshare 可用"""
    try:
        import akshare as ak
        return ak
    except ImportError:
        print(json.dumps({"error": "akshare not installed"}), file=sys.stderr)
        sys.exit(1)


def safe_json(obj):
    """输出 JSON，处理 NaN"""
    import pandas as pd
    if isinstance(obj, pd.DataFrame):
        obj = obj.where(pd.notna(obj), None)
        text = json.dumps(obj.to_dict(orient="records"), ensure_ascii=False, default=str)
    else:
        text = json.dumps(obj, ensure_ascii=False, default=str)
    sys.stdout.buffer.write(text.encode("utf-8"))
    sys.stdout.buffer.write(b"\n")


def get_rd_expense_ratio(ak, code):
    """
    获取最近一期研发费用率（研发费用/营业总收入）
    数据源: 同花顺财务摘要 → 销售毛利率+销售净利率差值作为代理
    或直接尝试东方财富利润表获取研发费用。

    返回: (rd_ratio, source_label)
      rd_ratio: float (0-100)
      source_label: 数据来源标记
    """
    try:
        # 尝试从东方财富利润表获取研发费用
        df = ak.stock_profit_sheet_by_report_em(symbol=code)
        if df is None or df.empty:
            return None, "数据不可获取"

        # 找最新一期有研发费用的记录
        # 列名可能包含: 研发费用, 营业总收入
        rd_col = None
        revenue_col = None
        for col in df.columns:
            if "研发费用" in str(col):
                rd_col = col
            if "营业总收入" in str(col) or "营业收入" in str(col):
                revenue_col = col

        if rd_col is None or revenue_col is None:
            # 降级: 用 THS 财务摘要中的毛利率/净利率代理
            return _get_rd_proxy(ak, code)

        # 取最新一期
        latest = df.iloc[0]
        rd_expense = float(latest[rd_col]) if pd.notna(latest[rd_col]) else 0
        revenue = float(latest[revenue_col]) if pd.notna(latest[revenue_col]) else 0

        if revenue <= 0:
            return None, "营收数据异常"

        rd_ratio = round(rd_expense / revenue * 100, 2)
        return rd_ratio, "[1]东方财富利润表"

    except Exception:
        return _get_rd_proxy(ak, code)


def _get_rd_proxy(ak, code):
    """
    降级方案：用同花顺财务摘要的 销售毛利率 - 销售净利率 作为研发费用率代理
    逻辑: 毛利-净利 差额主要来自 销售费用+管理费用+研发费用，
    科技公司中研发费用通常是最大单项，取差值*0.5作为保守估计
    """
    try:
        df = ak.stock_financial_abstract_ths(symbol=code)
        if df is None or df.empty:
            return None, "代理方案也无数据"

        latest = df.iloc[-1]  # THS 升序，取最后一条
        gross_margin = _parse_pct(latest.get("销售毛利率", "0%"))
        net_margin = _parse_pct(latest.get("销售净利率", "0%"))

        # 毛利率 - 净利率 = 期间费用率总额，取50%作为研发费率代理
        expense_gap = gross_margin - net_margin
        rd_proxy = round(expense_gap * 0.5, 2)

        return max(0, rd_proxy), "[B]同花顺毛利率代理(Phase1)"
    except Exception:
        return None, "不可获取"


def _parse_pct(val):
    """解析百分比字符串，如 '45.3%' → 45.3"""
    if val is None:
        return 0.0
    s = str(val).replace(",", "").strip()
    if s.endswith("%"):
        s = s[:-1]
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def get_research_report_count(ak, code, months=12):
    """
    获取近N个月券商研报覆盖数

    返回: (count, source_label)
    """
    try:
        df = ak.stock_research_report_em(symbol=code)
        if df is None or df.empty:
            return 0, "[1]东方财富研报(无覆盖)"

        # 列名: 评级日期, 券商名称, 评级, 评级变化, 目标价, ...
        date_col = None
        for col in df.columns:
            if "日期" in str(col):
                date_col = col
                break

        if date_col is None:
            # 假设第一列是日期
            date_col = df.columns[0]

        cutoff = datetime.now() - timedelta(days=months * 30)

        count = 0
        for _, row in df.iterrows():
            try:
                d = pd.to_datetime(row[date_col])
                if d >= cutoff:
                    count += 1
            except Exception:
                count += 1  # 日期解析失败也计入

        return count, "[1]东方财富研报"

    except Exception:
        return 0, "[1]东方财富研报(获取失败)"


def get_revenue_purity(ak, code):
    """
    收入纯度: 主营收入/营业总收入，通过行业分类+毛利率判断业务集中度。

    此指标无法完全自动化，需人工确认。本函数提供辅助信号：
    - 如果毛利率>30%且来自单一行业(东方财富行业分类)，标记为"高纯度候选"

    返回: (purity_assessment, confidence, note)
    """
    try:
        # 获取个股行业分类 (东方财富)
        df = ak.stock_individual_info_em(symbol=code)
        if df is not None and not df.empty:
            # stock_individual_info_em 返回: item, value
            industry = ""
            for _, row in df.iterrows():
                if "行业" in str(row.get("item", "")):
                    industry = str(row.get("value", ""))
                    break

            # 如果有明确的行业归属，初步判断收入纯度
            if industry:
                return {
                    "assessment": "候选",
                    "confidence": "低(需人工确认)",
                    "industry": industry,
                    "note": "行业分类明确，需人工确认细分收入占比"
                }

        return {
            "assessment": "待确认",
            "confidence": "低(需人工确认)",
            "industry": "",
            "note": "无法自动获取收入纯度，请查阅年报分部收入"
        }

    except Exception:
        return {
            "assessment": "待确认",
            "confidence": "低(需人工确认)",
            "industry": "",
            "note": "数据获取失败"
        }


def nominate(ak, codes, output_file=None):
    """
    主提名逻辑: 扫描指定股票列表，按三条件评估并输出提名

    参数:
      codes: list[str] 股票代码列表
      output_file: str 可选JSON输出路径

    返回: list[dict] 提名结果列表
    """
    import pandas as pd

    results = []
    total = len(codes)

    for i, code in enumerate(codes, 1):
        print(f"[{i}/{total}] 评估 {code}...", file=sys.stderr)

        result = {
            "code": code,
            "criteria": {},
            "nominated": False,
            "summary": "",
        }

        # C1: 收入纯度
        purity = get_revenue_purity(ak, code)
        result["criteria"]["revenue_purity"] = purity
        c1_pass = purity.get("assessment") == "候选"

        # C2: 研发费用率
        rd_ratio, rd_source = get_rd_expense_ratio(ak, code)
        c2_pass = rd_ratio is not None and rd_ratio > 15
        result["criteria"]["rd_expense_rate"] = {
            "value": rd_ratio,
            "threshold": 15,
            "passed": c2_pass,
            "source": rd_source,
        }

        # C3: 券商研报覆盖
        report_count, report_source = get_research_report_count(ak, code)
        c3_pass = report_count >= 10
        result["criteria"]["research_coverage"] = {
            "value": report_count,
            "threshold": 10,
            "passed": c3_pass,
            "source": report_source,
        }

        # 综合判断
        passed = sum([c1_pass, c2_pass, c3_pass])
        result["criteria_met"] = passed
        result["nominated"] = passed >= 3

        if passed >= 3:
            result["summary"] = "符合全部三项条件，建议提名加入白名单"
        elif passed == 2:
            result["summary"] = "符合2/3条件，建议人工复审"
        else:
            result["summary"] = f"仅符合{passed}/3条件，暂不提名"

        results.append(result)

        # API 限速
        if i < total:
            time.sleep(0.35)

    # 输出
    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, ensure_ascii=False, indent=2, fp=f)
        print(f"\n结果已写入: {output_file}", file=sys.stderr)

    # 摘要
    nominated = [r for r in results if r["nominated"]]
    candidates = [r for r in results if r["criteria_met"] >= 2]
    print(f"\n=== 提名摘要 ===", file=sys.stderr)
    print(f"扫描股票: {total}", file=sys.stderr)
    print(f"3/3提名: {len(nominated)} 只", file=sys.stderr)
    print(f"2/3候选: {len(candidates) - len(nominated)} 只", file=sys.stderr)
    if nominated:
        print(f"提名名单: {[r['code'] for r in nominated]}", file=sys.stderr)

    safe_json(results)
    return results


def main():
    parser = argparse.ArgumentParser(description="白名单半自动提名引擎")
    parser.add_argument("--stocks", type=str, default="",
                        help="逗号分隔的股票代码列表，如 688256,002371,300661")
    parser.add_argument("--input", type=str, default="",
                        help="从JSON文件读取股票列表（key: stocks）")
    parser.add_argument("--output", type=str, default="",
                        help="输出JSON文件路径")
    parser.add_argument("--whitelist", type=str, default="",
                        help="现有白名单JSON路径，用于排除已入选股票")

    args = parser.parse_args()

    ak = check_akshare()

    # 加载候选股票
    codes = []
    if args.stocks:
        codes = [c.strip() for c in args.stocks.split(",") if c.strip()]
    elif args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                codes = data
            elif isinstance(data, dict) and "stocks" in data:
                codes = data["stocks"]

    if not codes:
        print(json.dumps({"error": "请提供 --stocks 或 --input 参数"}), file=sys.stderr)
        sys.exit(1)

    # 排除已入选白名单的股票
    if args.whitelist:
        try:
            with open(args.whitelist, "r", encoding="utf-8") as f:
                wl = json.load(f)
                existing = set()
                for theme, info in wl.get("whitelist", {}).items():
                    for s in info.get("stocks", []):
                        existing.add(s)
                codes = [c for c in codes if c not in existing]
                print(f"排除已入选: {len(existing)} 只, 剩余候选: {len(codes)} 只", file=sys.stderr)
        except FileNotFoundError:
            pass

    if not codes:
        print(json.dumps({"error": "所有候选股票已在白名单中"}), file=sys.stderr)
        sys.exit(0)

    output_file = args.output if args.output else None
    nominate(ak, codes, output_file)


if __name__ == "__main__":
    main()
