#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v2.2 评分引擎 × v1.4 后评估框架 · 评估报告
基于5月21日推荐 → 5月22日实际表现的完整评估
生成: 15个核心指标 + 维度归因 + 优化建议
"""
import json, os, math
from datetime import datetime
from collections import defaultdict

ROOT = r"Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))"
DATA_DIR = os.path.join(ROOT, "代码文件", "数据")
REPORT_DIR = os.path.join(ROOT, "临时报告")

# ── 加载三个数据源 ──
with open(os.path.join(DATA_DIR, "data_scored_may21.json"), 'r', encoding='utf-8-sig') as f:
    may21 = json.load(f)
with open(os.path.join(DATA_DIR, "data_scored_may22.json"), 'r', encoding='utf-8-sig') as f:
    may22 = json.load(f)
with open(os.path.join(DATA_DIR, "data_full_may22.bak"), 'r', encoding='utf-8-sig') as f:
    may22_full = json.load(f)

# ── 构建查找表 ──
may21_recs = may21.get('Recommendations', [])
may21_all = may21.get('AllStocks', [])
may21_vetoed_list = may21.get('VetoedStocks', [])
may22_recs = may22.get('Recommendations', [])
may22_all = may22.get('AllStocks', [])
may22_full_stocks = may22_full.get('Stocks', [])

may22_full_by_code = {s['Code']: s for s in may22_full_stocks}
may22_all_by_code = {s['Code']: s for s in may22_all}
may21_all_by_code = {s['Code']: s for s in may21_all}
may21_vetoed_by_code = {s['Code']: s for s in may21_vetoed_list}

# ──── 1. 基础胜率统计 ────
def calc_basic_stats():
    """基础指标：胜率、盈亏比、组合收益"""
    rows = []
    for r21 in may21_recs:
        code = r21['Code']
        fs = may22_full_by_code.get(code)
        actual_chg = fs.get('ChangePct', 0) if fs else None
        if actual_chg is None:
            continue
        score21 = r21.get('TotalScore', 0)
        tech21 = r21.get('S_Tech', 0)
        money21 = r21.get('S_Money', 0)
        fund21 = r21.get('S_Fund', 0)
        base21 = r21.get('S_Base', 0)
        news21 = r21.get('S_News', 0)
        risk21 = r21.get('S_Risk', 0)

        # 从 full may22 获取真实换手率和量比用于拥挤度判断
        turnover = fs.get('TurnoverRate', 0) if fs else 0
        vol_ratio = fs.get('VolRatio', 1) if 'VolRatio' in (fs or {}) else 1
        # 从 may21_all 获取量比
        a21 = may21_all_by_code.get(code, {})
        vol_ratio_t = a21.get('VolRatio', 1)
        volume_percentile = a21.get('VolumePercentile')

        rows.append({
            'code': code, 'name': r21.get('Name', code),
            'score': score21, 'tech': tech21, 'money': money21,
            'fund': fund21, 'news': news21, 'base': base21, 'risk': risk21,
            'actual_chg': actual_chg,
            'turnover': turnover, 'vol_ratio': vol_ratio_t,
            'volume_percentile': volume_percentile,
            'PE': r21.get('PE', 0),
            'MA5': r21.get('MA5', 0), 'MA10': r21.get('MA10', 0), 'MA20': r21.get('MA20', 0),
            'RSI': r21.get('RSI', 50),
            'MACD_Status': r21.get('MACD_Status', ''),
            'SectorPhase': a21.get('SectorPhase', ''),
            'PathTag': a21.get('PathTag'),
        })

    total = len(rows)
    if total == 0:
        return {'rows': [], 'total': 0, 'wins': 0, 'losses': 0, 'win_rate': 0,
                'avg_return': 0, 'profit_loss_ratio': 0}

    wins = sum(1 for r in rows if r['actual_chg'] > 0)
    losses = sum(1 for r in rows if r['actual_chg'] < 0)
    win_rate = wins / total * 100

    total_profit = sum(r['actual_chg'] for r in rows if r['actual_chg'] > 0)
    total_loss = abs(sum(r['actual_chg'] for r in rows if r['actual_chg'] < 0))
    pl_ratio = total_profit / total_loss if total_loss > 0 else float('inf')

    avg_return = sum(r['actual_chg'] for r in rows) / total

    return {
        'rows': rows, 'total': total, 'wins': wins, 'losses': losses,
        'win_rate': win_rate, 'avg_return': avg_return,
        'total_profit': total_profit, 'total_loss': total_loss,
        'profit_loss_ratio': pl_ratio,
    }

basic = calc_basic_stats()
rows = basic['rows']

# ──── 2. 评分区分度 ────
def calc_score_distinction(rows):
    """高分组 vs 低分组 区分度"""
    sorted_rows = sorted(rows, key=lambda x: x['score'], reverse=True)
    mid = len(sorted_rows) // 2
    high_group = sorted_rows[:mid]
    low_group = sorted_rows[mid:]

    high_wins = sum(1 for r in high_group if r['actual_chg'] > 0)
    low_wins = sum(1 for r in low_group if r['actual_chg'] > 0)
    high_rate = high_wins / len(high_group) * 100 if high_group else 0
    low_rate = low_wins / len(low_group) * 100 if low_group else 0

    high_avg = sum(r['actual_chg'] for r in high_group) / len(high_group) if high_group else 0
    low_avg = sum(r['actual_chg'] for r in low_group) / len(low_group) if low_group else 0

    # 70分以上 vs 70分以下
    above70 = [r for r in rows if r['score'] >= 70]
    below70 = [r for r in rows if r['score'] < 70]
    above70_rate = sum(1 for r in above70 if r['actual_chg'] > 0) / len(above70) * 100 if above70 else 0
    below70_rate = sum(1 for r in below70 if r['actual_chg'] > 0) / len(below70) * 100 if below70 else 0

    return {
        'high_avg': high_avg, 'low_avg': low_avg,
        'high_win_rate': high_rate, 'low_win_rate': low_rate,
        'distinction': high_rate - low_rate,
        'above70_rate': above70_rate, 'below70_rate': below70_rate,
        'score70_distinction': above70_rate - below70_rate,
    }

distinction = calc_score_distinction(rows)

# ──── 3. Spearman 相关系数 ────
def spearman_rank(xs, ys):
    """计算Spearman秩相关系数"""
    n = len(xs)
    if n < 3:
        return 0
    # 排名
    x_rank = {v: i+1 for i, v in enumerate(sorted(set(xs)))}
    y_rank = {v: i+1 for i, v in enumerate(sorted(set(ys)))}

    # 处理并列值用平均排名
    def get_ranks(vals):
        sorted_vals = sorted(set(vals))
        rank_map = {}
        for i, v in enumerate(sorted_vals):
            # 检查并列
            count = sum(1 for x in vals if x == v)
            if count > 1:
                avg_r = sum(range(i+1, i+1+count)) / count
                rank_map[v] = avg_r
            else:
                rank_map[v] = float(i+1)
        return [rank_map[v] for v in vals]

    rx = get_ranks(xs)
    ry = get_ranks(ys)

    d_sq = sum((rx[i] - ry[i])**2 for i in range(n))
    rho = 1 - (6 * d_sq) / (n * (n**2 - 1))
    return rho

def calc_dimension_corr(rows):
    """各维度评分与次日涨跌幅的Spearman相关系数"""
    dims = ['score', 'tech', 'money', 'fund', 'news', 'base', 'risk']
    labels = {'score': '总分', 'tech': '技术', 'money': '资金', 'fund': '基本面',
              'news': '消息面', 'base': '基础', 'risk': '风控'}
    corr = {}
    for dim in dims:
        valid = [(r[dim], r['actual_chg']) for r in rows
                 if isinstance(r.get(dim), (int, float)) and r['actual_chg'] is not None]
        if len(valid) >= 5:
            xs = [v[0] for v in valid]
            ys = [v[1] for v in valid]
            corr[labels[dim]] = round(spearman_rank(xs, ys), 4)
        else:
            corr[labels[dim]] = None
    return corr

dim_corr = calc_dimension_corr(rows)

# ──── 4. 维度误判率 ────
def calc_dim_misjudge(rows):
    """各维度误判率：维度给高分(>60%满分)但亏损>3%"""
    dim_config = {
        'tech': {'max': 25, 'label': '技术面', 'key': 'tech'},
        'money': {'max': 20, 'label': '资金面', 'key': 'money'},
        'fund': {'max': 20, 'label': '基本面', 'key': 'fund'},
        'news': {'max': 20, 'label': '消息面', 'key': 'news'},
        'base': {'max': 10, 'label': '基础', 'key': 'base'},
        'risk': {'max': 5, 'label': '风控', 'key': 'risk'},
    }

    results = {}
    for dim_key, cfg in dim_config.items():
        threshold = cfg['max'] * 0.6
        high_score = [r for r in rows if r.get(dim_key, 0) >= threshold]
        misjudged = [r for r in high_score if r['actual_chg'] < -3]

        total = len(high_score)
        mis_count = len(misjudged)
        rate = mis_count / total * 100 if total > 0 else 0

        results[cfg['label']] = {
            'total': total, 'misjudged': mis_count, 'rate': rate,
            'threshold': threshold,
            'mis_examples': [(r['name'], r['code'], r['actual_chg'], r.get(dim_key, 0))
                           for r in misjudged[:5]]
        }
    return results

misjudge = calc_dim_misjudge(rows)

# ──── 5. 否决误杀率 ────
def calc_veto_stats(rows, may21_vetoed_by_code, may22_full_by_code):
    """否决规则验证：否决池 vs 推荐池 vs 全市场"""
    # 否决池中可以被匹配到 May 22 数据的
    vetoed_perf = []
    for code, v in may21_vetoed_by_code.items():
        fs = may22_full_by_code.get(code)
        if fs:
            actual_chg = fs.get('ChangePct', 0)
            vetoed_perf.append({
                'code': code,
                'name': v.get('Name', code),
                'score': v.get('TotalScore', 0),
                'reason': v.get('VetoReason', ''),
                'actual_chg': actual_chg,
            })

    # 否决误杀率：被否决但大涨>5%
    miskilled = [s for s in vetoed_perf if s['actual_chg'] > 5]
    miskill_rate = len(miskilled) / len(vetoed_perf) * 100 if vetoed_perf else 0

    # 否决池胜率
    veto_wins = sum(1 for s in vetoed_perf if s['actual_chg'] > 0)
    veto_win_rate = veto_wins / len(vetoed_perf) * 100 if vetoed_perf else 0

    # 否决有效度 = 推荐池胜率 - 否决池胜率
    veto_effectiveness = basic['win_rate'] - veto_win_rate

    # 全市场基准 (所有72只的平均涨跌)
    all_perf = [fs.get('ChangePct', 0) for fs in may22_full_stocks if fs.get('ChangePct') is not None]
    mkt_wins = sum(1 for p in all_perf if p > 0)
    mkt_win_rate = mkt_wins / len(all_perf) * 100 if all_perf else 0
    mkt_avg = sum(all_perf) / len(all_perf) if all_perf else 0

    # 评分区分度(对照版) = 推荐池胜率 - 全市场胜率
    score_distinction_mkt = basic['win_rate'] - mkt_win_rate

    # 整理否决原因分布
    reason_dist = defaultdict(list)
    for s in vetoed_perf:
        reason = s['reason']
        # 提取否决条件类型
        rtype = 'unknown'
        for prefix in ['vetoed_abs_1', 'vetoed_abs_2', 'vetoed_abs_3',
                       'vetoed_cond_1', 'vetoed_cond_2', 'vetoed_cond_3',
                       'vetoed_cond_4', 'vetoed_cond_5']:
            if prefix in reason:
                rtype = prefix
                break
        if rtype == 'unknown':
            for kw in ['PE', '涨幅', '连涨', '空头', '死叉', '净利润']:
                if kw in reason:
                    rtype = kw
                    break
        reason_dist[rtype].append(s)

    return {
        'vetoed_perf': vetoed_perf,
        'vetoed_count': len(vetoed_perf),
        'veto_wins': veto_wins,
        'veto_win_rate': veto_win_rate,
        'miskilled': miskilled,
        'miskill_count': len(miskilled),
        'miskill_rate': miskill_rate,
        'veto_effectiveness': veto_effectiveness,
        'mkt_win_rate': mkt_win_rate,
        'mkt_avg': mkt_avg,
        'score_distinction_mkt': score_distinction_mkt,
        'reason_dist': dict(reason_dist),
    }

veto_stats = calc_veto_stats(rows, may21_vetoed_by_code, may22_full_by_code)

# ──── 6. 拥挤度预警有效性 ────
def calc_congestion(rows):
    """拥挤度预警：支持分位模式（VolumePercentile>80 + VolRatio>1.5）和固定阈值模式（换手>8% + 量比>2）"""
    # 分位模式（优先）
    percentile_stocks = [r for r in rows
                         if r.get('volume_percentile') is not None
                         and r['volume_percentile'] > 80
                         and r['vol_ratio'] > 1.5]
    percentile_dropped = [r for r in percentile_stocks if r['actual_chg'] < -2]
    # 固定阈值模式（fallback / 对照）
    fixed_stocks = [r for r in rows if r['turnover'] > 8 and r['vol_ratio'] > 2.0]
    fixed_dropped = [r for r in fixed_stocks if r['actual_chg'] < -2]
    # 混合：取并集
    all_congestion = {r['code']: r for r in percentile_stocks + fixed_stocks}
    congestion_stocks = list(all_congestion.values())
    dropped = [r for r in congestion_stocks if r['actual_chg'] < -2]
    total = len(congestion_stocks)
    drop_rate = len(dropped) / total * 100 if total > 0 else 0

    return {
        'total': total,
        'dropped': len(dropped),
        'drop_rate': drop_rate,
        'percentile_mode': {'total': len(percentile_stocks), 'dropped': len(percentile_dropped)},
        'fixed_mode': {'total': len(fixed_stocks), 'dropped': len(fixed_dropped)},
        'stocks': [(r['name'], r['code'], r['actual_chg'], r['turnover'], r['vol_ratio'])
                  for r in congestion_stocks],
    }

congestion = calc_congestion(rows)

# ──── 7. 路径优选分析 ────
def classify_path(r):
    """路径分类：优先使用引擎预标记的 PathTag，没有则本地计算（向后兼容旧数据）"""
    path_tag = r.get('PathTag')
    if path_tag:
        return path_tag
    # fallback: 四路径分类（旧数据兼容）
    ma5 = r.get('MA5', 0)
    ma10 = r.get('MA10', 0)
    ma20 = r.get('MA20', 0)
    rsi = r.get('RSI', 50)

    if rsi > 70:
        return '逃顶'
    if ma5 > ma10 > ma20 and rsi > 55:
        return '追高'
    if rsi < 35:
        return '抄底'
    if ma5 < ma10 < ma20:
        return '追空'
    return '震荡'

def calc_path_analysis(rows):
    """按路径统计胜率"""
    paths = defaultdict(list)
    for r in rows:
        path = classify_path(r)
        paths[path].append(r)

    path_stats = {}
    for path, stocks in paths.items():
        wins = sum(1 for s in stocks if s['actual_chg'] > 0)
        avg_ret = sum(s['actual_chg'] for s in stocks) / len(stocks)
        path_stats[path] = {
            'count': len(stocks),
            'wins': wins,
            'win_rate': wins / len(stocks) * 100,
            'avg_return': avg_ret,
        }

    # 路径优选有效性 = max - min win rate
    rates = [v['win_rate'] for v in path_stats.values()]
    path_effectiveness = max(rates) - min(rates) if len(rates) >= 2 else 0

    return path_stats, path_effectiveness

path_stats, path_effectiveness = calc_path_analysis(rows)

# ──── 8. 动态权重区分度 ────
def calc_dynamic_weight(rows):
    """上升趋势 vs 下降趋势的胜率差异"""
    up_trend = [r for r in rows if r['MA5'] > r['MA20']]
    down_trend = [r for r in rows if r['MA5'] < r['MA20']]

    up_wins = sum(1 for r in up_trend if r['actual_chg'] > 0)
    down_wins = sum(1 for r in down_trend if r['actual_chg'] > 0)

    up_rate = up_wins / len(up_trend) * 100 if up_trend else 0
    down_rate = down_wins / len(down_trend) * 100 if down_trend else 0

    return {
        'up_count': len(up_trend), 'up_win_rate': up_rate,
        'down_count': len(down_trend), 'down_win_rate': down_rate,
        'distinction': up_rate - down_rate,
    }

dynamic = calc_dynamic_weight(rows)

# ──── 9. 量比惩罚有效性 ────
def calc_vol_penalty(rows):
    """量比>12的股票后续表现"""
    high_vol = [r for r in rows if r['vol_ratio'] > 12]
    dropped = [r for r in high_vol if r['actual_chg'] < -3]
    total = len(high_vol)
    drop_rate = len(dropped) / total * 100 if total > 0 else 0
    return {
        'total': total,
        'dropped': len(dropped),
        'drop_rate': drop_rate,
        'stocks': [(r['name'], r['code'], r['actual_chg'], r['vol_ratio'])
                  for r in high_vol],
    }

vol_penalty = calc_vol_penalty(rows)

# ──── 10. MACD假金叉检测 ────
def calc_macd_analysis(rows):
    """MACD金叉后的实际表现"""
    golden_cross = [r for r in rows if r.get('MACD_Status', '') == 'golden_cross']
    death_cross = [r for r in rows if r.get('MACD_Status', '') == 'death_cross']

    gc_wins = sum(1 for r in golden_cross if r['actual_chg'] > 0)
    dc_wins = sum(1 for r in death_cross if r['actual_chg'] > 0)

    gc_avg = sum(r['actual_chg'] for r in golden_cross) / len(golden_cross) if golden_cross else 0
    dc_avg = sum(r['actual_chg'] for r in death_cross) / len(death_cross) if death_cross else 0

    return {
        'golden_cross': {'count': len(golden_cross), 'wins': gc_wins,
                        'win_rate': gc_wins/len(golden_cross)*100 if golden_cross else 0,
                        'avg_return': gc_avg,
                        'top': [(r['name'], r['actual_chg']) for r in
                               sorted(golden_cross, key=lambda x: x['actual_chg'], reverse=True)[:3]]},
        'death_cross': {'count': len(death_cross), 'wins': dc_wins,
                       'win_rate': dc_wins/len(death_cross)*100 if death_cross else 0,
                       'avg_return': dc_avg,
                       'top': [(r['name'], r['actual_chg']) for r in
                              sorted(death_cross, key=lambda x: x['actual_chg'], reverse=True)[:3]]},
    }

macd_analysis = calc_macd_analysis(rows)

# ──── 诊断面板 ────
def generate_findings(basic, distinction, dim_corr, misjudge, veto_stats,
                      congestion, path_stats, path_effectiveness, dynamic,
                      vol_penalty, macd_analysis, rows):
    findings = []
    suggestions = []

    # 预计算常用值
    wr = basic['win_rate']
    wr_ok = wr >= 60
    ar = basic['avg_return']
    plr = basic['profit_loss_ratio']
    wins = basic['wins']
    losses = basic['losses']
    total = basic['total']

    d = distinction
    dist_val = d['distinction']
    dist_ok = dist_val >= 15
    hwr = d['high_win_rate']
    lwr = d['low_win_rate']
    havg = d['high_avg']
    lavg = d['low_avg']

    ve = veto_stats
    ve_val = ve['veto_effectiveness']
    ve_ok = ve_val >= 20
    vwr_val = ve['veto_win_rate']
    mr = ve['miskill_rate']
    mc = ve['miskill_count']
    vc = ve['vetoed_count']
    mwr = ve['mkt_win_rate']

    pe = path_effectiveness
    pe_ok = pe >= 15

    dy = dynamic
    dy_val = dy['distinction']
    dy_ok = dy_val >= 10
    duc = dy['up_count']
    dwc = dy['down_count']
    duwr = dy['up_win_rate']
    dwwr = dy['down_win_rate']

    cg = congestion
    cgt = cg['total']
    cgr = cg['drop_rate']

    vp = vol_penalty
    vpt = vp['total']
    vpr = vp['drop_rate']

    # 1. 整体表现
    title1 = '整体胜率 {:.1f}% — {}'.format(wr, '达标' if wr_ok else '未达标')
    findings.append({
        'icon': 's', 'title': title1,
        'detail': '组合收益 {:+.2f}%，盈亏比 {:.2f}:1，盈利 {}只 / 亏损 {}只'.format(ar, plr, wins, losses),
    })

    # 2. 评分区分度
    title2 = '评分区分度(高/低分组) {:.1f}% — {}'.format(
        dist_val, '达标' if dist_ok else ('预警边缘' if dist_val >= 10 else '未达标'))
    findings.append({
        'icon': 't', 'title': title2,
        'detail': '高分组胜率 {:.1f}% (收益 {:+.2f}%) | 低分组胜率 {:.1f}% (收益 {:+.2f}%)'.format(hwr, havg, lwr, lavg),
    })

    # 3. 维度相关系数
    best_dim = max(dim_corr.items(), key=lambda x: x[1] if x[1] is not None else -999)
    worst_dim = min(dim_corr.items(), key=lambda x: x[1] if x[1] is not None else 999)
    corr_detail = ' | '.join(['{}: {:.3f}'.format(k, v) for k, v in dim_corr.items() if v is not None])
    findings.append({
        'icon': 'o',
        'title': '维度相关性：{} 最高 ({:.3f})，{} 最低 ({:.3f})'.format(
            best_dim[0], best_dim[1], worst_dim[0], worst_dim[1]),
        'detail': corr_detail,
    })

    # 4. 维度误判率
    high_mis = [(k, v) for k, v in misjudge.items() if v['rate'] > 20]
    mis_summary = '全部正常' if not high_mis else '{}个维度偏高'.format(len(high_mis))
    mis_detail = ' | '.join(['{}: {:.1f}%({}/{})'.format(k, v['rate'], v['misjudged'], v['total'])
                            for k, v in misjudge.items()])
    findings.append({
        'icon': 'w', 'title': '维度误判率分析 — ' + mis_summary,
        'detail': mis_detail,
    })

    # 5. 否决分析
    ve_status = '达标' if ve_ok else '需关注'
    findings.append({
        'icon': 'v',
        'title': '否决有效度 {:.1f}% — {}'.format(ve_val, ve_status),
        'detail': '否决池胜率 {:.1f}% | 误杀率 {:.1f}% ({}只涨>5%被误杀) | 全市场基准胜率 {:.1f}%'.format(
            vwr_val, mr, mc, mwr),
    })

    # 6. 路径优选
    pe_status = '达标' if pe_ok else '区分度不足'
    path_detail = ' | '.join(['{}: {:.0f}%({}只,{:+.2f}%)'.format(
        k, v['win_rate'], v['count'], v['avg_return']) for k, v in path_stats.items()])
    findings.append({
        'icon': 'r',
        'title': '路径优选有效性 {:.1f}% — {}'.format(pe, pe_status),
        'detail': path_detail,
    })

    # 7. 动态权重
    dy_status = '达标' if dy_ok else '不足'
    findings.append({
        'icon': 'd',
        'title': '上升/下降趋势区分度 {:.1f}% — {}'.format(dy_val, dy_status),
        'detail': '上升趋势 {}只, 胜率 {:.1f}% | 下降趋势 {}只, 胜率 {:.1f}%'.format(duc, duwr, dwc, dwwr),
    })

    # 8. 拥挤度
    findings.append({
        'icon': 'c',
        'title': '拥挤度预警有效性 — {}只触发预警，{:.1f}%次日跌>2%'.format(cgt, cgr),
        'detail': '预警股票：' + str([s[0] for s in cg['stocks'][:5]]),
    })

    # 9. 量比惩罚
    findings.append({
        'icon': 'q',
        'title': '量比惩罚({}只>12) — {:.1f}%跌>3%'.format(vpt, vpr),
        'detail': '触发股票：' + str([s[0] for s in vp['stocks'][:3]]),
    })

    # ── 生成优化建议 ──

    # 建议1: 相关系数
    poor_dims = [k for k, v in dim_corr.items() if v is not None and v < 0.1]
    if poor_dims:
        suggestions.append({
            'priority': 'P1',
            'title': f'{", ".join(poor_dims)}评分维度与次日收益相关性极低(<0.1)',
            'action': '建议审查该维度的评分逻辑，检查子因子是否有效。例如，资金面维度当前仅依赖换手率+振幅+板块动量加成，'
                      '缺少资金净流入方向判断。',
            'impact': '高 — 修复可提升整体评分区分度',
        })

    # 建议2: 否决阈值
    if ve['miskill_rate'] > 15:
        suggestions.append({
            'priority': 'P1',
            'title': f'否决误杀率 {ve["miskill_rate"]:.1f}% 超过15%阈值',
            'action': '审查被误杀的股票，找出共同的否决条件。特别关注"中期空头(MA死叉)"条件——'
                      '在强势股短暂回调时会被触发，但未必是真死叉。建议：'
                      '(1) 增加MA20趋势方向判断(向上时放宽死叉否决)；'
                      '(2) 结合量能判断，缩量回调死叉应豁免。',
            'impact': '高 — 减少误杀可提高推荐池质量',
        })

    # 建议3: MACD信号
    macd_gc = macd_analysis['golden_cross']
    if macd_gc['count'] >= 5 and macd_gc['win_rate'] < 55:
        suggestions.append({
            'priority': 'P2',
            'title': f'MACD金叉信号胜率仅 {macd_gc["win_rate"]:.0f}%（{macd_gc["count"]}只），存在假金叉',
            'action': '增加MACD金叉质量过滤：(1) 金叉时DIF与DEA的间距必须>0.5；'
                      '(2) 金叉前MACD柱必须在缩短（绿柱变短）；'
                      '(3) 结合成交量确认——金叉日应放量。',
            'impact': '中 — 可减少技术面误判',
        })

    # 建议4: 拥挤度因子
    if congestion['total'] >= 3 and congestion['drop_rate'] < 60:
        suggestions.append({
            'priority': 'P2',
            'title': f'拥挤度预警不足：触发率 {congestion["drop_rate"]:.0f}% < 目标60%',
            'action': '当前仅用换手率>8%+量比>2判断拥挤。建议：'
                      '(1) 增加换手率分位值判断（相对于过去20日）；'
                      '(2) 增加成交量分位值判断；'
                      '(3) 联合判断：换手率分位>80%且成交量分位>80% → 拥挤预警。',
            'impact': '中 — 可提升风控维度有效性',
        })

    # 建议5: 路径权重
    if path_effectiveness < 15:
        suggestions.append({
            'priority': 'P2',
            'title': f'路径优选有效性 {path_effectiveness:.1f}% < 15%，四路径区分度不足',
            'action': '当前分类标准过于简单（仅用均线+RSI）。建议：'
                      '(1) 追高路径增加放量条件（当日成交量>MA5均量1.5倍）；'
                      '(2) 抄底路径增加缩量条件（成交量<MA5均量0.6倍）；'
                      '(3) 不同路径使用不同的评分权重组合。',
            'impact': '中 — 长期可提升场景适应性',
        })

    # 建议6: 动态权重
    if dynamic['distinction'] < 10:
        suggestions.append({
            'priority': 'P3',
            'title': f'上升/下降趋势区分度 {dynamic["distinction"]:.1f}% < 10%',
            'action': 'v2.2中上升趋势和下降趋势的推荐胜率差异不大，说明评分未充分利用趋势信息。'
                      '建议：上升趋势中提高技术面权重(当前25→30)，下降趋势中提高风控权重(当前5→10)。',
            'impact': '低 — 需要更多数据验证，建议积累20个交易日后再调整',
        })

    # 建议7: 技术分区分度
    tech_scores = [r['tech'] for r in rows]
    tech_range = max(tech_scores) - min(tech_scores) if tech_scores else 0
    if tech_range < 15:
        suggestions.append({
            'priority': 'P2',
            'title': f'技术分区分度不足(范围{min(tech_scores)}-{max(tech_scores)})',
            'action': '虽然已修复K线采集，但技术分仍集中在较窄范围。建议：'
                      '(1) 增加突破确认信号的权重（当前突破确认仅2分，占比过低）；'
                      '(2) 引入RSI极端值惩罚（RSI>80或<20时额外扣分）；'
                      '(3) 均线多头排列应给予更高基础分。',
            'impact': '中 — 改善后可更好识别强势股',
        })

    # 建议8: 胜率
    if basic['win_rate'] < 60:
        suggestions.append({
            'priority': 'P1',
            'title': f'整体胜率 {basic["win_rate"]:.1f}% 未达60%目标',
            'action': '需系统性提升。(1) 优先修复相关系数低的维度；'
                      '(2) 放宽否决阈值减少误杀；'
                      '(3) 增加第二道筛选——在总分排序后，剔除RSI>80或换手率>15%的高风险股。',
            'impact': '高 — 直接影响策略收益',
        })

    return findings, suggestions

findings, suggestions = generate_findings(
    basic, distinction, dim_corr, misjudge, veto_stats,
    congestion, path_stats, path_effectiveness, dynamic,
    vol_penalty, macd_analysis, rows
)

# ──── 生成 HTML ────
now_str = datetime.now().strftime('%Y-%m-%d %H:%M')

def chg_html(val):
    if val is None: return '<span class="na">-</span>'
    cls = 'up' if val > 0 else ('down' if val < 0 else 'flat')
    return f'<span class="{cls}">{val:+.2f}%</span>'

def bar_html(val, max_val, color='#1A1A2E'):
    pct = min(abs(val) / max_val * 100, 100) if max_val > 0 else 0
    return f'<div class="bar-wrap"><div class="bar" style="width:{pct}%;background:{color}"></div></div>'

html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>v2.2 评分引擎 × v1.4 后评估报告</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:'Microsoft YaHei',Arial,sans-serif; font-size:13px; color:#333; background:#f0f2f5; }}
.page {{ max-width:1200px; margin:20px auto; background:#fff; padding:30px; border-radius:8px; box-shadow:0 2px 12px rgba(0,0,0,0.08); }}
h1 {{ color:#1A1A2E; font-size:22px; margin-bottom:5px; }}
h2 {{ color:#16213E; font-size:17px; margin:25px 0 12px 0; padding-bottom:6px; border-bottom:2px solid #1A1A2E; }}
h3 {{ font-size:14px; color:#333; margin:0 0 8px 0; }}
.subtitle {{ color:#888; font-size:12px; margin-bottom:20px; }}

/* Metric Cards */
.metrics {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(170px,1fr)); gap:10px; margin:15px 0; }}
.metric {{ background:#f7f8fa; border-radius:6px; padding:12px; text-align:center; }}
.metric .label {{ font-size:11px; color:#888; margin-bottom:4px; }}
.metric .val {{ font-size:22px; font-weight:bold; }}
.metric .val.danger {{ color:#e74c3c; }}
.metric .val.warn {{ color:#e67e22; }}
.metric .val.success {{ color:#27ae60; }}
.metric .sub {{ font-size:11px; color:#999; margin-top:2px; }}

/* Status badges */
.badge {{ display:inline-block; padding:2px 8px; border-radius:3px; font-size:11px; font-weight:bold; }}
.badge-ok {{ background:#d4edda; color:#155724; }}
.badge-warn {{ background:#fff3cd; color:#856404; }}
.badge-danger {{ background:#f8d7da; color:#721c24; }}

/* Finding cards */
.findings-list {{ list-style:none; padding:0; }}
.findings-list li {{ background:#f8f9fa; border-left:4px solid #1A1A2E; padding:12px 16px; margin:8px 0; border-radius:0 6px 6px 0; line-height:1.6; }}
.findings-list li .f-title {{ font-weight:bold; font-size:13px; }}
.findings-list li .f-detail {{ font-size:12px; color:#666; margin-top:4px; }}

/* Suggestion cards */
.suggestion {{ background:#fff; border:1px solid #e0e0e0; border-radius:6px; padding:14px 16px; margin:8px 0; }}
.suggestion.p1 {{ border-left:4px solid #e74c3c; }}
.suggestion.p2 {{ border-left:4px solid #e67e22; }}
.suggestion.p3 {{ border-left:4px solid #3498db; }}
.suggestion .s-prio {{ display:inline-block; padding:1px 6px; border-radius:3px; font-size:10px; font-weight:bold; margin-right:6px; }}
.suggestion .s-prio.p1 {{ background:#e74c3c; color:#fff; }}
.suggestion .s-prio.p2 {{ background:#e67e22; color:#fff; }}
.suggestion .s-prio.p3 {{ background:#3498db; color:#fff; }}

/* Tables */
table {{ width:100%; border-collapse:collapse; margin:10px 0; font-size:12px; }}
th {{ background:#1A1A2E; color:#fff; padding:6px 5px; text-align:center; font-weight:normal; }}
td {{ padding:5px; text-align:center; border-bottom:1px solid #eee; }}
tr:nth-child(even) {{ background:#fafafa; }}
tr:hover {{ background:#eef3ff; }}
tr.top1 {{ background:#fff8e1 !important; }}
tr.top3 {{ background:#f5f5f5 !important; }}

.up {{ color:#e74c3c; font-weight:bold; }}
.down {{ color:#27ae60; font-weight:bold; }}
.flat {{ color:#999; }}
.na {{ color:#ccc; }}

.bar-wrap {{ background:#eee; border-radius:3px; height:6px; margin-top:4px; }}
.bar {{ height:6px; border-radius:3px; }}

.chart {{ display:flex; align-items:flex-end; gap:6px; height:120px; padding:10px 0; }}
.chart-bar {{ flex:1; min-width:30px; border-radius:4px 4px 0 0; position:relative; text-align:center; }}
.chart-bar .chg {{ position:absolute; top:-18px; left:50%; transform:translateX(-50%); font-size:11px; font-weight:bold; }}
.chart-bar .label {{ position:absolute; bottom:-20px; left:50%; transform:translateX(-50%); font-size:10px; color:#888; white-space:nowrap; }}

.corr-grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(130px,1fr)); gap:8px; margin:10px 0; }}
.corr-item {{ background:#f7f8fa; border-radius:4px; padding:10px; text-align:center; }}
.corr-item .dim {{ font-size:11px; color:#888; }}
.corr-item .rho {{ font-size:18px; font-weight:bold; }}

.footer {{ text-align:center; color:#aaa; font-size:11px; margin-top:25px; padding-top:12px; border-top:1px solid #eee; }}
</style>
</head>
<body>
<div class="page">

<h1>v2.2 评分引擎 × v1.4 后评估报告</h1>
<div class="subtitle">评估对象：5月21日推荐 → 5月22日实际表现 | 生成时间：{now_str}</div>

<!-- 核心指标卡片 -->
<div class="metrics">
  <div class="metric">
    <div class="label">次日胜率</div>
    <div class="val {'success' if basic['win_rate']>=60 else 'warn'}">{basic['win_rate']:.1f}%</div>
    <div class="sub">{basic['wins']}/{basic['total']}</div>
  </div>
  <div class="metric">
    <div class="label">组合次日收益</div>
    <div class="val {'success' if basic['avg_return']>0 else 'danger'}">{basic['avg_return']:+.2f}%</div>
  </div>
  <div class="metric">
    <div class="label">盈亏比</div>
    <div class="val {'success' if basic['profit_loss_ratio']>=1.5 else 'warn'}">{basic['profit_loss_ratio']:.2f}</div>
    <div class="sub">目标≥1.5</div>
  </div>
  <div class="metric">
    <div class="label">评分区分度(高/低)</div>
    <div class="val {'success' if distinction['distinction']>=15 else 'warn'}">{distinction['distinction']:.1f}%</div>
    <div class="sub">目标≥15%</div>
  </div>
  <div class="metric">
    <div class="label">否决有效度</div>
    <div class="val {'success' if veto_stats['veto_effectiveness']>=20 else 'warn'}">{veto_stats['veto_effectiveness']:.1f}%</div>
    <div class="sub">目标≥20%</div>
  </div>
  <div class="metric">
    <div class="label">否决误杀率</div>
    <div class="val {'danger' if veto_stats['miskill_rate']>15 else 'success'}">{veto_stats['miskill_rate']:.1f}%</div>
    <div class="sub">{veto_stats['miskill_count']}只涨>5%被误杀</div>
  </div>
  <div class="metric">
    <div class="label">全市场基准胜率</div>
    <div class="val">{veto_stats['mkt_win_rate']:.1f}%</div>
    <div class="sub">72只平均 {veto_stats['mkt_avg']:+.2f}%</div>
  </div>
  <div class="metric">
    <div class="label">路径优选有效性</div>
    <div class="val {'success' if path_effectiveness>=15 else 'warn'}">{path_effectiveness:.1f}%</div>
    <div class="sub">目标≥15%</div>
  </div>
  <div class="metric">
    <div class="label">趋势区分度</div>
    <div class="val {'success' if dynamic['distinction']>=10 else 'warn'}">{dynamic['distinction']:.1f}%</div>
    <div class="sub">目标≥10%</div>
  </div>
</div>

<!-- 维度相关系数 -->
<h2>维度相关系数（Spearman ρ）</h2>
<div class="corr-grid">
"""
for dim, rho in dim_corr.items():
    if rho is not None:
        cls = 'success' if rho > 0.3 else ('warn' if rho > 0.1 else 'danger')
        html += f'<div class="corr-item"><div class="dim">{dim}</div><div class="rho {cls}">{rho:.3f}</div></div>\n'
    else:
        html += f'<div class="corr-item"><div class="dim">{dim}</div><div class="rho na">N/A</div></div>\n' \

