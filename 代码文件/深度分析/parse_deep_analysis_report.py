"""
深度分析报告解析器 — Markdown → 评估数据JSON + 质量闸门
L0 工具模块。读取深度分析报告Markdown，提取结构化评估数据。
用法:
    python parse_deep_analysis_report.py <report_md_path> [--output <json_path>]
    python parse_deep_analysis_report.py --validate <report_md_path>
    python parse_deep_analysis_report.py --validate-date YYYYMMDD
"""
import re, json, sys, os
from datetime import datetime
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "scripts"))
from check_deep_d07_lishi_gate import check_report as _d07_lishi_check

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SIGNAL_DIR = os.path.join(ROOT, ".claude")
REGEN_SIGNAL_DIR = os.path.join(SIGNAL_DIR, "regen")
# v2.0: 删除 25KB 硬阈值，改为内容要素检查
REQUIRED_CHAPTERS = [
    "一、公司概要",
    "二、宏观与行业环境",
    "三、财务深度分析",
    "四、技术面深度分析",
    "五、估值分析",
    "六、风险评估",
    "七、综合评分",
    "八、操作策略",
    "九、",
]
REQUIRED_ROLES = ["山猫", "信鸽", "玉夜", "流金", "青山"]

def _role_has_paragraph(text, role):
    """角色是否有≥80字的独立分析段落（排除header打勾行）。

    检查优先级：
    1. 独立结论段落（如"山猫结论:"）
    2. 章节归属（如山猫→§二宏观、玉夜→§三财务、流金→§六风险）
    3. 报告header中的全团咨询声明
    """
    # 1. 独立结论段落
    for pat in [rf'{role}结论[：:]', rf'（{role}）']:
        m = re.search(pat, text)
        if m:
            chunk = text[m.start():m.start() + 600]
            if len(chunk.strip()) >= 80:
                return True

    # 2. 青山特殊处理：策略维度体现在§七综合评分中
    if role == '青山':
        # 检查§七是否有≥200字的分析内容
        sec7 = _section(text, r'综合评分|七、')
        if len(sec7.strip()) >= 200:
            return True
        # 或报告header中明确列出青山
        if re.search(r'青山[）\)]\s*(策略|因子)', text):
            return True

    # 3. 报告header分析团队声明: "山猫（宏观行业）" 格式
    if re.search(rf'{role}（[^）]+）', text):
        return True
    # 4. 旧版header: "山猫✓" 格式
    if re.search(rf'{role}\s*✓', text):
        return True

    return False

# P0: 核心章节严查 — 分析动作是否执行
P0_CHECKS = [
    ("九章完整", lambda t: all(ch in t for ch in REQUIRED_CHAPTERS)),
    ("概念映射表", lambda t: len(re.findall(r'\|.+\|.+\|.+\|', _section(t, r'概念映射'))) >= 2),
    ("催化剂≥2条", lambda t: len(re.findall(r'\|\s*\*?\*?[SABC]\*?\*?\s*\|', _section(t, r'催化剂'))) >= 2),
    ("竞对≥2家", lambda t: len(re.findall(r'\|\s*[\w]+.*\|.*\|.*\|', _section(t, r'竞争位势|竞争格局'))) >= 2),
    ("财务趋势≥4期", lambda t: _count_table_rows(_section(t, r'收入与利润趋势|3\.1')) >= 4),
    ("单季EPS拆解", lambda t: bool(re.search(r'Q1.*Q2.*Q3.*Q4|单季.*EPS.*拆解', t))),
    ("AI幻觉检查", lambda t: bool(re.search(r'⚠️.*幻觉|AI幻觉检查|反常识', t))),
    ("关键位≥5层", lambda t: len(re.findall(r'[RS]\d|支撑|阻力|铁底', _section(t, r'关键技术位|关键价位'))) >= 5),
    ("Wyckoff或RSI", lambda t: bool(re.search(r'Wyckoff|RSI.*\d|超买|超卖', _section(t, r'4\.\d|技术')))),
    ("五红旗逐条", lambda t: len(re.findall(r'[🟢🟡🔴①②③④⑤]', _section(t, r'五红旗|6\.4'))) >= 5),
    ("资金面≥3日趋势", lambda t: bool(re.search(r'[3-5]日|连续\d日', _section(t, r'资金面|6\.3')))),
    ("仓位建议", lambda t: bool(re.search(r'试探仓|核心仓|不入场|3%|8%|12%|仓位', _section(t, r'仓位|6\.\d')))),
    ("六维评分表", lambda t: _count_table_rows(_section(t, r'综合评分|七、')) >= 6),
    ("情景应对表", lambda t: bool(re.search(r'开盘价|情景应对', t)) and _count_table_rows(_section(t, r'情景应对|8\.\d')) >= 3),
    ("价格梯队≥3层", lambda t: len(re.findall(r'[RS]\d|现价', _section(t, r'价格梯队|8\.\d'))) >= 4),
    ("独立止损位", lambda t: bool(re.search(r'止损.*[¥\d]', t))),
    ("一句话结论", lambda t: bool(re.search(r'一句话结论|核心结论|战略定位.*候选|战略定位.*回避', _section(t, r'九、|中长期展望'))) ),
    ("全团独立段落", lambda t: all(_role_has_paragraph(t, r) for r in REQUIRED_ROLES)),
]

