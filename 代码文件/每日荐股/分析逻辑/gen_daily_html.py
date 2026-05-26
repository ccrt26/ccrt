#!/usr/bin/env python3
"""Generate daily stock recommendation report (landscape HTML).
Replaces gen_daily_html.ps1 — identical output, Python-native UTF-8.
"""
import argparse, json, os, sys, subprocess
from datetime import datetime

# ── Constants ──────────────────────────────────────────
PHASE_ORDER = {"潜伏期": 0, "主升调整": 1, "高潮期": 2, "衰退期": 3}

CSS = """@page{size:landscape;margin:12mm 15mm}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:"Microsoft YaHei","PingFang SC","Noto Sans SC",sans-serif;background:#f4f5f7;color:#333;padding:24px}
.container{max-width:100%;margin:0 auto}
.hdr{background:#1a1a2e;color:#fff;padding:36px 44px;border-radius:12px;margin-bottom:22px}
.hdr h1{font-size:36px;font-weight:900;margin-bottom:14px}
.hdr .sub{font-size:20px;font-weight:700;display:flex;justify-content:space-between;margin-top:0;color:#fff}
.hdr .tag{font-size:18px;font-weight:600;margin-top:14px;color:#fff;line-height:1.8}
.sec{background:#fff;border-radius:10px;padding:22px;margin-bottom:18px;box-shadow:0 1px 6px rgba(0,0,0,.06)}
.sec h2{font-size:17px;font-weight:700;margin-bottom:14px;padding-bottom:8px;border-bottom:2px solid #1a1a2e}
table{width:100%;border-collapse:collapse;font-size:12px}
th{background:#f0f2f5;padding:7px 8px;text-align:center;font-weight:600;border-bottom:2px solid #ddd;font-size:11px}
td{padding:6px 8px;text-align:center;border-bottom:1px solid #eee;font-size:11.5px}
.card-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.card{border:1px solid #e6e8ed;border-radius:10px;padding:20px 24px;background:#fafbfc}
.c-hdr{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}
.c-name{font-size:22px;font-weight:700}.c-code{font-size:13px;color:#999;margin-left:8px}
.c-scr{font-size:32px;font-weight:800;color:#1a1a2e}.c-scr span{font-size:14px;font-weight:400;color:#aaa}
.c-meta{display:flex;gap:10px;margin-bottom:12px;flex-wrap:wrap}
.c-meta-item{font-size:14px;background:#edf0f7;padding:5px 14px;border-radius:14px}
.c-logic{font-size:14px;color:#444;margin-top:12px;padding:12px 16px;background:#f2f6ff;border-radius:6px;border-left:3px solid #4a6cf7;line-height:1.6}
.s-bar{height:7px;background:#eee;border-radius:4px;margin-top:12px;overflow:hidden}.s-fill{height:100%;border-radius:4px}
.src-tag{font-size:10px;color:#999;font-weight:400;margin-left:1px;white-space:nowrap}
.bg-green{background:#2ecc71}.bg-yellow{background:#f39c12}.bg-red{background:#e74c3c}
.up{color:#e74c3c;font-weight:600}.down{color:#27ae60;font-weight:600}
.tag{display:inline-block;padding:2px 8px;border-radius:8px;font-size:10px;font-weight:600}
.t-green{background:#d4edda;color:#155724}.t-yellow{background:#fff3cd;color:#856404}.t-red{background:#f8d7da;color:#721c24}
.note{border-left:4px solid #1a1a2e;background:#f8f9fa;padding:10px 14px;border-radius:0 8px 8px 0;margin:10px 0;font-size:12px;line-height:1.6}
.ftr{text-align:center;font-size:11px;color:#aaa;padding:16px 0;line-height:1.8}
.sc-high{background:#d4edda;font-weight:700}.sc-mid{background:#fff3cd;font-weight:600}
.row-2{display:flex;gap:14px;margin-bottom:0}.row-2 .col{flex:1;min-width:0}
@media print{body{background:#fff;padding:15px}.sec{box-shadow:none;border:1px solid #ddd;page-break-inside:avoid}}"""

