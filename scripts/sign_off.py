#!/usr/bin/env python3
"""
sign_off.py — HMAC 签名工具 (fix3)

用法: python3 sign_off.py --actor <操作者> --role <角色> --run-id <ID> --checklist <路径> [--comment "..."] [--audit-report <路径>]

安全机制:
- actor→role 白名单强制校验
- 阿黑 actor 只能扮演 阿黑 role, 且不得对业务阶段产生有效签名
- HMAC-SHA256 签名, 密钥不在 repo
"""
import sys, json, os, argparse
from datetime import datetime, timezone
from log_utils import (
    append_log, checklist_content_hash, hmac_sign, get_actor_secret,
    ACTOR_TO_ALLOWED_ROLES, VALID_ACTORS, VALID_ROLES, sha256_file,
)

STATE_FILE = os.environ.get("PIPELINE_STATE_FILE", ".claude/pipeline_active.json")


def load_state():
    if not os.path.exists(STATE_FILE):
        return {"runs": {}}
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {"runs": {}}


def sign_off(actor, role, run_id, checklist_path, comment="", audit_report_path=None):
    # 1. actor 白名单
    if actor not in VALID_ACTORS:
        print(f"错误: 非法 actor '{actor}'")
        sys.exit(1)

    # 2. actor→role 映射校验
    allowed = ACTOR_TO_ALLOWED_ROLES.get(actor, [])
    if role not in allowed:
        print(f"错误: actor '{actor}' 无权扮演 role '{role}'")
        print(f"  允许扮演: {allowed}")
        sys.exit(1)

    # 3. 阿黑 role 不能签任何业务阶段
    if role == "阿黑":
        print(f"错误: 阿黑不得对任何业务阶段产生有效签名")
        sys.exit(1)

    # 4. 检查 HMAC 密钥
    secret = get_actor_secret(actor)
    if not secret:
        print(f"错误: actor '{actor}' 无有效 HMAC 密钥。请设置 ACTOR_SECRET_{actor} 环境变量或 {os.environ.get('PIPELINE_SECRETS_FILE', '.claude/actor_secrets.json')}")
        sys.exit(1)

    # 5. checklist 存在性
    if not os.path.exists(checklist_path):
        print(f"错误: 清单文件不存在: {checklist_path}")
        sys.exit(1)

    try:
        with open(checklist_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"错误: JSON格式非法: {e}")
        sys.exit(1)

    c_run_id = data.get("run_id")
    if c_run_id != run_id:
        print(f"错误: run_id不匹配。清单:{c_run_id}, 提供:{run_id}")
        sys.exit(1)

    # 6. 审计报告 hash（如有）
    audit_report_hash = ""
    if audit_report_path:
        if not os.path.exists(audit_report_path):
            print(f"错误: 审计报告文件不存在: {audit_report_path}")
            sys.exit(1)
        audit_report_hash = sha256_file(audit_report_path)

    # 7. 阶段校验
    state = load_state()
    run = state.get("runs", {}).get(run_id)
    current_stage = run.get("current_stage", "unknown") if run else "unknown"

    # 8. 生成 HMAC 签名
    content_hash = checklist_content_hash(checklist_path)
    now_ts = datetime.now(timezone.utc).isoformat()
    git_sha = os.environ.get("GIT_COMMIT_SHA", "")

    signature = hmac_sign(
        actor, role, run_id, current_stage,
        content_hash, audit_report_hash, now_ts, git_sha, secret,
    )

    if not signature:
        print("错误: HMAC 签名生成失败")
        sys.exit(1)

    # 9. 写入 checklist
    if "signoffs" not in data:
        data["signoffs"] = {}

    data["signoffs"][role] = {
        "signed": True,
        "timestamp": now_ts,
        "stage": current_stage,
        "checklist_version": content_hash,
        "signature": signature,
        "sig_type": "HMAC-SHA256",
        "actor": actor,
        "git_sha": git_sha,
        "audit_report_hash": audit_report_hash,
        "comment": comment,
    }

    try:
        with open(checklist_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✓ {actor}→{role} HMAC签名成功")
        print(f"  需求: {run_id}")
        print(f"  阶段: {current_stage}")
        print(f"  清单指纹: {content_hash[:16]}...")
        print(f"  HMAC: {signature[:16]}...")
    except Exception as e:
        print(f"错误: 无法写入: {e}")
        sys.exit(1)

    # 10. 日志
    append_log("signature", {
        "run_id": run_id, "stage": current_stage, "role": role,
        "action": "sign", "checklist_version": content_hash,
        "signature": signature, "comment": f"[{actor}] {comment}",
    })
    append_log("checklist_chg", {
        "run_id": run_id, "modified_by": f"{actor}→{role}",
        "operation": "updated",
        "diff_summary": f"{actor}→{role}在{current_stage}HMAC签名",
        "previous_hash": "see log", "new_hash": content_hash,
    })

    print(f"  ✓ 日志已记录")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="铁律量化 - HMAC签名工具 (fix3)")
    p.add_argument("--actor", required=True, help="实际操作者")
    p.add_argument("--role", required=True, help="业务角色")
    p.add_argument("--run-id", required=True, help="需求ID")
    p.add_argument("--checklist", required=True, help="清单JSON路径")
    p.add_argument("--comment", default="", help="备注")
    p.add_argument("--audit-report", default=None, help="审计报告路径(P0 post_audit)")
    args = p.parse_args()
    sign_off(args.actor, args.role, args.run_id, args.checklist, args.comment, args.audit_report)
