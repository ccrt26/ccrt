#!/usr/bin/env python3
"""pipeline_auth.py — Code File Write Protection Shared Auth Module (v2.0).

Actor-bound authorization. Single source of truth for:
- Governance path patterns (always require pipeline token)
- AutoCommit exemption patterns
- Protected path patterns
- Pipeline authorization with actor/stage/scope binding

Used by: write_protection_hook.py, pre-commit-check.py
Code level: L2 (security infrastructure)
"""
import json
import os
import re

# Governance paths — ALWAYS require pipeline token
GOVERNANCE_PATHS = [
    r'^\.claude[/\\]hooks[/\\]',
    r'^\.claude[/\\]settings\.json$',
    r'^\.claude[/\\]settings\.local\.json$',
    r'^\.claude[/\\]scheduled_tasks\.json$',
    r'^\.claude[/\\]pipeline_active\.json$',
    r'^\.claude[/\\]commands[/\\]',
    r'^\.claude[/\\]agents[/\\]',
]

# AutoCommit exemption patterns
AUTOCOMMIT_EXTENSIONS = [
    r'\.log$', r'\.json$', r'\.jsonl$', r'\.csv$', r'\.txt$',
    r'\.md$', r'\.pdf$', r'\.docx$', r'\.html$'
]

AUTOCOMMIT_PATHS = [
    r'^\.claude[/\\]im_queue[/\\]',
    r'^\.claude[/\\]knowledge[/\\]',
    r'^\.claude[/\\]pipeline_history[/\\]',
    r'^\.claude[/\\]regen[/\\]',
    r'^\.claude[/\\]sweep\.lock$',
    r'^\.claude[/\\]deploy_requested$',
    r'^临时报告[/\\]',
    r'^历史数据[/\\]',
    r'^审计报告[/\\]',
    r'^重点股票[/\\]股票报告[/\\]',
    r'^重点股票[/\\]次日评估[/\\]',
    r'^重点股票[/\\]预判记录[/\\]',
    r'^重点股票[/\\]消息面数据[/\\]',
    r'^每日荐股[/\\]股票报告[/\\]',
    r'^每日荐股[/\\]评估报告[/\\]',
    r'^模拟交易[/\\]持仓记录[/\\]',
    r'^模拟交易[/\\]每日快照[/\\]',
    r'^模拟交易[/\\]绩效报告[/\\]',
    r'^项目成员[/\\]',
    r'^CLAUDE\.md$',
    r'^inspect_data_health\.py$'
]

PROTECTED_PATHS = [
    r'^重点股票[/\\]深度分析[/\\]深度分析报告[/\\]',
    r'^代码文件[/\\]',
    r'^模拟交易[/\\]sim_orchestrator\.py$',
    r'^模拟交易[/\\]交易引擎[/\\]',
    r'^模拟交易[/\\]每日荐股赛道[/\\]交易引擎[/\\]',
    r'^模拟交易[/\\]共享模块[/\\]',
    r'^模拟交易[/\\]否决审查[/\\]',
    r'^模拟交易[/\\]分析[/\\]',
    r'^模拟交易[/\\]展示[/\\]',
    r'^模拟交易[/\\]工具[/\\]'
]

# Stages that allow code writes and their authorized roles
CODE_WRITE_STAGES = {
    "coding": ["红结"],
    "deploy": ["红枫"],
    "verify": ["新安"],
    "post_audit": ["旧影"],
}

# Audit-only: 旧影 can only write audit records, not business code
AUDIT_RESTRICTED_PATHS = [
    r'^logs[/\\]audit[/\\]',
    r'^logs[/\\]checklist[/\\]',
]

VALID_EXECUTORS = ["红结", "红枫", "新安", "旧影"]


def _normalize(path):
    return path.replace("\\", "/")


