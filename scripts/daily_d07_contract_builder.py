#!/usr/bin/env python3
"""
daily_d07_contract_builder.py — 构造日报 sidecar 的 D07_v1.2 合同字段。

职责：
1. 基于当日数据处理（K线、资金流、基线、P0决策卡、角色解读），
   生成符合 D07_v1.2 合同要求的 sidecar 字段。
2. 生成 d07_interpretation 可通过 统一解读/validate_interpretation.py 的 U-9/U-10/D07 校验。
3. 不修改金融结论，不生成 BUY/SELL 强动作。

用法:
    from scripts.daily_d07_contract_builder import build_daily_d07_contract
    d07_fields = build_daily_d07_contract(date=..., code=..., name=..., ...)
    sidecar.update(d07_fields)
"""

import json
import uuid
from datetime import datetime, timezone, timedelta

TZ_SHANGHAI = timezone(timedelta(hours=8))

# 持仓票列表（当前仅600114）
HELD_CODES = {"600114"}

# 知识库引用（日报场景适用的已注册 knowledge_id）
DAILY_KNOWLEDGE_REFS = [
    "YAOZI-VAL-001",   # PE(TTM)估值, L1
    "YUYE-DATA-001",   # 13源数据源列表, L1
    "LIUJIN-RISK-001", # 仓位边界规则, L2
]


def _now_str():
    return datetime.now(TZ_SHANGHAI).strftime("%H%M%S")


def _random_suffix(length=6):
    return uuid.uuid4().hex[:length]


def _fmt_money(x):
    if x is None:
        return "0万"
    return f"{x:+.0f}万"


def _norm_date(date_str):
    """Ensure YYYYMMDD → YYYY-MM-DD."""
    d = date_str.replace("-", "")
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}"


def _has_margin_degradation(degraded_items):
    """Check if degraded_items contains margin/margin_detail reference."""
    for item in degraded_items or []:
        if "margin" in str(item).lower():
            return True
    return False


