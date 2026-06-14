#!/usr/bin/env python3
"""
sign_off.py — HMAC 签名工具 (v4.0 — actual_actor binding)

用法: python3 sign_off.py --actor <申请者> --role <申请角色> --run-id <ID> --checklist <路径>

actual_actor 来自环境变量(不可伪造)，CLI --actor 降级为 requested_actor。
actual_actor != requested_role → BLOCK
actual_actor == 阿黑 → BLOCK
"""
import sys, json, os, argparse
from datetime import datetime, timezone
from log_utils import (
    append_log, checklist_content_hash, hmac_sign, get_actor_secret,
    ACTOR_TO_ALLOWED_ROLES, VALID_ACTORS, VALID_ROLES, sha256_file,
)

STATE_FILE = os.environ.get("PIPELINE_STATE_FILE", ".claude/pipeline_active.json")

# Stage → allowed signer roles
STAGE_SIGNERS = {
    "design": ["情墨"],
    "review_1a": ["腰子"],
    "consult": ["山猫", "信鸽", "玉夜", "流金", "青山"],
    "review_1b": ["旧影", "新安"],
    "coding": ["红结"],
    "verify": ["新安"],
    "deploy": ["红枫"],
    "deploy_verify": ["旧影"],
    "audit": ["旧影"],
    "post_audit": ["旧影"],
}

# 阿黑禁止的动作
AHEI_FORBIDDEN_ACTIONS = {"sign", "advance", "complete", "deploy", "verify", "audit", "coding"}


def get_actual_actor():
    """Read actual_actor from non-forgeable context."""
    for key in ["CLAUDE_CURRENT_ACTOR", "CURRENT_ACTOR"]:
        val = os.environ.get(key, "").strip()
        if val:
            return val
    # Check session identity file
    id_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           ".claude", "current_actor")
    if os.path.exists(id_file):
        try:
            with open(id_file, 'r') as f:
                val = f.read().strip()
                if val:
                    return val
        except Exception:
            pass
    return ""


def get_session_id():
    return os.environ.get("CLAUDE_SESSION_ID", os.environ.get("SESSION_ID", ""))


def load_state():
    if not os.path.exists(STATE_FILE):
        return {"runs": {}}
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {"runs": {}}


