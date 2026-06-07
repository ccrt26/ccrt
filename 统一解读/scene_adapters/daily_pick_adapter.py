#!/usr/bin/env python3
"""每日荐股场景适配器"""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from create_interpretation import create_interpretation, validate, build_unified_output, write_eval_hook_for

SAMPLE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "样例")

def adapt_pick(stock_code, trade_date, pick_data, selected, reject_reason=""):
    obj = create_interpretation(
        scene="每日荐股", stock_code=stock_code, trade_date=trade_date, role="腰子",
        data_fact=pick_data.get("data_fact",{}), hypothesis=pick_data.get("pick_rationale",""),
        supporting=pick_data.get("supporting_evidence",[]), counter=pick_data.get("counter_evidence",[]),
        implication=f"{'入选' if selected else '剔除'}: {pick_data.get('pick_rationale','')}",
        action_bias="BUY" if selected else "WATCH", confidence=pick_data.get("confidence","MEDIUM"),
        trigger_cond=pick_data.get("trigger_condition",""), price_range=pick_data.get("price_range",""),
        position_limit=pick_data.get("position_limit",""), time_window=pick_data.get("time_window",""),
        invalidation=pick_data.get("invalidation_condition",""), rule_refs=pick_data.get("rule_refs",[]),
        knowledge_refs=pick_data.get("knowledge_refs",[]), signal_refs=pick_data.get("signal_refs",[]),
        eval_window=pick_data.get("eval_window",{}))
    result = validate(obj)
    u9, u10 = result.get("u9",{"status":"ERROR"}), result.get("u10",{"status":"ERROR"})
    overall = result.get("overall","ERROR")
    hook_ids = [write_eval_hook_for(obj)] if overall in ("PASS","WARN") and write_eval_hook_for(obj) else []
    return build_unified_output(obj, u9, u10, hook_ids)

if __name__ == "__main__":
    with open(os.path.join(SAMPLE_DIR, "样例3_每日荐股_300750.json"), "r", encoding="utf-8") as f:
        d = json.load(f)
    output = adapt_pick(d["stock_code"], d["trade_date"],
        {"data_fact":d["data_fact"],"pick_rationale":d["interpretation_hypothesis"],
         "supporting_evidence":d["supporting_evidence"],"counter_evidence":d["counter_evidence"],
         "confidence":d["confidence"],"trigger_condition":d.get("trigger_condition",""),
         "price_range":d.get("price_range",""),"position_limit":d.get("position_limit",""),
         "time_window":d.get("time_window",""),"invalidation_condition":d.get("invalidation_condition",""),
         "rule_refs":d.get("rule_refs",[]),"knowledge_refs":d.get("knowledge_refs",[]),
         "signal_refs":d.get("signal_refs",[]),"eval_window":d.get("eval_window",{})}, True)
    print(json.dumps(output, ensure_ascii=False, indent=2))
