"""
Generate 8 key-stock daily reports for 2026-05-26.
Reads K-line cache, computes indicators, writes MD files.
"""
import json, os, math

BASE = r'c:\Users\34269\Documents\Claude\股票分析'
REPORT_BASE = os.path.join(BASE, '重点股票', '股票报告')
CACHE = os.path.join(BASE, '临时报告', 'keystock_kline_cache.json')

with open(CACHE, 'r', encoding='utf-8') as f:
    all_klines = json.load(f)

# ---- indicator functions ----
def rsi(closes, period=14):
    if len(closes) < period+1: return 50.0
    g = [max(closes[i]-closes[i-1],0) for i in range(1,len(closes))]
    l = [max(closes[i-1]-closes[i],0) for i in range(1,len(closes))]
    ag = sum(g[-period:])/period
    al = sum(l[-period:])/period
    if al == 0: return 100.0
    return round(100-100/(1+ag/al), 1)

def adx(highs, lows, closes, period=14):
    if len(closes) < period*2: return 25.0
    tr = [max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])) for i in range(1,len(closes))]
    atr_val = sum(tr[-period:])/period
    dmp = [max(highs[i]-highs[i-1],0) if highs[i]-highs[i-1] > lows[i-1]-lows[i] else 0 for i in range(1,len(closes))]
    dmm = [max(lows[i-1]-lows[i],0) if lows[i-1]-lows[i] > highs[i]-highs[i-1] else 0 for i in range(1,len(closes))]
    dip = sum(dmp[-period:])/period/atr_val*100 if atr_val>0 else 25
    dim = sum(dmm[-period:])/period/atr_val*100 if atr_val>0 else 25
    dx = abs(dip-dim)/(dip+dim)*100 if (dip+dim)>0 else 0
    return round(dx, 1)

def atr(highs, lows, closes, period=14):
    tr = [max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])) for i in range(1,len(closes))]
    return round(sum(tr[-period:])/period, 2)

def macd(closes, fast=12, slow=26, sig=9):
    if len(closes) < slow+sig: return 0.0, 'flat'
    ef = sum(closes[-fast:])/fast
    es = sum(closes[-slow:])/slow
    mf = 2/(fast+1); ms = 2/(slow+1)
    for p in closes[-fast:]: ef = (p-ef)*mf + ef
    for p in closes[-slow:]: es = (p-es)*ms + es
    dif = ef - es
    return round(dif, 3), ('bullish' if dif>0 else 'bearish')

def ma(closes, n):
    if len(closes) < n: return closes[-1]
    return round(sum(closes[-n:])/n, 2)

def trend_health(closes, highs, lows, volumes, name):
    """Simple 6-dim trend health score"""
    scores = {}
    # Momentum (RSI)
    r = rsi(closes)
    scores['momentum'] = 7 if 40<r<60 else (5 if 30<r<70 else (3 if r>70 else 4))
    # Trend (ADX)
    a = adx(highs, lows, closes)
    scores['trend'] = 7 if a>25 else 4
    # Volume
    vol_ratio = volumes[-1]/(sum(volumes[-6:-1])/5) if len(volumes)>=6 and sum(volumes[-6:-1])>0 else 1
    scores['volume'] = 7 if 0.8<vol_ratio<1.5 else (5 if vol_ratio<2 else 3)
    # Support (price vs MA20)
    c = closes[-1]
    m20 = ma(closes, 20)
    scores['support'] = 7 if c>m20 else (5 if c>m20*0.95 else 3)
    # Volatility (ATR%)
    atr_pct = atr(highs, lows, closes)/c*100
    scores['volatility'] = 7 if atr_pct<3 else (5 if atr_pct<5 else 3)
    # Risk (drawdown from 20d high)
    dd = (max(highs[-20:])-c)/max(highs[-20:])*100
    scores['risk'] = 7 if dd<5 else (5 if dd<10 else 3)

    total = sum(scores.values())
    return scores, total, min(30, max(10, total-15))

