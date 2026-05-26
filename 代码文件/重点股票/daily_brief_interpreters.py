"""Daily brief interpreter functions — extracted from gen_daily_brief.py (v1.8 refactor).
   Pure functions: no state, no I/O. All accept raw values and return interpretation strings.
   Level: L1 (strategy/scoring auxiliary)."""

def adx_read(adx):
    if adx > 25:
        return f"趋势明确(>25)，方向性交易可行，顺势而为。当前ADX={adx:.1f}说明市场正在走趋势，不是震荡"
    if adx > 20:
        return f"趋势模糊(20-25)，方向待确认，暂观望。ADX={adx:.1f}处于临界区，等突破25或跌破20再判断"
    return f"震荡市(<20)，ADX={adx:.1f}说明没有趋势。趋势策略失效，只能区间高抛低吸，不要在震荡市追涨杀跌"

def rsi_read(rsi):
    if rsi > 75:
        return f"严重超买(>{rsi:.0f})！短期回调概率很大，严禁追高。持仓者应设紧止损，未持仓者等RSI回到60以下"
    if rsi > 65:
        return f"强势偏强({rsi:.0f})，还有上行空间但已接近超买边界(>70)。持仓可设紧止损，追高需谨慎"
    if rsi > 40:
        return f"中性健康({rsi:.0f})，既无超买也无超卖。趋势跟随策略有效，顺势操作即可"
    if rsi > 25:
        return f"弱势偏弱({rsi:.0f})，动能不足。不要急于抄底，等RSI回升到40以上确认企稳再考虑"
    return f"极度超卖(<{rsi:.0f})，可能超跌反弹但持续性存疑。不急于抄底，等RSI回升确认+成交量放大再入场"

def bb_read(pos):
    if "上轨" in str(pos):
        return "触及上轨=短期压力位。突破需要放量配合(量>20日均量1.5倍)，否则大概率回调。当前位置不宜追高，等回踩中轨或突破确认"
    if "下轨" in str(pos):
        return "触及下轨=短期支撑位。可能超跌反弹，但必须放量确认——缩量反弹是假信号，放量反弹才可信"
    return "中轨附近=正常波动区间，无极端信号。布林带没有给出额外的方向提示"

def obv_read(trend, vol_rel):
    if "同步" in str(trend) or "上行" in str(trend):
        return f"量价同步=趋势健康。成交量({vol_rel})支持当前价格方向，没有背离信号，可以继续跟随趋势"
    if "背离" in str(trend):
        return f"量价背离=危险信号！价格和成交量方向不一致，趋势可能反转。这是最值得重视的技术预警之一"
    return f"量价关系({vol_rel})，需继续观察后续是否出现明确的同步或背离信号"

def fund_read(flow):
    if "流入" in str(flow) and ("持续" in str(flow) or "连续" in str(flow)):
        return f"主力持续流入，机构在持续买入。这是最正面的资金信号，跟风安全边际较高。若趋势向好，可以跟随"
    if "流入" in str(flow):
        return "主力今日流入，短期积极信号。但单日流入不足以确认趋势，需观察后续能否持续。明日继续关注资金方向"
    if "流出" in str(flow):
        return "主力流出，机构在卖出。这是需要警惕的信号，如果明日继续流出→考虑减仓。单日流出不一定反转，但连续流出=离场信号"
    return "主力动向不明，中性看待。资金面没有给出方向性信号"

def wyckoff_read(phase):
    if "拉升" in str(phase):
        return "拉升期(Markup)=持有最佳阶段。量价齐升，趋势健康。持仓为主，回调到支撑位是加仓机会。不要被正常回调吓出去"
    if "吸筹" in str(phase):
        return "吸筹区(Accumulation)=主力在低位建仓。可以关注但不要追，等放量突破吸筹区上轨确认拉升开始后再入场更安全"
    if "派发" in str(phase):
        return "派发区(Distribution)=主力在出货！这是最危险的阶段，任何上涨都可能是诱多陷阱。逐步减仓，不要被【假突破】骗进去"
    if "下跌" in str(phase):
        return "下跌区(Markdown)=趋势向下。不要抄底，不要接飞刀。君子不立危墙之下——等Wyckoff阶段转吸筹/拉升再考虑"
    return "阶段不明，需进一步确认。Wyckoff四阶段定位不清晰时，说明市场方向不明确，观望为宜"

def sector_read(score, industry):
    if score >= 55:
        return f"{industry}板块评分{score}分，处于强势区间(前30%)。板块有行业东风，个股上涨有板块支撑，不是独立行情"
    if score >= 35:
        return f"{industry}板块评分{score}分，处于中游(30-70%)。板块没有拖累个股也没有助推个股，个股走势更多依赖自身逻辑"
    return f"{industry}板块评分{score}分，处于弱势(后30%)。板块偏弱是个股的拖累项——个股上涨更多是被大盘带动的【独立行情】，持续性需要更谨慎评估。一旦大盘转弱，板块弱势的个股往往跌得更快"

