#!/usr/bin/env python3
"""临时分析场景适配器"""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from create_interpretation import create_interpretation, validate, build_unified_output, write_eval_hook_for

def adapt_temp(stock_code, trade_date, analysis_data):
    obj = create_interpretation(
        scene="临时分析", stock_code=stock_code, trade_date=trade_date,
        role=analysis_data.get("role","腰子"), data_fact=analysis_data.get("data_fact",{}),
        hypothesis=analysis_data.get("hypothesis",""),
        supporting=analysis_data.get("supporting_evidence",[]),
        counter=analysis_data.get("counter_evidence",[]),
        implication=analysis_data.get("investment_implication",""),
        action_bias=analysis_data.get("action_bias","NEUTRAL"),
        confidence=analysis_data.get("confidence","MEDIUM"),
        trigger_cond=analysis_data.get("trigger_condition",""),
        invalidation=analysis_data.get("invalidation_condition",""),
        rule_refs=analysis_data.get("rule_refs",[]),
        knowledge_refs=analysis_data.get("knowledge_refs",[]),
        signal_refs=analysis_data.get("signal_refs",[]),
        eval_window=analysis_data.get("eval_window",{"t1":"检查方向","t3":"检查持续","t5":"综合验证"}))
    result = validate(obj)
    u9, u10 = result.get("u9",{"status":"ERROR"}), result.get("u10",{"status":"ERROR"})
    overall = result.get("overall","ERROR")
    hook_ids = [write_eval_hook_for(obj)] if overall in ("PASS","WARN") and write_eval_hook_for(obj) else []
    return build_unified_output(obj, u9, u10, hook_ids)

if __name__ == "__main__":
    output = adapt_temp("MARKET", "2026-06-02", {
        "role":"腰子","analysis_type":"市场概况",
        "data_fact":{"source":"Tushare+新浪","freshness":"当日","values":{"sh_index":3250.50,"change_pct":0.3}},
        "hypothesis":"大盘震荡偏多，量能正常，短期无系统性风险",
        "supporting_evidence":[{"evidence":"上证微涨0.3%，成交量正常","source":"新浪行情","strength":"中","source_level":"L3","source_ref":"新浪.上证.2026-06-02"}],
        "counter_evidence":[{"evidence":"M1-M2剪刀差为负","source":"央行数据","type":"宏观风险"}],
        "investment_implication":"市场整体处于震荡偏多状态，个股操作环境正常，但需注意信用收缩和M1-M2剪刀差为负的结构性压力，建议控制仓位在流动性约束范围内操作",
        "action_bias":"NEUTRAL","confidence":"MEDIUM",
        "invalidation_condition":"上证跌破3200或量能萎缩至0.7x以下",
        "rule_refs":["M-02","M-04"],"knowledge_refs":["SHANMAO-MARKET-001","SHANMAO-MACRO-001"],
        "eval_window":{"t1":"检查指数方向","t3":"检查量能","t5":"验证判断"}})
    print(json.dumps(output, ensure_ascii=False, indent=2))
