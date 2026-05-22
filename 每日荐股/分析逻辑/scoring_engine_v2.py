#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
铁律量化 · 否决+评分引擎 v2
=================================
流程: 绝对否决 → 评分 → 条件否决 → 排序
输出: data_scored.json (含 VetoStatus 字段)
"""
import json, math, os, sys

ROOT = r"C:\Users\34269\Documents\Claude\股票分析"
DATA_FILE = os.path.join(ROOT, "data_full.json")
OUTPUT_FILE = os.path.join(ROOT, "data_scored.json")

# ============ 技术指标计算 ============
def calc_ma(values, period):
    result = []
    for i in range(len(values)):
        if i < period - 1:
            result.append(None)
        else:
            result.append(sum(values[i-period+1:i+1]) / period)
    return result

def calc_ema(values, n):
    result = []
    k = 2.0 / (n + 1)
    for i in range(len(values)):
        if i == 0:
            result.append(values[i])
        else:
            result.append(values[i] * k + result[-1] * (1 - k))
    return result

def calc_rsi(values, period=14):
    result = []
    for i in range(len(values)):
        if i < period:
            result.append(None)
            continue
        gains, losses = 0, 0
        for j in range(i - period + 1, i + 1):
            diff = values[j] - values[j-1]
            if diff > 0:
                gains += diff
            else:
                losses -= diff
        avg_gain = gains / period
        avg_loss = losses / period
        if avg_loss == 0:
            result.append(100.0)
        else:
            result.append(round(100 - 100 / (1 + avg_gain / avg_loss), 2))
    return result

def calc_macd(values, fast=12, slow=26, signal=9):
    ema_fast = calc_ema(values, fast)
    ema_slow = calc_ema(values, slow)
    dif = [ema_fast[i] - ema_slow[i] for i in range(len(values))]
    dea = calc_ema(dif, signal)
    macd = [(dif[i] - dea[i]) * 2 for i in range(len(dif))]
    return {"DIF": dif, "DEA": dea, "MACD": macd}

# ============ 否决规则 ============
PE_ABSOLUTE_THRESHOLD = {
    # 科技/成长行业 — 高PE是常态，大幅提高阈值让综合评分说话
    "电子": 300, "计算机": 300, "通信": 250,
    "汽车": 150, "电力设备": 150, "机械设备": 150, "传媒": 150,
    # 消费/医药 — 适度放宽
    "食品饮料": 60, "医药生物": 80,
    # 金融 — 低PE行业，维持严格
    "银行": 15, "非银金融": 20,
}
PE_COND_THRESHOLD = 80  # 条件否决 PE>80
PE_COND_EXEMPT_SCORE = 85
C3_EXEMPT_SCORE = 75   # MA5<MA10 豁免线（短期回踩）
C5_EXEMPT_SCORE = 75   # MA10≤MA20 豁免线（高分豁免）

def check_absolute_vetoes(s):
    """8条绝对否决, 返回 (否决id, 原因) 或 None"""
    closes = s.get("KClose", [])
    price = s.get("Price", 0)
    pe = s.get("PE", 0)
    industry = s.get("Industry", "")
    eps = s.get("EPS", None)
    mkt_cap = s.get("MktCap", 0)
    change_pct = s.get("ChangePct", 0)

    # V1: 已降级为条件否决(C5)，移至 check_conditional_vetoes

    # V0: ST股票直接否决
    name = s.get("Name", "")
    if "ST" in name or "st" in name.lower():
        return ("vetoed_abs_st", f"ST股票: {name} 带帽风险股，不纳入推荐")

    # V2: PE相对估值超标
    if pe > 0:
        threshold = PE_ABSOLUTE_THRESHOLD.get(industry, 80)
        if pe > threshold:
            return ("vetoed_abs_2", f"PE估值泡沫: {pe:.0f} > {threshold}({industry})")

    # V3: 30日涨幅 > 50%
    if len(closes) >= 30:
        close_30d = closes[-30]
        if close_30d > 0:
            gain_30d = (price - close_30d) / close_30d * 100
            if gain_30d > 50:
                return ("vetoed_abs_3", f"短期暴涨: 30日涨幅{gain_30d:.0f}% > 50%")

    # V4: PE无法计算(EPS为0/空/负)
    if eps is None or eps <= 0:
        if pe <= 0:
            return ("vetoed_abs_4", "财务数据异常: EPS≤0且PE无法计算")

    # V5: 流动性枯竭
    volume = s.get("Volume", 0)
    turnover_rate = s.get("TurnoverRate", 0) or 0
    if price > 0:
        turnover_value = volume * price / 100  # 万元（Volume单位为手，*100=股）
        if turnover_value < 1500 and turnover_rate < 0.5:
            return ("vetoed_abs_5", f"流动性枯竭: 成交额{turnover_value:.0f}万 < 3000万")

    # V6: 高负债率 (需要财务数据，暂用EPS缺失作为代理)
    # V7: 连续2季亏损 (需要财报数据)
    # 这两条需要完整的财务数据，在当前数据源中难以获取，暂跳过

    return None  # 通过绝对否决


# ============ 板块动量计算 ============
def classify_phase(chg_pct, turn_rate):
    """根据板块指数涨跌幅和换手率判断相位 (与 gen_daily_html.ps1 的 Get-PhaseName 一致)"""
    if turn_rate > 5 and chg_pct > 2:
        return "高潮期"
    elif turn_rate > 3 and chg_pct < -3:
        return "衰退期"
    elif turn_rate > 3 and chg_pct > 0:
        return "主升调整"
    elif turn_rate > 2 and chg_pct < -1:
        return "主升调整"
    elif chg_pct >= -1.5 and turn_rate <= 4:
        return "潜伏期"
    elif chg_pct >= -2 and turn_rate <= 2:
        return "潜伏期"
    else:
        return "潜伏期"


def calc_sector_bonus(phase, chg_pct, count):
    """根据板块相位和涨幅确定资金面/消息面试加分"""
    if count < 3:
        # 板块内股票太少，相位可能失真，降级为基准
        return 1, 0
    if phase == "高潮期":
        return 4, 2
    elif phase == "主升调整":
        if chg_pct > 3:
            return 3, 1
        else:
            return 2, 1
    elif phase == "衰退期":
        return -3, -1
    else:  # 潜伏期
        return 1, 0


def compute_sector_phases(stocks, sector_data=None, sector_fund_flow=None):
    """
    计算各板块的动量相位和加权分数。

    优先使用 real sector_data（东方财富行业板块API返回的真实市场数据），
    如果某个行业在 real data 中不存在，则回退到池内聚合计算。

    Args:
        stocks: 所有股票列表（含 Industry 字段）
        sector_data: 真实板块行情数据 [{SectorCode, SectorName, Index, ChangePct, Turnover}]
        sector_fund_flow: 真实板块资金流 [{SectorCode, SectorName, NetInflow, MainInflow, ChangePct, TurnRate}]

    Returns:
        { industry: {phase, avg_chg, avg_turn, count, momentum_score, money_bonus, news_bonus} }
    """
    # 构建真实板块数据字典（keyed by SectorName）
    real_sectors = {}
    if sector_data:
        fund_map = {}
        if sector_fund_flow:
            for f in sector_fund_flow:
                fund_map[f["SectorCode"]] = f

        for sd in sector_data:
            name = sd["SectorName"]
            code = sd["SectorCode"]
            fund = fund_map.get(code, {})
            turn_rate = fund.get("TurnRate", 0) if isinstance(fund.get("TurnRate"), (int, float)) else 5.0
            # 使用板块换手率（来自资金流API）；如果无数据则用成交额估算
            if turn_rate <= 0:
                index_val = sd.get("Index", 0) or 0
                turnover = sd.get("Turnover", 0) or 0
                if index_val > 0:
                    # 估算换手率 = 成交额 / 指数值（只是一个量级参考）
                    turn_rate = min(15, max(0.5, turnover / index_val / 10000))

            chg_pct = sd.get("ChangePct", 0) or 0
            phase = classify_phase(chg_pct, turn_rate)
            momentum = chg_pct * 0.5 + turn_rate * 1.0
            money_bonus, news_bonus = calc_sector_bonus(phase, chg_pct, 999)  # count=999表示真实数据

            real_sectors[name] = {
                "phase": phase,
                "avg_chg": chg_pct,
                "avg_turn": round(turn_rate, 2),
                "count": -1,  # -1 表示真实市场数据
                "momentum_score": round(momentum, 2),
                "money_bonus": money_bonus,
                "news_bonus": news_bonus,
                "sector_code": code
            }

    # 池内聚合计算（作为未在真实数据中找到的行业的 fallback）
    sectors = {}
    for s in stocks:
        ind = s.get("Industry", "未知")
        if ind not in sectors:
            sectors[ind] = []
        sectors[ind].append(s)

    result = {}
    # 先用真实数据
    if real_sectors:
        result.update(real_sectors)

    # 对每个行业：如果在 result 中已有（来自真实数据），跳过；否则用池内聚合
    for ind, members in sectors.items():
        if ind in result:
            continue  # 真实数据已覆盖

        chgs = [s.get("ChangePct", 0) or 0 for s in members]
        turns = [s.get("TurnoverRate", 0) or 0 for s in members]
        avg_chg = sum(chgs) / len(chgs) if chgs else 0
        avg_turn = sum(turns) / len(turns) if turns else 0
        count = len(members)
        phase = classify_phase(avg_chg, avg_turn)
        money_bonus, news_bonus = calc_sector_bonus(phase, avg_chg, count)

        result[ind] = {
            "phase": phase,
            "avg_chg": round(avg_chg, 2),
            "avg_turn": round(avg_turn, 2),
            "count": count,
            "momentum_score": round(avg_chg * 0.5 + avg_turn * 1.0, 2),
            "money_bonus": money_bonus,
            "news_bonus": news_bonus,
        }

    return result


def compute_scores(s, sector_info=None):
    """计算六维评分, 返回 (scores_dict, tech_detail)"""
    closes = s.get("KClose", [])
    volumes = s.get("KVolume", [])
    price = s.get("Price", 0)
    chg_pct = s.get("ChangePct", 0)
    turnover = s.get("TurnoverRate", 0) or 0
    amplitude = s.get("Amplitude", 0) or 0
    pe = s.get("PE", 0)
    mkt_cap = s.get("MktCap", 0)
    fund_net = s.get("FundMainNet", 0)
    industry = s.get("Industry", "")

    min_closes = min(closes[-5:]) if len(closes) >= 5 else price
    max_closes = max(closes[-5:]) if len(closes) >= 5 else price

    # --- S_Base: 基础门槛 (10分) ---
    base = 10
    if price < 5: base -= 3
    if turnover < 0.3: base -= 2
    if mkt_cap < 300000: base -= 2  # 市值<30亿
    base = max(1, min(10, base))

    # --- S_Fund: 基本面 (20分) ---
    fund = 12  # 默认中等
    if 0 < pe <= 15: fund = 18
    elif 15 < pe <= 30: fund = 16
    elif 30 < pe <= 50: fund = 14
    elif 50 < pe <= 80: fund = 10
    elif pe > 80: fund = 6
    if mkt_cap > 1000000: fund += 2  # 大盘溢价
    fund = max(1, min(20, fund))

    # --- S_Tech: 技术面 (25分) - 复用scoring_engine.py逻辑 ---
    if len(closes) >= 20:
        ma5_arr = calc_ma(closes, 5)
        ma10_arr = calc_ma(closes, 10)
        ma20_arr = calc_ma(closes, 20)
        rsi_arr = calc_rsi(closes, 14)
        macd = calc_macd(closes)
        vol_ma5_arr = calc_ma(volumes, 5)

        i = len(closes) - 1
        ma5 = ma5_arr[i] if ma5_arr[i] is not None else 0
        ma10 = ma10_arr[i] if ma10_arr[i] is not None else 0
        ma20 = ma20_arr[i] if ma20_arr[i] is not None else 0
        rsi = rsi_arr[i] if rsi_arr[i] is not None else 50
        dif = macd["DIF"][i] if i < len(macd["DIF"]) else 0
        dea = macd["DEA"][i] if i < len(macd["DEA"]) else 0
        vol_latest = volumes[i] if i < len(volumes) else 0
        vol_ma5 = vol_ma5_arr[i] if vol_ma5_arr[i] is not None else 0

        # 前值
        prev_ma5 = ma5_arr[i-1] if i-1 >= 0 and ma5_arr[i-1] is not None else None
        prev_ma10 = ma10_arr[i-1] if i-1 >= 0 and ma10_arr[i-1] is not None else None
        prev_ma20 = ma20_arr[i-1] if i-1 >= 0 and ma20_arr[i-1] is not None else None
        prev_dif = macd["DIF"][i-1] if i-1 >= 0 else None
        prev_dea = macd["DEA"][i-1] if i-1 >= 0 else None

        # 构建K线历史
        klines_10d = []
        for j in range(max(0, i-9), i+1):
            prev_c = closes[j-1] if j-1 >= 0 else closes[j]
            chg = (closes[j] - prev_c) / prev_c * 100 if prev_c > 0 else 0
            klines_10d.append({
                "Open": s.get("KOpen", [])[j] if j < len(s.get("KOpen", [])) else 0,
                "High": s.get("KHigh", [])[j] if j < len(s.get("KHigh", [])) else 0,
                "Low": s.get("KLow", [])[j] if j < len(s.get("KLow", [])) else 0,
                "Close": closes[j], "Volume": volumes[j],
                "ChgPct": chg, "PrevClose": prev_c
            })

        klines_5d = klines_10d[-5:] if len(klines_10d) >= 5 else klines_10d
        prices_5d = [k["ChgPct"] for k in klines_5d]
        vol_ratio = vol_latest / vol_ma5 if vol_ma5 > 0 else 1

        # 子项评分
        s1 = _score_ma_system(ma5, ma10, ma20, price)
        s2 = _score_ma_converge(ma5, ma10, ma20, prev_ma5, prev_ma10, prev_ma20)
        s3 = _score_volume_price(chg_pct, vol_latest, vol_ma5, prices_5d, klines_5d)
        s4 = _score_bottom_support(klines_10d, price, ma20)
        s5 = _score_rsi(rsi, chg_pct, vol_ratio)
        s6 = _score_macd(dif, dea, prev_dif, prev_dea)
        s7 = _score_breakout_confirmation(klines_10d, chg_pct, vol_latest, vol_ma5, price)

        raw_tech = s1 + s2 + s3 + s4 + s5 + s6 + s7
        tech = round(raw_tech / 27 * 25)
        tech = max(1, min(25, tech))
        tech_detail = f"{s1}+{s2}+{s3}+{s4}+{s5}+{s6}+{s7}={raw_tech}→{tech}"

        # ---- 存储技术指标用于报告分析 ----
        s["MA5"] = round(ma5, 2)
        s["MA10"] = round(ma10, 2)
        s["MA20"] = round(ma20, 2)
        s["RSI"] = round(rsi, 1)
        s["VolRatio"] = round(vol_ratio, 2)

        # MACD状态
        if prev_dif is not None and prev_dea is not None:
            if dif > dea and prev_dif <= prev_dea:
                s["MACD_Status"] = "金叉"
            elif dif <= dea and prev_dif > prev_dea:
                s["MACD_Status"] = "死叉"
            elif dif > dea > 0:
                s["MACD_Status"] = "多头"
            elif dif <= dea:
                s["MACD_Status"] = "空头"
            else:
                s["MACD_Status"] = "中性"
        else:
            s["MACD_Status"] = "中性"

        # 均线状态描述
        if ma5 > ma10 > ma20 and price > ma20:
            ma_desc = f"MA5({ma5:.1f})>MA10({ma10:.1f})>MA20({ma20:.1f}) 多头排列"
        elif ma5 > ma10 > ma20:
            ma_desc = f"MA5({ma5:.1f})>MA10({ma10:.1f})>MA20({ma20:.1f}) 短中期多头"
        elif ma10 > ma5 > ma20:
            ma_desc = f"MA10({ma10:.1f})>MA5({ma5:.1f})>MA20({ma20:.1f}) 短期整理"
        elif ma10 <= ma20:
            if price > ma20 * 1.02:
                ma_desc = f"MA10({ma10:.1f})≤MA20({ma20:.1f}) 价格突破均线，趋势转多"
            elif price > ma10:
                ma_desc = f"MA10({ma10:.1f})≤MA20({ma20:.1f}) 价格站上均线，待确认"
            else:
                ma_desc = f"MA10({ma10:.1f})≤MA20({ma20:.1f}) 均线死叉"
        else:
            ma_desc = f"MA5({ma5:.1f})/MA10({ma10:.1f})/MA20({ma20:.1f}) 均线收敛"

        # 量价关系描述
        if vol_ratio > 1.5 and chg_pct > 3:
            vol_desc = f"放量上涨(量比{vol_ratio:.1f})"
        elif vol_ratio > 1.5 and chg_pct < -2:
            vol_desc = f"放量下跌(量比{vol_ratio:.1f})"
        elif vol_ratio < 0.7:
            vol_desc = f"缩量整理(量比{vol_ratio:.1f})"
        else:
            vol_desc = f"量能正常(量比{vol_ratio:.1f})"

        # 综合技术分析描述
        tech_parts = [ma_desc, vol_desc]
        if rsi < 30:
            tech_parts.append(f"RSI({rsi})超卖")
        elif rsi > 70:
            tech_parts.append(f"RSI({rsi})超买")
        else:
            tech_parts.append(f"RSI({rsi})中性")

        if s6 > 0 and s["MACD_Status"]:
            tech_parts.append(f"MACD{s['MACD_Status']}")

        s["TechAnalysis"] = " | ".join(tech_parts)
    else:
        tech = 10
        tech_detail = "数据不足"

    # --- S_Money: 资金面 (20分) + 板块动量加分 ---
    money = 10
    if 2 <= turnover <= 5: money += 4
    elif 5 < turnover <= 8: money += 2
    elif turnover > 8: money -= 2
    if 3 <= amplitude <= 7: money += 3
    elif amplitude > 10: money -= 2
    if fund_net > 0: money += 2
    elif fund_net < -10000000: money -= 2
    # 板块动量加分：热门板块资金关注度高
    sector_bonus = 0
    if sector_info:
        money += sector_info["money_bonus"]
        sector_bonus = sector_info["money_bonus"]
    money = max(1, min(20, money))

    # --- S_News: 消息面/RS强度 (20分) + 板块催化加分 ---
    news = 10
    # 用RSI和涨跌幅代替RS强度
    if len(closes) >= 5:
        if chg_pct > 3: news += 4
        elif chg_pct > 1: news += 2
        elif chg_pct < -3: news -= 3
    if sector_info:
        news += sector_info["news_bonus"]
    news = max(1, min(20, news))

    # --- S_Risk: 风控 (5分) ---
    risk = 3
    if pe > 0 and pe < 60: risk += 1
    if 1 <= turnover <= 8: risk += 1
    risk = max(1, min(5, risk))

    total = base + fund + tech + money + news + risk
    total = max(0, min(100, total))

    return {
        "S_Base": base, "S_Fund": fund, "S_Tech": tech,
        "S_Money": money, "S_News": news, "S_Risk": risk,
        "TotalScore": total
    }, tech_detail


# ============ 技术面子项评分（从scoring_engine.py复用） ============
def _score_ma_system(ma5, ma10, ma20, price):
    if ma5 is None or ma10 is None or ma20 is None:
        return 3
    if ma5 > ma10 > ma20 and price > ma20: return 6
    if ma5 > ma10 > ma20: return 5
    if ma10 > 0 and ma20 > 0:
        spread = max(ma5, ma10, ma20) / min(ma5, ma10, ma20) - 1
        if spread < 0.01: return 6
    if ma10 > ma5 > ma20: return 3
    if ma10 <= ma20: return 1
    return 4

def _score_ma_converge(ma5, ma10, ma20, prev_ma5, prev_ma10, prev_ma20):
    if any(v is None for v in [ma5, ma10, ma20]): return 3
    if ma10 <= 0 or ma20 <= 0: return 3
    spread = max(ma5, ma10, ma20) / min(ma5, ma10, ma20) - 1
    if prev_ma5 and prev_ma10 and prev_ma20 and min(prev_ma5, prev_ma10, prev_ma20) > 0:
        prev_spread = max(prev_ma5, prev_ma10, prev_ma20) / min(prev_ma5, prev_ma10, prev_ma20) - 1
        if prev_spread < 0.02 and spread > prev_spread and ma5 > ma10: return 5
    if spread < 0.02: return 4
    if spread < 0.05: return 3
    if spread < 0.08: return 2
    return 0

def _score_volume_price(chg_pct, volume, vol_ma5, prices_5d, klines_5d):
    if len(klines_5d) >= 5 and volume > 0 and vol_ma5 > 0:
        vol_ratio = volume / vol_ma5
        shake_days = 0
        for k in klines_5d:
            amp = (k["High"] - k["Low"]) / k["PrevClose"] * 100 if k["PrevClose"] > 0 else 0
            if amp > 5: shake_days += 1
        if shake_days >= 2 and vol_ratio > 1.5 and chg_pct > 3:
            return 4
        if all(abs(k["ChgPct"]) < 3 for k in klines_5d[:-1]) and chg_pct > 3 and vol_ratio > 1.5:
            return 5
    if chg_pct >= 3 and vol_ma5 > 0 and volume > vol_ma5 * 1.5:
        return 3
    if 0 < chg_pct < 2 and vol_ma5 > 0 and vol_ma5 * 0.8 <= volume <= vol_ma5 * 1.2:
        return 5
    if prices_5d:
        small_up = sum(1 for p in prices_5d if 0 < p < 2)
        if small_up >= 3: return 4
    if chg_pct < 0 and vol_ma5 > 0 and volume > vol_ma5 * 1.5 and chg_pct < -3:
        return 0
    return 3

def _score_bottom_support(klines_10d, price, ma20):
    lows_10d = [k["Low"] for k in klines_10d]
    highs_10d = [k["High"] for k in klines_10d]
    if len(klines_10d) >= 10:
        prev_high = max(highs_10d[:-1])
        if price > prev_high:
            shake = sum(1 for k in klines_10d[-10:-1] if k["PrevClose"] > 0 and (k["High"]-k["Low"])/k["PrevClose"]*100 > 5)
            if shake >= 3: return 4
    if len(lows_10d) >= 10:
        seg = len(lows_10d) // 2
        if min(lows_10d[seg:]) > min(lows_10d[:seg]): return 4
    if ma20 and ma20 > 0:
        for k in klines_10d[-3:]:
            if abs(k["Low"] - ma20) / ma20 < 0.01: return 3
    return 2

def _score_rsi(rsi, chg_pct, vol_ratio):
    if rsi is None: return 2
    if 40 <= rsi <= 55: return 3
    if 30 <= rsi < 40: return 2
    if 55 < rsi <= 70: return 2
    if rsi < 30: return 1
    if rsi > 70:
        # 突破中RSI>70例外
        if chg_pct > 3 and vol_ratio > 1.5: return 2
        return 0
    return 2

def _score_macd(dif, dea, prev_dif, prev_dea):
    if dif is None or dea is None: return 1
    if dif > dea and prev_dif is not None and prev_dea is not None:
        if prev_dif <= prev_dea: return 2
    if dif > dea > 0: return 1
    if dif <= dea: return 0
    return 1

def _score_breakout_confirmation(klines_10d, chg_pct, volume, vol_ma5, price):
    bonus = 0
    if len(klines_10d) >= 10 and volume > 0 and vol_ma5 > 0:
        vol_ratio = volume / vol_ma5
        shake_days = sum(1 for k in klines_10d if k["PrevClose"] > 0 and (k["High"]-k["Low"])/k["PrevClose"]*100 > 5)
        if shake_days >= 3 and chg_pct > 3 and vol_ratio > 1.5:
            bonus += 1
        prev_high = max(k["High"] for k in klines_10d[:-1])
        if price > prev_high and chg_pct > 3 and vol_ratio > 1.5:
            bonus += 1
    return bonus


def check_conditional_vetoes(s, scores):
    """6条条件否决, 返回 (否决id, 原因) 或 None"""
    closes = s.get("KClose", [])
    price = s.get("Price", 0)
    pe = s.get("PE", 0)
    total = scores["TotalScore"]
    industry = s.get("Industry", "")

    # C1: PE偏高(科技制造>120)
    if pe > 120 and industry in ("电子", "计算机", "通信", "汽车", "电力设备", "机械设备"):
        if total < PE_COND_EXEMPT_SCORE:
            return ("vetoed_cond_1", f"科技PE过高: {pe:.0f} > 120 (豁免需总分≥{PE_COND_EXEMPT_SCORE})")

    # C2: PE偏高(高成长>80)
    if pe > PE_COND_THRESHOLD:
        if total < PE_COND_EXEMPT_SCORE:
            return ("vetoed_cond_2", f"PE过高: {pe:.0f} > {PE_COND_THRESHOLD} (豁免需总分≥{PE_COND_EXEMPT_SCORE})")

    # C3: MA5 < MA10*0.99 (短期均线回踩)
    if len(closes) >= 10:
        ma5 = calc_ma(closes, 5)[-1]
        ma10 = calc_ma(closes, 10)[-1]
        if ma5 is not None and ma10 is not None and ma5 < ma10 * 0.97:
            if total < C3_EXEMPT_SCORE:
                return ("vetoed_cond_3", f"短期均线回踩: MA5({ma5:.2f}) < MA10({ma10:.2f})×0.97 (豁免需总分≥{C3_EXEMPT_SCORE})")

    # C4: 30日涨幅过高 (市场自适应)
    if len(closes) >= 30 and closes[-30] > 0:
        gain_30d = (price - closes[-30]) / closes[-30] * 100
        if gain_30d > 50:
            return ("vetoed_cond_4", f"30日涨幅{gain_30d:.0f}% > 50%")

    # C5: MA10 ≤ MA20 (原绝对否决V1降级，允许高分豁免)
    if len(closes) >= 20:
        ma10 = calc_ma(closes, 10)[-1]
        ma20 = calc_ma(closes, 20)[-1]
        if ma10 is not None and ma20 is not None and ma10 <= ma20:
            if total < C5_EXEMPT_SCORE:
                ma5 = calc_ma(closes, 5)[-1]
                detail = f"MA10({ma10:.2f})≤MA20({ma20:.2f})"
                if ma5 is not None and ma5 > ma10:
                    pass  # 短期仍在多头，豁免
                else:
                    return ("vetoed_cond_5", f"均线死叉: {detail} (豁免需总分≥{C5_EXEMPT_SCORE})")

    return None


def main():
    if not os.path.exists(DATA_FILE):
        print(f"错误: {DATA_FILE} 不存在，请先运行 batch_data_collector.ps1")
        sys.exit(1)

    with open(DATA_FILE, "r", encoding="utf-8-sig") as f:
        raw = json.load(f)

    # 兼容新旧两种格式：
    #   旧格式: [stock1, stock2, ...]
    #   新格式: { "Stocks": [...], "SectorData": [...], "SectorFundFlow": [...] }
    if isinstance(raw, dict):
        stocks = raw.get("Stocks", [])
        sector_data = raw.get("SectorData", None)
        sector_fund_flow = raw.get("SectorFundFlow", None)
    else:
        stocks = raw
        sector_data = None
        sector_fund_flow = None
    print(f"加载 {len(stocks)} 只股票数据\n")

    # 计算板块动量（优先使用东方财富真实市场数据）
    sector_phases = compute_sector_phases(stocks, sector_data, sector_fund_flow)
    for ind, info in sorted(sector_phases.items(), key=lambda x: x[1]["money_bonus"], reverse=True):
        bn = info["money_bonus"]
        sign = "+" if bn >= 0 else ""
        cnt = f"{info['count']}只" if info['count'] > 0 else "市场数据"
        print(f"  板块 {ind:8s} | {info['phase']:5s} | 涨幅{info['avg_chg']:+.2f}% 换手{info['avg_turn']:.2f}% | 资金面{sign}{bn}分 ({cnt})")

    passed = []
    vetoed = []

    for s in stocks:
        code = s.get("Code", "")
        name = s.get("Name", "")
        sector_info = sector_phases.get(s.get("Industry", ""))

        # Phase A: 绝对否决
        veto = check_absolute_vetoes(s)
        if veto:
            s["VetoStatus"] = veto[0]
            s["VetoReason"] = veto[1]
            # 给默认低分（含板块动量加分）
            bonus = sector_info["money_bonus"] if sector_info else 0
            s["S_Base"] = s.get("S_Base", 5)
            s["S_Fund"] = s.get("S_Fund", 10)
            s["S_Tech"] = s.get("S_Tech", 13)
            s["S_Money"] = max(1, min(20, (s.get("S_Money", 10) or 10) + bonus))
            s["S_News"] = s.get("S_News", 10)
            s["S_Risk"] = s.get("S_Risk", 3)
            s["TotalScore"] = s["S_Base"] + s["S_Fund"] + s["S_Tech"] + s["S_Money"] + s["S_News"] + s["S_Risk"]
            if sector_info:
                s["SectorPhase"] = sector_info["phase"]
            vetoed.append(s)
            continue

        # Phase B: 评分（传入板块动量信息）
        scores, tech_info = compute_scores(s, sector_info)
        s.update(scores)

        # Phase C: 条件否决
        veto = check_conditional_vetoes(s, scores)
        if veto:
            s["VetoStatus"] = veto[0]
            s["VetoReason"] = veto[1]
            if sector_info:
                s["SectorPhase"] = sector_info["phase"]
            vetoed.append(s)
            continue

        s["VetoStatus"] = "passed"
        s["VetoReason"] = ""
        if sector_info:
            s["SectorPhase"] = sector_info["phase"]
        passed.append(s)

    # 通过者按总分排序
    passed.sort(key=lambda x: x["TotalScore"], reverse=True)
    # 被否决者也排序（方便查看）
    vetoed.sort(key=lambda x: x["TotalScore"], reverse=True)

    # 清理K线数据（减小输出文件）
    for s in passed + vetoed:
        for key in ("KClose", "KVolume", "KOpen", "KHigh", "KLow"):
            s.pop(key, None)

    # 将 sector_phases 转换为 JSON 可序列化格式
    sector_phase_map = {}
    for ind, info in sector_phases.items():
        sector_phase_map[ind] = {
            "phase": info["phase"],
            "avg_chg": info["avg_chg"],
            "avg_turn": info["avg_turn"],
            "count": info["count"],
            "momentum_score": info["momentum_score"],
            "money_bonus": info["money_bonus"],
            "news_bonus": info["news_bonus"],
            "sector_code": info.get("sector_code", "")
        }

    # 输出
    output = {
        "BuildTime": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Summary": {
            "Total": len(stocks),
            "Passed": len(passed),
            "Vetoed": len(vetoed),
            "PassRate": f"{len(passed)/len(stocks)*100:.1f}%"
        },
        "SectorPhaseMap": sector_phase_map,
        "VetoedStocks": [{
            "Code": s["Code"], "Name": s["Name"],
            "Industry": s.get("Industry", ""),
            "TotalScore": s["TotalScore"],
            "VetoStatus": s["VetoStatus"],
            "VetoReason": s["VetoReason"]
        } for s in vetoed],
        "Recommendations": [{
            "Code": s["Code"], "Name": s["Name"],
            "Industry": s.get("Industry", ""),
            "TotalScore": s["TotalScore"],
            "S_Base": s["S_Base"], "S_Fund": s["S_Fund"],
            "S_Tech": s["S_Tech"], "S_Money": s["S_Money"],
            "S_News": s["S_News"], "S_Risk": s["S_Risk"],
            "PoolSource": s.get("PoolSource", ""),
            "Price": s.get("Price", 0),
            "ChangePct": s.get("ChangePct", 0),
            "TurnoverRate": s.get("TurnoverRate", 0),
            "PE": s.get("PE", 0),
            # 技术指标（供报告生成使用）
            "MA5": s.get("MA5"), "MA10": s.get("MA10"), "MA20": s.get("MA20"),
            "RSI": s.get("RSI"), "MACD_Status": s.get("MACD_Status", ""),
            "VolRatio": s.get("VolRatio"),
            "TechAnalysis": s.get("TechAnalysis", ""),
            "SectorPhase": s.get("SectorPhase", "")
        } for s in passed[:25]],  # 限制推荐不超过25只
        "AllStocks": passed + vetoed
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8-sig") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"{'='*50}")
    print(f"否决结果:")
    print(f"  通过: {len(passed)} 只 ({output['Summary']['PassRate']})")
    print(f"  否决: {len(vetoed)} 只")

    if vetoed:
        print(f"\n否决明细:")
        for v in vetoed:
            print(f"  [{v['VetoStatus']}] {v['Code']} {v['Name']} — {v['VetoReason']} (总分:{v['TotalScore']})")

    print(f"\n推荐排序 (前10):")
    for i, r in enumerate(output["Recommendations"][:10], 1):
        src = "★" if r["PoolSource"] == "core_stock" else " "
        print(f"  {i:2d}. {src}{r['Code']} {r['Name']:6s} | 总分:{r['TotalScore']:2d} "
              f"| 技术:{r['S_Tech']:2d} 资金:{r['S_Money']:2d} "
              f"| PE:{r['PE']:.0f} 涨跌:{r['ChangePct']:+.2f}%")

    print(f"\n输出: {OUTPUT_FILE}")
    print("Done")


if __name__ == "__main__":
    main()
