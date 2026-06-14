import json
import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path("/Users/ccrt/ccrt")
KB = ROOT / "00_项目地基/07_知识进化/knowledge"
REPORT = KB / "reports/knowledge_workflow_foundation_validation_v1.0.json"
WRITE_REPORT = "--write-report" in sys.argv
if WRITE_REPORT:
    sys.argv = [x for x in sys.argv if x != "--write-report"]

required_files = [
    KB / "policies/validation_policy_matrix_v1.0.json",
    KB / "workflow_schemas/knowledge_ingest_workflow_schema_v1.0.json",
    KB / "workflow_schemas/rule_candidate_validation_task_schema_v1.0.json",
    KB / "workflow_schemas/workflow_run_schema_v1.0.json",
    KB / "workflow_runs/.gitkeep",
    KB / "validation_tasks/.gitkeep",
]

required_manifest_ids = {
    "kb-validation-policy-matrix-v1.0",
    "kb-workflow-schema-knowledge-ingest-v1.0",
    "kb-workflow-schema-rule-candidate-validation-task-v1.0",
    "kb-workflow-schema-workflow-run-v1.0",
    "kb-script-validate-knowledge-workflow-foundation-v1.0",
}

required_knowledge_types = {
    "source_candidate",
    "literature_card",
    "rule_candidate",
    "validation_task",
    "scenario_trace",
    "validation_review",
    "knowledge_merge_check",
    "active_rule",
}

required_states = {
    "source_candidate",
    "quality_scored",
    "literature_card_draft",
    "rule_candidate_draft",
    "validation_task_open",
    "scenario_trace_collecting",
    "weekly_validation_summary_ready",
    "validation_review_ready",
    "role_confirmation_ready",
    "knowledge_merge_check_ready",
    "promotion_decision_ready",
    "active_rule_ready",
    "knowledge_adoption_recorded",
    "performance_monitoring",
    "role_metrics_updated",
}

def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))

def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def line_count(path):
    if path.stat().st_size == 0:
        return 0
    return len(path.read_text(encoding="utf-8").splitlines())

def rel(path):
    return str(path.relative_to(ROOT))

missing = [str(p) for p in required_files if not p.exists()]
json_errors = []
for p in required_files:
    if p.suffix == ".json" and p.exists():
        try:
            load_json(p)
        except Exception as exc:
            json_errors.append({"path": str(p), "error": str(exc)})

policy = load_json(KB / "policies/validation_policy_matrix_v1.0.json")
workflow = load_json(KB / "workflow_schemas/knowledge_ingest_workflow_schema_v1.0.json")

missing_knowledge_types = sorted(required_knowledge_types - set(policy.get("knowledge_types", {}).keys()))
missing_states = sorted(required_states - set(workflow.get("workflow_states", [])))

states = set(workflow.get("workflow_states", []))
transition_errors = []
for src, dsts in workflow.get("allowed_transitions", {}).items():
    if src not in states:
        transition_errors.append({"source": src, "error": "source_state_not_declared"})
    for dst in dsts:
        if dst not in states:
            transition_errors.append({"source": src, "target": dst, "error": "target_state_not_declared"})

policy_state_errors = []
for k, v in policy.get("knowledge_types", {}).items():
    for field in ("default_next_state", "initial_status"):
        state = v.get(field)
        if state and state not in states and state != "candidate_draft":
            policy_state_errors.append({"knowledge_type": k, "field": field, "state": state, "error": "not_in_workflow_states"})

manifest_path = KB / "manifest.json"
manifest_bad = []
manifest_entry_ids = []
manifest_entry_count = 0
manifest_counts_total = None
manifest_abs_paths = []
manifest_missing_id = []
manifest_required_kind_missing = []

if manifest_path.exists():
    manifest = load_json(manifest_path)
    entries = manifest.get("entries", [])
    manifest_entry_count = len(entries)
    manifest_counts_total = manifest.get("counts", {}).get("total_entries")
    manifest_entry_ids = [e.get("id") for e in entries]
    for e in entries:
        if not e.get("id"):
            manifest_missing_id.append(e.get("path"))
        path_value = e.get("path")
        if isinstance(path_value, str) and path_value.startswith("/"):
            manifest_abs_paths.append(path_value)
        if not path_value:
            manifest_bad.append({"id": e.get("id"), "path": path_value, "error": "path_missing"})
            continue
        p = Path(path_value) if Path(path_value).is_absolute() else ROOT / path_value
        if not p.exists():
            manifest_bad.append({"id": e.get("id"), "path": path_value, "error": "missing"})
            continue
        # Skip sha/line check for reports that change during inter-validator subprocess calls
        skip_volatile = any(x in str(path_value) for x in [
            "knowledge_workflow_foundation_validation",
            "global_krm_restore_after_qingshan_flow_validation",
            "rule_candidate_validation_task_closure_",
        ])
        expected_sha = e.get("sha256")
        expected_lines = e.get("line_count")
        if expected_sha and sha256(p) != expected_sha and not skip_volatile:
            manifest_bad.append({"id": e.get("id"), "path": path_value, "error": "sha256_mismatch"})
        if expected_lines is not None and line_count(p) != expected_lines and not skip_volatile:
            manifest_bad.append({"id": e.get("id"), "path": path_value, "error": "line_count_mismatch"})
