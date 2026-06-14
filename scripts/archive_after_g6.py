#!/usr/bin/env python3
"""CCRT G6 archive dry-run evaluator.

This script does not archive, tag, merge, push, or write production files.
It only evaluates G6 evidence and optionally writes an archive task JSON to
an explicitly supplied output directory.
"""

import argparse
import json
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

try:
    from log_utils import append_log
except ImportError:
    append_log = None

RESULT_ARCHIVE_READY_DRY_RUN = "ARCHIVE_READY_DRY_RUN"
RESULT_WAITING_FORMAL_SIGNOFF = "WAITING_FORMAL_SIGNOFF"
RESULT_REPAIR_DISPATCH_REQUIRED = "REPAIR_DISPATCH_REQUIRED"
RESULT_USER_ESCALATION_REQUIRED = "USER_ESCALATION_REQUIRED"
RESULT_BLOCK = "BLOCK"

FORBIDDEN_ACTIONS = ["archive", "tag", "merge", "push", "production_write", "sign"]
REQUIRED_FIELDS = {"task_id", "gate", "artifact_type", "result", "formal_signoff"}
PROJECT_ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_REPO_OUTPUT_DIR = PROJECT_ROOT / "00_项目地基" / "08_审计与验收"


def load_json(path):
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def safe_filename(value):
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value or "UNKNOWN").strip("_")
    return cleaned or "UNKNOWN"


def validate_structure(evidence):
    if not isinstance(evidence, dict):
        return ["invalid_evidence_json"]
    return [f"missing_field:{field}" for field in sorted(REQUIRED_FIELDS - set(evidence))]


def evaluate(evidence):
    structure_issues = validate_structure(evidence)
    if structure_issues:
        return make_response(
            RESULT_BLOCK,
            evidence if isinstance(evidence, dict) else {},
            structure_issues,
            "complete_g6_archive_evidence",
            True,
        )

    signoff = evidence.get("formal_signoff") or {}
    issues = []

    if evidence.get("gate") != "G6":
        issues.append("not_g6_evidence")
    if evidence.get("artifact_type") != "formal_signoff":
        issues.append("missing_formal_signoff_artifact")
    if evidence.get("result") != "PASS":
        issues.append("g6_not_pass")

    if not isinstance(signoff, dict):
        issues.append("missing_hmac")
    else:
        if signoff.get("role") != "腰子":
            issues.append("role_substitution")
        actual_actor = signoff.get("actual_actor", "")
        if not actual_actor:
            issues.append("missing_actual_actor")
        elif actual_actor != "腰子":
            issues.append("actual_actor_role_mismatch")
        if signoff.get("signed") is not True:
            issues.append("missing_hmac")
        if signoff.get("sig_type") != "HMAC-SHA256":
            issues.append("missing_hmac")

    requested_actions = evidence.get("requested_actions", [])
    if requested_actions is None:
        requested_actions = []
    if not isinstance(requested_actions, list):
        issues.append("invalid_requested_actions")
        requested_actions = []

    production_actions = [a for a in requested_actions if a in {"archive", "tag", "merge", "push", "production_write"}]
    user_confirmed = evidence.get("user_confirmed_release") is True
    if production_actions and not user_confirmed:
        issues.append("production_action_without_user_confirmation")

    deduped = []
    for issue in issues:
        if issue not in deduped:
            deduped.append(issue)
    issues = deduped

    if "role_substitution" in issues:
        return make_response(
            RESULT_REPAIR_DISPATCH_REQUIRED,
            evidence,
            issues,
            "invalidate_artifact_and_request_correct_role_resign",
            False,
        )
    if "actual_actor_role_mismatch" in issues:
        return make_response(
            RESULT_REPAIR_DISPATCH_REQUIRED,
            evidence,
            issues,
            "invalidate_artifact_and_request_correct_role_resign",
            False,
        )
    if "missing_actual_actor" in issues:
        return make_response(
            RESULT_WAITING_FORMAL_SIGNOFF,
            evidence,
            issues,
            "create_formal_signoff_dispatch_for_腰子",
            False,
        )
    if "missing_hmac" in issues:
        return make_response(
            RESULT_WAITING_FORMAL_SIGNOFF,
            evidence,
            issues,
            "create_formal_signoff_dispatch_for_腰子",
            False,
        )
    if "production_action_without_user_confirmation" in issues:
        return make_response(
            RESULT_USER_ESCALATION_REQUIRED,
            evidence,
            issues,
            "escalate_to_user_for_release_confirmation",
            True,
        )
    if issues:
        return make_response(
            RESULT_REPAIR_DISPATCH_REQUIRED,
            evidence,
            issues,
            "create_g6_archive_evidence_repair_dispatch",
            False,
        )

    return make_response(
        RESULT_ARCHIVE_READY_DRY_RUN,
        evidence,
        [],
        "create_archive_task_or_wait_for_explicit_execution",
        False,
    )


