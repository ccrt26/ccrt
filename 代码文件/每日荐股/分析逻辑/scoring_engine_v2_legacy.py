#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
铁律量化 · 否决+评分引擎 v2.9
=================================
遵循白皮书：每日荐股分析逻辑白皮书 v2.9
关键要求：§否决体系(一票否决)、§评分维度(4维加权)、§(十二)数据源策略(腾讯[1]/新浪[2]/东方财富[3][7][9])、§(十七)题材三分类+差异化PE估值
v2.9 核心变更 (相位折扣扩展: 技术面+资金面+消息面):
  - 相位折扣从仅技术面→技术面+资金面+消息面三项受折扣(调整面11%→52%)
  - 资金面×phase_mult(涨停换手率/资金流虚高去水分)
  - 消息面×phase_mult(CAR5含当日暴涨去水分)
v2.8 核心变更 (权重重构+相位折扣+CAR5修复):
  - 技术面30→20分 + 板块趋势10→20分(预判与反应平衡)
  - 相位风险折扣(潜伏×1.0/主升×0.75/高潮×0.55/衰退×0.45)
  - 消息面CAR5替代当日涨跌幅(对齐白皮书§二十四)
=================================
流程: 绝对否决 → 评分 → 条件否决 → 排序
输出: data_scored.json (含 VetoStatus 字段)
"""
import json, math, os, sys
from datetime import date

ROOT = r"Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))"
DATA_FILE = os.path.join(ROOT, "代码文件", "数据", "data_full.json")
OUTPUT_FILE = os.path.join(ROOT, "代码文件", "数据", "data_scored.json")
THEME_WHITELIST_FILE = os.path.join(ROOT, "每日荐股", "配置", "industry_whitelist.json")
HISTORY_FILE = os.path.join(ROOT, "代码文件", "数据", "score_history.jsonl")  # v2.9 路线二 阶段A

# ============ 特殊股票豁免 ============
# 对国家战略级/高研发投入股票放宽否决阈值
SPECIAL_STOCK_EXEMPTIONS = {
    "688981": {  # 中芯国际 — 晶圆代工龙头，国家战略
        "exempt_abs_pe": True,      # 豁免绝对PE否决
        "exempt_cond_pe": True,     # 豁免条件PE否决
        "exempt_ma_death": True,    # 豁免MA死叉否决
    },
    "688041": {  # 海光信息 — CPU/DCU国产替代
        "exempt_cond_pe": True,     # 豁免条件PE否决（C2阈值80太高）
    },
    "688256": {  # 寒武纪 — AI芯片独角兽
        "exempt_abs_pe": True,      # 豁免绝对PE否决
        "exempt_cond_pe": True,     # 豁免条件PE否决
    },
    "688012": {  # 中微公司 — 半导体刻蚀/薄膜设备
        "abs_pe_threshold": 200,    # 绝对PE阈值提高至200
        "cond_pe_threshold": 150,   # 条件PE阈值提高至150
    },
    "603986": {  # 兆易创新 — NOR Flash/MCU
        "abs_pe_threshold": 150,    # 绝对PE阈值提高至150
        "cond_pe_threshold": 150,   # 条件PE阈值提高至150
    },
    "688008": {  # 澜起科技 — 内存接口芯片
        "cond_pe_threshold": 150,   # 条件PE阈值提高至150
    },
    "002371": {  # 北方华创 — 半导体设备龙头
        "cond_pe_threshold": 120,   # 条件PE阈值提高至120
    },
    "300661": {  # 圣邦股份 — 模拟芯片
        "cond_pe_threshold": 150,   # 条件PE阈值提高至150
    },
    "300604": {  # 长川科技 — 半导体测试设备
        "cond_pe_threshold": 120,   # 条件PE阈值提高至120
    },
    "688072": {  # 拓荆科技 — CVD薄膜沉积设备
        "cond_pe_threshold": 150,   # 条件PE阈值提高至150
    },
    "688120": {  # 华海清科 — CMP抛光设备
        "cond_pe_threshold": 150,   # 条件PE阈值提高至150
    },
    "300782": {  # 卓胜微 — 射频前端芯片龙头
        "exempt_abs_eps": True,     # 豁免EPS<=0否决（季度性波动）
    },
    "600703": {  # 三安光电 — 化合物半导体
        "exempt_abs_eps": True,     # 豁免EPS<=0否决
    },
    "688521": {  # 芯原股份 — 芯片设计服务
        "exempt_abs_eps": True,     # 豁免EPS<=0否决（高研发投入）
    },
    "688561": {  # 奇安信 — 网络安全龙头
        "exempt_abs_eps": True,     # 豁免EPS<=0否决
    },
    "300418": {  # 昆仑万维 — AI应用
        "exempt_abs_eps": True,     # 豁免EPS<=0否决
    },
}

# ============ 东方财富细分行业 → 申万大类行业 映射 ============
EASTMONEY_TO_BROAD_INDUSTRY = {
    "工业金属": "有色金属", "铜": "有色金属", "铝": "有色金属",
    "铅锌": "有色金属", "钨": "有色金属", "钴": "有色金属",
    "镍": "有色金属", "锡": "有色金属",
    "磁性材料": "有色金属", "金属新材料": "有色金属", "其他金属新材料": "有色金属",
    "印制电路板": "电子", "元件": "电子", "被动元件": "电子",
    "光学元件": "电子", "电子化学品Ⅱ": "电子", "电子化学品Ⅲ": "电子",
    "消费电子": "电子", "消费电子零部件及组装": "电子",
    "氟化工": "基础化工", "膜材料": "基础化工",
    "塑料": "基础化工", "改性塑料": "基础化工", "其他化学纤维": "基础化工",
    "磨具磨料": "机械设备", "激光设备": "机械设备",
    "锂电专用设备": "电力设备", "燃料电池": "电力设备",
    "玻纤制造": "建筑材料", "玻璃玻纤": "建筑材料",
    "非金属材料Ⅱ": "建筑材料", "非金属材料Ⅲ": "建筑材料",
    "通信设备": "通信", "通信网络设备及器件": "通信",
}

# 反向映射: 大类行业 → 其包含的东方财富细分行业列表
BROAD_TO_EASTMONEY = {}
for em_name, broad_name in EASTMONEY_TO_BROAD_INDUSTRY.items():
    BROAD_TO_EASTMONEY.setdefault(broad_name, []).append(em_name)

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

# ============ v2.6 题材三分类系统 ============
# 白皮书 §十七-A: 题材三分类 — 强成长(PEG+PS) / 周期成长(PB+价格趋势) / 稳定价值(PE合理区间)

# 行业→题材分类映射（第一层：基于申万大类行业）
# 个股可通过 industry_whitelist.json 获得额外标签（多标签叠加）
THEME_CLASSIFICATION = {
    # === 强成长：远期空间定价，PE参考价值低，用PEG+PS ===
    "电子": "强成长",
    "计算机": "强成长",
    "通信": "强成长",
    "传媒": "强成长",
    "国防军工": "强成长",
    # === 周期成长：盈利周期波动，PB锚底+趋势判断 ===
    "有色金属": "周期成长",
    "基础化工": "周期成长",
    "钢铁": "周期成长",
    "煤炭": "周期成长",
    "石油石化": "周期成长",
    "建筑材料": "周期成长",
    "电力设备": "周期成长",
    "机械设备": "周期成长",
    "汽车": "周期成长",
    # === 稳定价值：PE在合理区间才有参考意义 ===
    "食品饮料": "稳定价值",
    "银行": "稳定价值",
    "非银金融": "稳定价值",
    "公用事业": "稳定价值",
    "交通运输": "稳定价值",
    "建筑装饰": "稳定价值",
    "房地产": "稳定价值",
    "医药生物": "稳定价值",
    "家用电器": "稳定价值",
    "纺织服饰": "稳定价值",
    "商贸零售": "稳定价值",
    "社会服务": "稳定价值",
    "环保": "稳定价值",
    "农林牧渔": "稳定价值",
    "轻工制造": "稳定价值",
}

# v2.7 TECH-05: 大宗商品→行业映射 (周期产品价格趋势)
COMMODITY_TO_SECTOR = {
    "CU": ["有色金属", "铜", "工业金属"],        # 铜
    "AL": ["有色金属", "铝"],                     # 铝
    "ZN": ["有色金属", "锌", "铅锌"],             # 锌
    "AU": ["有色金属", "黄金", "贵金属"],         # 黄金
    "AG": ["有色金属", "白银"],                   # 白银
    "SC": ["石油石化", "化工"],                   # 原油
    "RB": ["钢铁", "建筑材料"],                   # 螺纹钢
    "LC": ["有色金属", "电力设备", "新能源"],     # 碳酸锂
}
# 预处理: symbol→[(sector_keyword, trend_10d, trend_20d, change_pct)]
_commodity_sector_map = None  # lazy init in _score_cyclical_growth


# 稳定价值行业PE合理区间 (白皮书 §十七-D)
STABLE_VALUE_PE_RANGE = {
    "食品饮料": (20, 45), "银行": (4, 10), "非银金融": (8, 20),
    "公用事业": (10, 25), "交通运输": (10, 22), "建筑装饰": (6, 18),
    "房地产": (5, 15), "医药生物": (22, 50), "家用电器": (10, 22),
    "纺织服饰": (12, 28), "商贸零售": (12, 30), "社会服务": (15, 40),
    "环保": (10, 28), "农林牧渔": (12, 35), "轻工制造": (12, 30),
}


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
C3_EXEMPT_SCORE = 70   # MA5<MA10 豁免线（短期回踩，v2.3放宽）
C5_EXEMPT_SCORE = 75   # MA10≤MA20 豁免线（高分豁免）

# 数据源标记映射表（红线规则 v1.4 §1.2）
FIELD_SOURCE_MAP = {
    "Price": "[1]", "ChangePct": "[1]", "Volume": "[2]",
    "TurnoverRate": "[1]", "PE": "[3]", "MktCap": "[1]",
    "EPS": "[3]", "MA5": "[5]", "MA10": "[5]", "MA20": "[5]",
    "RSI": "[5]", "VolRatio": "[5]", "VolumePercentile": "[5]",
    "FundMainNet": "[9]", "SectorPhase": "[7]", "SectorTrend": "[7]",
    # v2.6: 新增财务字段(三路径PE评分)
    "BPS": "[3]", "RevenueTTM": "[3]", "RevenueYOY": "[3]",
    "NetProfitYOY": "[3]", "GrossMargin": "[3]",
    # v2.8: 北向资金 + 融资融券 + 一致预期
    "NorthboundSharesRatio": "[8]", "NorthboundFreeRatio": "[8]",
    "NorthboundHoldMktCap": "[8]",
    "MarginRZYE": "[12]", "MarginRZJME": "[12]",
    "MarginRZYE_5dChange": "[12]",
    "ConsensusGrowth": "[11]", "ResearchReportCount": "[11]",
}

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


def compute_scores(s, sector_info=None, sector_trend_info=None):
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

    return {
        "S_Base": base, "S_Fund": fund, "S_Tech": tech,
        "S_Money": money, "S_News": news, "S_Risk": risk,
        "S_SectorTrend": sector_trend_score,
        "S_Tech_Details": tech_details,
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


def assess_data_quality(s):
    """
    三级数据质量标签 (白皮书 §三十二)
    返回: "完整" | "部分缺失" | "严重缺失"
    """
    kline = s.get("KClose", [])
    price = s.get("Price")
    volume = s.get("Volume")
    eps = s.get("EPS")
    pe = s.get("PE")
    fund_net = s.get("FundMainNet")

    # "严重缺失": KLine为空或行情数据缺失
    if len(kline) == 0 or price is None or price == 0:
        return "严重缺失"

    # "部分缺失": KLine<20或EPS缺失或资金流缺失
    if len(kline) < 20 or eps is None or fund_net is None:
        return "部分缺失"

    # "完整": 所有必需数据齐全
    # KLine有≥20个值, EPS存在, PE可计算, 行情数据完整
    if pe is not None and pe > 0 and volume is not None:
        return "完整"

    # PE不可计算的边界情况 → 部分缺失
    return "部分缺失"


# ----- v2.9 路线二 阶段A: 评分历史落库 -----
def append_history(stocks, sector_phase_map, run_date=None):
    """每日评分完成后，将分项得分追加到 score_history.jsonl。
    目标变量 (ret_t1/t3/t5) 设为 null，由次日 backfill_returns.py 回填。
    """
    if run_date is None:
        run_date = date.today().strftime("%Y-%m-%d")

    existing = set()
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    key = (rec.get("date"), rec.get("code"))
                    if key[0] == run_date:
                        existing.add(key[1])
                except json.JSONDecodeError:
                    pass

    written = 0
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        for s in stocks:
            code = s.get("Code", "")
            if code in existing:
                continue  # 当日已记录，跳过重复

            industry = s.get("Industry", "")
            phase = sector_phase_map.get(industry, {}).get("phase", "潜伏期") if sector_phase_map else "潜伏期"
            td = s.get("S_Tech_Details", {})

            rec = {
                "date": run_date,
                "code": code,
                "name": s.get("Name", ""),
                "industry": industry,
                "phase": s.get("SectorPhase", phase),
                "price": s.get("Price", 0),
                "change_pct": s.get("ChangePct", 0),
                "turnover": s.get("TurnoverRate", 0),
                "pe": s.get("PE", 0),
                "S_Base": s.get("S_Base", 0),
                "S_Fund": s.get("S_Fund", 0),
                "S_Tech": s.get("S_Tech", 0),
                "S_Money": s.get("S_Money", 0),
                "S_News": s.get("S_News", 0),
                "S_Risk": s.get("S_Risk", 0),
                "S_SectorTrend": s.get("S_SectorTrend", 0),
                "TotalScore": s.get("TotalScore", 0),
                "S1_MA": td.get("S1_MA_System", 0),
                "S2_Converge": td.get("S2_MA_Converge", 0),
                "S3_Volume": td.get("S3_Volume_Price", 0),
                "S4_Support": td.get("S4_Support", 0),
                "S5_RSI": td.get("S5_RSI", 0),
                "S6_MACD": td.get("S6_MACD", 0),
                "S7_Breakout": td.get("S7_Breakout", 0),
                "S8_Momentum": td.get("S8_Trend_Momentum", 0),
                "raw_tech": td.get("raw_tech", 0),
                "ret_t1": None, "ret_t3": None, "ret_t5": None,
                "ret_t1_vs_market": None
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            written += 1

    print(f"[History] {run_date}: appended {written} records to score_history.jsonl "
          f"(skipped {len(existing)} duplicates)")

def main(run_date=None, verbose=False):
    """run_date: 交易日 YYYY-MM-DD，默认今天（用于评分历史的日期标记）"""
    if run_date is None:
        run_date = date.today().strftime("%Y-%m-%d")

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
        sector_kline = raw.get("SectorKLine", None)  # v2.4: 板块指数历史K线
        market_turnover = raw.get("MarketTurnover", None)  # v2.7: 全市场近5日均成交额(亿)
        commodity_prices = raw.get("CommodityPrices", None)  # v2.7 TECH-05: 大宗商品价格
    else:
        stocks = raw
        sector_data = None
        sector_fund_flow = None
        sector_kline = None
        market_turnover = None
    print(f"加载 {len(stocks)} 只股票数据\n")

    # v2.7: 计算V5动态阈值
    v5_threshold, v5_tier = _get_v5_threshold(market_turnover)
    print(f"V5流动性阈值: {v5_threshold}万 ({v5_tier})")

    # 计算板块动量（优先使用东方财富真实市场数据）
    sector_phases = compute_sector_phases(stocks, sector_data, sector_fund_flow)
    if verbose:
        for ind, info in sorted(sector_phases.items(), key=lambda x: x[1]["money_bonus"], reverse=True):
            bn = info["money_bonus"]
            sign = "+" if bn >= 0 else ""
            cnt = f"{info['count']}只" if info['count'] > 0 else "市场数据"
            print(f"  板块 {ind:8s} | {info['phase']:5s} | 涨幅{info['avg_chg']:+.2f}% 换手{info['avg_turn']:.2f}% | 资金面{sign}{bn}分 ({cnt})")

    # v2.7: 计算板块趋势持续性（白皮书 §二十七 五因子模型）
    sector_trends = compute_sector_trend(sector_kline, sector_phases)

    # v2.7 TECH-04: 主线衰减检测 — 连续5日趋势分下降触发降级
    attenuation_file = os.path.join(ROOT, "代码文件", "data_cache", "sector_trend_history.json")
    trend_history = {}
    if os.path.exists(attenuation_file):
        try:
            with open(attenuation_file, "r", encoding="utf-8-sig") as f:
                trend_history = json.load(f)
        except (json.JSONDecodeError, OSError):
            trend_history = {}

    # 对当前为主线(>=6)的板块检查是否连续5日趋势分下降
    attenuation_alerts = []
    for ind_name, info in sector_trends.items():
        if not info.get("is_long_term_main_line"):
            continue
        code = info.get("sector_code", ind_name)
        if code not in trend_history:
            continue
        past_scores = trend_history[code].get("scores", [])
        # 检查最近5日(含今日)是否连续下降
        if len(past_scores) >= 4:
            recent_5 = past_scores[-4:] + [info["trend_score"]]
            if all(recent_5[i] > recent_5[i+1] for i in range(len(recent_5)-1)):
                info["is_long_term_main_line"] = False
                info["trend_score"] = min(info["trend_score"], 5)
                info["attenuation"] = True
                info["_attenuation_detail"] = f"连续5日下降: {recent_5}"
                attenuation_alerts.append(f"  ⚠ {ind_name}: {recent_5} 连续5日下降→降级至轮动中")

    if attenuation_alerts:
        print(f"\n⚠ 主线衰减检测 (TECH-04):")
        for a in attenuation_alerts:
            print(a)

    # 保存今日趋势分至历史缓存
    today_scores = {}
    for ind_name, info in sector_trends.items():
        code = info.get("sector_code", ind_name)
        if code in trend_history:
            past = trend_history[code].get("scores", [])
        else:
            past = []
        past.append(info["trend_score"])
        if len(past) > 10:
            past = past[-10:]  # 保留最近10日
        today_scores[code] = {"scores": past, "last_update": __import__("datetime").datetime.now().strftime("%Y-%m-%d")}
    try:
        os.makedirs(os.path.dirname(attenuation_file), exist_ok=True)
        with open(attenuation_file, "w", encoding="utf-8-sig") as f:
            json.dump(today_scores, f, ensure_ascii=False, indent=2)
    except OSError:
        pass  # 缓存写入失败不影响主流程

    if sector_trends and verbose:
        print(f"\n板块趋势持续性 (基于板块历史K线, 五因子 v2.7):")
        for ind, info in sorted(sector_trends.items(), key=lambda x: x[1]["trend_score"], reverse=True)[:10]:
            main_line = "★主线" if info["is_long_term_main_line"] else "  轮动"
            attn = " [衰减]" if info.get("attenuation") else ""
            kline_flag = "有" if info.get("sector_kline_available") else "无"
            factors = info.get("factor_details", {})
            fstr = "/".join(str(factors.get(k, "?")) for k in ["f1_capital_persistence","f2_pullback_quality","f3_volume_structure","f4_diffusion_ratio","f5_correlation"])
            print(f"  {main_line}{attn} {ind:8s} | 置信度{info['trend_score']}分 | 因子{fstr} | K线:{kline_flag}")
    elif not sector_trends:
        print(f"\n板块趋势持续性: 无 SectorKLine 数据，SectorTrendMap 置空")

    passed = []
    vetoed = []

    # v2.8: 预计算全市场5日涨幅中位数（CAR5基准，代理沪深300）
    all_5d_returns = []
    for _s in stocks:
        _closes = _s.get("KClose", [])
        if len(_closes) >= 5 and _closes[-5] > 0:
            _ret = (_closes[-1] - _closes[-5]) / _closes[-5] * 100
            all_5d_returns.append(_ret)
    market_5d_median = sorted(all_5d_returns)[len(all_5d_returns)//2] if all_5d_returns else 0
    if verbose:
        print(f"全市场5日涨幅中位数: {market_5d_median:.2f}% (CAR5基准)")

    # v2.7 D.1: 市场环境自适应 — 检测全市场状态(强势/弱势/震荡)
    market_state, market_pe_mult, market_exempt_delta = detect_market_state(stocks)
    print(f"\n市场环境: {market_state} | PE阈值×{market_pe_mult} | 豁免分Δ={market_exempt_delta:+d}")

    # 构建行业名反向查找: 对每个大类行业，合并其下所有细分行业的相位数据
    # 优先使用大类行业名直接查找，其次通过细分→大类映射查找
    def get_sector_info(stock_industry):
        """查找股票的板块相位信息，支持大类/细分行业名双向查找"""
        # 直接命中
        if stock_industry in sector_phases:
            return sector_phases[stock_industry]
        # 通过东方财富细分名反向查找（股票行业为细分名 → 映射到大类）
        broad = EASTMONEY_TO_BROAD_INDUSTRY.get(stock_industry)
        if broad and broad in sector_phases:
            return sector_phases[broad]
        # 通过大类→细分映射查找（股票行业为大类名 → 合并细分相位）
        subs = BROAD_TO_EASTMONEY.get(stock_industry, [])
        if subs:
            candidates = [sector_phases[sub] for sub in subs if sub in sector_phases]
            if candidates:
                # 合并: 使用加权平均（或取最佳）
                best = max(candidates, key=lambda x: x["money_bonus"] + x["news_bonus"])
                return best
        return None

    def get_sector_trend_info(stock_industry):
        """查找股票的板块趋势持续性信息（v2.4新增），支持行业名/sector_code 双向查找"""
        # 直接用行业名称查找
        if stock_industry in sector_trends:
            return sector_trends[stock_industry]
        # 通过东方财富细分名反向查找（股票行业为细分名 → 映射到大类）
        broad = EASTMONEY_TO_BROAD_INDUSTRY.get(stock_industry)
        if broad and broad in sector_trends:
            return sector_trends[broad]
        # 通过大类→细分映射查找（股票行业为大类名 → 合并细分趋势）
        subs = BROAD_TO_EASTMONEY.get(stock_industry, [])
        if subs:
            candidates = [sector_trends[sub] for sub in subs if sub in sector_trends]
            if candidates:
                best = max(candidates, key=lambda x: x["trend_score"])
                return best
        # 回退：按 sector_code 遍历查找（当 code_to_name 映射未覆盖时）
        for ind, info in sector_trends.items():
            if info.get("sector_code") == stock_industry:
                return info
        return None

    for s in stocks:
        code = s.get("Code", "")
        name = s.get("Name", "")
        # v2.7 TECH-05: 附加商品价格供 scoring 使用
        s["_CommodityPrices"] = commodity_prices
        s["_Market5DMedian"] = market_5d_median  # v2.8: CAR5基准
        sector_info = get_sector_info(s.get("Industry", ""))
        sector_trend_info = get_sector_trend_info(s.get("Industry", ""))  # v2.4

        # === 数据质量标签 (白皮书 §三十二) ===
        s["DataQuality"] = assess_data_quality(s)

        # Phase A: 绝对否决
        veto = check_absolute_vetoes(s, v5_threshold)
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
            s["TotalScore"] = s["S_Base"] + s["S_Fund"] + s["S_Tech"] + s["S_Money"] + s["S_News"] + s["S_Risk"] + s.get("S_SectorTrend", 0)
            if sector_info:
                s["SectorPhase"] = sector_info["phase"]
            # 补全技术指标默认值（否决股不走 compute_scores 但报告/评估需要这些字段）
            price = s.get("Price", 0)
            s["MA5"] = s.get("MA5") or round(price, 2)
            s["MA10"] = s.get("MA10") or round(price, 2)
            s["MA20"] = s.get("MA20") or round(price, 2)
            s["RSI"] = s.get("RSI") or 50
            s["VolRatio"] = s.get("VolRatio") or 1.0
            s["MACD_Status"] = s.get("MACD_Status", "中性")
            s["TechAnalysis"] = s.get("TechAnalysis", "")
            s["VolumePercentile"] = s.get("VolumePercentile")
            s["PathTag"] = s.get("PathTag") or "震荡"
            vetoed.append(s)
            continue

        # Phase B: 评分（传入板块动量信息+板块趋势持续性v2.4）
        scores, tech_info = compute_scores(s, sector_info, sector_trend_info)
        s.update(scores)

        # Phase C: 条件否决（v2.7: +D.1市场自适应参数）
        veto = check_conditional_vetoes(s, scores, sector_phases, sector_trends, market_state)
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

    # 将 sector_phases 转换为 JSON 可序列化格式（v2.7: +diffusion_ratio）
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
            "sector_code": info.get("sector_code", ""),
            "diffusion_ratio": info.get("diffusion_ratio", 0),  # v2.7: 扩散比率
            "surge_count": info.get("surge_count", 0),
        }

    # v2.7: 板块趋势持续性（五因子 + 衰减检测）
    sector_trend_map = {}
    for ind, info in sector_trends.items():
        code = info.get("sector_code", ind)
        sector_trend_map[code] = {
            "sector_code": code,
            "sector_name": info.get("sector_name", ind),
            "trend_score": info["trend_score"],
            "is_long_term_main_line": info["is_long_term_main_line"],
            "sector_kline_available": info.get("sector_kline_available", False),
            "daily_details": info.get("daily_details", {}),
            "factor_details": info.get("factor_details", {}),  # v2.7: 五因子明细
            "attenuation": info.get("attenuation", False),     # v2.7: 衰减标记
        }

    # 输出
    output = {
        "BuildTime": date.today().strftime("%Y-%m-%d") + " " + __import__("time").strftime("%H:%M:%S"),
        "TradeDate": run_date,
        "Summary": {
            "Total": len(stocks),
            "Passed": len(passed),
            "Vetoed": len(vetoed),
            "PassRate": f"{len(passed)/len(stocks)*100:.1f}%"
        },
        "SectorPhaseMap": sector_phase_map,
        "SectorTrendMap": sector_trend_map,  # v2.4 板块趋势持续性
        "FieldSources": FIELD_SOURCE_MAP,  # 数据源标记映射表（红线规则 v1.4 §1.2）
        "Recommendations": [{
            "Code": s["Code"], "Name": s["Name"],
            "Industry": s.get("Industry", ""),
            "TotalScore": s["TotalScore"],
            "S_Base": s["S_Base"], "S_Fund": s["S_Fund"],
            "S_Tech": s["S_Tech"], "S_Money": s["S_Money"],
            "S_News": s["S_News"], "S_Risk": s["S_Risk"],
            "S_SectorTrend": s.get("S_SectorTrend", 0),  # v2.4 板块趋势持续性
            "S_Tech_Details": s.get("S_Tech_Details", {}),  # v2.4 技术面子项
            "DataQuality": s.get("DataQuality", ""),  # 数据质量标签
            "PoolSource": s.get("PoolSource", ""),
            "Price": s.get("Price", 0),
            "ChangePct": s.get("ChangePct", 0),
            "TurnoverRate": s.get("TurnoverRate", 0),
            "PE": s.get("PE", 0),
            # v2.6: 题材三分类 + C7纯度
            "ThemePath": s.get("_ThemePath", ""),
            "ThemeDetails": s.get("_ThemeDetails", {}),
            "C7_Purity": s.get("_C7_Purity", -1),
            "C7_PurityDetails": s.get("_C7_PurityDetails", {}),
            # 技术指标（供报告生成使用）
            "MA5": s.get("MA5"), "MA10": s.get("MA10"), "MA20": s.get("MA20"),
            "RSI": s.get("RSI"), "MACD_Status": s.get("MACD_Status", ""),
            "VolRatio": s.get("VolRatio"),
            "VolumePercentile": s.get("VolumePercentile"),
            "PathTag": s.get("PathTag", "震荡"),
            "TechAnalysis": s.get("TechAnalysis", ""),
            "SectorPhase": s.get("SectorPhase", ""),
            "ATR14": s.get("ATR14", 0),  # 流金 v2026-05-24
        } for s in passed[:25]],  # 限制推荐不超过25只
        "AllStocks": passed,  # 仅含通过股
        "VetoedStocks": [{  # v2.4.1: VetoedStocks供内部审计用，不再在HTML报告中展示
            "Code": s["Code"], "Name": s["Name"],
            "Industry": s.get("Industry", ""),
            "TotalScore": s["TotalScore"],
            "VetoStatus": s.get("VetoStatus", ""),
            "VetoReason": s.get("VetoReason", ""),
            "ThemePath": s.get("_ThemePath", ""),
            "C7_Purity": s.get("_C7_Purity", -1),
            "S_Base": s["S_Base"], "S_Fund": s["S_Fund"],
            "S_Tech": s["S_Tech"], "S_Money": s["S_Money"],
            "S_News": s["S_News"], "S_Risk": s["S_Risk"],
            "S_SectorTrend": s.get("S_SectorTrend", 0),
            "DataQuality": s.get("DataQuality", ""),
            "PoolSource": s.get("PoolSource", ""),
            "Price": s.get("Price", 0),
            "ChangePct": s.get("ChangePct", 0),
            "PE": s.get("PE", 0),
            "MA5": s.get("MA5"), "MA10": s.get("MA10"), "MA20": s.get("MA20"),
            "RSI": s.get("RSI"), "MACD_Status": s.get("MACD_Status", ""),
            "VolRatio": s.get("VolRatio"),
            "VolumePercentile": s.get("VolumePercentile"),
            "PathTag": s.get("PathTag", "震荡"),
            "SectorPhase": s.get("SectorPhase", ""),
            "ATR14": s.get("ATR14", 0),  # 流金 v2026-05-24
        } for s in vetoed],
        "data_quality": {  # 玉夜 v2026-05-24
            "flag": "normal",
            "degraded_fields": [],
            "cached_fields": [],
            "api_latency_ms": 0,
            "checked_at": date.today().isoformat()
        }
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8-sig") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"{'='*50}")
    print(f"否决结果:")
    print(f"  通过: {len(passed)} 只 ({output['Summary']['PassRate']})")
    print(f"  否决: {len(vetoed)} 只")

    if verbose:
        if vetoed:
            print(f"\n否决明细 (仅供控制台审计):")
            for v in vetoed:
                print(f"  [{v['VetoStatus']}] {v['Code']} {v['Name']} — {v['VetoReason']} (总分:{v['TotalScore']})")

        print(f"\n推荐排序 (前10):")
        for i, r in enumerate(output["Recommendations"][:10], 1):
            src = "★" if r["PoolSource"] == "core_stock" else " "
            print(f"  {i:2d}. {src}{r['Code']} {r['Name']:6s} | 总分:{r['TotalScore']:2d} "
                  f"| 技术:{r['S_Tech']:2d} 资金:{r['S_Money']:2d} "
                  f"| PE:{r['PE']:.0f} 涨跌:{r['ChangePct']:+.2f}%")

    print(f"\n输出: {OUTPUT_FILE}")

    # v2.9 路线二 阶段A: 评分历史落库
    append_history(passed, sector_phase_map, run_date)

    print("Done")


if __name__ == "__main__":
    run_date = None
    verbose = False
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--date" and i + 1 < len(args):
            run_date = args[i + 1]
            i += 1
        elif arg == "--verbose":
            verbose = True
        i += 1
    main(run_date, verbose=verbose)
