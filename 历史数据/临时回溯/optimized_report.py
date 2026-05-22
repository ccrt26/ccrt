#!/usr/bin/env python3
"""生成优化评分对比报告 HTML"""
import json, os
from datetime import datetime

ROOT = r"C:\Users\34269\Documents\Claude\股票分析"
ORIG_PATH = os.path.join(ROOT, "代码文件", "数据", "data_final.json")
NEW_PATH = os.path.join(ROOT, "代码文件", "数据", "data_final_optimized.json")
OUT_PATH = os.path.join(ROOT, "历史数据", "临时回溯", "optimized_report.html")

with open(ORIG_PATH, "r", encoding="utf-8-sig") as f:
    orig = json.load(f)
with open(NEW_PATH, "r", encoding="utf-8-sig") as f:
    new_data = json.load(f)

# Build comparison
stocks = []
for o, n in zip(orig, new_data):
    delta_tech = n["S_Tech"] - o["S_Tech"]
    delta_total = n["TotalScore"] - o["TotalScore"]
    stocks.append({
        "code": o["Code"], "name": o["Name"], "industry": o["Industry"],
        "price": o["Price"], "chg": o["ChangePct"],
        "old_tech": o["S_Tech"], "new_tech": n["S_Tech"], "delta_tech": delta_tech,
        "old_total": o["TotalScore"], "new_total": n["TotalScore"], "delta_total": delta_total,
        "pe": o["PE"], "turnover": o["TurnoverRate"]
    })

# Sort by delta_tech desc
stocks.sort(key=lambda x: x["delta_tech"], reverse=True)

# Stats
improved = sum(1 for s in stocks if s["delta_tech"] > 0)
degraded = sum(1 for s in stocks if s["delta_tech"] < 0)
unchanged = sum(1 for s in stocks if s["delta_tech"] == 0)
avg_delta = sum(s["delta_tech"] for s in stocks) / len(stocks)
avg_new_tech = sum(s["new_tech"] for s in stocks) / len(stocks)
avg_old_tech = sum(s["old_tech"] for s in stocks) / len(stocks)

old_avg_total = sum(s["old_total"] for s in stocks) / len(stocks)
new_avg_total = sum(s["new_total"] for s in stocks) / len(stocks)

# Build rows
rank = 0
rows = ""
for s in stocks:
    rank += 1
    chg_cls = "up" if s["chg"] >= 0 else "down"
    chg_str = f"+{s['chg']:.2f}%" if s["chg"] >= 0 else f"{s['chg']:.2f}%"
    if s["delta_tech"] > 5:
        delta_cls = "win"
        arrow = "↑"
    elif s["delta_tech"] > 0:
        delta_cls = "win"
        arrow = "↑"
    elif s["delta_tech"] < -5:
        delta_cls = "lose"
        arrow = "↓"
    elif s["delta_tech"] < 0:
        delta_cls = "lose"
        arrow = "↓"
    else:
        delta_cls = ""
        arrow = "→"

    tech_bar = int(s["new_tech"] / 25 * 100)
    old_tech_bar = int(s["old_tech"] / 25 * 100)

    rows += f"""<tr>
        <td>{rank}</td>
        <td>{s['code']}</td>
        <td style="text-align:left;padding-left:8px;font-weight:600">{s['name']}</td>
        <td>{s['industry']}</td>
        <td>{s['price']:.2f}</td>
        <td class="{chg_cls}">{chg_str}</td>
        <td>{s['pe']:.1f}</td>
        <td>
            <div style="display:flex;align-items:center;gap:4px">
                <div class="bar-bg" style="flex:1;max-width:60px"><div class="bar bar-old" style="width:{old_tech_bar}%"></div></div>
                <span style="font-size:11px;color:#999">{s['old_tech']}</span>
            </div>
        </td>
        <td>
            <div style="display:flex;align-items:center;gap:4px">
                <div class="bar-bg" style="flex:1;max-width:60px"><div class="bar bar-new" style="width:{tech_bar}%"></div></div>
                <span style="font-size:11px;color:#333;font-weight:bold">{s['new_tech']}</span>
            </div>
        </td>
        <td class="{delta_cls}">{arrow}{s['delta_tech']:+d}</td>
        <td>{s['old_total']} → <strong>{s['new_total']}</strong></td>
        <td class="{delta_cls}">{s['delta_total']:+d}</td>
    </tr>"""

# Top gainers
top5 = [s for s in stocks if s["delta_tech"] > 0][:5]
top5_html = ""
for s in top5:
    top5_html += f"""<div class="card"><div class="card-hdr">{s['name']} ({s['code']})</div>
    <div class="card-body">技术面: {s['old_tech']} → <strong>{s['new_tech']}</strong> <span class="tag-up">+{s['delta_tech']}</span><br>
    总分: {s['old_total']} → <strong>{s['new_total']}</strong> <span class="tag-up">+{s['delta_total']}</span><br>
    涨幅: {s['chg']:+.2f}% | PE: {s['pe']:.1f}</div></div>"""

