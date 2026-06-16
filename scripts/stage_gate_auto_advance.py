#!/usr/bin/env python3
"""CCRT stage gate auto-advance dry-run evaluator.

This script only evaluates stage-gate evidence and prints the next action.
It does not sign for roles, write dispatch files, archive, tag, merge, or push.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from log_utils import append_log
except ImportError:
    append_log = None

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "00_项目地基" / "05_流程与角色" / "stage_gate_registry.json"

RESULT_ADVANCE_READY = "ADVANCE_READY"
RESULT_REPAIR_DISPATCH_REQUIRED = "REPAIR_DISPATCH_REQUIRED"
RESULT_WAITING_FORMAL_SIGNOFF = "WAITING_FORMAL_SIGNOFF"
RESULT_WAITING_PERMISSION = "WAITING_PERMISSION"
RESULT_USER_ESCALATION_REQUIRED = "USER_ESCALATION_REQUIRED"
RESULT_BLOCK = "BLOCK"

DISPATCH_KIND_ADVANCE = "advance_dispatch"
DISPATCH_KIND_REPAIR = "repair_dispatch"
DISPATCH_KIND_SIGNOFF = "formal_signoff_dispatch"
DISPATCH_KIND_PERMISSION = "permission_dispatch"
DISPATCH_KIND_USER_ESCALATION = "user_escalation_dispatch"

GATE_REQUIRED_SIGNOFF_ROLE = {
    "G5": "旧影",
    "G6": "腰子",
}

FORMAL_SIGNOFF_REPAIR_ISSUES = {
    "missing_hmac",
    "missing_actual_actor",
    "role_substitution",
    "actual_actor_role_mismatch",
}

REQUIRED_EVIDENCE_FIELDS = {
    "task_id",
    "gate",
    "artifact_type",
    "result",
}


def load_json(path):
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def load_registry(path=REGISTRY_PATH):
    registry = load_json(path)
    for key in ("artifact_types", "advance_rules", "repair_rules", "user_escalation_rules", "safety_limits"):
        if key not in registry:
            raise ValueError(f"registry missing key: {key}")
    return registry


def find_advance_rule(registry, gate):
    for rule in registry.get("advance_rules", []):
        if rule.get("from_gate") == gate:
            return rule
    return None


def repair_rule_for(registry, issue):
    for rule in registry.get("repair_rules", []):
        if rule.get("issue") == issue:
            return rule
    return {
        "issue": issue,
        "classification": "user_decision_block",
        "return_to_gate": "current_gate",
        "dispatch_action": "escalate_to_user_for_rule_gap",
        "user_escalation": True,
    }


def classify_issue(registry, issue):
    repair = repair_rule_for(registry, issue)
    if repair.get("user_escalation") is True:
        return RESULT_USER_ESCALATION_REQUIRED, repair
    if repair.get("classification") == "missing_signoff":
        return RESULT_WAITING_FORMAL_SIGNOFF, repair
    if repair.get("classification") == "permission_block":
        return RESULT_WAITING_PERMISSION, repair
    return RESULT_REPAIR_DISPATCH_REQUIRED, repair


ISSUE_PRIORITY = [
    "codex_implementation_detected",
    "role_substitution",
    "actual_actor_role_mismatch",
    "missing_actual_actor",
    "candidate_claims_formal_signoff",
    "production_action_without_user_confirmation",
    "scope_expansion",
    "permission_missing",
    "missing_hmac",
    "BLOCK_in_G5_review",
    "BLOCK",
    "missing_implementation_evidence",
    "missing_evidence",
    "registry_rule_conflict",
]


def choose_primary_issue(issues):
    for issue in ISSUE_PRIORITY:
        if issue in issues:
            return issue
    return issues[0] if issues else "missing_evidence"


def _is_codex_actor(actor_str):
    """Check if an actor string contains 'codex' (case-insensitive).

    Catches exact 'codex', 'Codex', 'CODEX', and variants like
    'codex_app', 'codex-agent', 'CodexAgent', etc.
    """
    return "codex" in (actor_str or "").lower()


def validate_role_boundary(evidence):
    """Validate G3/G4 implementation actor role boundary.

    Checks that the G3 implementation was performed by an authorized actor
    (deepseek_live / Claude Code live), not by the Codex planning layer.
    Returns a list of issue strings (empty = PASS).
    """
    issues = []

    gate = evidence.get("gate", "")
    if gate not in ("G3", "G4"):
        return issues

    # Check codex_write_detected flag
    if evidence.get("codex_write_detected") is True:
        issues.append("codex_implementation_detected")

    # Check implementation_actor field (case-insensitive, catches variants)
    impl_actor = evidence.get("implementation_actor", "")
    if _is_codex_actor(impl_actor) and "codex_implementation_detected" not in issues:
        issues.append("codex_implementation_detected")

    # Check actual_actor field (top-level, not signoff)
    actual_actor = evidence.get("actual_actor", "")
    if _is_codex_actor(actual_actor) and "codex_implementation_detected" not in issues:
        issues.append("codex_implementation_detected")

    # Override: G3_IMPL_ALLOWED_BY_USER env var suppresses codex_implementation_detected.
    # Only the process environment variable is trusted, NOT a self-filled evidence field.
    if os.environ.get("G3_IMPL_ALLOWED_BY_USER", "").lower() == "true":
        if "codex_implementation_detected" in issues:
            issues.remove("codex_implementation_detected")

    # Check required implementation evidence fields
    # actual_actor must be present and non-empty
    if not actual_actor:
        issues.append("missing_implementation_evidence")
    # implementation_actor must be present and non-empty
    if not impl_actor:
        issues.append("missing_implementation_evidence")
    # changed_files must be present and be a list
    changed = evidence.get("changed_files")
    if changed is None or not isinstance(changed, list):
        issues.append("missing_implementation_evidence")
    # changed_files must not be empty
    if isinstance(changed, list) and len(changed) == 0:
        issues.append("missing_implementation_evidence")
    # tool_calls must be present and non-empty
    tool_calls = evidence.get("tool_calls")
    if not tool_calls or not isinstance(tool_calls, list) or len(tool_calls) == 0:
        issues.append("missing_implementation_evidence")
    # live_model_call must be true for G3/G4 implementation evidence
    if evidence.get("live_model_call") is not True:
        issues.append("missing_implementation_evidence")

    return issues


def normalize_evidence(data):
    if not isinstance(data, dict):
        return {}, ["invalid_evidence_json"]
    missing = sorted(REQUIRED_EVIDENCE_FIELDS - set(data))
    return data, [f"missing_field:{m}" for m in missing]


def detect_issues(rule, evidence):
    issues = []
    artifact_type = evidence.get("artifact_type")
    result = evidence.get("result")
    required_role = rule.get("required_role")

    if result == "BLOCK":
        issues.append("BLOCK_in_G5_review" if evidence.get("gate") == "G5" else "BLOCK")

    if result != rule.get("required_result"):
        issues.append("missing_evidence")

    if artifact_type != rule.get("required_artifact_type"):
        issues.append("missing_evidence")

    if artifact_type == "candidate" and evidence.get("claims_formal_signoff") is True:
        issues.append("candidate_claims_formal_signoff")

    if rule.get("formal_signoff_required") is True:
        signoff = evidence.get("formal_signoff") or {}
        if not isinstance(signoff, dict) or signoff.get("sig_type") != "HMAC-SHA256":
            issues.append("missing_hmac")
        if required_role and signoff.get("role") != required_role:
            issues.append("role_substitution")
        actual_actor = signoff.get("actual_actor", "")
        if required_role and not actual_actor:
            issues.append("missing_actual_actor")
        elif required_role and actual_actor != required_role:
            issues.append("actual_actor_role_mismatch")
        if signoff.get("signed") is not True:
            issues.append("missing_hmac")

    if "permission_missing" in evidence.get("issues", []):
        issues.append("permission_missing")
    if "production_action_without_user_confirmation" in evidence.get("issues", []):
        issues.append("production_action_without_user_confirmation")
    if "scope_expansion" in evidence.get("issues", []):
        issues.append("scope_expansion")

    # G3/G4 implementation role boundary check
    role_boundary_issues = validate_role_boundary(evidence)
    issues.extend(role_boundary_issues)

    deduped = []
    for issue in issues:
        if issue not in deduped:
            deduped.append(issue)
    return deduped


def evaluate(registry, evidence_data):
    evidence, structure_issues = normalize_evidence(evidence_data)
    if structure_issues:
        issue = "missing_evidence"
        state, repair = classify_issue(registry, issue)
        return make_response(state, evidence, None, [issue] + structure_issues, repair)

    gate = evidence.get("gate")
    rule = find_advance_rule(registry, gate)
    if not rule:
        issue = "registry_rule_conflict"
        state, repair = classify_issue(registry, issue)
        return make_response(state, evidence, None, [issue], repair)

    issues = detect_issues(rule, evidence)
    if issues:
        primary_issue = choose_primary_issue(issues)
        state, repair = classify_issue(registry, primary_issue)
        return make_response(state, evidence, rule, issues, repair)

    return make_response(
        RESULT_ADVANCE_READY,
        evidence,
        rule,
        [],
        {
            "issue": "",
            "classification": "advance",
            "return_to_gate": rule.get("to_gate"),
            "dispatch_action": rule.get("action"),
            "user_escalation": False,
        },
    )


def make_response(state, evidence, rule, issues, repair):
    next_gate = rule.get("to_gate") if rule else repair.get("return_to_gate")
    response = {
        "status": state,
        "task_id": evidence.get("task_id", ""),
        "from_gate": evidence.get("gate", ""),
        "to_gate": next_gate,
        "issues": issues,
        "dispatch_action": repair.get("dispatch_action", ""),
        "user_escalation": repair.get("user_escalation", False),
        "dry_run": True,
        "writes": [],
        "forbidden_actions": ["sign", "archive", "tag", "merge", "push", "production_write"],
    }
    response["dispatch"] = build_dispatch(response, evidence)
    return response


def dispatch_kind_for(response):
    status = response.get("status")
    if status == RESULT_ADVANCE_READY:
        return DISPATCH_KIND_ADVANCE
    if status == RESULT_WAITING_FORMAL_SIGNOFF:
        return DISPATCH_KIND_SIGNOFF
    if status == RESULT_WAITING_PERMISSION:
        return DISPATCH_KIND_PERMISSION
    if status == RESULT_USER_ESCALATION_REQUIRED:
        return DISPATCH_KIND_USER_ESCALATION
    return DISPATCH_KIND_REPAIR


def build_dispatch(response, evidence):
    kind = dispatch_kind_for(response)
    return {
        "dispatch_kind": kind,
        "task_id": response.get("task_id", ""),
        "source_gate": response.get("from_gate", ""),
        "target_gate": response.get("to_gate", ""),
        "status": response.get("status", ""),
        "issues": response.get("issues", []),
        "dispatch_action": response.get("dispatch_action", ""),
        "user_escalation": response.get("user_escalation", False),
        "candidate_only": True,
        "no_role_signoff_claimed": True,
        "required_role": required_role_for_dispatch(response, evidence),
        "required_artifact_type": required_artifact_for_dispatch(response),
        "forbidden_claims": [
            "G5_PASS",
            "G6_PASS",
            "formal_signoff_completed",
            "archive_completed",
            "tag_completed",
            "merge_completed",
            "push_completed"
        ],
    }


def needs_formal_signoff_repair(response):
    if response.get("status") == RESULT_WAITING_FORMAL_SIGNOFF:
        return True
    return any(issue in FORMAL_SIGNOFF_REPAIR_ISSUES for issue in response.get("issues", []))


def required_role_for_dispatch(response, evidence):
    if needs_formal_signoff_repair(response):
        role = GATE_REQUIRED_SIGNOFF_ROLE.get(response.get("from_gate", ""), "")
        if role:
            return role
    return evidence.get("required_role", "")


def required_artifact_for_dispatch(response):
    if needs_formal_signoff_repair(response):
        return "formal_signoff"
    if response.get("status") == RESULT_ADVANCE_READY:
        if response.get("to_gate") in ("G5", "G6"):
            return "candidate"
        if response.get("to_gate") == "archive":
            return "archive_record"
    return "candidate"


def safe_filename(value):
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value or "UNKNOWN").strip("_")
    return cleaned or "UNKNOWN"


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


def write_dispatch_file(response, output_dir):
    dispatch = response.get("dispatch")
    if not dispatch:
        raise ValueError("response missing dispatch payload")
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    task_id = safe_filename(response.get("task_id", "UNKNOWN"))
    kind = safe_filename(dispatch.get("dispatch_kind", "dispatch"))
    filename = f"{task_id}_{kind}_{timestamp}.json"
    out_path = out_dir / filename
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generator": "scripts/stage_gate_auto_advance.py",
        "dry_run_source": False,
        "dispatch": dispatch,
        "response_snapshot": {k: v for k, v in response.items() if k != "dispatch"},
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    response["dry_run"] = False
    response["writes"] = [str(out_path)]
    return response


def run_self_test():
    registry = load_registry()

    cases = [
        (
            "G4 candidate with empty evidence is repair",
            {
                "task_id": "SELFTEST-G4",
                "gate": "G4",
                "artifact_type": "candidate",
                "result": "PASS",
                "actual_actor": "deepseek_live",
                "implementation_actor": "deepseek_live",
                "changed_files": [],
            },
            RESULT_REPAIR_DISPATCH_REQUIRED,
        ),
        (
            "G4 candidate claiming formal is repaired",
            {
                "task_id": "SELFTEST-G4-BAD",
                "gate": "G4",
                "artifact_type": "candidate",
                "result": "PASS",
                "claims_formal_signoff": True,
            },
            RESULT_REPAIR_DISPATCH_REQUIRED,
        ),
        (
            "G5 formal missing hmac waits signoff",
            {
                "task_id": "SELFTEST-G5",
                "gate": "G5",
                "artifact_type": "formal_signoff",
                "result": "PASS",
                "formal_signoff": {"role": "旧影", "signed": True, "actual_actor": "旧影"},
            },
            RESULT_WAITING_FORMAL_SIGNOFF,
        ),
        (
            "G5 formal signed advances",
            {
                "task_id": "SELFTEST-G5-OK",
                "gate": "G5",
                "artifact_type": "formal_signoff",
                "result": "PASS",
                "formal_signoff": {"role": "旧影", "signed": True, "sig_type": "HMAC-SHA256", "actual_actor": "旧影"},
            },
            RESULT_ADVANCE_READY,
        ),
        (
            "G6 production action escalates user",
            {
                "task_id": "SELFTEST-G6-PROD",
                "gate": "G6",
                "artifact_type": "formal_signoff",
                "result": "PASS",
                "formal_signoff": {"role": "腰子", "signed": True, "sig_type": "HMAC-SHA256", "actual_actor": "腰子"},
                "issues": ["production_action_without_user_confirmation"],
            },
            RESULT_USER_ESCALATION_REQUIRED,
        ),
        (
            "G5 wrong role is security repair even when hmac is missing",
            {
                "task_id": "SELFTEST-G5-WRONG-ROLE",
                "gate": "G5",
                "artifact_type": "formal_signoff",
                "result": "PASS",
                "formal_signoff": {"role": "阿黑", "signed": True},
            },
            RESULT_REPAIR_DISPATCH_REQUIRED,
        ),
        (
            "G4 codex implementation detected is repair",
            {
                "task_id": "SELFTEST-G4-CODEX",
                "gate": "G4",
                "artifact_type": "candidate",
                "result": "PASS",
                "implementation_actor": "codex",
                "actual_actor": "deepseek_live",
                "changed_files": [],
            },
            RESULT_REPAIR_DISPATCH_REQUIRED,
        ),
        (
            "G4 codex_write_detected true is repair",
            {
                "task_id": "SELFTEST-G4-CODEX-WRITE",
                "gate": "G4",
                "artifact_type": "candidate",
                "result": "PASS",
                "codex_write_detected": True,
                "actual_actor": "deepseek_live",
                "changed_files": [],
            },
            RESULT_REPAIR_DISPATCH_REQUIRED,
        ),
        (
            "G4 missing implementation evidence is repair",
            {
                "task_id": "SELFTEST-G4-MISSING-EVIDENCE",
                "gate": "G4",
                "artifact_type": "candidate",
                "result": "PASS",
            },
            RESULT_REPAIR_DISPATCH_REQUIRED,
        ),
        (
            "G4 deepseek live advances",
            {
                "task_id": "SELFTEST-G4-DEEPSEEK-OK",
                "gate": "G4",
                "artifact_type": "candidate",
                "result": "PASS",
                "actual_actor": "deepseek_live",
                "implementation_actor": "deepseek_live",
                "execution_model": "deepseek-via-claude-code",
                "live_model_call": True,
                "changed_files": ["test.py"],
                "tool_calls": [
                    {"name": "Read", "count": 3},
                    {"name": "Edit", "count": 1},
                ],
            },
            RESULT_ADVANCE_READY,
        ),
        (
            "G4 codex with self-filled g3_impl_allowed_by_user (no env var) is repair",
            {
                "task_id": "SELFTEST-G4-CODEX-NOENV",
                "gate": "G4",
                "artifact_type": "candidate",
                "result": "PASS",
                "implementation_actor": "codex",
                "actual_actor": "codex",
                "g3_impl_allowed_by_user": True,
                "changed_files": ["test.py"],
                "tool_calls": [{"name": "Read", "count": 2}],
                "live_model_call": True,
            },
            RESULT_REPAIR_DISPATCH_REQUIRED,
        ),
    ]

    expected_dispatch_actions = {
        "G4 codex implementation detected is repair": "invalidate_implementation_and_request_deepseek_rerun",
        "G4 codex_write_detected true is repair": "invalidate_implementation_and_request_deepseek_rerun",
        "G4 missing implementation evidence is repair": "create_evidence_completion_dispatch",
    }

    failures = []
    for name, evidence, expected in cases:
        actual = evaluate(registry, evidence)
        if actual["status"] != expected:
            failures.append({"case": name, "expected": expected, "actual": actual})
        if name in expected_dispatch_actions:
            expected_action = expected_dispatch_actions[name]
            if actual.get("dispatch_action") != expected_action:
                failures.append({
                    "case": f"{name} (dispatch_action)",
                    "expected": expected_action,
                    "actual": actual.get("dispatch_action"),
                })
        if name == "G5 wrong role is security repair even when hmac is missing":
            expected_action = "invalidate_artifact_and_request_correct_role_resign"
            if actual.get("dispatch_action") != expected_action:
                failures.append({
                    "case": f"{name} (dispatch_action)",
                    "expected": expected_action,
                    "actual": actual.get("dispatch_action"),
                })
            dispatch = actual.get("dispatch", {})
            if dispatch.get("required_role") != "旧影":
                failures.append({
                    "case": f"{name} (required_role)",
                    "expected": "旧影",
                    "actual": dispatch.get("required_role"),
                })
            if dispatch.get("required_artifact_type") != "formal_signoff":
                failures.append({
                    "case": f"{name} (required_artifact_type)",
                    "expected": "formal_signoff",
                    "actual": dispatch.get("required_artifact_type"),
                })

    if failures:
        print(json.dumps({"self_test": "BLOCK", "failures": failures}, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps({"self_test": "PASS", "cases": len(cases)}, ensure_ascii=False, indent=2))
    return 0


def main():
    parser = argparse.ArgumentParser(description="CCRT stage gate auto-advance dry-run evaluator")
    parser.add_argument("--evidence", help="Path to evidence JSON")
    parser.add_argument("--registry", default=str(REGISTRY_PATH), help="Path to stage_gate_registry.json")
    parser.add_argument("--self-test", action="store_true", help="Run built-in self tests")
    parser.add_argument("--write-dispatch", action="store_true", help="Write dispatch JSON to --output-dir")
    parser.add_argument("--output-dir", help="Directory for dispatch JSON when --write-dispatch is used")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    if not args.evidence:
        print("BLOCK: --evidence is required unless --self-test is used", file=sys.stderr)
        return 2

    if args.write_dispatch and not args.output_dir:
        print("BLOCK: --output-dir is required when --write-dispatch is used", file=sys.stderr)
        return 2

    registry = load_registry(args.registry)
    evidence = load_json(args.evidence)
    response = evaluate(registry, evidence)
    if args.write_dispatch:
        response = write_dispatch_file(response, args.output_dir)
    log_auto_advance_event(response, "scripts/stage_gate_auto_advance.py")
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0 if response["status"] in {
        RESULT_ADVANCE_READY,
        RESULT_REPAIR_DISPATCH_REQUIRED,
        RESULT_WAITING_FORMAL_SIGNOFF,
        RESULT_WAITING_PERMISSION,
        RESULT_USER_ESCALATION_REQUIRED,
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
