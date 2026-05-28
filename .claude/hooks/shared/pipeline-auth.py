#!/usr/bin/env python3
"""pipeline-auth.py — Code File Write Protection Shared Auth Module.

Replaces pipeline-auth.ps1 (v1.0). Single source of truth for:
- AutoCommit exemption patterns
- Protected path patterns
- Pipeline authorization logic

Used by: pre-commit-check.py, write_protection_hook.py
Code level: L2 (security infrastructure)
"""
import json
import os
import re

# ── AutoCommit exemption patterns ──────────────────────
AUTOCOMMIT_EXTENSIONS = [
    r'\.log$', r'\.json$', r'\.jsonl$', r'\.csv$', r'\.txt$',
    r'\.md$', r'\.pdf$', r'\.docx$', r'\.html$'
]

AUTOCOMMIT_PATHS = [
    r'^.claude[/\\]',
    r'^临时报告[/\\]',
    r'^历史数据[/\\]',
    r'^审计报告[/\\]',
    r'^重点股票[/\\]股票报告[/\\]',
    r'^重点股票[/\\]深度分析[/\\]',
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

VALID_EXECUTORS = ["红结", "红枫"]


def _normalize(path):
    """Normalize path to use forward slashes."""
    return path.replace("\\", "/")


def test_pipeline_authorization(file_path, project_root, extra_patterns=None):
    """Check if a code file write is authorized under current pipeline state.

    Returns: dict with keys: authorized (bool), reason (str), executor (str),
             gate1 (str), scope_match (bool)
    """
    normalized = _normalize(file_path)

    # Step 0: AutoCommit exemption
    for pat in AUTOCOMMIT_PATHS:
        if re.search(pat, normalized):
            return {"authorized": True, "reason": f"Auto-commit path: matches {pat}",
                    "executor": "", "gate1": "", "scope_match": True}
    for pat in AUTOCOMMIT_EXTENSIONS:
        if re.search(pat, normalized):
            return {"authorized": True, "reason": f"Auto-commit extension: matches {pat}",
                    "executor": "", "gate1": "", "scope_match": True}

    # Step 1: Check if file is in any protected path
    all_patterns = list(PROTECTED_PATHS) + (extra_patterns or [])
    is_protected = any(re.search(pat, normalized) for pat in all_patterns)
    if not is_protected:
        return {"authorized": True, "reason": "Not a protected path",
                "executor": "", "gate1": "", "scope_match": True}

    # Step 2: Check pipeline token
    token_path = os.path.join(project_root, ".claude", "pipeline_active.json")
    if not os.path.exists(token_path):
        return {"authorized": False, "reason": "No pipeline token found",
                "executor": "", "gate1": "", "scope_match": False}

    try:
        with open(token_path, "r", encoding="utf-8") as f:
            token = json.load(f)
    except Exception as e:
        return {"authorized": False, "reason": f"Pipeline token corrupted: {e}",
                "executor": "", "gate1": "", "scope_match": False}

    # Step 3: Check active + executor + gate_1
    if not token.get("active"):
        return {"authorized": False,
                "reason": f"Pipeline not active (active={token.get('active')})",
                "executor": "", "gate1": token.get("gate_1", ""), "scope_match": False}

    if token.get("executor", "") not in VALID_EXECUTORS:
        return {"authorized": False,
                "reason": f"Invalid executor: {token.get('executor')}",
                "executor": "", "gate1": token.get("gate_1", ""), "scope_match": False}

    if token.get("gate_1") != "PASS":
        return {"authorized": False,
                "reason": f"Gate_1 not PASS (current: {token.get('gate_1')})",
                "executor": token.get("executor", ""),
                "gate1": token.get("gate_1", ""), "scope_match": False}

    # Step 4: Scope check
    files_scope = token.get("files_scope", [])
    if files_scope:
        in_scope = any(normalized.startswith(_normalize(s)) for s in files_scope)
        if not in_scope:
            return {"authorized": False,
                    "reason": f"File outside pipeline scope (declared: {', '.join(files_scope)})",
                    "executor": token.get("executor", ""), "gate1": "PASS", "scope_match": False}
    else:
        return {"authorized": False,
                "reason": "Pipeline files_scope is empty",
                "executor": token.get("executor", ""), "gate1": "PASS", "scope_match": False}

    return {"authorized": True,
            "reason": "Pipeline authorized: executor valid, gate_1=PASS, scope OK",
            "executor": token.get("executor", ""), "gate1": "PASS", "scope_match": True}