html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<title>每日荐股评分优化报告 v2.1</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box }}
body {{ font-family:"Microsoft YaHei",sans-serif; background:#f0f2f5; padding:20px; color:#333 }}
.container {{ max-width:1200px; margin:0 auto }}
h1 {{ color:#1A1A2E; border-bottom:3px solid #1A1A2E; padding-bottom:10px; margin-bottom:16px }}
h2 {{ color:#16213E; margin:24px 0 12px }}
.summary-grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin:16px 0 }}
.summary-item {{ background:#fff; border-radius:8px; padding:16px; text-align:center; box-shadow:0 2px 8px rgba(0,0,0,0.08) }}
.summary-item .val {{ font-size:28px; font-weight:bold; margin:4px 0 }}
.summary-item .lbl {{ font-size:12px; color:#888 }}
.card-grid {{ display:grid; grid-template-columns:repeat(5,1fr); gap:10px; margin:12px 0 }}
.card {{ background:#fff; border-radius:8px; padding:12px; box-shadow:0 1px 4px rgba(0,0,0,0.08); font-size:12px }}
.card-hdr {{ font-weight:bold; font-size:14px; margin-bottom:6px }}
.card-body {{ line-height:1.8 }}
.tag-up {{ display:inline-block; background:#00a854; color:#fff; border-radius:4px; padding:0 6px; font-size:11px }}
.tag-down {{ display:inline-block; background:#d93025; color:#fff; border-radius:4px; padding:0 6px; font-size:11px }}
table {{ width:100%; border-collapse:collapse; margin:10px 0; background:#fff; box-shadow:0 2px 8px rgba(0,0,0,0.08); font-size:12px }}
th {{ background:#1A1A2E; color:#fff; padding:8px 6px; text-align:center; font-size:11px }}
td {{ padding:6px; text-align:center; border-bottom:1px solid #eee }}
tr:hover {{ background:#f0f4ff }}
.up {{ color:#d93025; font-weight:bold }}
.down {{ color:#00a854; font-weight:bold }}
.win {{ color:#00a854; font-weight:bold }}
.lose {{ color:#d93025; font-weight:bold }}
.bar-bg {{ background:#eee; height:12px; border-radius:6px; overflow:hidden }}
.bar {{ height:100%; border-radius:6px }}
.bar-old {{ background:#bbb }}
.bar-new {{ background:#4a6cf7 }}
.insight {{ background:#e6f7ff; border-left:4px solid #1890ff; padding:12px 16px; margin:12px 0; border-radius:4px; font-size:13px; line-height:1.6 }}
.warn {{ background:#fff7e6; border-left:4px solid #faad14; padding:12px 16px; margin:12px 0; border-radius:4px; font-size:13px; line-height:1.6 }}
.footer {{ text-align:center; color:#999; margin-top:30px; padding:16px; font-size:12px }}
</style></head><body>
<div class="container">
<h1>📋 每日荐股评分优化报告 v2.1 — 突破确认模块</h1>

<div class="summary-grid">
    <div class="summary-item"><div class="lbl">技术面均值(原)</div><div class="val" style="color:#999">{avg_old_tech:.1f}</div><div class="lbl">满分25分</div></div>
    <div class="summary-item"><div class="lbl">技术面均值(新)</div><div class="val" style="color:#4a6cf7">{avg_new_tech:.1f}</div><div class="lbl">↑+{avg_delta:+.1f}</div></div>
    <div class="summary-item"><div class="lbl">总分均值(原)</div><div class="val" style="color:#999">{old_avg_total:.1f}</div><div class="lbl">满分100</div></div>
    <div class="summary-item"><div class="lbl">总分均值(新)</div><div class="val" style="color:#4a6cf7">{new_avg_total:.1f}</div><div class="lbl">↑+{new_avg_total-old_avg_total:+.1f}</div></div>
</div>

<div class="insight">
<strong>改进说明：</strong>新增<strong>突破确认模块</strong>（§3.4.7），修正量价评分对放量突破的误判，调整RSI>70在突破形态下的惩罚规则。
<ul style="margin:6px 0 0 20px">
<li><strong>东睦股份</strong> S_Tech 2→17（+15）— ✅ 识别剧烈震荡洗盘后突破</li>
<li><strong>同花顺</strong> S_Tech 2→18（+16）— ✅ 识别放量突破形态</li>
<li><strong>中芯国际</strong> S_Tech 1→17（+16）— ✅ 均线多头+底部支撑修复</li>
<li>共 {improved} 只提升, {degraded} 只下降, {unchanged} 只不变</li>
</ul>
</div>

<h2>🏆 改善最大的5只</h2>
<div class="card-grid">{top5_html}</div>

<h2>📊 全部42只评分对比</h2>
<table>
<tr><th>#</th><th>代码</th><th>名称</th><th>行业</th><th>价格</th><th>涨跌</th><th>PE</th><th>原技术分</th><th>新技术分</th><th>变化</th><th>总分变化</th><th>总差</th></tr>
{rows}
</table>

<div class="warn">
<strong>注意事项：</strong><br>
1. 部分股票（贵州茅台、招商银行、五粮液）技术分下降明显是因为<strong>原人工评分虚高</strong>（RSI低至1-3却被给了23分）。新引擎按规则计算后更客观。<br>
2. 突破确认模块不改变基本面(20分)/资金面(20分)/消息面(20分)/风控(5分)评分，仅优化技术面(25分)。<br>
3. 建议将本模块补充写入白皮书 v2.1，并替换原有 data_final.json。
</div>

<div class="footer">
铁律量化 · 评分优化 v2.1 | 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}<br>
数据: klines_data.json → scoring_engine.py → data_final_optimized.json
</div>
</div></body></html>"""

with open(OUT_PATH, "w", encoding="utf-8") as f:
    f.write(html)
print(f"Report: {OUT_PATH}")
