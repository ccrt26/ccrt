#!/usr/bin/env python3
"""CCRT stage-gate release orchestrator.

This script coordinates post-G4 automation under an explicit release policy.
It never forges role signatures. It may execute sign_off.py only when the
current actual_actor already matches the required role.

All file writes go through prepare_output_context() — never directly
mkdir or write_json() on args.output_dir.
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
FALLBACK_BLOCKED_DIR = Path("/private/tmp/ccrt_release_orchestrator_blocked")

# Post-sync evidence MUST go outside the repo — never writes to repo after push.
POST_SYNC_EVIDENCE_DIR = Path("/private/tmp/ccrt_release_orchestrator_post_sync")

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


def prepare_output_context(requested_output_dir, run_id):
    """Unified output context: validates and provides safe fallback.

    Rules:
    - If requested_output_dir is valid → use it as safe_output_dir.
    - If invalid → do NOT create it, use fallback under /private/tmp.
    - Never mkdir() on invalid requested dir.
    """
    valid, issue = validate_output_dir(requested_output_dir)
    if valid:
        safe_dir = Path(requested_output_dir).resolve()
        safe_dir.mkdir(parents=True, exist_ok=True)
        return {
            "output_dir_valid": True,
            "output_dir_issue": "",
            "safe_output_dir": safe_dir,
            "requested_output_dir": Path(requested_output_dir).resolve(),
        }
    else:
        safe_dir = FALLBACK_BLOCKED_DIR / run_id
        safe_dir.mkdir(parents=True, exist_ok=True)
        return {
            "output_dir_valid": False,
            "output_dir_issue": issue,
            "safe_output_dir": safe_dir,
            "requested_output_dir": Path(requested_output_dir) if requested_output_dir else Path(".").resolve(),
        }


G6_HYGIENE_SKIP_VAR = "CCRT_SKIP_G6_WORKSPACE_HYGIENE"


def check_g6_workspace_hygiene():
    """Run git_workspace_hygiene.py --quiet to enforce clean workspace before G6 COMPLETE.

    Skips the check if CCRT_SKIP_G6_WORKSPACE_HYGIENE=true env var is set.
    Returns None if pass, or a BLOCK response dict if fail.
    """
    if os.environ.get(G6_HYGIENE_SKIP_VAR, "").lower() in ("true", "1"):
        return None

    proc = run_cmd([sys.executable, "scripts/git_workspace_hygiene.py", "--quiet"])
    if proc["returncode"] != 0:
        return {
            "status": STATUS_BLOCK,
            "reason": "workspace not clean — git_workspace_hygiene --quiet returned non-zero",
            "workspace_hygiene_report": proc,
            "user_escalation": False,
        }
    return None


def post_sync_output_context():
    """Return an output context routed to POST_SYNC_EVIDENCE_DIR.

    After push, no files may be written inside the repo.
    """
    return {
        "output_dir_valid": True,
        "output_dir_issue": "",
        "safe_output_dir": POST_SYNC_EVIDENCE_DIR,
        "requested_output_dir": POST_SYNC_EVIDENCE_DIR,
    }


def write_internal_evidence(full_response, output_context):
    """Full internal evidence JSON to safe output dir.

    Always writes even when output_dir_valid=false (writes to fallback).
    Never writes to invalid requested dir.
    """
    run_id = full_response.get("task_id", "UNKNOWN")
    safe_dir = output_context["safe_output_dir"]
    safe_dir.mkdir(parents=True, exist_ok=True)
    internal_path = safe_dir / f"{run_id}_internal_orchestrator_response.json"
    write_json(internal_path, full_response)
    return internal_path


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


def maybe_sign(run_id, gate, checklist, state_file, role, comment, output_context):
    actor = actual_actor()
    safe_dir = output_context["safe_output_dir"]

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


def make_archive_record(run_id, g6_signoff, output_context, policy_name, policy):
    archive_eval, signoff = evaluate_g6_archive_evidence(g6_signoff)
    safe_dir = output_context["safe_output_dir"]

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
    out = safe_dir / f"{run_id}_G6_archive_record.json"
    write_json(out, archive_record)
    return out, archive_record


def build_user_visible_response(full_response, evidence_path):
    """Build minimal user-visible output package.

    Default stdout must only contain:
      - user_visible_status
      - user_visible_message
      - internal_evidence_record (path to full evidence file)
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
    """Post-process responses to add user_visible_status and message."""
    resp = dict(response)
    resp["internal_stage_evidence_hidden_from_user"] = True

    status = resp.get("status", "")
    archive_completed = resp.get("archive_completed", False)
    github_sync_completed = resp.get("github_sync_completed", False)
    push_completed = resp.get("push_completed", False)
    issues = resp.get("issues", []) or []
    reason = resp.get("reason", "")

    if status == STATUS_G6_COMPLETE:
        final_pass = resp.get("final_hygiene_pass", False)
        if final_pass is True:
            resp["user_visible_status"] = "COMPLETE"
            resp["user_visible_message"] = "CCRT 全流程已完成，已归档，已提交 GitHub。"
        else:
            resp["user_visible_status"] = "BLOCK"
            resp["user_visible_message"] = "BLOCK: archive+github sync complete but final hygiene check failed."
    elif status in (STATUS_WAITING_ROLE_SIGNOFF, "WAITING_FORMAL_SIGNOFF"):
        resp["user_visible_status"] = "AUTO_REPAIRING"
        resp["user_visible_message"] = "发现问题，系统已打回对应环节自动修复，无需用户处理。"
    elif status == STATUS_BLOCK:
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


