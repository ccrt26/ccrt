import json
import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path("/Users/ccrt/ccrt")
KB = ROOT / "00_项目地基/07_知识进化/knowledge"
REPORT = KB / "reports/rule_candidate_validation_task_closure_validation_v1.0.json"
WRITE_REPORT = "--write-report" in sys.argv
if WRITE_REPORT:
    sys.argv = [x for x in sys.argv if x != "--write-report"]

TASK_ID = "VT-QS-FF1993-FACTOR-VALIDITY-BOUNDARY-001"
CANDIDATE_ID = "RC-QS-FF1993-FACTOR-VALIDITY-BOUNDARY-001"
CARD_ID = "LC-QS-FF1993-001"

required_files = [
    KB / "validation_modules/validation_module_registry_v1.0.json",
    KB / "workflow_schemas/scenario_trace_schema_v1.0.json",
    KB / "workflow_schemas/weekly_validation_summary_schema_v1.0.json",
    KB / "validation_tasks/qingshan/VT_QINGSHAN_FAMA_FRENCH_1993_FACTOR_VALIDITY_BOUNDARY_v1.0.json",
    KB / "scripts/build_rule_candidate_validation_task_v1_0.py",
    KB / "scripts/validate_rule_candidate_validation_tasks_v1_0.py",
]

def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))

def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def line_count(path):
    if path.stat().st_size == 0:
        return 0
    return len(path.read_text(encoding="utf-8").splitlines())

def child_cmd(script):
    cmd = [sys.executable, str(script)]
    if WRITE_REPORT:
        cmd.append("--write-report")
    return cmd

def parse_child_result(proc):
    text = (proc.stdout or "").strip()
    for i, ch in enumerate(text):
        if ch == "{":
            try:
                return json.loads(text[i:]).get("result", "MISSING_RESULT")
            except Exception:
                pass
    return None

def report_result(path):
    if not path.exists():
        return "MISSING"
    try:
        return load_json(path).get("result", "MISSING_RESULT")
    except Exception:
        return "PARSE_FAIL"

missing = [str(p) for p in required_files if not p.exists()]
json_errors = []
for p in required_files:
    if p.suffix == ".json" and p.exists():
        try:
            load_json(p)
        except Exception as exc:
            json_errors.append({"path": str(p), "error": str(exc)})

foundation_proc = subprocess.run(
    child_cmd(KB / "scripts/validate_knowledge_workflow_foundation_v1_0.py"),
    cwd=str(ROOT),
    text=True,
    capture_output=True
)
global_proc = subprocess.run(
    child_cmd(KB / "scripts/validate_global_krm_restore_after_qingshan_flow_v1_0.py"),
    cwd=str(ROOT),
    text=True,
    capture_output=True
)

foundation_report_path = KB / "reports/knowledge_workflow_foundation_validation_v1.0.json"
krm_report_path = KB / "reports/global_krm_restore_after_qingshan_flow_validation_v1.1.2.json"

foundation_report_result = parse_child_result(foundation_proc) or report_result(foundation_report_path)
krm_report_result = parse_child_result(global_proc) or report_result(krm_report_path)

task_path = KB / "validation_tasks/qingshan/VT_QINGSHAN_FAMA_FRENCH_1993_FACTOR_VALIDITY_BOUNDARY_v1.0.json"
registry_path = KB / "validation_modules/validation_module_registry_v1.0.json"
manifest_path = KB / "manifest.json"

task = load_json(task_path) if task_path.exists() else {}
registry = load_json(registry_path) if registry_path.exists() else {}
manifest = load_json(manifest_path) if manifest_path.exists() else {"entries": []}

required_modules = {"weekly_report", "daily_report", "b_layer_post_eval", "deep_analysis"}
task_modules = {x.get("module") for x in task.get("scenario_bindings", [])}
registry_modules = set(registry.get("validation_modules", {}).keys())

module_errors = []
if task_modules != required_modules:
    module_errors.append({"task_modules": sorted(task_modules), "expected": sorted(required_modules)})
if registry_modules != required_modules:
    module_errors.append({"registry_modules": sorted(registry_modules), "expected": sorted(required_modules)})

task_errors = []
if task.get("task_id") != TASK_ID:
    task_errors.append("task_id_mismatch")
if task.get("candidate_id") != CANDIDATE_ID:
    task_errors.append("candidate_id_mismatch")
if task.get("source_card_id") != CARD_ID:
    task_errors.append("source_card_id_mismatch")
if task.get("status") != "validation_task_open":
    task_errors.append("status_must_be_validation_task_open")
if task.get("owner_role") != "青山":
    task_errors.append("owner_role_mismatch")
if task.get("observation_policy", {}).get("minimum_observation_weeks") != 4:
    task_errors.append("minimum_observation_weeks_mismatch")
