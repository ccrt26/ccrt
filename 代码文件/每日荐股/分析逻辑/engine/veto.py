#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""铁律量化 · 评分引擎 — 否决体系 + 市场状态检测 [L2]"""
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

# L2 风控模块 — 每条规则引用红线条款编号，变更须经 流金 复核
# 交叉导入:
from .theme import classify_theme, check_theme_purity, load_industry_whitelist
from .technical import calc_ma
from .sector import should_exempt_by_sector

def _get_v5_threshold(market_turnover_yi=None):
    """
    V5流动性动态阈值 (白皮书 §十五 v2.7)

    根据全市场近5日均成交额三档设定：
      > 1万亿  → 2000万 (流动性充裕，提高门槛)
      5000亿-1万亿 → 1500万 (正常，维持原阈值)
      < 5000亿 → 1000万 (流动性紧张，放宽)

    Args:
      market_turnover_yi: 全市场近5日均成交额(亿元)。None时返回默认1500万。
    Returns: (threshold_wan, tier_label)
    """
    if market_turnover_yi is None or market_turnover_yi <= 0:
        return 1500, "默认(无市场数据)"
    if market_turnover_yi > 10000:
        return 2000, f"充裕(均额{market_turnover_yi:.0f}亿>1万亿)"
    elif market_turnover_yi >= 5000:
        return 1500, f"正常(均额{market_turnover_yi:.0f}亿)"
    else:
        return 1000, f"紧张(均额{market_turnover_yi:.0f}亿<5000亿)"


def check_absolute_vetoes(s, v5_dynamic_threshold=None):
    """8条绝对否决, 返回 (否决id, 原因) 或 None"""
    closes = s.get("KClose", [])
    price = s.get("Price", 0)
    pe = s.get("PE", 0)
    industry = s.get("Industry", "")
    eps = s.get("EPS", None)
    mkt_cap = s.get("MktCap", 0)
    change_pct = s.get("ChangePct", 0)
    code = s.get("Code", "")
    exemption = SPECIAL_STOCK_EXEMPTIONS.get(code, {})

    # V1: 已降级为条件否决(C5)，移至 check_conditional_vetoes

    # V0: ST股票直接否决
    name = s.get("Name", "")
    if "ST" in name or "st" in name.lower():
        return ("vetoed_abs_st", f"ST股票: {name} 带帽风险股，不纳入推荐")

    # V2: PE相对估值超标（检查特殊豁免）
    if pe > 0 and not exemption.get("exempt_abs_pe"):
        threshold = exemption.get("abs_pe_threshold", PE_ABSOLUTE_THRESHOLD.get(industry, 80))
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
        if pe <= 0 and not exemption.get("exempt_abs_eps"):
            return ("vetoed_abs_4", "财务数据异常: EPS≤0且PE无法计算")

    # V5: 流动性枯竭（v2.7: 动态阈值）
    volume = s.get("Volume", 0)
    turnover_rate = s.get("TurnoverRate", 0) or 0
    if price > 0:
        turnover_value = volume * price / 100  # 万元（Volume单位为手，*100=股）
        v5_threshold = v5_dynamic_threshold if v5_dynamic_threshold else 1500
        if turnover_value < v5_threshold and turnover_rate < 0.5:
            return ("vetoed_abs_5", f"流动性枯竭: 成交额{turnover_value:.0f}万 < {v5_threshold}万")

    # V6: 高负债率 (需要财务数据，暂用EPS缺失作为代理)
    # V7: 连续2季亏损 (需要财报数据)
    # 这两条需要完整的财务数据，在当前数据源中难以获取，暂跳过

    return None  # 通过绝对否决


