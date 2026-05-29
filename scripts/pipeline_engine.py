#!/usr/bin/env python3
"""
pipeline_engine.py - 流程引擎（校验和状态推进）
用法: python pipeline_engine.py --validate <清单JSON路径>
"""
import sys
import json
import os
from datetime import datetime, timezone
from log_utils import append_log


def validate_checklist(checklist_path):
    """主校验逻辑"""
    if not os.path.exists(checklist_path):
        print(f"FAIL: 清单文件不存在: {checklist_path}")
        sys.exit(1)

    try:
        with open(checklist_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"FAIL: JSON格式非法: {e}")
        sys.exit(1)

    run_id = data.get("run_id", "UNKNOWN")
    errors = []

    # 必填字段检查
    for field in ["run_id", "signoffs", "items", "deploy_items"]:
        if field not in data:
            errors.append(f"Missing field: {field}")

    # 检查每个需求项
    for item in data.get("items", []):
        for f in ["id", "description", "code_level", "token_budget"]:
            if f not in item:
                errors.append(f"Item {item.get('id', '?')} missing {f}")

    # 文件预算检查
    for f_budget in data.get("file_budgets", []):
        if f_budget.get("max_lines", 0) > 500:
            errors.append(f"File budget {f_budget['path']} exceeds 500 lines without exemption")

    # 记录 engine 事件：校验开始
    append_log("engine", {
        "run_id": run_id,
        "event_type": "validate_start",
        "from_stage": "design",
        "to_stage": "design",
        "target_role": "情墨",
        "package_files": [checklist_path],
        "override_reason": ""
    })

    if errors:
        append_log("gate", {
            "run_id": run_id,
            "gate": "stage1_validate",
            "script": "pipeline_engine.py",
            "trigger": "manual",
            "commit_sha": os.environ.get("GIT_COMMIT_SHA", "unknown"),
            "checks": [{"check_name": "format", "result": "FAIL"}],
            "overall_result": "FAIL",
            "fail_reasons": errors,
            "duration_ms": 0
        })
        append_log("engine", {
            "run_id": run_id,
            "event_type": "validate_fail",
            "from_stage": "design",
            "to_stage": "design",
            "target_role": "情墨",
            "package_files": [],
            "override_reason": f"校验失败: {errors}"
        })
        print("FAIL")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        append_log("gate", {
            "run_id": run_id,
            "gate": "stage1_validate",
            "script": "pipeline_engine.py",
            "trigger": "manual",
            "commit_sha": os.environ.get("GIT_COMMIT_SHA", "unknown"),
            "checks": [{"check_name": "format", "result": "PASS"}],
            "overall_result": "PASS",
            "fail_reasons": [],
            "duration_ms": 0
        })
        append_log("engine", {
            "run_id": run_id,
            "event_type": "validate_pass",
            "from_stage": "design",
            "to_stage": "review_1a",
            "target_role": "腰子",
            "package_files": [checklist_path],
            "override_reason": ""
        })
        print("PASS: 清单校验通过，流程可进入下一阶段")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--validate":
        validate_checklist(sys.argv[2])
    else:
        print("用法: python pipeline_engine.py --validate <清单JSON路径>")
        sys.exit(1)