html += """</div>

<!-- 维度误判率 -->
<h2>维度误判率</h2>
<table>
<tr><th>维度</th><th>高分阈值</th><th>高分总次数</th><th>误判次数(亏损>3%)</th><th>误判率</th><th>判定</th></tr>
"""
for dim_name, info in misjudge.items():
    if info['rate'] <= 10:
        badge = '<span class="badge badge-ok">优秀</span>'
    elif info['rate'] <= 20:
        badge = '<span class="badge badge-warn">正常</span>'
    else:
        badge = '<span class="badge badge-danger">偏高</span>'
    html += f"""<tr>
    <td>{dim_name}</td><td>>={info['threshold']:.0f}</td>
    <td>{info['total']}</td><td>{info['misjudged']}</td>
    <td>{info['rate']:.1f}%</td><td>{badge}</td></tr>"""

html += """</table>

<!-- 否决分析 -->
<h2>否决规则诊断</h2>
<table>
<tr><th>否决条件</th><th>股票数</th><th>平均收益</th><th>误杀(>5%)</th></tr>
"""
for reason, stocks in veto_stats['reason_dist'].items():
    if not stocks: continue
    avg_ret = sum(s['actual_chg'] for s in stocks) / len(stocks)
    mis = sum(1 for s in stocks if s['actual_chg'] > 5)
    html += f'<tr><td style="text-align:left;font-size:11px">{reason}</td><td>{len(stocks)}</td>'
    html += f'<td>{chg_html(avg_ret)}</td><td>{mis}</td></tr>\n'

