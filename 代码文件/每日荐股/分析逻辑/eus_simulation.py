#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
退出急迫度评分（EUS）模拟 v2
按3个场景分组模拟持仓，展示退出机制对不同情况的分辨能力
"""
import json, os, random
from datetime import datetime

ROOT = r"Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))"
SCORED_FILE = os.path.join(ROOT, "代码文件", "数据", "data_scored.json")
FULL_FILE = os.path.join(ROOT, "代码文件", "数据", "data_full.json")
OUT_DIR = os.path.join(ROOT, "历史数据", "临时回溯")

random.seed(42)

def calc_ma(values, period):
    result = []
    for i in range(len(values)):
        if i < period - 1: result.append(None)
        else: result.append(sum(values[i-period+1:i+1]) / period)
    return result

# 加载数据
with open(SCORED_FILE, "r", encoding="utf-8-sig") as f: scored = json.load(f)
with open(FULL_FILE, "r", encoding="utf-8-sig") as f: full_data = json.load(f)
full_map = {}
for s in full_data: full_map[s["Code"]] = s

passed = scored["Recommendations"]
print(f"通过否决: {len(passed)} 只")

# ====== 构建3种场景 ======
# 场景A "看错了": 持仓12-15天，盈亏-3%~-8%，技术面走坏
# 场景B "需观察": 持仓7-12天，盈亏-3%~+2%，技术面中性
# 场景C "正常持有": 持仓1-6天，盈亏-1%~+5%，技术面良好

holdings = []
n = len(passed)
for i, r in enumerate(passed):
    code = r["Code"]
    f = full_map.get(code, {})
    closes = f.get("KClose", [])
    volumes = f.get("KVolume", [])

    # 分配到场景
    if i < n * 0.20:  # 20% — 看错
        hold_days = random.randint(12, 15)
        pnl = round(random.uniform(-8, -3), 2)
        entry_price = round(r["Price"] / (1 + pnl/100), 2)
    elif i < n * 0.45:  # 25% — 需观察
        hold_days = random.randint(7, 12)
        pnl = round(random.uniform(-3, 2), 2)
        entry_price = round(r["Price"] / (1 + pnl/100), 2)
    else:  # 55% — 正常
        hold_days = random.randint(1, 6)
        pnl = round(random.uniform(-1, 5), 2)
        entry_price = round(r["Price"] / (1 + pnl/100), 2)

    holdings.append({
        "Code": code, "Name": r["Name"], "Industry": r.get("Industry", ""),
        "Price": r["Price"], "EntryPrice": entry_price, "PnlPct": pnl,
        "HoldDays": hold_days, "EntryDate": (datetime.now()).strftime("%m-%d"),
        "TotalScore": r["TotalScore"], "PE": r.get("PE", 0), "ChangePct": r.get("ChangePct", 0),
        "PoolSource": r.get("PoolSource", ""),
        "closes": closes, "volumes": volumes
    })

# ====== EUS 计算 ======
for h in holdings:
    closes = h["closes"]; volumes = h["volumes"]
    price = h["Price"]; pnl = h["PnlPct"]; hd = h["HoldDays"]

    # 1. 时间因子 (25%)
    if hd <= 5: ts = 0
    elif hd <= 10: ts = (hd - 5) / 5 * 50
    elif hd <= 15: ts = 50 + (hd - 10) / 5 * 40
    else: ts = 90
    ts = min(100, ts)

    # 2. 盈亏状态 (30%)
    if pnl <= -7: ps = 100
    elif pnl <= -5: ps = 80
    elif pnl <= -3: ps = 60
    elif pnl <= 3: ps = 40
    elif pnl <= 8: ps = 20
    elif pnl <= 15: ps = 10
    elif pnl <= 20: ps = 30
    else: ps = 50

    # 3. 技术面 (25%)
    tech_s = 0
    if len(closes) >= 20:
        ma5_arr = calc_ma(closes, 5); ma10_arr = calc_ma(closes, 10); ma20_arr = calc_ma(closes, 20)
        ma5 = ma5_arr[-1] or 0; ma10 = ma10_arr[-1] or 0; ma20 = ma20_arr[-1] or 0
        if price < ma20 * 0.97: tech_s = 75
        elif price < ma20: tech_s = 55
        elif ma5 < ma10: tech_s = 40
        elif len(volumes) >= 5:
            vol_ma5 = sum(volumes[-5:]) / 5
            low_days = sum(1 for v in volumes[-3:] if v < vol_ma5 * 0.8) if vol_ma5 > 0 else 0
            tech_s = 25 if low_days >= 3 else 0

    # 4. 资金面 (20%)
    fund_s = 0
    chg = h["ChangePct"]
    if chg < -3: fund_s = 55
    elif abs(chg) < 0.5: fund_s = 25
    elif chg > 5: fund_s = 10

    # 综合
    eus = ts * 0.25 + ps * 0.30 + tech_s * 0.25 + fund_s * 0.20

    # 一票否决
    one_vote = ""
    if pnl <= -7: one_vote = "硬止损 -7%"
    elif hd >= 15 and pnl < -5: one_vote = "超15天且亏损>5%"
    elif price > 0 and len(closes) >= 20:
        ma20 = calc_ma(closes, 20)[-1] or 0
        if price < ma20 * 0.95: one_vote = "价格<MA20×0.95"

    if one_vote: action = "一票退出"
    elif eus >= 50: action = "全面退出"
    elif eus >= 35: action = "退出2/3"
    elif eus >= 20: action = "减半仓"
    else: action = "继续持有"

    h["EUS"] = round(eus, 1)
    h["TimeScore"] = round(ts)
    h["ProfitScore"] = round(ps)
    h["TechScore"] = round(tech_s)
    h["FundScore"] = round(fund_s)
    h["Action"] = action
    h["OneVote"] = one_vote

# 排序
holdings.sort(key=lambda x: x["EUS"], reverse=True)

# ====== 统计数据 ======
action_dist = {}
for h in holdings:
    a = h["Action"]
    action_dist[a] = action_dist.get(a, 0) + 1

print(f"\n操作建议分布 ({len(holdings)} 只):")
for a in ["一票退出", "全面退出", "退出2/3", "减半仓", "继续持有"]:
    c = action_dist.get(a, 0)
    pct = c / len(holdings) * 100
    bar = "█" * int(pct / 2) + "░" * (50 - int(pct / 2))
    print(f"  {a:8s}: {c:2d} ({pct:4.0f}%)")

print(f"\nEUS 范围: {min(h['EUS'] for h in holdings):.0f} ~ {max(h['EUS'] for h in holdings):.0f}")
print(f"EUS 均值: {sum(h['EUS'] for h in holdings)/len(holdings):.0f}")

# ====== 场景分析 ======
print(f"\n场景分组分析:")
scenarios = {
    "看错了(20%)": lambda h: h["HoldDays"] >= 12 and h["PnlPct"] <= -3,
    "需观察(25%)": lambda h: 7 <= h["HoldDays"] <= 12 and -3 <= h["PnlPct"] <= 2,
    "正常(55%)": lambda h: h["HoldDays"] <= 6 and h["PnlPct"] >= -1
}
for label, fn in scenarios.items():
    group = [h for h in holdings if fn(h)]
    if group:
        avg_eus = sum(h["EUS"] for h in group) / len(group)
        exit_cnt = sum(1 for h in group if h["Action"] in ("全面退出", "一票退出"))
        print(f"  {label}: {len(group):2d} 只, EUS均{avg_eus:.0f}, 需退出{exit_cnt}只")

# ====== 按EUS区间统计 ======
buckets = [(0, "0-10"), (10, "10-20"), (20, "10-20x2"),
           (25, "20-25"), (30, "25-30"), (35, "30-35"),
           (40, "35-40"), (50, "40-50"), (100, "50+")]
for threshold, label in buckets:
    cnt = sum(1 for h in holdings if h["EUS"] < threshold)
    # cumulative reverse
cnt_above_50 = sum(1 for h in holdings if h["EUS"] >= 50)
cnt_35_50 = sum(1 for h in holdings if 35 <= h["EUS"] < 50)
cnt_20_35 = sum(1 for h in holdings if 20 <= h["EUS"] < 35)
cnt_below_20 = sum(1 for h in holdings if h["EUS"] < 20)
print(f"\nEUS 分布: <20:{cnt_below_20}  20-35:{cnt_20_35}  35-50:{cnt_35_50}  >=50:{cnt_above_50}")

# ====== 生成 HTML ======
now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8">
<title>退出急迫度(EUS)模拟报告 — {now_str[:10]}</title>
<style>
@page{{size:landscape;margin:10mm}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:"Microsoft YaHei","PingFang SC",sans-serif;background:#f4f5f7;color:#333;padding:16px}}
h1{{font-size:20px;margin-bottom:2px}}
.sub{{color:#666;font-size:12px;margin-bottom:12px}}
.summary{{background:#fff;border-radius:10px;padding:16px;margin-bottom:14px;box-shadow:0 1px 6px rgba(0,0,0,.06)}}
.grid{{display:grid;grid-template-columns:repeat(6,1fr);gap:8px}}
.stat{{text-align:center;padding:10px;border-radius:8px;background:#f8f9fa}}
.stat .num{{font-size:24px;font-weight:800}}
.stat .label{{font-size:11px;color:#666}}
.sec{{background:#fff;border-radius:10px;padding:16px;margin-bottom:14px;box-shadow:0 1px 6px rgba(0,0,0,.06)}}
.sec h2{{font-size:14px;font-weight:700;margin-bottom:10px;border-bottom:2px solid #1a1a2e;padding-bottom:6px}}
table{{width:100%;border-collapse:collapse;font-size:11px}}
th{{background:#f0f2f5;padding:5px;text-align:center;font-weight:600;border-bottom:2px solid #ddd;font-size:10px;white-space:nowrap}}
td{{padding:4px 5px;text-align:center;border-bottom:1px solid #eee;font-size:10.5px}}
.bar{{height:4px;border-radius:2px;background:#eee;overflow:hidden}}
.fill{{height:100%;border-radius:2px}}
.tag{{padding:1px 5px;border-radius:4px;font-size:9px;font-weight:600;white-space:nowrap}}
.green{{background:#d4edda;color:#155724}}
.yellow{{background:#fff3cd;color:#856404}}
.orange{{background:#ffe0b2;color:#e65100}}
.red{{background:#f8d7da;color:#721c24}}
.up{{color:#e74c3c}} .down{{color:#27ae60}}
.scenario-a{{border-left:3px solid #e74c3c}}
.scenario-b{{border-left:3px solid #f39c12}}
.scenario-c{{border-left:3px solid #2ecc71}}
</style></head>
<body>
<h1>退出急迫度评分 (EUS) 模拟报告</h1>
<div class="sub">{now_str} | 模拟{len(holdings)}只持仓 | 3种场景: 看错(20%) + 需观察(25%) + 正常(55%)</div>

<div class="summary">
<div class="grid">
<div class="stat"><div class="num">{len(holdings)}</div><div class="label">持仓</div></div>
<div class="stat"><div class="num" style="color:#2ecc71">{action_dist.get("继续持有",0)}</div><div class="label">继续持有</div></div>
<div class="stat"><div class="num" style="color:#f39c12">{action_dist.get("减半仓",0)}</div><div class="label">减半仓</div></div>
<div class="stat"><div class="num" style="color:#e65100">{action_dist.get("退出2/3",0)}</div><div class="label">退出2/3</div></div>
<div class="stat"><div class="num" style="color:#e74c3c">{action_dist.get("全面退出",0) + action_dist.get("一票退出",0)}</div><div class="label">需退出</div></div>
<div class="stat"><div class="num">{sum(h['EUS'] for h in holdings)/len(holdings):.0f}</div><div class="label">EUS均值</div></div>
</div>
</div>

<div class="sec">
<h2>全持仓按EUS排序 (急迫度由高到低)</h2>
<table>
<thead><tr>
<th>#</th><th>代码</th><th>名称</th><th>行业</th><th>持有时长</th><th>买入价</th><th>盈亏</th><th>EUS</th><th>时间分</th><th>盈亏分</th><th>技术分</th><th>资金分</th><th>建议</th>
</tr></thead>
<tbody>
"""

