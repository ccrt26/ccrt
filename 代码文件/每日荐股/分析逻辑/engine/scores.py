#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""铁律量化 · 评分引擎 — 四维评分计算 + 相位折扣"""
import json, math, os, sys
from datetime import date, datetime, timedelta
from collections import Counter, defaultdict

from . import (
    ROOT, DATA_FILE, OUTPUT_FILE, THEME_WHITELIST_FILE, HISTORY_FILE,
    SPECIAL_STOCK_EXEMPTIONS, EASTMONEY_TO_BROAD_INDUSTRY, BROAD_TO_EASTMONEY,
    THEME_CLASSIFICATION, COMMODITY_TO_SECTOR, STABLE_VALUE_PE_RANGE,
    PE_ABSOLUTE_THRESHOLD, PE_COND_THRESHOLD,
    PE_COND_EXEMPT_SCORE, C3_EXEMPT_SCORE, C5_EXEMPT_SCORE, FIELD_SOURCE_MAP,
)

# 交叉导入:
from .theme import score_pe_by_theme
from .technical import calc_ma, calc_rsi, calc_macd, calc_atr, calc_adx, calc_bb, calc_obv
from .subscores import (_score_ma_system, _score_ma_converge, _score_volume_price,
    _score_bottom_support, _score_rsi, _score_macd,
    _score_breakout_confirmation, _score_trend_momentum)

def calc_percentile(values, target):
    """计算 target 在 values 序列中的百分位 (0-100)"""
    valid = [v for v in values if v > 0]
    if len(valid) < 5:
        return None
    count_below = sum(1 for v in valid if v < target)
    return round(count_below / len(valid) * 100, 1)


def classify_path_6features(s):
    """6特征路径分类：逃顶 > 追高 > 抄底 > 追空 > 追涨 > 杀跌 > 震荡"""
    ma5 = s.get("MA5", 0) or 0
    ma10 = s.get("MA10", 0) or 0
    ma20 = s.get("MA20", 0) or 0
    rsi = s.get("RSI", 50) or 50
    chg_pct = s.get("ChangePct", 0) or 0
    vol_ratio = s.get("VolRatio", 1) or 1
    macd = s.get("MACD_Status", "")
    price = s.get("Price", 0) or 0

    # MA排列
    ma_bullish = ma5 > ma10 > ma20 and price > ma20
    ma_bearish = ma5 < ma10 < ma20 and price < ma20

    # 逃顶：超买
    if rsi > 70:
        return "逃顶"
    # 追高：均线多头 + RSI中性偏强 + 放量上涨
    if ma_bullish and rsi >= 55 and vol_ratio > 1.2 and chg_pct > 0:
        return "追高"
    # 抄底：超卖
    if rsi < 35:
        return "抄底"
    # 追空：均线空头 + 放量下跌
    if ma_bearish and vol_ratio > 1.2 and chg_pct < 0:
        return "追空"
    # 追涨：放量上涨但不满足追高条件
    if vol_ratio > 1.5 and chg_pct > 3:
        return "追涨"
    # 杀跌：放量下跌但不满足追空条件
    if vol_ratio > 1.5 and chg_pct < -3:
        return "杀跌"
    return "震荡"


def _calc_ttm_pe(stock):
    """红线核心公式: PE(TTM) = Price[1] / TTM_EPS[3]
    返回 (pe_value, pe_source_label)
    """
    price = stock.get("Price", 0) or 0
    eps = stock.get("EPS", 0) or 0
    raw_pe = stock.get("PE", 0) or 0
    if price > 0 and eps > 0:
        return round(price / eps, 1), "[5]TTM自算(Price/EPS)"
    if raw_pe > 0:
        return raw_pe, "[3]东财PE(兜底,非TTM)"
    return 0, "不可得"