html += f"""</table>

<p style="font-size:12px;color:#666">
<b>否决池整体</b>：{veto_stats['vetoed_count']}只 | 胜率 {veto_stats['veto_win_rate']:.1f}% |
平均收益 {sum(s['actual_chg'] for s in veto_stats['vetoed_perf'])/len(veto_stats['vetoed_perf']):+.2f}%
</p>

<h3>误杀明细（否决池涨>5%的股票）</h3>
<table>
<tr><th>代码</th><th>名称</th><th>评分</th><th>否决原因</th><th>次日涨跌</th></tr>
"""
for s in veto_stats['miskilled'][:10]:
    reason_short = s['reason'][:40] if s['reason'] else '-'
    html += f'<tr><td>{s["code"]}</td><td style="text-align:left">{s["name"]}</td>'
    html += f'<td>{s["score"]}</td><td style="text-align:left;font-size:11px;color:#888">{reason_short}</td>'
    html += f'<td>{chg_html(s["actual_chg"])}</td></tr>\n'

html += """</table>

<!-- 发现与诊断 -->
<h2>诊断发现</h2>
<ul class="findings-list">
"""
for f_item in findings:
    html += f'<li><div class="f-title">{f_item["icon"]} {f_item["title"]}</div>'
    html += f'<div class="f-detail">{f_item["detail"]}</div></li>\n'

