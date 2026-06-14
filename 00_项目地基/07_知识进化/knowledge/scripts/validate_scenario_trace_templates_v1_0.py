
import json, hashlib, subprocess, sys
from pathlib import Path

ROOT = Path('/Users/ccrt/ccrt')
KB = ROOT / "00_项目地基/07_知识进化/knowledge"
REPORT = KB / "reports/scenario_trace_templates_validation_v1.0.json"
WRITE_REPORT = "--write-report" in sys.argv
if WRITE_REPORT:
    sys.argv = [x for x in sys.argv if x != "--write-report"]
STAGE = 'G3-KB-SCENARIO-TRACE-TEMPLATES-v1.0'
TASK_ID = 'VT-QS-FF1993-FACTOR-VALIDITY-BOUNDARY-001'
CANDIDATE_ID = 'RC-QS-FF1993-FACTOR-VALIDITY-BOUNDARY-001'

def load_json(p):
    return json.loads(p.read_text(encoding="utf-8"))

def child_cmd(script):
    cmd = [sys.executable, str(script)]
    if WRITE_REPORT:
        cmd.append("--write-report")
    return cmd

required = [
    KB / "validation_modules/validation_trace_binding_registry_v1.0.json",
    KB / "scenario_trace_templates/weekly_report/TEMPLATE_WEEKLY_REPORT_RC_QS_FF1993_v1.0.json",
    KB / "scenario_trace_templates/daily_report/TEMPLATE_DAILY_REPORT_RC_QS_FF1993_v1.0.json",
    KB / "scenario_trace_templates/b_layer_post_eval/TEMPLATE_B_LAYER_POST_EVAL_RC_QS_FF1993_v1.0.json",
    KB / "scenario_trace_templates/deep_analysis/TEMPLATE_DEEP_ANALYSIS_RC_QS_FF1993_v1.0.json",
    KB / "weekly_validation_summary_templates/TEMPLATE_WEEKLY_VALIDATION_SUMMARY_RC_QS_FF1993_v1.0.json",
]

missing = [str(p) for p in required if not p.exists()]
json_errors = []
for p in required:
    if p.exists():
        try:
            load_json(p)
        except Exception as exc:
            json_errors.append({"path": str(p), "error": str(exc)})

template_errors = []
scenarios = {"weekly_report", "daily_report", "b_layer_post_eval", "deep_analysis"}
seen = set()
for p in required:
    if not p.exists() or p.suffix != ".json":
        continue
    data = load_json(p)
    if p.name.startswith("TEMPLATE_") and "VALIDATION_SUMMARY" not in p.name:
        seen.add(data.get("scenario"))
        if data.get("template_status") != "template_only":
            template_errors.append({"path": str(p), "error": "template_status_not_template_only"})
        if data.get("task_id") != TASK_ID:
            template_errors.append({"path": str(p), "error": "task_id_mismatch"})
        if data.get("candidate_id") != CANDIDATE_ID:
            template_errors.append({"path": str(p), "error": "candidate_id_mismatch"})
        if not data.get("required_fields"):
            template_errors.append({"path": str(p), "error": "required_fields_empty"})

missing_scenarios = sorted(scenarios - seen)

real_trace_dirs = [
    KB / "scenario_traces", KB / "weekly_validation_summaries",
    KB / "validation_reviews", KB / "role_confirmations", KB / "knowledge_merge_checks"
]

def collect_real_trace_files():
    files = []
    for d in real_trace_dirs:
        if d.exists():
            files.extend([str(p) for p in d.rglob("*") if p.is_file()])
    return sorted(files)

existing_real_trace_files = collect_real_trace_files()

task_proc = subprocess.run(
    child_cmd(KB / "scripts/validate_rule_candidate_validation_tasks_v1_0.py"),
    cwd=str(ROOT), text=True, capture_output=True)
foundation_proc = subprocess.run(
    child_cmd(KB / "scripts/validate_knowledge_workflow_foundation_v1_0.py"),
    cwd=str(ROOT), text=True, capture_output=True)
krm_proc = subprocess.run(
    child_cmd(KB / "scripts/validate_global_krm_restore_after_qingshan_flow_v1_0.py"),
    cwd=str(ROOT), text=True, capture_output=True)

after_real_trace_files = collect_real_trace_files()
new_real_trace_files = sorted(set(after_real_trace_files) - set(existing_real_trace_files))

checks = {
    "required_files_ok": not missing,
    "json_parse_ok": not json_errors,
    "all_four_scenarios_bound": not missing_scenarios,
    "template_identity_ok": not template_errors,
    "no_new_real_trace_generated": not new_real_trace_files,
    "task_validator_ok": task_proc.returncode == 0,
    "foundation_validator_ok": foundation_proc.returncode == 0,
    "global_krm_validator_ok": krm_proc.returncode == 0
}

result = "PASS" if all(checks.values()) else "FAIL"
report = {
    "stage": STAGE,
    "result": result,
    "checks": checks,
    "missing": missing,
    "json_errors": json_errors,
    "template_errors": template_errors,
    "missing_scenarios": missing_scenarios,
    "existing_real_trace_files": existing_real_trace_files,
    "new_real_trace_files": new_real_trace_files,
    "formal_pipeline_note": "This is a CCRT relay-package validation record, not actor/HMAC formal pipeline PASS."
}
if WRITE_REPORT:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
raise SystemExit(0 if result == "PASS" else 1)
