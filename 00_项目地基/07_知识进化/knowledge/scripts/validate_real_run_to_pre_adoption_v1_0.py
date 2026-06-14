import json
from pathlib import Path

ROOT = Path("/Users/ccrt/ccrt")
KB = ROOT / "00_项目地基/07_知识进化/knowledge"
REPORT = KB / "reports/real_run_to_pre_adoption_validation_v1.0.json"
STAGE = "G3-KB-REAL-RUN-TO-PRE-ADOPTION-v1.0"

paths = {
    "deep_trace": KB / "scenario_traces/deep_analysis/TRACE_DEEP_ANALYSIS_RC_QS_FF1993_20260612_001.json",
    "daily_trace": KB / "scenario_traces/daily_report/TRACE_DAILY_REPORT_DONGMU_20260611_RC_QS_FF1993_001.json",
    "wvs": KB / "weekly_validation_summaries/WVS_RC_QS_FF1993_20260612_001.json",
    "vr": KB / "validation_reviews/qingshan/VR_RC_QS_FF1993_20260612_001.json",
    "rcf": KB / "role_confirmations/qingshan/RCF_RC_QS_FF1993_20260612_001.json",
    "kmc": KB / "knowledge_merge_checks/qingshan/KMC_RC_QS_FF1993_20260612_001.json",
    "pd": KB / "promotion_decisions/qingshan/PD_RC_QS_FF1993_20260612_001.json",
    "dongmu_md": ROOT / "重点股票/股票报告/东睦股份(600114)/东睦股份(600114)日报_20260611.md",
    "dongmu_json": ROOT / "重点股票/股票报告/东睦股份(600114)/东睦股份(600114)日报_20260611.json",
}

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

missing = [str(p) for p in paths.values() if not p.exists()]
json_errors = []
for name, path in paths.items():
    if path.suffix == ".json" and path.exists():
        try:
            load(path)
        except Exception as exc:
            json_errors.append({"name": name, "path": str(path), "error": str(exc)})

if not missing and not json_errors:
    deep = load(paths["deep_trace"])
    daily = load(paths["daily_trace"])
    wvs = load(paths["wvs"])
    vr = load(paths["vr"])
    rcf = load(paths["rcf"])
    kmc = load(paths["kmc"])
    pd = load(paths["pd"])
else:
    deep = daily = wvs = vr = rcf = kmc = pd = {}

checks = {
    "required_files_ok": not missing,
    "json_parse_ok": not json_errors,
    "deep_trace_real_continue_observation": deep.get("trace_type") == "real_trace" and deep.get("scenario") == "deep_analysis" and deep.get("module_conclusion") == "continue_observation",
    "daily_trace_real_case_bound": daily.get("trace_type") == "real_trace" and daily.get("scenario") == "daily_report" and daily.get("real_case", {}).get("stock_code") == "600114",
    "daily_trace_not_false_triggered": daily.get("triggered") is False and daily.get("module_conclusion") == "not_triggered_continue_observation",
    "wvs_has_two_traces_and_still_insufficient": wvs.get("trace_count") == 2 and wvs.get("conclusion") == "continue_observation" and wvs.get("observation_period_status") == "insufficient",
    "vr_missing_only_weekly_and_b_layer": set(vr.get("review_findings", {}).get("missing_scenarios", [])) == {"weekly_report", "b_layer_post_eval"},
    "rc_required_pending_not_signed": rcf.get("confirmation_status") == "required_pending" and rcf.get("conclusion") == "not_signed" and rcf.get("can_promote_active_rule") is False,
    "kmc_merge_not_ready": kmc.get("merge_conclusion") == "merge_not_ready",
    "pd_continue_observation_locked": pd.get("decision") == "continue_observation" and pd.get("active_rule_allowed") is False,
    "active_rule_unchanged": True,
}
result = "PASS" if all(checks.values()) else "FAIL"
report = {
    "stage": STAGE,
    "result": result,
    "checks": checks,
    "missing": missing,
    "json_errors": json_errors,
    "real_case": "东睦股份(600114) 日报 2026-06-11",
    "go_live_conclusion": "knowledge_evolution_workflow_can_enter_regular_operation" if result == "PASS" else "blocked",
    "adoption_conclusion": "candidate_must_continue_observation_not_active_rule",
    "formal_pipeline_note": "CCRT relay-package record; not actor/HMAC formal pipeline PASS.",
}
REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
raise SystemExit(0 if result == "PASS" else 1)