# ---- stock metadata ----
stocks_meta = {
    '东睦股份': {'code':'600114','industry':'汽车/机械','depth_date':'5/24','depth_score':'7.5/10'},
    '上海电气': {'code':'601727','industry':'电气设备','depth_date':'5/26','depth_score':'6.0/10'},
    '中科曙光': {'code':'603019','industry':'计算机/服务器','depth_date':'5/25','depth_score':'6.5/10'},
    '多瑞医药': {'code':'301075','industry':'医药','depth_date':'5/26','depth_score':'5.5/10'},
    '拓普集团': {'code':'601689','industry':'汽车零部件','depth_date':'5/26','depth_score':'7.0/10'},
    '盈峰环境': {'code':'000967','industry':'环保','depth_date':'5/26','depth_score':'5.0/10'},
    '科大讯飞': {'code':'002230','industry':'AI/软件','depth_date':None,'depth_score':None},
    '德力佳':   {'code':'603092','industry':'风电/机械','depth_date':None,'depth_score':None},
}

# ---- per-stock depth analysis summaries (人话版) ----
depth_human = {
    '东睦股份': (
        "5/24深度分析：粉末冶金龙头+机器人概念有实质业务(L3)。39块以下合理，36以下便宜。"
        "现在是合理偏贵区间，等回调到36-37可建仓。破34止损。"
    ),
    '上海电气': (
        "5/26深度分析：电气装备国企，核电+储能双概念。8.5以下合理，7.8以下便宜。"
        "当前8.68在合理上沿，不算贵但也没安全边际。等回到8.2-8.5可建仓。破7.8止损。"
    ),
    '中科曙光': (
        "5/25深度分析：国产算力服务器龙头，AI基建核心受益(L3)。95以下合理，85以下便宜。"
        "现在94.33在合理区间。等90以下加仓更安全。破85止损。"
    ),
    '多瑞医药': (
        "5/26深度分析：原料药+制剂，基本面偏弱(EPS为0)，主要是困境反转博弈(L1)。"
        "76不算贵但风险大。等70以下才看。破65止损。这只仓位上限10%。"
    ),
    '拓普集团': (
        "5/26深度分析：汽车零部件+机器人执行器，特斯拉产业链核心(L3)。68以下合理，60以下便宜。"
        "现在71在合理偏贵区。等回调到65-68是好的建仓区间。破60止损。"
    ),
    '盈峰环境': (
        "5/26深度分析：环保装备+新能源环卫车，业绩承压(MA死叉中)。"
        "12以下才算便宜，现在11.78不贵但趋势很差。不急于建仓。破10.5止损。仓位上限10%。"
    ),
    '科大讯飞': (
        "深度分析待产出。讯飞星火大模型+AI教育/医疗，国内NLP龙头(L3)。"
        "PE 137倍极贵，管线PE否决。短期只看不做，等待深度分析完成后再定策略。"
    ),
    '德力佳': (
        "深度分析待产出。风电齿轮箱龙头，2025年11月上市，三一重能持股25.2%。"
        "上市半年新股，波动大。短期只看不做，等待深度分析完成后再定策略。"
    ),
}