CATALYST_MAP = {
    "宁德时代": "固太电池储能", "豪威集团": "半导体CIS", "阳光电源": "EU能源电网",
    "五粮液": "消费催化", "恒生电子": "数字人民币", "金山办公": "AI办公",
    "比亚迪": "新车周期", "北方华创": "国产替代", "海康威视": "AI安防",
    "贵州茅台": "消费复苏", "招商银行": "高股息", "汇川技术": "工控周期",
    "昆仑万维": "AI应用", "科大讯飞": "大模型",
}
INDUSTRY_CATALYST = {"计算机": "数字中国", "电子": "半导体周期", "通信": "算力基建"}

# ── Helpers ────────────────────────────────────────────

def fmt_pct(v, signed=True):
    if v is None: return "N/A"
    if signed and v >= 0: return f"+{v:.2f}%"
    return f"{v:.2f}%"

def get_phase_name(avg_chg, avg_turn, count):
    if count <= 0: return "衰退期"
    if avg_turn > 5 and avg_chg > 2: return "高潮期"
    if avg_turn > 3 and avg_chg < -3: return "衰退期"
    if avg_turn > 3 and avg_chg > 0: return "主升调整"
    if avg_turn > 2 and avg_chg < -1: return "主升调整"
    if avg_chg >= -1.5 and avg_turn <= 4: return "潜伏期"
    if avg_chg >= -2 and avg_turn <= 2: return "潜伏期"
    return "潜伏期"

def get_phase_advice(p):
    if p == "潜伏期": return ("提前埋伏", "t-green")
    if p == "主升调整": return ("持有不加仓", "t-yellow")
    return ("减仓回避", "t-red")

def get_phase_emoji(p):
    return {"潜伏期": "🟢", "高潮期": "🔴", "衰退期": "🔴"}.get(p, "🟡")

def get_short_phase(p):
    return {"潜伏期": "潜伏", "主升调整": "主升", "高潮期": "高潮", "衰退期": "衰退"}.get(p, p)

def get_catalyst(name, industry):
    if name in CATALYST_MAP: return CATALYST_MAP[name]
    if industry in INDUSTRY_CATALYST: return INDUSTRY_CATALYST[industry]
    return None

def get_reason_text(s, phase_info):
    parts = []
    tech_desc = s.get("TechAnalysis")
    if not tech_desc:
        ma_parts = []
        ma5, ma10, ma20 = s.get("MA5"), s.get("MA10"), s.get("MA20")
        if ma5 and ma10 and ma20 and ma5 > 0:
            if ma5 > ma10 > ma20: ma_parts.append("均线多头排列")
            elif ma10 <= ma20: ma_parts.append("均线收敛")
            else: ma_parts.append("均线偏多")
            ma_parts.append(f"MA5={ma5:.1f} MA10={ma10:.1f} MA20={ma20:.1f}")
            rsi = s.get("RSI")
            if rsi is not None:
                rsi = round(rsi)
                if rsi >= 60: ma_parts.append(f"RSI{rsi}偏强")
                elif rsi <= 40: ma_parts.append(f"RSI{rsi}偏弱")
                else: ma_parts.append(f"RSI{rsi}中性")
            macd = s.get("MACD_Status")
            if macd: ma_parts.append(f"MACD{macd}")
        if ma_parts: tech_desc = " | ".join(ma_parts)
    if tech_desc: parts.append(f"技术面：{tech_desc}")

    if phase_info:
        adv, _ = get_phase_advice(phase_info["phase"])
        parts.append(f"板块：{phase_info['name']}处于{phase_info['phase']}，建议{adv}")

    cat = get_catalyst(s.get("Name", ""), s.get("Industry", ""))
    if cat:
        parts.append(f"催化：{cat}")
    elif phase_info and phase_info.get("avgChg", 0) > 3:
        parts.append("催化：板块整体走强，资金关注度提升")
    else:
        parts.append("催化：行业基本面支撑")
    return " | ".join(parts)

def get_source_tag(field, field_sources):
    if field in field_sources: return f'<sup class="src-tag">{field_sources[field]}</sup>'
    return ""