def make_response(status, evidence, issues, dispatch_action, user_escalation):
    task_id = evidence.get("task_id", "") if isinstance(evidence, dict) else ""
    requested_actions = evidence.get("requested_actions", []) if isinstance(evidence, dict) else []
    if not isinstance(requested_actions, list):
        requested_actions = []

    return {
        "status": status,
        "task_id": task_id,
        "from_gate": evidence.get("gate", "") if isinstance(evidence, dict) else "",
        "to_gate": "archive",
        "issues": issues,
        "dispatch_action": dispatch_action,
        "user_escalation": user_escalation,
        "dry_run": True,
        "writes": [],
        "would_write": [],
        "would_tag": "tag" in requested_actions,
        "would_merge": "merge" in requested_actions,
        "would_push": "push" in requested_actions,
        "forbidden_actions": FORBIDDEN_ACTIONS,
        "archive_task": build_archive_task(status, evidence, issues, dispatch_action, user_escalation),
    }


def build_archive_task(status, evidence, issues, dispatch_action, user_escalation):
    return {
        "task_kind": "g6_archive_task",
        "task_id": evidence.get("task_id", "") if isinstance(evidence, dict) else "",
        "source_gate": evidence.get("gate", "") if isinstance(evidence, dict) else "",
        "target_gate": "archive",
        "status": status,
        "issues": issues,
        "dispatch_action": dispatch_action,
        "candidate_only": True,
        "no_role_signoff_claimed": True,
        "archive_not_executed": True,
        "user_escalation": user_escalation,
        "required_role": "腰子",
        "required_artifact_type": "formal_signoff",
        "forbidden_claims": [
            "G6_PASS",
            "formal_signoff_completed",
            "archive_completed",
            "tag_completed",
            "merge_completed",
            "push_completed"
        ],
    }


def is_relative_to(path, parent):
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def validate_output_dir(output_dir):
    raw = Path(output_dir)
    if not raw.is_absolute():
        return False, "relative output directory is forbidden"

    resolved = raw.resolve()
    project_root = PROJECT_ROOT.resolve()
    forbidden_repo_dir = FORBIDDEN_REPO_OUTPUT_DIR.resolve()

    if is_relative_to(resolved, project_root):
        return False, "repository output directory is forbidden"
    if is_relative_to(resolved, forbidden_repo_dir):
        return False, "audit archive output directory is forbidden"

    allowed_roots = {
        Path("/tmp").resolve(),
        Path("/private/tmp").resolve(),
        Path(tempfile.gettempdir()).resolve(),
    }
    if not any(is_relative_to(resolved, root) or resolved == root for root in allowed_roots):
        return False, "output directory must be under tmp"

    return True, ""


def log_auto_advance_event(response, source_script):
    if append_log is None:
        return
    append_log("auto_advance", {
        "task_id": response.get("task_id", ""),
        "source_script": source_script,
        "status": response.get("status", ""),
        "from_gate": response.get("from_gate", ""),
        "to_gate": response.get("to_gate", ""),
        "issues": response.get("issues", []),
        "dispatch_action": response.get("dispatch_action", ""),
        "user_escalation": response.get("user_escalation", False),
        "dry_run": response.get("dry_run", True),
        "writes": response.get("writes", []),
        "forbidden_actions": response.get("forbidden_actions", []),
    })


def write_archive_task(response, output_dir):
    task = response.get("archive_task")
    if not task:
        raise ValueError("response missing archive_task")
    ok, reason = validate_output_dir(output_dir)
    if not ok:
        raise ValueError(f"unsafe output directory: {reason}")
    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    task_id = safe_filename(response.get("task_id", "UNKNOWN"))
    filename = f"{task_id}_g6_archive_task_{timestamp}.json"
    out_path = out_dir / filename
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generator": "scripts/archive_after_g6.py",
        "dry_run_source": False,
        "archive_task": task,
        "response_snapshot": {k: v for k, v in response.items() if k != "archive_task"},
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    response["dry_run"] = False
    response["writes"] = [str(out_path)]
    response["would_write"] = [str(out_path)]
    return response


