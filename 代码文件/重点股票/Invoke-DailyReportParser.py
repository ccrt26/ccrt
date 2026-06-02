"""
日报→JSON数据提取器 v3.6 — 按后评估白皮书v1.8 §3.7 + 日报v3.6 schema
等级: L0（工具/数据/缓存）
v3.6升级: 四档资金/融资/北向新鲜度/信号胜率/风险标签/action_change/机器字段>=50项
用法: python Invoke-DailyReportParser.py [YYYYMMDD] [output.json]
"""
import re, json, os, sys, glob

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

STOCK_MAP = {
    '600114': '东睦股份', '601727': '上海电气', '603019': '中科曙光',
    '301075': '多瑞医药', '601689': '拓普集团', '000967': '盈峰环境',
    '002230': '科大讯飞', '603092': '德力佳',
    '300450': '先导智能', '300736': '百邦科技',
}

def extract(text, pattern, group=1, default=None):
    m = re.search(pattern, text)
    return m.group(group) if m else default


def _parse_number(s):
    """Extract numeric value from strings like '32元', '35.16(MA20)', '25.66元(S3)'"""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    m = re.search(r'([\d.]+)', str(s))
    return float(m.group(1)) if m else None


def _convert_stock_to_format_a(stock):
    """Convert a single stock from Format B (v3.6) to Format A (engine-compatible).

    Format A is expected by sim_trading.py: {"Stocks": [{"Code","Name","Price",
    "Rating","Scores":{"Composite"},"Signals", "KeyLevels":{"Support","StopLoss",
    "Resistance"},"TrendHealth":{"Label"},"Prediction":{"Short"}}]}
    """
    p0 = stock.get('p0_decision_card', {})
    pl = stock.get('price_levels', {})
    tv = stock.get('technical_values', {})
    sc = stock.get('scores', {})
    t5 = stock.get('t5_outlook', {})
    sig = stock.get('signals', {})

    close_price = pl.get('close')
    composite = sc.get('composite')
    if composite is None:
        composite = 50  # neutral default so data-quality gate passes

    # Key levels: parse from p0 string fields, fallback to price_levels
    new_sl = _parse_number(p0.get('new_position_stop_loss'))
    held_sl = _parse_number(p0.get('held_position_stop_loss'))
    stop_loss = new_sl or held_sl
    support = pl.get('S1') or _parse_number(p0.get('key_buy_point'))
    resistance = pl.get('R1')
    # Conservative fallback: if no stop-loss at all, use 90% of close (engine safety)
    if not stop_loss and close_price:
        stop_loss = round(close_price * 0.9, 2)
    if not support and close_price:
        support = round(close_price * 0.95, 2)

    # TrendHealth inference from Wyckoff stage
    wyckoff = tv.get('wyckoff_stage', '')
    if wyckoff in ('Markup', 'Accumulation'):
        th_label = '健康'
    elif wyckoff in ('Distribution', 'Markdown'):
        th_label = '警戒'
    else:
        th_label = '数据不足'

    # Rating mapping from P0 action
    action = p0.get('t1_action', '观望')
    rating_map = {'加仓': '买入', '试探': '谨慎买入', '观望': '谨慎', '减仓': '卖出', '清仓': '卖出'}
    rating = rating_map.get(action, '谨慎')

    # Build signals (Format A uses boolean dict)
    signals_a = {}
    if sig:
        signals_a = {k: v for k, v in sig.items() if v}

    # Truncate Prediction.Short to keyword only (strip trailing commentary)
    direction = t5.get('direction', '中性') or '中性'
    for kw in ['看多', '偏多', '中性', '偏空', '看空']:
        if direction.startswith(kw):
            direction = kw
            break

    return {
        'Code': stock.get('code'),
        'Name': stock.get('name'),
        'Price': close_price,
        'Rating': rating,
        'Industry': '',
        'Scores': {'Composite': composite},
        'Signals': signals_a,
        'KeyLevels': {
            'Support': support,
            'StopLoss': stop_loss,
            'Resistance': resistance,
        },
        'TrendHealth': {'Label': th_label},
        'Prediction': {'Short': direction},
        'Date': '',
    }

