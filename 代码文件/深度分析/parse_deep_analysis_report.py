"""
深度分析报告解析器 — Markdown → 评估数据JSON
L0 工具模块。读取深度分析报告Markdown，提取结构化评估数据。
用法: python parse_deep_analysis_report.py <report_md_path> [--output <json_path>]
"""
import re, json, sys, os
from datetime import datetime

# Windows console UTF-8 fix
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

def extract_version(text):
    """提取方法论版本声明"""
    m = re.search(r'方法论版本[^v]*(v[\d.]+)', text)
    return m.group(1) if m else None

def extract_scores(text):
    """提取六维评分 + 综合评分（从§七综合评分表）"""
    scores = {}
    # 模式: **X** 或 | X | 格式
    patterns = {
        'fundamental': r'基本面[^\d]*?\*?\*?(\d+)\*?\*?',
        'technical': r'技术面[^\d]*?\*?\*?(\d+)\*?\*?',
        'fund_flow': r'资金面[^\d]*?\*?\*?(\d+)\*?\*?',
        'sector': r'行业面[^\d]*?\*?\*?(\d+)\*?\*?',
        'valuation': r'估值[^\d]*?\*?\*?(\d+)\*?\*?',
        'risk_control': r'风控[^\d]*?\*?\*?(\d+)\*?\*?',
    }
    for key, pat in patterns.items():
        m = re.search(pat, text)
        if m:
            scores[key] = int(m.group(1))

    # 综合评分
    m = re.search(r'加权综合[^\d]*?\*?\*?([\d.]+)\*?\*?', text)
    if m:
        scores['composite'] = float(m.group(1))

    return scores if len(scores) >= 4 else None

def extract_market_judgment(text):
    """提取市场阶段判断"""
    result = {}
    m = re.search(r'市场阶段判断[^:：]*[：:]\s*(牛|熊|震荡)[\s\w]*[初早中末]', text)
    if m:
        result['regime'] = m.group(1)
    else:
        m = re.search(r'(牛市|熊市|震荡市)', text)
        if m: result['regime'] = m.group(1).replace('市','')

    m = re.search(r'(初期|中期|末期)', text)
    if m: result['phase'] = m.group(1)

    m = re.search(r'(价值|成长|均衡|大小盘)\s*(偏强|偏弱|占优)', text)
    if m: result['style'] = m.group(0)

    return result if result else None

def extract_industry_judgment(text):
    """提取行业判断五维"""
    result = {}
    patterns = {
        'lifecycle': r'行业生命周期[^\n]*?[：:]\s*(导入|成长|成熟|衰退)',
        'demand': r'下游需求[^\n]*?[：:]\s*(增长|稳定|萎缩)',
        'raw_material': r'原材料成本[^\n]*?[：:]\s*(有利|中性|不利)',
        'policy': r'政策面[^\n]*?[：:]\s*(利好|中性|利空)',
        'competition': r'竞争格局[^\n]*?[：:]\s*(集中|分散[→]集中|分散)',
    }
    for key, pat in patterns.items():
        m = re.search(pat, text)
        if m: result[key] = m.group(1)
    return result if result else None

def extract_catalysts(text):
    """提取催化剂表（§一.4）"""
    catalysts = []
    # 查找催化剂表格区域
    cat_section = re.search(r'催化剂强制识别.*?(?=\n##|\n---|\Z)', text, re.DOTALL)
    if not cat_section: return catalysts

    section = cat_section.group(0)
    # 匹配表格行: | S/A/B/C | 描述 | 类别 | 状态 | 概率 | 影响 | 来源 |
    rows = re.findall(r'\|\s*([SABC])\s*\|\s*(.+?)\s*\|\s*(并购|订单|政策|产品|管理层|其他)\s*\|\s*(已落地|待落地|落空)\s*\|\s*(\d+)%\s*\|\s*([±]?\d+%)\s*\|\s*(.+?)\s*\|', section)
    for r in rows:
        catalysts.append({
            'level': r[0],
            'description': r[1].strip(),
            'category': r[2],
            'status': r[3],
            'probability': int(r[4]) / 100.0,
            'expected_impact': r[5],
            'source': r[6].strip()
        })
    return catalysts