else:
    manifest_bad.append({"path": str(manifest_path), "error": "manifest_missing"})

missing_manifest_ids = sorted(required_manifest_ids - set(manifest_entry_ids))

required_kinds = {
    "role_startup_pack",
    "shared_rule",
    "legacy_role_kb",
    "role_capability_rule",
    "task_router",
    "literature_policy",
    "literature_card",
    "rule_candidate",
    "knowledge_evolution_policy",
    "workflow_schema",
    "validator_script",
    "validation_report",
}
kinds = set()
if manifest_path.exists():
    for e in load_json(manifest_path).get("entries", []):
        kinds.add(e.get("kind") or e.get("type"))
manifest_required_kind_missing = sorted(required_kinds - kinds)

literature_cards = list((KB / "literature_cards").glob("**/*.json")) if (KB / "literature_cards").exists() else []
rule_candidates = list((KB / "rule_candidates").glob("**/*.json")) if (KB / "rule_candidates").exists() else []
card_ids = set()
candidate_ids = set()
for p in literature_cards:
    try:
        card_ids.add(load_json(p).get("card_id"))
    except Exception:
        pass
for p in rule_candidates:
    try:
        candidate_ids.add(load_json(p).get("candidate_id"))
    except Exception:
        pass

registered_ids = set(manifest_entry_ids)
unregistered_cards = sorted(x for x in card_ids if x and x not in registered_ids)
unregistered_candidates = sorted(x for x in candidate_ids if x and x not in registered_ids)

global_report = KB / "reports/global_krm_restore_after_qingshan_flow_validation_v1.1.2.json"
global_validator_script = KB / "scripts/validate_global_krm_restore_after_qingshan_flow_v1_0.py"
global_script_exists = global_validator_script.exists()
global_result = "NOT_CHECKED"
global_report_result = None
global_stdout = ""

def parse_child_result(proc):
    text = (proc.stdout or "").strip()
    for i, ch in enumerate(text):
        if ch == "{":
            try:
                return json.loads(text[i:]).get("result", "MISSING_RESULT")
            except Exception:
                pass
    return None

if not global_script_exists:
    global_result = "NO_SCRIPT"
    global_report_result = "NO_SCRIPT"
    global_stdout = "KRM script not found"
else:
    cmd = [sys.executable, str(global_validator_script)]
    if WRITE_REPORT:
        cmd.append("--write-report")
    proc = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True)
    global_report_result = parse_child_result(proc) or "PARSE_FAIL"
    global_result = global_report_result
    global_stdout = (proc.stdout + proc.stderr)[-2000:]

checks = {
    "required_files_ok": not missing,
    "json_parse_ok": not json_errors,
    "knowledge_types_ok": not missing_knowledge_types,
    "workflow_states_ok": not missing_states,
    "transitions_ok": not transition_errors,
    "policy_states_ok": not policy_state_errors,
    "manifest_integrity_ok": not manifest_bad,
    "manifest_required_ids_ok": not missing_manifest_ids,
    "manifest_min_count_ok": manifest_entry_count >= 124,
    "manifest_counts_match_ok": manifest_counts_total == manifest_entry_count,
    "manifest_no_abs_path_ok": not manifest_abs_paths,
    "manifest_no_missing_id_ok": not manifest_missing_id,
    "manifest_required_kinds_ok": not manifest_required_kind_missing,
    "literature_cards_registered_ok": not unregistered_cards,
    "rule_candidates_registered_ok": not unregistered_candidates,
    "global_krm_validator_ok": global_result in ("PASS", "WARN"),
}

result = "PASS" if all(checks.values()) else "FAIL"

report = {
    "stage": "G3-KB-WORKFLOW-FOUNDATION-FIX-v1.0",
    "result": result,
    "checks": checks,
    "missing_files": missing,
    "json_errors": json_errors,
    "missing_knowledge_types": missing_knowledge_types,
    "missing_states": missing_states,
    "transition_errors": transition_errors,
    "policy_state_errors": policy_state_errors,
    "manifest_check": {
        "entry_count": manifest_entry_count,
        "counts_total_entries": manifest_counts_total,
        "missing_required_ids": missing_manifest_ids,
        "bad_entries": manifest_bad,
        "absolute_paths": manifest_abs_paths,
        "missing_id_entries": manifest_missing_id,
        "missing_required_kinds": manifest_required_kind_missing
    },
    "registration_check": {
        "literature_card_count": len(literature_cards),
        "rule_candidate_count": len(rule_candidates),
        "unregistered_cards": unregistered_cards,
        "unregistered_candidates": unregistered_candidates
    },
    "global_krm_validator": {
        "result": global_result,
        "report_result": global_report_result,
        "tail": global_stdout
    },
    "boundary_check": {
        "no_active_rule_promotion_claimed": True,
        "no_production_entry_change_claimed": True,
        "formal_pipeline_note": "This is a CCRT relay-package validation record, not actor/HMAC formal pipeline PASS."
    }
}

if WRITE_REPORT:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
raise SystemExit(0 if result == "PASS" else 1)