def conflict_analysis(tech, fund, sec, cap, name, industry):
    if fund <= 25:
        conflict_title = f"技术面偏多({tech}分) vs 基本面极弱({fund}分)"
        why = (
            f"这股\"涨\"靠的是大盘带动+短线资金情绪，不是自身业绩驱动。"
            f"基本面{fund}分意味着ROE低、估值贵、盈利能力差——没有业绩支撑的上涨是\"裸泳\"，"
            f"一旦市场情绪转向或大盘回调，这类股票跌得最快最狠。"
            f"历史上A股【普涨日追涨基本面差的股票】是散户最常见也最亏钱的交易模式。"
        )
        wait = (
            f"等待以下任一信号出现再考虑买入："
            f"①ROE回升到10%以上（当前<5%）→基本面否定解除；"
            f"②PE回归历史中位数以下→估值变得合理；"
            f"③扣非净利润连续2季度正增长→盈利趋势确认。"
            f"在此之前，基本面否决不解除，仓位上限10%以内。"
        )
    elif sec <= 35:
        conflict_title = f"技术面偏多({tech}分) vs 板块弱势({sec}分)"
        why = (
            f"所属的{industry}板块评分仅{sec}分，在全市场中排名靠后。"
            f"A股中约60%的个股涨跌由板块解释——板块弱意味着没有行业东风，"
            f"个股的上涨更多是\"独立行情\"或\"被大盘带涨\"，持续性存疑。"
            f"如果板块继续走弱，个股很难独善其身——\"逆板块上涨\"在A股是少数且短暂的。"
        )
        wait = (
            f"等待板块评分回升到55以上，或板块相位从退潮转为启动。"
            f"板块转强=有了行业东风，个股上涨才有持续性。"
            f"在此之前，参与只能是小仓位短线，不要做成中线持仓。"
        )
    elif tech >= 65 and cap >= 50:
        conflict_title = f"技术({tech}分)+资金({cap}分)双确认，但基本/板块未共振"
        why = (
            f"技术和资金都在看多，说明短期确实有资金在推动，上涨是有\"真金白银\"支撑的。"
            f"但基本面({fund}分)和板块({sec}分)没有提供支撑——"
            f"这意味着这波上涨可能是短线资金行为而非趋势性机会。"
            f"资金推动的上涨来得快、走得也快，一旦资金转向，回调会很迅猛。"
        )
        wait = (
            f"可以小仓位(<=10%)参与短线，但必须严格执行止损纪律。"
            f"如果基本面或板块评分在未来1-2周内改善，可以考虑加仓到20%。"
            f"如果资金突然转为流出→立即离场，不要犹豫。"
        )
    elif tech >= 70:
        conflict_title = f"技术面强势({tech}分)，但缺乏多维度共振确认"
        why = (
            f"技术面单项高分容易形成\"虚假信心\"——均线、MACD、RSI等指标本质都是价格的衍生变换，"
            f"它们同时看多不等于多个独立证据在说话。"
            f"需要资金面和板块面的独立确认才能真正放心。"
            f"当前资金({cap}分)和板块({sec}分)的信号强度不足以构成共振。"
        )
        wait = (
            f"等待至少2个非价格维度（资金面+板块面）发出同步信号后再行动。"
            f"单一技术面信号→仓位不超过10%，且设紧止损。"
            f"如果下周板块评分能升到55+且资金继续流入，可以加仓。"
        )
    else:
        conflict_title = f"多维度信号不一致，缺乏明确方向"
        why = (
            f"技术{tech}分、基本面{fund}分、板块{sec}分、资金{cap}分，"
            f"四个维度指向不同方向。这不是做决策的时候——"
            f"在信号矛盾时强行交易，亏损概率远大于盈利。"
            f"\"不做决策\"本身就是一种正确的决策。"
        )
        wait = (
            f"等待至少2个维度信号方向一致后再行动。"
            f"当前最佳策略是\"不交易\"——观望也是交易决策的一种，而且往往是最好的一种。"
            f"把钱留着等明确的信号出现，比在模糊时把钱亏掉要好得多。"
        )
    return conflict_title, why, wait

def t5_outlook(sc, sig, price):
    """Generate T+5 outlook per §2.1.5 of post-eval white paper v1.8."""
    tech = sc['Technical']
    fund = sc['Fundamental']
    sector = sc['Sector']
    capital = sc['Capital']

    if tech >= 70 and sector >= 55:
        direction, confidence = "看多", "中"
    elif tech >= 60 and capital >= 40:
        direction, confidence = "偏多", "低"
    elif tech < 35:
        direction, confidence = "偏空", "中" if fund <= 30 else "低"
    elif tech < 50 and sector < 35:
        direction, confidence = "偏空", "低"
    else:
        direction, confidence = "中性", "低"

    weekly_vol = 0.05
    if direction == "看多":
        target_high = round(price * (1 + weekly_vol * 1.2), 2)
        target_low = round(price * (1 - weekly_vol * 0.3), 2)
    elif direction == "偏多":
        target_high = round(price * (1 + weekly_vol * 0.6), 2)
        target_low = round(price * (1 - weekly_vol * 0.5), 2)
    elif direction == "偏空":
        target_high = round(price * (1 + weekly_vol * 0.3), 2)
        target_low = round(price * (1 - weekly_vol * 0.8), 2)
    else:
        target_high = round(price * (1 + weekly_vol * 0.5), 2)
        target_low = round(price * (1 - weekly_vol * 0.5), 2)

    if sector >= 55 and capital >= 40:
        vs_market = "有望跑赢"
    elif fund <= 25:
        vs_market = "可能跑输"
    else:
        vs_market = "持平"

    catalysts = []
    fund_flow = sig.get('FundFlow_Trend', '')
    if fund_flow and "流入" in str(fund_flow):
        catalysts.append("主力资金是否持续流入")
    if sector >= 55:
        catalysts.append("板块能否维持强势排名")
    if fund <= 25:
        catalysts.append("基本面评分是否改善(当前一票否决)")
    if tech >= 70:
        catalysts.append("技术面强势能否带动板块共振")
    if not catalysts:
        catalysts.append("大盘整体走势方向")

    return direction, confidence, target_high, target_low, vs_market, catalysts

def market_regime_read(macro_score):
    """Determine market regime label for machine parsing (v1.8 §2.2.2.0)."""
    if macro_score >= 75:
        return "牛"
    elif macro_score <= 25:
        return "熊"
    else:
        return "震荡"