html += """</ul>

<!-- 优化建议 -->
<h2>优化建议</h2>
"""
for s in suggestions:
    prio = s['priority']
    html += f'<div class="suggestion {prio.lower()}">'
    html += f'<div><span class="s-prio {prio.lower()}">{prio}</span>'
    html += f'<b>{s["title"]}</b></div>'
    html += f'<p style="font-size:12px;color:#555;margin:8px 0;line-height:1.6">{s["action"]}</p>'
    html += f'<p style="font-size:11px;color:#888">影响评估：{s["impact"]}</p></div>\n'

# 逐股明细
html += """
<h2>逐股明细（按评分降序）</h2>
<table>
<tr><th>#</th><th>代码</th><th>名称</th><th>总分</th><th>技术</th><th>资金</th><th>基本面</th>
<th>PE</th><th>MACD</th><th>RSI</th><th>实际涨跌</th><th>路径</th></tr>
"""
sorted_rows = sorted(rows, key=lambda x: x['score'], reverse=True)
for i, r in enumerate(sorted_rows):
    cls = 'top1' if i == 0 else ('top3' if i < 3 else '')
    path = classify_path(r)
    macd = r.get('MACD_Status', '')
    macd_label = {'golden_cross': '金叉', 'death_cross': '死叉'}.get(macd, macd[:6])
    html += f'<tr class="{cls}">'
    html += f'<td>{i+1}</td><td>{r["code"]}</td><td style="text-align:left">{r["name"]}</td>'
    html += f'<td>{r["score"]}</td><td>{r["tech"]}</td><td>{r["money"]}</td><td>{r["fund"]}</td>'
    html += f'<td>{r["PE"]}</td><td style="font-size:10px">{macd_label}</td><td>{r["RSI"]:.0f}</td>'
    html += f'<td>{chg_html(r["actual_chg"])}</td><td style="font-size:11px">{path}</td></tr>\n'

