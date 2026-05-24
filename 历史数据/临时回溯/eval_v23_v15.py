#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v2.3 评分引擎 × v1.5 后评估
评估对象：5月21日推荐 → 5月22日实际表现
"""

import json
import math
import os
import sys
from collections import Counter

# ─── CSS样式 ─────────────────────────────────────────────────
def load_css():
    css_path = os.path.join(os.path.dirname(__file__), '数据', 'report_style.css')
    with open(css_path, 'r', encoding='utf-8') as f:
        return f.read()

# ─── 读取数据 ───────────────────────────────────────────────
def load_json(path):
    with open(path, 'r', encoding='utf-8-sig') as f:
        return json.load(f)

v23_data  = load_json(r'C:\Users\34269\Documents\Claude\股票分析\代码文件\数据\data_scored_may21_v2.3.json')
v22_data  = load_json(r'C:\Users\34269\Documents\Claude\股票分析\代码文件\数据\data_scored_may21.json')
full22    = load_json(r'C:\Users\34269\Documents\Claude\股票分析\代码文件\数据\data_full_may22.bak')

# ─── 构建行情映射 code -> ChangePct ───────────────────────
change_map = {}
for s in full22['Stocks']:
    change_map[s['Code']] = s['ChangePct']

# ─── 辅助函数 ───────────────────────────────────────────────
def get_actual(stock):
    """获取股票次日实际涨跌幅"""
    c = stock['Code']
    return change_map.get(c, None)

def get_macd_status(macd_val):
    """将MACD_Status映射为中文类别"""
    if not macd_val:
        return 'unknown'
    macd_str = str(macd_val)
    if '多头' in macd_str or '金叉' in macd_str:
        return 'bullish'
    if '空头' in macd_str or '死叉' in macd_str:
        return 'bearish'
    return 'unknown'

def classify_trend_from_stock(stock):
    """从股票数据判断趋势，使用MACD_Status + MA关系"""
    macd = get_macd_status(stock.get('MACD_Status', ''))
    if macd == 'bullish':
        return 'up'
    if macd == 'bearish':
        return 'down'
    # 备选：使用MA关系
    ma5 = stock.get('MA5', 0)
    ma10 = stock.get('MA10', 0)
    ma20 = stock.get('MA20', 0)
    if ma5 and ma10 and ma20:
        if ma5 > ma10 > ma20:
            return 'up'
        elif ma5 < ma10 < ma20:
            return 'down'
    return 'sideways'

def classify_path_v2_from_stock(stock):
    """v1.5路径分类 - 使用MACD_Status + RSI + VolRatio值"""
    macd = stock.get('MACD_Status', '')
    macd_str = str(macd)
    rsi_val = stock.get('RSI', 50)
    if rsi_val is None:
        rsi_val = 50
    vol_ratio = stock.get('VolRatio', 1.0)
    if vol_ratio is None:
        vol_ratio = 1.0

    is_bull = '多头' in macd_str or '金叉' in macd_str
    is_bear = '空头' in macd_str
    is_deadcross = '死叉' in macd_str

    if is_bull and rsi_val >= 70 and vol_ratio >= 1.3:
        return 'chase_high'  # 追高（强势放量）
    elif is_bull and rsi_val < 70:
        return 'trend_up'  # 上升趋势
    elif is_deadcross:
        return 'dead_cross'  # 死叉
    elif is_bear and rsi_val <= 30:
        return 'oversold'  # 超卖反弹
    elif is_bear:
        return 'trend_down'  # 下降趋势
    else:
        return 'sideways'  # 震荡

def safe_div(a, b):
    if b == 0:
        return 0.0
    return a / b

def spearman_rho(ranks_x, ranks_y):
    """计算Spearman相关系数"""
    n = len(ranks_x)
    if n < 2:
        return 0.0
    # 计算排名差值
    d_sum = sum((rx - ry) ** 2 for rx, ry in zip(ranks_x, ranks_y))
    rho = 1 - 6 * d_sum / (n * (n * n - 1))
    return rho

def rank_list(values):
    """给列表中的值排名（相同值用平均排名）"""
    sorted_vals = sorted(enumerate(values), key=lambda x: x[1])
    ranks = [0] * len(values)
    i = 0
    while i < len(sorted_vals):
        j = i
        # 找相同值的组
        while j < len(sorted_vals) and sorted_vals[j][1] == sorted_vals[i][1]:
            j += 1
        avg_rank = (i + 1 + j) / 2
        for k in range(i, j):
            ranks[sorted_vals[k][0]] = avg_rank
        i = j
    return ranks

# ─── 解析v2.3数据 ───────────────────────────────────────────
v23_recs = v23_data['Recommendations']  # 25只推荐
v23_all  = v23_data['AllStocks']        # 72只全市场
v23_ves  = v23_data['VetoedStocks']     # 41只否决

print(f"[数据] v2.3: 推荐{len(v23_recs)}只, 全市场{len(v23_all)}只, 否决{len(v23_ves)}只")

# 构建v2.3全市场评分映射
v23_score_map = {}
for s in v23_all:
    v23_score_map[s['Code']] = s['TotalScore']

# ─── 获取实际收益 ───────────────────────────────────────────
v23_rec_actual = []
for r in v23_recs:
    actual = get_actual(r)
    if actual is not None:
        v23_rec_actual.append({'stock': r, 'actual': actual})

print(f"[数据] v2.3推荐池匹配到{len(v23_rec_actual)}只股票的实际行情")

v23_ves_actual = []
for v in v23_ves:
    actual = get_actual(v)
    if actual is not None:
        v23_ves_actual.append({'stock': v, 'actual': actual})

# 全市场
v23_market_actual = []
for s in v23_all:
    actual = get_actual(s)
    if actual is not None:
        v23_market_actual.append({'stock': s, 'actual': actual})

# ─── v2.2 同样处理 ─────────────────────────────────────────
v22_recs = v22_data['Recommendations']
v22_ves  = v22_data['VetoedStocks']
v22_all  = v22_data['AllStocks']

v22_rec_actual = []
for r in v22_recs:
    actual = get_actual(r)
    if actual is not None:
        v22_rec_actual.append({'stock': r, 'actual': actual})

v22_ves_actual = []
for v in v22_ves:
    actual = get_actual(v)
    if actual is not None:
        v22_ves_actual.append({'stock': v, 'actual': actual})

v22_market_actual = []
for s in v22_all:
    actual = get_actual(s)
    if actual is not None:
        v22_market_actual.append({'stock': s, 'actual': actual})

# ═══════════════════════════════════════════════════════════════
#  核心指标计算
# ═══════════════════════════════════════════════════════════════

def calc_metrics(rec_actual, veto_actual, market_actual, all_market, label=''):
    """计算所有评估指标"""
    m = {}

    # 1. 次日胜率
    winners = [x for x in rec_actual if x['actual'] > 0]
    m['win_rate'] = len(winners) / len(rec_actual) * 100 if rec_actual else 0
    m['win_count'] = len(winners)
    m['total_count'] = len(rec_actual)

    # 2. 组合次日收益
    avg_ret = sum(x['actual'] for x in rec_actual) / len(rec_actual) if rec_actual else 0
    m['avg_return'] = avg_ret

    # 3. 盈亏比
    total_profit = sum(x['actual'] for x in rec_actual if x['actual'] > 0)
    total_loss = sum(abs(x['actual']) for x in rec_actual if x['actual'] < 0)
    m['profit_loss_ratio'] = safe_div(total_profit, total_loss)
    m['total_profit'] = total_profit
    m['total_loss'] = total_loss

    # 4. 评分区分度(高/低分组)
    sorted_recs = sorted(rec_actual, key=lambda x: x['stock']['TotalScore'], reverse=True)
    mid = len(sorted_recs) // 2
    high_group = sorted_recs[:mid]
    low_group = sorted_recs[mid:]
    if len(sorted_recs) % 2 != 0:
        low_group = sorted_recs[mid+1:]  # 去掉中间一个

    high_win = sum(1 for x in high_group if x['actual'] > 0) / len(high_group) * 100 if high_group else 0
    low_win = sum(1 for x in low_group if x['actual'] > 0) / len(low_group) * 100 if low_group else 0
    high_avg = sum(x['actual'] for x in high_group) / len(high_group) if high_group else 0
    low_avg = sum(x['actual'] for x in low_group) / len(low_group) if low_group else 0

    m['high_win_rate'] = high_win
    m['low_win_rate'] = low_win
    m['high_avg_return'] = high_avg
    m['low_avg_return'] = low_avg
    m['score_discrimination'] = high_win - low_win

    # 5. 评分区分度(相对排名) - Spearman
    scores = [x['stock']['TotalScore'] for x in rec_actual]
    returns = [x['actual'] for x in rec_actual]
    score_ranks = rank_list(scores)
    ret_ranks = rank_list(returns)
    m['spearman_rho'] = spearman_rho(score_ranks, ret_ranks)

    # 6. 否决有效度 = 推荐池胜率 - 否决池胜率
    veto_winners = sum(1 for x in veto_actual if x['actual'] > 0)
    m['veto_win_rate'] = veto_winners / len(veto_actual) * 100 if veto_actual else 0
    m['veto_count'] = len(veto_actual)
    m['veto_effectiveness'] = m['win_rate'] - m['veto_win_rate']

    # 7. 否决误杀率 (涨>5%)
    false_killed = [x for x in veto_actual if x['actual'] > 5]
    m['false_kill_rate'] = len(false_killed) / len(veto_actual) * 100 if veto_actual else 0
    m['false_kill_count'] = len(false_killed)
    m['false_kill_list'] = false_killed

    # 8. 全市场基准胜率
    mkt_winners = sum(1 for x in market_actual if x['actual'] > 0)
    m['market_win_rate'] = mkt_winners / len(market_actual) * 100 if market_actual else 0
    m['market_avg_return'] = sum(x['actual'] for x in market_actual) / len(market_actual) if market_actual else 0

    # 9. 趋势区分度
    trend_map = {'up': [], 'down': [], 'sideways': [], 'unknown': []}
    for x in rec_actual:
        trend = classify_trend_from_stock(x['stock'])
        trend_map[trend].append(x['actual'])

    for t in trend_map:
        arr = trend_map[t]
        if arr:
            trend_map[t] = {
                'count': len(arr),
                'win_rate': sum(1 for v in arr if v > 0) / len(arr) * 100,
                'avg_ret': sum(arr) / len(arr)
            }
        else:
            trend_map[t] = {'count': 0, 'win_rate': 0, 'avg_ret': 0}

    m['trend'] = trend_map
    up_wr = trend_map['up']['win_rate'] if trend_map['up']['count'] > 0 else 0
    down_wr = trend_map['down']['win_rate'] if trend_map['down']['count'] > 0 else 0
    m['trend_discrimination'] = up_wr - down_wr

    # 10. 路径优选有效性
    path_map = {}
    for x in rec_actual:
        path = classify_path_v2_from_stock(x['stock'])
        if path not in path_map:
            path_map[path] = []
        path_map[path].append(x['actual'])

    path_stats = {}
    for p, arr in path_map.items():
        path_stats[p] = {
            'count': len(arr),
            'win_rate': sum(1 for v in arr if v > 0) / len(arr) * 100,
            'avg_ret': sum(arr) / len(arr)
        }
    m['path_stats'] = path_stats

    # 计算路径差异（最大胜率 - 最小胜率，排除unknown）
    valid_paths = {k: v for k, v in path_stats.items() if k != 'unknown' and v['count'] >= 3}
    if len(valid_paths) >= 2:
        wr_list = [v['win_rate'] for v in valid_paths.values()]
        m['path_discrimination'] = max(wr_list) - min(wr_list)
    else:
        m['path_discrimination'] = 0

    # 11-12. 维度相关系数 + 维度误判率
    dims = ['TotalScore', 'S_Tech', 'S_Money', 'S_Fund', 'S_News', 'S_Base', 'S_Risk']
    dim_names = {'TotalScore': '总分', 'S_Tech': '技术', 'S_Money': '资金',
                 'S_Fund': '基本面', 'S_News': '消息面', 'S_Base': '基础', 'S_Risk': '风控'}
    dim_thresholds = {'TotalScore': 70, 'S_Tech': 15, 'S_Money': 12, 'S_Fund': 12,
                      'S_News': 12, 'S_Base': 6, 'S_Risk': 3}

    # v1.5 动态基线 - 强势市场日(全市场平均>+2%)
    # 误判条件: 个股涨幅 < 全市场平均 - 3%
    mkt_avg = m['market_avg_return']
    is_strong_market = mkt_avg > 2.0
    misjudge_threshold = mkt_avg - 3.0  # 动态基线

    m['is_strong_market'] = is_strong_market
    m['misjudge_threshold'] = misjudge_threshold

    dim_corrs = {}
    dim_misjudge = {}

    for dim_key in dims:
        dim_name = dim_names.get(dim_key, dim_key)

        # 全市场Rho (使用所有72只)
        market_scores = [s['stock'][dim_key] if dim_key != 'TotalScore' else s['stock'].get('TotalScore', 0) for s in market_actual]
        market_rets = [s['actual'] for s in market_actual]

        # 对72只去重（有些股票可能在AllStocks重复）
        seen = set()
        unique_scores = []
        unique_rets = []
        for s_actual in market_actual:
            code = s_actual['stock']['Code']
            if code not in seen:
                seen.add(code)
                sc = s_actual['stock'][dim_key] if dim_key != 'TotalScore' else s_actual['stock'].get('TotalScore', 0)
                unique_scores.append(sc)
                unique_rets.append(s_actual['actual'])

        if len(unique_scores) >= 2:
            sr = rank_list(unique_scores)
            rr = rank_list(unique_rets)
            rho = spearman_rho(sr, rr)
        else:
            rho = 0
        dim_corrs[dim_name] = rho

        # 维度误判率 - 使用推荐池高分股票
        threshold = dim_thresholds.get(dim_key, 70) if dim_key != 'TotalScore' else 70
        # 对推荐池中该维度得高分者
        high_scorers = []
        for x in rec_actual:
            val = x['stock'][dim_key] if dim_key != 'TotalScore' else x['stock'].get('TotalScore', 0)
            if val >= threshold:
                high_scorers.append(x)

        if is_strong_market:
            # 强势市场日: 涨幅 < 全市场平均 - 3% 算误判
            misjudged = [x for x in high_scorers if x['actual'] < misjudge_threshold]
        else:
            # 正常日: 亏损 > 3% 算误判
            misjudged = [x for x in high_scorers if x['actual'] < -3]

        dim_misjudge[dim_name] = {
            'total': len(high_scorers),
            'misjudged': len(misjudged),
            'rate': len(misjudged) / len(high_scorers) * 100 if high_scorers else 0,
            'threshold': threshold,
            'misjudge_threshold_actual': misjudge_threshold if is_strong_market else -3
        }

    m['dim_correlations'] = dim_corrs
    m['dim_misjudge'] = dim_misjudge

    # 13. 各否决条件误杀
    veto_reason_stats = {}
    for x in veto_actual:
        v = x['stock']
        vr = v.get('VetoReason', '')
        if isinstance(vr, list):
            reason_key = '; '.join(vr)
        else:
            reason_key = str(vr)

        # 归类
        if '死叉' in reason_key or '均线死叉' in reason_key or 'MA10' in reason_key:
            category = '均线死叉'
        elif '回踩' in reason_key or 'MA5' in reason_key:
            category = '短期均线回踩'
        elif 'PE' in reason_key or '市盈率' in reason_key:
            if '泡沫' in reason_key:
                category = 'PE估值泡沫'
            else:
                category = 'PE过高'
        elif '涨幅' in reason_key or '30日涨幅' in reason_key:
            category = '短期涨幅过高'
        elif '异常' in reason_key or 'EPS' in reason_key:
            category = '基本面异常'
        else:
            category = '其他'

        if category not in veto_reason_stats:
            veto_reason_stats[category] = {'count': 0, 'total_ret': 0, 'false_kill_count': 0}
        veto_reason_stats[category]['count'] += 1
        veto_reason_stats[category]['total_ret'] += x['actual']
        if x['actual'] > 5:
            veto_reason_stats[category]['false_kill_count'] += 1

    for cat, st in veto_reason_stats.items():
        st['avg_ret'] = st['total_ret'] / st['count']
    m['veto_reason_stats'] = veto_reason_stats

    # 否决池平均收益
    veto_avg_ret = sum(x['actual'] for x in veto_actual) / len(veto_actual) if veto_actual else 0
    m['veto_avg_return'] = veto_avg_ret

    return m


# ═══════════════════════════════════════════════════════════════
#  计算 v2.3 和 v2.2 指标
# ═══════════════════════════════════════════════════════════════

m23 = calc_metrics(v23_rec_actual, v23_ves_actual, v23_market_actual, v23_all, 'v2.3')
m22 = calc_metrics(v22_rec_actual, v22_ves_actual, v22_market_actual, v22_all, 'v2.2')

# ═══════════════════════════════════════════════════════════════
#  输出核心指标对比
# ═══════════════════════════════════════════════════════════════

def fmt_pct(v, digits=1):
    if v is None or math.isnan(v):
        return 'N/A'
    return f'{v:+.{digits}f}%'

def fmt_val(v, digits=2):
    if v is None or math.isnan(v):
        return 'N/A'
    return f'{v:.{digits}f}'

def fmt_win(v):
    if v >= 60:
        return f'[OK] {v:.1f}%'
    elif v >= 50:
        return f'[WARN] {v:.1f}%'
    else:
        return f'[BAD] {v:.1f}%'

def fmt_rho(v):
    if v >= 0.2:
        return f'[OK] {v:.3f}'
    elif v >= 0.1:
        return f'[WARN] {v:.3f}'
    else:
        return f'[BAD] {v:.3f}'

print('\n' + '='*70)
print('  v2.3 评分引擎 × v1.5 后评估报告')
print('  评估对象：5月21日推荐 → 5月22日实际表现')
print('='*70)

print(f'\n{"指标":<24} {"v2.2":<16} {"v2.3":<16} {"变化":<16}')
print('-'*72)

# 1. 胜率
print(f'{"次日胜率":<18}', end=' ')
print(f'{fmt_win(m22["win_rate"]):<16}', end=' ')
print(f'{fmt_win(m23["win_rate"]):<16}', end=' ')
print(f'{m23["win_rate"] - m22["win_rate"]:+.1f}%')

# 2. 组合收益
print(f'{"组合次日收益":<18}', end=' ')
print(f'{fmt_pct(m22["avg_return"]):<16}', end=' ')
print(f'{fmt_pct(m23["avg_return"]):<16}', end=' ')
print(f'{m23["avg_return"] - m22["avg_return"]:+.2f}%')

# 3. 盈亏比
print(f'{"盈亏比":<18}', end=' ')
print(f'{fmt_val(m22["profit_loss_ratio"]):<16}', end=' ')
print(f'{fmt_val(m23["profit_loss_ratio"]):<16}', end=' ')
print(f'{m23["profit_loss_ratio"] - m22["profit_loss_ratio"]:+.2f}')

# 4. 评分区分度
print(f'{"评分区分度(高/低)":<18}', end=' ')
print(f'{fmt_pct(m22["score_discrimination"]):<16}', end=' ')
print(f'{fmt_pct(m23["score_discrimination"]):<16}', end=' ')
print(f'{m23["score_discrimination"] - m22["score_discrimination"]:+.1f}%')

# 5. Spearman Rho
print(f'{"评分区分度(Spearman)":<18}', end=' ')
print(f'{fmt_rho(m22["spearman_rho"]):<16}', end=' ')
print(f'{fmt_rho(m23["spearman_rho"]):<16}', end=' ')
print(f'{m23["spearman_rho"] - m22["spearman_rho"]:+.3f}')

# 6. 否决有效度
print(f'{"否决有效度":<18}', end=' ')
print(f'{fmt_pct(m22["veto_effectiveness"]):<16}', end=' ')
print(f'{fmt_pct(m23["veto_effectiveness"]):<16}', end=' ')
print(f'{m23["veto_effectiveness"] - m22["veto_effectiveness"]:+.1f}%')

# 7. 否决误杀率
print(f'{"否决误杀率":<18}', end=' ')
print(f'{fmt_pct(m22["false_kill_rate"]):<16}', end=' ')
print(f'{fmt_pct(m23["false_kill_rate"]):<16}', end=' ')
print(f'{m23["false_kill_rate"] - m22["false_kill_rate"]:+.1f}%')

# 8. 市场基准
print(f'{"全市场基准胜率":<18}', end=' ')
print(f'{fmt_win(m22["market_win_rate"]):<16}', end=' ')
print(f'{fmt_win(m23["market_win_rate"]):<16}', end=' ')
print(f'{m23["market_win_rate"] - m22["market_win_rate"]:+.1f}%')

# 9. 趋势区分度
print(f'{"趋势区分度":<18}', end=' ')
print(f'{fmt_pct(m22["trend_discrimination"]):<16}', end=' ')
print(f'{fmt_pct(m23["trend_discrimination"]):<16}', end=' ')
print(f'{m23["trend_discrimination"] - m22["trend_discrimination"]:+.1f}%')

# 10. 路径区分度
print(f'{"路径优选有效性":<18}', end=' ')
print(f'{fmt_pct(m22["path_discrimination"]):<16}', end=' ')
print(f'{fmt_pct(m23["path_discrimination"]):<16}', end=' ')
print(f'{m23["path_discrimination"] - m22["path_discrimination"]:+.1f}%')

print(f'\n--- v2.3 详细数据 ---')
print(f'推荐池: {m23["win_count"]}/{m23["total_count"]} 只上涨, 胜率 {m23["win_rate"]:.1f}%')
print(f'推荐池平均收益: {m23["avg_return"]:+.2f}%')
print(f'否决池: {m23["veto_count"]}只, 胜率 {m23["veto_win_rate"]:.1f}%, 平均收益 {m23["veto_avg_return"]:+.2f}%')
print(f'否决有效度: {m23["veto_effectiveness"]:+.1f}%')
print(f'否决误杀率: {m23["false_kill_rate"]:.1f}% ({m23["false_kill_count"]}只涨>5%被误杀)')
print(f'全市场: {m23["market_win_rate"]:.1f}% 胜率, 平均 {m23["market_avg_return"]:+.2f}%')
print(f'大盘状态: {"强势市场日" if m23["is_strong_market"] else "正常"} (全市场平均 {m23["market_avg_return"]:+.2f}%)')
print(f'动态误判基线: 涨跌幅 < {m23["misjudge_threshold"]:+.2f}%')

print(f'\n--- 评分区分度 ---')
print(f'高分组(前{len(v23_rec_actual)//2}只): 胜率 {m23["high_win_rate"]:.1f}%, 平均 {m23["high_avg_return"]:+.2f}%')
print(f'低分组(后{len(v23_rec_actual)//2}只): 胜率 {m23["low_win_rate"]:.1f}%, 平均 {m23["low_avg_return"]:+.2f}%')
print(f'区分度: {m23["score_discrimination"]:+.1f}%')
print(f'Spearman Rho: {m23["spearman_rho"]:.3f}')

print(f'\n--- 趋势分析 ---')
for t, st in sorted(m23['trend'].items()):
    if st['count'] > 0:
        print(f'  {t}: {st["count"]}只, 胜率 {st["win_rate"]:.1f}%, 平均 {st["avg_ret"]:+.2f}%')

print(f'\n--- 路径分析 ---')
for p, st in sorted(m23['path_stats'].items()):
    if st['count'] > 0:
        print(f'  {p}: {st["count"]}只, 胜率 {st["win_rate"]:.1f}%, 平均 {st["avg_ret"]:+.2f}%')

print(f'\n--- 维度相关系数 (Spearman Rho) ---')
for dim_name, rho in m23['dim_correlations'].items():
    print(f'  {dim_name}: {rho:+.3f}')

print(f'\n--- 维度误判率 (v1.5动态基线) ---')
print(f'  强势市场日基线: 涨跌幅 < {m23["misjudge_threshold"]:+.2f}% (=全市场平均{m23["market_avg_return"]:+.2f}% - 3%)')
for dim_name, st in m23['dim_misjudge'].items():
    print(f'  {dim_name}(>={st["threshold"]}): {st["misjudged"]}/{st["total"]} = {st["rate"]:.1f}%')

print(f'\n--- 否决规则诊断 ---')
for cat, st in sorted(m23['veto_reason_stats'].items()):
    print(f'  {cat}: {st["count"]}只, 平均收益 {st["avg_ret"]:+.2f}%, 误杀{st["false_kill_count"]}只')

print(f'\n--- v2.2 vs v2.3 关键对比 ---')
# 盈利提升
print(f'推荐池收益: v2.2 {m22["avg_return"]:+.2f}% -> v2.3 {m23["avg_return"]:+.2f}%')
print(f'否决误杀: v2.2 {m22["false_kill_rate"]:.1f}% ({m22["false_kill_count"]}只) -> v2.3 {m23["false_kill_rate"]:.1f}% ({m23["false_kill_count"]}只)')
print(f'否决有效度: v2.2 {m22["veto_effectiveness"]:+.1f}% -> v2.3 {m23["veto_effectiveness"]:+.1f}%')

# ═══════════════════════════════════════════════════════════════
#  HTML报告
# ═══════════════════════════════════════════════════════════════

def badge_class(val, good_thresh, warn_thresh=None):
    """根据阈值返回badge样式"""
    if warn_thresh is None:
        warn_thresh = good_thresh * 0.7
    if val >= good_thresh:
        return 'badge-ok'
    elif val >= warn_thresh:
        return 'badge-warn'
    else:
        return 'badge-danger'

def val_class(val, invert=False):
    """返回数值CSS class"""
    if invert:
        if val <= 15:
            return 'success'
        elif val <= 30:
            return 'warn'
        else:
            return 'danger'
    else:
        if val >= 60:
            return 'success'
        elif val >= 50:
            return 'warn'
        else:
            return 'danger'

def rho_class(v):
    if v >= 0.2:
        return 'success'
    elif v >= 0.1:
        return 'warn'
    else:
        return 'danger'

def fmt_ret(v):
    if v > 0:
        return f'<span class="up">+{v:.2f}%</span>'
    elif v < 0:
        return f'<span class="down">{v:.2f}%</span>'
    else:
        return f'<span class="flat">0.00%</span>'

def fmt_ret_raw(v):
    if v > 0:
        return f'+{v:.2f}%'
    elif v < 0:
        return f'{v:.2f}%'
    else:
        return '0.00%'

# 生成逐股明细表
def gen_stock_table(rec_actual):
    rows = ''
    for i, x in enumerate(rec_actual):
        s = x['stock']
        ret = x['actual']
        tr_class = 'top1' if i == 0 else ('top3' if i < 3 else '')
        tech = s.get('TechAnalysis', '')
        # 使用MACD_Status字段
        macd_raw = str(s.get('MACD_Status', ''))
        if '多头' in macd_raw: macd = '多头'
        elif '金叉' in macd_raw: macd = '金叉'
        elif '空头' in macd_raw: macd = '空头'
        elif '死叉' in macd_raw: macd = '死叉'
        else: macd = '--'

        rsi_s = str(s.get('RSI', '--'))

        path = classify_path_v2_from_stock(s)
        path_cn = {'chase_high': '追高', 'trend_up': '上升趋势', 'dead_cross': '死叉',
                   'oversold': '超卖', 'trend_down': '下降趋势', 'sideways': '震荡', 'unknown': '未知'}

        rows += f'''<tr class="{tr_class}">
    <td>{i+1}</td>
    <td>{s['Code']}</td>
    <td style="text-align:left">{s['Name']}</td>
    <td>{s['TotalScore']}</td>
    <td>{s.get('S_Tech', '--')}</td>
    <td>{s.get('S_Money', '--')}</td>
    <td>{s.get('S_Fund', '--')}</td>
    <td>{macd}</td>
    <td>{rsi_s}</td>
    <td>{fmt_ret(ret)}</td>
    <td style="font-size:11px">{path_cn.get(path, path)}</td>
  </tr>'''
    return rows

# 生成误杀明细表
def gen_false_kill_table(false_killed):
    rows = ''
    for x in false_killed:
        s = x['stock']
        vr = s.get('VetoReason', '')
        if isinstance(vr, list):
            vr_str = '; '.join(vr)
        else:
            vr_str = str(vr)
        # 截断过长的理由
        if len(vr_str) > 50:
            vr_str = vr_str[:50] + '...'
        rows += f'''<tr>
    <td>{s['Code']}</td>
    <td style="text-align:left">{s['Name']}</td>
    <td>{s['TotalScore']}</td>
    <td style="text-align:left;font-size:11px;color:#888">{vr_str}</td>
    <td>{fmt_ret(x['actual'])}</td>
  </tr>'''
    return rows

# 生成维度相关系数HTML
def gen_corr_grid(dim_corrs):
    items = ''
    for dim_name, rho in dim_corrs.items():
        items += f'''<div class="corr-item"><div class="dim">{dim_name}</div><div class="rho {rho_class(rho)}">{rho:+.3f}</div></div>\n'''
    return items

# 生成维度误判表
def gen_misjudge_table(dim_misjudge, is_strong, threshold_display):
    rows = ''
    for dim_name, st in dim_misjudge.items():
        rate = st['rate']
        if rate <= 10:
            badge = '<span class="badge badge-ok">优秀</span>'
        elif rate <= 20:
            badge = '<span class="badge badge-warn">关注</span>'
        else:
            badge = '<span class="badge badge-danger">超标</span>'

        threshold_label = f'<{threshold_display:.1f}%' if is_strong else '<-3%'
        rows += f'''<tr>
    <td>{dim_name}</td>
    <td>>={st["threshold"]}</td>
    <td>{st["total"]}</td>
    <td>{st["misjudged"]}</td>
    <td>{rate:.1f}%</td>
    <td>{badge}</td>
  </tr>'''
    return rows

import datetime
gen_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')

# 生成趋势bar图
def gen_trend_chart(trend_data):
    bars = ''
    colors = {'up': '#27ae60', 'down': '#e74c3c', 'sideways': '#f39c12', 'unknown': '#95a5a6'}
    labels = {'up': '上升趋势', 'down': '下降趋势', 'sideways': '震荡', 'unknown': '未知'}
    max_count = max((v['count'] for v in trend_data.values()), default=1)
    if max_count == 0:
        max_count = 1

    for t in ['up', 'down', 'sideways', 'unknown']:
        v = trend_data.get(t, {'count': 0, 'avg_ret': 0})
        h = max(v['count'] / max_count * 120, 4)
        bars += f'''<div class="chart-bar" style="height:{h}px;background:{colors.get(t, '#95a5a6')}"><div class="chg">{v["avg_ret"]:+.1f}%</div><div class="label">{labels.get(t, t)} ({v["count"]})</div></div>\n'''
    return bars

# 生成路径bar图
def gen_path_chart(path_stats):
    bars = ''
    colors_list = ['#3498db', '#2ecc71', '#e67e22', '#9b59b6', '#1abc9c', '#e74c3c', '#95a5a6']
    labels_cn = {'chase_high': '追高', 'trend_up': '上升趋势', 'dead_cross': '死叉',
                 'oversold': '超卖', 'trend_down': '下降趋势', 'sideways': '震荡', 'unknown': '未知'}
    max_count = max((v['count'] for v in path_stats.values()), default=1)
    if max_count == 0:
        max_count = 1

    for i, (p, v) in enumerate(sorted(path_stats.items())):
        h = max(v['count'] / max_count * 120, 4)
        c = colors_list[i % len(colors_list)]
        bars += f'''<div class="chart-bar" style="height:{h}px;background:{c}"><div class="chg">{v["avg_ret"]:+.1f}%</div><div class="label">{labels_cn.get(p, p)} ({v["count"]})</div></div>\n'''
    return bars

# 构建否决池平均收益与推荐池对比行
veto_vs_rec = f'''
<tr><td style="text-align:left;font-weight:bold">推荐池(25只)</td><td>25</td><td>{fmt_ret(m23["avg_return"])}</td><td>{m23["win_count"]}</td><td>{m23["win_rate"]:.1f}%</td><td>-</td></tr>
<tr><td style="text-align:left;font-weight:bold">否决池(41只)</td><td>41</td><td>{fmt_ret(m23["veto_avg_return"])}</td><td>{sum(1 for x in v23_ves_actual if x["actual"] > 0)}</td><td>{m23["veto_win_rate"]:.1f}%</td><td>{m23["false_kill_count"]}</td></tr>
'''

# 构建否决规则诊断表
veto_reason_rows = ''
for cat, st in sorted(m23['veto_reason_stats'].items()):
    veto_reason_rows += f'''<tr>
    <td style="text-align:left;font-size:11px">{cat}</td>
    <td>{st["count"]}</td>
    <td>{fmt_ret(st["avg_ret"])}</td>
    <td>{st["false_kill_count"]}</td>
  </tr>'''

# 诊断发现
findings = []

# 1. 整体胜率
if m23['win_rate'] >= 60:
    findings.append((f'整体胜率 {m23["win_rate"]:.1f}% -- 达标',
                     f'组合收益 {m23["avg_return"]:+.2f}%，盈亏比 {m23["profit_loss_ratio"]:.2f}:1，盈利 {m23["win_count"]}只 / 亏损 {m23["total_count"] - m23["win_count"]}只'))
else:
    findings.append((f'整体胜率 {m23["win_rate"]:.1f}% -- 未达标',
                     f'目标>=60%，组合收益 {m23["avg_return"]:+.2f}%'))

# 2. 评分区分度
if abs(m23['score_discrimination']) >= 15:
    findings.append((f'评分区分度(高/低分组) {m23["score_discrimination"]:+.1f}% -- 达标',
                     f'高分组胜率 {m23["high_win_rate"]:.1f}% (收益 {m23["high_avg_return"]:+.2f}%) | 低分组胜率 {m23["low_win_rate"]:.1f}% (收益 {m23["low_avg_return"]:+.2f}%)'))
elif m23['score_discrimination'] < 0:
    findings.append((f'评分区分度(高/低分组) {m23["score_discrimination"]:+.1f}% -- 反向',
                     f'高分组胜率 {m23["high_win_rate"]:.1f}% (收益 {m23["high_avg_return"]:+.2f}%) 低于 低分组胜率 {m23["low_win_rate"]:.1f}% (收益 {m23["low_avg_return"]:+.2f}%)'))
else:
    findings.append((f'评分区分度(高/低分组) {m23["score_discrimination"]:+.1f}% -- 不足',
                     f'目标>=15%，高分组胜率 {m23["high_win_rate"]:.1f}% (收益 {m23["high_avg_return"]:+.2f}%) | 低分组胜率 {m23["low_win_rate"]:.1f}% (收益 {m23["low_avg_return"]:+.2f}%)'))

# 3. Spearman
if m23['spearman_rho'] >= 0.2:
    findings.append((f'评分区分度(相对排名) Spearman={m23["spearman_rho"]:.3f} -- 达标',
                     f'目标>0.2，评分排序与涨跌幅排序存在正向关联'))
elif m23['spearman_rho'] >= 0:
    findings.append((f'评分区分度(相对排名) Spearman={m23["spearman_rho"]:.3f} -- 弱相关',
                     f'目标>0.2，当前相关性较弱'))
else:
    findings.append((f'评分区分度(相对排名) Spearman={m23["spearman_rho"]:.3f} -- 负相关',
                     f'评分越高反而收益越低'))

# 4. 维度相关性
best_dim = max(m23['dim_correlations'], key=lambda k: m23['dim_correlations'][k])
worst_dim = min(m23['dim_correlations'], key=lambda k: m23['dim_correlations'][k])
corr_str = ' | '.join([f'{k}: {v:+.3f}' for k, v in m23['dim_correlations'].items()])
findings.append((f'维度相关性：{best_dim}最高 ({m23["dim_correlations"][best_dim]:+.3f})，{worst_dim}最低 ({m23["dim_correlations"][worst_dim]:+.3f})',
                 corr_str))

# 5. 维度误判率
misjudge_items = []
for dim_name, st in m23['dim_misjudge'].items():
    misjudge_items.append(f'{dim_name}: {st["rate"]:.1f}%({st["misjudged"]}/{st["total"]})')
findings.append((f'维度误判率分析 (v1.5动态基线: {"强势市场日" if m23["is_strong_market"] else "正常日"}, 阈值<{m23["misjudge_threshold"]:+.2f}%)',
                 ' | '.join(misjudge_items)))

# 6. 否决
findings.append((f'否决有效度 {m23["veto_effectiveness"]:+.1f}% -- {"达标" if m23["veto_effectiveness"] >= 20 else "需关注" if m23["veto_effectiveness"] >= 0 else "反向"}',
                 f'否决池胜率 {m23["veto_win_rate"]:.1f}% | 误杀率 {m23["false_kill_rate"]:.1f}% ({m23["false_kill_count"]}只涨>5%被误杀) | 全市场基准胜率 {m23["market_win_rate"]:.1f}%'))

# 7. 路径
findings.append((f'路径优选有效性 {m23["path_discrimination"]:+.1f}% -- {"达标" if m23["path_discrimination"] >= 15 else "区分度不足"}',
                 ' | '.join([f'{k}: {v["win_rate"]:.0f}%({v["count"]}只,{v["avg_ret"]:+.2f}%)' for k, v in sorted(m23['path_stats'].items())])))

# 8. 趋势
findings.append((f'上升/下降趋势区分度 {m23["trend_discrimination"]:+.1f}% -- {"达标" if m23["trend_discrimination"] >= 10 else "不足"}',
                 f'上升趋势 {m23["trend"]["up"]["count"]}只, 胜率 {m23["trend"]["up"]["win_rate"]:.1f}% | 下降趋势 {m23["trend"]["down"]["count"]}只, 胜率 {m23["trend"]["down"]["win_rate"]:.1f}%'))

# 9. v2.2 vs v2.3 对比发现
findings.append((f'v2.2 vs v2.3 对比',
                 f'推荐池收益: {m22["avg_return"]:+.2f}% -> {m23["avg_return"]:+.2f}% ({m23["avg_return"] - m22["avg_return"]:+.2f}%) | '
                 f'胜率: {m22["win_rate"]:.1f}% -> {m23["win_rate"]:.1f}% ({m23["win_rate"] - m22["win_rate"]:+.1f}%) | '
                 f'Spearman: {m22["spearman_rho"]:.3f} -> {m23["spearman_rho"]:.3f} | '
                 f'否决误杀: {m22["false_kill_rate"]:.1f}% -> {m23["false_kill_rate"]:.1f}%'))

# 优化建议
suggestions = []

# 分析需要优化的方面
if abs(m23['spearman_rho']) < 0.2:
    suggestions.append(('P1', '总分与次日收益相关性不足(Spearman={:.3f})'.format(m23['spearman_rho']),
     '建议审查总分合成逻辑。当前各维度权重是否合理？分析各维度rho发现：' +
     ' | '.join([f'{k}({v:+.3f})' for k, v in sorted(m23['dim_correlations'].items(), key=lambda x: abs(x[1]), reverse=True)]),
     '高 -- 修复可提升评分整体区分度'))

if m23['false_kill_rate'] > 15:
    suggestions.append(('P1', '否决误杀率 {:.1f}% 超过15%阈值'.format(m23['false_kill_rate']),
     '审查被误杀股票({}只涨>5%)的共同否决条件。特别关注"短期均线回踩"条件——在强势股短暂回调时会被触发，但未必是真回调。建议：(1) 增加MA20趋势方向判断(向上时放宽回踩否决)；(2) 结合量能判断，缩量回调应豁免。'.format(m23['false_kill_count']),
     '高 -- 减少误杀可提高推荐池质量'))

if m23['score_discrimination'] < 15:
    suggestions.append(('P2', '评分区分度(高/低分组) {:.1f}% < 15%'.format(m23['score_discrimination']),
     '当前高分半区和低分半区区分度不足，Spearman相关系数仅{:.3f}。建议：(1) 扩大评分范围，增加极端高分(>90)和极端低分(<30)的分布；(2) 各维度使用非线性映射，让高分更难获得；(3) 引入更多区分性因子。'.format(m23['spearman_rho']),
     '中 -- 改善后可更好识别优质股'))

if m23['path_discrimination'] < 15:
    suggestions.append(('P2', '路径优选有效性 {:.1f}% < 15%'.format(m23['path_discrimination']),
     '各路径区分度不足，无法根据不同市场状态选择最优路径。建议：(1) 追高路径增加放量条件；(2) 不同路径使用不同的评分权重组合；(3) 增加路径切换的市场状态判断。',
     '中 -- 长期可提升场景适应性'))

if m23['veto_effectiveness'] < 0:
    suggestions.append(('P1', '否决有效度为负值({:.1f}%)，否决池表现优于推荐池'.format(m23['veto_effectiveness']),
     '否决规则过于严格，误杀了大量本应入选的优质股。建议：(1) 优先降低误杀率最高的否决条件阈值；(2) 增加豁免条件覆盖范围；(3) 考虑对部分否决条件使用更宽松的标准。',
     '高 -- 当前否决规则严重损害推荐池质量'))

# HTML生成
css_content = load_css()
html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>v2.3 评分引擎 × v1.5 后评估报告</title>
<style>
{css_content}
</style>
</head>
<body>
<div class="page">

<h1>v2.3 评分引擎 × v1.5 后评估报告</h1>
<div class="subtitle">评估对象：5月21日推荐(25只) → 5月22日实际表现 | 生成时间：{gen_time}</div>

<div style="font-size:12px;color:#666;margin-bottom:15px;padding:8px 12px;background:#e8f4fd;border-radius:4px;">
<b>大盘环境：</b>5月22日全市场等权平均 <b>{m23["market_avg_return"]:+.2f}%</b>（{"强势市场日" if m23["is_strong_market"] else "正常日"}）
| 维度误判基线：v1.5动态阈值 < {m23["misjudge_threshold"]:+.2f}%（={m23["market_avg_return"]:+.2f}% - 3%）
</div>

<!-- 核心指标卡片 -->
<div class="metrics">
  <div class="metric">
    <div class="label">次日胜率</div>
    <div class="val {val_class(m23['win_rate'])}">{m23["win_rate"]:.1f}%</div>
    <div class="sub">{m23["win_count"]}/{m23["total_count"]}</div>
  </div>
  <div class="metric">
    <div class="label">组合次日收益</div>
    <div class="val {val_class(m23['avg_return'] + 100)}">{m23["avg_return"]:+.2f}%</div>
  </div>
  <div class="metric">
    <div class="label">盈亏比</div>
    <div class="val {"success" if m23["profit_loss_ratio"] >= 1.5 else "warn"}">{m23["profit_loss_ratio"]:.2f}</div>
    <div class="sub">目标≥1.5</div>
  </div>
  <div class="metric">
    <div class="label">评分区分度(高/低)</div>
    <div class="val {val_class(abs(m23['score_discrimination']), False)}">{m23["score_discrimination"]:+.1f}%</div>
    <div class="sub">目标≥15%</div>
  </div>
  <div class="metric">
    <div class="label">Spearman Rho</div>
    <div class="val {rho_class(m23['spearman_rho'])}">{m23["spearman_rho"]:.3f}</div>
    <div class="sub">目标>0.2 (v1.5新增)</div>
  </div>
  <div class="metric">
    <div class="label">否决有效度</div>
    <div class="val {val_class(m23['veto_effectiveness'] + 100)}">{m23["veto_effectiveness"]:+.1f}%</div>
    <div class="sub">推荐-否决胜率差</div>
  </div>
  <div class="metric">
    <div class="label">否决误杀率</div>
    <div class="val {"danger" if m23["false_kill_rate"] > 15 else "warn" if m23["false_kill_rate"] > 10 else "success"}">{m23["false_kill_rate"]:.1f}%</div>
    <div class="sub">{m23["false_kill_count"]}只涨>5%被误杀</div>
  </div>
  <div class="metric">
    <div class="label">全市场基准胜率</div>
    <div class="val">{m23["market_win_rate"]:.1f}%</div>
    <div class="sub">72只平均 {m23["market_avg_return"]:+.2f}%</div>
  </div>
  <div class="metric">
    <div class="label">趋势区分度</div>
    <div class="val {val_class(abs(m23['trend_discrimination']), False)}">{m23["trend_discrimination"]:+.1f}%</div>
    <div class="sub">目标≥10%</div>
  </div>
  <div class="metric">
    <div class="label">路径优选有效性</div>
    <div class="val {val_class(abs(m23['path_discrimination']), False)}">{m23["path_discrimination"]:+.1f}%</div>
    <div class="sub">目标≥15%</div>
  </div>
</div>

<!-- v2.2 vs v2.3 对比表 -->
<h2>v2.2 vs v2.3 核心指标对比</h2>
<table>
<tr><th>指标</th><th>目标</th><th>v2.2 (5月21日)</th><th>v2.3 (5月21日)</th><th>变化</th><th>判定</th></tr>
<tr>
  <td style="text-align:left">次日胜率</td>
  <td>≥60%</td>
  <td>{m22["win_rate"]:.1f}%</td>
  <td>{m23["win_rate"]:.1f}%</td>
  <td class="{"compare-up" if m23["win_rate"] >= m22["win_rate"] else "compare-down"}">{m23["win_rate"] - m22["win_rate"]:+.1f}%</td>
  <td><span class="badge {"badge-ok" if m23["win_rate"] >= 60 else "badge-warn" if m23["win_rate"] >= 50 else "badge-danger"}">{m23["win_rate"]:.1f}%</span></td>
</tr>
<tr>
  <td style="text-align:left">组合次日收益</td>
  <td>>0%</td>
  <td>{m22["avg_return"]:+.2f}%</td>
  <td>{m23["avg_return"]:+.2f}%</td>
  <td class="{"compare-up" if m23["avg_return"] >= m22["avg_return"] else "compare-down"}">{m23["avg_return"] - m22["avg_return"]:+.2f}%</td>
  <td><span class="badge {"badge-ok" if m23["avg_return"] > 0 else "badge-danger"}">{m23["avg_return"]:+.2f}%</span></td>
</tr>
<tr>
  <td style="text-align:left">盈亏比</td>
  <td>≥1.5</td>
  <td>{m22["profit_loss_ratio"]:.2f}</td>
  <td>{m23["profit_loss_ratio"]:.2f}</td>
  <td class="{"compare-up" if m23["profit_loss_ratio"] >= m22["profit_loss_ratio"] else "compare-down"}">{m23["profit_loss_ratio"] - m22["profit_loss_ratio"]:+.2f}</td>
  <td><span class="badge {"badge-ok" if m23["profit_loss_ratio"] >= 1.5 else "badge-warn"}">{m23["profit_loss_ratio"]:.2f}</span></td>
</tr>
<tr>
  <td style="text-align:left">评分区分度(高/低)</td>
  <td>≥15%</td>
  <td>{m22["score_discrimination"]:+.1f}%</td>
  <td>{m23["score_discrimination"]:+.1f}%</td>
  <td class="{"compare-up" if m23["score_discrimination"] >= m22["score_discrimination"] else "compare-down"}">{m23["score_discrimination"] - m22["score_discrimination"]:+.1f}%</td>
  <td><span class="badge {"badge-ok" if abs(m23["score_discrimination"]) >= 15 else "badge-warn" if m23["score_discrimination"] >= 0 else "badge-danger"}">{m23["score_discrimination"]:+.1f}%</span></td>
</tr>
<tr>
  <td style="text-align:left">Spearman Rho</td>
  <td>>0.2</td>
  <td>{m22["spearman_rho"]:.3f}</td>
  <td>{m23["spearman_rho"]:.3f}</td>
  <td class="{"compare-up" if m23["spearman_rho"] >= m22["spearman_rho"] else "compare-down"}">{m23["spearman_rho"] - m22["spearman_rho"]:+.3f}</td>
  <td><span class="badge {"badge-ok" if m23["spearman_rho"] >= 0.2 else "badge-warn" if m23["spearman_rho"] >= 0 else "badge-danger"}">{m23["spearman_rho"]:.3f}</span></td>
</tr>
<tr>
  <td style="text-align:left">否决有效度</td>
  <td>≥20%</td>
  <td>{m22["veto_effectiveness"]:+.1f}%</td>
  <td>{m23["veto_effectiveness"]:+.1f}%</td>
  <td class="{"compare-up" if m23["veto_effectiveness"] >= m22["veto_effectiveness"] else "compare-down"}">{m23["veto_effectiveness"] - m22["veto_effectiveness"]:+.1f}%</td>
  <td><span class="badge {"badge-ok" if m23["veto_effectiveness"] >= 20 else "badge-warn" if m23["veto_effectiveness"] >= 0 else "badge-danger"}">{m23["veto_effectiveness"]:+.1f}%</span></td>
</tr>
<tr>
  <td style="text-align:left">否决误杀率</td>
  <td>≤15%</td>
  <td>{m22["false_kill_rate"]:.1f}%</td>
  <td>{m23["false_kill_rate"]:.1f}%</td>
  <td class="{"compare-up" if m23["false_kill_rate"] <= m22["false_kill_rate"] else "compare-down"}">{m23["false_kill_rate"] - m22["false_kill_rate"]:+.1f}%</td>
  <td><span class="badge {"badge-ok" if m23["false_kill_rate"] <= 15 else "badge-warn" if m23["false_kill_rate"] <= 30 else "badge-danger"}">{m23["false_kill_rate"]:.1f}%</span></td>
</tr>
<tr>
  <td style="text-align:left">趋势区分度</td>
  <td>≥10%</td>
  <td>{m22["trend_discrimination"]:+.1f}%</td>
  <td>{m23["trend_discrimination"]:+.1f}%</td>
  <td class="{"compare-up" if m23["trend_discrimination"] >= m22["trend_discrimination"] else "compare-down"}">{m23["trend_discrimination"] - m22["trend_discrimination"]:+.1f}%</td>
  <td><span class="badge {"badge-ok" if m23["trend_discrimination"] >= 10 else "badge-warn"}">{m23["trend_discrimination"]:+.1f}%</span></td>
</tr>
<tr>
  <td style="text-align:left">路径优选有效性</td>
  <td>≥15%</td>
  <td>{m22["path_discrimination"]:+.1f}%</td>
  <td>{m23["path_discrimination"]:+.1f}%</td>
  <td class="{"compare-up" if m23["path_discrimination"] >= m22["path_discrimination"] else "compare-down"}">{m23["path_discrimination"] - m22["path_discrimination"]:+.1f}%</td>
  <td><span class="badge {"badge-ok" if m23["path_discrimination"] >= 15 else "badge-warn"}">{m23["path_discrimination"]:+.1f}%</span></td>
</tr>
</table>

<!-- 维度相关系数 -->
<h2>维度相关系数（Spearman ρ） — 全市场72只</h2>
<div class="corr-grid">
{gen_corr_grid(m23['dim_correlations'])}
</div>

<!-- 维度误判率(v1.5动态基线) -->
<h2>维度误判率（v1.5动态基线）</h2>
<div style="font-size:12px;color:#666;margin-bottom:8px;padding:6px 10px;background:#fff3cd;border-radius:4px;">
<b>动态基线说明：</b>{"强势市场日(全市场平均>{:.1f}%)，误判需跑输大盘>3%" if m23["is_strong_market"] else "正常日，误判标准为亏损>3%"}<br>
<b>当日全市场平均：</b>{m23["market_avg_return"]:+.2f}% → 误判阈值：涨跌幅 < {m23["misjudge_threshold"]:+.2f}%
</div>
<table>
<tr><th>维度</th><th>高分阈值</th><th>高分总次数</th><th>误判次数</th><th>误判率</th><th>判定</th></tr>
{gen_misjudge_table(m23['dim_misjudge'], m23['is_strong_market'], m23['misjudge_threshold'])}
</table>

<!-- 否决规则诊断 -->
<h2>否决规则诊断</h2>
<h3>否决池 vs 推荐池</h3>
<table>
<tr><th>池</th><th>股票数</th><th>平均收益</th><th>上涨只数</th><th>胜率</th><th>误杀(>5%)</th></tr>
{veto_vs_rec}
</table>

<h3>按否决条件分类</h3>
<table>
<tr><th>否决条件</th><th>股票数</th><th>平均收益</th><th>误杀(>5%)</th></tr>
{veto_reason_rows}
</table>

<h3>误杀明细（否决池涨>5%的股票）</h3>
<table>
<tr><th>代码</th><th>名称</th><th>评分</th><th>否决原因</th><th>次日涨跌</th></tr>
{gen_false_kill_table(m23['false_kill_list'])}
</table>

<!-- 趋势分析 -->
<h2>趋势分析</h2>
<div class="chart">
{gen_trend_chart(m23['trend'])}
</div>

<!-- 路径分析 -->
<h2>路径分析</h2>
<div class="chart">
{gen_path_chart(m23['path_stats'])}
</div>

<!-- 诊断发现 -->
<h2>诊断发现</h2>
<ul class="findings-list">
'''
for title, detail in findings:
    html += f'<li><div class="f-title">{title}</div><div class="f-detail">{detail}</div></li>\n'

html += '''
</ul>

<!-- 优化建议 -->
<h2>优化建议</h2>
'''
for prio, title, detail, impact in suggestions:
    html += f'''<div class="suggestion {prio.lower()}"><div><span class="s-prio {prio.lower()}">{prio}</span><b>{title}</b></div><p style="font-size:12px;color:#555;margin:8px 0;line-height:1.6">{detail}</p><p style="font-size:11px;color:#888">影响评估：{impact}</p></div>\n'''

# 逐股明细
html += f'''
<h2>逐股明细（按评分降序）</h2>
<table>
<tr><th>#</th><th>代码</th><th>名称</th><th>总分</th><th>技术</th><th>资金</th><th>基本面</th><th>MACD</th><th>RSI</th><th>实际涨跌</th><th>路径</th></tr>
{gen_stock_table(v23_rec_actual)}
</table>

<!-- 技术分分布图 -->
<h2>技术分分布</h2>
<div class="chart">
'''
# 技术分分布
tech_scores = [x['stock'].get('S_Tech', 0) for x in v23_rec_actual]
tech_bins = {'0-5': 0, '6-10': 0, '11-15': 0, '16-20': 0, '21-25': 0}
for ts in tech_scores:
    if ts <= 5: tech_bins['0-5'] += 1
    elif ts <= 10: tech_bins['6-10'] += 1
    elif ts <= 15: tech_bins['11-15'] += 1
    elif ts <= 20: tech_bins['16-20'] += 1
    else: tech_bins['21-25'] += 1
max_bin = max(tech_bins.values()) if max(tech_bins.values()) > 0 else 1
colors_dist = {'0-5': '#e74c3c', '6-10': '#e74c3c', '11-15': '#27ae60', '16-20': '#27ae60', '21-25': '#27ae60'}
for bin_name, count in tech_bins.items():
    h = max(count / max_bin * 120, 4)
    html += f'''<div class="chart-bar" style="height:{h}px;background:{colors_dist[bin_name]}"><div class="chg">{count}</div><div class="label">{bin_name}</div></div>\n'''

html += f'''
</div>

<h2>基础分分布</h2>
<div class="chart">
'''
base_scores = [x['stock'].get('S_Base', 0) for x in v23_rec_actual]
base_bins = {'0-2': 0, '3-4': 0, '5-6': 0, '7-8': 0, '9-10': 0}
for bs in base_scores:
    if bs <= 2: base_bins['0-2'] += 1
    elif bs <= 4: base_bins['3-4'] += 1
    elif bs <= 6: base_bins['5-6'] += 1
    elif bs <= 8: base_bins['7-8'] += 1
    else: base_bins['9-10'] += 1
max_bin = max(base_bins.values()) if max(base_bins.values()) > 0 else 1
for bin_name, count in base_bins.items():
    h = max(count / max_bin * 120, 4)
    html += f'''<div class="chart-bar" style="height:{h}px;background:#3498db"><div class="chg">{count}</div><div class="label">{bin_name}</div></div>\n'''

html += f'''
</div>

<div class="footer">
<p>铁律量化 · v2.3评分引擎 × v1.5后评估框架 | 生成时间 {gen_time}</p>
<p>数据源：data_scored_may21_v2.3.json + data_full_may22.bak + data_scored_may21.json(v2.2对照)</p>
<p>评估方法论：《次日后评估白皮书_v1.5.md》14项核心指标 + 动态基线归因</p>
</div>

</div>
</body>
</html>'''

# 保存HTML
report_path = r'C:\Users\34269\Documents\Claude\股票分析\临时报告\v2.3_v1.5_evaluation_report.html'
with open(report_path, 'w', encoding='utf-8') as f:
    f.write(html)
print(f'\n[OK] 报告已保存到: {report_path}')
