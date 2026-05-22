#!/usr/bin/env python3
"""每日荐股评分引擎 v2.1 — 含突破确认模块"""
import json, math, os, sys
from copy import deepcopy

ROOT = r"C:\Users\34269\Documents\Claude\股票分析"
KLINE_PATH = os.path.join(ROOT, "历史数据", "临时回溯", "klines_data.json")
OUTPUT_PATH = os.path.join(ROOT, "代码文件", "数据", "data_final_optimized.json")

# ========== 技术指标计算 ==========
def calc_ma(values, period):
    result = []
    for i in range(len(values)):
        if i < period - 1:
            result.append(None)
        else:
            result.append(sum(values[i-period+1:i+1]) / period)
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

def calc_ema(values, n):
    result = []
    k = 2.0 / (n + 1)
    for i in range(len(values)):
        if i == 0:
            result.append(values[i])
        else:
            result.append(values[i] * k + result[-1] * (1 - k))
    return result

def calc_macd(values, fast=12, slow=26, signal=9):
    ema_fast = calc_ema(values, fast)
    ema_slow = calc_ema(values, slow)
    dif = [ema_fast[i] - ema_slow[i] for i in range(len(values))]
    dea = calc_ema(dif, signal)
    macd = [(dif[i] - dea[i]) * 2 for i in range(len(dif))]
    return {"DIF": dif, "DEA": dea, "MACD": macd}

def calc_bollinger(values, period=20, multiplier=2):
    ma = calc_ma(values, period)
    upper, lower = [], []
    for i in range(len(values)):
        if ma[i] is None:
            upper.append(None)
            lower.append(None)
        else:
            window = values[max(0,i-period+1):i+1]
            std = (sum((x - ma[i])**2 for x in window) / len(window)) ** 0.5
            upper.append(ma[i] + multiplier * std)
            lower.append(ma[i] - multiplier * std)
    return {"MA": ma, "Upper": upper, "Lower": lower}

# ========== 评分逻辑 ==========
def score_ma_system(ma5, ma10, ma20, price):
    """3.4.1 均线系统 (6分)"""
    if ma5 is None or ma10 is None or ma20 is None or price is None:
        return 3
    # MA5 > MA10 > MA20 > MA60 (没有MA60, 用MA20代替部分逻辑)
    if ma5 > ma10 > ma20 and price > ma20:
        return 6
    if ma5 > ma10 > ma20:
        return 5
    # 均线收敛 (间距<1%)
    if ma10 > 0 and ma20 > 0:
        spread = max(ma5, ma10, ma20) / min(ma5, ma10, ma20) - 1
        if spread < 0.01:
            return 6
    if ma10 > ma5 > ma20:
        return 3
    if ma10 <= ma20:
        return 1
    return 4

def score_ma_converge(ma5, ma10, ma20, prev_ma5, prev_ma10, prev_ma20):
    """3.4.2 均线收敛与发散形态 (5分)"""
    if any(v is None for v in [ma5, ma10, ma20]):
        return 3
    if ma10 <= 0 or ma20 <= 0:
        return 3
    # 当前间距
    spread = max(ma5, ma10, ma20) / min(ma5, ma10, ma20) - 1
    # 前期间距
    if prev_ma5 and prev_ma10 and prev_ma20 and min(prev_ma5, prev_ma10, prev_ma20) > 0:
        prev_spread = max(prev_ma5, prev_ma10, prev_ma20) / min(prev_ma5, prev_ma10, prev_ma20) - 1
        # 从收敛开始发散向上
        if prev_spread < 0.02 and spread > prev_spread and ma5 > ma10:
            return 5
    # 持续收敛中
    if spread < 0.02:
        return 4
    if spread < 0.05:
        return 3
    if spread < 0.08:
        return 2
    return 0

