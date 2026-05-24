#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""铁律量化 · 评分引擎 — 题材三分类系统 + PE差异化估值"""
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

_commodity_sector_map = None  # lazy init in _score_cyclical_growth

def load_industry_whitelist():
    """加载产业认可白名单 JSON，失败时返回空字典"""
    if not os.path.exists(THEME_WHITELIST_FILE):
        return {}
    try:
        with open(THEME_WHITELIST_FILE, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        return data.get("whitelist", {})
    except (json.JSONDecodeError, OSError):
        return {}


def classify_theme(stock, whitelist=None):
    """
    题材三分类 (支持多标签)

    第一层：行业→题材映射 (THEME_CLASSIFICATION)
    第二层：白名单覆盖（industry_whitelist.json 中明确列出的股票获得对应题材标签）
    第三层：name-based keyword matching (AI/机器人/低空经济等概念名称)

    Returns: list[str] — 题材标签列表，如 ["强成长"] 或 ["强成长", "周期成长"]
    """
    industry = stock.get("Industry", "")
    code = stock.get("Code", "")
    name = stock.get("Name", "")
    themes = set()

    # 第一层：行业映射
    base_theme = THEME_CLASSIFICATION.get(industry, "稳定价值")  # 未知行业默认为稳定价值
    themes.add(base_theme)

    # 第二层：白名单覆盖 (多标签叠加，不替换)
    if whitelist:
        for theme_name, theme_info in whitelist.items():
            if not isinstance(theme_info, dict):
                continue
            wl_stocks = theme_info.get("stocks", [])
            if code in wl_stocks:
                # 白名单中的股票根据其所属产业类型叠加标签
                wl_theme = _map_whitelist_to_theme(theme_name)
                if wl_theme:
                    themes.add(wl_theme)

    # 第三层：名称关键词匹配（概念标签→题材映射）
    name_upper = (name or "").upper()
    if any(kw in name_upper for kw in ["AI", "人工智能", "智能", "机器人", "无人", "自动"]):
        if industry in ("电子", "计算机", "通信", "机械设备"):
            themes.add("强成长")

    return sorted(themes)  # 稳定排序


def _map_whitelist_to_theme(whitelist_name):
    """将白名单产业名称映射到题材类型"""
    whitelist_name_lower = whitelist_name.lower()
    strong_growth_kw = ["ai", "人工智能", "半导体", "芯片", "机器人", "低空", "创新药", "软件", "云计算"]
    cyclical_kw = ["存储", "面板", "有色", "化工", "钢铁", "煤炭", "新能源", "光伏", "风电", "锂电"]

    for kw in strong_growth_kw:
        if kw in whitelist_name_lower:
            return "强成长"
    for kw in cyclical_kw:
        if kw in whitelist_name_lower:
            return "周期成长"
    return "强成长"  # 白名单默认视为强成长（需要PE豁免的才进白名单）


def check_theme_purity(stock, whitelist=None):
    """
    题材纯度检查 C7 (白皮书 §十七-B)

    三维度打分（每项0-1分，满分3分）：
      1. 收入纯度 (>30%)：营收增长率验证 — RevenueYOY > 30% 得1分
      2. 研发可信度 (研发费用率>8% 且 研发人员>20%)：暂用毛利率代理 — GrossMargin > 30% 得1分
         (Phase 2: 接入研发费用/研发人员数据后替换)
      3. 产业认可白名单：股票在 industry_whitelist.json 中明确列出 → 得1分

    Returns: (purity_score, details_dict)
      purity_score: 0-3 (3=全面PE豁免, 2=有条件豁免, 0-1=不豁免)
    """
    score = 0
    details = {"revenue_purity": False, "rd_credibility": False, "whitelist_match": False}

    # 维度1: 收入纯度 — 营收同比增长 > 30%
    revenue_yoy = stock.get("RevenueYOY") or 0
    if revenue_yoy > 30:
        details["revenue_purity"] = True
        score += 1

    # 维度2: 研发可信度 — Phase 1 用毛利率代理 (毛利率>30%暗示技术壁垒)
    # Phase 2: 替换为 研发费用率>8% AND 研发人员占比>20%
    gross_margin = stock.get("GrossMargin") or 0
    if gross_margin > 30:
        details["rd_credibility"] = True
        score += 1

    # 维度3: 产业认可白名单
    if whitelist:
        for theme_name, theme_info in whitelist.items():
            if not isinstance(theme_info, dict):
                continue
            wl_stocks = theme_info.get("stocks", [])
            if stock.get("Code", "") in wl_stocks:
                details["whitelist_match"] = True
                score += 1
                break

    return score, details


def score_pe_by_theme(stock):
    """
    三路径PE评分 (白皮书 §二十一 v2.6重写)

    路径选择: classify_theme() → 多标签取最宽松路径(最高分)

    强成长路径 (PEG+PS):    PEG<1→12分, PEG 1-1.5→10分, 亏损→PS路径
                             PS<行业中位数×0.8→10分, 大盘股+2分, 归一化至15分
    周期成长路径 (PB+趋势):  PB<1.2→15分, PB 1.2-1.5→13分, 价格趋势向上+2/向下-3
                             大盘股+2分, 归一化至15分
    稳定价值路径 (PE区间):  PE在行业中位数±30%→15分, 超出每10%扣1分, 大盘股+2分

    Returns: (fund_score, theme_path_used, theme_details)
    """
    pe = stock.get("PE", 0) or 0
    price = stock.get("Price", 0) or 0
    mkt_cap = stock.get("MktCap", 0) or 0  # 万元
    industry = stock.get("Industry", "")
    bps = stock.get("BPS") or 0       # 每股净资产
    revenue_ttm = stock.get("RevenueTTM") or 0  # 营收TTM（万元?元? 取决于API）
    eps = stock.get("EPS") or 0
    net_profit_yoy = stock.get("NetProfitYOY") or 0
    revenue_yoy = stock.get("RevenueYOY") or 0

    # 加载白名单
    whitelist = load_industry_whitelist()

    # v2.7 TECH-05: 商品价格 (从stock临时字段读取)
    commodity_prices = stock.get("_CommodityPrices", None)

    # 多标签分类
    themes = classify_theme(stock, whitelist)

    # 大盘股判定 (市值>1000亿 → 10000000万)
    is_large_cap = mkt_cap > 10000000

    best_score = 7  # 兜底分数
    best_path = themes[0] if themes else "未知"
    all_paths = []

    for theme in themes:
        if theme == "强成长":
            path_score, path_details = _score_strong_growth(pe, price, eps, mkt_cap, revenue_ttm, net_profit_yoy, is_large_cap, stock)
        elif theme == "周期成长":
            path_score, path_details = _score_cyclical_growth(pe, price, bps, mkt_cap, is_large_cap, stock, commodity_prices)
        elif theme == "稳定价值":
            path_score, path_details = _score_stable_value(pe, industry, is_large_cap)
        else:
            path_score, path_details = (7, {"method": "默认PE区间"})

        all_paths.append((theme, path_score, path_details))
        if path_score > best_score:
            best_score = path_score
            best_path = theme

    # 归一化至15分
    fund_score = max(1, min(15, best_score))

    return fund_score, best_path, {"themes": themes, "all_paths": all_paths}


def _score_strong_growth(pe, price, eps, mkt_cap, revenue_ttm, net_profit_yoy, is_large_cap, stock):
    """
    强成长路径: PEG + PS 双轨

    PEG = PE / 净利润增长率
    PS = 市值 / 营收TTM
    """
    score = 7

    # 亏损企业 → PS路径
    if eps is None or eps <= 0 or pe <= 0:
        # PS = 总市值 / 营收TTM
        if revenue_ttm > 0 and mkt_cap > 0:
            # mkt_cap单位万元, revenue_ttm可能是元 → 统一为亿元
            mkt_cap_yi = mkt_cap / 10000  # 万元→亿元
            # revenue_ttm可能已经是万元或元，检测量级
            if revenue_ttm > mkt_cap_yi * 1e8:
                rev_yi = revenue_ttm / 1e8
            elif revenue_ttm > mkt_cap_yi * 10000:
                rev_yi = revenue_ttm / 10000
            else:
                rev_yi = max(revenue_ttm, 0.01)
            if rev_yi > 0:
                ps = mkt_cap_yi / rev_yi
                # PS越低越好，<行业×0.8为佳（行业PS中位数暂用10作为通用参考）
                if ps < 5:
                    score = 12
                elif ps < 10:
                    score = 10
                elif ps < 20:
                    score = 7
                else:
                    score = 4
                return score, {"method": "PS(亏损企业)", "PS": round(ps, 1)}
        return 5, {"method": "PS(数据不足)", "PS": None}

    # 盈利企业 → PEG路径 (v2.7: 数据源分级 — 豆包建议#3)
    # 优先券商一致预期[11]，不可得时TTM降权×0.8，标注来源透明度
    consensus_growth = stock.get("ConsensusGrowth") or 0  # 东方财富一致预期[11]
    growth_source = "[TTM]历史增速仅供参考"
    growth_quality = 0.8  # TTM数据降权20%，无前瞻性

    if consensus_growth > 0:
        eps_growth = consensus_growth
        growth_source = "[11]一致预期"
        growth_quality = 1.0
    else:
        eps_growth = net_profit_yoy  # 净利润同比增长率(%)
        if eps_growth is None or eps_growth == 0:
            revenue_yoy = stock.get("RevenueYOY") or 0
            eps_growth = revenue_yoy if revenue_yoy > 0 else 15
            growth_source = "[TTM]营收增速代理"

    if eps_growth > 0:
        raw_peg = pe / eps_growth
        if raw_peg < 1:
            score = 12
        elif raw_peg < 1.5:
            score = 10
        elif raw_peg < 2.5:
            score = 8
        else:
            score = 6
        # 应用数据源质量降权
        score = max(1, int(score * growth_quality))
        details = {"method": "PEG", "PEG": round(raw_peg, 2), "PE": round(pe, 1),
                   "growth": round(eps_growth, 1), "growth_source": growth_source}
    else:
        # 负增长 → PS路径兜底
        if revenue_ttm > 0 and mkt_cap > 0:
            mkt_cap_yi = mkt_cap / 10000
            rev_yi = revenue_ttm / 1e8 if revenue_ttm > 1e8 else max(revenue_ttm / 10000, 0.01)
            ps = mkt_cap_yi / rev_yi if rev_yi > 0 else 999
            score = 7 if ps < 15 else 4
            details = {"method": "PS(负增长兜底)", "PS": round(ps, 1)}
        else:
            score = 5
            details = {"method": "PEG/PS(数据不足)", "growth_source": growth_source}

    # PS辅助判断
    if score >= 8 and revenue_ttm > 0 and mkt_cap > 0:
        mkt_cap_yi = mkt_cap / 10000
        rev_yi = revenue_ttm / 1e8 if revenue_ttm > 1e8 else max(revenue_ttm / 10000, 0.01)
        ps = mkt_cap_yi / rev_yi if rev_yi > 0 else 999
        if ps > 30:
            score -= 2

    # 大盘股溢价
    if is_large_cap:
        score = min(15, score + 2)

    return score, details


def _score_cyclical_growth(pe, price, bps, mkt_cap, is_large_cap, stock, commodity_prices=None):
    """
    周期成长路径: PB + 价格趋势 + 商品价格趋势 (v2.7 TECH-05)

    PB = Price / 每股净资产(BPS)
    价格趋势: 近期涨幅方向
    商品价格: 对应大宗商品(铜/铝/原油等)的10d/20d趋势
    """
    score = 7
    details = {"method": "PB+趋势+商品"}

    # PB估值
    pb = None
    if bps and bps > 0 and price > 0:
        pb = price / bps
        details["PB"] = round(pb, 2)
        if pb < 0.8:
            score = 15
        elif pb < 1.2:
            score = 14
        elif pb < 1.5:
            score = 13
        elif pb < 2.0:
            score = 11
        elif pb < 3.0:
            score = 9
        else:
            score = 6
    else:
        if 0 < pe < 15:
            score = 13
        elif 15 <= pe < 25:
            score = 11
        elif 25 <= pe < 50:
            score = 9
        else:
            score = 7
        details["PB"] = None
        details["method"] = "PE近似(无BPS)"

    # 价格趋势调整
    closes = stock.get("KClose", [])
    if len(closes) >= 20 and closes[-1] > 0 and closes[-20] > 0:
        trend_20d = (closes[-1] - closes[-20]) / closes[-20] * 100
        details["trend_20d"] = round(trend_20d, 1)
        if trend_20d > 10:
            score = min(15, score + 2)
        elif trend_20d > 5:
            score = min(15, score + 1)
        elif trend_20d < -10:
            score = max(1, score - 3)
    elif len(closes) >= 5 and closes[-1] > 0 and closes[-5] > 0:
        trend_5d = (closes[-1] - closes[-5]) / closes[-5] * 100
        if trend_5d < -5:
            score = max(1, score - 2)

    # v2.7 TECH-05: 商品价格趋势 (周期股最大α来源)
    industry = stock.get("Industry", "")
    if commodity_prices:
        commodity_trend = _get_commodity_trend(industry, commodity_prices)
        if commodity_trend is not None:
            ct_10d, ct_20d, ct_change, ct_symbol = commodity_trend
            details["commodity_symbol"] = ct_symbol
            details["commodity_trend_10d"] = ct_10d

            # 商品趋势强→周期股盈利上行→加分
            if ct_10d > 10:
                score = min(15, score + 3)
                details["commodity_bonus"] = "+3(强趋势)"
            elif ct_10d > 5:
                score = min(15, score + 2)
                details["commodity_bonus"] = "+2(上行)"
            elif ct_10d > 0:
                score = min(15, score + 1)
                details["commodity_bonus"] = "+1(温和)"
            elif ct_10d < -10:
                score = max(1, score - 3)
                details["commodity_bonus"] = "-3(暴跌)"
            elif ct_10d < -5:
                score = max(1, score - 2)
                details["commodity_bonus"] = "-2(下行)"
            details["method"] = "PB+趋势+商品"

    # 大盘股溢价
    if is_large_cap:
        score = min(15, score + 2)

    return score, details


def _get_commodity_trend(industry, commodity_prices):
    """
    查找行业对应的大宗商品价格趋势

    Returns: (trend_10d, trend_20d, change_pct, symbol) or None
    """
    if not commodity_prices:
        return None

    # 遍历所有商品，匹配行业关键词
    for cp in commodity_prices:
        if not isinstance(cp, dict) or cp.get("error"):
            continue
        symbol = cp.get("symbol", "")
        sectors = COMMODITY_TO_SECTOR.get(symbol, [])
        for kw in sectors:
            if kw in industry:
                return (
                    cp.get("trend_10d", 0),
                    cp.get("trend_20d", 0),
                    cp.get("change_pct", 0),
                    symbol
                )
    return None


def _score_stable_value(pe, industry, is_large_cap):
    """
    稳定价值路径: PE在行业合理区间内

    PE在行业中位数±30%→15分，超出每10%扣1分，下限1分
    """
    score = 7
    pe_range = STABLE_VALUE_PE_RANGE.get(industry, (10, 25))
    pe_low, pe_high = pe_range

    if pe <= 0:
        return 5, {"method": "PE区间(PE无效)", "range": pe_range}

    details = {"method": "PE区间", "range": pe_range, "PE": round(pe, 1)}

    if pe_low <= pe <= pe_high:
        score = 15
    elif pe < pe_low:
        deviation = (pe_low - pe) / pe_low * 100  # 低于下限百分比
        penalty = int(deviation / 10)
        score = max(1, 12 - penalty)
    else:  # pe > pe_high
        deviation = (pe - pe_high) / pe_high * 100
        penalty = int(deviation / 10)
        score = max(1, 14 - penalty)

    if is_large_cap:
        score = min(15, score + 2)

    return score, details


def calc_sector_correlation(stock_closes, sector_closes, min_days=10):
    """
    P2-7 板块联动性验证：计算个股与板块指数的10日收益率Pearson相关性

    参数:
      stock_closes: list[float] 个股收盘价序列
      sector_closes: list[float] 板块指数收盘价序列
      min_days: 最少所需数据天数

    返回:
      correlation (float) 或 None（数据不足时）

    用途: 题材分类多维度交叉验证，相关性>0.7才认定为该题材
    """
    if not stock_closes or not sector_closes:
        return None
    if len(stock_closes) < min_days or len(sector_closes) < min_days:
        return None

    # 对齐长度
    n = min(len(stock_closes), len(sector_closes))
    if n < min_days:
        return None

    stock_ret = []
    sector_ret = []
    for i in range(1, n):
        if stock_closes[i-1] > 0 and sector_closes[i-1] > 0:
            stock_ret.append((stock_closes[i] - stock_closes[i-1]) / stock_closes[i-1])
            sector_ret.append((sector_closes[i] - sector_closes[i-1]) / sector_closes[i-1])

    if len(stock_ret) < min_days - 1:
        return None

    # Pearson相关系数
    n_r = len(stock_ret)
    mean_s = sum(stock_ret) / n_r
    mean_m = sum(sector_ret) / n_r

    cov = sum((stock_ret[i] - mean_s) * (sector_ret[i] - mean_m) for i in range(n_r))
    var_s = sum((r - mean_s) ** 2 for r in stock_ret)
    var_m = sum((r - mean_m) ** 2 for r in sector_ret)

    if var_s == 0 or var_m == 0:
        return 0.0

    return cov / ((var_s ** 0.5) * (var_m ** 0.5))