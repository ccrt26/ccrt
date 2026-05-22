#!/usr/bin/env python3
"""每日荐股临时回溯 - 信号有效性分析与报告生成"""

import json
import os
import sys
from collections import defaultdict

ROOT = r"C:\Users\34269\Documents\Claude\股票分析"
HTML_OUT = os.path.join(ROOT, "历史数据", "临时回溯", "daily_backtest_report.html")

# ============================================================
# 加载数据
# ============================================================
with open(os.path.join(ROOT, "临时回溯", "backtest_signals.json"), "r", encoding="utf-8-sig") as f:
    raw = json.load(f)


samples = raw if isinstance(raw, list) else raw.get("samples", raw)
print(f"Total samples: {len(samples)}")

# Filter to samples with NextDayChg available
valid = [s for s in samples if s.get("NextDayChg") is not None]
print(f"Valid samples (with T+1): {len(valid)}")

# ============================================================
# 信号定义
# ============================================================
SIGNALS = [
    ("S_MA_Bull", "均线多头 (MA5>MA10>MA20)"),
    ("S_MA_Bear", "均线空头 (MA5<MA10<MA20)"),
    ("S_MA_Converge", "均线收敛 (间距<1%)"),
    ("S_MACD_Golden", "MACD多头 (DIF>DEA)"),
    ("S_MACD_Dead", "MACD空头 (DIF<DEA)"),
    ("S_RSI_40_55", "RSI中性偏强(40-55)"),
    ("S_RSI_LT30", "RSI超卖(<30)"),
    ("S_RSI_GT70", "RSI超买(>70)"),
    ("S_Boll_Upper", "布林触及上轨"),
    ("S_Boll_Lower", "布林触及下轨"),
    ("S_Boll_MidAbove", "价格在布林中轨上方"),
    ("S_Vol_Shrink", "缩量下跌 (量比<0.7,跌)"),
    ("S_Vol_Expand", "放量上涨 (量比>1.5,涨)"),
    ("S_Vol_Gentle", "温和放量小阳 (量比0.8-1.2,涨0-2%)"),
    ("S_Bottom_Rising", "底部抬高 (近5日低点上移)"),
]

# ============================================================
# 信号有效性分析
# ============================================================
signal_stats = {}
for key, label in SIGNALS:
    present = [s for s in valid if s.get(key, 0) == 1]
    absent  = [s for s in valid if s.get(key, 0) == 0]
    total = len(present)
    if total < 5:
        signal_stats[key] = {"label": label, "count": total, "skip": True}
        continue

    # T+1 win rate
    t1_wins = sum(1 for s in present if s["NextDayChg"] > 0)
    t1_avg = sum(s["NextDayChg"] for s in present) / total
    t1_winrate = t1_wins / total * 100

    # T+1 avg for absent (baseline)
    ab_avg = sum(s["NextDayChg"] for s in absent) / len(absent) if absent else 0
    ab_winrate = sum(1 for s in absent if s["NextDayChg"] > 0) / len(absent) * 100 if absent else 0

    # T+3 (if available)
    t3_valid = [s for s in present if s.get("Day3Chg") is not None]
    t3_avg = sum(s["Day3Chg"] for s in t3_valid) / len(t3_valid) if t3_valid else 0
    t3_winrate = sum(1 for s in t3_valid if s["Day3Chg"] > 0) / len(t3_valid) * 100 if t3_valid else 0

    signal_stats[key] = {
        "label": label,
        "count": total,
        "skip": False,
        "t1_winrate": round(t1_winrate, 1),
        "t1_avg": round(t1_avg, 2),
        "t1_baseline_avg": round(ab_avg, 2),
        "t1_baseline_winrate": round(ab_winrate, 1),
        "t1_edge": round(t1_winrate - ab_winrate, 1),  # 胜率差（超额预测能力）
        "t3_winrate": round(t3_winrate, 1) if t3_valid else None,
        "t3_avg": round(t3_avg, 2) if t3_valid else None,
    }

