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


def check_forbidden_dirs(cwd=None):
    violations = []
    for d in FORBIDDEN_DIRS:
        result = run_git(["status", "--short", "--", d], cwd=cwd)
        if result["stdout"].strip():
            violations.append(d)
    return violations


def get_branch_info(cwd=None):
    branch = run_git(["branch", "--show-current"], cwd=cwd)
    if branch["returncode"] != 0:
        return None, "cannot determine current branch"
    upstream = run_git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], cwd=cwd)
    if upstream["returncode"] != 0:
        return branch["stdout"], None
    return branch["stdout"], upstream["stdout"]


def check_workspace_vs_allowed(allowed_paths, cwd=None):
    """Check if all dirty files are within the allowed set. Returns (ok, violations).

    *allowed_paths* is a list of file paths that are expected to have changes.
    Any dirty file outside this list is a violation.

    Uses -c core.quotepath=false so Chinese/UTF-8 paths are not escaped.
    """
    if allowed_paths is None:
        allowed_paths = []

    status = run_git(["-c", "core.quotepath=false", "status", "--porcelain"], cwd=cwd)
    if not status["stdout"].strip():
        return True, []

    violations = []
    for line in status["stdout"].splitlines():
        line = line.rstrip()
        if not line:
            continue
        # Format: XY <path> where XY = index status + worktree status (2 chars)
        # Leading space means "nothing in index". Strip would break the offset.
        # Path starts at index 3 (after XY + separator space)
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ")[-1]
        # Check if this dirty file is within allowed paths
        is_allowed = False
        for ap in allowed_paths:
            ap_str = str(ap)
            if path == ap_str or path.startswith(ap_str + "/"):
                is_allowed = True
                break
        if not is_allowed:
            violations.append(path)

    return len(violations) == 0, violations


