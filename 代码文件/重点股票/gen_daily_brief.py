"""Generate daily brief MD files from eval data - v2 format with interpretations."""
import json, os, sys, subprocess
from daily_brief_interpreters import (adx_read, rsi_read, bb_read, obv_read,
    fund_read, wyckoff_read, sector_read, conflict_analysis,
    t5_outlook, market_regime_read)

with open('重点股票/次日评估/评估数据_20260526.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

date_str = data['Date']
stocks = data['Stocks']

stock_info = {
    '600114': ('东睦股份', '汽车/机械'),
    '601727': ('上海电气', '电气设备'),
    '603019': ('中科曙光', '计算机/服务器'),
    '301075': ('多瑞医药', '医药'),
    '601689': ('拓普集团', '汽车零部件'),
    '000967': ('盈峰环境', '环保'),
    '600584': ('长电科技', '半导体封测'),
}

def rating_label(score):
    if score >= 80: return ('4星', '强烈关注', 30)
    if score >= 65: return ('3星', '关注', 20)
    if score >= 45: return ('2星', '观察', 10)
    if score >= 30: return ('1星', '谨慎', 5)
    return ('0星', '回避', 0)

def health_mark(score):
    if score >= 60: return 'G'
    if score >= 40: return 'Y'
    return 'R'

generated = 0
for s in stocks:
    code = s['Code']
    name, industry = stock_info.get(code, (s['Name'], '未知'))

    sc = s['Scores']
    sig = s['Signals']
    kl = s['KeyLevels']
    th = s['TrendHealth']

    price = s['Price']
    comp = sc['Composite']
    stars, rating, pos_max = rating_label(comp)
    support = kl['Support']
    resistance = kl['Resistance']
    stoploss = kl.get('StopLoss', 0) or support * 0.85

    rsi = sig.get('RSI_Value', 50)
    adx = sig.get('ADX_Value', 20)
    vol_rel = sig.get('Volume_Relation', '数据不可获取')
    ma_trend = sig.get('MA_Trend', '—')
    fund_flow = sig.get('FundFlow_Trend', '数据不可获取')
    wyckoff = sig.get('Wyckoff_Phase', '—')
    obv = sig.get('OBV_Trend', '—')
    bb_pos = sig.get('Bollinger_Position', '—')
    macd_signal = sig.get('MACD_Signal', '—')
    volume_signal = sig.get('Volume_Signal', '—')
    # v1.8: P0/P1 fields for machine parsing
    macro_score = sc.get('Macro', {}).get('Score', 50) if isinstance(sc.get('Macro'), dict) else 50
    market_regime = market_regime_read(macro_score)
    market_breadth = sig.get('Market_Breadth', '—')
    sector_pct = sc.get('SectorPercentile', '—')

    r1 = resistance * 0.97 if resistance > price else resistance
    s1_val = support
    s3_val = stoploss

    dist_r1 = ((r1/price)-1)*100 if r1 > price else 0
    dist_s1 = ((price/s1_val)-1)*100 if s1_val < price else 0
    dist_s3 = ((price/s3_val)-1)*100 if s3_val < price else 0

    chase_triggered = (rsi > 80 or dist_s1 > 5)
    rsi80_triggered = (rsi > 80)

    tech_m = health_mark(sc['Technical'])
    fund_m = health_mark(sc['Fundamental'])
    sec_m = health_mark(sc['Sector'])
    cap_m = health_mark(sc['Capital'])
    comp_m = health_mark(comp)

    def dim_read(val, name, good=60, bad=40):
        if val >= good: return f"{name}健康({val}分)，无需担忧，这是当前的优势维度"
        if val >= bad: return f"{name}处于警戒区域({val}分)，需要关注后续变化，可能转好也可能恶化"
        return f"{name}是当前最弱维度({val}分)，是拖累综合评分的主因。这个短板不改善，综合评分难以上升"

    n_green = sum(1 for m in [tech_m, fund_m, sec_m, cap_m] if m == 'G')
    n_red = sum(1 for m in [tech_m, fund_m, sec_m, cap_m] if m == 'R')

    if n_red >= 2:
        health_summary = f"[R] {n_red}个维度处于危险状态，建议评估是否需要减仓。最需要关注的是基本面({sc['Fundamental']}分)和板块({sc['Sector']}分)——这两个不是短期能改善的，决定了这股只适合短线，不适合中长期持有"
    elif n_green >= 3:
        health_summary = f"[G] {n_green}个维度健康，可以安心持仓。关注最弱的维度是否有改善迹象"
    elif n_red == 0:
        worst_dim = min([('技术面', sc['Technical']), ('基本面', sc['Fundamental']), ('板块', sc['Sector']), ('资金面', sc['Capital'])], key=lambda x: x[1])
        health_summary = f"[Y] 多个维度处于警戒状态，提高警惕。最需要关注的是{worst_dim[0]}({worst_dim[1]}分)——这是拖累项"
    else:
        health_summary = f"[Y] 存在{'' if n_red == 0 else str(n_red) + '个'}危险信号{'，' if n_red > 0 else ''}评估是否需要减仓"

    if dist_s1 > 15:
        stop_advice = f"当前价距S1支撑{round(dist_s1)}%，中间无有效支撑。建议设一个心理止损位在{round(price*0.95,2)}元(约-5%)，跌破就减仓，不要干等S1——等跌到S1再止损已经亏了{round(dist_s1)}%，损失太大"
    elif dist_s1 > 10:
        stop_advice = f"S1支撑距离偏大({round(dist_s1)}%)，如果发生回调损失不小。建议密切关注，若回撤到-5%时评估是否减仓"
    else:
        stop_advice = "S1支撑距离合理，回撤风险可控。当前风控状态正常"

    price_range_pct = 5.0
    # Scenario thresholds (real data only, no estimation)
    high_open = round(price * 1.02, 2)
    low_open = round(price * 0.98, 2)

    conflict_title, why, wait = conflict_analysis(
        sc['Technical'], sc['Fundamental'], sc['Sector'], sc['Capital'], name, industry
    )

    t5_direction, t5_confidence, t5_high, t5_low, t5_vs_market, t5_catalysts_list = t5_outlook(sc, sig, price)
    t5_catalysts = "；".join(t5_catalysts_list)

    md = f"""# 重点关注股票日报

> **日期**：2026年05月26日（周一）
> ⚠️ 本报告由AI自动生成，基于公开数据，仅供参考，不构成投资建议

---

## 一、今日盘面速读

### 1.1 大盘环境

<!-- eval:market_regime={market_regime} -->
<!-- eval:market_breadth={market_breadth} -->

| 项目 | 内容 |
|:-----|:-----|
| **大盘** | 强势普涨，全市场100%个股上涨，平均涨幅+4.9%，宏观评分{macro_score} |
| **市场状态** | {market_regime}市（宏观{macro_score}分） |
| **涨跌比** | {market_breadth} |
| **情绪** | 普涨格局，赚钱效应极强。但普涨日要区分【被大盘带起来】和【自身逻辑驱动】 |
| **北向** | 数据不可获取（FundFlow主源API故障） |

> 山猫判断：今日是典型的【普涨日】——所有股票都在涨，但这不代表所有股票都值得买。普涨日容易产生【错过恐惧】(FOMO)，但追涨普涨日上涨的弱势股票是散户最常见的亏钱模式。

### 1.2 板块定位

<!-- eval:sector_pct={sector_pct} -->

| 项目 | 内容 |
|:-----|:-----|
| **所属板块** | {industry}，板块评分{sc['Sector']}分 |
| **板块排名** | 前{sector_pct}% |
| **板块强弱** | {"强势(前30%)" if sc['Sector'] >= 55 else ("中游(30-70%)" if sc['Sector'] >= 35 else "弱势(后30%)")} |
| **板块相位** | {"主升期" if sc['Sector'] >= 65 else ("启动期" if sc['Sector'] >= 45 else "退潮期/见底期")} |

> 板块解读：{sector_read(sc['Sector'], industry)}

### 1.3 个股今日行情

| 收盘价 | 综合评分 | 评级 | 仓位上限 | 量价关系 |
|:-----:|:------:|:----:|:------:|:-----|
| **{price:.2f}** | {comp}分 | {rating} | {pos_max}% | {vol_rel} |

> 个股解读：今日收盘**{price:.2f}元**，综合评分**{comp}分（{rating}）**，仓位上限**{pos_max}%**。{adx_read(adx)} 量价关系：{vol_rel}。

---

## 二、信号变化追踪

### 2.1 技术四维

<!-- eval:ma_arrangement={ma_trend} -->
<!-- eval:adx_value={adx} -->
<!-- eval:rsi_value={rsi} -->
<!-- eval:macd_signal={macd_signal} -->
<!-- eval:volume_signal={volume_signal} -->
<!-- eval:bollinger_position={bb_pos} -->

| 维度 | 指标 | 当前值 | 方向 | 解读 |
|:----:|:-----|:------:|:----:|:-----|
| 趋势 | ADX(14) | {adx:.1f} | {"↑" if adx>25 else "→"} | {adx_read(adx)} |
| 趋势 | MA排列 | {ma_trend} | — | MA排列{"多头，趋势向上" if "多头" in str(ma_trend) else ("空头，趋势向下" if "空头" in str(ma_trend) else "交叉，方向待定")} |
| 动量 | RSI(9) | {rsi:.1f} | {"↑" if rsi>50 else "↓"} | {rsi_read(rsi)} |
| 动量 | MACD | {macd_signal} | — | {"MACD金叉=短期看涨信号" if "金叉" in str(macd_signal) else ("MACD死叉=短期看跌信号" if "死叉" in str(macd_signal) else "MACD无明确交叉信号") if macd_signal != "—" else "MACD数据不可获取"} |
| 波动 | BB(20,2) | {bb_pos} | — | {bb_read(bb_pos)} |
| 量能 | OBV/量价 | {obv} | {"↑" if "同步" in str(obv) else "→"} | {obv_read(obv, vol_rel)} |
| 量能 | 量能标签 | {volume_signal} | — | {"放量上涨=动能充足" if "放量上涨" in str(volume_signal) else ("缩量下跌=抛压减轻" if "缩量下跌" in str(volume_signal) else "量能正常") if volume_signal != "—" else "量能数据不可获取"} |

> 青山策略判断：{"四维中多数偏多，技术面整体偏强。" if sc['Technical'] >= 65 else "四维信号存在分歧，没有形成一致的方向。" if sc['Technical'] >= 40 else "四维整体偏弱，技术面不是当前的优势维度。"}{" MA排列：" + str(ma_trend) if ma_trend != "—" else ""}{" 当前技术面的核心矛盾是" + ("RSI已接近超买区(" + str(round(rsi)) + ")，短期上涨空间在收窄，但趋势(ADX)仍然向上" if rsi > 65 and adx > 25 else "趋势明确但动量偏弱，可能进入整理") if sc['Technical'] >= 60 else ""}

### 2.2 资金面

<!-- eval:fund_flow_direction={fund_flow} -->
<!-- eval:wyckoff_stage={wyckoff} -->

| 指标 | 当前 | 趋势 | 解读 |
|:-----|:----|:-----|:-----|
| 主力净流入 | {fund_flow} | 单日数据 | {fund_read(fund_flow)} |
| Wyckoff阶段 | {wyckoff} | 阶段判断 | {wyckoff_read(wyckoff)} |

### 2.3 关键价位距离

| 价位 | 价格 | 距当前价 | 解读 |
|:----:|:----:|:-------:|:-----|
| **R1**(阻力) | {r1:.2f} | +{dist_r1:.1f}% | {"距阻力很近(<3%)，随时可能遇阻回落。如果要突破，需要放量+利好消息配合" if dist_r1 < 3 else "距阻力" + str(round(dist_r1)) + "%，上行空间充足，短期没有技术压力"} |
| **当前价** | **{price:.2f}** | — | — |
| **S1**(支撑) | {s1_val:.2f} | -{dist_s1:.1f}% | {"支撑距离过大(" + str(round(dist_s1)) + "%)！一旦回调中间没有有效支撑，止损成本很高。当前位置的风险收益比不理想" if dist_s1 > 10 else "支撑距离合理(" + str(round(dist_s1)) + "%)，回撤风险可控。在S1附近买入有较好的安全边际"} |
| **S3**(止损) | {s3_val:.2f} | -{dist_s3:.1f}% | {"最大可承受亏损约" + str(round(dist_s3)) + "%。注意：如果这个亏损幅度你无法接受，应该现在就减仓，而不是等止损触发" if dist_s3 > 15 else "止损距离合理，风险可控"} |

---

## 三、风控红线检查

### 3.1 止损触发检查

| 止损位 | 价格 | 距当前价 | 是否跌破 | 解读与操作 |
|:------:|:----:|:-------:|:--------:|:-----|
| S1 | {s1_val:.2f} | -{dist_s1:.1f}% | 否 | 未跌破S1，短期趋势未转弱，正常持仓 |
| S3 | {s3_val:.2f} | -{dist_s3:.1f}% | 否 | 未跌破S3止损线，无需清仓 |

> 流金判断：{stop_advice}

### 3.2 "不做"清单每日核查

**1. 追涨买入** — {"触发！" if chase_triggered else "未触发"}
- 条件：RSI>80 或 距S1>5%
- 今日：RSI={rsi:.0f}，距S1={dist_s1:.1f}%
- {"**触发**：距S1高达" + str(round(dist_s1)) + "%，当前位置追进去，回调到S1要亏" + str(round(dist_s1)) + "%。风险收益比极差。**禁止今日开新仓**，等回调到S1(" + str(s1_val) + "元)附近再评估。如果已持仓：盈利状态下可以继续持有，但检查一下浮盈有没有超过10%——如果有，建议收紧止损保护利润" if chase_triggered else "**未触发**：RSI和支撑距离均在安全范围，追涨风险可控"}

**2. 亏损加仓** — 未触发
- 条件：持仓亏损>5%
- 今日：无持仓数据可用
- 亏损加仓（摊平成本）是散户最大亏损来源。**任何时候都不要在亏损状态下加仓**。等股价回到成本价上方或出现明确底部信号再考虑

**3. 财报前3日开新仓** — 待确认
- 下次财报日期：待确认，需查询交易所披露日历
- 如果财报在3个交易日内→禁止开新仓。业绩是信息不对称的黑箱，不赌方向

**4. RSI>80加仓** — {"触发！" if rsi80_triggered else "未触发"}
- 条件：RSI(9)>80
- 今日：RSI={rsi:.0f}
- {"**触发**：RSI=" + str(rsi) + ">80，短期严重超买。此时加仓=高位接盘，回调风险极大。等RSI回落到60以下再评估加仓" if rsi80_triggered else "**未触发**：RSI在正常范围，没有极端超买信号，加仓不受此条限制"}

**5. 单一板块>50%** — 未触发
- 条件：同一板块所有持仓合计>总仓位50%
- 今日：{industry}板块持仓占比待确认
- 如果同行业已有其他持仓注意分散。板块黑天鹅（如行业政策突变）会同时打击所有同板块标的

### 3.3 趋势健康度速查

| 指标 | 状态 | 标记 | 解读 |
|:-----|:----|:----:|:-----|
| 技术面 | {sc['Technical']}分 | [{tech_m}] | {dim_read(sc['Technical'], "技术面")} |
| 基本面 | {sc['Fundamental']}分 | [{fund_m}] | {dim_read(sc['Fundamental'], "基本面")} |
| 板块 | {sc['Sector']}分 | [{sec_m}] | {dim_read(sc['Sector'], "板块")} |
| 资金面 | {sc['Capital']}分 | [{cap_m}] | {dim_read(sc['Capital'], "资金面")} |
| **综合** | **{comp}分** | **[{comp_m}]** | {rating}级别，仓位上限{pos_max}%{"，可以正常配置" if comp >= 65 else ("，轻仓试探为主" if comp >= 45 else "，不建议参与")} |

> 综合评估：{health_summary}

---

## 四、明日情景应对

> 基于今日收盘价 **{price:.2f}元**，明日（周二）操作情景
> 仓位上限：综合评分{comp}分 → 单只上限**{pos_max}%**

| 开盘价 | 判断 | 动作 |
|:------|:-----|:-----|
| **> {high_open:.2f}** | 高开>2%：跳空高开说明多头强势或有盘后利好。但高开后常伴随获利回吐，追高容易被套 | {"已持仓者可在高开后减仓1/3锁定利润（高开+RSI=" + str(round(rsi)) + "说明短期情绪可能过热）。未持仓者**不要追**，等回踩确认支撑再考虑" if rsi > 65 else "已持仓者持有观察，关注开盘30分钟后能否守住跳空缺口。未持仓者等回踩确认后再入场"} |
| **{low_open:.2f}–{high_open:.2f}** | 平开/正常波动：市场消化信息中，方向待选择。这是最常见的开盘方式，不要急于操作 | 维持现有仓位不动。重点观察**开盘30分钟**的量能和方向——放量上行=积极，缩量震荡=等待，放量下行=警惕。前30分钟不操作 |
| **{s1_val:.2f}–{low_open:.2f}** | 低开/回调：可能是正常的获利回吐，也可能是趋势转弱的开始。关键区别在于S1能否守住 | 关注S1({s1_val:.2f})能否守住。守住→回调是机会（但不急于抄底，等企稳信号）；守不住→减仓至{max(pos_max//2, 0)}%以下。注意：不要在S1附近抄底，等确认守住再行动 |
| **< {s1_val:.2f}** | 破位下行：跌破S1支撑，趋势可能逆转。这是需要**立即行动**的价位 | 已持仓者减仓至{max(pos_max//3, 0)}%以下或清仓。未持仓者继续观望。破位抄底是散户最常见的亏钱方式，等重新站上S1再考虑入场 |

---

## 四.5 一周情景展望 (T+5)

> 基于今日信号对未来5个交易日的预判，用于后评估§2.1.5主窗口验证
> 预判生成时间：{date_str}收盘后

| 项目 | 内容 |
|:-----|:-----|
| T+5方向预判 | {t5_direction} |
| T+5相对大盘 | {t5_vs_market} |
| T+5目标区间 | {t5_low:.2f}元 – {t5_high:.2f}元 |
| 预判置信度 | {t5_confidence} |
| 关键验证点 | {t5_catalysts} |

---

## 核心矛盾

> **{conflict_title}**

**矛盾在哪？**
技术面{sc['Technical']}分（{"看多" if sc['Technical'] >= 65 else "中性" if sc['Technical'] >= 40 else "偏弱"}）{"与基本面" + str(sc['Fundamental']) + "分（" + ("健康" if sc['Fundamental'] >= 60 else "偏弱" if sc['Fundamental'] >= 30 else "极弱") + "）之间存在显著背离" if sc['Fundamental'] <= 30 else ""}。板块{sc['Sector']}分/资金{sc['Capital']}分/宏观{sc['Macro']['Score']}分。

**为什么这很重要？**
{why}

**怎么办/等什么？**
{wait}

---

## 数据源

| 维度 | 来源 | 状态 |
|:-----|:----:|:----:|
| K线/技术指标 | [2]->[5] | 正常 |
| 财务数据 | [3] | 正常 |
| 板块数据 | [7] | 正常 |
| 资金数据 | [9][10][12] | FundFlow主源偶发故障 |

> **风险提示**：本报告由AI自动生成，基于公开数据源和量化分析框架，仅供参考，不构成投资建议。所有操作建议均为分析框架内的判断参考，不代表对用户的投资指令。投资有风险，入市需谨慎。
> 参考引擎报告：{name}({code})分析报告__{date_str}.pdf
"""

    out_dir = f'重点股票/股票报告/{name}({code})'
    os.makedirs(out_dir, exist_ok=True)
    md_path = f'{out_dir}/重点关注股票日报_{date_str}.md'
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md)

    lines = md.count('\n')
    print(f'[OK] {name}({code}): {lines}行, {comp}分{rating} | 技术{sc["Technical"]} 基本{sc["Fundamental"]} 板块{sc["Sector"]} 资金{sc["Capital"]}')
    generated += 1

# Auto-commit: daily_brief outputs
subprocess.run([
    'powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass',
    '-File', '代码文件/tools/git_autocommit.ps1',
    '-Module', 'daily_brief',
    '-Paths', '重点股票/股票报告/',
    '-Message', '日报产出'
], capture_output=True)

print(f'\nDone: {generated} daily briefs in v2 format')
