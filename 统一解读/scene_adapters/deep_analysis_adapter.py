#!/usr/bin/env python3
"""深度分析场景适配器"""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from create_interpretation import create_interpretation, validate, build_unified_output, write_eval_hook_for

SAMPLE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "样例")

def adapt_deep(stock_code, trade_date, chapter_data, action_bias, confidence, **kw):
    extra_fields = kw.get("extra_fields", None) or chapter_data
    obj = create_interpretation(
        scene="深度分析", stock_code=stock_code, trade_date=trade_date, role="腰子",
        data_fact=chapter_data.get("data_fact",{}), hypothesis=chapter_data.get("hypothesis",""),
        supporting=chapter_data.get("supporting_evidence",[]), counter=chapter_data.get("counter_evidence",[]),
        implication=chapter_data.get("investment_implication",""), action_bias=action_bias, confidence=confidence,
        trigger_cond=kw.get("trigger_condition",""), price_range=kw.get("price_range",""),
        position_limit=kw.get("position_limit",""), time_window=kw.get("time_window",""),
        invalidation=kw.get("invalidation_condition",""), rule_refs=kw.get("rule_refs",[]),
        knowledge_refs=kw.get("knowledge_refs",[]), signal_refs=kw.get("signal_refs",[]),
        eval_window=kw.get("eval_window",{}), extra_fields=extra_fields)
    # D07 v1.2 字段追加写入（透传未覆盖的场景）
    for key in ["framework_version", "hypotheses", "evidence_gap_requests",
                 "long_term_institutional_evidence", "conclusion_strength"]:
        if key not in obj and key in extra_fields:
            obj[key] = extra_fields[key]
    result = validate(obj)
    u9, u10 = result.get("u9",{"status":"ERROR"}), result.get("u10",{"status":"ERROR"})
    overall = result.get("overall","ERROR")
    hook_ids = [write_eval_hook_for(obj)] if overall in ("PASS","WARN") and write_eval_hook_for(obj) else []
    return build_unified_output(obj, u9, u10, hook_ids)

if __name__ == "__main__":
    with open(os.path.join(SAMPLE_DIR, "样例2_深度分析_600519.json"), "r", encoding="utf-8") as f:
        d = json.load(f)
    output = adapt_deep(d["stock_code"], d["trade_date"],
        {"data_fact":d["data_fact"],"hypothesis":d["interpretation_hypothesis"],
         "supporting_evidence":d["supporting_evidence"],"counter_evidence":d["counter_evidence"],
         "investment_implication":d["investment_implication"]},
        d["action_bias"], d["confidence"],
        trigger_condition=d.get("trigger_condition",""), price_range=d.get("price_range",""),
        position_limit=d.get("position_limit",""), time_window=d.get("time_window",""),
        invalidation_condition=d.get("invalidation_condition",""), rule_refs=d.get("rule_refs",[]),
        knowledge_refs=d.get("knowledge_refs",[]), signal_refs=d.get("signal_refs",[]),
        eval_window=d.get("eval_window",{}))
    print(json.dumps(output, ensure_ascii=False, indent=2))