def _merge_stocks(json_stock, md_stock):
    """Null-fill JSON sidecar stock with MD-parsed data. JSON is authoritative for P0 decisions."""
    if md_stock is None:
        return json_stock
    # scores
    for k in json_stock['scores']:
        if json_stock['scores'][k] is None:
            json_stock['scores'][k] = md_stock['scores'].get(k)
    # signals: prefer MD (regex-extracted boolean signals are richer)
    if md_stock.get('signals') and not json_stock.get('signals'):
        json_stock['signals'] = md_stock['signals']
    # technical_values
    for k in json_stock['technical_values']:
        if json_stock['technical_values'][k] is None:
            json_stock['technical_values'][k] = md_stock['technical_values'].get(k)
    # price_levels
    for k in json_stock['price_levels']:
        if json_stock['price_levels'][k] is None:
            json_stock['price_levels'][k] = md_stock['price_levels'].get(k)
    # p0_decision_card
    for k in json_stock['p0_decision_card']:
        if json_stock['p0_decision_card'][k] is None:
            json_stock['p0_decision_card'][k] = md_stock['p0_decision_card'].get(k)
    # Recalculate data_quality after merge
    dq = {}
    for key, val in json_stock['v36_machine_fields'].items():
        dq[key] = 'OK' if (val is not None and val != '' and val != '—') else 'MISS'
    # Augment with scores/technicals quality
    for key in ['composite', 'technical', 'fundamental', 'sector', 'fund_flow', 'macro']:
        dq[f'score_{key}'] = 'OK' if json_stock['scores'].get(key) is not None else 'MISS'
    for key in ['adx', 'rsi', 'ma_arrangement', 'macd_signal', 'volume_signal']:
        dq[f'tech_{key}'] = 'OK' if json_stock['technical_values'].get(key) is not None else 'MISS'
    json_stock['data_quality'] = dq
    return json_stock


def parse_from_json_sidecar(json_path, code, name):
    """v3.6.1: 从JSON sidecar直接加载所有字段"""
    if not os.path.exists(json_path):
        return None
    with open(json_path, 'r', encoding='utf-8') as f:
        j = json.load(f)
    if j.get('stock_code') != code:
        return None

    # 直接从JSON sidecar映射到stock结构
    p0 = j.get('p0_decision_card', {})
    mf = j.get('machine_fields', {})
    ff = j.get('fund_flow_4level', {})
    risk = j.get('risk_light', {})
    baseline = j.get('baseline', {})
    dc = j.get('data_completeness', {})
    dsc = j.get('data_source_check', {})

    # Extract price levels: delta.close + baseline key support/resistance
    bs = baseline.get('key_support', {})
    br = baseline.get('key_resistance', {})
    stock = {
        "code": code, "name": name,
        "daily_report_path": json_path,
        "source": "json_sidecar",
        "scores": {"composite": None, "technical": None, "fundamental": None,
                   "news": None, "sector": None, "fund_flow": None, "macro": None},
        "signals": {},
        "technical_values": {
            "adx": mf.get('adx_value'), "rsi": mf.get('rsi_value'),
            "ma_arrangement": mf.get('ma_arrangement'), "macd_signal": mf.get('macd_signal'),
            "volume_signal": mf.get('volume_signal'), "bollinger_position": mf.get('bollinger_position'),
            "wyckoff_stage": mf.get('wyckoff_stage'), "fund_flow_direction": mf.get('fund_flow_direction'),
        },
        "price_levels": {
            "close": j.get('delta', {}).get('close'),
            "R1": _parse_number(br.get('R1')),
            "S1": _parse_number(bs.get('S1')),
            "S3": _parse_number(bs.get('S3')),
        },
        "p0_decision_card": {
            "t1_action": p0.get('t1_action'), "current_position_cap": p0.get('current_position_cap'),
            "triggered_position": p0.get('triggered_position_cap'),
            "key_buy_point": p0.get('key_buy_point'),
            "forbidden_actions": str(p0.get('forbidden_actions', '')),
            "new_position_stop_loss": p0.get('new_position_stop_loss'),
            "held_position_stop_loss": p0.get('held_position_stop_loss'),
            "confidence_level": p0.get('confidence_level'),
            "action_change": j.get('action_change'),
        },
        "fund_flow_4level": {
            "super_large_net": ff.get('super_large_net'), "large_net": ff.get('large_net'),
            "medium_net": ff.get('medium_net') or ff.get('mid_small_net'),
            "small_net": ff.get('small_net'),
            "main_force_net": ff.get('main_force_net') or ff.get('main_force_total'),
            "mid_small_net": ff.get('mid_small_net'), "main_force_total": ff.get('main_force_total'),
            "structure_judgment": ff.get('structure_judgment'),
        },
        "margin_trading": {"balance": None, "change": None, "signal": mf.get('margin_signal')},
        "northbound": {"daily_status": None, "quarterly_date": None, "status": mf.get('northbound_status')},
        "signal_winrate": j.get('signal_winrate', []),
        "risk_flags": {
            "pledge": {"ratio": None, "light": risk.get('pledge')},
            "unlock": {"days": None, "light": risk.get('unlock')},
            "holder_trend": None, "block_trade_discount": None,
        },
        "data_completeness": {
            "overall_pct": dc.get('overall_pct'), "fresh_count": None, "stale_count": None, "missing_count": None,
        },
        "daily_report_sections": {"scenario_table": [], "no_do_list": [], "stop_loss_check": {}, "health_labels": {}},
        "data_source_status": {"kline_technical": dsc.get('kline', {}).get('status', '正常'),
                               "financial": dsc.get('financial', {}).get('status', '正常'),
                               "fund_flow_4level": dsc.get('fund_flow_4level', {}).get('status', '正常'),
                               "margin": dsc.get('margin', {}).get('status', '正常'),
                               "northbound": dsc.get('northbound', {}).get('status', '正常')},
        "data_quality": {k: 'OK' if v else 'MISS' for k, v in mf.items()},
        "t5_outlook": {"direction": mf.get('t5_direction'), "vs_market": None, "target_range": None, "confidence": None, "key_checkpoint": None},
        "v36_machine_fields": mf,
    }

    # ── v3.6.2: enrich with deep analysis baseline if available ─
    _enrich_from_deep_baseline(stock, os.path.dirname(json_path), code)

    return stock


