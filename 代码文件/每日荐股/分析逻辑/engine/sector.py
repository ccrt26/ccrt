#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""铁律量化 · 评分引擎 — 板块相位 + 动量 + 趋势"""
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

    # 对每个行业：计算扩散比率并合并真实数据
    for ind, members in sectors.items():
        chgs = [s.get("ChangePct", 0) or 0 for s in members]
        turns = [s.get("TurnoverRate", 0) or 0 for s in members]
        avg_chg = sum(chgs) / len(chgs) if chgs else 0
        avg_turn = sum(turns) / len(turns) if turns else 0
        count = len(members)

        # v2.7: 扩散比率 — 板块内涨幅>3%个股占比（池内统计）
        surge_count = sum(1 for c in chgs if c > 3)
        diffusion_ratio = round(surge_count / count * 100, 1) if count > 0 else 0

        if ind in result:
            # 真实数据已存在 → 仅补充扩散比率
            result[ind]["diffusion_ratio"] = diffusion_ratio
            result[ind]["surge_count"] = surge_count
            # 如果有真实数据但count还是999，用池内count
            if result[ind].get("count", 0) <= 0:
                result[ind]["count"] = count
        else:
            # 无真实数据，用池内聚合
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
                "diffusion_ratio": diffusion_ratio,
                "surge_count": surge_count,
            }

    return result

def _convert_sector_kline_list_to_dict(kline_list, sector_phases):
    """
    兼容旧格式: 将 list[{SectorCode, ClosePrices, Dates, Volumes}]
    转为 dict[sector_code] = [{"close": x, "volume": y}, ...]
    """
    result = {}
    for item in kline_list:
        if not isinstance(item, dict):
            continue
        sc = item.get("SectorCode") or item.get("sector_code")
        if not sc:
            continue
        closes = item.get("ClosePrices") or item.get("close_prices") or []
        dates = item.get("Dates") or item.get("dates") or []
        volumes = item.get("Volumes") or item.get("volumes") or []
        klines = []
        for i in range(len(closes)):
            klines.append({
                "close": float(closes[i]) if closes[i] is not None else 0,
                "volume": float(volumes[i]) if i < len(volumes) and volumes[i] is not None else 0,
                "date": str(dates[i]) if i < len(dates) and dates[i] is not None else ""
            })
        if klines:
            result[sc] = klines
    return result