def extract_valuation_scenarios(text):
    """提取三情景EPS（§五.2）"""
    scenarios = {}
    # 匹配情景表格
    m = re.search(r'乐观[^\n]*?(\d+\.\d+).*?(\d+\.\d+).*?(\d+\.\d+)', text)
    if not m: return None

    # 更精确的匹配：三情景EPS
    opt_m = re.search(r'乐观[^\n]*?(\d+\.\d+)', text)
    neu_m = re.search(r'中性[^\n]*?(\d+\.\d+)', text)
    pes_m = re.search(r'悲观[^\n]*?(\d+\.\d+)', text)

    if opt_m: scenarios['optimistic_eps'] = float(opt_m.group(1))
    if neu_m: scenarios['neutral_eps'] = float(neu_m.group(1))
    if pes_m: scenarios['pessimistic_eps'] = float(pes_m.group(1))

    # 当前价
    price_m = re.search(r'现价[^\d]*?(\d+\.\d+)', text)
    if price_m: scenarios['current_price'] = float(price_m.group(1))

    return scenarios if len(scenarios) >= 3 else None

def extract_wyckoff_stage(text):
    """提取Wyckoff阶段定位（§四.2）"""
    stage_map = {
        'accumulation': 'Accumulation', '吸筹': 'Accumulation',
        'markup': 'Markup', '拉升': 'Markup',
        'distribution': 'Distribution', '派发': 'Distribution',
        'markdown': 'Markdown', '下跌': 'Markdown'
    }
    result = {}
    m = re.search(r'(?:Wyckoff阶段|当前阶段)[^\n]*?[：:]\s*[^\n]*?(Accumulation|Markup|Distribution|Markdown|吸筹|拉升|派发|下跌)', text, re.IGNORECASE)
    if m:
        raw = m.group(1)
        result['stage'] = stage_map.get(raw.lower(), raw)

    m = re.search(r'(?:时间|时间段)[^\n]*?[：:]\s*([^\n]+)', text)
    if m: result['time_range'] = m.group(1).strip()

    m = re.search(r'(?:价格区间)[^\n]*?[：:]\s*([^\n]+)', text)
    if m: result['price_range'] = m.group(1).strip()

    return result if result else None

def extract_red_flags(text):
    """提取五红旗判定（§六.4）"""
    flags = {}
    # 匹配 🟢/🟡/🔴 或 green/yellow/red
    flag_patterns = [
        ('flag1_extreme_valuation', r'①.*?(?:🟢|绿色|green)'),
        ('flag2_unstable_earnings', r'②.*?(?:🟢|🟡|🔴|绿色|黄色|红色)'),
        ('flag3_high_volatility', r'③.*?(?:🟢|🟡|🔴|绿色|黄色|红色)'),
        ('flag4_liquidity_risk', r'④.*?(?:🟢|🟡|🔴|绿色|黄色|红色)'),
        ('flag5_stop_loss_feasibility', r'⑤.*?(?:🟢|🟡|🔴|绿色|黄色|红色)'),
    ]
    for key, pat in flag_patterns:
        m = re.search(pat, text)
        if m:
            cell = m.group(0)
            if '🟢' in cell or '绿色' in cell: flags[key] = 'green'
            elif '🟡' in cell or '黄色' in cell: flags[key] = 'yellow'
            elif '🔴' in cell or '红色' in cell: flags[key] = 'red'

    return flags if flags else None

def extract_stop_loss(text):
    """提取止损位（§八.4）"""
    result = {}
    m = re.search(r'止损线[^\n]*?¥\s*([\d.]+)', text)
    if m: result['hard_stop'] = float(m.group(1))

    m = re.search(r'移动止盈[^\n]*?¥\s*([\d.]+)', text)
    if m: result['trailing_stop'] = float(m.group(1))

    m = re.search(r'建议仓位上限[^\d]*?(\d+)%', text)
    if m: result['suggested_max_pct'] = int(m.group(1))

    m = re.search(r'当前仓位[^\d]*?(\d+)%', text)
    if m: result['current_pct'] = int(m.group(1))

    return result if result else None