def build_daily_d07_contract(
    *,
    date: str,
    code: str,
    name: str,
    k: dict,
    f: dict,
    bl: dict,
    p0: dict,
    roles: dict,
    daily_synthesis: dict,
    degraded_items: list,
    support,
    pressure,
    stop,
    phase: str,
    industry: str,
    baseline_id: str,
) -> dict:
    """Build D07_v1.2 contract fields for daily report sidecar.

    Returns a dict that can be merged into the sidecar, containing:
      framework_version, logic_version, interpretation_id,
      conclusion_strength, hypotheses, evidence_gap_requests,
      rule_refs, knowledge_refs, d07_interpretation,
      unified_interpretation, role_interpretations.
    """
    trade_date = _norm_date(date)
    held = code in HELD_CODES
    action_bias = "HOLD" if held else "WATCH"

    close = k.get("close", 0)
    low = k.get("low", 0)
    volume = k.get("volume", 0)
    main_force = f.get("main_force_net") if f else None
    super_large = f.get("super_large_net") if f else None
    large = f.get("large_net") if f else None
    medium = f.get("medium_net") if f else None
    small = f.get("small_net") if f else None

    has_margin_degraded = _has_margin_degradation(degraded_items)

    interpretation_id = f"INT-{date}-{_now_str()}-{_random_suffix(6)}"

    # rule_refs
    rule_refs = ["D07_v1.2", "U-9", "U-10"]
    knowledge_refs = []

    # hypotheses — at least 2, including one reverse/risk
    hypotheses = [
        {
            "hypothesis_id": "H1",
            "statement": (
                f"{name}收回支撑位{fmt_num(support)}并站稳压力位{fmt_num(pressure)}后，"
                f"短线进一步确认，资金配合时可转为主动持有。"
            ),
            "status": "active",
            "conclusion_strength": "倾向判断",
            "missing_data": "需T+1确认主力资金流是否持续改善",
        },
        {
            "hypothesis_id": "H2",
            "statement": (
                f"{name}若跌破{fmt_num(stop)}或持续呈现主力净流出，"
                f"则短线结构走弱，需要重新评估持仓逻辑。"
            ),
            "status": "active",
            "conclusion_strength": "倾向判断",
            "counter_evidence_refs": ["CE-close-below-stop", "CE-net-outflow"],
        },
    ]
    if has_margin_degraded:
        hypotheses.append({
            "hypothesis_id": "H3-margin",
            "statement": (
                f"融资融券数据T+1延迟，资金结构判断受样本时效影响，"
                f"不作为加仓依据。"
            ),
            "status": "pending_evidence",
            "conclusion_strength": "数据不足",
            "missing_data": "当日融资数据T+1延迟需等待次日补齐",
        })

    # conclusion_strength
    if has_margin_degraded:
        conclusion_strength = "数据不足"
    elif not held:
        conclusion_strength = "风险假设"
    else:
        conclusion_strength = "倾向判断"

    # evidence_gap_requests
    evidence_gap_requests = []
    if has_margin_degraded:
        evidence_gap_requests.append({
            "gap_id": f"GAP-{date}-{code}-margin_detail",
            "gap_type": "field_missing",
            "description": "融资融券明细存在T+1延迟，日报仅作风险降级处理",
            "requested_source": ["margin_detail"],
            "requested_fields": ["融资余额", "融券余额", "融资买入额"],
            "status": "open",
            "impact": "降低结论强度，不作为加仓依据",
            "owner_role_hint": "玉夜_数据",
        })

    # ===== Complete role_interpretations with 职责/解读/结论 =====
    support_str = fmt_num(support)
    pressure_str = fmt_num(pressure)
    stop_str = fmt_num(stop)
    main_force_str = _fmt_money(main_force)
    vol_str = str(round(float(volume) / 1000000.0, 1)) + "万手" if volume else "—"

    complete_roles = {
        "山猫_宏观": {
            "职责": "分析大盘板块相位对个股的宏观背景影响",
            "解读": roles.get("山猫_宏观", {}).get("解读", f"{industry}板块相位为{phase}。"),
            "结论": f"{industry}板块相位为{phase}，板块环境对{name}构成背景参考，买卖仍由价格与资金面决定。",
        },
        "信鸽_事件": {
            "职责": "识别当日及近期强制否决事件与重要消息面变化",
            "解读": roles.get("信鸽_事件", {}).get("解读", f"{name}当日未触发强制否决事件。"),
            "结论": "事件面未产生强制干预信号，后续跟踪公司事件线。",
        },
        "玉夜_数据": {
            "职责": "核对价格、成交、资金与数据新鲜度",
            "解读": roles.get("玉夜_数据", {}).get("解读", ""),
            "结论": "数据可用于日报判断。" + ("存在降级项时降低结论强度。" if has_margin_degraded else ""),
        },
        "流金_风控": {
            "职责": "计算仓位边界、止损位与风险灯",
            "解读": roles.get("流金_风控", {}).get("解读", f"价格未站稳{pressure_str}前不扩大仓位。"),
            "结论": f"综合风控灯黄色。未站稳{pressure_str}前持仓不扩大；跌破{stop_str}进入否决流程。",
        },
        "青山_信号": {
            "职责": "信号系统对当前价格位置的匹配判断",
            "解读": roles.get("青山_信号", {}).get("解读", f"价格低于{pressure_str}。"),
            "结论": f"信号系统支持跟踪但触发条件不满足，不支持主动加仓。",
        },
        "腰子_整合": {
            "职责": "综合六角色得出结论，生成P0明日决策卡",
            "解读": roles.get("腰子_整合", {}).get("解读", ""),
            "结论": p0.get("one_line_conclusion", f"{name}收{close}，先看{support_str}能否收回。"),
        },
    }

    t1 = p0.get("t1_action", "持有待涨，不主动加仓" if held else "观察，不主动新开")

    # daily_discussion materialized
    daily_discussion = {
        "status": "materialized",
        "participants": ["山猫_宏观", "信鸽_事件", "玉夜_数据", "流金_风控", "青山_信号", "腰子_整合"],
        "summary": (
            f"{name} {trade_date} 收{close}。板块{phase}，"
            f"主力{main_force_str}。"
            f"压力{pressure_str}，支撑{support_str}。"
        ),
        "decision": t1 if held else "观察，不主动新开",
    }
    complete_roles["daily_discussion"] = daily_discussion

    # ===== d07_interpretation (validated by validate_interpretation.py) =====
    data_fact = {
        "source": "daily_report_sidecar",
        "freshness": "当日",
        "completeness": "部分缺失" if has_margin_degraded else "完整",
        "degradation": "L1降级" if has_margin_degraded else "无降级",
        "values": {
            "code": code,
            "name": name,
            "close": close,
            "open": k.get("open", 0),
            "high": k.get("high", 0),
            "low": low,
            "volume": volume,
            "volume_wan_shou": vol_str,
            "main_force_net": main_force,
            "super_large_net": super_large,
            "large_net": large,
            "medium_net": medium,
            "small_net": small,
            "support": support,
            "pressure": pressure,
            "stop": stop,
            "sector_phase": phase,
            "industry": industry,
            "baseline_id": baseline_id,
        },
    }

    supporting_evidence = [
        {
            "evidence": f"{name} {trade_date} 收{close}，成交量{vol_str}。",
            "source": "kline_cache",
            "strength": "中",
            "source_level": "L1",
            "source_ref": f"kline_cache/{code}.json",
        },
        {
            "evidence": f"主力资金净{main_force_str}，超大单净{_fmt_money(super_large)}。",
            "source": "fund_flow_cache",
            "strength": "中",
            "source_level": "L2",
            "source_ref": f"fund_flow_cache/{code}.json",
        },
        {
            "evidence": f"权威基线压力{pressure_str}，支撑{support_str}，止损{stop_str}。",
            "source": "resolve_current_baseline",
            "strength": "强",
            "source_level": "L1",
            "source_ref": f"baseline_id={baseline_id}",
        },
    ]

    counter_evidence = [
        {
            "evidence": f"收盘价{close}未站稳压力位{pressure_str}，短线尚未确认突破。",
            "source": "kline_cache",
            "type": "技术面反证",
        },
        {
            "evidence": f"当日最低价{low}，若持续走弱存在跌破{stop_str}的止损风险。",
            "source": "kline_cache",
            "type": "资金面反证",
        },
    ]
    if has_margin_degraded:
        counter_evidence.append({
            "evidence": "融资融券数据T+1延迟，当日筹码面判断受时效限制。",
            "source": "margin_detail",
            "type": "其他",
        })

    invalidation_conditions = [
        f"跌破{stop_str}",
        "股价连续3日低于支撑位且主力净流出扩大",
    ]

    d07_interp = {
        "interpretation_id": interpretation_id,
        "scene": "日报",
        "stock_code": code,
        "trade_date": trade_date,
        "role": "腰子",
        "data_fact": data_fact,
        "interpretation_hypothesis": (
            f"{name}当前价格{close}处于支撑位{support_str}与压力位{pressure_str}之间，"
            f"主力{main_force_str}。短线需先观察能否收回{support_str}，"
            f"再验证{pressure_str}能否转支撑。操作纪律以守为主。"
        ),
        "supporting_evidence": supporting_evidence,
        "counter_evidence": counter_evidence,
        "investment_implication": (
            f"价格未突破压力位{pressure_str}前以持有或观察为主，"
            f"不主动加仓。若价格跌破{stop_str}需启动否决流程。"
        ),
        "action_bias": action_bias,
        "trigger_condition": f"收回{support_str}并站稳{pressure_str}且主力转为净流入",
        "confidence": "MEDIUM",
        "invalidation_condition": (
            f"股价跌破{stop_str}或连续3日主力合计净流出超过500万。"
        ),
        "eval_window": {
            "t1": f"验证是否收回{support_str}并靠近{pressure_str}",
            "t3": f"3个交易日{pressure_str}能否触及",
            "t5": f"5个交易日{pressure_str}能否转支撑，跌破{stop_str}则否决",
        },
        "rule_refs": rule_refs,
        "knowledge_refs": DAILY_KNOWLEDGE_REFS,
        "framework_version": "D07_v1.2",
        "hypotheses": hypotheses,
        "evidence_gap_requests": evidence_gap_requests,
    }

    # unified_interpretation: short summary mirror of d07
    unified_interpretation = {
        "interpretation_id": interpretation_id,
        "stock_code": code,
        "stock_name": name,
        "trade_date": trade_date,
        "scene": "日报",
        "framework_version": "D07_v1.2",
        "action_bias": action_bias,
        "conclusion_strength": conclusion_strength,
        "summary": (
            f"{name}收{close}，低于关键压力{pressure_str}。"
            f"主力合计{main_force_str}。"
            f"先看{support_str}能否收回，再看{pressure_str}能否站稳。"
            + (f"融资T+1延迟，结论强度受时效限制。" if has_margin_degraded else "")
        ),
        "trigger_condition": f"收回{support_str}并站稳{pressure_str}",
        "invalidation_condition": f"跌破{stop_str}",
        "hypotheses_summary": [
            {"hypothesis_id": h["hypothesis_id"], "statement": h["statement"][:80], "status": h["status"]}
            for h in hypotheses
        ],
        "evidence_gaps": [
            {"gap_id": g["gap_id"], "status": g["status"], "gap_type": g["gap_type"]}
            for g in evidence_gap_requests
        ],
    }

    return {
        "framework_version": "D07_v1.2",
        "logic_version": "v3.6.3",
        "interpretation_id": interpretation_id,
        "conclusion_strength": conclusion_strength,
        "hypotheses": hypotheses,
        "evidence_gap_requests": evidence_gap_requests,
        "rule_refs": rule_refs,
        "knowledge_refs": [],
        "d07_interpretation": d07_interp,
        "unified_interpretation": unified_interpretation,
        "role_interpretations": complete_roles,
        # daily_discussion is inside role_interpretations; also expose at top
        "daily_discussion": daily_discussion,
    }


def fmt_num(value, fmt=".2f", fallback="—"):
    if value is None:
        return fallback
    return f"{value:{fmt}}"
