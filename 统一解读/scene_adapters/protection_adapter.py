#!/usr/bin/env python3
"""保护机制场景适配器"""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from create_interpretation import create_interpretation, validate, build_unified_output, write_eval_hook_for

def adapt_protection(stock_code, trade_date, protection_data):
    tt = protection_data.get("trigger_type","刹车")
    obj = create_interpretation(
        scene="保护机制", stock_code=stock_code, trade_date=trade_date, role="流金",
        data_fact=protection_data.get("data_fact",{}),
        hypothesis=f"保护机制{tt}触发: {protection_data.get('reason','')}",
        supporting=protection_data.get("supporting_evidence",[]),
        counter=protection_data.get("counter_evidence",[]),
        implication=f"保护机制{tt}触发: {protection_data.get('reason','')}，建议{protection_data.get('action_bias','HOLD')}，等待保护条件解除后再评估",
        action_bias=protection_data.get("action_bias","HOLD"),
        confidence=protection_data.get("confidence","MEDIUM"),
        trigger_cond=protection_data.get("trigger_condition",""),
        invalidation=protection_data.get("invalidation_condition","保护条件解除"),
        rule_refs=protection_data.get("rule_refs",["I-03","A-06"]),
        knowledge_refs=protection_data.get("knowledge_refs",["LIUJIN-STOP-001","LIUJIN-RISK-001"]),
        signal_refs=protection_data.get("signal_refs",[]),
        eval_window=protection_data.get("eval_window",{"t1":"检查保护条件是否持续","t3":"检查是否可解除","t5":"评估保护效果"}))
    result = validate(obj)
    u9, u10 = result.get("u9",{"status":"ERROR"}), result.get("u10",{"status":"ERROR"})
    overall = result.get("overall","ERROR")
    hook_ids = [write_eval_hook_for(obj)] if overall in ("PASS","WARN") and write_eval_hook_for(obj) else []
    return build_unified_output(obj, u9, u10, hook_ids)

if __name__ == "__main__":
    output = adapt_protection("000001.XSHE", "2026-06-02", {
        "trigger_type":"刹车", "reason":"连续3日下跌累计超5%",
        "data_fact":{"source":"Tushare","freshness":"当日","values":{"close":11.50,"change_3d_pct":-5.2}},
        "supporting_evidence":[{"evidence":"连续3日下跌累计5.2%","source":"Tushare","strength":"强","source_level":"L3","source_ref":"Tushare.000001.2026-06-02"}],
        "counter_evidence":[{"evidence":"成交量未放大，恐慌性抛售不明显","source":"Tushare","type":"技术面反证"}],
        "action_bias":"HOLD","confidence":"MEDIUM","trigger_condition":"连续3日跌幅>5%",
        "invalidation_condition":"T+2内股价回升至12.00以上且量能恢复",
        "rule_refs":["I-03","A-06"],"knowledge_refs":["LIUJIN-STOP-001","LIUJIN-RISK-001"],
        "eval_window":{"t1":"检查跌幅是否收窄","t3":"检查是否回升","t5":"评估保护效果"}})
    print(json.dumps(output, ensure_ascii=False, indent=2))
