import json, os, hashlib
from datetime import datetime, timezone

LOG_DIR = "logs"

def _ensure_dir(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)

def append_log(log_type, data):
    spec = {
        "gate": ("gates/gate_check.jsonl", ["timestamp","run_id","gate","script","trigger","commit_sha","checks","overall_result","fail_reasons","duration_ms"]),
        "signature": ("signatures/signature_events.jsonl", ["timestamp","run_id","stage","role","action","checklist_version","signature","comment"]),
        "checklist_chg": ("checklist/checklist_changelog.jsonl", ["timestamp","run_id","modified_by","operation","diff_summary","previous_hash","new_hash"]),
        "ai_ops": ("ai_ops/ai_ops.jsonl", ["timestamp","run_id","stage","role","task_type","input_context_hash","output_summary","token_used","model","duration_ms","result","error_msg"]),
        "engine": ("engine/engine_events.jsonl", ["timestamp","run_id","event_type","from_stage","to_stage","target_role","package_files","override_reason"]),
        "deploy": ("deployments/verify_deploy.jsonl", ["timestamp","run_id","deploy_item","check_type","expected","actual","result"]),
        "audit": ("audit/audit_findings.jsonl", ["timestamp","finding_id","severity","category","related_run_id","description","evidence_log_paths","recommended_action","status"])
    }
    if log_type not in spec:
        raise ValueError("Unknown log type")
    rel_path, fields = spec[log_type]
    path = os.path.join(LOG_DIR, rel_path)
    _ensure_dir(path)
    record = {f: data.get(f) for f in fields}
    record["timestamp"] = record.get("timestamp") or datetime.now(timezone.utc).isoformat()
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

def sha256_file(filepath):
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            h.update(chunk)
    return h.hexdigest()
