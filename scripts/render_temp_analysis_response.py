#!/usr/bin/env python3
"""Render a human-readable temporary-analysis response from a gated brief."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_temp_analysis_brief_gate import check_brief, load_json, DEFAULT_SCHEMA, DEFAULT_CONTRACT


STATE_LABELS = {
    "normal_fluctuation": "正常波动",
    "strength_confirmation": "走强确认",
    "false_breakout": "假突破风险",
    "breakdown_weakness": "破位走弱",
    "event_driven": "事件驱动",
    "data_insufficient": "数据不足",
}

ACTION_LABELS = {
    "WATCH": "观察",
    "HOLD": "持有",
    "REDUCE": "降低风险仓位",
    "EXIT": "退出",
    "CONDITIONAL_ADD": "满足条件再加",
    "T_CONDITION": "只在条件满足时做T",
    "NEUTRAL": "中性等待",
}


def visible_data_warning(brief):
    dq = brief.get("data_quality", {})
    missing = [k for k, v in dq.items() if v == "missing"]
    if not missing:
        return ""
    return "数据提示：当前缺少 " + "、".join(missing) + "，所以结论不能强判。"


def current_read(brief):
    state = brief.get("intraday_state")
    action = brief.get("action_bias")
    strength = brief.get("conclusion_strength")
    if state == "normal_fluctuation":
        return "现在更像是关键区间内的正常盘中波动，暂时没有证据支持追涨或恐慌处理。"
    if state == "false_breakout":
        return "现在的重点不是涨了多少，而是冲高能不能站稳；如果量能和关键位不确认，容易变成假突破。"
    if state == "breakdown_weakness":
        return "现在风险重点在下方失效位；跌破后不能快速收回，就要优先控制回撤。"
    if state == "event_driven":
        return "现在需要先确认异动原因和持续量能，不能把单次刺激直接当成趋势确认。"
    if state == "data_insufficient":
        return "现在数据不足，不能给强动作，只能先等关键行情、市场或基线信息补齐。"
    return f"当前结论强度为{strength}，操作倾向为{ACTION_LABELS.get(action, action)}。"


def counter_points(brief):
    levels = brief.get("key_levels", {})
    confirm = levels.get("confirm_above", "上方确认位")
    invalid = levels.get("invalidate_below", "下方失效位")
    ref = levels.get("intraday_reference", "盘中参考线")
    state = brief.get("intraday_state")

    points = [
        f"如果重新站稳 {confirm}，并且成交配合，偏弱或谨慎判断要降级。",
        f"如果跌破 {invalid} 后 15 分钟仍收不回，风险要升级。",
        f"如果始终围绕 {ref} 上下窄幅波动，就不宜把它解读成趋势变化。",
        "如果板块和指数同步转强，个股冲高的可信度会提高。",
    ]
    if state in {"false_breakout", "event_driven"}:
        points.append("如果只是消息或盘口刺激，但没有持续成交，仍然不适合追。")
    elif state == "breakdown_weakness":
        points.append("如果跌破后快速收回并放量，破位判断要重新评估。")
    else:
        points.append("如果突然放量突破并站稳确认位，正常波动判断要上调。")
    return points[:5]


def operation_plan(brief):
    action = brief.get("action_bias")
    levels = brief.get("key_levels", {})
    confirm = levels.get("confirm_above", "上方确认位")
    invalid = levels.get("invalidate_below", "下方失效位")
    ref = levels.get("intraday_reference", "盘中参考线")

    if action == "REDUCE":
        return [
            f"已持仓：跌破 {invalid} 且不能收回时，优先降低风险仓位。",
            f"空仓：不要在 {invalid} 下方抢反弹，先等重新收回。",
            f"冲高：如果只是回抽 {ref} 附近不过，不当作转强。",
            f"止错：重新站回 {confirm} 后，降低仓位动作暂停复核。",
            "复核：午盘和尾盘各复查一次，避免被单根分时误导。",
        ]
    if action in {"WATCH", "NEUTRAL"}:
        return [
            f"空仓：不急着追，等站稳 {confirm} 或回踩确认。",
            f"已持仓：先观察 {ref} 是否守住，别因为一段拉升改变计划。",
            f"冲高：没有量能和站稳动作时，冲高只看作观察信号。",
            f"转弱：跌破 {invalid} 且不能收回，转入风险处理。",
            "复核：10:30、午盘、尾盘三个时间点重新判断。",
        ]
    if action == "HOLD":
        return [
            f"已持仓：维持原计划，核心看 {ref} 和 {invalid}。",
            f"空仓：不追高，等回踩不破或站稳 {confirm} 再说。",
            f"冲高：接近 {confirm} 但站不稳，不当作买点。",
            f"转弱：跌破 {invalid} 且不能收回，持有判断失效。",
            "复核：午盘看量能，尾盘看是否仍在关键区间内。",
        ]
    return [
        f"条件成立前不动作，先看 {confirm} 和 {invalid}。",
        "已持仓按触发条件处理，不做情绪化加减。",
        "空仓只等确认，不抢没有边界的位置。",
        "冲高看站稳，回落看承接。",
        "尾盘统一复核，不把盘中噪声当结论。",
    ]


def answer_question(question, brief):
    q = question or ""
    action = brief.get("action_bias")
    levels = brief.get("key_levels", {})
    confirm = levels.get("confirm_above", "上方确认位")
    invalid = levels.get("invalidate_below", "下方失效位")

    if any(word in q for word in ["追", "买", "加仓"]):
        if action == "CONDITIONAL_ADD":
            return f"不是直接追，只有站稳 {confirm} 且量能确认后，才考虑条件加仓。"
        return f"现在不建议追，至少要等站稳 {confirm} 或回踩确认。"
    if any(word in q for word in ["卖", "减", "降仓", "走不走"]):
        if action in {"REDUCE", "EXIT"}:
            return f"如果跌破 {invalid} 且不能收回，应按风险处理执行。"
        return f"现在还不是必须卖的信号，重点看 {invalid} 是否失守。"
    if any(word in q for word in ["破", "跌破", "怎么办"]):
        return f"跌破 {invalid} 后先看能否快速收回；收不回就按风险升级处理。"
    return "当前先按上面的状态和触发条件处理；你可以继续追问追不追、卖不卖、破位怎么办。"


def render_response(brief, question=""):
    title = f"临时分析｜{brief.get('stock_name', '')} {brief.get('stock_code', '')}".strip()
    state = STATE_LABELS.get(brief.get("intraday_state"), brief.get("intraday_state", "未知"))
    action = ACTION_LABELS.get(brief.get("action_bias"), brief.get("action_bias", "未知"))
    strength = brief.get("conclusion_strength", "")
    levels = brief.get("key_levels", {})
    warning = visible_data_warning(brief)

    lines = [
        title,
        "",
        f"1. 一句话判断：现在属于【{state}】，结论强度【{strength}】，操作倾向【{action}】。",
    ]
    if warning:
        lines.extend(["", warning])

    lines.extend([
        "",
        "2. 现在怎么看",
        current_read(brief),
        "",
        "3. 关键价位",
        f"- 上方确认位：{levels.get('confirm_above', '待确认')}",
        f"- 下方失效位：{levels.get('invalidate_below', '待确认')}",
        f"- 盘中参考线：{levels.get('intraday_reference', '待确认')}",
        "",
        "4. 哪些情况说明判断可能错了",
    ])
    lines.extend([f"- {item}" for item in counter_points(brief)])
    lines.extend(["", "5. 操作计划"])
    lines.extend([f"- {item}" for item in operation_plan(brief)])
    lines.extend([
        "",
        "6. 针对你的问题",
        answer_question(question, brief),
        "",
        "7. 下次复核点",
        "10:30、午盘、尾盘；或者价格先触发上方确认位/下方失效位时提前复核。",
    ])
    return "\n".join(lines) + "\n"


def validate_brief(brief):
    schema = load_json(DEFAULT_SCHEMA)
    contract = load_json(DEFAULT_CONTRACT)
    return check_brief(brief, schema, contract)


def main():
    parser = argparse.ArgumentParser(description="Render temporary-analysis decision response")
    parser.add_argument("--brief", required=True)
    parser.add_argument("--question", default="")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    try:
        brief = load_json(args.brief)
        overall, findings = validate_brief(brief)
        if overall != "PASS":
            print(json.dumps({"status": "BLOCK", "gate_overall": overall, "findings": findings}, ensure_ascii=False, indent=2))
            return 2
        text = render_response(brief, args.question)
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(json.dumps({"status": "PASS", "output": str(out), "gate_overall": overall}, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "BLOCK", "error_type": type(exc).__name__, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