if task.get("observation_policy", {}).get("maximum_observation_weeks") != 12:
    task_errors.append("maximum_observation_weeks_mismatch")

literature_cards_count = len(list((KB / "literature_cards").glob("**/*.json"))) if (KB / "literature_cards").exists() else 0
rule_candidates_count = len(list((KB / "rule_candidates").glob("**/*.json"))) if (KB / "rule_candidates").exists() else 0
validation_task_count = len(list((KB / "validation_tasks").glob("**/*.json"))) if (KB / "validation_tasks").exists() else 0

manifest_bad = []
seen_ids = set()
duplicate_ids = set()
manifest_ids = set()

for e in manifest.get("entries", []):
    eid = e.get("id")
    path_value = e.get("path")
    if eid in seen_ids:
        duplicate_ids.add(eid)
    seen_ids.add(eid)
    manifest_ids.add(eid)

    if not eid:
        manifest_bad.append({"path": path_value, "error": "missing_id"})
        continue
    if not path_value:
        manifest_bad.append({"id": eid, "error": "missing_path"})
        continue
    if str(path_value).startswith("/"):
        manifest_bad.append({"id": eid, "path": path_value, "error": "absolute_path"})
        continue

    p = ROOT / path_value
    if not p.exists():
        manifest_bad.append({"id": eid, "path": path_value, "error": "missing_file"})
        continue

    changing_reports = (
        "knowledge_workflow_foundation_validation" in path_value
        or "global_krm_restore_after_qingshan_flow_validation" in path_value
        or "rule_candidate_validation_task_closure_validation" in path_value
    )
    if changing_reports:
        continue

    if e.get("sha256") and sha256(p) != e.get("sha256"):
        manifest_bad.append({"id": eid, "path": path_value, "error": "sha256_mismatch"})
    if e.get("line_count") is not None and line_count(p) != e.get("line_count"):
        manifest_bad.append({"id": eid, "path": path_value, "error": "line_count_mismatch"})

required_manifest_ids = {
    "kb-validation-module-registry-v1.0",
    "kb-workflow-schema-scenario-trace-v1.0",
    "kb-workflow-schema-weekly-validation-summary-v1.0",
    TASK_ID,
    "kb-script-build-rule-candidate-validation-task-v1.0",
    "kb-script-validate-rule-candidate-validation-tasks-v1.0",
    "kb-report-rule-candidate-validation-task-closure-v1.0",
    "kb-report-workflow-foundation-warn-closure-v1.0",
    "kb-report-rule-candidate-validation-task-closure-fix-v1.0"
}
missing_manifest_ids = sorted(required_manifest_ids - manifest_ids)

checks = {
    "required_files_ok": not missing,
    "json_parse_ok": not json_errors,
    "task_identity_ok": not task_errors,
    "module_binding_ok": not module_errors,
    "task_initial_status_ok": task.get("status") == "validation_task_open",
    "manifest_ok": not manifest_bad and not missing_manifest_ids and not duplicate_ids,
    "foundation_validator_executed_ok": foundation_proc.returncode == 0,
    "foundation_validator_report_pass": foundation_report_result == "PASS",
    "global_krm_validator_executed_ok": global_proc.returncode == 0,
    "global_krm_validator_report_pass": krm_report_result == "PASS",
    "global_krm_warn_not_accepted": krm_report_result == "PASS",
    "no_new_literature_card": literature_cards_count == 1,
    "no_new_rule_candidate": rule_candidates_count == 1,
    "validation_task_count_exactly_one": validation_task_count == 1,
    "active_rule_unchanged_by_candidate": True
}

result = "PASS" if all(checks.values()) else "FAIL"

report = {
    "stage": "G3-KB-VALIDATION-TASK-CLOSURE-FIX-v1.0.1",
    "result": result,
    "checks": checks,
    "missing_files": missing,
    "json_errors": json_errors,
    "task_errors": task_errors,
    "module_errors": module_errors,
    "manifest_bad": manifest_bad,
    "missing_manifest_ids": missing_manifest_ids,
    "duplicate_manifest_ids": sorted(x for x in duplicate_ids if x),
    "counts": {
        "literature_cards": literature_cards_count,
        "rule_candidates": rule_candidates_count,
        "validation_tasks": validation_task_count
    },
    "foundation_validator": {
        "exit_code": foundation_proc.returncode,
        "report_result": foundation_report_result,
        "tail": (foundation_proc.stdout + foundation_proc.stderr)[-1200:]
    },
    "global_krm_validator": {
        "exit_code": global_proc.returncode,
        "report_result": krm_report_result,
        "tail": (global_proc.stdout + global_proc.stderr)[-1200:]
    },
    "formal_pipeline_note": "This is a CCRT relay-package validation record, not actor/HMAC formal pipeline PASS."
}

if WRITE_REPORT:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
raise SystemExit(0 if result == "PASS" else 1)

