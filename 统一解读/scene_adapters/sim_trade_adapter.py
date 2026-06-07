#!/usr/bin/env python3
"""模拟交易场景适配器"""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from create_interpretation import create_interpretation, validate, build_unified_output, write_eval_hook_for

SAMPLE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "样例")

def adapt_trade(stock_code, trade_date, trade_data):
    obj = create_interpretation(
        scene="模拟交易", stock_code=stock_code, trade_date=trade_date, role="腰子",
        data_fact=trade_data.get("data_fact",{}), hypothesis=trade_data.get("trade_rationale",""),
        supporting=trade_data.get("supporting_evidence",[]), counter=trade_data.get("counter_evidence",[]),
        implication=trade_data.get("investment_implication",""),
        action_bias=trade_data.get("action_bias","HOLD"), confidence=trade_data.get("confidence","MEDIUM"),
        trigger_cond=trade_data.get("trigger_condition",""), price_range=trade_data.get("price_range",""),
        position_limit=trade_data.get("position_limit",""), time_window=trade_data.get("time_window",""),
        invalidation=trade_data.get("invalidation_condition",""), rule_refs=trade_data.get("rule_refs",[]),
        knowledge_refs=trade_data.get("knowledge_refs",[]), signal_refs=trade_data.get("signal_refs",[]),
        eval_window=trade_data.get("eval_window",{}))
    result = validate(obj)
    u9, u10 = result.get("u9",{"status":"ERROR"}), result.get("u10",{"status":"ERROR"})
    overall = result.get("overall","ERROR")
    hook_ids = [write_eval_hook_for(obj)] if overall in ("PASS","WARN") and write_eval_hook_for(obj) else []
    return build_unified_output(obj, u9, u10, hook_ids)

if __name__ == "__main__":
    with open(os.path.join(SAMPLE_DIR, "样例1_日报_000001.json"), "r", encoding="utf-8") as f:
        d = json.load(f)
    output = adapt_trade(d["stock_code"], d["trade_date"],
        {"data_fact":d["data_fact"],"trade_rationale":d["interpretation_hypothesis"],
         "supporting_evidence":d["supporting_evidence"],"counter_evidence":d["counter_evidence"],
         "investment_implication":d["investment_implication"],"action_bias":d["action_bias"],
         "confidence":d["confidence"],"trigger_condition":d.get("trigger_condition",""),
         "price_range":d.get("price_range",""),"position_limit":d.get("position_limit",""),
         "time_window":d.get("time_window",""),"invalidation_condition":d.get("invalidation_condition",""),
         "rule_refs":d.get("rule_refs",[]),"knowledge_refs":d.get("knowledge_refs",[]),
         "signal_refs":d.get("signal_refs",[]),"eval_window":d.get("eval_window",{})})
    print(json.dumps(output, ensure_ascii=False, indent=2))
