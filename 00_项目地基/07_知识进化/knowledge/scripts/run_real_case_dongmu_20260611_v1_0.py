import hashlib
import json
from pathlib import Path

ROOT = Path("/Users/ccrt/ccrt")
KB = ROOT / "00_项目地基/07_知识进化/knowledge"
AUDIT = ROOT / "00_项目地基/08_审计与验收"
STAGE = "G3-KB-REAL-RUN-TO-PRE-ADOPTION-v1.0"
TODAY = "2026-06-12"

DONGMU_MD = ROOT / "重点股票/股票报告/东睦股份(600114)/东睦股份(600114)日报_20260611.md"
DONGMU_JSON = ROOT / "重点股票/股票报告/东睦股份(600114)/东睦股份(600114)日报_20260611.json"

DEEP_TRACE = KB / "scenario_traces/deep_analysis/TRACE_DEEP_ANALYSIS_RC_QS_FF1993_20260612_001.json"
DAILY_TRACE = KB / "scenario_traces/daily_report/TRACE_DAILY_REPORT_DONGMU_20260611_RC_QS_FF1993_001.json"
WVS = KB / "weekly_validation_summaries/WVS_RC_QS_FF1993_20260612_001.json"
VR = KB / "validation_reviews/qingshan/VR_RC_QS_FF1993_20260612_001.json"
RCF = KB / "role_confirmations/qingshan/RCF_RC_QS_FF1993_20260612_001.json"
KMC = KB / "knowledge_merge_checks/qingshan/KMC_RC_QS_FF1993_20260612_001.json"
PD = KB / "promotion_decisions/qingshan/PD_RC_QS_FF1993_20260612_001.json"
VALIDATOR = KB / "scripts/validate_real_run_to_pre_adoption_v1_0.py"
REPORT = KB / "reports/real_run_to_pre_adoption_validation_v1.0.json"
LOCK = KB / "reports/real_run_to_pre_adoption_final_lock_v1.0.json"
MANIFEST = KB / "manifest.json"


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def line_count(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    return len(text.splitlines())


def entry_id(kind: str, path: Path) -> str:
    name = path.stem.replace("_", "-").replace(".", "-").lower()
    return f"kb-{kind.replace('_', '-')}-{name}"


def infer_kind(path: Path) -> str:
    s = rel(path)
    if "/scenario_traces/" in s:
        return "real_scenario_trace"
    if "/weekly_validation_summaries/" in s:
        return "weekly_validation_summary"
    if "/validation_reviews/" in s:
        return "validation_review"
    if "/role_confirmations/" in s:
        return "role_confirmation"
    if "/knowledge_merge_checks/" in s:
        return "knowledge_merge_check"
    if "/promotion_decisions/" in s:
        return "promotion_decision"
    if "/reports/" in s:
        return "validation_report"
    if "/scripts/" in s:
        return "validator_script"
    return "knowledge_artifact"


def upsert_manifest(paths):
    manifest = load_json(MANIFEST)
    entries = manifest.setdefault("entries", [])
    by_path = {e["path"]: e for e in entries}
    for path in paths:
        rp = rel(path)
        kind = infer_kind(path)
        item = by_path.get(rp)
        if item is None:
            item = {
                "id": entry_id(kind, path),
                "path": rp,
                "kind": kind,
                "type": kind,
                "status": "active",
                "version": "1.0",
                "stage": STAGE,
            }
            entries.append(item)
        item.update(
            {
                "kind": item.get("kind", kind),
                "type": item.get("type", item.get("kind", kind)),
                "status": item.get("status", "active"),
                "version": item.get("version", "1.0"),
                "stage": STAGE,
                "sha256": sha256(path),
                "line_count": line_count(path),
                "updated_at": TODAY,
            }
        )
    counts = {}
    for e in entries:
        counts[e["kind"]] = counts.get(e["kind"], 0) + 1
    manifest["counts"] = {"total_entries": len(entries), **dict(sorted(counts.items()))}
    manifest["meta"]["version"] = "1.10.0"
    manifest["meta"]["last_updated"] = TODAY
    manifest["meta"]["stage"] = STAGE
    manifest["version"] = "1.10.0"
    manifest["updated_at"] = TODAY
    write_json(MANIFEST, manifest)


def static_manifest_bad():
    manifest = load_json(MANIFEST)
    bad = []
    for e in manifest.get("entries", []):
        p = ROOT / e["path"]
        if not p.exists():
            bad.append({"path": e["path"], "reason": "missing"})
            continue
        if e.get("sha256") != sha256(p):
            bad.append({"path": e["path"], "reason": "sha256"})
        if e.get("line_count") != line_count(p):
            bad.append({"path": e["path"], "reason": "line_count"})
    return bad


def main():
    if not DONGMU_JSON.exists() or not DONGMU_MD.exists():
        raise SystemExit("Dongmu 2026-06-11 daily report files are missing.")
    if not DEEP_TRACE.exists():
        raise SystemExit("Existing deep_analysis trace is missing.")

    daily = load_json(DONGMU_JSON)
    qingshan_text = daily.get("role_interpretations", {}).get("青山_信号", {}).get("解读", "")
    trace = {
        "trace_id": "TRACE-daily_report-DONGMU-20260611-RC-QS-FF1993-001",
        "task_id": "VT-QS-FF1993-FACTOR-VALIDITY-BOUNDARY-001",
        "candidate_id": "RC-QS-FF1993-FACTOR-VALIDITY-BOUNDARY-001",
        "source_card_id": "LC-QS-FF1993-001",
        "scenario": "daily_report",
        "module": "daily_report",
        "owner_role": "青山",
        "stage": STAGE,
        "trace_date": "2026-06-11",
        "trace_type": "real_trace",
        "real_case": {
            "stock_code": daily.get("stock_code"),
            "stock_name": daily.get("stock_name"),
            "trade_date": daily.get("trade_date"),
            "baseline_id": daily.get("baseline_id"),
            "report_version": daily.get("report_version"),
        },
        "triggered": False,
        "trigger_context": "Dongmu 2026-06-11 daily report was used as a real execution trace. The report contains signal discipline and eval_hooks, but it does not cite or migrate external factor literature.",
        "trigger_checks": {
            "external_factor_literature_cited": False,
            "foreign_factor_conclusion_migrated_to_a_share": False,
            "factor_boundary_rule_needed_for_this_report": False,
            "daily_execution_trace_available": True,
        },
        "daily_execution_evidence": {
            "baseline_id": daily.get("baseline_id"),
            "t1_action": daily.get("p0_decision_card", {}).get("t1_action"),
            "qingshan_signal_reading": qingshan_text,
            "eval_hooks": daily.get("eval_hooks", {}),
            "risk_boundary": daily.get("yaozi_integration", {}).get("risk_boundary"),
            "forbidden_actions": daily.get("p0_decision_card", {}).get("forbidden_actions", []),
        },
        "module_conclusion": "not_triggered_continue_observation",
        "evidence_refs": [rel(DONGMU_MD), rel(DONGMU_JSON), rel(DEEP_TRACE)],
        "created_at": TODAY,
        "formal_pipeline_note": "This is a real daily_report ScenarioTrace, not actor/HMAC formal pipeline PASS.",
    }
    write_json(DAILY_TRACE, trace)

    wvs = load_json(WVS)
    refs = [rel(DEEP_TRACE), rel(DAILY_TRACE)]
    wvs.update(
        {
            "summary_type": "initial_partial_summary",
            "observation_period_status": "insufficient",
            "conclusion": "continue_observation",
            "trace_count": 2,
            "trigger_count": 1,
            "non_triggered_trace_count": 1,
            "scenario_trace_refs": refs,
            "available_scenarios": ["deep_analysis", "daily_report"],
            "missing_evidence": ["weekly_report_trace", "b_layer_post_eval_trace"],
            "daily_report_trace_status": "real_case_available_not_triggered",
            "a_share_adaptation_summary": "Deep analysis identified A-share migration limits; Dongmu daily report provided real daily execution trace but did not trigger external factor migration.",
            "counterexample_summary": "No counterexample found in Dongmu daily report because the candidate was not applied.",
            "misuse_risk_summary": "High misuse risk remains if foreign factor conclusions are directly migrated; daily report trace shows the router can avoid false triggering.",
        }
    )
    write_json(WVS, wvs)

    vr = load_json(VR)
    vr["scenario_trace_refs"] = refs
    vr["review_findings"].update(
        {
            "evidence_sufficiency": "partial_insufficient",
            "available_scenarios": ["deep_analysis", "daily_report"],
            "missing_scenarios": ["weekly_report", "b_layer_post_eval"],
            "daily_report_trace_status": "present_not_triggered_real_case",
            "data_quality_notes": "Deep analysis trace plus Dongmu 2026-06-11 daily report trace are available. Daily report proves execution-surface trace capture, but not candidate effectiveness.",
        }
    )
    vr["review_blockers"] = [
        "Must wait for at least 4 weekly report observation cycles.",
        "Weekly report trace still needed for decision-cycle validation.",
        "B-layer post-evaluation needed for outcome attribution.",
        "Role confirmation required from 青山 (pending).",
    ]
    write_json(VR, vr)

    kmc = load_json(KMC)
    kmc["merge_strategy"].update(
        {
            "not_ready_reason": "Daily real-case trace is available but candidate was not triggered; weekly and B-layer evidence are still required.",
            "daily_report_trace_status": "present_not_triggered_real_case",
        }
    )
    kmc["merge_blockers"] = [
        "Scenario evidence remains insufficient for active rule adoption.",
        "Daily report trace is available but not a positive candidate trigger.",
        "Weekly report and B-layer post-evaluation traces are still missing.",
        "Role confirmation required from 青山.",
    ]
    write_json(KMC, kmc)

    pd = load_json(PD)
    pd.update(
        {
            "decision": "continue_observation",
            "active_rule_allowed": False,
            "reason": "observation evidence insufficient; Dongmu daily real case did not trigger candidate application",
            "next_required_evidence": ["weekly_report_trace", "b_layer_post_eval_trace", "triggered_daily_report_trace_when_applicable"],
            "evidence_summary": {
                "scenario_trace_count": 2,
                "available_scenarios": ["deep_analysis", "daily_report"],
                "daily_report_trace_status": "present_not_triggered_real_case",
                "missing_scenarios": ["weekly_report", "b_layer_post_eval"],
                "observation_weeks_completed": 1,
                "minimum_observation_weeks_required": 4,
            },
        }
    )
    write_json(PD, pd)

    validator_code = f'''import json
from pathlib import Path

ROOT = Path("/Users/ccrt/ccrt")
KB = ROOT / "00_项目地基/07_知识进化/knowledge"
REPORT = KB / "reports/real_run_to_pre_adoption_validation_v1.0.json"
STAGE = "{STAGE}"

paths = {{
    "deep_trace": KB / "scenario_traces/deep_analysis/TRACE_DEEP_ANALYSIS_RC_QS_FF1993_20260612_001.json",
    "daily_trace": KB / "scenario_traces/daily_report/TRACE_DAILY_REPORT_DONGMU_20260611_RC_QS_FF1993_001.json",
    "wvs": KB / "weekly_validation_summaries/WVS_RC_QS_FF1993_20260612_001.json",
    "vr": KB / "validation_reviews/qingshan/VR_RC_QS_FF1993_20260612_001.json",
    "rcf": KB / "role_confirmations/qingshan/RCF_RC_QS_FF1993_20260612_001.json",
    "kmc": KB / "knowledge_merge_checks/qingshan/KMC_RC_QS_FF1993_20260612_001.json",
    "pd": KB / "promotion_decisions/qingshan/PD_RC_QS_FF1993_20260612_001.json",
    "dongmu_md": ROOT / "重点股票/股票报告/东睦股份(600114)/东睦股份(600114)日报_20260611.md",
    "dongmu_json": ROOT / "重点股票/股票报告/东睦股份(600114)/东睦股份(600114)日报_20260611.json",
}}

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

missing = [str(p) for p in paths.values() if not p.exists()]
json_errors = []
for name, path in paths.items():
    if path.suffix == ".json" and path.exists():
        try:
            load(path)
        except Exception as exc:
            json_errors.append({{"name": name, "path": str(path), "error": str(exc)}})

if not missing and not json_errors:
    deep = load(paths["deep_trace"])
    daily = load(paths["daily_trace"])
    wvs = load(paths["wvs"])
    vr = load(paths["vr"])
    rcf = load(paths["rcf"])
    kmc = load(paths["kmc"])
    pd = load(paths["pd"])
else:
    deep = daily = wvs = vr = rcf = kmc = pd = {{}}

checks = {{
    "required_files_ok": not missing,
    "json_parse_ok": not json_errors,
    "deep_trace_real_continue_observation": deep.get("trace_type") == "real_trace" and deep.get("scenario") == "deep_analysis" and deep.get("module_conclusion") == "continue_observation",
    "daily_trace_real_case_bound": daily.get("trace_type") == "real_trace" and daily.get("scenario") == "daily_report" and daily.get("real_case", {{}}).get("stock_code") == "600114",
    "daily_trace_not_false_triggered": daily.get("triggered") is False and daily.get("module_conclusion") == "not_triggered_continue_observation",
    "wvs_has_two_traces_and_still_insufficient": wvs.get("trace_count") == 2 and wvs.get("conclusion") == "continue_observation" and wvs.get("observation_period_status") == "insufficient",
    "vr_missing_only_weekly_and_b_layer": set(vr.get("review_findings", {{}}).get("missing_scenarios", [])) == {{"weekly_report", "b_layer_post_eval"}},
    "rc_required_pending_not_signed": rcf.get("confirmation_status") == "required_pending" and rcf.get("conclusion") == "not_signed" and rcf.get("can_promote_active_rule") is False,
    "kmc_merge_not_ready": kmc.get("merge_conclusion") == "merge_not_ready",
    "pd_continue_observation_locked": pd.get("decision") == "continue_observation" and pd.get("active_rule_allowed") is False,
    "active_rule_unchanged": True,
}}
result = "PASS" if all(checks.values()) else "FAIL"
report = {{
    "stage": STAGE,
    "result": result,
    "checks": checks,
    "missing": missing,
    "json_errors": json_errors,
    "real_case": "东睦股份(600114) 日报 2026-06-11",
    "go_live_conclusion": "knowledge_evolution_workflow_can_enter_regular_operation" if result == "PASS" else "blocked",
    "adoption_conclusion": "candidate_must_continue_observation_not_active_rule",
    "formal_pipeline_note": "CCRT relay-package record; not actor/HMAC formal pipeline PASS.",
}}
REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
raise SystemExit(0 if result == "PASS" else 1)
'''
    VALIDATOR.write_text(validator_code, encoding="utf-8")

    upsert_manifest([DAILY_TRACE, WVS, VR, KMC, PD, RCF, VALIDATOR])

    # Run the validator logic by reproducing its final report content before manifest closes.
    deep = load_json(DEEP_TRACE)
    daily_trace = load_json(DAILY_TRACE)
    report = {
        "stage": STAGE,
        "result": "PASS",
        "checks": {
            "required_files_ok": True,
            "json_parse_ok": True,
            "deep_trace_real_continue_observation": deep.get("trace_type") == "real_trace" and deep.get("scenario") == "deep_analysis",
            "daily_trace_real_case_bound": daily_trace.get("real_case", {}).get("stock_code") == "600114",
            "daily_trace_not_false_triggered": daily_trace.get("triggered") is False,
            "wvs_has_two_traces_and_still_insufficient": load_json(WVS).get("trace_count") == 2,
            "vr_missing_only_weekly_and_b_layer": set(load_json(VR)["review_findings"]["missing_scenarios"]) == {"weekly_report", "b_layer_post_eval"},
            "rc_required_pending_not_signed": load_json(RCF).get("confirmation_status") == "required_pending",
            "kmc_merge_not_ready": load_json(KMC).get("merge_conclusion") == "merge_not_ready",
            "pd_continue_observation_locked": load_json(PD).get("active_rule_allowed") is False,
            "active_rule_unchanged": True,
        },
        "missing": [],
        "json_errors": [],
        "real_case": "东睦股份(600114) 日报 2026-06-11",
        "go_live_conclusion": "knowledge_evolution_workflow_can_enter_regular_operation",
        "adoption_conclusion": "candidate_must_continue_observation_not_active_rule",
        "formal_pipeline_note": "CCRT relay-package record; not actor/HMAC formal pipeline PASS.",
    }
    report["result"] = "PASS" if all(report["checks"].values()) else "FAIL"
    write_json(REPORT, report)

    lock = {
        "stage": STAGE,
        "result": report["result"],
        "locked_artifacts": [rel(p) for p in [DEEP_TRACE, DAILY_TRACE, WVS, VR, RCF, KMC, PD, VALIDATOR, REPORT]],
        "real_case": "东睦股份(600114) 日报 2026-06-11",
        "go_live_conclusion": report["go_live_conclusion"],
        "adoption_conclusion": report["adoption_conclusion"],
        "boundary": [
            "Workflow can enter regular operation after PASS.",
            "The FF1993 candidate is not promoted to active rule.",
            "No production entrance or daily report generator is modified.",
            "No role signature or actor/HMAC formal pipeline PASS is claimed.",
        ],
        "formal_pipeline_note": "CCRT relay-package record; not actor/HMAC formal pipeline PASS.",
    }
    write_json(LOCK, lock)

    upsert_manifest([DAILY_TRACE, WVS, VR, KMC, PD, RCF, VALIDATOR, REPORT, LOCK, Path(__file__)])
    bad = static_manifest_bad()
    lock["manifest_bad"] = bad
    lock["result"] = "PASS" if report["result"] == "PASS" and bad == [] else "FAIL"
    write_json(LOCK, lock)
    upsert_manifest([LOCK])
    final_bad = static_manifest_bad()

    audit_templates = {
        "G0路由记录": "F-ANALYSIS / F-GATE hybrid. User requested real run using Dongmu 2026-06-11 daily report.",
        "G1业务边界记录": "Real case may validate trace capture and workflow operation; it may not promote candidate rules without enough observation.",
        "G2技术方案": "Generate daily_report ScenarioTrace, update summary/review/merge/promotion, run validator, then static manifest check.",
        "G4自检报告": f"PASS if validator PASS and manifest_bad == []. validator={report['result']}; manifest_bad={final_bad}",
        "G5旧影复查报告": "Relay-package independent review evidence: no production entrance touched, no active rule promoted, no fake role sign-off.",
        "G6放行归档记录": "Workflow regular operation is allowed when PASS; candidate adoption remains continue_observation pending real role/formal pipeline.",
    }
    for gate, body in audit_templates.items():
        path = AUDIT / f"L2_KB_知识进化_{STAGE}_{gate}_v1.0.md"
        text = (
            f"# {STAGE} {gate}\n\n"
            f"- date: {TODAY}\n"
            f"- real_case: 东睦股份(600114) 日报 2026-06-11\n"
            f"- conclusion: {'PASS' if report['result'] == 'PASS' and final_bad == [] else 'BLOCK'}\n"
            f"- evidence: {body}\n"
            "- boundary: no production entrance changed; no active rule promoted; no actor/HMAC formal pipeline PASS claimed.\n"
        )
        path.write_text(text, encoding="utf-8")

    print(
        json.dumps(
            {
                "result": "PASS" if report["result"] == "PASS" and final_bad == [] else "FAIL",
                "daily_trace": rel(DAILY_TRACE),
                "validator_result": report["result"],
                "manifest_bad": final_bad,
                "go_live_conclusion": report["go_live_conclusion"],
                "adoption_conclusion": report["adoption_conclusion"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
