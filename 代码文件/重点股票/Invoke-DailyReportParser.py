"""
日报→JSON数据提取器 — 按后评估白皮书v1.8 §3.7规范
等级: L0（工具/数据/缓存）
用法: python Invoke-DailyReportParser.py [YYYYMMDD] [output.json]
"""
import re, json, os, sys, glob

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

STOCK_MAP = {
    '600114': '东睦股份', '601727': '上海电气', '603019': '中科曙光',
    '301075': '多瑞医药', '601689': '拓普集团', '000967': '盈峰环境',
    '002230': '科大讯飞', '603092': '德力佳',
}

def extract(text, pattern, group=1, default=None):
    m = re.search(pattern, text)
    return m.group(group) if m else default

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

    # T+5 outlook
    t5_dir = extract(md, r'T\+5方向预判\s*\|\s*(看多|偏多|中性|偏空|看空)')
    t5_vs  = extract(md, r'T\+5相对大盘\s*\|\s*(有望跑赢|持平|可能跑输)')
    t5_con = extract(md, r'预判置信度\s*\|\s*(高|中|低)')

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

    # Quality markers
    field_sources = {
        'market_regime': regime, 'market_breadth': breadth,
        'ma_arrangement': ma_trend, 'adx': adx_v, 'rsi': rsi_v,
        'macd_signal': macd_s, 'volume_signal': vol_s,
        'bollinger_position': bb_p, 'fund_flow': fund_f,
        'wyckoff_stage': wyckoff_s, 'sector_pct': sector_p,
        'composite': comp_s, 'technical': tech_s, 'fundamental': fund_s,
        'sector': sect_s, 'capital': cap_s, 'macro': mac_s,
    }
    data_quality = {}
    for key, val in field_sources.items():
        if val is not None and val != '' and val != '—':
            data_quality[key] = 'C' if ('故障' in str(fund_status) and key == 'fund_flow') else 'OK'
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
            "S01": ma_trend == '多头排列', "S02": ma_trend == '空头排列',
            "S05": f(rsi_v) is not None and f(rsi_v) >= 70,
            "S06": f(rsi_v) is not None and f(rsi_v) < 30,
            "S07": f(rsi_v) is not None and 50 <= f(rsi_v) < 70,
            "S15": fund_f == '主力流入', "S16": fund_f == '主力流出',
            "S19": regime == '牛', "S20": regime == '熊', "S21": regime == '震荡',
            "S26": wyckoff_s == 'Accumulation', "S27": wyckoff_s == 'Markup',
            "S28": wyckoff_s == 'Distribution', "S29": wyckoff_s == 'Markdown',
        },
        "technical_values": {
            "adx": f(adx_v), "rsi": f(rsi_v),
            "ma_arrangement": ma_trend, "macd_signal": macd_s,
            "volume_signal": vol_s, "bollinger_position": bb_p,
            "wyckoff_stage": wyckoff_s, "fund_flow_direction": fund_f,
        },
        "price_levels": {
            "close": f(close_p), "R1": f(r1_p), "S1": f(s1_p), "S3": f(s3_p),
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
            "fund_flow": fund_status.strip() if fund_status else "正常 [9][10]",
        },
        "data_quality": data_quality,
        "t5_outlook": {
            "direction": t5_dir, "vs_market": t5_vs, "confidence": t5_con,
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
        report_path = os.path.join(report_dir, f'{name}({code})', f'{name}({code})分析日报_{date_str}.md')
        print(f"  解析: {name}({code})...", end=' ')
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
            "schema_ref": "重点股票次日后评估白皮书_v1.8 §3.7.2",
        },
        "stocks": stocks,
    }

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    size_kb = os.path.getsize(out_path) / 1024
    print(f"\nDone: {len(stocks)}只股票 -> {out_path} ({size_kb:.1f} KB)")


if __name__ == '__main__':
    main()