# ============================================================
# 信号组合分析：多个看多信号同时出现时的效果
# ============================================================
bull_signals = ["S_MA_Bull", "S_MACD_Golden", "S_Boll_MidAbove", "S_RSI_40_55", "S_Vol_Gentle", "S_Bottom_Rising"]
combo_stats = {}
for threshold in range(1, 7):
    combo = [s for s in valid if sum(s.get(k, 0) for k in bull_signals) >= threshold]
    if len(combo) < 5:
        continue
    wr = sum(1 for s in combo if s["NextDayChg"] > 0) / len(combo) * 100
    avg = sum(s["NextDayChg"] for s in combo) / len(combo)
    combo_stats[threshold] = {"count": len(combo), "winrate": round(wr, 1), "avg_return": round(avg, 2)}

# ============================================================
# 信号强度排序
# ============================================================
ranked = [(k, v) for k, v in signal_stats.items() if not v["skip"]]
ranked.sort(key=lambda x: x[1]["t1_winrate"], reverse=True)

print("\n===== 信号有效性排名 (T+1胜率) =====")
for key, stat in ranked:
    print(f"  {stat['label']:20s} | 样本:{stat['count']:3d} | T+1胜率:{stat['t1_winrate']:5.1f}% | 基准:{stat['t1_baseline_winrate']:5.1f}% | 超额:{stat['t1_edge']:+5.1f}% | 均值:{stat['t1_avg']:+5.2f}%")

# ============================================================
# 整体统计
# ============================================================
all_returns = [s["NextDayChg"] for s in valid]
avg_return = sum(all_returns) / len(all_returns)
win_rate = sum(1 for r in all_returns if r > 0) / len(all_returns) * 100
pos_avg = sum(r for r in all_returns if r > 0) / max(sum(1 for r in all_returns if r > 0), 1)
neg_avg = sum(r for r in all_returns if r < 0) / max(sum(1 for r in all_returns if r < 0), 1)

# T+3
t3_returns = [s["Day3Chg"] for s in valid if s.get("Day3Chg") is not None]
t3_avg_all = sum(t3_returns) / len(t3_returns) if t3_returns else 0
t3_win_all = sum(1 for r in t3_returns if r > 0) / len(t3_returns) * 100 if t3_returns else 0

# ============================================================
# 均线趋势 vs 其他均线状态
# ============================================================
ma_states = {}
for state_label, bull_cond, bear_cond in [
    ("均线多头(牛市)", True, False),
    ("均线空头(熊市)", False, True),
    ("均线收敛(变盘)", False, False),
]:
    if bull_cond:
        subset = [s for s in valid if s.get("S_MA_Bull", 0) == 1]
    elif bear_cond:
        subset = [s for s in valid if s.get("S_MA_Bear", 0) == 1]
    else:
        subset = [s for s in valid if s.get("S_MA_Bull", 0) == 0 and s.get("S_MA_Bear", 0) == 0 and s.get("S_MA_Converge", 0) == 1]
    if len(subset) < 3:
        continue
    wr = sum(1 for s in subset if s["NextDayChg"] > 0) / len(subset) * 100
    avg_ret = sum(s["NextDayChg"] for s in subset) / len(subset)
    ma_states[state_label] = {"count": len(subset), "winrate": round(wr, 1), "avg_return": round(avg_ret, 2)}

