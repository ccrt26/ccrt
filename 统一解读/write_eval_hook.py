#!/usr/bin/env python3
"""
eval_hook 写入器 — 双对象格式支持，禁止 UNKNOWN
用法: python3 write_eval_hook.py --interpretation <JSON>
"""

import json, sys, os, uuid
from datetime import datetime, date, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STORE_DIR = os.path.join(SCRIPT_DIR, "eval_hooks", "store")

os.makedirs(STORE_DIR, exist_ok=True)


def extract_interpretation(data):
    """提取原始解释对象，支持双对象格式"""
    # 格式1: 纯原始解释对象
    if "data_fact" in data and "interpretation_id" in data:
        return data
    # 格式2: 双对象 {interpretation: ..., unified_interpretation: ...}
    if "interpretation" in data:
        inner = data["interpretation"]
        if isinstance(inner, dict) and "data_fact" in inner:
            return inner
    # 格式3: 只有 unified_interpretation → 拒绝
    if "unified_interpretation" in data and "interpretation" not in data:
        print("BLOCK: 仅有 unified_interpretation，缺少 raw interpretation，无法生成 eval_hook")
        return None
    return None


def generate_eval_hook(interp_obj):
    iid = interp_obj.get("interpretation_id", "")
    if not iid or iid == "UNKNOWN":
        raise ValueError(f"interpretation_id 无效: '{iid}'，禁止生成 eval_hook")

    trade_date = interp_obj.get("trade_date", datetime.now().strftime("%Y-%m-%d"))
    try:
        td = datetime.strptime(trade_date, "%Y-%m-%d").date()
    except ValueError:
        td = date.today()

    return {
        "eval_hook_id": f"EVAL-{td.strftime('%Y%m%d')}-{datetime.now().strftime('%H%M%S')}-{uuid.uuid4().hex[:6]}",
        "interpretation_id": iid,
        "scene": interp_obj.get("scene",""),
        "stock_code": interp_obj.get("stock_code",""),
        "trade_date": interp_obj.get("trade_date",""),
        "role": interp_obj.get("role",""),
        "claim": interp_obj.get("interpretation_hypothesis", ""),
        "action_bias": interp_obj.get("action_bias", "NEUTRAL"),
        "confidence": interp_obj.get("confidence", "MEDIUM"),
        "rule_refs": interp_obj.get("rule_refs", []),
        "knowledge_refs": interp_obj.get("knowledge_refs", []),
        "signal_refs": interp_obj.get("signal_refs", []),
        "source_levels": list(set(e.get("source_level","L5") for e in interp_obj.get("supporting_evidence",[]))),
        "trigger_condition": interp_obj.get("trigger_condition",""),
        "invalidation_condition": interp_obj.get("invalidation_condition",""),
        "t1_check": {
            "check_date": (td + timedelta(days=1)).isoformat(),
            "metric": "price_change_pct",
            "expected": interp_obj.get("eval_window", {}).get("t1", ""),
            "actual": "", "result": "待评估"
        },
        "t3_check": {
            "check_date": (td + timedelta(days=3)).isoformat(),
            "metric": "price_change_3d_pct",
            "expected": interp_obj.get("eval_window", {}).get("t3", ""),
            "actual": "", "result": "待评估"
        },
        "t5_check": {
            "check_date": (td + timedelta(days=5)).isoformat(),
            "metric": "price_change_5d_pct",
            "expected": interp_obj.get("eval_window", {}).get("t5", ""),
            "actual": "", "result": "待评估"
        },
        "success_criteria": interp_obj.get("invalidation_condition", ""),
        "failure_criteria": "T+5 未达到预期且 T+1 方向错误",
        "rule_update_candidate": False
    }


def write_hook(hook, filename=None):
    if not filename:
        filename = f"{hook['eval_hook_id']}.json"
    path = os.path.join(STORE_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(hook, f, ensure_ascii=False, indent=2)
    return path


def main():
    import argparse
    parser = argparse.ArgumentParser(description="eval_hook 写入器")
    parser.add_argument("--interpretation", required=True, help="解释对象JSON路径")
    parser.add_argument("--output", help="输出路径")
    args = parser.parse_args()

    with open(args.interpretation, "r", encoding="utf-8") as f:
        data = json.load(f)

    obj = extract_interpretation(data)

    if obj is None:
        print("BLOCK: 无法提取有效解释对象，eval_hook 生成失败")
        sys.exit(1)

    try:
        hook = generate_eval_hook(obj)
    except ValueError as e:
        print(f"BLOCK: {e}")
        sys.exit(1)

    path = write_hook(hook, args.output)
    print(f"eval_hook 已写入: {path}")
    print(f"  eval_hook_id: {hook['eval_hook_id']}")
    print(f"  interpretation_id: {hook['interpretation_id']}")
    print(f"  T+1: {hook['t1_check']['check_date']} | T+3: {hook['t3_check']['check_date']} | T+5: {hook['t5_check']['check_date']}")


if __name__ == "__main__":
    main()