def compute_scores(s, sector_info=None, sector_trend_info=None):
    """计算六维评分, 返回 (scores_dict, tech_detail)"""
    closes = s.get("KClose", [])
    volumes = s.get("KVolume", [])
    price = s.get("Price", 0)
    chg_pct = s.get("ChangePct", 0)
    turnover = s.get("TurnoverRate", 0) or 0
    amplitude = s.get("Amplitude", 0) or 0
    pe, pe_source = _calc_ttm_pe(s)
    s["PE_Source"] = pe_source
    s["PE_TTM"] = pe
    mkt_cap = s.get("MktCap", 0)
    fund_net = s.get("FundMainNet", 0)
    # v2.8: 北向资金 + 融资融券
    nb_shares_ratio = s.get("NorthboundSharesRatio", 0) or 0
    nb_free_ratio = s.get("NorthboundFreeRatio", 0) or 0
    nb_hold_mktcap = s.get("NorthboundHoldMktCap", 0) or 0
    mg_rzye = s.get("MarginRZYE", 0) or 0
    mg_rzjme = s.get("MarginRZJME", 0) or 0
    mg_rzye_5d = s.get("MarginRZYE_5dChange", 0) or 0
    industry = s.get("Industry", "")

    min_closes = min(closes[-5:]) if len(closes) >= 5 else price
    max_closes = max(closes[-5:]) if len(closes) >= 5 else price

    # --- S_Base: 基础门槛 (10分) ---
    # 白皮书§(二十): 非ST/非亏损3分 + 市值评分4分 + 流动性3分
    # 非ST/非亏损: ST已在V0否决，通过否决的非ST股票自动得3分
    base_non_st = 3

    # 市值评分(4分): MktCap单位为万元
    # 100-1000亿(1000000-10000000万)得4分
    # 50-100亿(500000-1000000万)或1000-3000亿(10000000-30000000万)得2分
    # <50亿(<500000万)得1分
    # >3000亿(>30000000万)得0分
    if 1000000 <= mkt_cap <= 10000000:
        base_mkt = 4
    elif (500000 <= mkt_cap < 1000000) or (10000000 < mkt_cap <= 30000000):
        base_mkt = 2
    elif mkt_cap < 500000:
        base_mkt = 1
    else:
        base_mkt = 0

    # 流动性(3分): 日成交额(万元)=Volume(手)*Price/100
    # >1亿(10000万)得3分; >5000万得2分; >3000万得1分
    volume = s.get("Volume", 0)
    turnover_value = volume * price / 100 if price > 0 and volume > 0 else 0
    if turnover_value > 10000:
        base_liq = 3
    elif turnover_value > 5000:
        base_liq = 2
    elif turnover_value > 3000:
        base_liq = 1
    else:
        base_liq = 0

    base = base_non_st + base_mkt + base_liq

    # --- S_Fund: 基本面 (15分 v2.6三路径PE评分) ---
    # 白皮书 §二十一 v2.6重写: 根据题材分类走不同PE估值路径
    # 强成长→PEG+PS / 周期成长→PB+趋势 / 稳定价值→PE合理区间
    # 多标签取最宽松路径
    fund, theme_path, theme_details = score_pe_by_theme(s)
    s["_ThemePath"] = theme_path
    s["_ThemeDetails"] = theme_details
    div_yield = s.get("DividendYield", 0) or 0
    if div_yield > 3:
        fund = min(15, fund + 2)
    elif div_yield > 1.5:
        fund = min(15, fund + 1)

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

        # 突破形态判定
        has_breakout = False
        if len(klines_10d) >= 10:
            shake = sum(1 for k in klines_10d if k["PrevClose"] > 0 and (k["High"]-k["Low"])/k["PrevClose"]*100 > 5)
            if shake >= 3 and chg_pct > 3 and vol_ratio > 1.5:
                has_breakout = True

        # 子项评分
        s1 = _score_ma_system(ma5, ma10, ma20, price)
        s2 = _score_ma_converge(ma5, ma10, ma20, prev_ma5, prev_ma10, prev_ma20)
        s3 = _score_volume_price(chg_pct, vol_latest, vol_ma5, prices_5d, klines_5d)
        s4 = _score_bottom_support(klines_10d, price, ma20)
        s5 = _score_rsi(rsi, chg_pct, vol_ratio, has_breakout)
        s6 = _score_macd(dif, dea, prev_dif, prev_dea)
        s7 = _score_breakout_confirmation(klines_10d, chg_pct, vol_latest, vol_ma5, price)
        ma20_5d_ago = ma20_arr[i-5] if i-5 >= 0 and ma20_arr[i-5] is not None else None
        s8 = _score_trend_momentum(klines_5d, price, ma20, ma20_5d_ago)

        raw_tech = s1 + s2 + s3 + s4 + s5 + s6 + s7 + s8
        tech = round(raw_tech / 27 * 20)  # v2.8 归一化至20分
        tech = max(1, min(20, tech))

        # v2.8 相位风险折扣: 潜伏期不打折，主升/高潮/衰退逐级打折
        phase_penalty_map = {"潜伏期": 1.0, "主升调整": 0.75, "高潮期": 0.55, "衰退期": 0.45}
        stock_phase = sector_info.get("phase", "潜伏期") if sector_info else "潜伏期"
        phase_mult = phase_penalty_map.get(stock_phase, 1.0)
        s["PhaseMultiplier"] = phase_mult
        tech = max(1, round(tech * phase_mult))
        tech_detail = f"{s1}+{s2}+{s3}+{s4}+{s5}+{s6}+{s7}+{s8}={raw_tech}→{tech}"
        tech_details = {
            "S1_MA_System": s1, "S2_MA_Converge": s2,
            "S3_Volume_Price": s3, "S4_Support": s4,
            "S5_RSI": s5, "S6_MACD": s6,
            "S7_Breakout": s7, "S8_Trend_Momentum": s8,
            "raw_tech": raw_tech, "tech_normalized": tech
        }

        # ---- 存储技术指标用于报告分析 ----
        s["MA5"] = round(ma5, 2)
        s["MA10"] = round(ma10, 2)
        s["MA20"] = round(ma20, 2)
        s["RSI"] = round(rsi, 1)
        s["VolRatio"] = round(vol_ratio, 2)

        # ATR14 calculation (流金 v2026-05-24)
        highs = s.get("KHigh", [])
        lows = s.get("KLow", [])
        if highs and lows and closes and len(highs) >= 15 and len(lows) >= 15 and len(closes) >= 15:
            atr_arr = calc_atr(highs, lows, closes, 14)
            s["ATR14"] = atr_arr[-1] if atr_arr[-1] is not None else 0
        else:
            s["ATR14"] = 0
        if highs and lows and closes and len(highs) >= 28 and len(lows) >= 28 and len(closes) >= 28:
            adx_arr = calc_adx(highs, lows, closes, 14)
            s["ADX14"] = round(adx_arr[-1], 1) if adx_arr[-1] is not None else None
        else:
            s["ADX14"] = None
        if closes:
            bb_upper, bb_mid, bb_lower = calc_bb(closes, 20, 2)
            s["BB_Upper"] = bb_upper[-1] if bb_upper[-1] is not None else None
            s["BB_Mid"] = bb_mid[-1] if bb_mid[-1] is not None else None
            s["BB_Lower"] = bb_lower[-1] if bb_lower[-1] is not None else None
        else:
            s["BB_Upper"] = s["BB_Mid"] = s["BB_Lower"] = None
        if closes and volumes:
            obv_arr = calc_obv(closes, volumes)
            s["OBV"] = obv_arr[-1] if obv_arr else None
        else:
            s["OBV"] = None
        s["VolumePercentile"] = calc_percentile(volumes, vol_latest)

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
        s["PathTag"] = classify_path_6features(s)
    else:
        tech = 10
        tech_detail = "数据不足"
        tech_details = {}
        phase_mult = 1.0
        s["VolumePercentile"] = None
        s["PathTag"] = "震荡"

    # --- S_Money: 资金面 (20分) + 板块动量加分 ---
    money = 10
    if turnover < 1: money -= 2  # 冷清（白皮书§(二十三)）
    elif 2 <= turnover <= 5: money += 4  # 活跃区间
    elif 5 < turnover <= 8: money += 2
    elif turnover > 8: money -= 2  # 过热
    if 3 <= amplitude <= 7: money += 3
    elif amplitude > 10: money -= 2
    if fund_net > 0: money += 2
    elif fund_net < -10000000: money -= 2
    # P0a: 连续N日主力趋势 (2026-05-26)
    fund_net_3d = s.get("FundMainNet_3d", 0) or 0
    fund_net_5d = s.get("FundMainNet_5d", 0) or 0
    fund_days_pos = s.get("FundMainNet_PosDays", 0) or 0
    if fund_days_pos >= 5 and fund_net_5d > 0:
        money += 4
    elif fund_days_pos >= 3 and fund_net_3d > 0:
        money += 2
    elif fund_days_pos <= 1 and fund_net_5d < 0:
        money -= 2
    # v2.8: 北向资金 [8] — 外资持仓信号
    if nb_shares_ratio > 5: money += 3      # 外资重仓(>5%)
    elif nb_shares_ratio > 2: money += 2     # 外资关注(>2%)
    elif nb_shares_ratio > 0.5: money += 1   # 外资轻仓(>0.5%)
    # v2.8: 融资融券 [12] — 杠杆资金信号
    if mg_rzjme > 0: money += 1              # 当日融资净买入
    if mg_rzye_5d > 0: money += 1            # 融资余额5日趋势向上
    # 板块动量加分：热门板块资金关注度高
    sector_bonus = 0
    if sector_info:
        money += sector_info["money_bonus"]
        sector_bonus = sector_info["money_bonus"]
    money = max(1, min(20, money))
    # v2.9: 资金面同样受板块相位折扣（涨停股换手率/资金流虚高 → 去水分）
    money = max(1, round(money * phase_mult))

    # --- S_News: 消息面/CAR5 (15分 v2.8修复) ---
    # v2.8: CAR5 = 个股近5日累计涨幅 - 全市场中位数5日涨幅（代理沪深300）
    # 对齐白皮书 §二十四，替代v2.7的当日涨跌幅
    news = 10
    if len(closes) >= 5 and closes[-5] > 0:
        stock_5d = (closes[-1] - closes[-5]) / closes[-5] * 100
        market_5d = s.get("_Market5DMedian", 0)
        car5 = stock_5d - market_5d
        if car5 > 5: news += 6
        elif car5 > 2: news += 4
        elif car5 > -2: news += 2
        elif car5 > -5: news += 1
        else: news += 0
    if sector_info:
        news += sector_info["news_bonus"]
    news = max(1, min(15, news))  # v2.4 消息面降权至15分
    # v2.9: 消息面同样受板块相位折扣（CAR5包含当日暴涨 → 去水分）
    news = max(1, round(news * phase_mult))

    # --- S_Risk: 风控 (5分) ---
    risk = 3
    if pe > 0 and pe < 60: risk += 1
    if 1 <= turnover <= 8: risk += 1
    risk = max(1, min(5, risk))

    # --- S_SectorTrend: 板块趋势持续性 (20分 v2.8升权) ---
    sector_trend_score = 0
    if sector_trend_info:
        raw_trend = sector_trend_info.get("trend_score", 0)
        sector_trend_score = max(0, min(20, raw_trend * 2))  # v2.8: 五因子0-10分→升权至0-20分

    total = base + fund + tech + money + news + risk + sector_trend_score
    total = max(0, min(100, total))

    # 提取估值指标
    theme_d = s.get("_ThemeDetails", {})
    peg = None; pb = None; ps = None; eps_growth = None; growth_source = None
    for t_path, t_score, t_details in theme_d.get("all_paths", []):
        if t_path == s.get("_ThemePath", ""):
            peg = t_details.get("PEG")
            pb = t_details.get("PB")
            ps = t_details.get("PS")
            eps_growth = t_details.get("growth")
            growth_source = t_details.get("growth_source")
            break

    car5 = None
    if len(closes) >= 5 and closes[-5] > 0:
        stock_5d = (closes[-1] - closes[-5]) / closes[-5] * 100
        market_5d = s.get("_Market5DMedian", 0)
        car5 = round(stock_5d - market_5d, 2)

    # P1a: 行业锚定参照 (2026-05-26)
    from . import INDUSTRY_BENCHMARK
    s["IndustryBenchmark"] = INDUSTRY_BENCHMARK.get(industry, 5.0)

    return {
        "S_Base": base, "S_Fund": fund, "S_Tech": tech,
        "S_Money": money, "S_News": news, "S_Risk": risk,
        "S_SectorTrend": sector_trend_score,
        "S_Tech_Details": tech_details,
        "TotalScore": total,
        "PE_Source": pe_source, "PE_TTM": pe,
        "PEG": peg, "PB": pb, "PS": ps,
        "CAR5": car5,
        "EPS_Growth": eps_growth, "GrowthSource": growth_source,
        "ThemePath": s.get("_ThemePath", ""),
    }, tech_detail


