#!/usr/bin/env python3
"""日报场景适配器 — 双对象格式输出"""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from create_interpretation import create_interpretation, validate, build_unified_output, write_eval_hook_for

SAMPLE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "样例")

def adapt_daily(stock_code, trade_date, data_fact, action_bias, confidence,
                supporting, counter, implication, trigger="", price="",
                position="", time_win="", invalidation="",
                rule_refs=None, knowledge_refs=None, signal_refs=None, eval_window=None):
    obj = create_interpretation(
        scene="日报", stock_code=stock_code, trade_date=trade_date, role="腰子",
        data_fact=data_fact, hypothesis=implication[:80], supporting=supporting,
        counter=counter, implication=implication, action_bias=action_bias,
        confidence=confidence, trigger_cond=trigger, price_range=price,
        position_limit=position, time_window=time_win, invalidation=invalidation,
        rule_refs=rule_refs, knowledge_refs=knowledge_refs, signal_refs=signal_refs,
        eval_window=eval_window)
    result = validate(obj)
    u9, u10 = result.get("u9", {"status": "ERROR"}), result.get("u10", {"status": "ERROR"})
    overall = result.get("overall", "ERROR")
    hook_ids = [write_eval_hook_for(obj)] if overall in ("PASS", "WARN") and write_eval_hook_for(obj) else []
    return build_unified_output(obj, u9, u10, hook_ids)

if __name__ == "__main__":
    with open(os.path.join(SAMPLE_DIR, "样例1_日报_000001.json"), "r", encoding="utf-8") as f:
        d = json.load(f)
    output = adapt_daily(d["stock_code"], d["trade_date"], d["data_fact"], d["action_bias"],
        d["confidence"], d["supporting_evidence"], d["counter_evidence"],
        d["investment_implication"], d.get("trigger_condition",""), d.get("price_range",""),
        d.get("position_limit",""), d.get("time_window",""), d.get("invalidation_condition",""),
        d.get("rule_refs",[]), d.get("knowledge_refs",[]), d.get("signal_refs",[]), d.get("eval_window",{}))
    print(json.dumps(output, ensure_ascii=False, indent=2))
