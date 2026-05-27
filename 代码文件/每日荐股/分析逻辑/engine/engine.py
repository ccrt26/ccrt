#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""铁律量化 · 评分引擎 — 主入口 + 编排 + 历史记录"""
import json, math, os, sys
from datetime import date, datetime, timedelta
from collections import Counter, defaultdict

from . import (
    ROOT, DATA_FILE, OUTPUT_FILE, FINAL_FILE, THEME_WHITELIST_FILE, HISTORY_FILE,
    SPECIAL_STOCK_EXEMPTIONS, EASTMONEY_TO_BROAD_INDUSTRY, BROAD_TO_EASTMONEY,
    THEME_CLASSIFICATION, COMMODITY_TO_SECTOR, STABLE_VALUE_PE_RANGE,
    PE_ABSOLUTE_THRESHOLD, PE_COND_THRESHOLD,
    PE_COND_EXEMPT_SCORE, C3_EXEMPT_SCORE, C5_EXEMPT_SCORE, FIELD_SOURCE_MAP,
)

# 交叉导入:
from .veto import _get_v5_threshold, check_absolute_vetoes, check_conditional_vetoes, detect_market_state
from .scores import compute_scores
from .sector import compute_sector_phases, compute_sector_trend

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


# ----- v1.3 证据等级加载 (深度分析方法论§零.7) -----
def load_evidence_levels(db_path):
    """从 events_db.json 加载每只股票的最高证据等级 (近90天MAX聚合)
    返回: dict {code: {"max_level": str, "track": str, "upgrade": bool}}
    """
    if not os.path.exists(db_path):
        return {}
    try:
        with open(db_path, "r", encoding="utf-8") as f:
            events = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}

    level_order = {"L4": 0, "L3": 1, "L2": 2, "L1": 3}
    cutoff = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")

    result = {}
    for e in events:
        code = e.get("code", "")
        level = e.get("evidence_level")
        if not level or level not in level_order:
            continue
        if e.get("fetch_date", "") < cutoff:
            continue
        if code not in result or level_order[level] > level_order[result[code]["max_level"]]:
            result[code] = {
                "max_level": level,
                "track": e.get("concept_track", ""),
                "upgrade": e.get("evidence_upgrade", False),
            }
    return result


# ----- v2.9 路线二 阶段A: 评分历史落库 -----
def append_history(stocks, sector_phase_map, run_date=None):
    """每日评分完成后，将分项得分追加到 score_history.jsonl。
    目标变量 (ret_t1/t3/t5) 设为 null，由次日 backfill_returns.py 回填。
    """
    if run_date is None:
        run_date = date.today().strftime("%Y-%m-%d")

    # P0 防卫: 周末/非交易日拒绝写入
    try:
        dt = datetime.strptime(run_date, "%Y-%m-%d")
        if dt.weekday() >= 5:  # Saturday=5, Sunday=6
            print(f"[History] {run_date} is weekend, skipping score_history append")
            return
    except ValueError:
        pass

    # 构建双重去重索引: (date, code) + 内容指纹
    existing_codes = set()       # 当日code去重
    content_fingerprints = {}    # code → set of (price, score, change_pct)
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    code = rec.get("code", "")
                    rec_date = rec.get("date", "")
                    # 当日去重
                    if rec_date == run_date:
                        existing_codes.add(code)
                    # 内容指纹 (防同一份数据被不同日期重复写入)
                    fp = (rec.get("price"), rec.get("TotalScore"), rec.get("change_pct"))
                    if code not in content_fingerprints:
                        content_fingerprints[code] = set()
                    content_fingerprints[code].add(fp)
                except json.JSONDecodeError:
                    pass

    written = 0
    skipped_fp = 0
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        for s in stocks:
            code = s.get("Code", "")
            if code in existing_codes:
                continue  # 当日已记录

            # 内容指纹检查: 同code+同price+同score+同涨跌幅=同一份源数据
            fp = (s.get("Price", 0), s.get("TotalScore", 0), s.get("ChangePct", 0))
            if fp in content_fingerprints.get(code, set()):
                skipped_fp += 1
                continue

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
                # v2026-05-24 P0: PE(TTM)透明化 + 估值指标持久化
                "pe_source": s.get("PE_Source", ""),
                "pe_ttm": s.get("PE_TTM", 0),
                "ttm_eps": s.get("EPS", 0),
                "peg": s.get("PEG"),
                "pb": s.get("PB"),
                "ps": s.get("PS"),
                "car5": s.get("CAR5"),
                "eps_growth": s.get("EPS_Growth"),
                "growth_source": s.get("GrowthSource", ""),
                "phase_multiplier": s.get("PhaseMultiplier", 1.0),
                "theme_path": s.get("ThemePath", ""),
                "veto_status": s.get("VetoStatus", "passed"),
                # P0a/P0b/P1a (2026-05-26)
                "breakthrough_type": s.get("_BreakthroughType"),
                "c8_penalty": s.get("_C8_Penalty"),
                "c8_bonus": s.get("_C8_Bonus"),
                "industry_benchmark": s.get("IndustryBenchmark"),
                "adx14": s.get("ADX14"),
                "bb_upper": s.get("BB_Upper"),
                "bb_lower": s.get("BB_Lower"),
                "obv": s.get("OBV"),
                "ret_t1": None, "ret_t3": None, "ret_t5": None,
                "ret_t1_vs_market": None
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            written += 1
        f.flush()
        os.fsync(f.fileno())

    print(f"[History] {run_date}: appended {written} records to score_history.jsonl "
          f"(skipped {len(existing_codes)} date-dupes, {skipped_fp} content-dupes)")

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
    attenuation_file = os.path.join(ROOT, "代码文件", "每日荐股", "data_cache", "sector_trend_history.json")
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

    # v1.3: 加载证据等级→评分联动数据
    events_db = os.path.join(ROOT, "重点股票", "消息面数据", "events_db.json")
    evidence_map = load_evidence_levels(events_db)
    if evidence_map:
        print(f"证据等级映射: {len(evidence_map)} 只股票有有效证据数据")
    else:
        print("证据等级映射: 无有效证据数据 (events_db不存在/空/无有效事件)")

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

        # v1.3: 证据等级→评分联动 (深度分析方法论§零.7)
        evidence_info = evidence_map.get(code, None) if evidence_map else None

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
        scores, tech_info = compute_scores(s, sector_info, sector_trend_info, evidence_info)
        s.update(scores)

        # Phase B2: 突破性质分类 (2026-05-26 P0b) [L2实验性]
        from .scores import classify_breakthrough_nature
        bt_type = classify_breakthrough_nature(s, scores)
        s["_BreakthroughType"] = bt_type

        # Phase C: 条件否决（v2.7: +D.1市场自适应参数 + C8突破性质）
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

    # 生成 data_final.json（从 scored 的 passed 股票中提取最终推荐列表）
    FINAL_KEYS = ['PE', 'MktCap', 'Name', 'TurnoverRate', 'Amplitude', 'TotalScore',
                  'S_News', 'S_Tech', 'Industry', 'S_Base', 'ChangePct', 'S_Fund',
                  'Price', 'Volume', 'S_Risk', 'Code', 'S_Money']
    final_stocks = []
    for s in passed:
        entry = {k: s[k] for k in FINAL_KEYS if k in s}
        final_stocks.append(entry)
    with open(FINAL_FILE, "w", encoding="utf-8") as f:
        json.dump(final_stocks, f, ensure_ascii=False, indent=2)
    print(f"输出: {FINAL_FILE} ({len(final_stocks)} 只)")

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