def extract_scenarios(text):
    """提取四情景概率（§六.2）"""
    scenarios = []
    # 匹配最优/基准/偏弱/最差 情景
    pattern = r'(最优|基准|偏弱|最差)[^\n]*?[：:]\s*([^\n]*?)(?:预估价格|价格)[^\d]*?([\d.]+)[^\d]*?(?:盈亏|±?)([+-]?[\d.]+%)[^\d]*?(?:概率)[^\d]*?(\d+)%'
    matches = re.findall(pattern, text)
    for m in matches:
        scenarios.append({
            'name': m[0],
            'trigger': m[1].strip(),
            'price': float(m[2]),
            'pct_gain': m[3],
            'probability': int(m[4]) / 100.0
        })
    return scenarios if scenarios else None

def extract_company_type(text):
    """提取公司类型判定"""
    m = re.search(r'(价值型|成长型|周期型|混合型)', text)
    return m.group(1) if m else None

def extract_anti_hallucination_flags(text):
    """提取幻觉防范标注（§三）"""
    flags = []
    # 匹配 ⚠️ 标记行
    for line in text.split('\n'):
        if '⚠️' in line:
            flags.append(line.strip())
    return flags if flags else None

def extract_data_source_status(text):
    """提取数据源状态（阶段0数据源表）"""
    sources = {}
    source_patterns = {
        'source_2': r'新浪\[2\]|K线.*?新浪',
        'source_3': r'东方财富\[3\]|财务.*?东方财富',
        'source_7': r'东方财富\[7\]|板块.*?东方财富',
        'source_8': r'东方财富\[8\]|北向.*?东方财富',
        'source_9': r'东方财富\[9\]|主力.*?东方财富',
        'source_10': r'东方财富\[10\]|行业资金.*?东方财富',
        'source_11': r'东方财富\[11\]|研报.*?东方财富',
        'source_12': r'东方财富\[12\]|融资.*?东方财富',
    }
    for key, pat in source_patterns.items():
        if re.search(pat, text):
            sources[key] = '正常'
    return sources if sources else None

def extract_base_signals(text):
    """提取33个基础信号(S01-S33)"""
    signals = {}

    # MA排列
    m = re.search(r'MA排列[^\n]*?(多头排列|空头排列|纠缠)', text)
    if m:
        signals['S01'] = m.group(1) == '多头排列'
        signals['S02'] = m.group(1) == '空头排列'

    # RSI
    m = re.search(r'RSI[^\d]*?(\d+\.?\d*)', text)
    if m:
        rsi = float(m.group(1))
        signals['S05'] = rsi >= 70
        signals['S06'] = rsi < 30
        signals['S07'] = 50 <= rsi < 70

    # MACD
    m = re.search(r'MACD[^\n]*?(金叉|死叉)', text)
    if m:
        signals['S03'] = '金叉' in m.group(1) and '零轴上' in m.group(0) if '零轴' in m.group(0) else '金叉' in m.group(1)
        signals['S04'] = '死叉' in m.group(1)

    # 布林
    m = re.search(r'布林[^\n]*?(上轨|下轨|中轨上方|中轨下方)', text)
    if m:
        signals['S08'] = '上轨' in m.group(1) and '触及' in m.group(0)
        signals['S09'] = '下轨' in m.group(1) and '触及' in m.group(0)

    # 量价
    m = re.search(r'(放量上涨|缩量下跌|放量下跌|缩量上涨)', text)
    if m:
        signals['S10'] = m.group(1) == '放量上涨'
        signals['S11'] = m.group(1) == '缩量下跌'

    # ROE
    m = re.search(r'ROE[^\d]*?(\d+\.?\d*)\s*%', text)
    if m:
        signals['S12'] = float(m.group(1)) >= 15

    # PE百分位
    m = re.search(r'PE[^\n]*?(?:百分位|分位)[^\d]*?(\d+)%', text)
    if m:
        pe_pct = int(m.group(1))
        signals['S13'] = pe_pct < 20
        signals['S14'] = pe_pct > 80

    # 资金流
    m = re.search(r'(主力持续流入|主力流入|主力流出|主力持续流出)', text)
    if m:
        signals['S15'] = '流入' in m.group(1) and '流出' not in m.group(1)
        signals['S16'] = '流出' in m.group(1)

    # 北向
    m = re.search(r'北向[^\n]*?持股[^\d]*?(\d+\.?\d*)\s*%', text)
    if m:
        signals['S17'] = float(m.group(1)) > 3

    # 研报
    signals['S18'] = bool(re.search(r'研报', text))

    # Wyckoff
    m = re.search(r'(?:Wyckoff|当前阶段)[^\n]*?(Accumulation|Markup|Distribution|Markdown|吸筹|拉升|派发|下跌)', text)
    if m:
        stage = m.group(1).lower()
        signals['S26'] = stage in ('accumulation', '吸筹')
        signals['S27'] = stage in ('markup', '拉升')
        signals['S28'] = stage in ('distribution', '派发')
        signals['S29'] = stage in ('markdown', '下跌')

    # 背离信号需要从K线独立计算，暂不提取
    return signals if signals else None