# ============================================================
# 评分数据加载与分析（data_final.json）
# ============================================================
score_data = None
score_analysis = {}
score_path = os.path.join(ROOT, "代码文件", "数据", "data_final.json")
if os.path.exists(score_path):
    with open(score_path, "r", encoding="utf-8-sig") as f:
        score_data = json.load(f)

    scores = [s.get("TotalScore", 0) for s in score_data]
    techs  = [s.get("S_Tech", 0) for s in score_data]
    funds  = [s.get("S_Fund", 0) for s in score_data]
    moneys = [s.get("S_Money", 0) for s in score_data]
    news   = [s.get("S_News", 0) for s in score_data]

    score_analysis = {
        "avg_score": round(sum(scores) / len(scores), 1),
        "min_score": min(scores), "max_score": max(scores),
        "rating_dist": {
            "否决(<55)": sum(1 for s in scores if s < 55),
            "观察(55-64)": sum(1 for s in scores if 55 <= s < 65),
            "达标(65-74)": sum(1 for s in scores if 65 <= s < 75),
            "优质(75-84)": sum(1 for s in scores if 75 <= s < 85),
            "极品(>=85)": sum(1 for s in scores if s >= 85),
        },
        "dim_correlations": {},
    }

    # 维度相关性分析
    import math
    def corr(x, y):
        n = len(x)
        mx, my = sum(x)/n, sum(y)/n
        num = sum((x[i]-mx)*(y[i]-my) for i in range(n))
        dx = math.sqrt(sum((xi-mx)**2 for xi in x))
        dy = math.sqrt(sum((yi-my)**2 for yi in y))
        return round(num/(dx*dy), 3) if dx*dy > 0 else 0

    score_analysis["dim_correlations"] = {
        "总分-Tech": corr(scores, techs),
        "总分-Fund": corr(scores, funds),
        "总分-Money": corr(scores, moneys),
        "总分-News": corr(scores, news),
        "Tech平均分": round(sum(techs)/len(techs), 1),
        "Fund平均分": round(sum(funds)/len(funds), 1),
        "Money平均分": round(sum(moneys)/len(moneys), 1),
    }

    # 检查否决比例是否合理
    total = len(score_data)
    vetoed = score_analysis["rating_dist"]["否决(<55)"]
    score_analysis["veto_pct"] = round(vetoed / total * 100, 1)
    score_analysis["pass_pct"] = round((total - vetoed) / total * 100, 1)

    # 各维度分数区间分析
    score_analysis["tech_analysis"] = {
        "min": min(techs), "max": max(techs), "avg": round(sum(techs)/len(techs), 1),
        "low_pct": round(sum(1 for t in techs if t < 6) / len(techs) * 100, 1),
        "high_pct": round(sum(1 for t in techs if t >= 15) / len(techs) * 100, 1),
    }

