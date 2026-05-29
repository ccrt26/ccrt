#!/usr/bin/env python3
import sys, json, os
from log_utils import append_log

def validate_checklist(checklist_path):
    with open(checklist_path, 'r') as f:
        data = json.load(f)
    errors = []
    # 必填字段检查
    for field in ["run_id","signoffs","items","deploy_items"]:
        if field not in data:
            errors.append(f"Missing field: {field}")
    # 检查每个需求项
    for item in data.get("items", []):
        for f in ["id","description","code_level","token_budget"]:
            if f not in item:
                errors.append(f"Item {item.get('id','?')} missing {f}")
    # 文件预算检查
    for f_budget in data.get("file_budgets", []):
        if f_budget.get("max_lines", 0) > 500:
            errors.append(f"File budget {f_budget['path']} exceeds 500 lines without exemption")
    if errors:
        append_log("gate", {
            "run_id": data.get("run_id"), "gate": "stage1_validate",
            "script": "pipeline_engine.py", "trigger": "manual",
            "checks": [{"check_name":"format","result":"FAIL"}],
            "overall_result": "FAIL", "fail_reasons": errors, "duration_ms": 0
        })
        print("FAIL", errors)
        sys.exit(1)
    print("PASS")
    append_log("gate", {
        "run_id": data.get("run_id"), "gate": "stage1_validate",
        "script": "pipeline_engine.py", "trigger": "manual",
        "checks": [{"check_name":"format","result":"PASS"}],
        "overall_result": "PASS", "fail_reasons": [], "duration_ms": 0
    })

if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--validate":
        validate_checklist(sys.argv[2])