def score_volume_price(chg_pct, volume, vol_ma5, prices_5d, klines_5d):
    """3.4.3 量价蓄势形态 (5分) — 含突破确认"""
    # === 新增: 剧烈震荡洗盘后放量突破 ===
    if len(klines_5d) >= 5 and volume > 0 and vol_ma5 > 0:
        vol_ratio = volume / vol_ma5
        # 检查前5日是否有剧烈震荡(至少2日振幅>5%且涨跌交替)
        shake_days = 0
        alt_count = 0
        for k in klines_5d[-5:]:
            amp = (k["High"] - k["Low"]) / k["PrevClose"] * 100
            if amp > 5:
                shake_days += 1
            if k["ChgPct"] > 2:
                alt_count += 1
            elif k["ChgPct"] < -2:
                alt_count -= 1
        has_shake = shake_days >= 2
        # 突破确认: 洗盘+放量+涨幅>3%
        if has_shake and vol_ratio > 1.5 and chg_pct > 3:
            return 4  # 洗盘后突破
        # 横盘整理后放量突破
        if all(abs(k["ChgPct"]) < 3 for k in klines_5d[:-1]) and chg_pct > 3 and vol_ratio > 1.5:
            return 5

    # === 原有逻辑 ===
    if chg_pct >= 3 and volume > vol_ma5 * 1.5:
        # 放量突破，但无洗盘 → 普通放量上涨
        return 3
    if 0 < chg_pct < 2 and vol_ma5 * 0.8 <= volume <= vol_ma5 * 1.2:
        if chg_pct > 0:
            return 5  # 缩量整理后温和放量+小阳线
    # 底部连续小阳线
    if prices_5d:
        small_up = sum(1 for p in prices_5d if 0 < p < 2)
        if small_up >= 3:
            return 4
    if chg_pct < 0 and volume > vol_ma5 * 1.5 and chg_pct < -3:
        return 0  # 放量暴跌
    if chg_pct < 2 and volume > vol_ma5 * 1.8:
        return 1  # 高位放量滞涨
    return 3