html += """</table>

<h2>技术分分布</h2>
"""
# 技术分分布柱状图
tech_ranges = {'0-5': 0, '6-10': 0, '11-15': 0, '16-20': 0, '21-25': 0}
for r in rows:
    t = r['tech']
    if t <= 5: tech_ranges['0-5'] += 1
    elif t <= 10: tech_ranges['6-10'] += 1
    elif t <= 15: tech_ranges['11-15'] += 1
    elif t <= 20: tech_ranges['16-20'] += 1
    else: tech_ranges['21-25'] += 1

max_count = max(tech_ranges.values()) if tech_ranges else 1
html += '<div class="chart">'
for rng, cnt in tech_ranges.items():
    pct = cnt / max_count * 100 if max_count > 0 else 0
    color = '#27ae60' if '11' in rng or '16' in rng or '21' in rng else '#e74c3c'
    height = max(cnt * 8, 4)
    html += f'<div class="chart-bar" style="height:{height}px;background:{color}"><div class="chg">{cnt}</div><div class="label">{rng}</div></div>'
html += '</div>'

html += f"""
<div class="footer">
<p>铁律量化 · v2.2评分引擎 × v1.4后评估框架 | 生成时间 {now_str}</p>
<p>数据源：data_scored_may21.json + data_scored_may22.json + data_full_may22.bak</p>
<p>评估方法论：《次日后评估白皮书_v1.4.md》15项核心指标</p>
</div>

</div>
</body>
</html>"""