def run_self_test():
    cases = [
        (
            "G6 formal signoff ready",
            {
                "task_id": "SELFTEST-G6-READY",
                "gate": "G6",
                "artifact_type": "formal_signoff",
                "result": "PASS",
                "formal_signoff": {"role": "腰子", "signed": True, "sig_type": "HMAC-SHA256", "actual_actor": "腰子"},
                "requested_actions": []
            },
            RESULT_ARCHIVE_READY_DRY_RUN,
            "create_archive_task_or_wait_for_explicit_execution",
        ),
        (
            "G6 missing hmac waits signoff",
            {
                "task_id": "SELFTEST-G6-MISSING-HMAC",
                "gate": "G6",
                "artifact_type": "formal_signoff",
                "result": "PASS",
                "formal_signoff": {"role": "腰子", "signed": True, "actual_actor": "腰子"},
                "requested_actions": []
            },
            RESULT_WAITING_FORMAL_SIGNOFF,
            "create_formal_signoff_dispatch_for_腰子",
        ),
        (
            "G6 wrong role repairs security",
            {
                "task_id": "SELFTEST-G6-WRONG-ROLE",
                "gate": "G6",
                "artifact_type": "formal_signoff",
                "result": "PASS",
                "formal_signoff": {"role": "阿黑", "signed": True, "sig_type": "HMAC-SHA256"},
                "requested_actions": []
            },
            RESULT_REPAIR_DISPATCH_REQUIRED,
            "invalidate_artifact_and_request_correct_role_resign",
        ),
        (
            "G6 production action needs user",
            {
                "task_id": "SELFTEST-G6-PROD",
                "gate": "G6",
                "artifact_type": "formal_signoff",
                "result": "PASS",
                "formal_signoff": {"role": "腰子", "signed": True, "sig_type": "HMAC-SHA256", "actual_actor": "腰子"},
                "requested_actions": ["tag", "push"]
            },
            RESULT_USER_ESCALATION_REQUIRED,
            "escalate_to_user_for_release_confirmation",
        ),
    ]

    failures = []
    for name, evidence, expected_status, expected_action in cases:
        actual = evaluate(evidence)
        if actual.get("status") != expected_status:
            failures.append({"case": name, "expected": expected_status, "actual": actual})
        if actual.get("dispatch_action") != expected_action:
            failures.append({
                "case": f"{name} dispatch_action",
                "expected": expected_action,
                "actual": actual.get("dispatch_action"),
            })
        if actual.get("writes") != [] or actual.get("dry_run") is not True:
            failures.append({"case": f"{name} dry_run_boundary", "actual": actual})

    if failures:
        print(json.dumps({"self_test": "BLOCK", "failures": failures}, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps({"self_test": "PASS", "cases": len(cases)}, ensure_ascii=False, indent=2))
    return 0


def main():
    parser = argparse.ArgumentParser(description="CCRT G6 archive dry-run evaluator")
    parser.add_argument("--evidence", help="Path to G6 evidence JSON")
    parser.add_argument("--self-test", action="store_true", help="Run built-in self tests")
    parser.add_argument("--write-task", action="store_true", help="Write archive task JSON to --output-dir")
    parser.add_argument("--output-dir", help="Directory for archive task JSON when --write-task is used")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    if not args.evidence:
        print("BLOCK: --evidence is required unless --self-test is used", file=sys.stderr)
        return 2

    if args.write_task and not args.output_dir:
        print("BLOCK: --output-dir is required when --write-task is used", file=sys.stderr)
        return 2

    evidence = load_json(args.evidence)
    response = evaluate(evidence)
    if args.write_task:
        try:
            response = write_archive_task(response, args.output_dir)
        except ValueError as exc:
            print(f"BLOCK: unsafe output directory", file=sys.stderr)
            return 2
    log_auto_advance_event(response, "scripts/archive_after_g6.py")
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0 if response.get("status") in {
        RESULT_ARCHIVE_READY_DRY_RUN,
        RESULT_WAITING_FORMAL_SIGNOFF,
        RESULT_REPAIR_DISPATCH_REQUIRED,
        RESULT_USER_ESCALATION_REQUIRED,
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