def get_tier_info(s, phase_info, trend_map):
    phase = phase_info["phase"] if phase_info else "潜伏期"
    trend_score = 0
    ind = s.get("Industry", "")
    if trend_map:
        ti = trend_map.get(ind)
        if not ti:
            for sub, broad in BROAD_TO_EM.items():
                if broad == ind and sub in trend_map:
                    ti = trend_map[sub]; break
        if ti: trend_score = ti.get("trend_score", 0)
    if phase == "潜伏期" and trend_score >= 4:
        return {"tier": "A", "label": "蓄势埋伏", "tclass": "t-green", "desc": "优先关注·未来1-2周布局窗口"}
    if phase == "主升调整" and trend_score >= 6:
        return {"tier": "B", "label": "趋势跟踪", "tclass": "t-yellow", "desc": "顺势而为·主线板块动量延续"}
    if phase == "高潮期":
        return {"tier": "C", "label": "高潮回避", "tclass": "t-red", "desc": "板块过热·技术面已打折"}
    return {"tier": "B", "label": "趋势跟踪", "tclass": "t-yellow", "desc": "关注·注意追涨风险"}

def test_c8_block(s, phase_map):
    pi = phase_map.get(s.get("Industry", ""))
    phase = pi["phase"] if pi else "潜伏期"
    return s.get("ChangePct", 0) > 7 and phase != "潜伏期"