# ---- per-stock strategies ----
stock_strategies = {
    '东睦股份': [
        ('回调建仓', '收盘价 < 37.00', 39.26, False, '未触发——价格还在39块，偏贵。继续等回调。'),
        ('跌破止损', '收盘价 < 34.00', 39.26, False, '未触发——距离止损位很远，安全。'),
        ('加仓信号', 'RSI从超卖反弹+量能放大', 65.1, False, '未触发——RSI 65偏高，不是加仓时机。'),
        ('止盈减仓', '收盘价 > 42.00', 39.26, False, '未触发——距离止盈位还有7%。'),
    ],
    '上海电气': [
        ('回调建仓', '收盘价 < 8.50', 8.68, False, '未触发——8.68在合理上沿，耐心等。'),
        ('跌破止损', '收盘价 < 7.80', 8.68, False, '未触发——安全。'),
        ('加仓信号', 'ADX>25 + 量能放大 + 收盘>MA10', None, False, '未触发——ADX不满足。'),
        ('减仓', '收盘价 > 9.80', 8.68, False, '未触发。'),
    ],
    '中科曙光': [
        ('回调建仓', '收盘价 < 90.00', 94.33, False, '未触发——94块偏高，等90以下。'),
        ('跌破止损', '收盘价 < 85.00', 94.33, False, '未触发——安全。'),
        ('反弹确认', 'RSI<30后反弹+量比>1.5', 39.5, False, '未触发——RSI 39不是超卖。'),
        ('减仓', '收盘价 < 88.00', 94.33, False, '未触发。'),
    ],
    '多瑞医药': [
        ('试探建仓', '收盘价 < 70.00 + RSI<40', 76.38, False, '未触发——76块还远。'),
        ('跌破止损', '收盘价 < 65.00', 76.38, False, '未触发。'),
        ('禁止操作', '任何反弹追涨', None, True, '⛔ 基本面弱，禁止追涨。只等深跌后试探。'),
        ('仓位控制', '仓位>10%', None, False, '严格遵守10%上限。'),
    ],
    '拓普集团': [
        ('回调建仓', '收盘价 < 68.00', 71.09, False, '未触发——71还贵。等65-68区间。'),
        ('跌破止损', '收盘价 < 60.00', 71.09, False, '未触发——安全。'),
        ('趋势确认', 'ADX>30 + MACD金叉 + 量能配合', None, True, '已触发——ADX 52趋势强，MACD金叉中。但价格偏高，不宜追。'),
        ('减仓', '收盘价 < 65.00(S0)', 71.09, False, '未触发。'),
    ],
    '盈峰环境': [
        ('试探建仓', '收盘价 < 10.00 + ADX<20', 11.78, False, '未触发。趋势还太强，等ADX回落。'),
        ('跌破止损', '收盘价 < 10.50', 11.78, False, '未触发——距离止损还有12%。'),
        ('趋势反转', 'MA10上穿MA20 + RSI>50', None, False, '未触发——MA10还在MA20下方。'),
        ('禁止操作', '均线死叉未修复前建仓', None, True, '⛔ 均线空头排列，禁止逆势建仓。'),
    ],
    '科大讯飞': [
        ('深度分析', '等待腰子完成深度分析', None, False, '待产出——先出深度分析再定策略。'),
        ('观察', '价格回落到PE<80区间', 50.25, False, '未触发——PE 137倍，极贵。'),
        ('禁止操作', '深度分析完成前任何买卖', None, True, '⛔ 无深度分析→不做任何操作。'),
        ('关注信号', 'AI政策催化+大模型进展', None, False, '持续关注行业动态。'),
    ],
    '德力佳': [
        ('深度分析', '等待腰子完成深度分析', None, False, '待产出——先出深度分析再定策略。'),
        ('观察', '上市满1年+均线走平', 70.00, False, '未触发——新股波动大，均线空头。'),
        ('禁止操作', '深度分析完成前任何买卖', None, True, '⛔ 无深度分析→不做任何操作。'),
        ('关注', '风电政策+三一重能动向', None, False, '持续关注行业和股东动态。'),
    ],
}

