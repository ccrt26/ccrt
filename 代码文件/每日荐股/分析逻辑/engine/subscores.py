#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""铁律量化 · 评分引擎 — 技术面子项评分"""
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

# ============ 技术面子项评分（从scoring_engine.py复用） ============
def _score_ma_system(ma5, ma10, ma20, price):
    if ma5 is None or ma10 is None or ma20 is None:
        return 3
    if ma5 > ma10 > ma20 and price > ma20: return 6
    if ma5 > ma10 > ma20: return 5
    if ma10 > 0 and ma20 > 0:
        spread = max(ma5, ma10, ma20) / min(ma5, ma10, ma20) - 1
        if spread < 0.01: return 4  # 均线收敛不一定是好事，降为4
    if ma10 > ma5 > ma20: return 3
    if ma10 <= ma20: return 1
    return 4

def _score_ma_converge(ma5, ma10, ma20, prev_ma5, prev_ma10, prev_ma20):
    if any(v is None for v in [ma5, ma10, ma20]): return 3
    if ma10 <= 0 or ma20 <= 0: return 3
    spread = max(ma5, ma10, ma20) / min(ma5, ma10, ma20) - 1
    if prev_ma5 and prev_ma10 and prev_ma20 and min(prev_ma5, prev_ma10, prev_ma20) > 0:
        prev_spread = max(prev_ma5, prev_ma10, prev_ma20) / min(prev_ma5, prev_ma10, prev_ma20) - 1
        if prev_spread < 0.02 and spread > prev_spread and ma5 > ma10: return 3
    if spread < 0.02: return 2
    if spread < 0.05: return 3
    if spread < 0.08: return 2
    return 0

def _score_volume_price(chg_pct, volume, vol_ma5, prices_5d, klines_5d):
    """量价蓄势形态 (5分) — 含突破确认"""
    if len(klines_5d) >= 5 and volume > 0 and vol_ma5 > 0:
        vol_ratio = volume / vol_ma5
        # 剧烈震荡洗盘后放量突破
        shake_days = 0
        for k in klines_5d[-5:]:
            amp = (k["High"] - k["Low"]) / k["PrevClose"] * 100 if k["PrevClose"] > 0 else 0
            if amp > 5:
                shake_days += 1
        has_shake = shake_days >= 2
        if has_shake and vol_ratio > 1.5 and chg_pct > 3:
            return 4  # 洗盘后突破
        # 横盘整理后放量突破
        if all(abs(k["ChgPct"]) < 3 for k in klines_5d[:-1]) and chg_pct > 3 and vol_ratio > 1.5:
            return 5

    # 放量上涨（无洗盘，普通放量）
    if chg_pct >= 3 and vol_ma5 > 0 and volume > vol_ma5 * 1.5:
        return 4
    # 温和上涨，量能正常
    if 0 < chg_pct < 2 and vol_ma5 > 0 and vol_ma5 * 0.8 <= volume <= vol_ma5 * 1.2:
        return 3
    # 连续小阳线
    if prices_5d:
        small_up = sum(1 for p in prices_5d if 0 < p < 2)
        if small_up >= 3: return 4
    # 放量下跌
    if chg_pct < 0 and vol_ma5 > 0 and volume > vol_ma5 * 1.5 and chg_pct < -3:
        return 0
    # 高位放量滞涨
    if chg_pct < 2 and vol_ma5 > 0 and volume > vol_ma5 * 1.8:
        return 1
    return 3

def _score_bottom_support(klines_10d, price, ma20):
    """底部/支撑形态 (4分) — 含突破确认"""
    lows_10d = [k["Low"] for k in klines_10d]
    highs_10d = [k["High"] for k in klines_10d]
    if len(klines_10d) >= 10:
        prev_high = max(highs_10d[:-1])
        if price > prev_high:
            shake = sum(1 for k in klines_10d[-10:-1] if k["PrevClose"] > 0 and (k["High"]-k["Low"])/k["PrevClose"]*100 > 5)
            if shake >= 3: return 4  # 洗盘后突破前高
    if len(lows_10d) >= 10:
        seg = len(lows_10d) // 2
        if min(lows_10d[seg:]) > min(lows_10d[:seg]): return 4  # 底部抬高
    # 双底形态
    if len(klines_10d) >= 10:
        first_min = min(lows_10d[:len(lows_10d)//2])
        second_min = min(lows_10d[len(lows_10d)//2:])
        if abs(first_min - second_min) / (first_min or 1) < 0.03:
            if price > max(k["Close"] for k in klines_10d[len(klines_10d)//2:]):
                return 4
    if ma20 and ma20 > 0:
        for k in klines_10d[-3:]:
            if abs(k["Low"] - ma20) / ma20 < 0.01: return 3  # 回踩MA20
    # 横盘整理
    if len(klines_10d) >= 10:
        prices_10d = [k["Close"] for k in klines_10d]
        pct_range = (max(prices_10d) - min(prices_10d)) / min(prices_10d) * 100
        if pct_range < 5: return 3
    return 2

def _score_rsi(rsi, chg_pct, vol_ratio, has_breakout=False):
    if rsi is None: return 2
    # 突破形态中超买不惩罚
    if rsi > 70 and has_breakout and vol_ratio > 1.5 and chg_pct > 3:
        return 2
    if 40 <= rsi <= 55: return 3
    if 30 <= rsi < 40: return 2
    if 55 < rsi <= 70: return 2
    if rsi < 30: return 1
    if rsi > 70:
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


def _score_trend_momentum(klines_5d, price, ma20, ma20_5d_ago=None):
    """趋势动量评分 (0-6分): 识别持续上涨趋势"""
    if not klines_5d or ma20 is None or ma20 <= 0:
        return 0
    score = 0
    # 最近5日涨幅 > 10%
    first_close = klines_5d[0]["Close"]
    last_close = klines_5d[-1]["Close"]
    if first_close > 0 and (last_close - first_close) / first_close * 100 > 10:
        score += 2
    # 最近5日涨幅 > 15% (额外加分，强趋势)
    if first_close > 0 and (last_close - first_close) / first_close * 100 > 15:
        score += 1
    # 价格在MA20上方超过8%
    if price > ma20 * 1.08:
        score += 1
    # 最近5日中至少3根阳线
    up_days = sum(1 for k in klines_5d if k["ChgPct"] > 0)
    if up_days >= 3:
        score += 1
    # MA20斜率向上 (当前MA20 > 5日前MA20)
    if ma20_5d_ago is not None and ma20 > ma20_5d_ago:
        score += 1
    return score