# ── Main ────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate daily stock recommendation HTML report")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"), help="Report date (yyyy-MM-dd)")
    parser.add_argument("--data-file", default="", help="Path to data_scored.json")
    parser.add_argument("--out-dir", default="", help="Output directory")
    parser.add_argument("--skip-pdf", action="store_true", help="Skip PDF generation")
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))

    data_file = args.data_file or os.path.join(root_dir, "代码文件", "数据", "data_scored.json")
    out_dir = args.out_dir or os.path.join(root_dir, "每日荐股", "股票报告")
    os.makedirs(out_dir, exist_ok=True)

    with open(data_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    all_stocks = data.get("AllStocks", [])
    summary = data.get("Summary")
    field_sources = data.get("FieldSources", {})
    sector_phase_map = data.get("SectorPhaseMap")
    sector_trend_map = data.get("SectorTrendMap", {})

    if not all_stocks:
        print("No stocks in data", file=sys.stderr)
        sys.exit(1)
    stocks = all_stocks

    # Load industry map
    global BROAD_TO_EM
    BROAD_TO_EM = {}
    ind_map_file = os.path.join(root_dir, "代码文件", "数据", "eastmoney_sector_map.json")
    industry_map = {}
    if os.path.exists(ind_map_file):
        with open(ind_map_file, "r", encoding="utf-8") as f:
            im = json.load(f)
        industry_map = im.get("Map", {})
        for em, broad in industry_map.items():
            BROAD_TO_EM.setdefault(broad, []).append(em)

    # Sector phase computation
    from collections import defaultdict
    sector_groups = defaultdict(list)
    for s in stocks:
        sector_groups[s.get("Industry", "未知")].append(s)

    sector_rows = []
    for name, group in sector_groups.items():
        sp = sector_phase_map.get(name) if sector_phase_map else None
        if not sp:
            for sub in BROAD_TO_EM.get(name, []):
                if sector_phase_map and sub in sector_phase_map:
                    sp = sector_phase_map[sub]; break
        if sp:
            ac, at, p = sp["avg_chg"], sp["avg_turn"], sp["phase"]
        else:
            ac = sum(g.get("ChangePct", 0) for g in group) / len(group) if group else 0
            at = sum(g.get("TurnoverRate", 0) for g in group) / len(group) if group else 0
            p = get_phase_name(ac, at, len(group))
        adv, tag_cls = get_phase_advice(p)
        sector_rows.append({"name": name, "count": len(group), "avgChg": ac,
                           "avgTurn": at, "phase": p, "advice": adv, "tagClass": tag_cls})

    sector_rows.sort(key=lambda r: (PHASE_ORDER.get(r["phase"], 9), -abs(r["avgChg"])))
    phase_map = {r["name"]: r for r in sector_rows}

    # Trend map
    trend_map = sector_trend_map

    # Score and tier
    scored = []
    for s in stocks:
        pi = phase_map.get(s.get("Industry", ""))
        ti = get_tier_info(s, pi, trend_map)
        tier_order = {"A": 0, "B": 1, "C": 2}.get(ti["tier"], 2)
        c8 = test_c8_block(s, phase_map)
        scored.append({"s": s, "total": s.get("TotalScore", 0), "tier": ti,
                       "tierOrder": tier_order, "c8Block": c8})

    scored.sort(key=lambda x: (x["tierOrder"], -x["total"]))

    # Top 5: A档 force at least 2
    a_stocks = [x for x in scored if x["tier"]["tier"] == "A"]
    non_a = [x for x in scored if x["tier"]["tier"] != "A" and not x["c8Block"]]
    top5 = a_stocks[:2]
    top5 += non_a[:5 - len(top5)]

    # --- Build HTML ---
    # Sector table
    sector_html_parts = []
    for r in sector_rows:
        cc = "up" if r["avgChg"] >= 0 else "down"
        emoji = get_phase_emoji(r["phase"])
        cs = f"+{r['avgChg']:.2f}%" if r["avgChg"] >= 0 else f"{r['avgChg']:.2f}%"
        sector_html_parts.append(
            f'<tr><td style="font-weight:600">{r["name"]}</td><td>{r["count"]}</td>'
            f'<td class="{cc}">{cs}</td><td>{r["avgTurn"]:.2f}%</td>'
            f'<td>{emoji} {r["phase"]}</td>'
            f'<td><span class="tag {r["tagClass"]}">{r["advice"]}</span></td></tr>')
    sector_html = "\n".join(sector_html_parts)

    # Top 5 cards
    card_parts = []
    for item in top5:
        s = item["s"]
        ti = item["tier"]
        cc = "up" if s.get("ChangePct", 0) >= 0 else "down"
        pi = phase_map.get(s.get("Industry", ""), {})
        pl = pi.get("phase", "") if pi else ""
        ptc = pi.get("tagClass", "t-green") if pi else "t-green"
        cs = f"+{s.get('ChangePct',0):.2f}%" if s.get("ChangePct", 0) >= 0 else f"{s.get('ChangePct',0):.2f}%"
        reason = get_reason_text(s, pi)
        tier_badge = f'<span class="tag {ti["tclass"]}" style="font-size:11px;margin-right:6px">{ti["tier"]}档·{ti["label"]}</span>'
        card_parts.append(
            f'<div class="card"><div class="c-hdr"><div><span class="c-name">{s.get("Name","")}</span>'
            f'<span class="c-code">{s.get("Code","")}</span></div><div>{tier_badge}'
            f'<span class="tag {ptc}">{pl}</span><span class="c-scr" style="margin-left:10px">{item["total"]}<span>/100</span></span></div></div>'
            f'<div class="c-meta"><span class="c-meta-item">{s.get("Industry","")}</span>'
            f'<span class="c-meta-item">{s.get("Price","")}{get_source_tag("Price",field_sources)}元</span>'
            f'<span class="c-meta-item {cc}">{cs}{get_source_tag("ChangePct",field_sources)}</span>'
            f'<span class="c-meta-item">换手{s.get("TurnoverRate","")}{get_source_tag("TurnoverRate",field_sources)}%</span>'
            f'<span class="c-meta-item">PE {s.get("PE","")}{get_source_tag("PE",field_sources)}</span></div>'
            f'<div class="c-logic">{reason}</div>'
            f'<div class="s-bar"><div class="s-fill bg-green" style="width:{item["total"]}%"></div></div></div>')
    card_html = "\n".join(card_parts)

    # Full table (top 25)
    full_parts = []
    for rank, item in enumerate(scored[:25], 1):
        s = item["s"]
        ti = item["tier"]
        cc = "up" if s.get("ChangePct", 0) >= 0 else "down"
        ts = s.get("TotalScore", 0)
        sc = "sc-high" if ts >= 60 else ("sc-mid" if ts >= 48 else "")
        star = "⭐⭐" if ts >= 60 else ("⭐" if ts >= 48 else "")
        pi2 = phase_map.get(s.get("Industry", ""), {})
        sp = get_short_phase(pi2["phase"]) if pi2 else ""
        em2 = get_phase_emoji(pi2["phase"]) if pi2 else ""
        cs = f"+{s.get('ChangePct',0):.2f}%" if s.get("ChangePct", 0) >= 0 else f"{s.get('ChangePct',0):.2f}%"
        st_trend = s.get("S_SectorTrend") or 0
        tier_label = f"{ti['tier']}档"
        full_parts.append(
            f'<tr><td>{rank}</td><td>{s.get("Code","")}</td>'
            f'<td style="font-weight:600;text-align:left;padding-left:8px">{s.get("Name","")}</td>'
            f'<td>{s.get("Industry","")}</td><td>{s.get("Price","")}{get_source_tag("Price",field_sources)}</td>'
            f'<td class="{cc}">{cs}{get_source_tag("ChangePct",field_sources)}</td>'
            f'<td>{s.get("TurnoverRate","")}{get_source_tag("TurnoverRate",field_sources)}%</td>'
            f'<td>{s.get("Amplitude","")}%</td><td>{s.get("PE","")}{get_source_tag("PE",field_sources)}</td>'
            f'<td>{s.get("S_Base","")}</td><td>{s.get("S_Fund","")}</td><td>{s.get("S_Tech","")}</td>'
            f'<td>{s.get("S_Money","")}</td><td>{s.get("S_News","")}</td><td>{s.get("S_Risk","")}</td>'
            f'<td>{st_trend}</td><td class="{sc}">{ts}</td><td>{star}</td>'
            f'<td><span class="tag {ti["tclass"]}">{tier_label}</span></td><td>{em2}{sp}</td></tr>')
    full_html = "\n".join(full_parts)

    # Sector trend table
    trend_parts = []
    if sector_trend_map:
        trend_items = []
        for key, info in sector_trend_map.items():
            trend_items.append({
                "sector_name": info.get("sector_name", key),
                "trend_score": info.get("trend_score", 0),
                "is_main": info.get("is_long_term_main_line", False),
                "kline_avail": info.get("sector_kline_available", False),
            })
        trend_items.sort(key=lambda x: x["trend_score"], reverse=True)
        for t in trend_items:
            main_tag = '<span class="tag t-green">★主线</span>' if t["is_main"] else '<span class="tag t-yellow">轮动</span>'
            kline_tag = '<span class="tag t-green">有</span>' if t["kline_avail"] else '<span class="tag t-red">无</span>'
            trend_parts.append(
                f'<tr><td style="font-weight:600">{t["sector_name"]}</td><td>{t["trend_score"]}分</td>'
                f'<td>{main_tag}</td><td>{kline_tag}</td></tr>')
        sector_trend_html = "\n".join(trend_parts)
    else:
        sector_trend_html = '<tr><td colspan="4" style="color:#999">暂无板块趋势持续性数据（SectorTrendMap 为空）</td></tr>'

    total_count = summary.get("Total", len(all_stocks)) if summary else len(all_stocks)
    vetoed_count = summary.get("Vetoed", 0) if summary else 0

    # Assemble full HTML
    date_str = args.date
    html = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<title>铁律量化 · 每日股票推荐 {date_str}</title><style>{CSS}</style></head><body><div class="container">

<div class="hdr"><h1>铁律量化 · 每日股票推荐</h1>
<div class="sub"><span>{date_str} 收盘</span><span>七维前向评分体系 v2.9</span></div>
<div class="tag">动态池: {total_count}只 | 通过否决: {len(all_stocks)}只 | 否决: {vetoed_count}只 | 推荐上限: 25只 | 否决制+七维评分 | 板块轮动选股</div></div>

<div class="sec"><h2>板块轮动速览</h2><table><tr><th>板块</th><th>股票</th><th>平均涨跌</th><th>平均换手</th><th>轮动相位</th><th>操作建议</th></tr>{sector_html}</table></div>

<div class="sec"><h2>板块趋势持续性 <span style="font-size:12px;color:#999;font-weight:400">(v2.9 · 20分制 五因子+相位折扣)</span></h2><table><tr><th>板块</th><th>持续性评分</th><th>主线判定</th><th>K线数据</th></tr>{sector_trend_html}</table></div>

<div class="sec"><h2>精选推荐 Top 5</h2>
<div class="note" style="border-left-color:#1a1a2e;margin-bottom:14px"><strong>v2.9 推荐分层：</strong>
<span class="tag t-green">A档·蓄势埋伏</span> 潜伏期板块+蓄势充分→<strong>强制Top5席位≥2只</strong>，优先关注·未来1-2周布局窗口 |
<span class="tag t-yellow">B档·趋势跟踪</span> 主升/主线板块→顺势而为，注意追涨风险 |
<span class="tag t-red">C档·高潮回避</span> 高潮期板块→技术面已打55折，减仓回避 |
<strong>C8拦截</strong>：当日>7%且非潜伏期→不进Top5</div>
<div class="note" style="border-left-color:#2ecc71"><strong>评分理念：</strong>一票否决制(14条规则)先筛除不合格股票→通过者按七维总分排序→取前5只展示推荐理由。总分=基础(10)+基本面(15)+技术面(20)+资金面(20)+消息面(15)+风控(5)+板块趋势(20)=105上限100分。v2.9相位折扣扩展至技术面+资金面+消息面三项(潜伏×1.0/主升×0.75/高潮×0.55)+C8单日追涨拦截。</div>
<div class="card-grid">{card_html}</div></div>

<div class="sec"><h2>全部标的评分表</h2><div style="overflow-x:auto"><table>
<tr><th>#</th><th>代码</th><th>名称</th><th>行业</th><th>价格</th><th>涨跌</th><th>换手</th><th>振幅</th><th>PE</th><th>基础</th><th>基本</th><th>技术</th><th>资金</th><th>消息</th><th>风控</th><th>趋势</th><th>总分</th><th>评级</th><th>分层</th><th>状态</th></tr>{full_html}</table></div></div>

<div class="row-2"><div class="col"><div class="sec"><h2>数据来源</h2><table>
<tr><th style="width:22%">数据</th><th style="width:28%">来源</th><th>说明</th></tr>
<tr><td style="font-weight:600">个股行情</td><td>腾讯行情</td><td>实时价格、涨跌幅、换手率</td></tr>
<tr><td style="font-weight:600">板块数据</td><td>东方财富板块API</td><td>行业板块指数+资金流向真实市场数据，计算轮动相位</td></tr>
<tr><td style="font-weight:600">行业归属</td><td>申万一级行业</td><td>{total_count}只股票覆盖{len(sector_rows)}个行业</td></tr>
<tr><td style="font-weight:600">评分计算</td><td>本地计算</td><td>七维前向评分体系 v2.9</td></tr></table></div></div>
<div class="col"><div class="sec"><h2>免责声明</h2>
<div style="font-size:11px;color:#666;line-height:1.6">本报告由铁律量化系统自动生成，仅供学习研究参考，不构成投资建议。股票投资有风险，过往表现不预示未来收益。请理性投资，风险自担。<br><span style="color:#999">铁律量化 · v2.9 · {date_str} 收盘</span></div></div></div></div>

<div class="ftr"><strong>免责声明</strong><br>本报告由铁律量化系统自动生成，仅供学习研究参考，不构成投资建议。<br>股票投资有风险，过往表现不预示未来收益。<br><br>铁律量化 · v2.9 · {date_str} 收盘</div>
</div></body></html>"""

    # Write output
    dc = date_str.replace("-", "")
    html_file = os.path.join(out_dir, f"daily_report_{dc}.html")
    with open(html_file, "w", encoding="utf-8") as f:
        f.write(html)
    html_size = os.path.getsize(html_file)
    if html_size < 10000:
        print(f"FAILED: HTML too small ({html_size} bytes)", file=sys.stderr)
        sys.exit(1)
    print(f"[OK] HTML: {html_file} ({html_size} bytes)")

    if not args.skip_pdf:
        edge = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
        pdf_file = os.path.join(out_dir, f"每日股票推荐_{dc}_landscape.pdf")
        if os.path.exists(edge):
            subprocess.run([
                edge, "--headless", "--disable-gpu",
                f"--print-to-pdf={pdf_file}",
                f"--print-to-pdf-landscape=true",
                html_file
            ], capture_output=True)
            if os.path.exists(pdf_file):
                pdf_size = os.path.getsize(pdf_file)
                print(f"[OK] PDF:  {pdf_file} ({pdf_size} bytes)")
            else:
                print(f"FAILED: PDF generation failed at {pdf_file}", file=sys.stderr)
                sys.exit(1)
        else:
            print("Edge not found, skip PDF generation", file=sys.stderr)


if __name__ == "__main__":
    main()
