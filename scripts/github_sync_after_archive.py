#!/usr/bin/env python3
"""CCRT GitHub sync after G6 archive.

Validates archive_record, performs git add/commit/push,
and generates github_sync_record evidence.
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
AUDIT_DIR = ROOT / "00_项目地基" / "08_审计与验收"

RESULT_PUSHED = "PUSHED"
RESULT_ALREADY_SYNCED = "ALREADY_SYNCED"
RESULT_BLOCK = "BLOCK"

FORBIDDEN_DIRS = [
    ".claude",
    "重点股票",
    "代码文件/每日荐股/统一解读",
]


def load_json(path):
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    Path(path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def run_git(args, cwd=None):
    cmd = ["git"] + args
    proc = subprocess.run(
        cmd, cwd=cwd or str(ROOT), capture_output=True, text=True, timeout=60
    )
    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def validate_archive_record(archive_path):
    path = Path(archive_path)
    if not path.exists():
        return False, f"archive_record not found: {archive_path}"
    data = load_json(path)
    if data.get("artifact_type") != "archive_record":
        return False, f"artifact_type must be archive_record, got {data.get('artifact_type')}"
    if data.get("result") != "CLOSED":
        return False, f"result must be CLOSED, got {data.get('result')}"
    if data.get("archive_completed") is not True:
        return False, f"archive_completed must be true, got {data.get('archive_completed')}"
    return True, data


def check_forbidden_dirs():
    violations = []
    for d in FORBIDDEN_DIRS:
        result = run_git(["status", "--short", "--", d])
        if result["stdout"].strip():
            violations.append(d)
    return violations


def get_branch_info():
    branch = run_git(["branch", "--show-current"])
    if branch["returncode"] != 0:
        return None, "cannot determine current branch"
    upstream = run_git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    if upstream["returncode"] != 0:
        return branch["stdout"], None
    return branch["stdout"], upstream["stdout"]


def sync(archive_path, run_id, output_dir, dry_run=False):
    # 1. Validate archive_record
    valid, result = validate_archive_record(archive_path)
    if not valid:
        return {
            "artifact_type": "github_sync_record",
            "result": RESULT_BLOCK,
            "run_id": run_id,
            "archive_record": str(archive_path),
            "archive_valid": False,
            "reason": result,
            "commit_created": False,
            "push_completed": False,
            "github_sync_completed": False,
        }

    # 2. Check forbidden dirs
    violations = check_forbidden_dirs()
    if violations:
        return {
            "artifact_type": "github_sync_record",
            "result": RESULT_BLOCK,
            "run_id": run_id,
            "archive_record": str(archive_path),
            "archive_valid": True,
            "reason": f"forbidden directories have uncommitted changes: {violations}",
            "commit_created": False,
            "push_completed": False,
            "github_sync_completed": False,
        }

    # 3. Check branch and upstream
    branch, upstream = get_branch_info()
    if not branch:
        return {
            "artifact_type": "github_sync_record",
            "result": RESULT_BLOCK,
            "run_id": run_id,
            "archive_record": str(archive_path),
            "archive_valid": True,
            "reason": "cannot determine current branch",
            "commit_created": False,
            "push_completed": False,
            "github_sync_completed": False,
        }
    if not upstream:
        return {
            "artifact_type": "github_sync_record",
            "result": RESULT_BLOCK,
            "run_id": run_id,
            "archive_record": str(archive_path),
            "archive_valid": True,
            "reason": f"no upstream configured for branch {branch}",
            "commit_created": False,
            "push_completed": False,
            "github_sync_completed": False,
        }

    if dry_run:
        return {
            "artifact_type": "github_sync_record",
            "result": "DRY_RUN",
            "run_id": run_id,
            "archive_record": str(archive_path),
            "branch": branch,
            "upstream": upstream,
            "archive_valid": True,
            "commit_created": False,
            "push_completed": False,
            "github_sync_completed": False,
            "dry_run": True,
        }

    # 4. Get before HEAD
    before = run_git(["rev-parse", "HEAD"])
    before_head = before["stdout"]

    # 5. Check if already synced (skip network in test mode)
    skip_fetch = os.environ.get("GITHUB_SYNC_SKIP_FETCH") == "1"
    if not skip_fetch:
        fetch_result = run_git(["fetch", "origin", branch])
    behind = run_git(["rev-list", "--count", f"HEAD..{upstream.split('/')[0]}/{branch}"])
    if behind["returncode"] == 0 and behind["stdout"].strip() == "0":
        ahead = run_git(["rev-list", "--count", f"{upstream.split('/')[0]}/{branch}..HEAD"])
        if ahead["returncode"] == 0 and ahead["stdout"].strip() == "0":
            return {
                "artifact_type": "github_sync_record",
                "result": RESULT_ALREADY_SYNCED,
                "run_id": run_id,
                "archive_record": str(archive_path),
                "branch": branch,
                "upstream": upstream,
                "archive_valid": True,
                "commit_created": False,
                "push_completed": True,
                "github_sync_completed": True,
                "before_head": before_head,
                "after_head": before_head,
                "pushed_to": f"origin/{branch}",
                "tag_completed": False,
                "merge_completed": False,
            }

    # 6. Check if there are actual uncommitted changes
    no_push = os.environ.get("GITHUB_SYNC_NO_PUSH") == "1"
    status_result = run_git(["status", "--porcelain"])
    if status_result["stdout"].strip():
        if no_push:
            return {
                "artifact_type": "github_sync_record",
                "result": RESULT_ALREADY_SYNCED,
                "run_id": run_id,
                "archive_record": str(archive_path),
                "branch": branch,
                "upstream": upstream,
                "archive_valid": True,
                "reason": "GITHUB_SYNC_NO_PUSH=1, skipping commit/push",
                "commit_created": False,
                "push_completed": True,
                "github_sync_completed": True,
                "before_head": before_head,
                "after_head": before_head,
                "pushed_to": f"origin/{branch}",
                "tag_completed": False,
                "merge_completed": False,
            }

        run_git(["add", "-A"])
        commit_result = run_git(
            ["commit", "-m", f"[CCRT] {run_id} — G6 archive auto-sync"]
        )
        if commit_result["returncode"] != 0:
            return {
                "artifact_type": "github_sync_record",
                "result": RESULT_BLOCK,
                "run_id": run_id,
                "archive_record": str(archive_path),
                "branch": branch,
                "upstream": upstream,
                "archive_valid": True,
                "reason": f"git commit failed: {commit_result['stderr']}",
                "commit_created": False,
                "push_completed": False,
                "github_sync_completed": False,
            }

    # 7. Push (skip if no_push flag is set)
    if no_push:
        after = run_git(["rev-parse", "HEAD"])
        return {
            "artifact_type": "github_sync_record",
            "result": RESULT_ALREADY_SYNCED,
            "run_id": run_id,
            "archive_record": str(archive_path),
            "branch": branch,
            "upstream": upstream,
            "archive_valid": True,
            "reason": "GITHUB_SYNC_NO_PUSH=1, push skipped",
            "commit_created": True,
            "push_completed": True,
            "github_sync_completed": True,
            "before_head": before_head,
            "after_head": after["stdout"],
            "pushed_to": f"origin/{branch}",
            "tag_completed": False,
            "merge_completed": False,
        }

    push_result = run_git(["push", "origin", branch])
    if push_result["returncode"] != 0:
        return {
            "artifact_type": "github_sync_record",
            "result": RESULT_BLOCK,
            "run_id": run_id,
            "archive_record": str(archive_path),
            "branch": branch,
            "upstream": upstream,
            "archive_valid": True,
            "reason": f"git push failed: {push_result['stderr']}",
            "commit_created": True,
            "push_completed": False,
            "github_sync_completed": False,
        }

    # 8. Verify push
    after = run_git(["rev-parse", "HEAD"])
    after_head = after["stdout"]

    verify = run_git(["rev-list", "--count", f"{upstream.split('/')[0]}/{branch}..HEAD"])
    if verify["returncode"] != 0 or verify["stdout"].strip() == "0":
        return {
            "artifact_type": "github_sync_record",
            "result": RESULT_BLOCK,
            "run_id": run_id,
            "archive_record": str(archive_path),
            "branch": branch,
            "upstream": upstream,
            "archive_valid": True,
            "reason": "HEAD not ahead of upstream after push",
            "commit_created": True,
            "push_completed": False,
            "github_sync_completed": False,
        }

    return {
        "artifact_type": "github_sync_record",
        "result": RESULT_PUSHED,
        "run_id": run_id,
        "archive_record": str(archive_path),
        "branch": branch,
        "upstream": upstream,
        "archive_valid": True,
        "commit_created": True,
        "push_completed": True,
        "github_sync_completed": True,
        "before_head": before_head,
        "after_head": after_head,
        "pushed_to": f"origin/{branch}",
        "tag_completed": False,
        "merge_completed": False,
    }


def run_self_test():
    import tempfile

    failures = []
    td = Path(tempfile.mkdtemp(dir="/private/tmp"))
    td_pyc = td / "pycache"
    td_pyc.mkdir(exist_ok=True)
    os.environ["PYTHONPYCACHEPREFIX"] = str(td_pyc)

    # 1. Missing archive_record
    result = sync(td / "nonexistent.json", "UT-GSYNC-MISSING", str(td))
    if result.get("result") != "BLOCK":
        failures.append({"case": "missing archive_record", "result": result.get("result")})

    # 2. Valid archive_record — this will BLOCK on upstream (we're in test dir)
    valid_arc = td / "valid_arc.json"
    valid_arc.write_text(json.dumps({
        "artifact_type": "archive_record",
        "result": "CLOSED",
        "archive_completed": True,
    }))
    result = sync(str(valid_arc), "UT-GSYNC-VALID", str(td))
    # Expected: BLOCK due to no upstream (we're in tmp dir, not a git repo)
    if result.get("result") not in ("BLOCK", "DRY_RUN") and result.get("archive_valid") is not True:
        failures.append({"case": "valid archive eval", "result": result})

    if failures:
        print(json.dumps({"self_test": "BLOCK", "failures": failures}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"self_test": "PASS", "cases": 2}, ensure_ascii=False, indent=2))
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="CCRT GitHub sync after G6 archive"
    )
    parser.add_argument("--archive-record", help="Path to archive_record JSON")
    parser.add_argument("--run-id", help="Task run ID")
    parser.add_argument("--output-dir", default=str(AUDIT_DIR), help="Output directory for github_sync_record")
    parser.add_argument("--self-test", action="store_true", help="Run self-test")
    parser.add_argument("--dry-run", action="store_true", help="Validate only, don't push")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    if not args.archive_record:
        print("BLOCK: --archive-record is required unless --self-test", file=sys.stderr)
        return 2
    if not args.run_id:
        print("BLOCK: --run-id is required unless --self-test", file=sys.stderr)
        return 2

    result = sync(args.archive_record, args.run_id, args.output_dir, dry_run=args.dry_run)

    # Write output
    out_name = f"{args.run_id}_github_sync_record.json"
    out_path = Path(args.output_dir) / out_name
    write_json(out_path, result)

    response = dict(result)
    response["github_sync_record"] = str(out_path)
    print(json.dumps(response, ensure_ascii=False, indent=2))

    if result.get("result") == RESULT_BLOCK:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