def _enrich_from_deep_baseline(stock, report_dir, code):
    """Read 深度分析_baseline_*.json if present and fill null fields with real data."""
    if not os.path.isdir(report_dir):
        return
    baseline_files = sorted(
        [f for f in os.listdir(report_dir)
         if f.startswith(f'{stock["name"]}({code})深度分析_baseline_') or
            f.startswith(f'深度分析_baseline_')],
        reverse=True,
    )
    if not baseline_files:
        return
    baseline_path = os.path.join(report_dir, baseline_files[0])
    try:
        with open(baseline_path, 'r', encoding='utf-8') as f:
            bl = json.load(f)
    except Exception:
        return

    kl = bl.get('key_levels', {})
    # Override price_levels with real key levels (null → baseline value)
    for field, bl_key in [('R1', 'R1'), ('S1', 'S1'), ('S3', 'S3')]:
        if stock['price_levels'].get(field) is None:
            v = kl.get(bl_key)
            if v is not None:
                stock['price_levels'][field] = v

    # Override stop loss with baseline values
    p0 = stock['p0_decision_card']
    if p0.get('new_position_stop_loss') is None:
        sl = kl.get('stop_loss_new')
        if sl is not None:
            p0['new_position_stop_loss'] = f'{sl}元'
    if p0.get('held_position_stop_loss') is None:
        sl = kl.get('stop_loss_held')
        if sl is not None:
            p0['held_position_stop_loss'] = f'{sl}元'

    # Enrich scores from baseline
    cs = bl.get('composite_score')
    if cs is not None and stock['scores']['composite'] is None:
        stock['scores']['composite'] = cs
    sd = bl.get('score_detail', {})
    for k in ['technical', 'fundamental', 'sector', 'fund_flow', 'macro', 'news']:
        if stock['scores'].get(k) is None and sd.get(k) is not None:
            stock['scores'][k] = sd[k]

    # Enrich signals from baseline
    bl_signals = bl.get('signal_labels', {})
    if bl_signals and not stock.get('signals'):
        stock['signals'] = {k: True for k in bl.get('signals', {}).keys() if bl['signals'].get(k)}

    # Enrich tech values: trend health, wyckoff
    if stock['technical_values'].get('wyckoff_stage') is None:
        th = bl.get('trend_health', '')
        thd = bl.get('trend_health_detail', '')
        if 'Markdown' in thd:
            stock['technical_values']['wyckoff_stage'] = 'Markdown'
        elif 'Distribution' in thd:
            stock['technical_values']['wyckoff_stage'] = 'Distribution'
        elif 'Markup' in thd:
            stock['technical_values']['wyckoff_stage'] = 'Markup'
        elif 'Accumulation' in thd:
            stock['technical_values']['wyckoff_stage'] = 'Accumulation'

    # Enrich prediction and rating
    pred = bl.get('prediction_short')
    if pred and stock['t5_outlook'].get('direction') is None:
        stock['t5_outlook']['direction'] = pred
    rating = bl.get('rating')
    if rating and stock['p0_decision_card'].get('t1_action') == '观望':
        stock['p0_decision_card']['t1_action'] = {'买入': '加仓', '谨慎买入': '试探', '卖出': '减仓'}.get(rating, rating)

