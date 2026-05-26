#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""铁律量化 · 评分引擎 — 技术指标计算 (MA/RSI/MACD/ATR/EMA/周月线聚合)"""
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

# ============ K线聚合缓存目录 ============
KLINE_CACHE_DIR = os.path.join(ROOT, '代码文件', '每日荐股', 'scripts', 'data_cache')

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

def calc_atr(highs, lows, closes, period=14):
    """计算 ATR(14) (流金 v2026-05-24)"""
    result = []
    trs = []
    for i in range(len(closes)):
        if i == 0:
            tr = highs[i] - lows[i]
        else:
            tr = max(highs[i] - lows[i],
                     abs(highs[i] - closes[i-1]),
                     abs(lows[i] - closes[i-1]))
        trs.append(tr)
    for i in range(len(trs)):
        if i < period:
            result.append(None)
        elif i == period:
            result.append(round(sum(trs[:period]) / period, 2))
        else:
            atr_prev = result[-1]
            result.append(round((atr_prev * (period - 1) + trs[i]) / period, 2))
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

def calc_adx(highs, lows, closes, period=14):
    """ADX — Wilder's smoothing (重点v3.0)"""
    n = len(closes)
    if n < period * 2:
        return [None] * n
    tr = [0.0] * n
    plus_dm = [0.0] * n
    minus_dm = [0.0] * n
    for i in range(1, n):
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
        up = highs[i] - highs[i-1]
        down = lows[i-1] - lows[i]
        plus_dm[i] = up if up > down and up > 0 else 0.0
        minus_dm[i] = down if down > up and down > 0 else 0.0
    atr_s = [0.0] * n
    pdm_s = [0.0] * n
    mdm_s = [0.0] * n
    atr_s[period] = sum(tr[1:period+1])
    pdm_s[period] = sum(plus_dm[1:period+1])
    mdm_s[period] = sum(minus_dm[1:period+1])
    for i in range(period + 1, n):
        atr_s[i] = atr_s[i-1] - atr_s[i-1]/period + tr[i]
        pdm_s[i] = pdm_s[i-1] - pdm_s[i-1]/period + plus_dm[i]
        mdm_s[i] = mdm_s[i-1] - mdm_s[i-1]/period + minus_dm[i]
    adx = [None] * n
    for i in range(period, n):
        atr_v = atr_s[i]
        pdi = (pdm_s[i] / atr_v * 100) if atr_v > 0 else 0
        mdi = (mdm_s[i] / atr_v * 100) if atr_v > 0 else 0
        denom = pdi + mdi
        dx = abs(pdi - mdi) / denom * 100 if denom > 0 else 0
        if i == period * 2 - 1:
            s = 0.0
            for j in range(period, i + 1):
                av = atr_s[j]; pj = pdm_s[j] / av * 100 if av > 0 else 0
                mj = mdm_s[j] / av * 100 if av > 0 else 0
                dn = pj + mj
                s += abs(pj - mj) / dn * 100 if dn > 0 else 0
            adx[i] = round(s / period, 2)
        elif i > period * 2 - 1:
            adx[i] = round((adx[i-1] * (period - 1) + dx) / period, 2)
    return adx

def calc_bb(closes, period=20, std_mult=2):
    """Bollinger Bands (重点v3.0)"""
    n = len(closes)
    if n < period:
        return ([None]*n, [None]*n, [None]*n)
    ma = calc_ma(closes, period)
    upper, lower = [None]*n, [None]*n
    for i in range(period-1, n):
        window = closes[i-period+1:i+1]
        mean = sum(window) / period
        var = sum((x - mean)**2 for x in window) / period
        std = var ** 0.5
        upper[i] = round(mean + std_mult * std, 2)
        lower[i] = round(mean - std_mult * std, 2)
    return upper, ma, lower

def calc_obv(closes, volumes):
    """OBV — 能量潮 (重点v3.0)"""
    n = len(closes)
    obv = [0.0] * n
    obv[0] = float(volumes[0]) if volumes[0] else 0
    for i in range(1, n):
        if closes[i] > closes[i-1]:
            obv[i] = obv[i-1] + (volumes[i] or 0)
        elif closes[i] < closes[i-1]:
            obv[i] = obv[i-1] - (volumes[i] or 0)
        else:
            obv[i] = obv[i-1]
    return obv