def compute_sector_trend(sector_kline_data=None, sector_phases=None, stocks=None):
    """
    板块趋势持续性评分 — 主线置信度五因子模型 (白皮书 §二十七 v2.7)

    v2.7 核心变更: 计算窗口20→10日 + 扩散比率因子 + 五因子模型
    因子1资金持续性(0-2) 因子2回调质量(0-2) 因子3成交量结构(0-2)
    因子4扩散比率(0-2) 因子5关联印证(0-2, 待TECH-06补全默认1分)
    主线判定: trend_score >= 6
    """
    if not sector_kline_data or not isinstance(sector_kline_data, dict):
        if isinstance(sector_kline_data, list):
            sector_kline_data = _convert_sector_kline_list_to_dict(sector_kline_data, sector_phases)
        if not sector_kline_data:
            return {}

    # 构建 sector_code → industry_name + diffusion_ratio 映射
    code_to_name = {}
    code_to_diffusion = {}
    for ind_name, info in (sector_phases or {}).items():
        code = info.get("sector_code")
        if code and isinstance(code, str) and code.strip():
            code_to_name[code.strip()] = ind_name
            code_to_diffusion[code.strip()] = info.get("diffusion_ratio", 0)

    result = {}

    for sector_code, klines in sector_kline_data.items():
        ind_name = code_to_name.get(sector_code, sector_code)
        diffusion_ratio = code_to_diffusion.get(sector_code, 0)

        # 提取收盘价和成交量序列
        closes = []
        vols = []
        kline_ok = False
        if isinstance(klines, list):
            for k in klines:
                if isinstance(k, dict) and "close" in k:
                    try:
                        closes.append(float(k["close"]))
                        vols.append(float(k.get("volume", 0)))
                        kline_ok = True
                    except (ValueError, TypeError):
                        continue
                elif isinstance(k, (list, tuple)) and len(k) >= 6:
                    try:
                        closes.append(float(k[4]))
                        vols.append(float(k[5]))
                        kline_ok = True
                    except (ValueError, TypeError):
                        continue

        # v2.7: 至少需要10日K线 (原20日)
        if not kline_ok or len(closes) < 10:
            result[ind_name] = {
                "trend_score": 0, "is_long_term_main_line": False,
                "sector_code": sector_code,
                "sector_name": ind_name if ind_name != sector_code else "",
                "sector_kline_available": kline_ok,
                "daily_details": {}, "factor_details": {}
            }
            continue

        N = len(closes)
        total_score = 0
        details = {}
        factor_details = {}

        # ---- 因子1: 资金持续性 (0-2分) ----
        # 10日中上涨天数>6天->+1; 近5日>=4天上涨->+1
        up_days_10 = sum(1 for i in range(N - 9, N) if closes[i] > closes[i - 1])
        recent_5d_up = sum(1 for i in range(N - 4, N) if closes[i] > closes[i - 1])
        f1 = (1 if up_days_10 > 6 else 0) + (1 if recent_5d_up >= 4 else 0)
        total_score += f1
        factor_details["f1_capital_persistence"] = f1
        details["up_days_10"] = up_days_10
        details["recent_5d_up"] = recent_5d_up
        if closes[-10] > 0:
            details["10d_return"] = round((closes[-1] - closes[-10]) / closes[-10] * 100, 2)

        # ---- 因子2: 回调质量 (0-2分) ----
        # 10日中回调日(跌幅>1.5%)平均量 vs 上涨日平均量: 缩量->2分
        f2 = 1
        if len(vols) >= 11:
            up_vols, down_vols = [], []
            for i in range(N - 9, N):
                if closes[i - 1] > 0:
                    chg = (closes[i] - closes[i - 1]) / closes[i - 1] * 100
                    if chg > 0:
                        up_vols.append(vols[i])
                    elif chg < -1.5:
                        down_vols.append(vols[i])
            if up_vols and down_vols:
                avg_up = sum(up_vols) / len(up_vols)
                avg_down = sum(down_vols) / len(down_vols)
                details["callback_vol_ratio"] = round(avg_up / avg_down if avg_down > 0 else 9, 2)
                if avg_down < avg_up:
                    f2 = 2
                elif avg_down <= avg_up * 1.1:
                    f2 = 1
                else:
                    f2 = 0
            elif up_vols and not down_vols:
                f2 = 2  # 无回调日=强势
        total_score += f2
        factor_details["f2_pullback_quality"] = f2

        # ---- 因子3: 成交量结构 (0-2分) ----
        # 上涨日均量/下跌日均量 >1.3->2分
        f3 = 1
        if len(vols) >= 11:
            up_v, down_v = [], []
            for i in range(N - 9, N):
                if closes[i - 1] > 0:
                    chg = (closes[i] - closes[i - 1]) / closes[i - 1] * 100
                    if chg > 0:
                        up_v.append(vols[i])
                    elif chg < 0:
                        down_v.append(vols[i])
            if up_v and down_v:
                avg_up_v = sum(up_v) / len(up_v)
                avg_down_v = sum(down_v) / len(down_v)
                ratio = avg_up_v / avg_down_v if avg_down_v > 0 else 9
                details["volume_structure_ratio"] = round(ratio, 2)
                if ratio > 1.3:
                    f3 = 2
                elif ratio >= 1.0:
                    f3 = 1
                else:
                    f3 = 0
        total_score += f3
        factor_details["f3_volume_structure"] = f3

        # ---- 因子4: 扩散比率 (0-2分) v2.7新增 ----
        # 板块内涨幅>3%个股占比: >40%->2, 30-40%->1, <30%->0
        f4 = 0
        if diffusion_ratio > 40:
            f4 = 2
        elif diffusion_ratio >= 30:
            f4 = 1
        elif diffusion_ratio > 0:
            f4 = 0
        else:
            f4 = 1  # 无成分股数据默认中性
        total_score += f4
        factor_details["f4_diffusion_ratio"] = f4
        details["diffusion_ratio_pct"] = diffusion_ratio

        # ---- 因子5: 关联印证 (0-2分) v2.7 TECH-06 ----
        # 遍历所有已处理板块，检查同向运动占比
        # >50%板块同向→2分(广泛参与), >30%→1分, <=30%→0分
        f5 = 1  # 默认中性
        this_dir = 1 if up_days_10 > 5 else -1  # 本板块方向
        if len(result) >= 3:  # 至少3个板块才有统计意义
            same_dir_count = sum(
                1 for _, info in result.items()
                if info.get("daily_details", {}).get("up_days_10", 5) > 5
            )
            opposite_count = sum(
                1 for _, info in result.items()
                if info.get("daily_details", {}).get("up_days_10", 5) <= 5
            )
            total_others = same_dir_count + opposite_count
            if total_others > 0 and this_dir == 1:
                agreement_pct = same_dir_count / total_others * 100
                details["sector_agreement_pct"] = round(agreement_pct, 1)
                if agreement_pct > 50:
                    f5 = 2
                elif agreement_pct > 30:
                    f5 = 1
                else:
                    f5 = 0
            elif total_others > 0 and this_dir == -1:
                agreement_pct = opposite_count / total_others * 100
                details["sector_agreement_pct"] = round(agreement_pct, 1)
                if agreement_pct > 50:
                    f5 = 2
                elif agreement_pct > 30:
                    f5 = 1
                else:
                    f5 = 0
        total_score += f5
        factor_details["f5_correlation"] = f5

        trend_score = min(10, max(0, total_score))

        result[ind_name] = {
            "trend_score": trend_score,
            "is_long_term_main_line": trend_score >= 6,
            "sector_code": sector_code,
            "sector_name": ind_name if ind_name != sector_code else "",
            "sector_kline_available": True,
            "daily_details": details,
            "factor_details": factor_details
        }

    return result


def should_exempt_by_sector(industry, sector_phases, sector_trends):
    """
    板块动量双层判断 (v2.4新增)
    判断是否因板块动量豁免否决

    返回: False=不豁免 | "partial"=部分豁免 | True=全面豁免
    """
    # 获取当日动量
    phase_info = sector_phases.get(industry, {})
    phase = phase_info.get("phase", "潜伏期")
    # 白皮书§(十八)第一层：板块强势=高潮期/主升调整（classify_phase已处理turn/chg阈值）
    is_strong_day = phase in ("高潮期", "主升调整")

    # 获取长期趋势
    trend_info = sector_trends.get(industry, {})
    is_strong_trend = trend_info.get("is_long_term_main_line", False)

    # 双层判定矩阵
    if is_strong_day and is_strong_trend:
        return True  # 主线加速 → 全面豁免
    if is_strong_day and not is_strong_trend:
        return "partial"  # 短期脉冲 → 部分豁免(PE放松+均线豁免)
    if not is_strong_day and is_strong_trend:
        return "partial_c3_only"  # 主线回调 → 仅豁免C3
    return False  # 冷门板块 → 正常执行