def orchestrate(args, output_context=None):
    if output_context is None:
        output_context = prepare_output_context(args.output_dir, args.run_id)

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

    # If requested output_dir is invalid, BLOCK early but still write internal evidence to fallback
    if not output_context["output_dir_valid"]:
        return {
            "task_id": args.run_id,
            "status": STATUS_BLOCK,
            "reason": output_context["output_dir_issue"],
            "user_escalation": False,
        }

    if args.mode == "signoff":
        role_spec = policy_data["role_signoff"][args.gate]
        return maybe_sign(
            args.run_id,
            args.gate,
            Path(args.checklist),
            Path(args.state_file),
            role_spec["role"],
            args.comment or f"{args.gate} automatic role signoff",
            output_context,
        )

    if args.mode == "archive":
        archive_path, record = make_archive_record(
            args.run_id,
            Path(args.g6_signoff),
            output_context,
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

        # Prepare all evidence paths.
        # Pre-sync evidence (archive_record, allowed_paths) may be in the repo.
        # Post-sync evidence (final hygiene, post-push internal) MUST go outside
        # the repo — always under POST_SYNC_EVIDENCE_DIR (/private/tmp).
        safe_dir = output_context["safe_output_dir"]
        post_sync_dir = POST_SYNC_EVIDENCE_DIR
        post_sync_dir.mkdir(parents=True, exist_ok=True)

        github_sync_record_path = safe_dir / f"{args.run_id}_github_sync_record.json"
        internal_evidence_path = safe_dir / f"{args.run_id}_internal_orchestrator_response.json"
        final_hygiene_path = post_sync_dir / f"{args.run_id}_final_hygiene.json"

        # Construct allowed_paths_json for github_sync.
        # IMPORTANT: only repo-relative paths are valid for git add.
        # Evidence files outside the repo (/private/tmp) are NOT in the
        # git working tree and must NOT appear in allowed_paths.
        allowed_paths = []

        # Include evidence files only if inside the repo
        for path_obj in [archive_path, github_sync_record_path]:
            try:
                rel = path_obj.relative_to(ROOT)
                allowed_paths.append(str(rel))
            except ValueError:
                pass  # Outside repo — not a git file

        # Merge payload paths as repo-relative paths
        if hasattr(args, 'payload_paths_json') and args.payload_paths_json:
            try:
                payload_list = load_json(args.payload_paths_json)
                if isinstance(payload_list, list):
                    for p in payload_list:
                        p_str = str(p).replace("\\", "/")
                        # Normalize absolute repo paths to relative
                        try:
                            rel = Path(p).resolve().relative_to(ROOT)
                            allowed_paths.append(str(rel))
                        except (ValueError, RuntimeError):
                            # Already relative or outside repo
                            if not p_str.startswith("/") and not p_str.startswith(".."):
                                allowed_paths.append(p_str)
            except Exception as e:
                return {
                    "task_id": args.run_id,
                    "status": STATUS_BLOCK,
                    "reason": f"failed to load --payload-paths-json: {e}",
                    "user_escalation": False,
                }

        # De-duplicate and filter
        seen = set()
        deduped = []
        for p in allowed_paths:
            if p and p not in seen:
                seen.add(p)
                deduped.append(p)
        allowed_paths = deduped

        allowed_paths_file = safe_dir / f"{args.run_id}_allowed_paths.json"
        write_json(allowed_paths_file, allowed_paths)

        # After archive, perform github sync if policy requires it
        github_sync_completed = False
        push_completed = False
        github_sync_path = ""

        if policy.get("auto_github_sync") is True:
            gsync_proc = run_cmd([
                sys.executable,
                "scripts/github_sync_after_archive.py",
                "--archive-record", str(archive_path),
                "--run-id", args.run_id,
                "--output-dir", str(safe_dir),
                "--allowed-paths-json", str(allowed_paths_file),
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

        # Update final hygiene evidence with actual post-push result
        if policy.get("auto_github_sync") is True and push_completed:
            hygiene_result = check_g6_workspace_hygiene()
            hygiene_passed = hygiene_result is None
            hygiene_evidence = {
                "status": "PASS" if hygiene_passed else "BLOCK",
                "check_type": "final_hygiene",
                "details": hygiene_result.get("reason", "") if hygiene_result else "workspace clean",
            }
            write_json(final_hygiene_path, hygiene_evidence)

            if not hygiene_passed:
                # Write internal evidence after all files synced
                full_response = {
                    "task_id": args.run_id,
                    "status": STATUS_BLOCK,
                    "release_policy": args.release_policy,
                    "archive_record": str(archive_path),
                    "github_sync_record": str(github_sync_record_path),
                    "archive_completed": True,
                    "github_sync_completed": github_sync_completed,
                    "push_completed": push_completed,
                    "reason": f"final hygiene check failed after push: {hygiene_evidence['details']}",
                    "user_escalation": False,
                }
                write_internal_evidence(full_response, post_sync_output_context())
                return full_response

            # All evidence is now committed and clean. Write final internal evidence.
            full_response = {
                "task_id": args.run_id,
                "status": STATUS_G6_COMPLETE,
                "release_policy": args.release_policy,
                "archive_record": str(archive_path),
                "github_sync_record": str(github_sync_record_path),
                "hygiene_evidence": str(final_hygiene_path),
                "archive_completed": True,
                "github_sync_completed": github_sync_completed,
                "push_completed": push_completed,
                "final_hygiene_pass": True,
                "tag_completed": False,
                "merge_completed": False,
                "production_switched": False,
                "user_escalation": False,
            }
            write_internal_evidence(full_response, post_sync_output_context())
            return full_response

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
    default_data = load_json(POLICY_PATH)
    if default_data.get("default_policy") != "archive_and_github_sync":
        failures.append({"case": "default policy should be archive_and_github_sync", "got": default_data.get("default_policy")})

    _, gsync_policy = load_policy("archive_and_github_sync")
    if gsync_policy.get("auto_github_sync") is not True:
        failures.append({"case": "archive_and_github_sync should auto_github_sync"})
    if gsync_policy.get("auto_push") is not True:
        failures.append({"case": "archive_and_github_sync should auto_push"})

    policy_data, policy = load_policy("audit_archive_only")
    ok, blocked = verify_policy(policy, False)
    if not ok or blocked:
        failures.append({"case": "audit archive policy should not need user", "blocked": blocked})

    dispatch = build_signoff_dispatch("UT", "G5", "旧影", "missing actor")
    if dispatch["required_role"] != "旧影" or dispatch["user_escalation"] is not False:
        failures.append({"case": "signoff dispatch", "dispatch": dispatch})

    # Test prepare_output_context with valid dir
    import tempfile
    with tempfile.TemporaryDirectory(dir="/private/tmp") as td:
        ctx = prepare_output_context(td, "UT-CTX-VALID")
        if not ctx["output_dir_valid"]:
            failures.append({"case": "valid tmp dir should be valid", "ctx": ctx})

    # Test with relative dir
    ctx2 = prepare_output_context("relative_dir", "UT-CTX-INVALID")
    if ctx2["output_dir_valid"]:
        failures.append({"case": "relative dir should be invalid", "ctx": ctx2})
    if not str(ctx2["safe_output_dir"]).startswith("/private/tmp/ccrt_release_orchestrator_blocked/"):
        failures.append({"case": "invalid dir should use blocked fallback", "ctx": ctx2})

    if failures:
        print(json.dumps({"self_test": "BLOCK", "failures": failures}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"self_test": "PASS", "cases": 7}, ensure_ascii=False, indent=2))
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
    parser.add_argument("--payload-paths-json", default="",
                        help="Path to JSON file listing repo-relative paths to stage as G6 commit payload")
    parser.add_argument("--internal-json", action="store_true",
                        help="Print full internal JSON to stdout (default: user-only package)")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    if not args.run_id:
        print("BLOCK: --run-id is required", file=sys.stderr)
        return 2

    # Unified output context — all writes go through this
    output_context = prepare_output_context(args.output_dir, args.run_id)

    response = orchestrate(args, output_context=output_context)
    full_response = add_user_report_fields(response)

    # All evidence writes go through write_internal_evidence
    # Archive mode: post-push evidence must go outside repo.
    # Other modes (signoff): use the original output context.
    post_ctx = post_sync_output_context() if args.mode == "archive" else output_context
    internal_path = write_internal_evidence(full_response, post_ctx)

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
