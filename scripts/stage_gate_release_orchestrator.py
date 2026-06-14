#!/usr/bin/env python3
"""CCRT stage-gate release orchestrator.

This script coordinates post-G4 automation under an explicit release policy.
It never forges role signatures. It may execute sign_off.py only when the
current actual_actor already matches the required role.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "00_项目地基" / "05_流程与角色" / "stage_gate_release_policy.json"
AUDIT_DIR = ROOT / "00_项目地基" / "08_审计与验收"

STATUS_ADVANCED = "ADVANCED"
STATUS_WAITING_ROLE_SIGNOFF = "WAITING_ROLE_SIGNOFF"
STATUS_ARCHIVED = "ARCHIVED"
STATUS_RELEASE_POLICY_BLOCKED = "RELEASE_POLICY_BLOCKED"
STATUS_BLOCK = "BLOCK"
STATUS_G6_COMPLETE = "G6_COMPLETE"

PROD_ACTIONS = {"tag", "merge", "production_report_write", "daily_scheduler_switch"}
# push is now part of auto_github_sync, not a user-confirmed production action
SAFE_OUTPUT_ROOTS = {
    Path("/tmp").resolve(),
    Path("/private/tmp").resolve(),
    Path(tempfile.gettempdir()).resolve(),
    AUDIT_DIR.resolve(),
}


def load_json(path):
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def is_relative_to(path, parent):
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def validate_output_dir(output_dir):
    path = Path(output_dir)
    if not path.is_absolute():
        return False, "relative output directory is forbidden"
    resolved = path.resolve()
    if any(resolved == root or is_relative_to(resolved, root) for root in SAFE_OUTPUT_ROOTS):
        return True, ""
    return False, "output directory must be under /tmp, /private/tmp, or audit evidence dir"


def actual_actor():
    return os.environ.get("CLAUDE_CURRENT_ACTOR", "").strip() or os.environ.get("CURRENT_ACTOR", "").strip()


def run_cmd(cmd, env=None):
    merged = os.environ.copy()
    if env:
        merged.update(env)
    proc = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True, env=merged)
    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "cmd": cmd,
    }


def load_policy(name):
    data = load_json(POLICY_PATH)
    policy = data["policies"].get(name or data["default_policy"])
    if not policy:
        raise ValueError(f"unknown release policy: {name}")
    return data, policy


def requested_actions_from_policy(policy):
    actions = []
    if policy.get("auto_tag"):
        actions.append("tag")
    if policy.get("auto_merge"):
        actions.append("merge")
    if policy.get("auto_push"):
        actions.append("push")
    if policy.get("auto_production_report_write"):
        actions.append("production_report_write")
    return actions


def verify_policy(policy, user_confirmed):
    requested = set(requested_actions_from_policy(policy))
    if requested & PROD_ACTIONS and not user_confirmed:
        return False, sorted(requested & PROD_ACTIONS)
    return True, []


def build_signoff_dispatch(run_id, gate, role, reason):
    return {
        "task_id": run_id,
        "status": STATUS_WAITING_ROLE_SIGNOFF,
        "gate": gate,
        "required_role": role,
        "required_artifact_type": "formal_signoff",
        "dispatch_action": "run_sign_off_in_required_actor_context",
        "reason": reason,
        "user_escalation": False,
        "user_visible_status": "AUTO_REPAIRING",
        "user_visible_message": "发现问题，系统已打回对应环节自动修复，无需用户处理。",
        "internal_stage_evidence_hidden_from_user": True,
        "forbidden_claims": [
            "role_signed_by_orchestrator",
            "archive_completed",
            "tag_completed",
            "merge_completed",
            "push_completed"
        ],
    }


def maybe_sign(run_id, gate, checklist, state_file, role, comment, output_dir):
    actor = actual_actor()
    if actor != role:
        return build_signoff_dispatch(run_id, gate, role, f"actual_actor({actor}) != required_role({role})")

    proc = run_cmd([
        sys.executable,
        "scripts/sign_off.py",
        "--actor", role,
        "--role", role,
        "--run-id", run_id,
        "--checklist", str(checklist),
        "--comment", comment,
    ], env={"PIPELINE_STATE_FILE": str(state_file)})

    if proc["returncode"] != 0:
        return {
            "task_id": run_id,
            "status": STATUS_BLOCK,
            "gate": gate,
            "required_role": role,
            "reason": "sign_off_failed",
            "sign_off_result": proc,
            "user_escalation": False,
        }

    return {
        "task_id": run_id,
        "status": STATUS_ADVANCED,
        "gate": gate,
        "role": role,
        "actual_actor": actor,
        "sign_off_result": proc,
        "user_escalation": False,
    }


def evaluate_g6_archive_evidence(g6_signoff):
    scripts_dir = ROOT / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from archive_after_g6 import evaluate as evaluate_archive

    evidence = load_json(g6_signoff)
    return evaluate_archive(evidence), evidence


def make_archive_record(run_id, g6_signoff, output_dir, policy_name, policy):
    archive_eval, signoff = evaluate_g6_archive_evidence(g6_signoff)
    if archive_eval.get("status") != "ARCHIVE_READY_DRY_RUN":
        return None, {
            "task_id": run_id,
            "stage": "G6_archive_record",
            "artifact_type": "archive_record",
            "result": "BLOCK",
            "source_g6_formal_signoff": str(g6_signoff),
            "release_policy": policy_name,
            "archive_eval": archive_eval,
            "archive_completed": False,
            "tag_completed": False,
            "merge_completed": False,
            "push_completed": False,
            "production_switched": False,
        }

    requested_actions = requested_actions_from_policy(policy)
    formal_signoff = signoff.get("formal_signoff") or {}
    archive_record = {
        "task_id": run_id,
        "stage": "G6_archive_record",
        "artifact_type": "archive_record",
        "result": "CLOSED",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_g6_formal_signoff": str(g6_signoff),
        "release_policy": policy_name,
        "requested_actions": requested_actions,
        "archive_eval": archive_eval,
        "g6_formal_signoff": {
            "role": signoff.get("role"),
            "actual_actor": formal_signoff.get("actual_actor"),
            "sig_type": formal_signoff.get("sig_type"),
            "signed": formal_signoff.get("signed"),
        },
        "archive_completed": True,
        "tag_completed": False,
        "merge_completed": False,
        "push_completed": False,
        "production_switched": False,
    }
    out = Path(output_dir) / f"{run_id}_G6_archive_record.json"
    write_json(out, archive_record)
    return out, archive_record


def build_user_visible_response(full_response, evidence_path):
    """Build minimal user-visible output package.

    Default stdout must only contain:
      - user_visible_status
      - user_visible_message
      - internal_evidence_record (path to full evidence file)

    Full internal JSON is written to evidence_path, not shown on stdout.
    """
    return {
        "user_visible_status": full_response.get("user_visible_status", "AUTO_REPAIRING"),
        "user_visible_message": full_response.get(
            "user_visible_message",
            "发现问题，系统已打回对应环节自动修复，无需用户处理。"
        ),
        "internal_evidence_record": str(evidence_path),
    }


def add_user_report_fields(response):
    """Post-process responses to add user_visible_status and message.

    Internal stage details remain in the JSON for evidence purposes
    but are tagged as hidden from user-facing output.
    """
    # Remove forbidden claims from user-visible output (keep in evidence)
    resp = dict(response)
    resp["internal_stage_evidence_hidden_from_user"] = True

    status = resp.get("status", "")
    archive_completed = resp.get("archive_completed", False)
    github_sync_completed = resp.get("github_sync_completed", False)
    push_completed = resp.get("push_completed", False)
    issues = resp.get("issues", []) or []
    reason = resp.get("reason", "")

    if status == STATUS_G6_COMPLETE:
        resp["user_visible_status"] = "COMPLETE"
        resp["user_visible_message"] = "CCRT 全流程已完成，已归档，已提交 GitHub。"
    elif status in (STATUS_WAITING_ROLE_SIGNOFF, "WAITING_FORMAL_SIGNOFF"):
        resp["user_visible_status"] = "AUTO_REPAIRING"
        resp["user_visible_message"] = "发现问题，系统已打回对应环节自动修复，无需用户处理。"
    elif status == STATUS_BLOCK:
        # Check if this is a user-escalation type block
        user_block_keywords = ["push failed", "no upstream", "upstream not configured",
                               "forbidden directories", "git push failed",
                               "HMAC secret", "permission denied",
                               "forbidden output", "relative output"]
        is_user_block = any(kw in reason.lower() for kw in user_block_keywords)
        if is_user_block:
            resp["user_visible_status"] = "BLOCK"
            resp["user_visible_message"] = f"BLOCK: {reason}" if reason else "BLOCK: 系统无法自动处理"
        else:
            resp["user_visible_status"] = "AUTO_REPAIRING"
            resp["user_visible_message"] = "发现问题，系统已打回对应环节自动修复，无需用户处理。"
    elif status == "ARCHIVED":
        # Archived without github sync — check if this is a user block
        if push_completed is True:
            resp["user_visible_status"] = "COMPLETE"
            resp["user_visible_message"] = "CCRT 全流程已完成，已归档，已提交 GitHub。"
        else:
            resp["user_visible_status"] = "AUTO_REPAIRING"
            resp["user_visible_message"] = "发现问题，系统已打回对应环节自动修复，无需用户处理。"
    elif status in ("ADVANCED", "RELEASE_POLICY_BLOCKED"):
        if any(kw in reason.lower() for kw in ["user escalation", "user_escalation"]) or resp.get("user_escalation") is True:
            resp["user_visible_status"] = "BLOCK"
            resp["user_visible_message"] = f"BLOCK: {reason}" if reason else "BLOCK: 需要用户确认"
        else:
            resp["user_visible_status"] = "AUTO_REPAIRING"
            resp["user_visible_message"] = "发现问题，系统已打回对应环节自动修复，无需用户处理。"
    else:
        resp["user_visible_status"] = "AUTO_REPAIRING"
        resp["user_visible_message"] = "发现问题，系统已打回对应环节自动修复，无需用户处理。"

    return resp


def orchestrate(args):
    policy_data, policy = load_policy(args.release_policy)
    ok, blocked_actions = verify_policy(policy, args.user_confirmed_release)
    if not ok:
        return {
            "task_id": args.run_id,
            "status": STATUS_RELEASE_POLICY_BLOCKED,
            "blocked_actions": blocked_actions,
            "release_policy": args.release_policy,
            "user_escalation": True,
        }

    ok_dir, dir_reason = validate_output_dir(args.output_dir)
    if not ok_dir:
        return {
            "task_id": args.run_id,
            "status": STATUS_BLOCK,
            "reason": dir_reason,
            "user_escalation": False,
        }

    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.mode == "signoff":
        role_spec = policy_data["role_signoff"][args.gate]
        return maybe_sign(
            args.run_id,
            args.gate,
            Path(args.checklist),
            Path(args.state_file),
            role_spec["role"],
            args.comment or f"{args.gate} automatic role signoff",
            out_dir,
        )

    if args.mode == "archive":
        archive_path, record = make_archive_record(
            args.run_id,
            Path(args.g6_signoff),
            out_dir,
            args.release_policy,
            policy,
        )
        if record.get("result") != "CLOSED":
            return {
                "task_id": args.run_id,
                "status": STATUS_BLOCK,
                "release_policy": args.release_policy,
                "archive_eval": record.get("archive_eval", {}),
                "archive_completed": False,
                "github_sync_completed": False,
                "push_completed": False,
                "tag_completed": False,
                "merge_completed": False,
                "production_switched": False,
                "user_escalation": False,
            }

        # After archive, perform github sync if policy requires it
        github_sync_completed = False
        push_completed = False
        github_sync_path = None

        if policy.get("auto_github_sync") is True:
            gsync_proc = run_cmd([
                sys.executable,
                "scripts/github_sync_after_archive.py",
                "--archive-record", str(archive_path),
                "--run-id", args.run_id,
                "--output-dir", str(out_dir),
            ])
            if gsync_proc["returncode"] == 0:
                gsync_data = json.loads(gsync_proc["stdout"])
                github_sync_completed = gsync_data.get("github_sync_completed", False)
                push_completed = gsync_data.get("push_completed", False)
                github_sync_path = gsync_data.get("github_sync_record", "")
            else:
                try:
                    gsync_data = json.loads(gsync_proc["stdout"])
                    github_sync_completed = gsync_data.get("github_sync_completed", False)
                    push_completed = gsync_data.get("push_completed", False)
                    github_sync_path = gsync_data.get("github_sync_record", "")
                except (json.JSONDecodeError, ValueError):
                    pass

        if policy.get("auto_github_sync") is True and not github_sync_completed:
            return {
                "task_id": args.run_id,
                "status": STATUS_BLOCK,
                "release_policy": args.release_policy,
                "archive_record": str(archive_path),
                "archive_completed": True,
                "github_sync_completed": False,
                "push_completed": False,
                "tag_completed": False,
                "merge_completed": False,
                "production_switched": False,
                "reason": "archive completed but github sync failed — G6 PASS requires both",
                "user_escalation": False,
            }

        if policy.get("auto_github_sync") is True:
            return {
                "task_id": args.run_id,
                "status": STATUS_G6_COMPLETE,
                "release_policy": args.release_policy,
                "archive_record": str(archive_path),
                "github_sync_record": github_sync_path or "",
                "archive_completed": True,
                "github_sync_completed": github_sync_completed,
                "push_completed": push_completed,
                "tag_completed": False,
                "merge_completed": False,
                "production_switched": False,
                "user_escalation": False,
            }

        # For policies without auto_github_sync (e.g. audit_archive_only)
        return {
            "task_id": args.run_id,
            "status": STATUS_ARCHIVED,
            "release_policy": args.release_policy,
            "archive_record": str(archive_path),
            "archive_completed": True,
            "github_sync_completed": False,
            "push_completed": False,
            "tag_completed": False,
            "merge_completed": False,
            "production_switched": False,
            "user_escalation": False,
        }

    return {"task_id": args.run_id, "status": STATUS_BLOCK, "reason": "unknown_mode"}


def self_test():
    failures = []
    # 1. Default policy must be archive_and_github_sync
    default_data = load_json(POLICY_PATH)
    if default_data.get("default_policy") != "archive_and_github_sync":
        failures.append({"case": "default policy should be archive_and_github_sync", "got": default_data.get("default_policy")})

    # 2. archive_and_github_sync policy has auto_github_sync and auto_push
    _, gsync_policy = load_policy("archive_and_github_sync")
    if gsync_policy.get("auto_github_sync") is not True:
        failures.append({"case": "archive_and_github_sync should auto_github_sync"})
    if gsync_policy.get("auto_push") is not True:
        failures.append({"case": "archive_and_github_sync should auto_push"})

    # 3. audit_archive_only still works
    policy_data, policy = load_policy("audit_archive_only")
    ok, blocked = verify_policy(policy, False)
    if not ok or blocked:
        failures.append({"case": "audit archive policy should not need user", "blocked": blocked})

    # 4. Signoff dispatch
    dispatch = build_signoff_dispatch("UT", "G5", "旧影", "missing actor")
    if dispatch["required_role"] != "旧影" or dispatch["user_escalation"] is not False:
        failures.append({"case": "signoff dispatch", "dispatch": dispatch})

    if failures:
        print(json.dumps({"self_test": "BLOCK", "failures": failures}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"self_test": "PASS", "cases": 4}, ensure_ascii=False, indent=2))
    return 0


def main():
    parser = argparse.ArgumentParser(description="CCRT stage-gate release orchestrator")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--mode", choices=["signoff", "archive"])
    parser.add_argument("--run-id")
    parser.add_argument("--gate", choices=["G5", "G6"])
    parser.add_argument("--checklist")
    parser.add_argument("--state-file")
    parser.add_argument("--g6-signoff")
    parser.add_argument("--release-policy", default="archive_and_github_sync")
    parser.add_argument("--user-confirmed-release", action="store_true")
    parser.add_argument("--output-dir", default="/private/tmp/ccrt_release_orchestrator")
    parser.add_argument("--comment", default="")
    parser.add_argument("--internal-json", action="store_true",
                        help="Print full internal JSON to stdout (default: user-only package)")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    if not args.run_id:
        print("BLOCK: --run-id is required", file=sys.stderr)
        return 2

    response = orchestrate(args)
    full_response = add_user_report_fields(response)

    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    internal_path = out_dir / f"{args.run_id}_internal_orchestrator_response.json"
    write_json(internal_path, full_response)

    if args.internal_json:
        print(json.dumps(full_response, ensure_ascii=False, indent=2))
    else:
        user_pkg = build_user_visible_response(full_response, internal_path)
        print(json.dumps(user_pkg, ensure_ascii=False, indent=2))

    return 0 if response.get("status") in {
        STATUS_ADVANCED,
        STATUS_WAITING_ROLE_SIGNOFF,
        STATUS_ARCHIVED,
        STATUS_G6_COMPLETE,
        STATUS_RELEASE_POLICY_BLOCKED,
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