def parse_daily_report(path, code, name):
    if not os.path.exists(path):
        print(f"  [MISS] {name}({code}): 日报文件不存在")
        return None

    with open(path, 'r', encoding='utf-8') as f:
        md = f.read()

    # Scores
    comp_s = extract(md, r'综合评分\*\*(\d+)分')
    tech_s = extract(md, r'技术(\d+)分')
    fund_s = extract(md, r'基本面(\d+)分')
    news_s = extract(md, r'消息(\d+)分')
    sect_s = extract(md, r'板块(\d+)分')
    cap_s  = extract(md, r'资金(\d+)分')
    mac_s  = extract(md, r'宏观(\d+)分')

    # HTML eval comments (v1.8)
    regime    = extract(md, r'<!-- eval:market_regime=(\S+) -->')
    breadth   = extract(md, r'<!-- eval:market_breadth=([\d.]+) -->')
    ma_trend  = extract(md, r'<!-- eval:ma_arrangement=(\S+) -->')
    adx_v     = extract(md, r'<!-- eval:adx_value=([\d.]+) -->')
    rsi_v     = extract(md, r'<!-- eval:rsi_value=([\d.]+) -->')
    macd_s    = extract(md, r'<!-- eval:macd_signal=(\S+) -->')
    vol_s     = extract(md, r'<!-- eval:volume_signal=(\S+) -->')
    bb_p      = extract(md, r'<!-- eval:bollinger_position=(\S+) -->')
    fund_f    = extract(md, r'<!-- eval:fund_flow_direction=(\S+) -->')
    wyckoff_s = extract(md, r'<!-- eval:wyckoff_stage=(\S+) -->')
    sector_p  = extract(md, r'<!-- eval:sector_pct=([\d.]+) -->')

    # Fallback: visible text regex
    if not ma_trend:
        ma_trend = extract(md, r'MA排列\s*\|\s*(多头排列|空头排列|交叉)')
    if not adx_v:
        adx_v = extract(md, r'ADX\(14\)\s*\|\s*([\d.]+)')
    if not rsi_v:
        rsi_v = extract(md, r'RSI\(9\)\s*\|\s*([\d.]+)')
    if not wyckoff_s:
        wyckoff_s = extract(md, r'Wyckoff阶段\s*\|\s*(Accumulation|Markup|Distribution|Markdown)')
    if not fund_f:
        fund_f = extract(md, r'主力.*?\|\s*(主力流入|主力流出)')
    if not bb_p:
        bb_p = extract(md, r'BB\(20,2\)\s*\|\s*(\S+)')

    # Price levels
    close_p = extract(md, r'收盘\*\*([\d.]+)元\*\*')
    r1_p    = extract(md, r'\*\*R1\*\*.*?\|\s*([\d.]+)\|')
    s1_p    = extract(md, r'\*\*S1\*\*.*?\|\s*([\d.]+)\|')
    s3_p    = extract(md, r'\*\*S3\*\*.*?\|\s*([\d.]+)\|')

    # Data source status
    fund_status = extract(md, r'资金数据\s*\|\s*\[[^\]]+\]\s*\|\s*(.+?)\s*$', default='正常 [9][10]')

    # === v3.6 新增: P0决策卡字段 ===
    t1_action = extract(md, r'\*?\*?明日主动作\*?\*?\s*\|\s*`?(观望|试探|加仓|减仓|清仓|暂停观察)`?')
    pos_cap   = extract(md, r'\*?\*?当前仓位上限\*?\*?\s*\|\s*`?([\d.]+%[^`\n]*)`?')
    pos_trig  = extract(md, r'\*?\*?条件触发后仓位\*?\*?\s*\|\s*`?(.+?)`?\s*(?:\n|$)')
    buy_point = extract(md, r'\*?\*?关键买点\*?\*?\s*\|\s*`?(.+?)`?\s*(?:\n|$)')
    forbid    = extract(md, r'\*?\*?禁止动作\*?\*?\s*\|\s*`?(.+?)`?\s*(?:\n|$)')
    new_sl    = extract(md, r'\*?\*?新仓止损\*?\*?\s*\|\s*`?(.+?)`?\s*(?:\n|$)')
    held_sl   = extract(md, r'\*?\*?已持仓止损\*?\*?\s*\|\s*`?(.+?)`?\s*(?:\n|$)')
    conf_level = extract(md, r'\*?\*?置信度\*?\*?\s*\|\s*`?高?(?:\(?>?70%\))?\s*(高|中|低)')
    action_chg = extract(md, r'\*?\*?action_change\*?\*?\s*\|\s*`?(upgrade|unchanged|downgrade|stop_watch|reanalysis_required)`?')

    # === v3.6 新增: 四档资金结构 ===
    super_large_net = extract(md, r'\*?\*?超大单净额\*?\*?\s*\|\s*`?([\d.,+\-−]*万)`?')
    large_net = extract(md, r'(?<!超)\*?\*?大单净额\*?\*?\s*\|\s*`?([\d.,+\-−]*万)`?')
    mid_small_net = extract(md, r'\*?\*?中小单净额\*?\*?\s*\|\s*`?([\d.,+\-−]*万)`?')
    main_force_total = extract(md, r'\*?\*?主力合计\*?\*?\s*\|\s*\*?\*?\s*`?([\d.,+\-−]*万)`?')
    fund_structure = extract(md, r'\*?\*?结构判断\*?\*?\s*\|\s*\*?\*?\s*`?(大资金撤.*?散户接|资金认可|资金分歧|抛压释放|共识|分歧)`?')

    # === v3.6 新增: 融资融券(禁止写不可获取) ===
    margin_bal = extract(md, r'融资余额\s*\|\s*([\d.]+亿)')
    margin_chg = extract(md, r'融资变化\s*\|\s*([+-][\d.]+亿)')
    margin_signal = extract(md, r'融资信号\s*\|\s*(加杠杆|去杠杆|稳定|上升|下降)')

    # === v3.6 新增: 北向新鲜度 ===
    nb_daily_status = extract(md, r'\*?\*?北向大盘日频\*?\*?\s*\|\s*`?(fresh|stale|missing)[^`\n]*`?')
    nb_quarterly_date = extract(md, r'北向个股季度.*?截止\s*(\d{4}-\d{2}-\d{2})')
    northbound_status = extract(md, r'<!-- eval:northbound_status=(\S+) -->')

    # === v3.6 新增: 信号胜率表 ===
    signal_rows = re.findall(r'\|\s*(TECH_\d+|FUND_\d+|S\d+)\s*\|\s*(.+?)\s*\|\s*(\d+)\s*\|\s*([\d.]+)%\s*\|', md)

    # === v3.6 新增: 风险标签 ===
    pledge_ratio = extract(md, r'质押比例\s*\|\s*([\d.]+%)')
    pledge_light = extract(md, r'质押风控\s*\|\s*([🔴🟡🟢])')
    unlock_days = extract(md, r'距解禁\s*\|\s*(\d+)日')
    unlock_light = extract(md, r'解禁风控\s*\|\s*([🔴🟡🟢])')
    holder_trend = extract(md, r'股东人数趋势\s*\|\s*(集中|分散|持平)')
    block_trade_discount = extract(md, r'大宗折价\s*\|\s*([\d.]+%)')

    # === v3.6 新增: 数据完整度 ===
    data_completeness_pct = extract(md, r'数据完整度\s*\|\s*([\d.]+%)')
    data_fresh_count = extract(md, r'fresh\s*\|\s*(\d+)/')
    data_stale_count = extract(md, r'stale\s*\|\s*(\d+)/')
    data_missing_count = extract(md, r'missing\s*\|\s*(\d+)')

    # === v3.6 新增: T+5展望 ===
    t5_dir = extract(md, r'T\+5方向预判\s*\|\s*(看多|偏多|中性|偏空|看空)')
    t5_vs  = extract(md, r'T\+5相对大盘\s*\|\s*(有望跑赢|持平|可能跑输)')
    t5_target = extract(md, r'T\+5目标区间\s*\|\s*([\d.]+元\s*[-–]\s*[\d.]+元)')
    t5_con = extract(md, r'预判置信度\s*\|\s*(高|中|低)')
    t5_key_check = extract(md, r'关键验证点\s*\|\s*(.+?)(?:\n|$)')

    # === v3.6 新增: 机器字段（HTML注释格式，v3.5兼容）===
    baseline_id = extract(md, r'<!-- eval:baseline_id=(\S+) -->')
    reanalysis = extract(md, r'<!-- eval:reanalysis_required=(true|false) -->')
    fund_flow_structure = extract(md, r'<!-- eval:fund_flow_structure=(\S+) -->')
    margin_signal_eval = extract(md, r'<!-- eval:margin_signal=(\S+) -->')
    sector_rank_pct = extract(md, r'<!-- eval:sector_rank_percentile=([\d.]+) -->')
    ma_arrangement = extract(md, r'<!-- eval:ma_arrangement=(\S+) -->')
    bollinger_position = extract(md, r'<!-- eval:bollinger_position=(\S+) -->')
    wyckoff_stage = extract(md, r'<!-- eval:wyckoff_stage=(\S+) -->')
    market_regime = extract(md, r'<!-- eval:market_regime=(\S+) -->')
    market_breadth = extract(md, r'<!-- eval:market_breadth=([\d.]+) -->')

    # === v3.6 新增: 机器字段（编号表格式fallback，v3.6报告使用）===
    mf_table = {}
    for m in re.finditer(r'\|\s*(\d+)\s*\|\s*`(\w+)`\s*\|\s*`([^`]*)`\s*\|', md):
        mf_table[m.group(2)] = m.group(3).strip()
    # Fallback: use table values if HTML comment extraction returned None
    if not baseline_id:
        baseline_id = mf_table.get('baseline_id')
    if not reanalysis:
        reanalysis = mf_table.get('reanalysis_required')
    if not fund_flow_structure:
        fund_flow_structure = mf_table.get('fund_flow_structure')
    if not margin_signal_eval:
        margin_signal_eval = mf_table.get('margin_signal')
    if not sector_rank_pct:
        sector_rank_pct = mf_table.get('sector_rank_percentile')
    if not ma_arrangement:
        ma_arrangement = mf_table.get('ma_arrangement')
    if not bollinger_position:
        bollinger_position = mf_table.get('bollinger_position')
    if not wyckoff_stage:
        wyckoff_stage = mf_table.get('wyckoff_stage')
    if not market_regime:
        market_regime = mf_table.get('market_regime')
    if not market_breadth:
        market_breadth = mf_table.get('market_breadth')
    # v3.6 fields that are only in table format
    report_version = mf_table.get('report_version')
    risk_light = mf_table.get('risk_light')
    data_quality_status = mf_table.get('data_quality_status')
    add_price = mf_table.get('add_position_price')
    reduce_price = mf_table.get('reduce_position_price')

    # Health labels
    tech_h = extract(md, r'技术面\s*\|\s*\d+\s*\|\s*\[(.)\]')
    fund_h = extract(md, r'基本面\s*\|\s*\d+\s*\|\s*\[(.)\]')
    sect_h = extract(md, r'板块\s*\|\s*\d+\s*\|\s*\[(.)\]')
    cap_h  = extract(md, r'资金面\s*\|\s*\d+\s*\|\s*\[(.)\]')
    comp_h = extract(md, r'\*\*综合\*\*\s*\|\s*\*\*\d+\*\*\s*\|\s*\*\*\[(.)\]')

    # No-do list
    def no_do_triggered(pattern):
        val = extract(md, pattern)
        return val in ('是!', '是')

    no_do = [
        {"rule": "追涨买入(RSI>80/距S1>5%)", "triggered": no_do_triggered(r'追涨买入.*?\|.*?(是!|是|否)')},
        {"rule": "亏损加仓", "triggered": no_do_triggered(r'亏损加仓.*?\|.*?(是!|是|否)')},
        {"rule": "财报前3日开新仓", "triggered": no_do_triggered(r'财报前3日.*?\|.*?(是!|是|否|待确认)')},
        {"rule": "RSI>80加仓", "triggered": no_do_triggered(r'RSI>80加仓.*?\|.*?(是!|是|否)')},
        {"rule": "单一板块>50%", "triggered": no_do_triggered(r'单一板块>50%.*?\|.*?(是!|是|否)')},
    ]

    # Quality markers (v3.6: expanded to >=50 fields)
    field_sources = {
        'market_regime': market_regime, 'market_breadth': market_breadth,
        'ma_arrangement': ma_arrangement, 'adx': adx_v, 'rsi': rsi_v,
        'macd_signal': macd_s, 'volume_signal': vol_s,
        'bollinger_position': bollinger_position, 'fund_flow': fund_f,
        'wyckoff_stage': wyckoff_stage, 'sector_pct': sector_p,
        'composite': comp_s, 'technical': tech_s, 'fundamental': fund_s,
        'sector': sect_s, 'capital': cap_s, 'macro': mac_s,
        # v3.6 新增
        't1_action': t1_action, 'action_change': action_chg,
        'confidence_level': conf_level, 'baseline_id': baseline_id,
        'fund_flow_structure': fund_flow_structure,
        'super_large_net': super_large_net, 'large_net': large_net,
        'mid_small_net': mid_small_net, 'main_force_total': main_force_total,
        'fund_structure_judgment': fund_structure,
        'margin_balance': margin_bal, 'margin_signal': margin_signal or margin_signal_eval,
        'northbound_daily': nb_daily_status, 'northbound_quarterly_date': nb_quarterly_date,
        'pledge_ratio': pledge_ratio, 'pledge_light': pledge_light,
        'unlock_days': unlock_days, 'unlock_light': unlock_light,
        'holder_trend': holder_trend,
        'data_completeness': data_completeness_pct,
        't5_direction': t5_dir, 't5_vs_market': t5_vs,
        't5_target': t5_target, 't5_confidence': t5_con,
        'reanalysis_required': reanalysis,
        'sector_rank_percentile': sector_rank_pct,
    }
    data_quality = {}
    for key, val in field_sources.items():
        if val is not None and val != '' and val != '—':
            data_quality[key] = 'OK'
        else:
            data_quality[key] = 'MISS'

    def i(s):
        return int(s) if s else None

    def f(s):
        return float(s) if s else None

    stock = {
        "code": code, "name": name,
        "daily_report_path": path,
        "scores": {
            "composite": i(comp_s), "technical": i(tech_s),
            "fundamental": i(fund_s), "news": i(news_s),
            "sector": i(sect_s), "fund_flow": i(cap_s), "macro": i(mac_s),
        },
        "signals": {
            "S01": ma_arrangement == '多头排列', "S02": ma_arrangement == '空头排列',
            "S05": f(rsi_v) is not None and f(rsi_v) >= 70,
            "S06": f(rsi_v) is not None and f(rsi_v) < 30,
            "S07": f(rsi_v) is not None and 50 <= f(rsi_v) < 70,
            "S15": fund_f == '主力流入', "S16": fund_f == '主力流出',
            "S19": market_regime == '牛', "S20": market_regime == '熊', "S21": market_regime == '震荡',
            "S26": wyckoff_stage == 'Accumulation', "S27": wyckoff_stage == 'Markup',
            "S28": wyckoff_stage == 'Distribution', "S29": wyckoff_stage == 'Markdown',
        },
        "technical_values": {
            "adx": f(adx_v), "rsi": f(rsi_v),
            "ma_arrangement": ma_arrangement, "macd_signal": macd_s,
            "volume_signal": vol_s, "bollinger_position": bollinger_position,
            "wyckoff_stage": wyckoff_stage, "fund_flow_direction": fund_f,
        },
        "price_levels": {
            "close": f(close_p), "R1": f(r1_p), "S1": f(s1_p), "S3": f(s3_p),
        },
        # === v3.6 新增: P0决策卡 ===
        "p0_decision_card": {
            "t1_action": t1_action,
            "current_position_cap": pos_cap,
            "triggered_position": pos_trig,
            "key_buy_point": buy_point,
            "forbidden_actions": forbid,
            "new_position_stop_loss": new_sl,
            "held_position_stop_loss": held_sl,
            "confidence_level": conf_level,
            "action_change": action_chg,
        },
        # === v3.6 新增: 四档资金结构 ===
        "fund_flow_4level": {
            "super_large_net": super_large_net,
            "large_net": large_net,
            "mid_small_net": mid_small_net,
            "main_force_total": main_force_total,
            "structure_judgment": fund_structure,
        },
        # === v3.6 新增: 融资融券 ===
        "margin_trading": {
            "balance": margin_bal,
            "change": margin_chg,
            "signal": margin_signal or margin_signal_eval,
        },
        # === v3.6 新增: 北向资金(区分日频/季度) ===
        "northbound": {
            "daily_status": nb_daily_status,
            "quarterly_date": nb_quarterly_date,
            "status": northbound_status,
        },
        # === v3.6 新增: 信号胜率 ===
        "signal_winrate": [
            {"signal_id": s[0], "name": s[1].strip(), "sample_count": int(s[2]), "win_rate": float(s[3])}
            for s in signal_rows
        ],
        # === v3.6 新增: 风险标签 ===
        "risk_flags": {
            "pledge": {"ratio": pledge_ratio, "light": pledge_light},
            "unlock": {"days": unlock_days, "light": unlock_light},
            "holder_trend": holder_trend,
            "block_trade_discount": block_trade_discount,
        },
        # === v3.6 新增: 数据完整度 ===
        "data_completeness": {
            "overall_pct": data_completeness_pct,
            "fresh_count": data_fresh_count,
            "stale_count": data_stale_count,
            "missing_count": data_missing_count,
        },
        "daily_report_sections": {
            "scenario_table": [],
            "no_do_list": no_do,
            "stop_loss_check": {"S1_breached": False, "S3_breached": False},
            "health_labels": {
                "technical": tech_h, "fundamental": fund_h,
                "sector": sect_h, "fund_flow": cap_h, "composite": comp_h,
            },
        },
        "data_source_status": {
            "kline_technical": "正常 [2]->[5]",
            "financial": "正常 [3]",
            "sector": "正常 [7]",
            "fund_flow_4level": "正常 [9]" if super_large_net else "降级",
            "margin": "正常 [12]" if margin_bal else "降级",
            "northbound": "正常 [8]" if nb_daily_status else "降级",
        },
        "data_quality": data_quality,
        # === v3.6: T+5展望 + 机器字段 ===
        "t5_outlook": {
            "direction": t5_dir, "vs_market": t5_vs, "target_range": t5_target,
            "confidence": t5_con, "key_checkpoint": t5_key_check,
        },
        "v36_machine_fields": {
            "report_version": report_version or "3.6.0",
            "baseline_id": baseline_id,
            "action_change": action_chg,
            "confidence_level": conf_level,
            "data_completeness": data_completeness_pct,
            "market_regime": market_regime,
            "market_breadth": market_breadth,
            "ma_arrangement": ma_arrangement,
            "adx_value": adx_v,
            "rsi_value": rsi_v,
            "macd_signal": macd_s,
            "volume_signal": vol_s,
            "fund_flow_direction": fund_f,
            "fund_flow_structure": fund_flow_structure or fund_structure,
            "margin_signal": margin_signal or margin_signal_eval,
            "northbound_status": northbound_status or nb_daily_status,
            "sector_rank_percentile": sector_rank_pct,
            "wyckoff_stage": wyckoff_stage,
            "bollinger_position": bollinger_position,
            "t1_action": t1_action or mf_table.get('t1_action') or mf_table.get('p0_action'),
            "t5_direction": t5_dir or mf_table.get('t5_direction'),
            "reanalysis_required": reanalysis or mf_table.get('reanalysis_required'),
            "risk_light": risk_light or mf_table.get('risk_light'),
            "data_quality_status": data_quality_status or mf_table.get('data_quality_status'),
            "add_position_price": add_price or mf_table.get('add_position_price'),
            "reduce_position_price": reduce_price or mf_table.get('reduce_position_price'),
            "stock_code": code,
            "trade_date": mf_table.get('trade_date'),
        },
    }
    return stock


