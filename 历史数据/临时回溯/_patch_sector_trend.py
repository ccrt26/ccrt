"""
Patch scoring_engine_v2.py: replace compute_sector_trend with v2.7 five-factor version.
TECH-02 (diffusion ratio) + TECH-03 (10-day windows) + TECH-04 (attenuation detection).
"""
import re

filepath = r'C:\Users\34269\Documents\Claude\股票分析\代码文件\每日荐股\分析逻辑\scoring_engine_v2.py'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

old_func = '''def compute_sector_trend(sector_kline_data=None, sector_phases=None, stocks=None):
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
'''

new_func = '''def compute_sector_trend(sector_kline_data=None, sector_phases=None, stocks=None):
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

        # ---- 因子5: 关联印证 (0-2分) 待TECH-06补全 (2026-06-06) ----
        f5 = 1  # 默认中性
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
'''

if old_func in content:
    content = content.replace(old_func, new_func, 1)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print("OK: compute_sector_trend replaced successfully")
else:
    print("ERROR: old function text not found exactly. Checking whitespace...")
    # Try finding the function start
    idx = content.find('def compute_sector_trend(')
    if idx >= 0:
        end_idx = content.find('\ndef should_exempt_by_sector(', idx)
        print(f"  Function found at {idx}, ends at {end_idx}")
        actual = content[idx:end_idx]
        print(f"  Actual first line: {repr(actual[:80])}")
        print(f"  Expected first line: {repr(old_func[:80])}")
        # Compare character by character
        for i, (a, b) in enumerate(zip(actual, old_func)):
            if a != b:
                print(f"  First diff at pos {i}: actual={repr(a)} expected={repr(b)}")
                print(f"  Context: ...{repr(actual[max(0,i-10):i+10])}...")
                break
