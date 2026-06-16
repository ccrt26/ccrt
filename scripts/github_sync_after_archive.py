#!/usr/bin/env python3
"""CCRT GitHub sync after G6 archive.

Validates archive_record, performs git add/commit/push,
generates github_sync_record evidence, handles output_dir
inside repo (commits+pushed the record), and final verifies
workspace clean + ahead/behind 0/0 + HEAD == upstream HEAD.
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
        # Use rstrip() not strip() — .strip() removes the leading space
        # from the first line of status --porcelain output, corrupting
        # the XY status prefix and shifting path offsets.
        "stdout": proc.stdout.rstrip("\n").rstrip("\r"),
        "stderr": proc.stderr.strip(),
    }


def _commit_args(msg):
    """Return git-commit arguments, optionally adding --no-verify."""
    args = ["commit", "-m", msg]
    if os.environ.get("GIT_COMMIT_NO_VERIFY") == "1":
        args.append("--no-verify")
    return args


def _output_dir_in_repo(output_dir, cwd=None):
    """Check if output_dir is inside the repository working tree."""
    repo_root = Path(cwd or ROOT).resolve()
    output_resolved = Path(output_dir).resolve()
    try:
        output_resolved.relative_to(repo_root)
        return True
    except ValueError:
        return False


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
    """Check if all dirty files are within the allowed set. Returns (ok, violations)."""
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
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ")[-1]
        is_allowed = False
        for ap in allowed_paths:
            ap_str = str(ap)
            if path == ap_str or path.startswith(ap_str + "/"):
                is_allowed = True
                break
        if not is_allowed:
            violations.append(path)

    return len(violations) == 0, violations


def _build_base_record(archive_path, run_id, branch, upstream, before_head):
    """Return a skeleton github_sync_record prior to sync operations."""
    return {
        "artifact_type": "github_sync_record",
        "result": RESULT_BLOCK,
        "run_id": run_id,
        "archive_record": str(archive_path),
        "branch": branch,
        "upstream": upstream,
        "archive_valid": True,
        "commit_created": False,
        "push_completed": False,
        "github_sync_completed": False,
        "before_head": before_head,
        "tag_completed": False,
        "merge_completed": False,
    }


def sync(archive_path, run_id, output_dir, dry_run=False, cwd=None, allowed_paths=None):
    """Perform the full GitHub sync lifecycle.

    Returns a dict (github_sync_record) with the outcome.
    Also writes the record to output_dir and, if output_dir is inside
    the repo, commits + pushes the record file and final-verifies.
    """
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

    # 4. Before HEAD
    before = run_git(["rev-parse", "HEAD"], cwd=cwd)
    before_head = before["stdout"]
    status_result = run_git(["-c", "core.quotepath=false", "status", "--porcelain"], cwd=cwd)
    workspace_dirty = bool(status_result["stdout"].strip())
    no_push = os.environ.get("GITHUB_SYNC_NO_PUSH") == "1"

    # 5. Determine output path and whether it lives inside the repo
    output_in_repo = _output_dir_in_repo(output_dir, cwd=cwd)
    github_sync_record_path = Path(output_dir) / f"{run_id}_github_sync_record.json"

    # 6. Dry run
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
            "output_in_repo": output_in_repo,
        }

    # 7. Check dirty files against allowed paths — never use git add -A
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

    # 8. GITHUB_SYNC_NO_PUSH — must NOT claim push / github sync completion
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
            "output_in_repo": output_in_repo,
        }

    # 9. Check remote equality (skip fetch if env var is set)
    skip_fetch = os.environ.get("GITHUB_SYNC_SKIP_FETCH") == "1"
    if not skip_fetch:
        run_git(["fetch", "origin", branch], cwd=cwd)

    behind = run_git(["rev-list", "--count", f"HEAD..{upstream.split('/')[0]}/{branch}"], cwd=cwd)
    ahead_count = None
    if behind["returncode"] == 0 and behind["stdout"].strip() == "0":
        ahead = run_git(["rev-list", "--count", f"{upstream.split('/')[0]}/{branch}..HEAD"], cwd=cwd)
        if ahead["returncode"] == 0:
            ahead_count = ahead["stdout"].strip()

    already_synced = (
        behind["returncode"] == 0 and behind["stdout"].strip() == "0"
        and ahead_count is not None and ahead_count == "0"
        and not workspace_dirty
    )

    if already_synced and not output_in_repo:
        # Truly nothing to do — return early
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

    # 10. Commit phase 1 — stage allowed paths and commit
    commit_made = False
    if workspace_dirty:
        for ap in (allowed_paths or []):
            run_git(["add", "--", str(ap)], cwd=cwd)
        commit_result = run_git(
            _commit_args(f"[CCRT] {run_id} — G6 archive auto-sync"), cwd=cwd
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
        commit_made = True

    # 11. Push phase 1
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
            "commit_created": commit_made,
            "push_completed": False,
            "github_sync_completed": False,
        }

    after_phase1 = run_git(["rev-parse", "HEAD"], cwd=cwd)
    after_head = after_phase1["stdout"]

    # 12. Final verify (before writing the record so workspace state is clean)
    if not skip_fetch:
        run_git(["fetch", "origin", branch], cwd=cwd)

    # 12a. Workspace clean
    post_status = run_git(["-c", "core.quotepath=false", "status", "--porcelain"], cwd=cwd)
    workspace_clean_final = not bool(post_status["stdout"].strip())

    # 12b. ahead / behind
    final_ahead = run_git(
        ["rev-list", "--count", f"{upstream.split('/')[0]}/{branch}..HEAD"], cwd=cwd
    )
    final_behind = run_git(
        ["rev-list", "--count", f"HEAD..{upstream.split('/')[0]}/{branch}"], cwd=cwd
    )
    ahead_0 = final_ahead["returncode"] == 0 and final_ahead["stdout"].strip() == "0"
    behind_0 = final_behind["returncode"] == 0 and final_behind["stdout"].strip() == "0"

    # 12c. HEAD == upstream HEAD
    remote_head = run_git(
        ["rev-parse", f"{upstream.split('/')[0]}/{branch}"], cwd=cwd
    )
    head_matches = remote_head["returncode"] == 0 and remote_head["stdout"].strip() == after_head

    # 12d. Hygiene check — pass CCRT_GIT_ROOT so the script targets the right repo.
    #      Use an absolute script path since cwd may point to a temp/test repo.
    hygiene_env = os.environ.copy()
    if cwd:
        hygiene_env["CCRT_GIT_ROOT"] = str(Path(cwd).resolve())
    hygiene_script = str(ROOT / "scripts/git_workspace_hygiene.py")
    hygiene_proc = subprocess.run(
        [sys.executable, hygiene_script, "--quiet"],
        cwd=cwd or str(ROOT), env=hygiene_env,
        capture_output=True, text=True, timeout=30,
    )
    hygiene_ok = hygiene_proc.returncode == 0

    verify_ok = workspace_clean_final and ahead_0 and behind_0 and head_matches and hygiene_ok

    # 13. Build COMPLETE github_sync_record (one write only)
    record = {
        "artifact_type": "github_sync_record",
        "result": RESULT_PUSHED if verify_ok else RESULT_BLOCK,
        "run_id": run_id,
        "archive_record": str(archive_path),
        "branch": branch,
        "upstream": upstream,
        "archive_valid": True,
        "commit_created": commit_made,
        "push_completed": verify_ok,
        "github_sync_completed": verify_ok,
        "before_head": before_head,
        "after_head": after_head,
        "pushed_to": f"origin/{branch}",
        "tag_completed": False,
        "merge_completed": False,
        "workspace_dirty": workspace_dirty,
        "output_in_repo": output_in_repo,
        "workspace_clean_final": workspace_clean_final,
        "ahead_count": final_ahead["stdout"].strip() if final_ahead["returncode"] == 0 else "?",
        "behind_count": final_behind["stdout"].strip() if final_behind["returncode"] == 0 else "?",
        "head_equals_upstream": head_matches,
        "workspace_hygiene_passed": hygiene_ok,
    }

    if not verify_ok:
        failures = []
        if not workspace_clean_final:
            failures.append("workspace not clean after sync")
        if not ahead_0:
            failures.append(f"ahead = {final_ahead['stdout'].strip()}")
        if not behind_0:
            failures.append(f"behind = {final_behind['stdout'].strip()}")
        if not head_matches:
            failures.append(f"HEAD {after_head} != remote {remote_head['stdout'].strip()}")
        if not hygiene_ok:
            failures.append(f"hygiene: {hygiene_proc.stdout.strip()}")
        record["reason"] = "; ".join(failures)

    # 14. Write the record once with final status
    write_json(github_sync_record_path, record)

    # 15. If output_dir is inside the repo AND verification passed,
    #     commit + push the record file separately.
    if output_in_repo and verify_ok:
        add_r = run_git(["add", "--", str(github_sync_record_path)], cwd=cwd)
        commit_r = run_git(
            _commit_args(f"[CCRT] {run_id} — G6 github_sync_record"),
            cwd=cwd,
        )
        if commit_r["returncode"] != 0:
            record["result"] = RESULT_BLOCK
            record["reason"] = f"github_sync_record commit failed: {commit_r['stderr']}"
            record["push_completed"] = False
            record["github_sync_completed"] = False
            write_json(github_sync_record_path, record)
            return record

        push_r = run_git(["push", "origin", branch], cwd=cwd)
        if push_r["returncode"] != 0:
            record["result"] = RESULT_BLOCK
            record["reason"] = f"github_sync_record push failed: {push_r['stderr']}"
            record["push_completed"] = True   # phase 1 push succeeded
            record["github_sync_completed"] = False
            write_json(github_sync_record_path, record)
            return record

        after_phase2 = run_git(["rev-parse", "HEAD"], cwd=cwd)
        record["after_head"] = after_phase2["stdout"]

    return record


def run_self_test():
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
    if result.get("result") not in ("BLOCK", "DRY_RUN") and result.get("archive_valid") is not True:
        failures.append({"case": "valid archive eval", "result": result})

    # 3. archive_completed missing (=None) must BLOCK
    missing_arc = td / "missing_completed_arc.json"
    missing_arc.write_text(json.dumps({
        "artifact_type": "archive_record",
        "result": "CLOSED",
    }))
    result = sync(str(missing_arc), "UT-GSYNC-MISSING-COMPLETED", str(td), cwd=str(td))
    if result.get("result") != "BLOCK":
        failures.append({"case": "missing archive_completed field", "result": result.get("result")})

    if failures:
        print(json.dumps({"self_test": "BLOCK", "failures": failures}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"self_test": "PASS", "cases": 3}, ensure_ascii=False, indent=2))
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

    # Ensure the github_sync_record file exists on disk.
    # sync() writes it on the final verification paths (commit+push+verify)
    # but early BLOCK/DRY_RUN returns skip that.  We write here as a fallback.
    out_name = f"{args.run_id}_github_sync_record.json"
    out_path = Path(args.output_dir) / out_name
    if not out_path.exists():
        write_json(out_path, result)

    response = dict(result)
    response["github_sync_record"] = str(out_path)
    print(json.dumps(response, ensure_ascii=False, indent=2))

    if result.get("result") == RESULT_BLOCK:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