def parse_report(report_path):
    """主解析函数"""
    with open(report_path, 'r', encoding='utf-8') as f:
        text = f.read()

    # 提取股票信息
    m = re.search(r'#\s*(\d{6})\s+(.+?)\s+[—\-]', text)
    if not m:
        m = re.search(r'(\d{6})\s+(.+?)\s+[—\-]', text)
    code = m.group(1) if m else '000000'
    name = m.group(2).strip() if m and len(m.groups()) >= 2 else 'Unknown'

    # 提取日期
    date_m = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', text)
    if date_m:
        date_str = f"{date_m.group(1)}{int(date_m.group(2)):02d}{int(date_m.group(3)):02d}"
    else:
        date_str = datetime.now().strftime('%Y%m%d')

    version = extract_version(text)
    scores = extract_scores(text)
    market = extract_market_judgment(text)
    industry = extract_industry_judgment(text)
    catalysts = extract_catalysts(text)
    valuation = extract_valuation_scenarios(text)
    wyckoff = extract_wyckoff_stage(text)
    red_flags = extract_red_flags(text)
    stop_loss = extract_stop_loss(text)
    scenarios = extract_scenarios(text)
    company_type = extract_company_type(text)
    hallucination_flags = extract_anti_hallucination_flags(text)
    data_sources = extract_data_source_status(text)
    base_signals = extract_base_signals(text)

    result = {
        'meta': {
            'date': date_str,
            'stock_code': code,
            'stock_name': name,
            'methodology_version': version or 'UNKNOWN',
            'report_path': report_path.replace('\\', '/')
        },
        'scores': scores or {},
        'market_judgment': market or {},
        'industry_judgment': industry or {},
        'catalysts': catalysts,
        'valuation_scenarios': valuation or {},
        'wyckoff_stage': wyckoff or {},
        'five_red_flags': red_flags or {},
        'stop_loss': stop_loss or {},
        'scenarios': scenarios,
        'company_type': company_type,
        'anti_hallucination_flags': hallucination_flags or [],
        'data_source_status': data_sources or {},
        'signals': base_signals or {}
    }

    return result

def main():
    if len(sys.argv) < 2:
        print("Usage: python parse_deep_analysis_report.py <report.md> [--output <json_path>]")
        sys.exit(1)

    report_path = sys.argv[1]
    output_path = None
    if '--output' in sys.argv:
        idx = sys.argv.index('--output')
        if idx + 1 < len(sys.argv):
            output_path = sys.argv[idx + 1]

    if not os.path.exists(report_path):
        print(f"ERROR: Report not found: {report_path}")
        sys.exit(1)

    result = parse_report(report_path)
    json_str = json.dumps(result, ensure_ascii=False, indent=2)

    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(json_str)
        print(f"OK: {output_path}")
    else:
        print(json_str)

if __name__ == '__main__':
    main()
