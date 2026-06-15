#!/usr/bin/env python3
"""Generate TemporaryAnalysisBrief from structured intraday context.

This is the Step 4 minimal generator. It does not fetch live data, does not
write daily/deep reports, and does not touch trade executors.
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts/check_temp_analysis_brief_gate.py"

STATE_NORMAL = "normal_fluctuation"
STATE_FALSE_BREAKOUT = "false_breakout"
STATE_BREAKDOWN = "breakdown_weakness"
STATE_EVENT = "event_driven"
STATE_DATA_INSUFFICIENT = "data_insufficient"


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, payload):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


def now_query_time():
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz).replace(microsecond=0).isoformat()


def as_float(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_identity(ctx):
    stock_code = str(ctx.get("stock_code", "")).strip()
    stock_name = str(ctx.get("stock_name", "")).strip()
    if not re.fullmatch(r"[0-9]{6}", stock_code):
        raise ValueError("stock_code must be six digits")
    if not stock_name:
        raise ValueError("stock_name must be non-empty")
    return {"stock_code": stock_code, "stock_name": stock_name}


def data_quality(ctx):
    return {
        "current_quote": "present" if isinstance(ctx.get("current_quote"), dict) else "missing",
        "market_context": "present" if isinstance(ctx.get("market_context"), dict) else "missing",
        "baseline_context": "present" if isinstance(ctx.get("baseline_context"), dict) else "missing",
        "event_context": "present" if isinstance(ctx.get("event_context"), dict) and ctx.get("event_context") else "not_applicable",
        "user_position_context": "present" if isinstance(ctx.get("user_position_context"), dict) and ctx.get("user_position_context") else "missing",
    }


def classify_state(ctx, dq):
    if dq["current_quote"] == "missing" or dq["market_context"] == "missing" or dq["baseline_context"] == "missing":
        return STATE_DATA_INSUFFICIENT

    quote = ctx.get("current_quote", {})
    event = ctx.get("event_context", {})
    pct = as_float(quote.get("change_pct"), 0.0)
    volume_ratio = as_float(quote.get("volume_ratio"), 1.0)
    above_reference = bool(quote.get("above_reference"))
    below_key = bool(quote.get("below_key_level"))
    reclaimed = bool(quote.get("reclaimed_key_level"))
    event_verified = bool(event.get("verified")) if isinstance(event, dict) else False

    if isinstance(event, dict) and event and not event_verified:
        if abs(pct) >= 3.0 or volume_ratio >= 1.8:
            return STATE_EVENT

    if below_key and not reclaimed:
        return STATE_BREAKDOWN

    if pct >= 3.0 and volume_ratio < 1.5 and not above_reference:
        return STATE_FALSE_BREAKOUT

    return STATE_NORMAL


def build_key_levels(ctx):
    baseline = ctx.get("baseline_context", {}) if isinstance(ctx.get("baseline_context"), dict) else {}
    quote = ctx.get("current_quote", {}) if isinstance(ctx.get("current_quote"), dict) else {}
    return {
        "confirm_above": str(baseline.get("confirm_above") or quote.get("intraday_high") or "待盘中确认位"),
        "invalidate_below": str(baseline.get("invalidate_below") or quote.get("intraday_vwap") or "待盘中失效位"),
        "intraday_reference": str(quote.get("intraday_reference") or quote.get("intraday_vwap") or "分时均价线")
    }


def build_hypotheses(state):
    if state == STATE_BREAKDOWN:
        return [
            {"hypothesis_id": "H1", "statement": "盘中跌破关键位且未能收回，短线风险上升。", "type": "main", "conclusion_strength": "倾向判断"},
            {"hypothesis_id": "H2", "statement": "若短时间重新站回失守价位，破位判断需要降级。", "type": "counter", "conclusion_strength": "风险假设"},
        ]
    if state in (STATE_FALSE_BREAKOUT, STATE_EVENT):
        return [
            {"hypothesis_id": "H1", "statement": "盘中异动或冲高可能缺少持续确认，存在回落风险。", "type": "main", "conclusion_strength": "风险假设"},
            {"hypothesis_id": "H2", "statement": "若事件确认且价格重新站稳高点，谨慎观察假设需要撤销。", "type": "counter", "conclusion_strength": "倾向判断"},
        ]
    if state == STATE_DATA_INSUFFICIENT:
        return [
            {"hypothesis_id": "H1", "statement": "关键数据缺失，当前不能形成可执行盘中判断。", "type": "main", "conclusion_strength": "数据不足"},
            {"hypothesis_id": "H2", "statement": "若行情、市场和基线数据补齐，可重新判断盘中状态。", "type": "counter", "conclusion_strength": "数据不足"},
        ]
    return [
        {"hypothesis_id": "H1", "statement": "当前属于正常盘中波动，尚未触发趋势或风控变化。", "type": "main", "conclusion_strength": "倾向判断"},
        {"hypothesis_id": "H2", "statement": "若跌破分时均价且不能收回，正常波动假设会转弱。", "type": "counter", "conclusion_strength": "风险假设"},
    ]


def build_counter_evidence(state):
    if state == STATE_BREAKDOWN:
        return [{"evidence": "若快速收回失守价位，说明破位可能只是盘中噪声。", "source": "current_quote", "type": "技术反证"}]
    if state in (STATE_FALSE_BREAKOUT, STATE_EVENT):
        return [{"evidence": "事件原因或持续量能未确认，不支持立即追涨。", "source": "event_or_quote", "type": "事件/量价反证"}]
    if state == STATE_DATA_INSUFFICIENT:
        return [{"evidence": "行情、市场或基线数据缺失，无法支持强动作。", "source": "data_quality", "type": "数据反证"}]
    return [{"evidence": "盘中量能没有形成明确放量上攻，暂不支持追加强动作。", "source": "current_quote", "type": "量价反证"}]


def build_gaps(ctx, state, dq):
    gaps = []
    if dq["current_quote"] == "missing":
        gaps.append({"gap_id": "GAP-CURRENT-QUOTE", "description": "current_quote 缺失。", "status": "open", "impact": "只能输出 WATCH/NEUTRAL 与 数据不足。"})
    if dq["market_context"] == "missing":
        gaps.append({"gap_id": "GAP-MARKET-CONTEXT", "description": "market_context 缺失。", "status": "open", "impact": "不能判断板块和指数相位。"})
    if dq["baseline_context"] == "missing":
        gaps.append({"gap_id": "GAP-BASELINE-CONTEXT", "description": "baseline_context 缺失。", "status": "open", "impact": "不能引用既有关键位和基线边界。"})
    event = ctx.get("event_context", {})
    if state == STATE_EVENT and isinstance(event, dict) and not event.get("verified"):
        gaps.append({"gap_id": "GAP-EVENT-UNVERIFIED", "description": "盘中事件原因未确认。", "status": "open", "impact": "结论强度限制为风险假设，不允许追涨。"})
    return gaps


def decide_action(state, dq):
    if state == STATE_DATA_INSUFFICIENT:
        return "NEUTRAL", "数据不足"
    if state == STATE_BREAKDOWN:
        if dq["user_position_context"] == "present":
            return "REDUCE", "倾向判断"
        return "WATCH", "风险假设"
    if state in (STATE_FALSE_BREAKOUT, STATE_EVENT):
        return "WATCH", "风险假设"
    return "HOLD", "倾向判断"


def build_trigger_actions(state, action, key_levels, dq):
    if action == "REDUCE":
        return [{
            "condition": f"跌破 {key_levels['invalidate_below']} 且 15 分钟不能收回",
            "action": "执行降仓防守",
            "price_range": f"{key_levels['invalidate_below']} 下方",
            "position_boundary": "仅对已持仓用户，降至预设风险仓位以内",
            "time_window": "尾盘前完成复核"
        }]
    if state in (STATE_FALSE_BREAKOUT, STATE_EVENT):
        return [{
            "condition": f"未重新站回 {key_levels['confirm_above']} 且事件或量能未确认",
            "action": "不追涨，等待回踩或事件确认",
            "price_range": "冲高回落区间",
            "position_boundary": "无持仓上下文时不给仓位比例",
            "time_window": "10:30、午盘或尾盘复核"
        }]
    if state == STATE_DATA_INSUFFICIENT:
        return [{
            "condition": "补齐行情、市场和基线数据后再判断",
            "action": "仅观察，不输出强动作",
            "price_range": "无有效价格区间",
            "position_boundary": "不调整仓位",
            "time_window": "数据补齐后复核"
        }]
    return [{
        "condition": "未跌破分时均价且量能无异常放大",
        "action": "持有观察，不新增仓位",
        "price_range": "当前关键区间内",
        "position_boundary": "维持原仓位",
        "time_window": "午盘或收盘复核"
    }]


def build_method_review(state, action):
    if action in {"REDUCE", "EXIT", "CONDITIONAL_ADD", "T_CONDITION"}:
        return {
            "role_code": "LISHI",
            "result": "PASS",
            "main_challenge": "强动作已绑定价位、时间、仓位边界，不是单点情绪判断。",
            "calibration_note": "动作只在触发条件满足时执行，未满足则保持观察。"
        }
    if state in (STATE_FALSE_BREAKOUT, STATE_EVENT):
        return {
            "role_code": "LISHI",
            "result": "WARN",
            "main_challenge": "事件或量能未确认时，不能把异动直接解释为趋势确认。",
            "calibration_note": "维持 WATCH，等待事件、量能或回踩确认。"
        }
    return {
        "role_code": "LISHI",
        "result": "NOT_REQUIRED",
        "main_challenge": "未输出强动作，暂不强制砺石审查。",
        "calibration_note": "保持观察结论，不将正常波动误判为趋势。"
    }


def build_eval_hook(state):
    if state == STATE_BREAKDOWN:
        return {"close_check": "收盘检查是否重新站回失守价位", "t1_check": "T+1 检查是否继续弱势", "t3_check": "T+3 检查降仓动作是否降低回撤"}
    if state in (STATE_FALSE_BREAKOUT, STATE_EVENT):
        return {"close_check": "收盘检查是否回落至分时均价下方", "t1_check": "T+1 检查冲高高点是否被有效收复", "t3_check": "T+3 检查异动是否演化为区间上沿"}
    return {"close_check": "收盘检查是否仍在关键区间内", "t1_check": "T+1 检查是否延续正常波动", "t3_check": "T+3 检查区间是否被突破或跌破"}


def generate_brief(ctx):
    identity = normalize_identity(ctx)
    dq = data_quality(ctx)
    state = classify_state(ctx, dq)
    action, strength = decide_action(state, dq)
    key_levels = build_key_levels(ctx)
    return {
        "scene": "临时分析",
        "framework_version": "D07_v1.2",
        "stock_code": identity["stock_code"],
        "stock_name": identity["stock_name"],
        "query_time": str(ctx.get("query_time") or now_query_time()),
        "intraday_state": state,
        "action_bias": action,
        "conclusion_strength": strength,
        "data_quality": dq,
        "key_levels": key_levels,
        "trigger_actions": build_trigger_actions(state, action, key_levels, dq),
        "hypotheses": build_hypotheses(state),
        "counter_evidence": build_counter_evidence(state),
        "evidence_gap_requests": build_gaps(ctx, state, dq),
        "method_review": build_method_review(state, action),
        "eval_hook": build_eval_hook(state),
        "non_goals_confirmed": {
            "no_daily_report": True,
            "no_deep_baseline_recalc": True,
            "no_trade_executor_write": True
        }
    }


def run_gate(path):
    proc = subprocess.run(
        [sys.executable, str(GATE), "--input", str(path), "--json"],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
    )
    return proc.returncode, proc.stdout, proc.stderr


def main():
    parser = argparse.ArgumentParser(description="Generate TemporaryAnalysisBrief")
    parser.add_argument("--input", required=True, help="structured intraday context JSON")
    parser.add_argument("--output", required=True, help="output TemporaryAnalysisBrief JSON")
    parser.add_argument("--skip-gate", action="store_true", help="write output without running gate")
    args = parser.parse_args()

    try:
        ctx = load_json(args.input)
        brief = generate_brief(ctx)
        out = write_json(args.output, brief)
    except Exception as exc:
        print(json.dumps({
            "status": "BLOCK",
            "error_type": type(exc).__name__,
            "error": str(exc)
        }, ensure_ascii=False, indent=2))
        return 2

    if args.skip_gate:
        print(json.dumps({"status": "WROTE", "output": str(out), "gate": "SKIPPED"}, ensure_ascii=False, indent=2))
        return 0

    rc, stdout, stderr = run_gate(out)
    payload = {"status": "PASS" if rc == 0 else "BLOCK", "output": str(out), "gate_returncode": rc, "gate_stdout": stdout}
    if stderr:
        payload["gate_stderr"] = stderr
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