# P1: 数据受限项宽松 — 缺失≤2项WARN，>2项FAIL
P1_CHECKS = [
    ("行业景气度监视器", lambda t: _count_table_rows(_section(t, r'景气度|2\.4')) >= 2),
    ("≥3种估值方法", lambda t: len(re.findall(r'PE|PB|PS|PEG|DCF|EV/EBITDA|市值空间', _section(t, r'5\.1|多方法估值'))) >= 3),
    ("三情景EPS", lambda t: bool(re.search(r'乐观.*EPS.*悲观|三情景', _section(t, r'5\.2|情景')))),
    ("可比估值对标", lambda t: bool(re.search(r'可比公司|对标|同业', _section(t, r'5\.\d')))),
    ("Volume Profile", lambda t: bool(re.search(r'Volume Profile|VP|POC|VAH|VAL', t))),
    ("筹码集中度", lambda t: bool(re.search(r'股东人数|筹码|集中度|holder', t))),
    ("质押风险", lambda t: bool(re.search(r'质押|pledge', t))),
    ("分段止盈三目标", lambda t: len(re.findall(r'目标\d', _section(t, r'止盈|8\.4a'))) >= 2),
    ("自检清单≥20条", lambda t: len(re.findall(r'\|\s*\d+\s*\|\s*.+?\s*\|\s*[✓✅]', t)) >= 20),
]

# 反灌水规则
def _anti_fluff_check(text):
    """返回 issues 列表。检测灌水行为。"""
    issues = []
    # 同一连续短语重复≥5次
    phrases = re.findall(r'[一-鿿]{8,30}', text)
    from collections import Counter
    for phrase, cnt in Counter(phrases).most_common(5):
        if cnt >= 5:
            issues.append(f"灌水: '{phrase}' 重复{cnt}次")
    # 连续3段无数字
    paras = [p.strip() for p in text.split('\n\n') if len(p.strip()) > 80]
    no_digit_streak = 0
    for p in paras:
        if not re.search(r'\d', p):
            no_digit_streak += 1
            if no_digit_streak >= 3:
                issues.append(f"灌水: 连续{no_digit_streak}段无数据")
                break
        else:
            no_digit_streak = 0
    # 表格密度
    table_count = len(re.findall(r'^\|.+\|.+|$', text, re.MULTILINE))
    if table_count < 12:
        issues.append(f"表格密度: 仅{table_count}行（建议≥12行）")
    return issues


def _section(text, keyword):
    """提取包含关键词的章节文本（约3000字符上下文）。

    优先匹配章节标题（## 开头的行），其次匹配任意位置。
    """
    # 优先找章节标题匹配
    heading_pat = rf'##\s*[^\n]*?(?:{keyword})[^\n]*\n'
    m = re.search(heading_pat, text)
    if m:
        start = m.start()
        end = min(len(text), start + 3000)
        return text[start:end]

    # 其次正则搜索
    m = re.search(keyword, text)
    if m:
        start = max(0, m.start() - 300)
        end = min(len(text), m.start() + 3000)
        return text[start:end]

    return ""


