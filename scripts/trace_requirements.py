#!/usr/bin/env python3
"""
trace_requirements.py - 需求追溯稽查 (闸门2 新安侧)
检查所有 code_ref 非空、指向文件存在、coder_ok == true。
任一项FAIL → 打回红结
"""
import sys
import json
import os
from log_utils import append_log

def trace_requirements(checklist_path):
    """主追溯逻辑"""
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
    items = data.get("items", [])
    errors = []

    if not items:
        errors.append("清单无需求项，无法追溯")

    for item in items:
        item_id = item.get("id", "未知项")

        # 检查 code_ref 非空
        code_ref = item.get("code_ref")
        if not code_ref:
            errors.append(f"项[{item_id}]: code_ref 为空，未回填代码引用")
            continue

        # 检查 coder_ok == true
        if not item.get("coder_ok"):
            errors.append(f"项[{item_id}]: coder_ok != true，红结未确认编码完成")

        # 检查 code_ref 指向的文件是否存在
        # code_ref 格式: "文件路径:行号" 或 "文件路径"
        file_path = code_ref.split(":")[0] if ":" in code_ref else code_ref
        if not os.path.exists(file_path):
            errors.append(f"项[{item_id}]: code_ref 指向的文件不存在: {file_path}")

    # 判定
    if errors:
        append_log("gate", {
            "run_id": run_id,
            "gate": "gate_2",
            "script": "trace_requirements.py",
            "trigger": "ci-pipeline",
            "commit_sha": os.environ.get("GIT_COMMIT_SHA", "unknown"),
            "checks": [
                {"check_name": "requirement_trace", "result": "FAIL"}
            ],
            "overall_result": "FAIL",
            "fail_reasons": errors,
            "duration_ms": 0
        })
        print("FAIL: 需求追溯不通过")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        append_log("gate", {
            "run_id": run_id,
            "gate": "gate_2",
            "script": "trace_requirements.py",
            "trigger": "ci-pipeline",
            "commit_sha": os.environ.get("GIT_COMMIT_SHA", "unknown"),
            "checks": [
                {"check_name": "requirement_trace", "result": "PASS"}
            ],
            "overall_result": "PASS",
            "fail_reasons": [],
            "duration_ms": 0
        })
        print("PASS: 所有需求项已追溯，code_ref有效，coder_ok确认")
        sys.exit(0)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        trace_requirements(sys.argv[1])
    else:
        print("用法: python trace_requirements.py <清单JSON路径>")
        sys.exit(1)