# ============ v2.7 市场环境自适应否决 D.1 ============
def detect_market_state(stocks):
    """
    市场环境三态检测 (白皮书 §附录D.1 v2.7落地)

    计算全市场等权近5日涨幅中位数：
      强势市场: median_5d > 2%   → PE阈值×1.2, 豁免分-10
      弱势市场: median_5d < -2%  → PE阈值×0.9, 豁免分+10
      震荡市场: -2% ≤ median_5d ≤ 2% → 不变

    Returns: (state, pe_multiplier, exemption_delta)
    """
    five_day_returns = []
    for s in stocks:
        closes = s.get("KClose", [])
        if len(closes) >= 5:
            close_5d_ago = closes[-5]
            current = closes[-1] if closes[-1] > 0 else s.get("Price", 0)
            if close_5d_ago > 0 and current > 0:
                ret_5d = (current - close_5d_ago) / close_5d_ago * 100
                five_day_returns.append(ret_5d)

    if len(five_day_returns) < 20:
        return "震荡", 1.0, 0  # 数据不足，保持默认

    five_day_returns.sort()
    n = len(five_day_returns)
    median_5d = five_day_returns[n // 2] if n % 2 == 1 else (five_day_returns[n // 2 - 1] + five_day_returns[n // 2]) / 2

    if median_5d > 2:
        return "强势", 1.2, -10
    elif median_5d < -2:
        return "弱势", 0.9, 10
    else:
        return "震荡", 1.0, 0

def check_conditional_vetoes(s, scores, sector_phases=None, sector_trends=None, market_state="震荡"):
    """7条条件否决 (v2.7: +D.1市场自适应), 返回 (否决id, 原因) 或 None"""
    closes = s.get("KClose", [])
    price = s.get("Price", 0)
    pe = s.get("PE", 0)
    total = scores["TotalScore"]
    industry = s.get("Industry", "")
    code = s.get("Code", "")
    exemption = SPECIAL_STOCK_EXEMPTIONS.get(code, {})

    # v2.7 D.1: 市场环境自适应 — 强势放宽/弱势收紧/震荡不变
    if market_state == "强势":
        pe_mult = 1.2    # PE阈值放宽20%
        exempt_delta = -10  # 豁免分降10分
    elif market_state == "弱势":
        pe_mult = 0.9    # PE阈值收紧10%
        exempt_delta = 10   # 豁免分升10分
    else:  # 震荡
        pe_mult = 1.0
        exempt_delta = 0

    # 自适应豁免分（不低于50，不高于90）
    adaptive_exempt = max(50, min(90, PE_COND_EXEMPT_SCORE + exempt_delta))
    adaptive_c3 = max(55, min(80, C3_EXEMPT_SCORE + exempt_delta))
    adaptive_c5 = max(60, min(85, C5_EXEMPT_SCORE + exempt_delta))

    # v2.4: 板块动量双层判断 — 主线板块全面豁免否决
    sector_exempt = should_exempt_by_sector(industry, sector_phases or {}, sector_trends or {})

    # v2.6 C7: 题材纯度检查 — 强成长标签需通过纯度验证才能豁免PE否决
    # 纯度≥2/3 → 真正强成长，PE豁免；纯度<2 → 题材存疑，PE否决正常执行
    theme_pure_exempt = False
    themes = classify_theme(s, load_industry_whitelist())
    if "强成长" in themes:
        purity_score, purity_details = check_theme_purity(s, load_industry_whitelist())
        s["_C7_Purity"] = purity_score
        s["_C7_PurityDetails"] = purity_details
        if purity_score >= 2:
            theme_pure_exempt = True  # C7通过 → PE豁免
    else:
        # 非强成长题材不适用C7，正常走PE否决
        s["_C7_Purity"] = -1  # -1 = 不适用
        s["_C7_PurityDetails"] = {}

    # C1: PE偏高(科技制造>120) — v2.7 D.1自适应PE阈值+豁免分
    cond_pe_threshold = exemption.get("cond_pe_threshold", 120) * pe_mult
    if not exemption.get("exempt_cond_pe"):
        if pe > cond_pe_threshold and industry in ("电子", "计算机", "通信", "汽车", "电力设备", "机械设备"):
            if total < adaptive_exempt:
                if sector_exempt == True or theme_pure_exempt:
                    pass
                elif sector_exempt == "partial_c3_only":
                    pass
                elif sector_exempt == "partial":
                    partial_exempt = max(60, adaptive_exempt - 15)
                    if total >= partial_exempt:
                        pass
                    else:
                        return ("vetoed_cond_1", f"科技PE过高: {pe:.0f} > {cond_pe_threshold:.0f} (短期脉冲豁免需总分≥{partial_exempt})")
                else:
                    return ("vetoed_cond_1", f"科技PE过高: {pe:.0f} > {cond_pe_threshold:.0f} (豁免需总分≥{adaptive_exempt})")

    # C2: PE偏高(高成长>80) — v2.7 D.1自适应PE阈值+豁免分
    c2_threshold = exemption.get("cond_pe_threshold", PE_COND_THRESHOLD) * pe_mult
    if not exemption.get("exempt_cond_pe"):
        if pe > c2_threshold:
            if total < adaptive_exempt:
                if sector_exempt == True or theme_pure_exempt:
                    pass
                elif sector_exempt == "partial_c3_only":
                    pass
                elif sector_exempt == "partial":
                    partial_exempt = max(60, adaptive_exempt - 15)
                    if total >= partial_exempt:
                        pass
                    else:
                        return ("vetoed_cond_2", f"PE过高: {pe:.0f} > {c2_threshold:.0f} (短期脉冲豁免需总分≥{partial_exempt})")
                else:
                    return ("vetoed_cond_2", f"PE过高: {pe:.0f} > {c2_threshold:.0f} (豁免需总分≥{adaptive_exempt})")

    # C3: MA5 < MA10*0.99 (短期均线回踩) — v2.7 D.1自适应豁免分
    if len(closes) >= 10:
        ma5 = calc_ma(closes, 5)[-1]
        ma10 = calc_ma(closes, 10)[-1]
        if ma5 is not None and ma10 is not None and ma5 < ma10 * 0.95:
            if total < adaptive_c3:
                if sector_exempt == True or sector_exempt == "partial" or sector_exempt == "partial_c3_only":
                    pass
                else:
                    return ("vetoed_cond_3", f"短期均线回踩: MA5({ma5:.2f}) < MA10({ma10:.2f})×0.95 (豁免需总分≥{adaptive_c3})")

    # C4: 30日涨幅过高 (市场自适应)
    if len(closes) >= 30 and closes[-30] > 0:
        gain_30d = (price - closes[-30]) / closes[-30] * 100
        if gain_30d > 50:
            return ("vetoed_cond_4", f"30日涨幅{gain_30d:.0f}% > 50%")

    # C5: MA10 ≤ MA20 (原绝对否决V1降级，允许高分豁免)
    if len(closes) >= 20 and not exemption.get("exempt_ma_death"):
        ma10 = calc_ma(closes, 10)[-1]
        ma20 = calc_ma(closes, 20)[-1]
        if ma10 is not None and ma20 is not None and ma10 <= ma20:
            if total < adaptive_c5:
                ma5 = calc_ma(closes, 5)[-1]
                detail = f"MA10({ma10:.2f})≤MA20({ma20:.2f})"
                if ma5 is not None and ma5 > ma10:
                    pass
                elif price > ma20 * 1.03:
                    pass
                elif sector_exempt == True or sector_exempt == "partial":
                    pass
                else:
                    return ("vetoed_cond_5", f"均线死叉: {detail} (v2.7 D.1 豁免需总分≥{adaptive_c5})")

    # C6: PE估值泡沫板块调整 (v2.4新增) — 仅板块处于衰退期时触发
    # 豁免条件：板块为长期主线（is_long_term_main_line）
    pe_abs_threshold = exemption.get("abs_pe_threshold", PE_ABSOLUTE_THRESHOLD.get(industry, 80))
    if pe > pe_abs_threshold and pe > 0:
        phase_info = (sector_phases or {}).get(industry, {})
        trend_info = (sector_trends or {}).get(industry, {})
        if phase_info.get("phase") == "衰退期":
            # 板块为长期主线时豁免C6
            if trend_info.get("is_long_term_main_line", False):
                pass  # 长期主线板块，衰退期可能是短暂调整，豁免
            else:
                return ("vetoed_cond_6", f"PE估值泡沫(板块衰退): PE={pe:.0f} > {pe_abs_threshold}({industry}) 且板块处于衰退期")

    return None