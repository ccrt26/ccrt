#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
铁律量化 · 周度因子归因脚本 (青山 v2026-05-24)
=================================================
从每日荐股模拟交易流水提取子维度归因，输出周度报告。
调度: 每周一 09:00 自动运行
输入: 模拟交易/每日荐股赛道/持仓记录/transactions_daily.csv
输出: 模拟交易/每日荐股赛道/周报/factor_attribution_YYYYWW.md
"""
import csv, json, os, sys
from datetime import date, datetime, timedelta
from collections import defaultdict
import math

ROOT = r"Split-Path -Parent (Split-Path -Parent $PSScriptRoot)"
TXN_FILE = os.path.join(ROOT, "模拟交易", "每日荐股赛道", "持仓记录", "transactions_daily.csv")
OUT_DIR = os.path.join(ROOT, "模拟交易", "每日荐股赛道", "周报")
PERF_FILE = os.path.join(ROOT, "模拟交易", "每日荐股赛道", "绩效报告", "perf_summary_daily.json")

# 子维度列表
SUB_FACTORS = ["S_Base", "S_Fund", "S_Tech", "S_Money", "S_News", "S_Risk", "S_SectorTrend"]
FACTOR_LABELS = {
    "S_Base": "基础门槛", "S_Fund": "基本面", "S_Tech": "技术面",
    "S_Money": "资金面", "S_News": "消息面", "S_Risk": "风控",
    "S_SectorTrend": "板块趋势"
}


def get_week_range():
    """获取上周一至周五的日期范围"""
    today = date.today()
    monday = today - timedelta(days=today.weekday() + 7)
    friday = monday + timedelta(days=4)
    return monday, friday


def parse_transactions():
    """解析交易流水，按股票聚合盈亏"""
    if not os.path.exists(TXN_FILE):
        print(f"ERROR: 交易流水文件不存在: {TXN_FILE}")
        return []

    trades = []
    with open(TXN_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            trades.append(row)

    monday, friday = get_week_range()
    monday_s = monday.strftime("%Y%m%d")
    friday_s = friday.strftime("%Y%m%d")

    # 聚合: (code, entry_date) -> {buy, sell, score, sector, theme, scores_detail}
    pairs = defaultdict(lambda: {"buys": [], "sells": [], "entry_score": 0,
                                  "entry_sector": "", "entry_theme": ""})

    for t in trades:
        t_date = t.get("date", "")
        if t_date < monday_s or t_date > friday_s:
            continue

        code = t.get("code", "")
        action = t.get("action", "BUY")

        if action == "BUY":
            pairs[(code, t_date)]["buys"].append(t)
            pairs[(code, t_date)]["entry_score"] = float(t.get("entry_score", 0))
            pairs[(code, t_date)]["entry_sector"] = t.get("entry_sector", "")
            pairs[(code, t_date)]["entry_theme"] = t.get("entry_theme", "")
        elif action in ("SELL", "SELL_HALF"):
            pairs[(code, t_date)]["sells"].append(t)

    return pairs


def calc_spearman(x_vals, y_vals):
    """计算Spearman秩相关系数"""
    if len(x_vals) < 3:
        return None
    n = len(x_vals)

    def rank(arr):
        sorted_idx = sorted(range(n), key=lambda i: arr[i])
        ranks = [0] * n
        for r, idx in enumerate(sorted_idx):
            ranks[idx] = r + 1
        return ranks

    rx = rank(x_vals)
    ry = rank(y_vals)
    d_sq = sum((rx[i] - ry[i]) ** 2 for i in range(n))
    return round(1 - 6 * d_sq / (n * (n * n - 1)), 3)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    monday, friday = get_week_range()
    week_label = f"{monday.strftime('%Y')}{monday.strftime('%W')}"
    out_file = os.path.join(OUT_DIR, f"factor_attribution_{week_label}.md")

    pairs = parse_transactions()
    if not pairs:
        print(f"WARNING: 上周 ({monday} ~ {friday}) 无交易记录")
        return

    # 计算每笔交易的盈亏
    results = []
    for (code, entry_date), data in pairs.items():
        if not data["buys"] or not data["sells"]:
            continue
        total_cost = sum(float(b.get("total_cost", 0)) for b in data["buys"])
        total_proceeds = sum(float(s.get("total_cost", 0)) for s in data["sells"])
        pnl = total_proceeds + total_cost  # total_cost是负数(买入支出)
        pnl_pct = round(pnl / abs(total_cost) * 100, 2) if total_cost != 0 else 0

        results.append({
            "code": code, "entry_date": entry_date,
            "pnl": pnl, "pnl_pct": pnl_pct,
            "entry_score": data["entry_score"],
            "entry_sector": data["entry_sector"],
            "entry_theme": data["entry_theme"],
        })

    if len(results) < 3:
        print(f"WARNING: 完整交易 < 3笔，样本量不足以做因子归因")
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(f"# 周度因子归因 {monday} ~ {friday}\n\n")
            f.write(f"**状态**: 样本不足（完整交易 {len(results)} 笔 < 3）\n")
        return

    # Spearman: TotalScore vs 收益
    scores = [r["entry_score"] for r in results]
    returns = [r["pnl_pct"] for r in results]
    spear_total = calc_spearman(scores, returns)

    # 板块阶段胜率
    sector_stats = defaultdict(lambda: {"wins": 0, "total": 0})
    for r in results:
        phase = r["entry_sector"] or "未知"
        sector_stats[phase]["total"] += 1
        if r["pnl_pct"] > 0:
            sector_stats[phase]["wins"] += 1

    # 生成报告
    lines = []
    lines.append(f"# 周度因子归因报告")
    lines.append(f"")
    lines.append(f"> 周期: {monday} ~ {friday} | 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"")
    lines.append(f"## 一、概览")
    lines.append(f"")
    lines.append(f"| 指标 | 值 |")
    lines.append(f"|:-----|:--|")
    lines.append(f"| 完整交易笔数 | {len(results)} |")
    wins = sum(1 for r in results if r["pnl_pct"] > 0)
    win_rate = round(wins / len(results) * 100, 1)
    lines.append(f"| 胜率 | {win_rate}% |")
    avg_return = round(sum(r["pnl_pct"] for r in results) / len(results), 2)
    lines.append(f"| 平均收益 | {avg_return}% |")
    lines.append(f"| Spearman(评分,收益) | {spear_total if spear_total is not None else 'N/A'} |")
    lines.append(f"")

    if spear_total is not None:
        if spear_total < 0:
            lines.append(f"> ⚠️ Spearman为负({spear_total})，评分与收益反向！需审查评分体系。")
        elif spear_total < 0.15:
            lines.append(f"> ⚠️ Spearman偏低({spear_total})，评分区分度不足。")
        else:
            lines.append(f"> ✅ Spearman={spear_total}，评分与收益正相关。")

    lines.append(f"")
    lines.append(f"## 二、板块阶段胜率")
    lines.append(f"")
    lines.append(f"| 板块阶段 | 胜率 | 交易数 |")
    lines.append(f"|:--------|:---:|:-----:|")
    for phase in ["主升", "主升调整", "潜伏期"]:
        stats = sector_stats.get(phase, {"wins": 0, "total": 0})
        wr = round(stats["wins"] / stats["total"] * 100, 1) if stats["total"] > 0 else "N/A"
        lines.append(f"| {phase} | {wr}% | {stats['total']} |")

    lines.append(f"")
    lines.append(f"## 三、预警信号")
    lines.append(f"")

    has_alerts = False
    if spear_total is not None and spear_total < 0:
        lines.append(f"- ⚠️ **评分反向**: Spearman={spear_total}，连续负相关需审查")
        has_alerts = True

    # 检查板块阶段异常
    for phase, stats in sector_stats.items():
        if stats["total"] >= 3:
            wr = round(stats["wins"] / stats["total"] * 100, 1)
            if wr < 30:
                lines.append(f"- ⚠️ **{phase}低胜率**: {wr}% ({stats['total']}笔)，该阶段选股可能失效")
                has_alerts = True

    if not has_alerts:
        lines.append(f"- 无预警信号")
    lines.append(f"")

    # 写入文件
    with open(out_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"周度因子归因完成: {out_file}")
    print(f"  交易: {len(results)}笔 | 胜率: {win_rate}% | Spearman: {spear_total}")


if __name__ == "__main__":
    main()