# ============ P0b 突破性质分类 (2026-05-26) [L2] ============
# 变更须经 流金 复核

def detect_breakthrough(s):
    """检测是否发生放量突破关键位。
    返回 (is_breakthrough, strength: 0|1|2)
    strength: 2=52周新高突破, 1=MA20以上放量突破, 0=无突破
    """
    chg_pct = s.get("ChangePct", 0) or 0
    vol_ratio = s.get("VolRatio", 1) or 1
    price = s.get("Price", 0) or 0
    closes = s.get("KClose", [])

    # 条件1: 量价确认 — 放量上涨
    volume_surge = vol_ratio > 1.5 and chg_pct > 3

    if not volume_surge:
        return False, 0

    # 条件2: 突破关键位
    # 2a: 52周新高 (最强信号)
    if len(closes) >= 250:
        recent_high = max(closes[-250:])
        if price >= recent_high:
            return True, 2

    # 2b: MA20以上+涨幅>5%
    ma20 = s.get("MA20", 0) or 0
    if ma20 > 0 and price > ma20 * 1.03 and chg_pct > 5:
        return True, 1

    # 2c: 10日横盘后突破 (S3_Volume_Price判定)
    td = s.get("S_Tech_Details", {})
    if td.get("S3_Volume_Price", 0) >= 4 and td.get("S7_Breakout", 0) >= 3:
        return True, 1

    return False, 0


def classify_breakthrough_nature(s, scores):
    """突破性质四分类，返回类型字符串或 None。
    - "quality_momentum": 质量+动量共振 (最优)
    - "fund_driven": 资金驱动 (基本面弱但有资金)
    - "pure_momentum": 纯动量 (无基本面+无资金确认)
    - None: 无有效突破
    """
    is_bt, strength = detect_breakthrough(s)
    if not is_bt:
        return None

    fund_quality = scores.get("S_Fund", 0)  # 0-15
    fund_net = s.get("FundMainNet", 0) or 0
    fund_net_3d = s.get("FundMainNet_3d", 0) or 0

    fund_positive = fund_net > 0 and fund_net_3d > 0
    quality_pass = fund_quality >= 8  # 基本面过半

    if quality_pass and fund_positive:
        return "quality_momentum"
    elif not quality_pass and fund_positive:
        return "fund_driven"
    else:
        return "pure_momentum"


# ============ 技术面子项评分（从scoring_engine.py复用） ============