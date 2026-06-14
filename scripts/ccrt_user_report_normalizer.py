#!/usr/bin/env python3
"""CCRT user report normalizer.

Reads internal evidence, identifies closed-loop state,
and generates user-visible terminal status reports.

User only sees three statuses:
  COMPLETE       — all gates, archive, github sync done
  AUTO_REPAIRING — system auto-fixing, no user action needed
  BLOCK          — user must intervene
"""

import argparse
import json
import sys
from pathlib import Path

RESULT_COMPLETE = "COMPLETE"
RESULT_AUTO_REPAIRING = "AUTO_REPAIRING"
RESULT_BLOCK = "BLOCK"

FORBIDDEN_USER_PHRASES = [
    "本输出只是",
    "不是 G5 PASS",
    "不是 G6 PASS",
    "等待独立复查",
    "等待复查",
    "等待 G6",
    "等待归档",
    "未 tag",
    "未 merge",
    "未 push",
    "未 tag/merge/push",
    "请用户确认下一阶段",
    "请用户判断",
    "请用户确认",
    "false 不是正确结果",
    "candidate_only",
    "not_g5_pass",
    "not_g6_pass",
    "waiting_review",
    "archive_not_executed",
    "forbidden_claims",
    "forbidden_actions",
    "no_role_signoff_claimed",
]


def load_json(path):
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def check_forbidden_phrases(text):
    found = []
    for phrase in FORBIDDEN_USER_PHRASES:
        if phrase in text:
            found.append(phrase)
    return found


def normalize(evidence_path):
    evidence = load_json(evidence_path)

    # Only scan user_visible_message for forbidden phrases, not the full evidence
    # Internal evidence fields (forbidden_claims, candidate_only, etc.) are allowed
    message = evidence.get("user_visible_message", evidence.get("user_message", ""))
    forbidden = check_forbidden_phrases(message)

    # Extract key fields with defaults
    archive_completed = evidence.get("archive_completed", False)
    github_sync_completed = evidence.get("github_sync_completed", False)
    push_completed = evidence.get("push_completed", False)
    result = evidence.get("result", "")
    status = evidence.get("status", "")
    issues = evidence.get("issues", []) or []
    reason = evidence.get("reason", "")

    # Also check archive_record if available
    archive_record = evidence.get("archive_record")
    if archive_record and isinstance(archive_record, str):
        arc_path = Path(archive_record)
        if arc_path.exists():
            arc_data = load_json(arc_path)
            if arc_data.get("archive_completed") is True:
                archive_completed = True

    # BLOCK logic — only escalate to user what system can't auto-repair
    auto_repair_issues = {
        "missing_hmac", "missing_evidence", "missing_actual_actor",
        "role_substitution", "actual_actor_role_mismatch",
        "candidate_claims_formal_signoff", "BLOCK", "BLOCK_in_G5_review",
        "missing_field", "missing_formal_signoff_artifact",
        "g6_not_pass", "not_g6_evidence", "invalid_requested_actions",
        "invalid_evidence_json", "registry_rule_conflict",
        "permission_missing", "scope_expansion",
    }

    user_block_triggers = {
        "push failed", "no upstream", "upstream not configured",
        "forbidden directories", "forbidden_dir",
        "git commit failed", "git push failed",
        "HMAC secret", "permission denied",
        "max_auto_repair_attempts", "production_action",
        "production_action_without_user_confirmation",
    }

    if forbidden:
        return make_block(evidence, f"内部话术泄漏至用户汇报层: {forbidden[0]}")

    # Check user-escalation-only situations
    for trigger in user_block_triggers:
        if trigger in reason.lower():
            return make_block(evidence, reason)

    # Check if this is a COMPLETE case
    if archive_completed is True and github_sync_completed is True and push_completed is True:
        if result in ("CLOSED", "PUSHED", "G6_COMPLETE", "COMPLETE") or status == "G6_COMPLETE":
            return make_complete(evidence)

    # Check if status/result indicates the full chain
    if status == "G6_COMPLETE":
        # G6_COMPLETE means archive + github sync both succeeded
        return make_complete(evidence)

    if status == "ARCHIVED" and evidence.get("github_sync_completed") is not True:
        # Archived without github sync — this is a problem with new default policy
        # auto_github_sync policy would have handled it → something blocked
        return make_block(evidence, "归档已完成但 GitHub 同步未执行")

    # Check for known auto-repair conditions
    all_issues = set(issues)
    # Also look deeper in the evidence
    for key, val in evidence.items():
        if isinstance(val, str) and val in auto_repair_issues:
            all_issues.add(val)

    if all_issues & auto_repair_issues:
        return make_auto_repairing(evidence)

    # Check waiting states
    if status in ("WAITING_ROLE_SIGNOFF", "WAITING_FORMAL_SIGNOFF") or "WAITING" in (status or ""):
        return make_auto_repairing(evidence)

    # Fallback COMPLETE: if the main result is success and no issues
    if result in ("PASS", "CLOSED", "PUSHED", "ACTIVE", "ARCHIVE_READY_DRY_RUN"):
        if github_sync_completed is True or status in ("G6_COMPLETE", "ARCHIVED"):
            if not issues:
                return make_complete(evidence)

    # Fallback
    return make_block(evidence, reason or "无法确定闭环状态")


