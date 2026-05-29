#!/usr/bin/env python3
"""generate_unified_view.py — 模拟交易统一视图生成器 v1.0

Aggregates all sim trading data into a single self-contained HTML page.
Usage: python3 generate_unified_view.py [--date YYYYMMDD]
Code level: L0
"""
import argparse
import json
import os
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = str(SCRIPT_DIR.parent.parent)


def load_json(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return None


def load_csv(path):
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        lines = f.read().strip().split("\n")
    if len(lines) < 2:
        return rows
    headers = lines[0].split(",")
    for line in lines[1:]:
        parts = line.split(",")
        if len(parts) >= 5:
            row = {headers[i]: parts[i] for i in range(min(len(headers), len(parts)))}
            rows.append(row)
    return rows


def collect_snapshots(root_dir):
    snap_dir = os.path.join(root_dir, "历史数据", "01_交易快照")
    if not os.path.exists(snap_dir):
        return []
    snaps = []
    for f in sorted(os.listdir(snap_dir)):
        if f.startswith("snapshot_") and f.endswith(".json") and "unified" not in f:
            data = load_json(os.path.join(snap_dir, f))
            if data:
                snaps.append(data)
    return snaps


def collect_transactions(root_dir):
    txn_file = os.path.join(root_dir, "历史数据", "00_核心交易", "transactions.csv")
    return load_csv(txn_file)


def collect_perf(root_dir):
    perf_file = os.path.join(root_dir, "历史数据", "00_核心交易", "perf_summary.json")
    return load_json(perf_file) or {}


def build_dashboard(snaps, perf):
    """Build cumulative dashboard data."""
    if not snaps:
        return {"current_value": 0, "total_return": 0, "benchmark_return": 0,
                "excess_return": 0, "max_drawdown": 0, "total_trades": 0,
                "win_rate": None, "position_count": 0}
    latest = snaps[-1]
    first = snaps[0]
    init_val = first.get("TotalValue", 1000000)
    cur_val = latest.get("TotalValue", 1000000)
    total_return = round((cur_val / 1000000 - 1) * 100, 2)
    bench_ret = latest.get("Benchmark", {}).get("BenchmarkReturnPct", 0)
    excess = round(total_return - bench_ret, 2)
    return {
        "current_value": cur_val,
        "total_return": total_return,
        "benchmark_return": bench_ret,
        "excess_return": excess,
        "max_drawdown": perf.get("MaxDrawdown") or 0,
        "total_trades": perf.get("TotalTrades", 0),
        "win_rate": perf.get("WinRate"),
        "position_count": latest.get("Positions", 0) if isinstance(latest.get("Positions"), int)
        else len(latest.get("Positions", {})),
    }


def build_net_value_points(snaps):
    """Build data points for net value chart."""
    if not snaps:
        return []
    points = []
    for s in snaps:
        val = round(s.get("TotalValue", 0))
        if val > 0:
            points.append({"date": s.get("Date", ""), "value": val})
    return points


def build_daily_cards(transactions, snaps, root_dir):
    """Build per-day trading cards."""
    # Group transactions by date
    txn_by_date = {}
    for t in transactions:
        d = t.get("date", "")
        if d:
            txn_by_date.setdefault(d, []).append(t)

    # Load strategy annotations
    anno_file = os.path.join(root_dir, "模拟交易", "分析", "strategy_annotations.json")
    annotations = load_json(anno_file) or {}

    # Build snapshot map
    snap_map = {s.get("Date", ""): s for s in snaps}

    cards = []
    # Collect all dates: transaction dates + snapshot dates (for no-trade observation days)
    all_dates_set = set(txn_by_date.keys()) | set(snap_map.keys())
    for date_str in sorted(all_dates_set):
        day_txns = txn_by_date.get(date_str, [])
        snap = snap_map.get(date_str, {})
        anno = annotations.get(date_str, {})

        # Classify day
        has_buy = any(t.get("action") == "BUY" for t in day_txns)
        has_sell = any(t.get("action") in ("SELL", "SELL_HALF") for t in day_txns)
        if has_buy and has_sell:
            day_type = "调仓"
        elif has_buy:
            day_type = "建仓"
        elif has_sell:
            day_type = "平仓"
        else:
            day_type = "观察"

        ops = []
        for t in day_txns:
            action = t.get("action", "")
            shares = int(float(t.get("shares", 0)))
            price = round(float(t.get("price", 0)), 2)
            total = round(float(t.get("total_cost", 0)), 2)
            reason = t.get("reason", "")
            name = t.get("name", "")
            code = t.get("code", "")

            if action == "BUY":
                desc = f"买入 {name}({code}) {shares}股 @ {price}"
            elif action == "SELL_HALF":
                desc = f"减仓50% {name}({code}) {shares}股 @ {price}"
            elif action == "SELL":
                desc = f"卖出 {name}({code}) {shares}股 @ {price}"
            else:
                desc = f"{action} {name} {shares}股"

            ops.append({
                "action": action, "shares": shares, "price": price,
                "total_cost": total, "reason": reason, "name": name, "code": code,
                "desc": desc,
            })

        # Positions from snapshot
        pos_list = []
        stock_details = snap.get("StockDetails", [])
        if not stock_details:
            pos_data = snap.get("Positions", {})
            if isinstance(pos_data, dict):
                stock_details = list(pos_data.values())
            else:
                stock_details = []
        for p in stock_details:
            pos_list.append({
                "name": p.get("Name", ""),
                "code": p.get("Code", ""),
                "shares": p.get("Shares", 0),
                "pnl": p.get("UnrealizedPnL", 0),
                "pnl_pct": p.get("UnrealizedPnLPct", 0),
            })

        cards.append({
            "date": date_str,
            "day_type": day_type,
            "total_value": snap.get("TotalValue", 0),
            "daily_return": snap.get("DailyReturn", 0),
            "operations": ops,
            "positions": pos_list,
            "thinking": anno.get("thinking", ""),
            "macro_note": anno.get("macro_note", ""),
            "event_note": anno.get("event_note", ""),
            "review": anno.get("review", ""),
        })

    return cards


def format_pnl(val):
    if val is None:
        return "—"
    sign = "+" if val > 0 else ""
    return f"{sign}{val:,.2f}"


def format_pct(val, default="—"):
    if val is None:
        return default
    sign = "+" if val > 0 else ""
    return f"{sign}{val}%"


def render_html(dashboard, net_points, cards, gen_date):
    """Render complete HTML page."""
    init_val = 1000000
    points_js = ",".join(f"{{x:{i},y:{p['value']}}}" for i, p in enumerate(net_points))

    # Collect unique stocks and dates for filter dropdowns
    stock_set = {}
    all_dates = []
    for card in cards:
        all_dates.append(card["date"])
        for op in card["operations"]:
            code = op["code"]
            name = op["name"]
            if code and code not in stock_set:
                stock_set[code] = name
    stock_options = "\n".join(
        f'<option value="{code}">{name} ({code})</option>'
        for code, name in stock_set.items()
    )
    date_options = "\n".join(
        f'<option value="{d}">{d[:4]}-{d[4:6]}-{d[6:]}</option>'
        for d in sorted(set(all_dates))
    )

    cards_html = ""
    for i, card in enumerate(cards):
        stock_codes = ",".join(set(op["code"] for op in card["operations"] if op["code"]))

        ops_html = ""
        if card["operations"]:
            for op in card["operations"]:
                cost_class = "buy" if op["action"] == "BUY" else "sell"
                ops_html += f"""
                <div class="op-row {cost_class}">
                    <span class="op-action">{op['action']}</span>
                    <span class="op-desc">{op['desc']}</span>
                    <span class="op-cost">{format_pnl(op['total_cost'])}</span>
                    <span class="op-reason">{op['reason']}</span>
                </div>"""
        else:
            ops_html = '<div class="op-row" style="color:#666;font-size:.85em;border-left-color:transparent;padding-left:8px">当日无操作（仅执行风控检查）</div>'

        pos_html = ""
        for p in card["positions"]:
            pct_sign = "+" if (p.get("pnl_pct") or 0) >= 0 else ""
            pnl_class = "positive" if (p.get("pnl") or 0) >= 0 else "negative"
            pos_html += f"""
                <div class="pos-row {pnl_class}">
                    <span>{p['name']}({p['code']})</span>
                    <span>{p['shares']}股</span>
                    <span>{format_pnl(p['pnl'])}</span>
                    <span>{pct_sign}{p.get('pnl_pct', 0)}%</span>
                </div>"""

        thinking = card["thinking"] or "<em>待复盘填充</em>"
        review = card.get("review", "")
        review_html = ""
        if review:
            review_html = f"""
                <div class="card-section review">
                    <h4>结果点评</h4>
                    <p>{review}</p>
                </div>"""

        cards_html += f"""
        <details class="day-card" data-date="{card['date']}" data-stocks="{stock_codes}" data-type="{card['day_type']}">
            <summary>
                <span class="card-date">{card['date']}</span>
                <span class="card-type type-{card['day_type']}">{card['day_type']}</span>
                <span class="card-value">净值 ¥{card['total_value']:,.0f}</span>
                <span class="card-return">{format_pct(card['daily_return'], '首日')}</span>
            </summary>
            <div class="card-body">
                <div class="card-section">
                    <h4>操作</h4>
                    {ops_html}
                </div>
                <div class="card-section">
                    <h4>持仓</h4>
                    {pos_html}
                </div>
                <div class="card-section thinking">
                    <h4>策略思路</h4>
                    <p>{thinking}</p>
                    {f'<p class="macro-note">宏观: {card["macro_note"]}</p>' if card.get("macro_note") else ''}
                    {f'<p class="event-note">事件: {card["event_note"]}</p>' if card.get("event_note") else ''}
                </div>
                {review_html}
            </div>
        </details>"""

    total_cards = len(cards)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>模拟交易统一视图 · {gen_date}</title>
<style>
:root{{
  --bg-primary:#1a1a2e;--bg-secondary:#16213e;--bg-card:#1f2b47;
  --text-primary:#e0e0e0;--text-secondary:#a0a0b8;--text-muted:#6a6a80;
  --accent-up:#e74c3c;--accent-down:#27ae60;--accent-warn:#f1c40f;
  --border:#2a3550;--radius-sm:8px;--radius-md:12px;
  --shadow-sm:0 1px 4px rgba(0,0,0,.2);--shadow-md:0 4px 16px rgba(0,0,0,.35);
}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:var(--bg-primary);color:var(--text-primary);line-height:1.6}}
.container{{max-width:960px;margin:0 auto;padding:24px 16px}}
h1{{font-size:1.5em;color:#fff;margin-bottom:4px}}
.subtitle{{color:var(--text-muted);font-size:.85em;margin-bottom:24px}}

/* Dashboard */
.dashboard{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:24px}}
.dash-card{{background:var(--bg-secondary);border-radius:8px;padding:16px;text-align:center}}
.dash-label{{font-size:.75em;color:var(--text-muted);text-transform:uppercase;margin-bottom:4px}}
.dash-value{{font-size:1.3em;font-weight:700;color:#fff}}
.dash-value.positive{{color:#e74c3c}}
.dash-value.negative{{color:#27ae60}}

/* Chart */
.chart-container{{background:var(--bg-secondary);border-radius:8px;padding:20px;margin-bottom:24px}}
.chart-container h3{{font-size:.85em;color:var(--text-muted);margin-bottom:12px;font-weight:400}}
canvas{{width:100%;height:200px;display:block}}

/* Filter bar */
.filter-bar{{background:var(--bg-secondary);border-radius:8px;padding:12px 16px;margin-bottom:16px}}
.filter-row{{display:flex;align-items:center;gap:12px;flex-wrap:wrap}}
.filter-label{{font-size:.75em;color:var(--text-muted)}}
.filter-select{{font-size:.8em;padding:4px 8px;border-radius:4px;border:1px solid rgba(255,255,255,.15);background:#1a1a2e;color:#ccc;cursor:pointer;min-width:100px}}
.filter-select:focus{{outline:none;border-color:#e74c3c}}
.filter-count{{font-size:.75em;color:#666;margin-left:auto}}

/* Day cards */
.day-card{{background:var(--bg-secondary);border-radius:8px;margin-bottom:8px;overflow:hidden}}
.day-card.hidden{{display:none}}
.day-card summary{{padding:12px 16px;cursor:pointer;display:flex;align-items:center;gap:12px;list-style:none}}
.day-card summary::-webkit-details-marker{{display:none}}
.day-card summary:hover{{background:rgba(255,255,255,.03)}}
.card-date{{font-weight:700;color:#fff;min-width:80px}}
.card-type{{font-size:.75em;padding:2px 8px;border-radius:4px;font-weight:600}}
.type-建仓{{background:rgba(231,76,60,.2);color:#e74c3c}}
.type-平仓{{background:rgba(39,174,96,.2);color:#27ae60}}
.type-调仓{{background:rgba(241,196,15,.2);color:#f1c40f}}
.type-观察{{background:rgba(255,255,255,.06);color:var(--text-muted)}}
.card-value{{margin-left:auto;color:#ccc;font-size:.9em}}
.card-return{{font-size:.9em;font-weight:600}}
.card-body{{padding:0 16px 16px}}
.card-section{{margin-top:12px}}
.card-section h4{{font-size:.8em;color:var(--text-muted);text-transform:uppercase;margin-bottom:6px;border-bottom:1px solid rgba(255,255,255,.06);padding-bottom:4px}}

/* Op rows */
.op-row{{display:flex;align-items:center;gap:8px;padding:4px 0;font-size:.85em;border-left:3px solid transparent;padding-left:8px;margin:2px 0}}
.op-row.buy{{border-left-color:#e74c3c}}
.op-row.sell{{border-left-color:#27ae60}}
.op-action{{font-weight:700;min-width:80px}}
.op-desc{{flex:1}}
.op-cost{{font-weight:600;min-width:100px;text-align:right}}
.op-reason{{color:var(--text-muted);font-size:.8em;min-width:120px;text-align:right}}

/* Pos rows */
.pos-row{{display:flex;gap:12px;font-size:.85em;padding:2px 0}}
.pos-row span{{min-width:80px}}
.pos-row span:first-child{{flex:1}}
.pos-row.positive{{color:#e74c3c}}
.pos-row.negative{{color:#27ae60}}

.thinking p{{font-size:.85em;color:#bbb;margin-top:4px}}
.review{{background:rgba(241,196,15,.05);border-radius:6px;padding:12px;margin-top:12px;border-left:3px solid #f1c40f}}
.review h4{{color:#f1c40f!important}}
.review p{{font-size:.85em;color:#ddd;margin-top:4px;line-height:1.7}}
.macro-note,.event-note{{font-size:.8em;color:#666;margin-top:2px}}

/* Footer */
.footer{{text-align:center;color:#555;font-size:.75em;margin-top:32px;padding:16px 0;border-top:1px solid rgba(255,255,255,.05)}}
</style>
</head>
<body>
<div class="container">
<h1>模拟交易统一视图</h1>
<p class="subtitle">初始资金 ¥{init_val:,} | 系统自动模拟每日开盘决策，基于评分信号执行买卖，仅供策略验证</p>

<div class="dashboard">
    <div class="dash-card">
        <div class="dash-label">当前净值</div>
        <div class="dash-value">¥{dashboard['current_value']:,.0f}</div>
    </div>
    <div class="dash-card">
        <div class="dash-label">累计收益率</div>
        <div class="dash-value {"positive" if dashboard['total_return'] > 0 else "negative"}">{format_pct(dashboard['total_return'])}</div>
    </div>
    <div class="dash-card">
        <div class="dash-label">超额收益(vs沪深300)</div>
        <div class="dash-value {"positive" if dashboard.get('excess_return', 0) > 0 else "negative"}">{format_pct(dashboard.get('excess_return'))}</div>
    </div>
    <div class="dash-card">
        <div class="dash-label">最大回撤</div>
        <div class="dash-value negative">{dashboard.get('max_drawdown', 0)}%</div>
    </div>
</div>

<div class="chart-container">
    <h3>净值曲线</h3>
    <canvas id="nvChart"></canvas>
</div>

<div class="filter-bar">
    <div class="filter-row">
        <span class="filter-label">日期</span>
        <select class="filter-select" id="filterDate">
            <option value="all">全部日期</option>
            {date_options}
        </select>
        <span class="filter-label">股票</span>
        <select class="filter-select" id="filterStock">
            <option value="all">全部股票</option>
            {stock_options}
        </select>
        <span class="filter-label">类型</span>
        <select class="filter-select" id="filterType">
            <option value="all">全部类型</option>
            <option value="建仓">建仓</option>
            <option value="平仓">平仓</option>
            <option value="调仓">调仓</option>
            <option value="观察">观察</option>
        </select>
        <span class="filter-count" id="filterCount">显示 {total_cards}/{total_cards} 天</span>
    </div>
</div>

<h2 style="font-size:1em;color:#fff;margin-bottom:12px">交易日操作</h2>
{cards_html}

<div class="footer">
    铁律量化 · 模拟交易系统 · 仅供策略验证和研究参考，不构成投资建议
</div>
</div>

<script>
(function(){{
    // --- Filter logic ---
    var cards = document.querySelectorAll('.day-card');
    var selDate = document.getElementById('filterDate');
    var selStock = document.getElementById('filterStock');
    var selType = document.getElementById('filterType');

    function applyFilters() {{
        var activeDate = selDate.value;
        var activeStock = selStock.value;
        var activeType = selType.value;
        var visible = 0;
        var total = cards.length;
        cards.forEach(function(card) {{
            var date = card.getAttribute('data-date');
            var stocks = card.getAttribute('data-stocks').split(',');
            var type = card.getAttribute('data-type');
            var dateMatch = activeDate === 'all' || date === activeDate;
            var stockMatch = activeStock === 'all' || stocks.indexOf(activeStock) !== -1;
            var typeMatch = activeType === 'all' || type === activeType;
            if (dateMatch && stockMatch && typeMatch) {{
                card.classList.remove('hidden');
                visible++;
            }} else {{
                card.classList.add('hidden');
            }}
        }});
        document.getElementById('filterCount').textContent = '显示 ' + visible + '/' + total + ' 天';
    }}

    selDate.addEventListener('change', applyFilters);
    selStock.addEventListener('change', applyFilters);
    selType.addEventListener('change', applyFilters);

    // --- Chart ---
    var canvas = document.getElementById('nvChart');
    if (!canvas) return;
    var ctx = canvas.getContext('2d');
    var dpr = window.devicePixelRatio || 1;
    var rect = canvas.parentElement.getBoundingClientRect();
    var W = rect.width, H = 200;
    canvas.width = W * dpr;
    canvas.height = H * dpr;
    canvas.style.width = W + 'px';
    canvas.style.height = H + 'px';
    ctx.scale(dpr, dpr);

    var points = [{points_js}];
    if (points.length < 2) {{
        ctx.fillStyle = '#888';
        ctx.font = '14px -apple-system,sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('数据不足，至少需要2个交易日', W/2, H/2);
        return;
    }}

    var pad = {{top:20, right:80, bottom:24, left:55}};
    var pw = W - pad.left - pad.right;
    var ph = H - pad.top - pad.bottom;

    var minV = points[0].y, maxV = points[0].y;
    for (var i = 1; i < points.length; i++) {{
        if (points[i].y < minV) minV = points[i].y;
        if (points[i].y > maxV) maxV = points[i].y;
    }}
    var baseLine = 1000000;
    var range = maxV - minV || 1000;
    minV = Math.min(minV, baseLine) - range * 0.15;
    maxV = Math.max(maxV, baseLine) + range * 0.15;
    range = maxV - minV;

    function x(i) {{ return pad.left + (i / (points.length - 1)) * pw; }}
    function y(v) {{ return pad.top + ph - ((v - minV) / range) * ph; }}

    // Background gradient
    var bgGrad = ctx.createLinearGradient(0, pad.top, 0, pad.top + ph);
    bgGrad.addColorStop(0, 'rgba(22,33,62,.6)');
    bgGrad.addColorStop(1, 'rgba(22,33,62,.2)');
    ctx.fillStyle = bgGrad;
    ctx.fillRect(pad.left, pad.top, pw, ph);

    // Grid lines + Y labels
    var gridLines = 4;
    for (var g = 0; g <= gridLines; g++) {{
        var gy = pad.top + (ph / gridLines) * g;
        var gv = maxV - (range / gridLines) * g;
        ctx.strokeStyle = 'rgba(255,255,255,.06)';
        ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(pad.left, gy); ctx.lineTo(pad.left + pw, gy); ctx.stroke();
        ctx.fillStyle = '#666';
        ctx.font = '10px -apple-system,sans-serif';
        ctx.textAlign = 'right';
        ctx.fillText('¥' + (gv / 10000).toFixed(1) + '万', pad.left - 6, gy + 3);
    }}

    // Baseline (¥1,000,000)
    var by = y(baseLine);
    ctx.strokeStyle = 'rgba(255,255,255,.18)';
    ctx.setLineDash([6, 4]);
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(pad.left, by); ctx.lineTo(pad.left + pw, by); ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = '#888';
    ctx.font = '10px -apple-system,sans-serif';
    ctx.textAlign = 'left';
    ctx.fillText('基准 ¥100万', pad.left + pw + 6, by + 3);

    // Area fill under line
    var areaGrad = ctx.createLinearGradient(0, pad.top, 0, pad.top + ph);
    areaGrad.addColorStop(0, 'rgba(231,76,60,.15)');
    areaGrad.addColorStop(1, 'rgba(231,76,60,.0)');
    ctx.fillStyle = areaGrad;
    ctx.beginPath();
    ctx.moveTo(x(0), pad.top + ph);
    for (var i = 0; i < points.length; i++) ctx.lineTo(x(i), y(points[i].y));
    ctx.lineTo(x(points.length - 1), pad.top + ph);
    ctx.closePath();
    ctx.fill();

    // Line
    ctx.strokeStyle = '#e74c3c';
    ctx.lineWidth = 2.2;
    ctx.lineJoin = 'round';
    ctx.beginPath();
    for (var i = 0; i < points.length; i++) {{
        var px = x(i), py = y(points[i].y);
        if (i === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
    }}
    ctx.stroke();

    // Dots + value labels + date labels
    for (var i = 0; i < points.length; i++) {{
        var px = x(i), py = y(points[i].y);
        // Outer glow
        ctx.fillStyle = 'rgba(231,76,60,.3)';
        ctx.beginPath(); ctx.arc(px, py, 6, 0, Math.PI * 2); ctx.fill();
        // Inner dot
        ctx.fillStyle = '#e74c3c';
        ctx.beginPath(); ctx.arc(px, py, 3.5, 0, Math.PI * 2); ctx.fill();
        // White center
        ctx.fillStyle = '#fff';
        ctx.beginPath(); ctx.arc(px, py, 1.5, 0, Math.PI * 2); ctx.fill();
        // Value label
        var labelY = py - 12;
        var valText = '¥' + (points[i].y / 10000).toFixed(1) + '万';
        ctx.fillStyle = '#e0e0e0';
        ctx.font = 'bold 11px -apple-system,sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(valText, px, labelY);
        // Date label
        var d = points[i].date;
        var dateText = d.slice(4, 6) + '/' + d.slice(6);
        ctx.fillStyle = '#888';
        ctx.font = '10px -apple-system,sans-serif';
        ctx.fillText(dateText, px, pad.top + ph + 16);
    }}

    // Title
    ctx.fillStyle = '#888';
    ctx.font = '11px -apple-system,sans-serif';
    ctx.textAlign = 'right';
    ctx.fillText('净值', pad.left + pw, pad.top - 6);
}})();
</script>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="Generate unified sim trading view")
    parser.add_argument("--date", default=datetime.now().strftime("%Y%m%d"), help="Run date")
    parser.add_argument("--root-dir", default=ROOT, help="Project root")
    parser.add_argument("--output", default="", help="Output path (default: 临时报告/)")
    args = parser.parse_args()

    root_dir = args.root_dir
    gen_date = args.date
    out_dir = os.path.join(root_dir, "docs", "sim_trading")
    os.makedirs(out_dir, exist_ok=True)
    out_path = args.output or os.path.join(out_dir, "模拟交易统一视图.html")

    print("收集数据...")
    snaps = collect_snapshots(root_dir)
    transactions = collect_transactions(root_dir)
    perf = collect_perf(root_dir)

    print(f"  快照: {len(snaps)} 个交易日")
    print(f"  交易: {len(transactions)} 条记录")

    dashboard = build_dashboard(snaps, perf)
    net_points = build_net_value_points(snaps)
    cards = build_daily_cards(transactions, snaps, root_dir)

    html = render_html(dashboard, net_points, cards, gen_date)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    trade_days = len(cards)
    print(f"\n统一视图已生成: {out_path}")
    print(f"  交易日: {trade_days} 天")
    print(f"  净值: ¥{dashboard['current_value']:,.0f} ({format_pct(dashboard['total_return'])})")


if __name__ == "__main__":
    main()