def sign_off(requested_actor, requested_role, run_id, checklist_path, comment="", audit_report_path=None):
    actual_actor = get_actual_actor()
    session_id = get_session_id()
    pid = str(os.getpid())

    # 1. Determine actor identity. Formal signoff requires actor-bound identity.
    if not actual_actor:
        print("BLOCK: actual_actor 无法从环境识别，拒绝 transitional 签名")
        append_log("signature", {
            "run_id": run_id, "stage": "", "role": requested_role,
            "requested_actor": requested_actor, "requested_role": requested_role,
            "actual_actor": "", "actual_role": "",
            "action": "sign", "decision": "BLOCK",
            "reason": "actual_actor missing",
            "checklist_version": "", "signature": "",
            "comment": comment, "session_id": session_id, "process_id": pid,
            "command_source": " ".join(sys.argv),
        })
        sys.exit(1)

    effective_actor = actual_actor
    decision_reason = ""

    # 3. actual_actor != requested_role → BLOCK
    if actual_actor and actual_actor != requested_role:
        print(f"BLOCK: actual_actor({actual_actor}) != requested_role({requested_role})")
        print(f"  你不能以 {effective_actor} 身份签 {requested_role} 的名")
        append_log("signature", {
            "run_id": run_id, "stage": "", "role": requested_role,
            "requested_actor": requested_actor, "requested_role": requested_role,
            "actual_actor": actual_actor, "actual_role": actual_actor,
            "action": "sign", "decision": "BLOCK",
            "reason": f"actual_actor({actual_actor}) != requested_role({requested_role})",
            "checklist_version": "", "signature": "",
            "comment": comment, "session_id": session_id, "process_id": pid,
            "command_source": " ".join(sys.argv),
        })
        sys.exit(1)

    # 4. 阿黑 → BLOCK
    if effective_actor == "阿黑":
        print(f"BLOCK: 阿黑不得执行签名操作")
        append_log("signature", {
            "run_id": run_id, "stage": "", "role": requested_role,
            "requested_actor": requested_actor, "requested_role": requested_role,
            "actual_actor": actual_actor, "actual_role": actual_actor,
            "action": "sign", "decision": "BLOCK",
            "reason": "阿黑不得签名", "checklist_version": "", "signature": "",
            "comment": comment, "session_id": session_id, "process_id": pid,
            "command_source": " ".join(sys.argv),
        })
        sys.exit(1)

    # 5. actor→role 映射校验
    allowed = ACTOR_TO_ALLOWED_ROLES.get(effective_actor, [])
    if requested_role not in allowed:
        print(f"错误: actor '{effective_actor}' 无权扮演 role '{requested_role}'")
        print(f"  允许扮演: {allowed}")
        sys.exit(1)

    # 6. HMAC 密钥
    secret = get_actor_secret(effective_actor)
    if not secret:
        print(f"错误: actor '{effective_actor}' 无有效 HMAC 密钥")
        sys.exit(1)

    # 7. checklist 存在性
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

    # 8. 阶段校验
    state = load_state()
    run = state.get("runs", {}).get(run_id)
    current_stage = run.get("current_stage", "unknown") if run else "unknown"

    # 检查角色是否允许在当前阶段签名
    allowed_signers = STAGE_SIGNERS.get(current_stage, [])
    if allowed_signers and requested_role not in allowed_signers:
        print(f"BLOCK: role({requested_role}) 不在阶段({current_stage})的允许签名者中")
        print(f"  允许: {allowed_signers}")
        append_log("signature", {
            "run_id": run_id, "stage": current_stage, "role": requested_role,
            "requested_actor": requested_actor, "requested_role": requested_role,
            "actual_actor": actual_actor, "actual_role": actual_actor,
            "action": "sign", "decision": "BLOCK",
            "reason": f"role({requested_role}) not allowed in stage({current_stage})",
            "checklist_version": "", "signature": "",
            "comment": comment, "session_id": session_id, "process_id": pid,
            "command_source": " ".join(sys.argv),
        })
        sys.exit(1)

    # 9. 审计报告 hash（如有）
    audit_report_hash = ""
    if audit_report_path:
        if not os.path.exists(audit_report_path):
            print(f"错误: 审计报告文件不存在: {audit_report_path}")
            sys.exit(1)
        audit_report_hash = sha256_file(audit_report_path)

    # 10. HMAC 签名
    content_hash = checklist_content_hash(checklist_path)
    now_ts = datetime.now(timezone.utc).isoformat()
    git_sha = os.environ.get("GIT_COMMIT_SHA", "")

    signature = hmac_sign(
        effective_actor, requested_role, run_id, current_stage,
        content_hash, audit_report_hash, now_ts, git_sha, secret,
    )

    if not signature:
        print("错误: HMAC 签名生成失败")
        sys.exit(1)

    # 11. 写入 checklist
    if "signoffs" not in data:
        data["signoffs"] = {}

    data["signoffs"][requested_role] = {
        "signed": True,
        "timestamp": now_ts,
        "stage": current_stage,
        "checklist_version": content_hash,
        "signature": signature,
        "sig_type": "HMAC-SHA256",
        "actor": effective_actor,
        "requested_actor": requested_actor,
        "actual_actor": actual_actor,
        "git_sha": git_sha,
        "audit_report_hash": audit_report_hash,
        "comment": comment,
    }

    try:
        with open(checklist_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✓ {effective_actor}→{requested_role} HMAC签名成功")
        print(f"  需求: {run_id}")
        print(f"  阶段: {current_stage}")
        print(f"  清单指纹: {content_hash[:16]}...")
        print(f"  HMAC: {signature[:16]}...")
    except Exception as e:
        print(f"错误: 无法写入: {e}")
        sys.exit(1)

    # 12. 日志
    append_log("signature", {
        "run_id": run_id, "stage": current_stage, "role": requested_role,
        "requested_actor": requested_actor, "requested_role": requested_role,
        "actual_actor": actual_actor, "actual_role": effective_actor,
        "action": "sign", "decision": "PASS",
        "reason": decision_reason or "authorized",
        "checklist_version": content_hash,
        "signature": signature,
        "comment": comment,
        "session_id": session_id, "process_id": pid,
        "command_source": " ".join(sys.argv),
    })
    append_log("checklist_chg", {
        "run_id": run_id, "modified_by": f"{effective_actor}→{requested_role}",
        "operation": "updated",
        "diff_summary": f"{effective_actor}→{requested_role}在{current_stage}HMAC签名",
        "previous_hash": "see log", "new_hash": content_hash,
    })

    print(f"  ✓ 日志已记录")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="铁律量化 - HMAC签名工具 (v4.0)")
    p.add_argument("--actor", required=True, help="申请签名角色(requested_actor)")
    p.add_argument("--role", required=True, help="申请签名身份(requested_role)")
    p.add_argument("--run-id", required=True, help="需求ID")
    p.add_argument("--checklist", required=True, help="清单JSON路径")
    p.add_argument("--comment", default="", help="备注")
    p.add_argument("--audit-report", default=None, help="审计报告路径(P0 post_audit)")
    args = p.parse_args()
    sign_off(args.actor, args.role, args.run_id, args.checklist, args.comment, args.audit_report)