def main():
    date_str = sys.argv[1] if len(sys.argv) > 1 else None
    out_path = sys.argv[2] if len(sys.argv) > 2 else None

    if not date_str:
        from datetime import date
        date_str = date.today().strftime('%Y%m%d')

    report_dir = os.path.join(ROOT, '重点股票', '股票报告')
    eval_dir = os.path.join(ROOT, '重点股票', '次日评估')

    if not out_path:
        out_path = os.path.join(eval_dir, f'评估数据_{date_str}.json')

    print(f"Invoke-DailyReportParser — 日报→JSON提取 ({date_str})")

    stocks = []
    for code, name in STOCK_MAP.items():
        stock_dir = os.path.join(report_dir, f'{name}({code})')
        # v3.6.1: JSON sidecar优先，然后v3.6.1 MD，然后v3.6 MD，最后旧版
        candidate_patterns = [
            f'{name}({code})日报_{date_str}.json',            # JSON sidecar（最优先）
            f'{name}({code})日报_{date_str}.md',              # 用户版Markdown
            f'{name}({code})日报_v3.6.3_{date_str}.json',    # v3.6.3 JSON（兼容）
            f'{name}({code})日报_v3.6.3_{date_str}.md',      # v3.6.3 MD（兼容）
            f'{name}({code})日报_v3.6_{date_str}.json',       # v3.6 JSON（兼容）
            f'{name}({code})日报_v3.6_{date_str}.md',         # v3.6 MD（兼容）
            f'{name}({code})分析日报_{date_str}.md',          # 旧版命名
            f'{name}({code})日报_{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}.md',  # 带分隔线
        ]
        report_path = None
        tried = []
        for pat in candidate_patterns:
            full = os.path.join(stock_dir, pat)
            tried.append(full)
            if os.path.exists(full):
                report_path = full
                break

        print(f"  解析: {name}({code})...", end=' ')
        if not report_path:
            print(f"[MISS] 尝试过: {', '.join(os.path.basename(p) for p in tried)}")
            continue

        stock = None
        if report_path.endswith('.json'):
            stock = parse_from_json_sidecar(report_path, code, name)
            # JSON sidecar sparse-check: if no baseline key-levels or no stop-loss, try MD merge
            pl = stock.get('price_levels', {}) if stock else {}
            p0 = stock.get('p0_decision_card', {}) if stock else {}
            is_sparse = (not pl.get('S1') and not pl.get('R1')) or \
                        (not p0.get('new_position_stop_loss') and not p0.get('held_position_stop_loss'))
            if is_sparse and stock:
                md_path = report_path.replace('.json', '.md')
                if os.path.exists(md_path):
                    md_stock = parse_daily_report(md_path, code, name)
                    if md_stock:
                        stock = _merge_stocks(stock, md_stock)
        else:
            stock = parse_daily_report(report_path, code, name)
        if stock:
            stocks.append(stock)
            ok = sum(1 for v in stock['data_quality'].values() if v == 'OK')
            miss = sum(1 for v in stock['data_quality'].values() if v == 'MISS')
            print(f"[OK] {ok}字段提取, {miss}缺失")
        else:
            print("[SKIP]")

    output = {
        "meta": {
            "date": date_str,
            "generated_by": "Invoke-DailyReportParser.py",
            "source": "重点股票/股票报告/",
            "stock_count": len(stocks),
            "schema_ref": "重点股票跟踪分析逻辑白皮书_v3.6.3",
        },
        "stocks": stocks,
        "Stocks": [_convert_stock_to_format_a(s) for s in stocks],
    }

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    size_kb = os.path.getsize(out_path) / 1024
    print(f"\nDone: {len(stocks)}只股票 -> {out_path} ({size_kb:.1f} KB)")


if __name__ == '__main__':
    main()
