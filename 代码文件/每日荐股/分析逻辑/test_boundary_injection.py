#!/usr/bin/env python3
"""边界注入测试 — 验证拆分后engine/包对极端输入的健壮性"""
import json, os, sys, copy
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from engine.engine import main as engine_main
from engine.veto import check_absolute_vetoes, check_conditional_vetoes, detect_market_state, _get_v5_threshold
from engine.scores import compute_scores, calc_percentile
from engine.theme import classify_theme, check_theme_purity, load_industry_whitelist
from engine.technical import calc_ma, calc_rsi, calc_macd, calc_atr
from engine.sector import classify_phase, should_exempt_by_sector

PASS, FAIL = 0, 0

def test(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}  -- {detail}")

def make_stock(code="000001", name="测试", price=10.0, pe=15.0, eps=0.5, volume=50000,
               turnover=3.0, mkt_cap=100, industry="银行", kclose=None, change_pct=1.5):
    """构造测试股票数据"""
    if kclose is None:
        kclose = [price] * 60  # 60天平坦价格
    return {
        "Code": code, "Name": name, "Price": price, "PE": pe, "EPS": eps,
        "Volume": volume, "TurnoverRate": turnover, "MktCap": mkt_cap,
        "Industry": industry, "KClose": kclose, "ChangePct": change_pct,
    }