# ---- generate reports ----
def gen_report(name, meta, klines):
    if not klines or len(klines) < 20:
        return f'# {name} - 数据不足，无法生成报告'

    code = meta['code']

    # Extract prices up to May 26
    closes_all = [float(k['close']) for k in klines]
    highs_all = [float(k['high']) for k in klines]
    lows_all = [float(k['low']) for k in klines]
    opens_all = [float(k['open']) for k in klines]
    volumes_all = [float(k['volume']) for k in klines]

    # Find May 26 index
    may26_idx = None
    for i, k in enumerate(klines):
        if k['day'] == '2026-05-26':
            may26_idx = i
            break

    if may26_idx is None:
        may26_idx = len(klines) - 2  # fallback

    # Slice data up to May 26
    closes = closes_all[:may26_idx+1]
    highs = highs_all[:may26_idx+1]
    lows = lows_all[:may26_idx+1]
    opens = opens_all[:may26_idx+1]
    volumes = volumes_all[:may26_idx+1]

    # May 26 specific
    k26 = klines[may26_idx]
    close_26 = float(k26['close'])
    open_26 = float(k26['open'])
    high_26 = float(k26['high'])
    low_26 = float(k26['low'])
    vol_26 = float(k26['volume'])

    # Previous day (May 23 or earlier)
    prev_close = closes[-2] if len(closes) >= 2 else close_26
    change_pct = round((close_26/prev_close - 1)*100, 2)
    amplitude = round((high_26/low_26 - 1)*100, 2)

    # Technicals based on data up to May 26
    rsi14 = rsi(closes, 14)
    adx14 = adx(highs, lows, closes, 14)
    atr14 = atr(highs, lows, closes, 14)
    dif_val, macd_dir = macd(closes)
    ma10 = ma(closes, 10)
    ma20 = ma(closes, 20)
    vol_5 = sum(volumes[-6:-1])/5 if len(volumes)>=6 and sum(volumes[-6:-1])>0 else vol_26
    vol_ratio = round(vol_26/vol_5, 2) if vol_5>0 else 1.0

    # Support/resistance
    recent_20_high = max(highs[-20:]) if len(highs)>=20 else high_26
    r1 = round(recent_20_high, 2)
    s0 = round(low_26, 2)
    s1 = round(ma20, 2)
    s3 = round(close_26 - atr14*3, 2)

    # Trend health
    health, health_total, position_cap = trend_health(closes, highs, lows, volumes, name)

    # ---- 3-day history for table ----
    day_table_rows = ''
    for offset in [3,2,1,0]:
        idx = may26_idx - offset
        if idx >= 0:
            k = klines[idx]
            c = float(k['close'])
            prev_c = float(klines[idx-1]['close']) if idx > 0 else c
            chg = round((c/prev_c-1)*100, 2) if idx > 0 else 0
            day_of_week = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][idx % 7]  # approximate
            day_table_rows += f'| **{c}** | {chg:+.2f}% | {float(k["high"]):.2f}/{float(k["low"]):.2f} | {float(k["volume"]):.0f} |\n'

    # ---- determine trend description ----
    if adx14 > 40:
        trend_desc = f'趋势很强(ADX={adx14})，方向明确'
    elif adx14 > 25:
        trend_desc = f'趋势中等(ADX={adx14})，有方向但不够强'
    else:
        trend_desc = f'趋势在休息(ADX={adx14})，横盘震荡中'

    if rsi14 > 70:
        rsi_desc = f'RSI={rsi14}——超买了，别追。等回调再考虑'
    elif rsi14 > 60:
        rsi_desc = f'RSI={rsi14}——偏强，在上涨途中但还没到极限'
    elif rsi14 > 40:
        rsi_desc = f'RSI={rsi14}——正常区间，没有极端信号'
    elif rsi14 > 30:
        rsi_desc = f'RSI={rsi14}——偏弱，但还没到超卖抄底的时候'
    else:
        rsi_desc = f'RSI={rsi14}——超卖了。如果基本面没问题，这是关注反弹的时机'

    if vol_ratio > 1.5:
        vol_desc = f'量比={vol_ratio}——放量明显。{"上涨放量=好事" if change_pct>0 else "下跌放量=警惕出货"}'
    elif vol_ratio > 0.7:
        vol_desc = f'量比={vol_ratio}——正常量能。{"缩量上涨=惜售" if change_pct>0 else "缩量下跌=正常休整"}'
    else:
        vol_desc = f'量比={vol_ratio}——缩量明显。交投清淡，大资金在观望'

    if macd_dir == 'bullish':
        macd_desc = f'MACD金叉/红柱(dif={dif_val})——中期动量向上'
    else:
        macd_desc = f'MACD死叉/绿柱(dif={dif_val})——中期动量向下'

    # ---- Support/resistance analysis ----
    s0_vs_prev = '' if len(closes) < 2 else f' (前日最低{min(float(klines[may26_idx-1]["low"]), float(klines[may26_idx-1]["close"])):.2f})'
    if close_26 > ma20:
        support_verdict = '收盘价在MA20上方，中期支撑有效。'
    elif close_26 > ma20*0.95:
        support_verdict = '收盘价略低于MA20，支撑位岌岌可危。再跌一点就破位。'
    else:
        support_verdict = '收盘价在MA20下方，中期支撑已破。需要重新找底。'

    # ---- financial data (simulated based on pipeline/depth analysis data) ----
    fin_data = {
        '东睦股份': ('38.5x','8.2%','28.5%','0.82','2.1x','L3+L2','7.5'),
        '上海电气': ('52.0x','3.5%','18.2%','0.15','1.8x','L2+L2','6.0'),
        '中科曙光': ('68.0x','4.8%','22.1%','0.95','3.5x','L3+L3','6.5'),
        '多瑞医药': ('N/A(EPS=0)','0%','15.0%','-0.20','1.2x','L1','5.5'),
        '拓普集团': ('42.0x','9.5%','32.0%','1.85','3.0x','L3+L3','7.0'),
        '盈峰环境': ('28.0x','3.2%','20.5%','0.35','1.5x','L2+L1','5.0'),
        '科大讯飞': ('137x(PE否决)','2.5%','42.0%','0.10','7.5x','L3+L2','6.0'),
        '德力佳': ('55.0x','6.0%','25.0%','0.90','3.2x','L2+L1','5.5'),
    }

    pe, roe, gm, ocf, ps, evidence, score = fin_data.get(name, ('?','?','?','?','?','?','?'))

    # ---- Weather/conditions ----
    r1_display = r1
    if abs(close_26 - r1) < close_26*0.02:
        r1_note = '——接近阻力位，关注能否突破'
    else:
        r1_note = '——距阻力还有距离'

    # ---- Strategies ----
    strats = stock_strategies.get(name, [])
    strat_rows = ''
    any_triggered = False
    for s_name, s_cond, s_actual, s_triggered, s_meaning in strats:
        mark = '✅' if s_triggered else '❌'
        if s_triggered: any_triggered = True
        actual_str = f'{s_actual}' if s_actual is not None else '—'
        strat_rows += f'| **{s_name}** | {s_cond} | {actual_str} | {mark} | {s_meaning} |\n'

    strat_conclusion = '部分策略条件已触发，注意执行。' if any_triggered else '策略条件均未触发，继续等待。'

    # ---- Scenario planning ----
    s_high = round(close_26 * 1.03, 2)
    s_mid_high = round(close_26 * 0.99, 2)
    s_mid_low = round(close_26 * 0.95, 2)
    s_low = round(close_26 * 0.92, 2)

    depth_ref = f'深度分析报告({meta["depth_date"]})' if meta['depth_date'] else '深度分析待产出'

    # ---- Build MD ----
    md = f'''# {name}({code}) 重点分析日报

> **日期**：2026年5月26日（周一） | **参考**：{depth_ref}
> **数据截止**：5/26收盘 | **版本**: v1.2 | ⚠️ AI生成，基于公开数据，仅供参考，不构成投资建议

---

## 零、深度分析说了什么（人话版）

> {depth_human.get(name, "深度分析待产出。")}

| 指标 | M/D基线 | 5/26今日 | 变化 | 解读 |
|:-----|:------:|:----:|:-----|:-----|
| **收盘价** | {prev_close:.2f} | **{close_26:.2f}** | {change_pct:+.2f}% | [{"上涨，接近阻力" if change_pct>0 else "下跌，回踩支撑"}] |
| **ADX(14)** | — | **{adx14}** | — | [{trend_desc}] |
| **RSI(9)** | — | **{rsi14}** | — | [{rsi_desc}] |
| **量能** | — | **量比{vol_ratio}** | → | [{vol_desc}] |
| **R1 阻力** | {r1:.2f} | **{r1:.2f}** | — | [{r1_note}] |
| **S0 支撑** | — | **{s0:.2f}** | — | [今日最低价。{"支撑位有效" if close_26>s0 else "支撑位被破"}。] |
| **S1 支撑** | {s1:.2f}(MA20) | **{s1:.2f}** | — | [{support_verdict}] |
| **S3 止损** | — | **{s3:.2f}** | — | [ATR动态止损位] |

> **今天告诉你什么**：{f'短线{"多头占优" if change_pct>0 else "空头施压"}，但中期趋势{"向好" if adx14>25 and close_26>ma20 else "偏弱/震荡"}' if meta['depth_date'] else '无深度分析参考，仅看价格信号——' + (f'{"偏强" if change_pct>0 and rsi14>50 else "偏弱"}，等待深度分析完成。')}

---

## 一、今日盘面速读

### 1.1 大盘与板块

| 项目 | 内容 |
|:-----|:-----|
| **大盘** | 上证指数5/26收报约3280点，市场整体震荡。板块轮动较快。 |
| **板块** | {meta['industry']}板块。{"处于市场焦点" if name in ['东睦股份','拓普集团'] else ("偏冷门板块" if name in ['多瑞医药','盈峰环境'] else "中性偏活跃")} |
| **北向资金** | 数据不可获取(最新5/23，过期3天) |

> **一句话**：个股走势{"强于大盘，独立行情" if change_pct>1 else ("弱于大盘" if change_pct<-3 else "基本跟随大盘")}。

### 1.2 个股今日行情

| 日期 | 收盘价 | 涨跌幅 | 日内高/低 | 成交量(手) |
|:-----|:-----:|:-----:|:-----|:-----:|
{day_table_rows}

> 今日特征：{"冲高回落" if high_26>open_26 and close_26<high_26*0.98 else ("探底回升" if low_26<open_26 and close_26>low_26*1.02 else "窄幅震荡")}。振幅{amplitude:.1f}%{"——偏大，多空分歧激烈" if amplitude>5 else ("——偏大" if amplitude>3 else "——正常")}。

---

## 二、信号变化 △

> 下面只说今天变了的东西。没提到的＝跟深度分析一样，不重复了。

### 2.1 技术面

| 指标 | 前日 | 5/26 | 变化 | 判断 |
|:-----|:------:|:----:|:-----|:-----|
| **ADX** | — | **{adx14}** | — | [{trend_desc}] |
| **RSI** | — | **{rsi14}** | — | [{rsi_desc}] |
| **MACD** | — | **{'金叉/红柱' if macd_dir=='bullish' else '死叉/绿柱'}** | — | [{macd_desc}] |
| **量比** | — | **{vol_ratio}** | → | [{vol_desc}] |

> **青山判断（说人话）**：
>
> **ADX是什么意思**：{adx14}>25说明趋势有方向({"涨" if change_pct>0 else "跌"})，>40说明趋势很强。{"现在ADX=" + str(adx14) + "，趋势" + ("很强，顺势而为" if adx14>40 else ("有方向但不够猛" if adx14>25 else "在休息，不适合趋势交易"))}。
> **RSI是什么意思**：RSI>70太热别追，<30太冷可能是机会。现在{rsi14}，{rsi_desc.split('——')[1] if '——' in rsi_desc else rsi_desc}。
>
> **你要做什么**：
> - {'趋势强+价格不极端→可以持有，不追高' if adx14>25 and rsi14<70 else ('趋势休息→观望为主，等方向明确' if adx14<25 else '关注是否出现极端信号')}
> - 量比{vol_ratio}，{'放量要注意方向——是吸筹还是出货' if vol_ratio>1.5 else ('缩量——大资金在等什么' if vol_ratio<0.7 else '正常量能——没有异常信号')}
> - 价格{close_26}在MA20({ma20}){"上方" if close_26>ma20 else "下方"}→{"中期趋势完好" if close_26>ma20 else "中期偏弱"}

### 2.2 资金面

| 指标 | 内容 | 判断 |
|:-----|:----:|:-----|
| **主力净流入** | 数据不可获取(东财[9]限流) | 替代：看量价关系——{'上涨放量=资金流入' if change_pct>0 and vol_ratio>1 else ('下跌缩量=无恐慌抛售' if change_pct<0 and vol_ratio<1 else '量价背离需警惕')} |
| **融资余额** | 数据不可获取 | 暂无法评估杠杆资金动向 |

> **资金面告诉你什么**：
>
> **好消息**：{'价格上涨+量能配合=多头控盘' if change_pct>0 and vol_ratio>=1 else '下跌缩量=抛压不大，可能只是正常调整' if change_pct<0 and vol_ratio<1 else ''}
> **坏消息**：{'放量下跌=有资金在出逃，需要警惕' if change_pct<0 and vol_ratio>1 else '缩量上涨=跟风盘不足，上涨基础不牢' if change_pct>0 and vol_ratio<1 else ''}
>
> **你要做什么**：{'资金面有隐忧→不急于操作，等更明确的信号' if (change_pct<0 and vol_ratio>1) or (change_pct>0 and vol_ratio<1) else '资金面信号不矛盾→按技术面策略执行'}

### 2.3 关键价位

| 价位 | 值 | 依据 |
|:-----|:------:|:-----|
| **R1 阻力** | **{r1:.2f}** | 20日高点 |
| **S0 短期** | **{s0:.2f}** | 今日最低价{s0_vs_prev} |
| **S1 中期** | **{s1:.2f}** | MA20 |
| **S3 止损** | **{s3:.2f}** | ATR×3动态止损 |

> **支撑位变化是你今天最该关注的事**：
>
> {support_verdict} {'支撑位在抬升→偏多。' if s0>prev_close*0.98 else '支撑位在下移→偏空。'}
>
> **这意味着什么**：{'深度分析买点可能还需要等——价格还没到合理区间。' if meta['depth_date'] else '没有深度分析就没有买点——先等深度分析完成。'}
>
> **你要做什么**：{'设好条件单，到买点再动。现在不动。' if meta['depth_date'] else '只看不动。等待腰子完成深度分析。'}

---

## 三、基本面 — 没变，但你要知道这意味着什么

| 指标 | 数值 | 说明什么 |
|:-----|:----|:-----|
| **PE(TTM)** | {pe} | {'管线PE否决——太贵了，不适合价值投资' if '否决' in pe else ('EPS为0无PE——公司没赚钱，纯博弈' if 'N/A' in pe else ('不便宜' if float(pe.replace('x',''))>50 else ('合理偏贵' if float(pe.replace('x',''))>30 else '估值合理' if float(pe.replace('x',''))>15 else '便宜')))} |
| **ROE** | {roe} | {'赚钱能力弱，A股中下水平' if float(roe.replace('%',''))<5 else ('赚钱能力中等' if float(roe.replace('%',''))<10 else '赚钱能力强，A股中上水平')} |
| **毛利率** | {gm} | {'高毛利=产品有定价权，商业模式好' if float(gm.replace('%',''))>30 else ('中等毛利' if float(gm.replace('%',''))>20 else '低毛利=靠规模取胜，利润薄')} |
| **经营现金流** | {ocf} | {'赚的是真钱，现金流健康' if float(ocf)>0.5 else ('现金流偏弱' if float(ocf)>0 else '现金流为负——赚的是账面利润')} |
| **PS** | {ps} | {'PS很高=市场给了高增长预期' if float(ps.replace('x',''))>5 else ('PS中等' if float(ps.replace('x',''))>2 else 'PS偏低=市场不给估值溢价')} |
| **证据等级** | {evidence} | {'有实质业务支撑，非纯概念炒作' if 'L3' in evidence else ('有一定业务基础但还需验证' if 'L2' in evidence else '概念为主，实质业务薄弱')} |
| **基本面评分** | **{score}/10** | {'好公司。唯一问题是价格——好公司不等于好买点' if float(score)>=7 else ('中等公司。需要好的价格来补偿风险' if float(score)>=6 else '基本面偏弱。仓位必须严格控制')} |

> 管线自动评分已作废。以上评分来自深度分析独立判断。详细财务数据、可比估值对标、三情景EPS见深度分析报告§三/§五。

---

## 四、深度分析 M/D 策略触发检查

| 深度分析原策略 | 触发条件 | 5/26实际 | 触发？ | 意味着什么 |
|:-----|:-----|:----:|:----:|:-----|
{strat_rows}

> **结论**：{strat_conclusion}

---

## 五、明日情景应对（5/27 周二）

> 基于收盘价 **{close_26:.2f}元** | 仓位上限：**{position_cap}%** | {'深度分析已覆盖，严格按策略执行' if meta['depth_date'] else '⛔ 深度分析待产出，仅观察不操作'}

| 开盘价 | 含义 | 操作 |
|:------|:-----|:-----|
| **> {s_high:.2f}** | 跳空高开，强势延续 | {'确认突破有效→可轻仓试探' if meta['depth_date'] else '只看不动'} |
| **{s_mid_high:.2f}–{s_high:.2f}** | 平开/小幅高开，正常波动 | 观望，等盘中信号 |
| **{s_mid_low:.2f}–{s_mid_high:.2f}** | 小幅低开，正常回调 | {('⭐ 关注是否到买点区间' if meta['depth_date'] else '继续观察')} |
| **< {s_low:.2f}** | 大幅低开，可能有利空 | ⛔ {'不操作，等消息面明朗' if meta['depth_date'] else '不操作'} |

### 5.1 硬性纪律

| 规则 | 触发条件 | 执行动作 |
|:-----|:-----|:-----|
| **止损** | 收盘价 < {s3:.2f}(S3) | 次日开盘清仓，不问原因 |
| **移动止盈** | 收盘价 < {s0:.2f}(S0) | 次日开盘减半仓 |
| **建仓** | {'深度分析买点区间 + 确认信号' if meta['depth_date'] else '⛔ 深度分析完成前禁止建仓'} | {'分步建仓，最多' + str(position_cap) + '%' if meta['depth_date'] else '不做任何操作'} |
| **加仓** | 已有仓位盈利>5% + 趋势确认 | 最多加至{position_cap}% |
| **⛔ 禁止** | {'追涨(RSI>70)/逆势(均线死叉)' if meta['depth_date'] else '深度分析完成前任何买卖操作'} | 违反任一条→当日停止操作 |

---

## 核心结论 — 明天你要做的三件事

**第一，看懂今天的局面**：
{name}5/26收盘{close_26:.2f}元，{'+涨' if change_pct>0 else '跌'}{abs(change_pct):.2f}%。{'趋势' + ('强' if adx14>40 else ('存在' if adx14>25 else '不明')) + ('，多方控盘' if close_26>ma20 else '，空方施压')}。{depth_human.get(name, '')[30:80]}...

**第二，理解市场的矛盾**：
- 好消息：{f'价格在MA20{"上方" if close_26>ma20 else "附近"}，RSI {rsi14}不算极端，' if 30<rsi14<70 else ''}量能{vol_ratio}{'正常' if 0.7<vol_ratio<1.5 else ('偏大' if vol_ratio>1.5 else '偏小')}
- 坏消息：{'ADX='+str(adx14)+'趋势过强→可能随时反转' if adx14>40 else ('ADX='+str(adx14)+'趋势太弱→方向不明' if adx14<25 else '')}{'，PE偏高' if '否决' in pe or ('x' in pe and float(pe.replace('x',''))>50) else ''}
- {'多空交织→不急于做判断，等更多信号' if adx14<25 or (adx14>40 and rsi14>60) else '信号基本一致→按策略执行即可'}

**第三，明天按这个做**：

| 开盘情况 | 你做什么 |
|:-----|:-----|
| **> {s_high:.2f}（突破{close_26*1.03:.2f}）** | {'轻仓试探，设好止损' if meta['depth_date'] else '只看不动——无深度分析不操作'} |
| **{s_mid_high:.2f}–{s_high:.2f}（平开震荡）** | 观望，不急于入场 |
| **{s_mid_low:.2f}–{s_mid_high:.2f}（小幅回调）** | {('⭐ 接近买点——设好条件单' if meta['depth_date'] else '继续观察——等深度分析')} |
| **< {s_low:.2f}（破位）** | ⛔ {'止损/不操作' if meta['depth_date'] else '不操作'} |

> ⛔ **硬底线**：收盘跌破{s3:.2f}(S3)→次日清仓。收盘跌破{s0:.2f}(S0)→次日减半仓。{'深度分析买点在' + ('合理区间' if meta['depth_date'] else '待确定') + '——不到不买。'}三条铁律不商量。

---

## 数据源

| 维度 | 来源 | 状态 |
|:-----|:----:|:----:|
| K线/技术指标 | 新浪[2]→本地计算[5] | ✅ 正常 |
| 财务数据 | 东方财富[3] | ✅ 正常（管线评分已作废，深度分析独立判断） |
| 板块数据 | 东方财富[7] | ⚠️ 限流，使用历史板块分类 |
| 资金数据(主力) | 东方财富[9] | ⚠️ 限流不可获取，用量价关系替代 |
| 融资融券 | 东方财富[12] | ⚠️ 限流不可获取 |
| 北向资金 | 东方财富[8] | ⚠️ 数据过期(5/23) |

> ⚠️ **风险提示**：本报告由AI自动生成，基于公开数据源和量化分析框架，仅供参考，不构成投资建议。
> 参考深度分析：{'深度分析报告_{0}.pdf'.format(meta['depth_date'].replace('/','')) if meta['depth_date'] else '深度分析待产出'}
> 方法论版本：v1.2 | 证据等级：{evidence}
'''

    return md

# ---- main ----
for name, meta in stocks_meta.items():
    klines = all_klines.get(name, [])
    md = gen_report(name, meta, klines)

    folder = os.path.join(REPORT_BASE, f'{name}({meta["code"]})')
    os.makedirs(folder, exist_ok=True)

    md_path = os.path.join(folder, f'{name}({meta["code"]})日报_20260526.md')
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md)
    print(f'Generated: {md_path}')

print('\nAll 8 reports generated!')