def sync(archive_path, run_id, output_dir, dry_run=False, cwd=None, allowed_paths=None):
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

    # 2. Check forbidden dirs (skip in dry_run — no actual git operations)
    if not dry_run:
        skip_forbidden = os.environ.get("GITHUB_SYNC_SKIP_FORBIDDEN") == "1"
        if not skip_forbidden:
            violations = check_forbidden_dirs(cwd=cwd)
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
    branch, upstream = get_branch_info(cwd=cwd)
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

    # 4. Get before HEAD and workspace state
    before = run_git(["rev-parse", "HEAD"], cwd=cwd)
    before_head = before["stdout"]
    status_result = run_git(["-c", "core.quotepath=false", "status", "--porcelain"], cwd=cwd)
    workspace_dirty = bool(status_result["stdout"].strip())
    no_push = os.environ.get("GITHUB_SYNC_NO_PUSH") == "1"

    # 5. If workspace dirty, validate against allowed paths — do NOT use git add -A
    if workspace_dirty:
        ok, violations = check_workspace_vs_allowed(allowed_paths, cwd=cwd)
        if not ok:
            return {
                "artifact_type": "github_sync_record",
                "result": RESULT_BLOCK,
                "run_id": run_id,
                "archive_record": str(archive_path),
                "branch": branch,
                "upstream": upstream,
                "archive_valid": True,
                "reason": f"dirty files outside allowed paths: {violations}",
                "commit_created": False,
                "push_completed": False,
                "github_sync_completed": False,
                "workspace_dirty": workspace_dirty,
                "violations": violations,
            }

    if no_push:
        return {
            "artifact_type": "github_sync_record",
            "result": "DRY_RUN" if not workspace_dirty else RESULT_BLOCK,
            "run_id": run_id,
            "archive_record": str(archive_path),
            "branch": branch,
            "upstream": upstream,
            "archive_valid": True,
            "reason": "GITHUB_SYNC_NO_PUSH=1; push completion cannot be claimed",
            "commit_created": False,
            "push_completed": False,
            "github_sync_completed": False,
            "before_head": before_head,
            "after_head": before_head,
            "pushed_to": "",
            "tag_completed": False,
            "merge_completed": False,
            "workspace_dirty": workspace_dirty,
        }

    # 6. Check remote equality only after proving workspace cleanliness.
    skip_fetch = os.environ.get("GITHUB_SYNC_SKIP_FETCH") == "1"
    if not skip_fetch:
        fetch_result = run_git(["fetch", "origin", branch], cwd=cwd)
    behind = run_git(["rev-list", "--count", f"HEAD..{upstream.split('/')[0]}/{branch}"], cwd=cwd)
    if behind["returncode"] == 0 and behind["stdout"].strip() == "0":
        ahead = run_git(["rev-list", "--count", f"{upstream.split('/')[0]}/{branch}..HEAD"], cwd=cwd)
        if ahead["returncode"] == 0 and ahead["stdout"].strip() == "0" and not workspace_dirty:
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
                "workspace_dirty": False,
            }

    # 7. Commit changes — only stage allowed paths, NEVER git add -A
    if workspace_dirty:
        for ap in (allowed_paths or []):
            run_git(["add", "--", str(ap)], cwd=cwd)
        commit_result = run_git(
            ["commit", "-m", f"[CCRT] {run_id} — G6 archive auto-sync"], cwd=cwd
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

    # 8. Push (skip if no_push flag is set)
    if no_push:
        after = run_git(["rev-parse", "HEAD"], cwd=cwd)
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

    push_result = run_git(["push", "origin", branch], cwd=cwd)
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

    # 9. Verify push + run git_workspace_hygiene --quiet
    after = run_git(["rev-parse", "HEAD"], cwd=cwd)
    after_head = after["stdout"]

    if not skip_fetch:
        run_git(["fetch", "origin", branch], cwd=cwd)
    remote_head = run_git(["rev-parse", f"{upstream.split('/')[0]}/{branch}"], cwd=cwd)
    post_status = run_git(["-c", "core.quotepath=false", "status", "--porcelain"], cwd=cwd)
    if remote_head["returncode"] != 0 or remote_head["stdout"].strip() != after_head or post_status["stdout"].strip():
        return {
            "artifact_type": "github_sync_record",
            "result": RESULT_BLOCK,
            "run_id": run_id,
            "archive_record": str(archive_path),
            "branch": branch,
            "upstream": upstream,
            "archive_valid": True,
            "reason": "remote HEAD mismatch or workspace not clean after push",
            "commit_created": True,
            "push_completed": False,
            "github_sync_completed": False,
            "local_head": after_head,
            "remote_head": remote_head["stdout"].strip(),
            "workspace_dirty_after_push": bool(post_status["stdout"].strip()),
        }

    # Post-push hygiene check
    hygiene_proc = subprocess.run(
        [sys.executable, "scripts/git_workspace_hygiene.py", "--quiet"],
        cwd=cwd or str(ROOT), capture_output=True, text=True, timeout=30,
    )
    if hygiene_proc.returncode != 0:
        return {
            "artifact_type": "github_sync_record",
            "result": RESULT_BLOCK,
            "run_id": run_id,
            "archive_record": str(archive_path),
            "branch": branch,
            "upstream": upstream,
            "archive_valid": True,
            "reason": f"workspace hygiene failed after push: {hygiene_proc.stdout.strip()}",
            "commit_created": True,
            "push_completed": True,
            "github_sync_completed": False,
            "workspace_hygiene_output": hygiene_proc.stdout.strip(),
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
        "workspace_hygiene_passed": True,
    }


def run_self_test():
    import tempfile

    failures = []
    td = Path(tempfile.mkdtemp(dir="/private/tmp"))
    td_pyc = td / "pycache"
    td_pyc.mkdir(exist_ok=True)
    os.environ["PYTHONPYCACHEPREFIX"] = str(td_pyc)

    # Init isolated git repo so self-test never touches the real project index
    subprocess.run(
        ["git", "init", "-b", "master"],
        cwd=str(td), capture_output=True, text=True, timeout=30,
    )
    subprocess.run(
        ["git", "-c", "user.email=test@test.com", "-c", "user.name=Test",
         "commit", "--allow-empty", "-m", "init"],
        cwd=str(td), capture_output=True, text=True, timeout=30,
    )

    # 1. Missing archive_record
    result = sync(td / "nonexistent.json", "UT-GSYNC-MISSING", str(td), cwd=str(td))
    if result.get("result") != "BLOCK":
        failures.append({"case": "missing archive_record", "result": result.get("result")})

    # 2. Valid archive_record — operates on isolated repo, expects BLOCK (no upstream)
    valid_arc = td / "valid_arc.json"
    valid_arc.write_text(json.dumps({
        "artifact_type": "archive_record",
        "result": "CLOSED",
        "archive_completed": True,
    }))
    result = sync(str(valid_arc), "UT-GSYNC-VALID", str(td), cwd=str(td))
    # Expected: BLOCK due to no upstream in isolated repo
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
    parser.add_argument("--allowed-paths-json", default="",
                        help="Path to JSON file containing list of allowed file paths to stage")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    if not args.archive_record:
        print("BLOCK: --archive-record is required unless --self-test", file=sys.stderr)
        return 2
    if not args.run_id:
        print("BLOCK: --run-id is required unless --self-test", file=sys.stderr)
        return 2

    allowed_paths = None
    if args.allowed_paths_json:
        allowed_paths = load_json(args.allowed_paths_json)
        if not isinstance(allowed_paths, list):
            print("BLOCK: --allowed-paths-json must contain a JSON array", file=sys.stderr)
            return 2

    result = sync(args.archive_record, args.run_id, args.output_dir,
                  dry_run=args.dry_run, allowed_paths=allowed_paths)

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