# ── 写出 HTML ──
html_path = os.path.join(REPORT_DIR, "v2.2_v1.4_evaluation_report.html")
with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html)

# ── 控制台摘要 ──
print(f"HTML 评估报告已生成：{html_path}")
print(f"   大小：{os.path.getsize(html_path)} 字节")
print()
print("=" * 60)
print("  v2.2 评分引擎 × v1.4 后评估 · 摘要")
print("=" * 60)
print(f"  评估期间：5月21日推荐 → 5月22日实际")
print(f"  推荐只数：{basic['total']}")
print(f"  整体胜率：{basic['win_rate']:.1f}% ({basic['wins']}/{basic['total']})")
print(f"  组合收益：{basic['avg_return']:+.2f}%")
print(f"  盈亏比：{basic['profit_loss_ratio']:.2f}:1")
print(f"  评分区分度(高/低分组)：{distinction['distinction']:.1f}%")
print(f"  否决有效度：{veto_stats['veto_effectiveness']:.1f}%")
print(f"  否决误杀率：{veto_stats['miskill_rate']:.1f}%")
print(f"  全市场基准胜率：{veto_stats['mkt_win_rate']:.1f}%")
print(f"  路径优选有效性：{path_effectiveness:.1f}%")
print(f"  趋势区分度：{dynamic['distinction']:.1f}%")
print()
print("维度相关系数：")
for dim, rho in dim_corr.items():
    if rho is not None:
        flag = " [OK]" if rho > 0.3 else (" [WARN]" if rho > 0.1 else " [BAD]")
        print(f"  {dim}: {rho:.3f}{flag}")
