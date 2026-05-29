#!/usr/bin/env python3
"""
check_checklist.py - 档案合规审查 (闸门1b 旧影侧)
检查清单JSON的格式合法性、签名完整性、A-F项非空。
任一FAIL → 打回阶段①
"""
import sys
import json
import os
from datetime import datetime, timezone
from log_utils import append_log

def check_checklist(checklist_path):
    """主检查逻辑"""
    # 1. 文件存在性
    if not os.path.exists(checklist_path):
        print(f"FAIL: 清单文件不存在: {checklist_path}")
        sys.exit(1)

    # 2. JSON格式合法性
    try:
        with open(checklist_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        record_fail(
            run_id="UNKNOWN",
            fail_reasons=[f"JSON格式非法: {str(e)}"]
        )
        print(f"FAIL: JSON格式非法: {e}")
        sys.exit(1)

    run_id = data.get("run_id", "UNKNOWN")
    errors = []

    # 3. 清单A-F段所有项 item 非空
    items = data.get("items", [])
    if not items:
        errors.append("A-F段为空: 清单没有任何需求项(items)")
    else:
        for idx, item in enumerate(items):
            item_id = item.get("id", f"索引{idx}")
            # 检查必填字段
            for field in ["id", "description", "white_paper_ref", "expected_output", "code_level"]:
                if not item.get(field):
                    errors.append(f"项[{item_id}]缺少必填字段: {field}")

    # 4. signoffs.情墨.signed == true ?
    signoffs = data.get("signoffs", {})
    if not signoffs.get("情墨", {}).get("signed"):
        errors.append("signoffs.情墨.signed != true: 情墨未签名")

    # 5. signoffs.腰子.signed == true ?
    if not signoffs.get("腰子", {}).get("signed"):
        errors.append("signoffs.腰子.signed != true: 腰子未签名")

    # 6. 判定结果
    if errors:
        record_fail(run_id=run_id, fail_reasons=errors)
        print(f"FAIL")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        record_pass(run_id=run_id)
        print("PASS: 清单格式合法，签名完整，所有项非空")
        sys.exit(0)


def record_fail(run_id, fail_reasons):
    """记录失败日志"""
    append_log("gate", {
        "run_id": run_id,
        "gate": "gate_1b",
        "script": "check_checklist.py",
        "trigger": "git-push",
        "commit_sha": os.environ.get("GIT_COMMIT_SHA", "unknown"),
        "checks": [
            {"check_name": "checklist_validation", "result": "FAIL"}
        ],
        "overall_result": "FAIL",
        "fail_reasons": fail_reasons,
        "duration_ms": 0
    })


def record_pass(run_id):
    """记录通过日志"""
    append_log("gate", {
        "run_id": run_id,
        "gate": "gate_1b",
        "script": "check_checklist.py",
        "trigger": "git-push",
        "commit_sha": os.environ.get("GIT_COMMIT_SHA", "unknown"),
        "checks": [
            {"check_name": "checklist_validation", "result": "PASS"}
        ],
        "overall_result": "PASS",
        "fail_reasons": [],
        "duration_ms": 0
    })


if __name__ == "__main__":
    if len(sys.argv) > 1:
        check_checklist(sys.argv[1])
    else:
        print("用法: python check_checklist.py <清单JSON路径>")
        sys.exit(1)
