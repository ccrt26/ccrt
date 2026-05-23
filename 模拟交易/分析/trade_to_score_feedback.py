#!/usr/bin/env python3
"""
铁律量化 - 模拟交易止损 → 评分系统反馈映射
读取 transactions.csv 的止损记录，关联到当日评估数据，
生成"评分系统调整建议"

用法: python trade_to_score_feedback.py [--date YYYYMMDD]
"""

import json
import csv
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 路径配置
ROOT_DIR = Path(r"C:\Users\34269\Documents\Claude\股票分析")
TRANSACTIONS_CSV = ROOT_DIR / "模拟交易" / "持仓记录" / "transactions.csv"
EVAL_DIR = ROOT_DIR / "重点股票" / "次日评估"
OUTPUT_FILE = ROOT_DIR / "模拟交易" / "分析" / "评分调整建议.json"

# 评分维度 (对应白皮书评分体系)
DIMENSIONS = ["技术面", "基本面", "消息面", "板块面", "资金面", "宏观面"]


def load_transactions():
    """读取交易记录，筛选止损退出 (P1) 的交易"""
    if not TRANSACTIONS_CSV.exists():
        print(f"[SKIP] 交易记录不存在: {TRANSACTIONS_CSV}")
        return []

    trades = []
    with open(TRANSACTIONS_CSV, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # P1退出 = 止损
            if row.get('reason', '').startswith('P1'):
                trades.append(row)

    return trades


def load_eval_data(date_str):
    """加载指定日期的评估数据"""
    eval_file = EVAL_DIR / f"评估数据_{date_str}.json"
    if not eval_file.exists():
        return None
    with open(eval_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def analyze_stop_loss(trade):
    """分析单个止损交易的误判维度"""
    code = trade.get('code', '')
    date = trade.get('date', '')

    # 加载对应日期的评估数据
    eval_data = load_eval_data(date)
    if not eval_data:
        return None

    # 找到该股的评分明细
    stock_eval = None
    for item in eval_data.get('Stocks', []):
        if item.get('code') == code or item.get('stock_code') == code:
            stock_eval = item
            break

    if not stock_eval:
        return None

    # 分析评分明细，找出最高分但实际走势相反的维度（误判）
    trade_price = float(trade.get('price', 0))
    analysis = {
        'code': code,
        'date': date,
        'exit_price': trade_price,
        'entry_price': trade_price,
        'loss_pct': 0,
        'dimension_scores': {},
        'likely_misjudged_dimensions': []
    }

    # 提取各维度评分（根据实际数据结构调整）
    for dim in DIMENSIONS:
        score = None
        for key in [f'{dim}_score', f'{dim}Score', dim]:
            if key in stock_eval:
                score = stock_eval[key]
                break
        if score is not None:
            analysis['dimension_scores'][dim] = score

    # 找出最高分维度（这些可能是误判来源——如果看多但跌了）
    if analysis['dimension_scores']:
        sorted_dims = sorted(analysis['dimension_scores'].items(), key=lambda x: -x[1])
        # 得分最高的2-3个维度标记为"潜在误判"
        for dim, score in sorted_dims[:3]:
            if score >= 60:  # 仅标记高分维度
                analysis['likely_misjudged_dimensions'].append({
                    'dimension': dim,
                    'score': score,
                    'suggestion': f'关注{dim}评分阈值是否需要上调（当前止损表明该维度信号可靠性不足）'
                })

    return analysis


def generate_recommendations(all_analyses):
    """汇总所有止损分析，生成评分系统调整建议"""
    if not all_analyses:
        return {'status': 'no_data', 'message': '无止损交易数据', 'recommendations': []}

    # 按维度汇总误判次数
    dim_miscount = {}
    for a in all_analyses:
        for d in a.get('likely_misjudged_dimensions', []):
            dim = d['dimension']
            if dim not in dim_miscount:
                dim_miscount[dim] = {'count': 0, 'total_score': 0, 'suggestions': []}
            dim_miscount[dim]['count'] += 1
            dim_miscount[dim]['total_score'] += d['score']
            dim_miscount[dim]['suggestions'].append(d['suggestion'])

    recommendations = []
    for dim, data in sorted(dim_miscount.items(), key=lambda x: -x[1]['count']):
        avg_score = data['total_score'] / data['count'] if data['count'] > 0 else 0
        rec = {
            'dimension': dim,
            'stop_loss_count': data['count'],
            'avg_score_when_wrong': round(avg_score, 1),
            'risk_level': 'high' if data['count'] >= 3 else ('medium' if data['count'] >= 2 else 'low'),
            'suggestion': (
                f"{dim}在{data['count']}次止损中平均得分{avg_score:.0f}分，"
                f"建议{'调高该维度及格线' if data['count'] >= 3 else '观察该维度信号可靠性'}"
            )
        }
        recommendations.append(rec)

    return {
        'status': 'ok',
        'total_stop_losses': len(all_analyses),
        'analysis_date': datetime.now().strftime('%Y-%m-%d'),
        'recommendations': recommendations
    }


def main():
    print("=" * 60)
    print("模拟交易止损 → 评分系统反馈映射")
    print("=" * 60)

    trades = load_transactions()
    if not trades:
        print("无止损交易记录，跳过分析")
        # 输出空报告
        result = {'status': 'no_data', 'message': '无止损交易数据', 'recommendations': []}
    else:
        print(f"发现 {len(trades)} 条止损记录")
        analyses = []
        for t in trades:
            a = analyze_stop_loss(t)
            if a:
                analyses.append(a)
                print(f"  {a['code']}: 亏损{a['loss_pct']:.1f}%, 误判维度: {[d['dimension'] for d in a['likely_misjudged_dimensions']]}")

        result = generate_recommendations(analyses)

    # 输出建议
    print(f"\n评分调整建议:")
    for rec in result.get('recommendations', []):
        level_tag = {'high': '🔴', 'medium': '🟡', 'low': '🟢'}.get(rec['risk_level'], '⚪')
        print(f"  {level_tag} [{rec['risk_level'].upper()}] {rec['suggestion']}")

    # 写入JSON
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n报告已写入: {OUTPUT_FILE}")


if __name__ == '__main__':
    main()