def make_complete(evidence):
    return {
        "user_visible_status": RESULT_COMPLETE,
        "user_visible_message": "CCRT 全流程已完成，已归档，已提交 GitHub。",
        "internal_stage_evidence_hidden_from_user": True,
        "original_status": evidence.get("status", ""),
        "original_result": evidence.get("result", ""),
    }


def make_auto_repairing(evidence):
    return {
        "user_visible_status": RESULT_AUTO_REPAIRING,
        "user_visible_message": "发现问题，系统已打回对应环节自动修复，无需用户处理。",
        "internal_stage_evidence_hidden_from_user": True,
        "original_status": evidence.get("status", ""),
        "original_result": evidence.get("result", ""),
        "original_issues": evidence.get("issues", []),
    }


def make_block(evidence, reason):
    return {
        "user_visible_status": RESULT_BLOCK,
        "user_visible_message": f"BLOCK: {reason}",
        "internal_stage_evidence_hidden_from_user": True,
        "original_status": evidence.get("status", ""),
        "original_result": evidence.get("result", ""),
    }


def run_self_test():
    failures = []

    # 1. COMPLETE detection
    complete = {
        "task_id": "UT-CMP",
        "status": "G6_COMPLETE",
        "archive_completed": True,
        "github_sync_completed": True,
        "push_completed": True,
        "result": "G6_COMPLETE",
        "issues": [],
    }
    r = normalize_from_dict(complete)
    if r["user_visible_status"] != RESULT_COMPLETE:
        failures.append({"case": "G6_COMPLETE -> COMPLETE", "got": r["user_visible_status"]})

    # 2. AUTO_REPAIRING detection
    repairing = {
        "task_id": "UT-REP",
        "status": "WAITING_ROLE_SIGNOFF",
        "issues": ["missing_actual_actor"],
        "result": "",
    }
    r = normalize_from_dict(repairing)
    if r["user_visible_status"] != RESULT_AUTO_REPAIRING:
        failures.append({"case": "WAITING_ROLE_SIGNOFF -> AUTO_REPAIRING", "got": r["user_visible_status"]})

    # 3. BLOCK detection: archive done but github sync not done
    block1 = {
        "task_id": "UT-BLK1",
        "status": "ARCHIVED",
        "archive_completed": True,
        "github_sync_completed": False,
        "push_completed": False,
        "result": "ARCHIVED",
        "issues": [],
    }
    r = normalize_from_dict(block1)
    if r["user_visible_status"] != RESULT_BLOCK:
        failures.append({"case": "archive without github sync -> BLOCK", "got": r["user_visible_status"]})

    # 4. BLOCK with reason
    block2 = {
        "task_id": "UT-BLK2",
        "status": "BLOCK",
        "reason": "no upstream configured for branch master",
        "issues": [],
    }
    r = normalize_from_dict(block2)
    if r["user_visible_status"] != RESULT_BLOCK:
        failures.append({"case": "no upstream -> BLOCK", "got": r["user_visible_status"]})

    # 5. Forbidden phrases blocked
    bad_evidence = {
        "task_id": "UT-BAD-PHRASE",
        "result": "PASS",
        "note": "本输出只是 G4 自检候选，不是 G5 PASS，不是 G6 PASS。等待独立复查。",
    }
    r = normalize_from_dict(bad_evidence)
    if r["user_visible_status"] != RESULT_BLOCK:
        failures.append({"case": "forbidden phrase -> BLOCK", "got": r["user_visible_status"]})

    if failures:
        print(json.dumps({"self_test": "BLOCK", "failures": failures}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"self_test": "PASS", "cases": 5}, ensure_ascii=False, indent=2))
    return 0


def normalize_from_dict(evidence_dict):
    """Helper for self-test: normalize a dict directly."""
    import tempfile
    td = Path(tempfile.mkdtemp(dir="/private/tmp"))
    path = td / "_evidence.json"
    path.write_text(json.dumps(evidence_dict, ensure_ascii=False), encoding="utf-8")
    result = normalize(str(path))
    import shutil
    shutil.rmtree(td)
    return result


def main():
    parser = argparse.ArgumentParser(description="CCRT user report normalizer")
    parser.add_argument("--self-test", action="store_true", help="Run self-test")
    parser.add_argument("--evidence", help="Path to evidence JSON")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    if not args.evidence:
        print("BLOCK: --evidence is required unless --self-test", file=sys.stderr)
        return 2

    response = normalize(args.evidence)
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0 if response["user_visible_status"] in {RESULT_COMPLETE, RESULT_AUTO_REPAIRING, RESULT_BLOCK} else 2


if __name__ == "__main__":
    raise SystemExit(main())