def load_pipeline_state(project_root):
    token_path = os.path.join(project_root, ".claude", "pipeline_active.json")
    if not os.path.exists(token_path):
        return None
    try:
        with open(token_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def get_active_code_runs(state):
    """Return list of active runs that are in a code-writing stage."""
    if not state:
        return []
    active = []
    runs = state.get("runs", {})
    for rid, run in runs.items():
        if not isinstance(run, dict):
            continue
        if run.get("status") not in ("active",):
            continue
        stage = run.get("current_stage", "")
        if stage in CODE_WRITE_STAGES:
            active.append(run)
    return active


def get_run_by_id(state, run_id):
    if not state:
        return None
    return state.get("runs", {}).get(run_id)


def test_pipeline_authorization(file_path, project_root, actor="", role="",
                                 run_id="", tool_name=""):
    """Check if a code file write is authorized under current pipeline state.

    Args:
        file_path: relative path to the file being written
        project_root: project root directory
        actor: who is actually operating (e.g. "红结", "阿黑")
        role: what role they're acting as
        run_id: explicit run_id (required when multiple active code runs)
        tool_name: the tool being used (Write/Edit/Bash/etc.)

    Returns: dict with keys:
        authorized (bool), reason (str), actor (str), role (str),
        stage (str), run_id (str), scope_match (bool), gate1 (str)
    """
    normalized = _normalize(file_path)

    # Step 0: Governance path check — BEFORE auto-commit exemption
    is_governance = any(re.search(pat, normalized) for pat in GOVERNANCE_PATHS)

    # Step 1: AutoCommit exemption (skipped for governance paths)
    if not is_governance:
        for pat in AUTOCOMMIT_PATHS:
            if re.search(pat, normalized):
                return {"authorized": True,
                        "reason": f"Auto-commit path: matches {pat}",
                        "actor": actor, "role": role, "stage": "", "run_id": "",
                        "scope_match": True, "gate1": ""}
        for pat in AUTOCOMMIT_EXTENSIONS:
            if re.search(pat, normalized):
                # .md/.json in protected code paths should still be checked
                if re.search(r'^代码文件[/\\]', normalized) or re.search(r'^scripts[/\\]', normalized):
                    break  # fall through to protected check
                return {"authorized": True,
                        "reason": f"Auto-commit extension: matches {pat}",
                        "actor": actor, "role": role, "stage": "", "run_id": "",
                        "scope_match": True, "gate1": ""}

    # Step 2: Check if file is in any protected path
    all_patterns = list(GOVERNANCE_PATHS) + list(PROTECTED_PATHS)
    is_protected = any(re.search(pat, normalized) for pat in all_patterns)
    if not is_protected:
        return {"authorized": True,
                "reason": "Not a protected path",
                "actor": actor, "role": role, "stage": "", "run_id": "",
                "scope_match": True, "gate1": ""}

    # Step 3: Load pipeline state
    state = load_pipeline_state(project_root)
    if not state:
        return {"authorized": False,
                "reason": "No pipeline state found — all protected writes require active pipeline",
                "actor": actor, "role": role, "stage": "", "run_id": "",
                "scope_match": False, "gate1": ""}

    # Step 4: Find the active run for authorization
    active_code_runs = get_active_code_runs(state)

    if not active_code_runs:
        return {"authorized": False,
                "reason": "No active code-writing run. Start a pipeline with coding stage first.",
                "actor": actor, "role": role, "stage": "", "run_id": "",
                "scope_match": False, "gate1": ""}

    target_run = None

    if run_id:
        # Explicit run_id specified
        target_run = get_run_by_id(state, run_id)
        if not target_run:
            return {"authorized": False,
                    "reason": f"Specified run_id '{run_id}' not found in pipeline state",
                    "actor": actor, "role": role, "stage": "", "run_id": run_id,
                    "scope_match": False, "gate1": ""}
        if target_run.get("status") != "active":
            return {"authorized": False,
                    "reason": f"Specified run_id '{run_id}' is not active (status={target_run.get('status')})",
                    "actor": actor, "role": role, "stage": "", "run_id": run_id,
                    "scope_match": False, "gate1": ""}
    elif len(active_code_runs) == 1:
        target_run = active_code_runs[0]
        run_id = target_run.get("run_id", "")
    else:
        # Multiple active code runs — must specify
        run_ids = [r.get("run_id", "?") for r in active_code_runs]
        return {"authorized": False,
                "reason": f"Multiple active code-writing runs ({', '.join(run_ids)}). Must specify run_id explicitly.",
                "actor": actor, "role": role, "stage": "", "run_id": "",
                "scope_match": False, "gate1": ""}

    # Step 5: Stage validation
    current_stage = target_run.get("current_stage", "")
    allowed_roles = CODE_WRITE_STAGES.get(current_stage, [])

    if not allowed_roles:
        return {"authorized": False,
                "reason": f"Stage '{current_stage}' does not allow code writes. Allowed stages: {list(CODE_WRITE_STAGES.keys())}",
                "actor": actor, "role": role, "stage": current_stage, "run_id": run_id,
                "scope_match": False, "gate1": ""}

    # Step 6: Role validation — role must be in the stage's allowed roles
    if role and role not in allowed_roles:
        return {"authorized": False,
                "reason": f"Role '{role}' not authorized for stage '{current_stage}'. Allowed: {allowed_roles}",
                "actor": actor, "role": role, "stage": current_stage, "run_id": run_id,
                "scope_match": False, "gate1": ""}

    # Step 7: Actor validation — 阿黑 can NEVER write code
    if actor == "阿黑":
        return {"authorized": False,
                "reason": "阿黑 is forbidden from writing code files under any circumstance (§3.1)",
                "actor": actor, "role": role, "stage": current_stage, "run_id": run_id,
                "scope_match": False, "gate1": "BLOCK_AHEI"}

    # Step 8: 旧影 audit restrictions — only allow audit log paths
    if role == "旧影" and current_stage in ("audit", "post_audit"):
        in_audit_scope = any(re.search(pat, normalized) for pat in AUDIT_RESTRICTED_PATHS)
        if not in_audit_scope:
            return {"authorized": False,
                    "reason": "旧影 in audit stage can only write audit logs, not business code",
                    "actor": actor, "role": role, "stage": current_stage, "run_id": run_id,
                    "scope_match": False, "gate1": ""}

    # Step 9: Scope check
    files_scope = target_run.get("files_scope", [])
    if not files_scope:
        return {"authorized": False,
                "reason": "Run has no files_scope defined",
                "actor": actor, "role": role, "stage": current_stage, "run_id": run_id,
                "scope_match": False, "gate1": ""}

    in_scope = any(normalized.startswith(_normalize(s)) for s in files_scope)
    if not in_scope:
        return {"authorized": False,
                "reason": f"File outside pipeline scope. Declared: {', '.join(files_scope[:5])}",
                "actor": actor, "role": role, "stage": current_stage, "run_id": run_id,
                "scope_match": False, "gate1": ""}

    # Step 10: Gate check
    gate1 = target_run.get("gate_1", "")
    if gate1 and gate1 != "PASS":
        return {"authorized": False,
                "reason": f"Gate_1 not PASS (current: {gate1})",
                "actor": actor, "role": role, "stage": current_stage, "run_id": run_id,
                "scope_match": True, "gate1": gate1}

    return {"authorized": True,
            "reason": f"Authorized: actor={actor}, role={role}, stage={current_stage}, scope OK",
            "actor": actor, "role": role, "stage": current_stage, "run_id": run_id,
            "scope_match": True, "gate1": gate1 or "PASS"}
