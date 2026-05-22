#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
铁律量化 · 否决+评分引擎 v2
=================================
遵循白皮书：每日荐股分析逻辑白皮书 v2.4
关键要求：§否决体系(一票否决)、§评分维度(4维加权)、§(十二)数据源策略(腾讯[1]/新浪[2]/东方财富[3][7][9])
=================================
流程: 绝对否决 → 评分 → 条件否决 → 排序
输出: data_scored.json (含 VetoStatus 字段)
"""
import json, math, os, sys

ROOT = r"C:\Users\34269\Documents\Claude\股票分析"
DATA_FILE = os.path.join(ROOT, "代码文件", "数据", "data_full.json")
OUTPUT_FILE = os.path.join(ROOT, "代码文件", "数据", "data_scored.json")

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
C3_EXEMPT_SCORE = 70   # MA5<MA10 豁免线（短期回踩，v2.3放宽）
C5_EXEMPT_SCORE = 75   # MA10≤MA20 豁免线（高分豁免）

# 数据源标记映射表（红线规则 v1.4 §1.2）
FIELD_SOURCE_MAP = {
    "Price": "[1]", "ChangePct": "[1]", "Volume": "[2]",
    "TurnoverRate": "[1]", "PE": "[3]", "MktCap": "[1]",
    "EPS": "[3]", "MA5": "[5]", "MA10": "[5]", "MA20": "[5]",
    "RSI": "[5]", "VolRatio": "[5]", "VolumePercentile": "[5]",
    "FundMainNet": "[9]", "SectorPhase": "[7]", "SectorTrend": "[7]",
}

def check_absolute_vetoes(s):
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

    # V5: 流动性枯竭
    volume = s.get("Volume", 0)
    turnover_rate = s.get("TurnoverRate", 0) or 0
    if price > 0:
        turnover_value = volume * price / 100  # 万元（Volume单位为手，*100=股）
        if turnover_value < 1500 and turnover_rate < 0.5:
            return ("vetoed_abs_5", f"流动性枯竭: 成交额{turnover_value:.0f}万 < 1500万")

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
    计算板块趋势持续性评分 (白皮书 §二十七 v2.4新增)
    基于板块指数历史K线，识别长期主线 vs 短期轮动

    评分维度（总分0-5）：
      +1  板块20日涨幅>10%
      +1  20日中上涨天数>12天(>60%)
      +1  板块20日涨幅跑赢沪深300>5%（需大盘K线数据，缺省时计0分）
      +2  主力资金趋势：20日净流入天数>12天+1，最近5日持续净流入+1
          （资金流历史数据不足时，以上涨天数/持续度作为价格-资金协同代理指标）

    返回: { industry_name: { trend_score, is_long_term_main_line, sector_code,
                              sector_name, sector_kline_available, daily_details } }
    数据不足时返回空字典（SectorTrendMap 置空）。
    当无外部K线数据时，使用 stocks 聚合计算合成板块K线作为备选。
    """
    if not sector_kline_data or not isinstance(sector_kline_data, dict):
        # 兼容: 旧格式是 list[{SectorCode, ClosePrices}], 转成 dict
        if isinstance(sector_kline_data, list):
            sector_kline_data = _convert_sector_kline_list_to_dict(sector_kline_data, sector_phases)
        if not sector_kline_data:
            return {}

    # 构建 sector_code → industry_name 映射（从 sector_phases 的 sector_code 字段）
    code_to_name = {}
    for ind_name, info in (sector_phases or {}).items():
        code = info.get("sector_code")
        if code and isinstance(code, str) and code.strip():
            code_to_name[code.strip()] = ind_name

    result = {}

    for sector_code, klines in sector_kline_data.items():
        # 获取行业名称
        ind_name = code_to_name.get(sector_code, sector_code)

        # 提取收盘价序列
        closes = []
        kline_ok = False
        if isinstance(klines, list):
            for k in klines:
                if isinstance(k, dict) and "close" in k:
                    try:
                        closes.append(float(k["close"]))
                        kline_ok = True
                    except (ValueError, TypeError):
                        continue
                elif isinstance(k, (list, tuple)) and len(k) >= 5:
                    try:
                        closes.append(float(k[4]))  # OHLCV → index 4 = close
                        kline_ok = True
                    except (ValueError, TypeError):
                        continue

        # 缓存穿透：K线天数<20的板块趋势评分默认0分
        if not kline_ok or len(closes) < 20:
            result[ind_name] = {
                "trend_score": 0,
                "is_long_term_main_line": False,
                "sector_code": sector_code,
                "sector_name": ind_name if ind_name != sector_code else "",
                "sector_kline_available": kline_ok,
                "daily_details": {}
            }
            continue

        score = 0
        details = {}

        # 1) 板块20日涨幅 > 10%（1分）
        if closes[-20] > 0:
            gain_20d = (closes[-1] - closes[-20]) / closes[-20] * 100
        else:
            gain_20d = 0
        details["20d_return"] = round(gain_20d, 2)
        if gain_20d > 10:
            score += 1

        # 2) 20日中上涨天数 > 12天 (>60%)（1分）
        up_days_20 = sum(
            1 for i in range(len(closes) - 19, len(closes))
            if closes[i] > closes[i - 1]
        )
        details["up_days_ratio"] = round(up_days_20 / 20, 2)
        if up_days_20 > 12:
            score += 1

        # 3) 相对大盘超额 > 5%（1分）
        # 沪深300等基准指数K线不在 SectorKLine 中，此项暂跳过。
        # 待未来数据源扩充后可启用，当前默认 0 分。
        details["excess_return"] = 0

        # 4) 主力资金趋势（2分）
        # 资金流历史数据不足（仅当日 snapshot），使用价格走势作为代理：
        #   +1  20日上涨天数>12天（价格持续上行 ≈ 资金持续净流入）
        #   +1  最近5日中至少4天上涨（持续净流入 ≈ 主力持续买入）
        recent_5d_up = sum(
            1 for i in range(len(closes) - 4, len(closes))
            if closes[i] > closes[i - 1]
        )
        details["net_inflow_days"] = up_days_20
        details["recent_5d_inflow"] = recent_5d_up >= 4

        if up_days_20 > 12:
            score += 1
        if recent_5d_up >= 4:
            score += 1

        score = min(5, score)

        result[ind_name] = {
            "trend_score": score,
            "is_long_term_main_line": score >= 3,
            "sector_code": sector_code,
            "sector_name": ind_name if ind_name != sector_code else "",
            "sector_kline_available": True,
            "daily_details": details
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

    # --- S_Fund: 基本面 (15分 v2.4降权) ---
    fund = 11  # 默认中等
    if 0 < pe <= 15: fund = 13
    elif 15 < pe <= 30: fund = 11
    elif 30 < pe <= 80: fund = 9
    elif pe > 80: fund = 7
    if mkt_cap > 1000000: fund += 2  # 大盘溢价
    fund = max(1, min(15, fund))

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
        tech = round(raw_tech / 27 * 30)  # v2.4 归一化至30分
        tech = max(1, min(30, tech))
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
    news = max(1, min(15, news))  # v2.4 消息面降权至15分

    # --- S_Risk: 风控 (5分) ---
    risk = 3
    if pe > 0 and pe < 60: risk += 1
    if 1 <= turnover <= 8: risk += 1
    risk = max(1, min(5, risk))

    # --- S_SectorTrend: 板块趋势持续性 (5分 v2.4新增) ---
    sector_trend_score = 0
    if sector_trend_info:
        sector_trend_score = sector_trend_info.get("trend_score", 0)
        sector_trend_score = max(0, min(5, sector_trend_score))

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


def check_conditional_vetoes(s, scores, sector_phases=None, sector_trends=None):
    """6条条件否决, 返回 (否决id, 原因) 或 None"""
    closes = s.get("KClose", [])
    price = s.get("Price", 0)
    pe = s.get("PE", 0)
    total = scores["TotalScore"]
    industry = s.get("Industry", "")
    code = s.get("Code", "")
    exemption = SPECIAL_STOCK_EXEMPTIONS.get(code, {})

    # v2.4: 板块动量双层判断 — 主线板块全面豁免否决
    sector_exempt = should_exempt_by_sector(industry, sector_phases or {}, sector_trends or {})

    # C1: PE偏高(科技制造>120) — 检查豁免
    cond_pe_threshold = exemption.get("cond_pe_threshold", 120)
    if not exemption.get("exempt_cond_pe"):
        if pe > cond_pe_threshold and industry in ("电子", "计算机", "通信", "汽车", "电力设备", "机械设备"):
            if total < PE_COND_EXEMPT_SCORE:
                if sector_exempt == True:
                    pass  # 全面豁免
                elif sector_exempt == "partial_c3_only":
                    pass  # 主线回调→豁免
                elif sector_exempt == "partial":
                    if total >= 70:
                        pass  # 短期脉冲→豁免分降至70
                    else:
                        return ("vetoed_cond_1", f"科技PE过高: {pe:.0f} > {cond_pe_threshold} (短期脉冲豁免需总分≥70)")
                else:
                    return ("vetoed_cond_1", f"科技PE过高: {pe:.0f} > {cond_pe_threshold} (豁免需总分≥{PE_COND_EXEMPT_SCORE})")

    # C2: PE偏高(高成长>80) — 检查豁免（含个股特定阈值）
    c2_threshold = exemption.get("cond_pe_threshold", PE_COND_THRESHOLD)
    if not exemption.get("exempt_cond_pe"):
        if pe > c2_threshold:
            if total < PE_COND_EXEMPT_SCORE:
                if sector_exempt == True:
                    pass  # 全面豁免
                elif sector_exempt == "partial_c3_only":
                    pass  # 主线回调→豁免
                elif sector_exempt == "partial":
                    if total >= 70:
                        pass  # 短期脉冲→豁免分降至70
                    else:
                        return ("vetoed_cond_2", f"PE过高: {pe:.0f} > {c2_threshold} (短期脉冲豁免需总分≥70)")
                else:
                    return ("vetoed_cond_2", f"PE过高: {pe:.0f} > {c2_threshold} (豁免需总分≥{PE_COND_EXEMPT_SCORE})")

    # C3: MA5 < MA10*0.99 (短期均线回踩)
    if len(closes) >= 10:
        ma5 = calc_ma(closes, 5)[-1]
        ma10 = calc_ma(closes, 10)[-1]
        if ma5 is not None and ma10 is not None and ma5 < ma10 * 0.95:
            if total < C3_EXEMPT_SCORE:
                if sector_exempt == True or sector_exempt == "partial" or sector_exempt == "partial_c3_only":
                    pass  # 板块动量豁免C3（主线/脉冲/主线回调均豁免C3）
                else:
                    return ("vetoed_cond_3", f"短期均线回踩: MA5({ma5:.2f}) < MA10({ma10:.2f})×0.95 (豁免需总分≥{C3_EXEMPT_SCORE})")

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
            if total < C5_EXEMPT_SCORE:
                ma5 = calc_ma(closes, 5)[-1]
                detail = f"MA10({ma10:.2f})≤MA20({ma20:.2f})"
                if ma5 is not None and ma5 > ma10:
                    pass  # 短期仍在多头，豁免
                elif price > ma20 * 1.03:
                    pass  # 价格远高于MA20，死叉可能是短暂回调(v2.4 1.05→1.03放宽)
                elif sector_exempt == True or sector_exempt == "partial":
                    pass  # 板块动量豁免（主线/脉冲均豁免C5）
                else:
                    return ("vetoed_cond_5", f"均线死叉: {detail} (豁免需总分≥{C5_EXEMPT_SCORE})")

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
        sector_kline = raw.get("SectorKLine", None)  # v2.4: 板块指数历史K线
    else:
        stocks = raw
        sector_data = None
        sector_fund_flow = None
        sector_kline = None
    print(f"加载 {len(stocks)} 只股票数据\n")

    # 计算板块动量（优先使用东方财富真实市场数据）
    sector_phases = compute_sector_phases(stocks, sector_data, sector_fund_flow)
    for ind, info in sorted(sector_phases.items(), key=lambda x: x[1]["money_bonus"], reverse=True):
        bn = info["money_bonus"]
        sign = "+" if bn >= 0 else ""
        cnt = f"{info['count']}只" if info['count'] > 0 else "市场数据"
        print(f"  板块 {ind:8s} | {info['phase']:5s} | 涨幅{info['avg_chg']:+.2f}% 换手{info['avg_turn']:.2f}% | 资金面{sign}{bn}分 ({cnt})")

    # v2.4: 计算板块趋势持续性（白皮书 §二十七）
    sector_trends = compute_sector_trend(sector_kline, sector_phases)
    if sector_trends:
        print(f"\n板块趋势持续性 (基于板块历史K线):")
        for ind, info in sorted(sector_trends.items(), key=lambda x: x[1]["trend_score"], reverse=True)[:10]:
            main_line = "★主线" if info["is_long_term_main_line"] else "  轮动"
            kline_flag = "有" if info.get("sector_kline_available") else "无"
            print(f"  {main_line} {ind:8s} | 持续性{info['trend_score']}分 | K线:{kline_flag}")
    else:
        print(f"\n板块趋势持续性: 无 SectorKLine 数据，SectorTrendMap 置空")

    passed = []
    vetoed = []

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
        sector_info = get_sector_info(s.get("Industry", ""))
        sector_trend_info = get_sector_trend_info(s.get("Industry", ""))  # v2.4

        # === 数据质量标签 (白皮书 §三十二) ===
        s["DataQuality"] = assess_data_quality(s)

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

        # Phase C: 条件否决（传入板块相位+趋势用于双层判断v2.4）
        veto = check_conditional_vetoes(s, scores, sector_phases, sector_trends)
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

    # v2.4: 板块趋势持续性（输出以 sector_code 为键，含 daily_details）
    sector_trend_map = {}
    for ind, info in sector_trends.items():
        code = info.get("sector_code", ind)
        sector_trend_map[code] = {
            "sector_code": code,
            "sector_name": info.get("sector_name", ind),
            "trend_score": info["trend_score"],
            "is_long_term_main_line": info["is_long_term_main_line"],
            "sector_kline_available": info.get("sector_kline_available", False),
            "daily_details": info.get("daily_details", {})
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
            # 技术指标（供报告生成使用）
            "MA5": s.get("MA5"), "MA10": s.get("MA10"), "MA20": s.get("MA20"),
            "RSI": s.get("RSI"), "MACD_Status": s.get("MACD_Status", ""),
            "VolRatio": s.get("VolRatio"),
            "VolumePercentile": s.get("VolumePercentile"),
            "PathTag": s.get("PathTag", "震荡"),
            "TechAnalysis": s.get("TechAnalysis", ""),
            "SectorPhase": s.get("SectorPhase", "")
        } for s in passed[:25]],  # 限制推荐不超过25只
        "AllStocks": passed,  # 仅含通过股
        "VetoedStocks": [{  # v2.4.1: VetoedStocks供内部审计用，不再在HTML报告中展示
            "Code": s["Code"], "Name": s["Name"],
            "Industry": s.get("Industry", ""),
            "TotalScore": s["TotalScore"],
            "VetoStatus": s.get("VetoStatus", ""),
            "VetoReason": s.get("VetoReason", ""),
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
            "SectorPhase": s.get("SectorPhase", "")
        } for s in vetoed]
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8-sig") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"{'='*50}")
    print(f"否决结果:")
    print(f"  通过: {len(passed)} 只 ({output['Summary']['PassRate']})")
    print(f"  否决: {len(vetoed)} 只")

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
    print("Done")


if __name__ == "__main__":
    main()