for i, h in enumerate(holdings, 1):
    pnl_cls = "up" if h["PnlPct"] >= 0 else "down"
    if h["Action"] == "一票退出":  tr_cls = "scenario-a"; tag_cls = "red"
    elif h["Action"] == "全面退出": tr_cls = "scenario-a"; tag_cls = "red"
    elif h["Action"] == "退出2/3": tr_cls = "scenario-b"; tag_cls = "orange"
    elif h["Action"] == "减半仓": tr_cls = "scenario-b"; tag_cls = "yellow"
    else: tr_cls = "scenario-c"; tag_cls = "green"

    bar_color = "#2ecc71" if h["EUS"] < 20 else ("#f39c12" if h["EUS"] < 35 else ("#e65100" if h["EUS"] < 50 else "#e74c3c"))

    html += f"""<tr class="{tr_cls}">
<td>{i}</td>
<td><b>{h["Code"]}</b></td>
<td>{h["Name"]}</td>
<td>{h["Industry"][:4]}</td>
<td>{h["HoldDays"]}d</td>
<td class="{pnl_cls}">{h["EntryPrice"]:.2f}</td>
<td class="{pnl_cls}">{h["PnlPct"]:+.1f}%</td>
<td><span class="tag {tag_cls}">{h["EUS"]:.0f}</span>
<div class="bar"><div class="fill" style="width:{min(h["EUS"],100)}%;background:{bar_color}"></div></div></td>
<td>{h["TimeScore"]}</td>
<td>{h["ProfitScore"]}</td>
<td>{h["TechScore"]}</td>
<td>{h["FundScore"]}</td>
<td style="font-size:10px">{h["Action"]}</td>
</tr>"""