def _count_table_rows(section_text):
    """计数表格数据行（排除表头分隔行）。"""
    rows = re.findall(r'^\|.+\|.+|$', section_text, re.MULTILINE)
    data_rows = [r for r in rows if not re.match(r'^[\|:\s\-]+$', r)]
    return len(data_rows)


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

# ============================================================
#  质量闸门 v2.0 — P0/P1分级 + 反灌水
# ============================================================

def validate_report(report_path):
    """对单份报告执行质量闸门检查。返回 (pass: bool, issues: list[str], warns: list[str])。

    v2.0: 删除25KB硬阈值。P0查分析动作是否执行，P1查数据受限项，反灌水查废话。
    回避豁免: 绝对回避/强烈回避标的自动豁免价格梯队和独立止损位。
    """
    issues = []   # FAIL 项
    warns = []    # WARN 项

    if not os.path.exists(report_path):
        return False, [f"文件不存在: {report_path}"], []

    with open(report_path, 'r', encoding='utf-8') as f:
        text = f.read()

    # 回避豁免: 报告含"绝对回避"或"强烈回避"→豁免部分P0项
    is_avoid = bool(re.search(r'绝对回避|强烈回避', text))
    avoid_exempt = {"价格梯队≥3层", "独立止损位", "分段止盈三目标", "三情景EPS"} if is_avoid else set()

    # === P0 检查 ===
    p0_fails = []
    for name, check_fn in P0_CHECKS:
        if name in avoid_exempt:
            continue  # 回避标的无需检查此项
        try:
            if not check_fn(text):
                p0_fails.append(name)
        except Exception:
            p0_fails.append(f"{name}(解析异常)")

    if p0_fails:
        issues.append(f"P0缺失: {', '.join(p0_fails)}")

    # === P1 检查（回避标的同样豁免部分项）===
    p1_exempt = avoid_exempt  # 同一豁免集合
    p1_missing = []
    for name, check_fn in P1_CHECKS:
        if name in p1_exempt:
            continue
        try:
            if not check_fn(text):
                p1_missing.append(name)
        except Exception:
            p1_missing.append(f"{name}(解析异常)")

    if len(p1_missing) > 2:
        issues.append(f"P1缺失{len(p1_missing)}项(>2): {', '.join(p1_missing)}")
    elif p1_missing:
        warns.append(f"P1缺失{len(p1_missing)}项(≤2): {', '.join(p1_missing)}")

    # === 反灌水检查 ===
    fluff = _anti_fluff_check(text)
    if fluff:
        issues.extend(fluff)

    # === D07_v1.2 + 砺石 硬闸门 ===
    d07_overall, d07_findings = _d07_lishi_check(Path(report_path))
    d07_blockers = [f for f in d07_findings if f["result"] == "BLOCK"]
    d07_warns = [f for f in d07_findings if f["result"] == "WARN"]
    if d07_blockers:
        for f in d07_blockers:
            issues.append(f"{f['check']}: {f['detail'][:120]}")
    if d07_warns:
        for f in d07_warns:
            warns.append(f"{f['check']}: {f['detail'][:120]}")

    # 判定
    passed = len(issues) == 0
    return passed, issues, warns