print()
print("维度误判率：")
for dim_name, info in misjudge.items():
    flag = "" if info['rate'] <= 10 else (" [WARN]" if info['rate'] <= 20 else " [BAD]")
    print(f"  {dim_name}: {info['rate']:.1f}% ({info['misjudged']}/{info['total']}){flag}")
print()
print("优化建议：")
for s in suggestions:
    print(f"  [{s['priority']}] {s['title']}")
print("=" * 60)

# ── 追加 summary.csv ──
summary_csv_path = os.path.join(REPORT_DIR, "summary.csv")
import csv
header = ["period", "start_date", "end_date", "total_recommendations", "wins", "losses",
          "win_rate", "total_profit", "total_loss", "profit_loss_ratio", "portfolio_return",
          "hs300_return", "excess_return", "tech_misjudge_rate", "money_misjudge_rate",
          "sector_misjudge_rate", "news_misjudge_rate", "veto_kill_rate", "exemption_win_rate",
          "recommended_win_rate", "vetoed_win_rate", "market_win_rate", "veto_effectiveness",
          "score_distinction"]
total_pool = may21.get("Summary", {}).get("Total", 0)
vetoed_count = may21.get("Summary", {}).get("Vetoed", 0)
veto_kill_rate = round(vetoed_count / total_pool * 100, 1) if total_pool > 0 else 0
row = {
    "period": "20260521-20260522",
    "start_date": "20260521", "end_date": "20260522",
    "total_recommendations": basic["total"],
    "wins": basic["wins"], "losses": basic["losses"],
    "win_rate": round(basic["win_rate"], 1),
    "total_profit": round(basic.get("total_profit", 0), 2),
    "total_loss": round(basic.get("total_loss", 0), 2),
    "profit_loss_ratio": round(basic["profit_loss_ratio"], 2),
    "portfolio_return": round(basic["avg_return"], 2),
    "hs300_return": "N/A", "excess_return": "N/A",
    "tech_misjudge_rate": round(misjudge.get("技术", {}).get("rate", 0), 1),
    "money_misjudge_rate": round(misjudge.get("资金", {}).get("rate", 0), 1),
    "sector_misjudge_rate": round(misjudge.get("板块", {}).get("rate", 0), 1),
    "news_misjudge_rate": round(misjudge.get("消息", {}).get("rate", 0), 1),
    "veto_kill_rate": veto_kill_rate,
    "exemption_win_rate": round(veto_stats.get("recommended_win_rate", 0), 1),
    "recommended_win_rate": round(veto_stats.get("recommended_win_rate", basic["win_rate"]), 1),
    "vetoed_win_rate": round(veto_stats.get("veto_win_rate", 0), 1),
    "market_win_rate": round(veto_stats.get("mkt_win_rate", 0), 1),
    "veto_effectiveness": round(veto_stats.get("veto_effectiveness", 0), 1),
    "score_distinction": round(distinction.get("distinction", 0), 1),
}
file_exists = os.path.isfile(summary_csv_path)
with open(summary_csv_path, "a", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=header)
    if not file_exists or os.path.getsize(summary_csv_path) == 0:
        writer.writeheader()
    writer.writerow(row)
print(f"  summary.csv 已追加 → {summary_csv_path}")