html += """</tbody></table></div>

<div class="sec">
<h2>一票退出明细</h2>
<table><thead><tr><th>代码</th><th>名称</th><th>盈亏</th><th>触发原因</th></tr></thead><tbody>
"""
one_vote_list = [h for h in holdings if h["OneVote"]]
if one_vote_list:
    for h in one_vote_list:
        html += f'<tr><td>{h["Code"]}</td><td>{h["Name"]}</td><td class="down">{h["PnlPct"]:+.1f}%</td><td>{h["OneVote"]}</td></tr>'
else:
    html += '<tr><td colspan="4" style="color:#999">未触发一票退出</td></tr>'

html += """</tbody></table></div>

<div class="sec">
<h2>规则卡片</h2>
<table style="font-size:11.5px">
<tr><th>维度</th><th>权重</th><th style="width:25%">低分(0)</th><th style="width:25%">中分(25-40)</th><th style="width:25%">高分(50-100)</th></tr>
<tr><td>时间因子</td><td>25%</td><td>1-5天</td><td>7-12天</td><td>15天+</td></tr>
<tr><td>盈亏状态</td><td>30%</td><td>-1%~+8%温和区间</td><td>-3%~-1%或+8%~+15%</td><td>≤-5%亏损或>+20%止盈</td></tr>
<tr><td>技术面</td><td>25%</td><td>价>MA20,均线多头</td><td>缩量滞涨或MA5<MA10</td><td>价<MA20×0.97,死叉</td></tr>
<tr><td>资金面</td><td>20%</td><td>温和放量/正常</td><td>不活跃/地量</td><td>放量下跌>3%</td></tr>
</table>
<p style="margin-top:10px;font-size:11px;color:#666">
EUS<20=持有 &nbsp;|&nbsp; 20-35=减半仓 &nbsp;|&nbsp; 35-50=退出2/3 &nbsp;|&nbsp; >50=全面退出 &nbsp;|&nbsp; 一票否决: -7%硬止损 / 超15天且亏>5% / 价<MA20×0.95
</p>
</div>
</body></html>
"""

os.makedirs(OUT_DIR, exist_ok=True)
out = os.path.join(OUT_DIR, f"eus_simulation_{datetime.now().strftime('%Y%m%d')}.html")
with open(out, "w", encoding="utf-8") as f: f.write(html)
print(f"\n报告: {out} ({os.path.getsize(out):,} bytes)")