def score_bottom_support(klines_10d, price, ma20):
    """3.4.4 底部/支撑形态 (4分) — 含突破确认"""
    lows_10d = [k["Low"] for k in klines_10d]
    highs_10d = [k["High"] for k in klines_10d]

    # 剧烈洗盘后突破前高
    if len(klines_10d) >= 10:
        prev_high = max(highs_10d[:-1])
        if price > prev_high:
            shake = 0
            for k in klines_10d[-10:-1]:
                amp = (k["High"] - k["Low"]) / k["PrevClose"] * 100
                if amp > 5:
                    shake += 1
            if shake >= 3:
                return 4  # 洗盘后突破前高

    # 底部抬高
    if len(lows_10d) >= 10:
        rising = True
        segment = len(lows_10d) // 2
        if min(lows_10d[:segment]) < min(lows_10d[segment:]):
            pass  # 后半段低点更高
        else:
            rising = False
        if rising:
            return 4

    # 双底
    if len(klines_10d) >= 10:
        first_half_min = min(lows_10d[:len(lows_10d)//2])
        second_half_min = min(lows_10d[len(lows_10d)//2:])
        if abs(first_half_min - second_half_min) / (first_half_min or 1) < 0.03:
            if price > max([k["Close"] for k in klines_10d[len(klines_10d)//2:]]):
                return 4

    # 回踩MA20
    if ma20 and ma20 > 0:
        for k in klines_10d[-3:]:
            if abs(k["Low"] - ma20) / ma20 < 0.01:
                return 3
    # 横盘整理
    if len(klines_10d) >= 10:
        prices_10d = [k["Close"] for k in klines_10d]
        pct_range = (max(prices_10d) - min(prices_10d)) / min(prices_10d) * 100
        if pct_range < 5:
            return 3
    return 2

def score_rsi(rsi, chg_pct, has_breakout, vol_ratio):
    """3.4.5 RSI位置 (3分) — 含突破例外"""
    if rsi is None:
        return 2
    # 突破形态下的RSI>70 → 不惩罚
    if rsi > 70 and has_breakout and vol_ratio > 1.5 and chg_pct > 3:
        return 2  # 突破中超买是正常现象
    if 40 <= rsi <= 55:
        return 3
    if 30 <= rsi < 40:
        return 2
    if 55 < rsi <= 70:
        return 2
    if rsi < 30:
        return 1
    if rsi > 70:
        return 0
    return 2

def score_macd(dif, dea, prev_dif, prev_dea):
    """3.4.6 MACD (2分)"""
    if dif is None or dea is None:
        return 1
    if dif > dea and prev_dif is not None and prev_dea is not None:
        if prev_dif <= prev_dea:
            return 2  # 刚金叉
    if dif > dea > 0:
        return 1
    if dif <= dea:
        return 0
    return 1

def score_breakout_confirmation(klines_10d, chg_pct, volume, vol_ma5, price):
    """3.4.7 突破确认加分 (2分) — 新增"""
    bonus = 0
    # 条件1: 剧烈震荡洗盘模式
    if len(klines_10d) >= 10 and volume > 0 and vol_ma5 > 0:
        vol_ratio = volume / vol_ma5
        shake_days = 0
        big_up = 0
        big_down = 0
        for k in klines_10d:
            amp = (k["High"] - k["Low"]) / k["PrevClose"] * 100
            if amp > 5:
                shake_days += 1
            if k["ChgPct"] > 3:
                big_up += 1
            elif k["ChgPct"] < -3:
                big_down += 1
        # 洗盘特征: 大幅震荡+涨跌交替+放量突破
        if shake_days >= 3 and big_up >= 1 and big_down >= 1 and vol_ratio > 1.5 and chg_pct > 3:
            bonus += 1
        # 突破前高
        prev_high = max(k["High"] for k in klines_10d[:-1])
        if price > prev_high and chg_pct > 3 and vol_ratio > 1.5:
            bonus += 1
    return bonus

# ========== 主流程 ==========
def main():
    with open(KLINE_PATH, "r", encoding="utf-8-sig") as f:
        stocks = json.load(f)

    print(f"加载 {len(stocks)} 只股票K线数据")

    results = []
    for s in stocks:
        closes = s["KClose"]
        volumes = s["KVolume"]
        highs = s["KHigh"]
        lows = s["KLow"]
        opens = s["KOpen"]

        if len(closes) < 20:
            s["S_Tech"] = 1
            s["TotalScore"] = s["S_Base"] + s["S_Fund"] + 1 + s["S_Money"] + s["S_News"] + s["S_Risk"]
            results.append(s)
            continue

        price = closes[-1]
        chg_pct = s.get("ChangePct", 0)

        # 计算指标
        ma5_arr = calc_ma(closes, 5)
        ma10_arr = calc_ma(closes, 10)
        ma20_arr = calc_ma(closes, 20)
        rsi_arr = calc_rsi(closes, 14)
        macd = calc_macd(closes)
        boll = calc_bollinger(closes, 20)
        vol_ma5_arr = calc_ma(volumes, 5)

        # 最新值
        i = len(closes) - 1
        ma5 = ma5_arr[i] if i < len(ma5_arr) and ma5_arr[i] is not None else 0
        ma10 = ma10_arr[i] if i < len(ma10_arr) and ma10_arr[i] is not None else 0
        ma20 = ma20_arr[i] if i < len(ma20_arr) and ma20_arr[i] is not None else 0
        rsi = rsi_arr[i] if i < len(rsi_arr) and rsi_arr[i] is not None else 50
        dif = macd["DIF"][i] if i < len(macd["DIF"]) else 0
        dea = macd["DEA"][i] if i < len(macd["DEA"]) else 0
        bu = boll["Upper"][i] if i < len(boll["Upper"]) and boll["Upper"][i] is not None else 0
        bm = boll["MA"][i] if i < len(boll["MA"]) and boll["MA"][i] is not None else 0
        bd = boll["Lower"][i] if i < len(boll["Lower"]) and boll["Lower"][i] is not None else 0
        vol_latest = volumes[i] if i < len(volumes) else 0
        vol_ma5 = vol_ma5_arr[i] if i < len(vol_ma5_arr) and vol_ma5_arr[i] is not None else 0

        # 前值
        prev_ma5 = ma5_arr[i-1] if i-1 >= 0 and i-1 < len(ma5_arr) and ma5_arr[i-1] is not None else None
        prev_ma10 = ma10_arr[i-1] if i-1 >= 0 and i-1 < len(ma10_arr) and ma10_arr[i-1] is not None else None
        prev_ma20 = ma20_arr[i-1] if i-1 >= 0 and i-1 < len(ma20_arr) and ma20_arr[i-1] is not None else None
        prev_dif = macd["DIF"][i-1] if i-1 >= 0 and i-1 < len(macd["DIF"]) else None
        prev_dea = macd["DEA"][i-1] if i-1 >= 0 and i-1 < len(macd["DEA"]) else None

        # 构建K线历史(用于形态判断)
        klines_10d = []
        for j in range(max(0, i-9), i+1):
            prev_c = closes[j-1] if j-1 >= 0 else closes[j]
            chg = (closes[j] - prev_c) / prev_c * 100
            klines_10d.append({
                "Open": opens[j], "High": highs[j], "Low": lows[j], "Close": closes[j],
                "Volume": volumes[j], "ChgPct": chg, "PrevClose": prev_c
            })

        klines_5d = klines_10d[-5:] if len(klines_10d) >= 5 else klines_10d
        prices_5d = [k["ChgPct"] for k in klines_5d]

        vol_ratio = vol_latest / vol_ma5 if vol_ma5 > 0 else 1

        # === 突破形态判定 ===
        has_breakout = False
        if len(klines_10d) >= 10:
            shake = sum(1 for k in klines_10d if (k["High"]-k["Low"])/k["PrevClose"]*100 > 5)
            if shake >= 3 and chg_pct > 3 and vol_ratio > 1.5:
                has_breakout = True

        # === 子项评分 ===
        s1 = score_ma_system(ma5, ma10, ma20, price)
        s2 = score_ma_converge(ma5, ma10, ma20, prev_ma5, prev_ma10, prev_ma20)
        s3 = score_volume_price(chg_pct, vol_latest, vol_ma5, prices_5d, klines_5d)
        s4 = score_bottom_support(klines_10d, price, ma20)
        s5 = score_rsi(rsi, chg_pct, has_breakout, vol_ratio)
        s6 = score_macd(dif, dea, prev_dif, prev_dea)
        s7 = score_breakout_confirmation(klines_10d, chg_pct, vol_latest, vol_ma5, price)

        # 总分 = 6+5+5+4+3+2+2 = 27分, 归一化到25分
        raw_tech = s1 + s2 + s3 + s4 + s5 + s6 + s7
        tech_score = round(raw_tech / 27 * 25)
        tech_score = max(1, min(25, tech_score))

        # 更新评分
        s["S_Tech"] = tech_score
        s["TotalScore"] = s["S_Base"] + s["S_Fund"] + tech_score + s["S_Money"] + s["S_News"] + s["S_Risk"]
        s["TotalScore"] = max(0, min(100, s["TotalScore"]))

        # 清理K线数据(不写入最终输出)
        del s["KClose"]
        del s["KVolume"]
        del s["KOpen"]
        del s["KHigh"]
        del s["KLow"]

        results.append(s)

        status = "↑" if tech_score >= 15 else "↓"
        print(f"  {s['Code']} {s['Name']:6s} | S_Tech: {s['S_Tech']:2d}/25 {status} | Total: {s['TotalScore']:2d} | "
              f"子项: {s1}+{s2}+{s3}+{s4}+{s5}+{s6}+{s7} | RSI={rsi:.0f} CHG={chg_pct:+.2f}%")

    # 输出
    with open(OUTPUT_PATH, "w", encoding="utf-8-sig") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n输出: {OUTPUT_PATH}")
    print(f"评分分布: {min(s['S_Tech'] for s in results)}-{max(s['S_Tech'] for s in results)} "
          f"(均值{sum(s['S_Tech'] for s in results)/len(results):.1f})")

    # 与原始对比
    orig_path = os.path.join(ROOT, "代码文件", "数据", "data_final.json")
    with open(orig_path, "r", encoding="utf-8-sig") as f:
        orig = json.load(f)
    changes = [(s["Code"], s["Name"], o["S_Tech"], s["S_Tech"])
               for s, o in zip(results, orig) if s["S_Tech"] != o["S_Tech"]]
    changes.sort(key=lambda x: x[3] - x[2], reverse=True)
    print(f"\n评分变化(前10):")
    for code, name, old, new in changes[:10]:
        print(f"  {code} {name:6s} {old}→{new} ({new-old:+d})")

if __name__ == "__main__":
    main()
