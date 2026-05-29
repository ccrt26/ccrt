#!/usr/bin/env python3
"""
sign_off.py - 角色签名工具
用法: python sign_off.py --role <角色名> --run-id <需求ID> --checklist <清单JSON路径> [--comment "备注"]
"""
import sys
import json
import os
import hashlib
from datetime import datetime, timezone
from log_utils import append_log, sha256_file


def sign_off(role, run_id, checklist_path, comment=""):
    """执行签名操作"""

    # 1. 验证清单文件存在
    if not os.path.exists(checklist_path):
        print(f"错误: 清单文件不存在: {checklist_path}")
        sys.exit(1)

    # 2. 读取清单
    try:
        with open(checklist_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"错误: JSON格式非法: {e}")
        sys.exit(1)

    # 3. 验证 run_id 一致
    if data.get("run_id") != run_id:
        print(f"错误: run_id不匹配。清单中是: {data.get('run_id')}, 你提供的是: {run_id}")
        sys.exit(1)

    # 4. 生成清单版本指纹
    checklist_hash = sha256_file(checklist_path)

    # 5. 生成签名（简化版：用角色名+run_id+清单指纹做哈希）
    sign_content = f"{role}|{run_id}|{checklist_hash}"
    signature = hashlib.sha256(sign_content.encode()).hexdigest()

    # 6. 更新清单中的签名字段
    if "signoffs" not in data:
        data["signoffs"] = {}

    data["signoffs"][role] = {
        "signed": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checklist_version": checklist_hash,
        "signature": signature,
        "comment": comment
    }

    # 7. 写回清单文件
    try:
        with open(checklist_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✓ {role} 签名成功")
        print(f"  需求: {run_id}")
        print(f"  清单版本: {checklist_hash[:16]}...")
        print(f"  签名: {signature[:16]}...")
    except Exception as e:
        print(f"错误: 无法写入清单文件: {e}")
        sys.exit(1)

    # 8. 记录签名事件日志
    append_log("signature", {
        "run_id": run_id,
        "stage": get_current_stage(data),
        "role": role,
        "action": "sign",
        "checklist_version": checklist_hash,
        "signature": signature,
        "comment": comment
    })

    # 9. 记录清单变更日志
    append_log("checklist_chg", {
        "run_id": run_id,
        "modified_by": role,
        "operation": "updated",
        "diff_summary": f"{role}签名已添加",
        "previous_hash": "see log",
        "new_hash": checklist_hash
    })

    # 10. 记录AI操作日志
    append_log("ai_ops", {
        "run_id": run_id,
        "stage": get_current_stage(data),
        "role": role,
        "task_type": "sign_off",
        "input_context_hash": checklist_hash,
        "output_summary": f"{role}完成签名",
        "token_used": 0,
        "model": "local_script",
        "duration_ms": 0,
        "result": "success",
        "error_msg": ""
    })

    print(f"  ✓ 日志已记录")


def get_current_stage(data):
    """根据已有签名推断当前阶段"""
    signoffs = data.get("signoffs", {})
    if not signoffs.get("情墨", {}).get("signed"):
        return "stage1_design"
    if not signoffs.get("腰子", {}).get("signed"):
        return "stage1a_review"
    if not signoffs.get("红结", {}).get("signed"):
        return "stage4_coding"
    if not signoffs.get("红枫", {}).get("signed"):
        return "stage6_deploy"
    return "stage7_done"


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="铁律量化项目 - 角色签名工具")
    parser.add_argument("--role", required=True, help="签名角色名")
    parser.add_argument("--run-id", required=True, help="需求ID")
    parser.add_argument("--checklist", required=True, help="清单JSON文件路径")
    parser.add_argument("--comment", default="", help="签名备注")

    args = parser.parse_args()
    sign_off(args.role, args.run_id, args.checklist, args.comment)