# ============ K线周期聚合 (周线/月线) — v2026-05-24 ============

def _iso_week_key(date_str):
    """从 'YYYY-MM-DD' 提取 ISO 年-周 键, e.g. '2026-W21'"""
    try:
        y, m, d = date_str.split("-")
        dt = date(int(y), int(m), int(d))
        iso = dt.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    except Exception:
        return None

def _month_key(date_str):
    """从 'YYYY-MM-DD' 提取 年-月 键, e.g. '2026-05'"""
    try:
        return date_str[:7]
    except Exception:
        return None

def aggregate_kline(dates, opens, highs, lows, closes, volumes, freq="W"):
    """日线K线聚合为周线(W)或月线(M)

    Args:
        dates:   [str] 日期列表 "YYYY-MM-DD", 升序(旧→新)
        opens/highs/lows/closes/volumes: [float/int] 与dates等长
        freq:    "W"(周线) 或 "M"(月线)

    Returns:
        dict with keys: dates, opens, highs, lows, closes, volumes
        每个数组按升序排列。输入不足1根周/月K线时返回空dict。
    """
    n = len(dates)
    if n == 0:
        return {}

    key_fn = _iso_week_key if freq == "W" else _month_key
    groups = defaultdict(list)

    for i in range(n):
        k = key_fn(dates[i])
        if k:
            groups[k].append(i)

    if not groups:
        return {}

    result = {"dates": [], "opens": [], "highs": [], "lows": [], "closes": [], "volumes": []}
    for gk in sorted(groups.keys()):
        idx = groups[gk]
        result["dates"].append(dates[idx[-1]])        # 期末日期
        result["opens"].append(opens[idx[0]])         # 期初开盘
        result["highs"].append(max(highs[i] for i in idx))
        result["lows"].append(min(lows[i] for i in idx))
        result["closes"].append(closes[idx[-1]])      # 期末收盘
        result["volumes"].append(sum(volumes[i] for i in idx))

    return result


