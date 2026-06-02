#!/usr/bin/env python3
"""bash_identity_detector.py — Detect batch role impersonation in Bash commands.

Detects: for-role loops, multiple sign_off calls, multiple --actor arguments,
chained pipeline_engine --advance across roles. When actual_actor=阿黑, direct BLOCK.

Code level: L2 (security infrastructure)
"""
import os
import re

ALL_ROLES = ["阿黑", "腰子", "山猫", "信鸽", "玉夜", "流金", "青山",
             "情墨", "千光", "红枫", "新安", "红结", "旧影"]

SIGN_OFF_PATTERN = re.compile(r'sign_off\.py\s+--actor\s+(\S+)', re.IGNORECASE)
ADVANCE_PATTERN = re.compile(r'pipeline_engine\.py\s+--advance\s+\S+\s+--actor\s+(\S+)', re.IGNORECASE)


def detect_batch_identity(command):
    """Detect batch role impersonation patterns in a Bash command.

    Returns: list of dicts with keys: pattern, description, severity
    """
    if not command:
        return []

    findings = []

    # 1. Detect for-role-in loop patterns
    if re.search(r'for\s+\w+\s+in\s+.*(?:role|actor)', command, re.IGNORECASE):
        findings.append({
            "pattern": "for_role_loop",
            "description": "Bash for-loop iterating over roles detected",
            "severity": "HIGH",
        })

    # 2. Count --actor mentions
    actor_mentions = SIGN_OFF_PATTERN.findall(command) + ADVANCE_PATTERN.findall(command)
    unique_actors = set(actor_mentions)
    if len(unique_actors) >= 3:
        findings.append({
            "pattern": "multiple_actors",
            "description": f"Command references {len(unique_actors)} distinct actors in sign/advance: {', '.join(sorted(unique_actors)[:5])}",
            "severity": "HIGH",
        })
    elif len(unique_actors) >= 2:
        findings.append({
            "pattern": "multiple_actors",
            "description": f"Command references {len(unique_actors)} distinct actors: {', '.join(sorted(unique_actors))}",
            "severity": "MEDIUM",
        })

    # 3. Count sign_off.py calls
    sign_off_count = len(re.findall(r'sign_off\.py\s+--actor', command))
    if sign_off_count >= 3:
        findings.append({
            "pattern": "batch_sign_off",
            "description": f"Command contains {sign_off_count} sign_off.py calls — likely batch signing",
            "severity": "HIGH",
        })
    elif sign_off_count >= 2:
        findings.append({
            "pattern": "batch_sign_off",
            "description": f"Command contains {sign_off_count} sign_off.py calls",
            "severity": "MEDIUM",
        })

    # 4. Detect chained pipeline advances (&& with multiple --advance)
    advance_count = len(re.findall(r'pipeline_engine\.py\s+--advance', command))
    if advance_count >= 3:
        findings.append({
            "pattern": "batch_advance",
            "description": f"Command contains {advance_count} pipeline_engine --advance calls — likely batch advancement",
            "severity": "HIGH",
        })
    elif advance_count >= 2:
        findings.append({
            "pattern": "batch_advance",
            "description": f"Command contains {advance_count} pipeline_engine --advance calls",
            "severity": "MEDIUM",
        })

    # 5. Detect sudo/privilege escalation
    if re.search(r'sudo\s', command):
        findings.append({
            "pattern": "privilege_escalation",
            "description": "sudo detected in command",
            "severity": "LOW",
        })

    return findings


def is_ahhei_blocked(command, actual_actor=""):
    """Check if command should be blocked for 阿黑.

    Returns (blocked: bool, reason: str)
    """
    if actual_actor != "阿黑":
        return False, ""

    findings = detect_batch_identity(command)
    if findings:
        high_findings = [f for f in findings if f["severity"] == "HIGH"]
        if high_findings:
            return True, f"阿黑批量角色操作: {high_findings[0]['description']}"

    # 阿黑 doing any sign_off or advance is blocked
    if SIGN_OFF_PATTERN.search(command):
        return True, "阿黑不得执行 sign_off"
    if ADVANCE_PATTERN.search(command):
        return True, "阿黑不得执行 pipeline_engine --advance"

    return False, ""


if __name__ == "__main__":
    tests = [
        ('for role in 腰子 山猫 信鸽; do python3 scripts/sign_off.py --actor $role; done', True),
        ('python3 scripts/sign_off.py --actor 腰子 --role 腰子 && python3 scripts/sign_off.py --actor 山猫 --role 山猫 && python3 scripts/sign_off.py --actor 信鸽 --role 信鸽', True),
        ('python3 scripts/sign_off.py --actor 腰子 --role 腰子 --run-id RUN-TEST --checklist x.json', True),
        ('python3 scripts/pipeline_engine.py --advance RUN --actor 红结 --role 红结', True),
        ('python3 scripts/pipeline_engine.py --status', False),
        ('python3 scripts/pipeline_engine.py --start FIX --task "test"', False),
        ('python3 scripts/audit_scan.py', False),
    ]
    for cmd, expected_block in tests:
        blocked, reason = is_ahhei_blocked(cmd, "阿黑")
        status = "PASS" if blocked == expected_block else "FAIL"
        print(f"[{status}] BLOCK={blocked} | {cmd[:70]}")
        if reason:
            print(f"       reason: {reason}")