def run_tests():
    global PASS, FAIL
    PASS = FAIL = 0

    # ============================================================
    print("\n一、技术指标计算边界")
    # ============================================================

    # 1.1 空数据
    try:
        calc_ma([], 5)
        test("MA空输入不崩溃", True)
    except Exception as e:
        test("MA空输入不崩溃", False, str(e))

    # 1.2 单元素
    try:
        r = calc_ma([10.0], 5)
        test("MA单元素不崩溃", isinstance(r, list))
    except Exception as e:
        test("MA单元素不崩溃", False, str(e))

    # 1.3 全零价格
    try:
        r = calc_ma([0.0]*30, 5)
        valid = [x for x in r if x is not None]
        test("MA全零价格", all(x == 0.0 for x in valid) and len(valid) > 0)
    except Exception as e:
        test("MA全零价格", False, str(e))

    # 1.4 RSI全涨
    try:
        rising = list(range(1, 31))
        r = calc_rsi(rising)
        test("RSI全涨接近100", r[-1] > 90 if r else False)
    except Exception as e:
        test("RSI全涨接近100", False, str(e))

    # 1.5 RSI全跌
    try:
        falling = list(range(30, 0, -1))
        r = calc_rsi(falling)
        test("RSI全跌接近0", r[-1] < 10 if r else False)
    except Exception as e:
        test("RSI全跌接近0", False, str(e))

    # 1.6 MACD震荡
    try:
        osc = [10, 12, 10, 12, 10, 12]*6
        r = calc_macd(osc)
        test("MACD震荡不崩溃", "DIF" in r and "MACD" in r)
    except Exception as e:
        test("MACD震荡不崩溃", False, str(e))

    # 1.7 ATR不足周期
    try:
        prices = [10, 11, 10, 12, 10, 13, 10, 14, 10, 15, 10, 16, 10, 17]
        r = calc_atr(prices, prices, prices, period=14)
        test("ATR边界周期不崩溃", isinstance(r, list))
    except Exception as e:
        test("ATR边界周期不崩溃", False, str(e))

    # ============================================================
    print("\n二、否决体系边界 — 绝对否决(V0-V7)")
    # ============================================================

    # 2.1 ST股票直接否决
    st_stock = make_stock(code="000001", name="*ST测试")
    r, reason = check_absolute_vetoes(st_stock) or (None, None)
    test("V0: ST股票直接否决", r == "vetoed_abs_st", f"got {r}")

    # 2.2 正常股票通过
    normal = make_stock()
    r, reason = check_absolute_vetoes(normal) or (None, None)
    test("V0-V7: 正常股票全部通过", r is None, f"rejected: {reason}")

    # 2.3 PE=0 (EPS为负)
    pe0 = make_stock(pe=0, eps=-0.5)
    r, reason = check_absolute_vetoes(pe0) or (None, None)
    test("V4: PE=0且EPS<=0触发否决", r == "vetoed_abs_4", f"got {r}")

    # 2.4 PE=0 但EPS为正（豁免）
    pe0_eps_pos = make_stock(pe=0, eps=0.8)
    r, reason = check_absolute_vetoes(pe0_eps_pos) or (None, None)
    test("V4: PE=0但EPS>0不触发否决", r is None, f"got {r}: {reason}")

    # 2.5 极端PE (电子行业300)
    extreme_pe = make_stock(pe=350, industry="电子")
    r, reason = check_absolute_vetoes(extreme_pe) or (None, None)
    test("V2: PE=350(电子)触发否决", r == "vetoed_abs_2", f"got {r}")

    # 2.6 极端PE (电子行业250 未超300)
    high_pe_ok = make_stock(pe=250, industry="电子")
    r, reason = check_absolute_vetoes(high_pe_ok) or (None, None)
    test("V2: PE=250(电子)不触发否决(阈值300)", r is None, f"got {r}: {reason}")

    # 2.7 成交量为0
    zero_vol = make_stock(volume=0, turnover=0)
    r, reason = check_absolute_vetoes(zero_vol) or (None, None)
    test("V5: 成交量为0触发流动性否决", r == "vetoed_abs_5", f"got {r}")

    # 2.8 30日涨幅>50%
    surge = make_stock(price=16.0, kclose=[10.0]*31 + [16.0]*29)
    r, reason = check_absolute_vetoes(surge) or (None, None)
    test("V3: 30日涨幅60%触发否决", r == "vetoed_abs_3", f"got {r}")

    # 2.9 特殊豁免(中芯国际) — 豁免表已内置，用code=688981自动匹配
    smic = make_stock(code="688981", name="中芯国际", pe=400, industry="电子")
    r, reason = check_absolute_vetoes(smic) or (None, None)
    test("豁免: 中芯国际PE=400不触发V2", r is None, f"got {r}: {reason}")

    # ============================================================
    print("\n三、否决体系边界 — 条件否决(C1-C7)")
    # ============================================================

    scores_base = {"TotalScore": 60, "TechScore": 20, "FundScore": 20, "SentiScore": 10, "TimingScore": 10}

    # 3.1 低分触发C2(PE>80)
    high_pe_low_score = make_stock(pe=100, industry="食品饮料")
    r, reason = check_conditional_vetoes(high_pe_low_score, scores_base) or (None, None)
    test("C2: PE>80且总分60触发PE否决", r == "vetoed_cond_2", f"got {r}")

    # 3.2 高分豁免C2
    high_score = dict(scores_base, TotalScore=88)
    r, reason = check_conditional_vetoes(high_pe_low_score, high_score) or (None, None)
    test("C2豁免: PE>80但总分88不触发", r is None, f"got {r}: {reason}")

    # 3.3 MA5<MA10触发C3
    falling_ma = make_stock(price=9.0, kclose=[12.0, 11.5, 11.0, 10.5, 10.0, 9.5]*10)
    r, reason = check_conditional_vetoes(falling_ma, scores_base) or (None, None)
    # MA5 should be < MA10 due to falling prices
    test("C3: 持续下跌触发均线回踩否决", r is not None, f"got {r}: {reason}")

    # ============================================================
    print("\n四、市场状态检测边界")
    # ============================================================

    # 4.1 空股票列表
    state, mult, delta = detect_market_state([])
    test("市场状态: 空列表返回震荡", state == "震荡" and mult == 1.0 and delta == 0)

    # 4.2 单只股票
    single = [make_stock()]
    state, mult, delta = detect_market_state(single)
    test("市场状态: 单只股票返回震荡(数据不足20)", state == "震荡")

    # 4.3 全涨市场(强势)
    bull_stocks = []
    for i in range(30):
        s = make_stock(code=f"0000{i:02d}", price=12.0, kclose=[10.0]*56 + [12.0]*4)
        bull_stocks.append(s)
    state, mult, delta = detect_market_state(bull_stocks)
    test("市场状态: 全涨10%识别为强势", state == "强势", f"got {state} mult={mult}")

    # 4.4 全跌市场(弱势)
    bear_stocks = []
    for i in range(30):
        s = make_stock(code=f"0000{i:02d}", price=8.0, kclose=[10.0]*56 + [8.0]*4)
        bear_stocks.append(s)
    state, mult, delta = detect_market_state(bear_stocks)
    test("市场状态: 全跌20%识别为弱势", state == "弱势", f"got {state} mult={mult}")

    # ============================================================
    print("\n五、V5流动性阈值边界")
    # ============================================================

    t, label = _get_v5_threshold(None)
    test("V5: None→默认1500万", t == 1500)

    t, label = _get_v5_threshold(0)
    test("V5: 0→默认1500万", t == 1500)

    t, label = _get_v5_threshold(12000)
    test("V5: >1万亿→2000万", t == 2000)

    t, label = _get_v5_threshold(7000)
    test("V5: 5千-1万亿→1500万", t == 1500)

    t, label = _get_v5_threshold(3000)
    test("V5: <5千亿→1000万", t == 1000)

    # ============================================================
    print("\n六、板块分类边界")
    # ============================================================

    # 6.1 空板块列表
    try:
        from engine.sector import compute_sector_phases
        phases = compute_sector_phases([])
        test("板块相位: 空列表不崩溃", isinstance(phases, dict))
    except Exception as e:
        test("板块相位: 空列表不崩溃", False, str(e))

    # 6.2 未知行业
    unknown = make_stock(industry="未知行业123")
    r, reason = check_absolute_vetoes(unknown) or (None, None)
    test("未知行业: 不崩溃(默认PE阈值80)", r is None or "PE" in str(reason), f"got {r}: {reason}")

    # ============================================================
    print("\n七、题材分类边界")
    # ============================================================

    # 7.1 未知行业分类
    whitelist = load_industry_whitelist()
    unknown = make_stock(industry="未知行业XYZ")
    themes = classify_theme(unknown, whitelist)
    test("题材: 未知行业返回默认分类", isinstance(themes, list), f"got {themes}")

    # 7.2 空whitelist
    themes2 = classify_theme(make_stock(industry="电子"), {})
    test("题材: 空白名单不崩溃(仅行业分类)", "强成长" in themes2, f"got {themes2}")

    # ============================================================
    print("\n八、评分计算边界")
    # ============================================================

    # 8.1 calc_percentile — 边界返回None是合理的(无法计算百分位)
    test("百分位: 空列表返回None(无法计算)", calc_percentile([], 10) is None)
    test("百分位: 单元素返回None(无法计算)", calc_percentile([10], 10) is None)
    test("百分位: 最小值返回~0", abs(calc_percentile([1,2,3,4,5], 1) - 0.0) < 0.1)

    # 8.2 compute_scores最小数据 — 返回(dict, str)元组是原始设计
    try:
        min_stock = make_stock(kclose=[10.0]*5)
        result, tech_info = compute_scores(min_stock, {}, {})
        test("评分: 最小数据不崩溃且返回字典", isinstance(result, dict) and "TotalScore" in result,
             f"got {type(result)}")
    except Exception as e:
        test("评分: 最小数据不崩溃", False, str(e))

    # ============================================================
    print("\n九、特殊股票豁免边界")
    # ============================================================

    # 9.1 豁免不存在
    from engine import SPECIAL_STOCK_EXEMPTIONS
    test("豁免表: 未知股票返回空dict", SPECIAL_STOCK_EXEMPTIONS.get("999999", {}) == {})

    # 9.2 已知豁免股票存在
    test("豁免表: 中芯国际(688981)存在", "688981" in SPECIAL_STOCK_EXEMPTIONS)

    # ============================================================
    print("\n十、导入完整性检查")
    # ============================================================

    modules = [
        ("engine.__init__", ["ROOT", "DATA_FILE", "OUTPUT_FILE", "THEME_WHITELIST_FILE",
                             "SPECIAL_STOCK_EXEMPTIONS", "THEME_CLASSIFICATION",
                             "PE_ABSOLUTE_THRESHOLD", "FIELD_SOURCE_MAP"]),
        ("engine.technical", ["calc_ma", "calc_ema", "calc_rsi", "calc_macd", "calc_atr"]),
        ("engine.theme", ["classify_theme", "check_theme_purity", "score_pe_by_theme",
                          "load_industry_whitelist", "calc_sector_correlation"]),
        ("engine.sector", ["classify_phase", "calc_sector_bonus", "compute_sector_phases",
                           "compute_sector_trend", "should_exempt_by_sector"]),
        ("engine.veto", ["_get_v5_threshold", "check_absolute_vetoes",
                         "check_conditional_vetoes", "detect_market_state"]),
        ("engine.subscores", ["_score_ma_system", "_score_ma_converge", "_score_volume_price",
                              "_score_bottom_support", "_score_rsi", "_score_macd",
                              "_score_breakout_confirmation", "_score_trend_momentum"]),
        ("engine.scores", ["compute_scores", "calc_percentile", "classify_path_6features"]),
        ("engine.engine", ["main", "assess_data_quality", "append_history"]),
    ]

    for mod_name, expected_attrs in modules:
        mod = __import__(mod_name, fromlist=expected_attrs)
        for attr in expected_attrs:
            has = hasattr(mod, attr)
            test(f"导入: {mod_name}.{attr}", has, f"missing in {mod_name}")

    # ============================================================
    print(f"\n{'='*50}")
    print(f"结果: {PASS} passed, {FAIL} failed, {PASS+FAIL} total")
    if FAIL > 0:
        print(f"*** {FAIL} boundary tests FAILED! ***")
    else:
        print(f"All {PASS} boundary tests PASSED")
    print(f"{'='*50}")
    return FAIL == 0

if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