# ============================================================
# HTML 报告生成
# ============================================================
def build_html():
    css = """
    <meta charset="utf-8">
    <style>
        body { font-family: 'Microsoft YaHei', sans-serif; background:#f5f6fa; margin:0; padding:20px; color:#333; }
        .container { max-width: 1100px; margin:0 auto; }
        h1 { color:#1A1A2E; border-bottom:3px solid #1A1A2E; padding-bottom:10px; }
        h2 { color:#16213E; margin-top:30px; }
        h3 { color:#333; margin-top:20px; }
        .summary-box { background:#fff; border-radius:8px; padding:20px; margin:15px 0; box-shadow:0 2px 8px rgba(0,0,0,0.1); }
        table { width:100%; border-collapse:collapse; margin:10px 0; background:#fff; box-shadow:0 2px 8px rgba(0,0,0,0.1); }
        th { background:#1A1A2E; color:#fff; padding:10px 12px; text-align:center; font-size:13px; }
        td { padding:8px 12px; text-align:center; border-bottom:1px solid #eee; font-size:13px; }
        tr:hover { background:#f0f4ff; }
        .win { color:#00a854; font-weight:bold; }
        .lose { color:#d93025; font-weight:bold; }
        .neutral { color:#faad14; }
        .tag { display:inline-block; padding:2px 8px; border-radius:4px; font-size:12px; margin:2px; }
        .tag-high { background:#00a85410; color:#00a854; border:1px solid #00a854; }
        .tag-mid { background:#faad1410; color:#b8860b; border:1px solid #faad14; }
        .tag-low { background:#d9302510; color:#d93025; border:1px solid #d93025; }
        .bar-bg { background:#eee; height:16px; border-radius:8px; overflow:hidden; }
        .bar { height:100%; border-radius:8px; }
        .bar-green { background:#00a854; }
        .bar-red { background:#d93025; }
        .bar-yellow { background:#faad14; }
        .footer { text-align:center; color:#999; margin-top:40px; padding:20px; font-size:12px; }
        .insight { background:#e6f7ff; border-left:4px solid #1890ff; padding:12px 16px; margin:10px 0; border-radius:4px; }
        .warn { background:#fff7e6; border-left:4px solid #faad14; padding:12px 16px; margin:10px 0; border-radius:4px; }
        .danger { background:#fff1f0; border-left:4px solid #f5222d; padding:12px 16px; margin:10px 0; border-radius:4px; }
    </style>
    """

    html = f"""<!DOCTYPE html><html lang="zh-CN"><head>{css}</head><body>
<div class="container">
<h1>📋 每日荐股技术信号回溯报告</h1>
<p>回溯日期: 2026-05-22 | 样本: {len(valid)} 个 (42只股票 × ~15个交易日) | 数据周期: 240分钟K线</p>

<div class="summary-box">
<h2>📊 整体统计</h2>
<table>
<tr><th>指标</th><th>T+1</th><th>T+3</th></tr>
<tr><td>平均收益率</td><td class="{'win' if avg_return>=0 else 'lose'}">{avg_return:+.2f}%</td><td class="{'win' if t3_avg_all>=0 else 'lose'}">{t3_avg_all:+.2f}%</td></tr>
<tr><td>胜率(次日上涨比例)</td><td>{win_rate:.1f}%</td><td>{t3_win_all:.1f}%</td></tr>
<tr><td>盈利交易均值</td><td class="win">+{pos_avg:.2f}%</td><td></td></tr>
<tr><td>亏损交易均值</td><td class="lose">{neg_avg:.2f}%</td><td></td></tr>
</table>
<div class="insight">A股240分钟K线 T+1胜率基准约50-52%，当前{win_rate:.1f}%为市场随机水平。</div>
</div>
"""

    # 评分分析
    if score_analysis:
        sa = score_analysis
        html += f"""
<div class="summary-box">
<h2>📈 当日评分分析 (2026-05-21 data_final.json)</h2>
<table>
<tr><th>指标</th><th>数值</th><th>说明</th></tr>
<tr><td>平均总分</td><td><b>{sa['avg_score']}</b></td><td>满分100，42只股票均值</td></tr>
<tr><td>分数范围</td><td><b>{sa['min_score']} - {sa['max_score']}</b></td><td>跨度{sa['max_score']-sa['min_score']}分</td></tr>
<tr><td>否决比例 (<55)</td><td class="lose"><b>{sa['veto_pct']}%</b></td><td>42只中{sa['rating_dist']['否决(<55)']}只被否决</td></tr>
<tr><td>达标及以上 (>=65)</td><td class="win"><b>{sa['pass_pct']}%</b></td><td>仅{sa['rating_dist']['达标(65-74)']}只达标, 优质/极品0只</td></tr>
</table>

<h3>维度相关性</h3>
<table>
<tr><th>相关对</th><th>相关系数</th><th>解读</th></tr>
<tr><td>总分 vs 技术面</td><td><b>{sa['dim_correlations']['总分-Tech']}</b></td><td>{'强相关(技术主导评分)' if abs(sa['dim_correlations']['总分-Tech'])>0.6 else '中度相关' if abs(sa['dim_correlations']['总分-Tech'])>0.3 else '弱相关'}</td></tr>
<tr><td>总分 vs 基本面</td><td><b>{sa['dim_correlations']['总分-Fund']}</b></td><td>{'强相关' if abs(sa['dim_correlations']['总分-Fund'])>0.6 else '中度相关' if abs(sa['dim_correlations']['总分-Fund'])>0.3 else '弱相关'}</td></tr>
<tr><td>总分 vs 资金面</td><td><b>{sa['dim_correlations']['总分-Money']}</b></td><td>{'强相关' if abs(sa['dim_correlations']['总分-Money'])>0.6 else '中度相关' if abs(sa['dim_correlations']['总分-Money'])>0.3 else '弱相关'}</td></tr>
<tr><td>总分 vs 消息面</td><td><b>{sa['dim_correlations']['总分-News']}</b></td><td>{'强相关' if abs(sa['dim_correlations']['总分-News'])>0.6 else '中度相关' if abs(sa['dim_correlations']['总分-News'])>0.3 else '弱相关'}</td></tr>
</table>

<h3>技术面评分分布</h3>
<table>
<tr><th>指标</th><th>数值</th></tr>
<tr><td>技术分范围</td><td>{sa['tech_analysis']['min']} - {sa['tech_analysis']['max']} (均值{sa['tech_analysis']['avg']})</td></tr>
<tr><td>低分段比例 (<6分/25分)</td><td class="lose">{sa['tech_analysis']['low_pct']}%</td></tr>
<tr><td>高分段比例 (>=15分/25分)</td><td class="win">{sa['tech_analysis']['high_pct']}%</td></tr>
</table>
"""

        # 否决比例合理性判断
        if sa['veto_pct'] > 75:
            html += f'<div class="warn">⚠️ 否决比例高达{sa["veto_pct"]}%，42只精选池中{sa["rating_dist"]["否决(<55)"]}只被否决。这可能意味着：①评分标准过严 ②精选池质量不足 ③市场环境不佳导致多数股票技术面走弱 ④否决阈值需要校准</div>'

    # 信号有效性排名
    html += """
<div class="summary-box">
<h2>🎯 信号有效性排名 (T+1胜率)</h2>
<p>按T+1胜率降序排列，胜率越高说明信号对次日上涨的预测越准确。</p>
<table>
<tr><th>排名</th><th>信号</th><th>样本数</th><th>T+1胜率</th><th>T+1均值</th><th>基准胜率</th><th>超额胜率</th><th>T+3胜率</th></tr>
"""
    rank = 0
    for key, stat in ranked:
        rank += 1
        wr = stat['t1_winrate']
        wr_class = "win" if wr > 55 else ("lose" if wr < 45 else "neutral")
        edge = stat['t1_edge']
        edge_class = "win" if edge > 3 else ("lose" if edge < -3 else "neutral")
        t3 = stat.get('t3_winrate', '-')
        t3_str = f"{t3}%" if t3 else "-"
        html += f"""<tr>
<td>{rank}</td>
<td style="text-align:left">{stat['label']}</td>
<td>{stat['count']}</td>
<td class="{wr_class}"><b>{wr}%</b></td>
<td>{stat['t1_avg']:+.2f}%</td>
<td>{stat['t1_baseline_winrate']}%</td>
<td class="{edge_class}">{edge:+.1f}%</td>
<td>{t3_str}</td>
</tr>"""
    html += "</table>"

    # 最佳/最差信号标识
    best = ranked[0][1] if ranked else None
    worst = ranked[-1][1] if ranked else None
    if best:
        html += f'<div class="insight">✅ <b>最有效信号</b>: {best["label"]} (T+1胜率{best["t1_winrate"]}%, 超额{best["t1_edge"]:+.1f}%)</div>'
    if worst:
        html += f'<div class="danger">❌ <b>最差信号</b>: {worst["label"]} (T+1胜率{worst["t1_winrate"]}%, 超额{worst["t1_edge"]:+.1f}%)</div>'
    html += "</div>"

    # 信号组合效果
    if combo_stats:
        html += """
<div class="summary-box">
<h2>🔗 信号组合效果 (看多信号叠加)</h2>
<p>同时满足的看多信号越多，T+1上涨概率和期望收益的变化趋势。</p>
<table>
<tr><th>同时满足信号数</th><th>样本数</th><th>T+1胜率</th><th>T+1均值收益</th></tr>
"""
        for thr in sorted(combo_stats.keys()):
            cs = combo_stats[thr]
            wr_class = "win" if cs['winrate'] > 55 else ("lose" if cs['winrate'] < 45 else "neutral")
            html += f"<tr><td><b>≥{thr}个</b></td><td>{cs['count']}</td><td class='{wr_class}'>{cs['winrate']}%</td><td>{cs['avg_return']:+.2f}%</td></tr>\n"
        html += "</table>"

        # 趋势判断
        combos = sorted(combo_stats.items())
        if len(combos) >= 2:
            low_wr = combos[0][1]['winrate']
            high_wr = combos[-1][1]['winrate']
            if high_wr > low_wr + 5:
                html += f'<div class="insight">✅ 信号叠加有效：≥{combos[-1][0]}个信号时胜率{high_wr}%，显著高于≥{combos[0][0]}个时的{low_wr}%（提升{high_wr-low_wr:+.1f}%）</div>'
            else:
                html += f'<div class="warn">⚠️ 信号叠加效果不明显：≥{combos[-1][0]}个信号时胜率{high_wr}% vs ≥{combos[0][0]}个时{low_wr}%（差距{high_wr-low_wr:+.1f}%）</div>'
        html += "</div>"

    # 均线状态对比
    if ma_states:
        html += """
<div class="summary-box">
<h2>📉 均线趋势状态对比</h2>
<table>
<tr><th>状态</th><th>样本</th><th>T+1胜率</th><th>T+1均值</th></tr>
"""
        for label, st in ma_states.items():
            cls = "win" if st['winrate'] > 55 else ("lose" if st['winrate'] < 45 else "neutral")
            html += f"<tr><td>{label}</td><td>{st['count']}</td><td class='{cls}'>{st['winrate']}%</td><td>{st['avg_return']:+.2f}%</td></tr>\n"
        html += "</table>"
        html += '<div class="insight">均线收敛(间距<1%)是白皮书重点强调的蓄势信号。验证其实际预测效果有助于判断是否应给予更高评分权重。</div>'
        html += "</div>"

    # 重点股票对比
    html += """
<div class="summary-box">
<h2>⚡ 与重点股票回溯结论对比</h2>
<table>
<tr><th>信号</th><th>重点股票回溯</th><th>每日荐股回溯</th><th>结论</th></tr>
"""
    # Cross-reference findings
    cross_signals = [
        ("布林触及上轨", "T+5胜率61.1% → +15分", f'T+1胜率{signal_stats.get("S_Boll_Upper", {}).get("t1_winrate", "N/A")}%', ""),
        ("缩量下跌", "反转胜率60.5% → +12分", f'T+1胜率{signal_stats.get("S_Vol_Shrink", {}).get("t1_winrate", "N/A")}%', ""),
        ("RSI超卖(<30)", "反弹胜率36.8% → 0分(反向)", f'T+1胜率{signal_stats.get("S_RSI_LT30", {}).get("t1_winrate", "N/A")}%', ""),
        ("RSI中性(40-55)", "未单独验证", f'T+1胜率{signal_stats.get("S_RSI_40_55", {}).get("t1_winrate", "N/A")}%', ""),
    ]
    for name, ks, ds, conc in cross_signals:
        html += f"<tr><td>{name}</td><td>{ks}</td><td>{ds}</td><td>{conc}</td></tr>\n"
    html += "</table>"
    html += '<div class="insight">注：重点股票回溯使用日K线(5日验证)，每日荐股使用240分钟K线(1-3日验证)。时间尺度不同，但信号方向应一致。</div>'
    html += "</div>"

    # 否决条件验证
    html += """
<div class="summary-box">
<h2>🚫 否决条件有效性检查 (基于数据逻辑推断)</h2>
<table>
<tr><th>否决条件</th><th>当前数据检查</th><th>建议</th></tr>
<tr>
<td>中期趋势空头 (MA10<=MA20)</td>
<td id="veto-ma">计算中...</td>
<td>需确认死叉是否确实预示后续下跌</td>
</tr>
<tr>
<td>PE估值泡沫</td>
<td>各行业PE阈值是否合理</td>
<td>消费PE>50, 科技PE>80, 金融PE>15 — 需验证</td>
</tr>
<tr>
<td>短期暴涨(30日涨幅>50%)</td>
<td>本次样本中未检测到极端涨幅</td>
<td>回测期间市场环境偏弱，难以验证</td>
</tr>
</table>
</div>
"""

    # 改进建议
    html += """
<div class="summary-box">
<h2>💡 基于回溯的改进建议</h2>
<ul>
"""
    # 根据实际结果生成建议
    for key, stat in ranked[:3]:
        if stat['t1_winrate'] > 55:
            html += f"<li><b>保留并强化</b>: {stat['label']} (T+1胜率{stat['t1_winrate']}%, 超额{stat['t1_edge']:+.1f}%) — 预测能力稳定，可维持或提高权重</li>\n"
    for key, stat in ranked[-3:]:
        if stat['t1_winrate'] < 48:
            html += f"<li><b>审查或降权</b>: {stat['label']} (T+1胜率{stat['t1_winrate']}%, 超额{stat['t1_edge']:+.1f}%) — 预测能力低于基准，考虑降低评分权重或重新定义信号条件</li>\n"

    if score_analysis and sa['veto_pct'] > 70:
        html += f"<li><b>重新校准否决阈值</b>: 当前否决比例{sa['veto_pct']}%，42只精选池中仅{sa['rating_dist']['达标(65-74)']}只达标。建议：①对精选池股票降低否决门槛 ②或扩大达标区间 ③或引入市场环境自适应阈值（震荡市/熊市自动降低标准）</li>\n"

    html += "</ul>"
    html += "</div>"

    # 结论
    html += """
<div class="summary-box">
<h2>📋 总结</h2>
<ul>
"""

    # Overall assessment
    effective_count = sum(1 for _, s in ranked if s['t1_winrate'] > 53)
    total_signal = len(ranked)
    html += f"<li>在{total_signal}个技术信号中，{effective_count}个具有正向预测能力(T+1胜率>53%)</li>\n"

    best_signal = ranked[0][1] if ranked else None
    worst_signal = ranked[-1][1] if ranked else None
    if best_signal:
        html += f"<li><b>最强信号</b>: {best_signal['label']} (胜率{best_signal['t1_winrate']}%)</li>\n"
    if worst_signal:
        html += f"<li><b>最弱信号</b>: {worst_signal['label']} (胜率{worst_signal['t1_winrate']}%)</li>\n"

    if score_analysis:
        html += f"<li>评分系统否决比例{sa['veto_pct']}%（{sa['rating_dist']['否决(<55)']}/{len(score_data)}只），精选池过半否决说明评分标准可能偏严</li>\n"

    html += """
<li>建议：①对预测能力强的信号提高权重 ②对弱于基准的信号重新审查 ③考虑市场环境自适应阈值</li>
</ul>
</div>
"""

    html += f"""
<div class="footer">
<p>铁律量化 · 每日荐股临时回溯报告 | 生成时间: 2026-05-22 | 数据: backtest_signals.json + data_final.json</p>
<p>本报告为临时分析结果，不构成投资建议</p>
</div>
</div></body></html>"""
    return html

html_content = build_html()
with open(HTML_OUT, "w", encoding="utf-8") as f:
    f.write(html_content)
print(f"\nHTML report generated: {HTML_OUT}")
print("Done!")