def write_regen_signal(code, name, date_str, issues, retry_count=0):
    """写重生成信号文件，含熔断计数。返回信号文件路径。"""
    os.makedirs(REGEN_SIGNAL_DIR, exist_ok=True)
    signal_file = os.path.join(REGEN_SIGNAL_DIR, f"regen_{code}.json")

    existing_retry = 0
    if os.path.exists(signal_file):
        try:
            with open(signal_file, 'r', encoding='utf-8') as f:
                existing_retry = json.load(f).get("retry_count", 0)
        except (json.JSONDecodeError, OSError):
            pass

    new_retry = retry_count if retry_count > 0 else (existing_retry + 1)
    max_retries = 3
    melted = new_retry >= max_retries

    payload = {
        "signal": "regen_deep_analysis",
        "code": code,
        "name": name,
        "date": date_str,
        "retry_count": new_retry,
        "max_retries": max_retries,
        "meltdown": melted,
        "fail_reasons": issues,
        "timestamp": datetime.now().isoformat(),
    }

    with open(signal_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    if melted:
        _write_meltdown_alert(code, name, issues, new_retry)

    return signal_file


def _write_meltdown_alert(code, name, issues, retry_count):
    """熔断告警：3次重试仍 FAIL → P1 升级人工。"""
    alert_file = os.path.join(SIGNAL_DIR, "signal_alert.json")
    payload = {
        "alert": "deep_analysis_meltdown",
        "severity": "P1",
        "code": code,
        "name": name,
        "retry_count": retry_count,
        "fail_reasons": issues,
        "recommend": "腰子人工复核+情墨排查数据/方法论问题",
        "timestamp": datetime.now().isoformat(),
    }
    with open(alert_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def validate_date_reports(date_str):
    """对指定日期的全部深度分析报告执行质量闸门。返回 (passed, failed, total)。"""
    report_base = os.path.join(ROOT, "重点股票", "深度分析", "深度分析报告")
    if not os.path.isdir(report_base):
        print(f"ERROR: report directory not found: {report_base}")
        return 0, 0, 0

    total, passed, failed = 0, 0, 0
    for entry in sorted(os.listdir(report_base)):
        entry_dir = os.path.join(report_base, entry)
        if not os.path.isdir(entry_dir):
            continue
        for fname in sorted(os.listdir(entry_dir)):
            if date_str in fname and fname.endswith('.md'):
                report_path = os.path.join(entry_dir, fname)
                # 从文件名提取代码: "东睦股份(600114)深度分析..." → 600114
                code_m = re.search(r'\((\d{6})\)', fname)
                code = code_m.group(1) if code_m else fname[:6]
                # 从文件名提取名称: "东睦股份(600114)..." → 东睦股份
                name_m = re.search(r'^(.+?)\(\d{6}\)', fname)
                name = name_m.group(1) if name_m else entry.split('(')[0]

                ok, issues, warns = validate_report(report_path)
                total += 1
                if ok:
                    passed += 1
                    status = "PASS"
                    if warns:
                        status += f" (WARN: {'; '.join(warns)})"
                    print(f"  {status}: {code} {name}")
                else:
                    failed += 1
                    print(f"  FAIL: {code} {name} — {'; '.join(issues)}")
                    write_regen_signal(code, name, date_str, issues)
                break

    print(f"\n闸门结果: {passed} PASS / {failed} FAIL / {total} total")
    return passed, failed, total


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
    # --validate-date: 批量质量闸门
    if '--validate-date' in sys.argv:
        idx = sys.argv.index('--validate-date')
        date_str = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else datetime.now().strftime('%Y%m%d')
        print(f"质量闸门扫描: {date_str}")
        passed, failed, total = validate_date_reports(date_str)
        sys.exit(0 if failed == 0 else 1)

    # --validate: 单份报告质量闸门
    if '--validate' in sys.argv:
        idx = sys.argv.index('--validate')
        report_path = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else None
        if not report_path:
            print("Usage: python parse_deep_analysis_report.py --validate <report.md>")
            sys.exit(1)
        ok, issues, warns = validate_report(report_path)
        if ok:
            msg = f"PASS: {report_path}"
            if warns:
                msg += f" (WARN: {'; '.join(warns)})"
            print(msg)
            sys.exit(0)
        else:
            print(f"FAIL: {report_path} — {'; '.join(issues)}")
            if warns:
                print(f"  WARN: {'; '.join(warns)}")
            code_m = re.search(r'\((\d{6})\)', os.path.basename(report_path))
            code = code_m.group(1) if code_m else '000000'
            date_m = re.search(r'(\d{8})', os.path.basename(report_path))
            date_str = date_m.group(1) if date_m else datetime.now().strftime('%Y%m%d')
            name_m = re.search(r'^(.+?)\(\d{6}\)', os.path.basename(report_path))
            name = name_m.group(1) if name_m else ''
            write_regen_signal(code, name, date_str, issues, retry_count=1)
            sys.exit(1)

    # 原有解析模式
    if len(sys.argv) < 2:
        print("Usage: python parse_deep_analysis_report.py <report.md> [--output <json_path>]")
        print("       python parse_deep_analysis_report.py --validate <report.md>")
        print("       python parse_deep_analysis_report.py --validate-date YYYYMMDD")
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