def get_weekly_kline_cache(code, dates, opens, highs, lows, closes, volumes):
    """获取周线K线（带缓存），返回 aggregate_kline 同格式dict"""
    cache_key = f"WKLine_{code}"
    cache_path = os.path.join(KLINE_CACHE_DIR, f"{cache_key}.json")

    # 尝试读取缓存
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            cache_date = cached.get("_last_daily_date", "")
            if dates and cache_date == dates[-1]:
                return {k: v for k, v in cached.items() if not k.startswith("_")}
        except Exception:
            pass

    # 聚合 + 写缓存
    result = aggregate_kline(dates, opens, highs, lows, closes, volumes, "W")
    if result and result["dates"]:
        cached = {"_last_daily_date": dates[-1] if dates else "", "_schema_version": "1.0"}
        cached.update(result)
        try:
            os.makedirs(KLINE_CACHE_DIR, exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(cached, f, ensure_ascii=False)
        except Exception:
            pass

    return result


def get_monthly_kline_cache(code, dates, opens, highs, lows, closes, volumes):
    """获取月线K线（带缓存），返回 aggregate_kline 同格式dict"""
    cache_key = f"MKLine_{code}"
    cache_path = os.path.join(KLINE_CACHE_DIR, f"{cache_key}.json")

    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            cache_date = cached.get("_last_daily_date", "")
            if dates and cache_date == dates[-1]:
                return {k: v for k, v in cached.items() if not k.startswith("_")}
        except Exception:
            pass

    result = aggregate_kline(dates, opens, highs, lows, closes, volumes, "M")
    if result and result["dates"]:
        cached = {"_last_daily_date": dates[-1] if dates else "", "_schema_version": "1.0"}
        cached.update(result)
        try:
            os.makedirs(KLINE_CACHE_DIR, exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(cached, f, ensure_ascii=False)
        except Exception:
            pass

    return result

def calc_volume_profile(highs, lows, closes, volumes, num_bins=50, lookback=None):
    """成交量分布图 (Volume Profile) — 基于OHLCV数据计算价格区间成交量分布

    Args:
        highs, lows, closes, volumes: 并行OHLCV数组 (同索引)
        num_bins: 价格区间分档数 (默认50)
        lookback: 回看K线数 (None=全部, 建议60-120)

    Returns:
        { POC, VAH, VAL, HVN_Above, HVN_Below, LVN_Zones,
          bin_centers, bin_volumes, price, price_range, total_volume }
        数据不足时返回空dict
    """
    n = min(len(highs), len(lows), len(closes), len(volumes))
    if lookback is not None:
        n = min(n, lookback)
    if n < 10:
        return {}

    h = highs[-n:]
    l = lows[-n:]
    c = closes[-n:]
    v = volumes[-n:]

    price = c[-1] if c else 0
    price_min = min(l)
    price_max = max(h)
    if price_max <= price_min:
        price_max = price_min + 0.01

    bin_width = (price_max - price_min) / num_bins
    bin_volumes = [0.0] * num_bins
    bin_centers = [round(price_min + bin_width * (i + 0.5), 2) for i in range(num_bins)]

    total_volume = 0.0
    for i in range(n):
        bar_high = h[i]
        bar_low = l[i]
        bar_vol = float(v[i]) if v[i] else 0.0
        if bar_vol <= 0 or bar_high <= bar_low:
            continue
        total_volume += bar_vol
        span = bar_high - bar_low
        for j in range(num_bins):
            bin_low = price_min + bin_width * j
            bin_high = bin_low + bin_width
            overlap_low = max(bar_low, bin_low)
            overlap_high = min(bar_high, bin_high)
            if overlap_high > overlap_low:
                fraction = (overlap_high - overlap_low) / span
                bin_volumes[j] += bar_vol * fraction

    if total_volume <= 0:
        return {}

    max_vol = max(bin_volumes)
    poc_idx = bin_volumes.index(max_vol)
    poc = bin_centers[poc_idx]

    sorted_by_vol = sorted(enumerate(bin_volumes), key=lambda x: x[1], reverse=True)
    va_cum = 0.0
    va_indices = set()
    for idx, bv in sorted_by_vol:
        va_cum += bv
        va_indices.add(idx)
        if va_cum >= total_volume * 0.70:
            break
    va_list = sorted(va_indices)
    val = bin_centers[va_list[0]] if va_list else poc
    vah = bin_centers[va_list[-1]] if va_list else poc

    avg_vol = total_volume / num_bins
    hvn_above = []
    hvn_below = []
    lvn_zones = []
    lvn_start = None

    for i, bv in enumerate(bin_volumes):
        center = bin_centers[i]
        if bv > avg_vol * 1.5:
            if center > price:
                hvn_above.append((center, round(bv, 0)))
            else:
                hvn_below.append((center, round(bv, 0)))
        if bv < avg_vol * 0.5:
            if lvn_start is None:
                lvn_start = price_min + bin_width * i
        else:
            if lvn_start is not None:
                lvn_end = price_min + bin_width * i
                if lvn_end - lvn_start >= bin_width * 1.5:
                    lvn_zones.append((round(lvn_start, 2), round(lvn_end, 2)))
                lvn_start = None

    if lvn_start is not None:
        lvn_end = price_max
        if lvn_end - lvn_start >= bin_width * 1.5:
            lvn_zones.append((round(lvn_start, 2), round(lvn_end, 2)))

    hvn_above.sort(key=lambda x: x[0])
    hvn_below.sort(key=lambda x: x[0], reverse=True)

    return {
        "POC": round(poc, 2),
        "VAH": round(vah, 2),
        "VAL": round(val, 2),
        "HVN_Above": hvn_above[:3],
        "HVN_Below": hvn_below[:3],
        "LVN_Zones": lvn_zones[:3],
        "bin_centers": bin_centers,
        "bin_volumes": [round(bv, 0) for bv in bin_volumes],
        "price": round(price, 2),
        "price_range": [round(price_min, 2), round(price_max, 2)],
        "total_volume": round(total_volume, 0),
    }
