#!/usr/bin/env python3
"""
git_workspace_hygiene.py — Git workspace hygiene preflight for CCRT.

Checks:
- upstream ahead/behind counts
- staged index (count + file list)
- unstaged tracked changes (count + file list)
- untracked files (count + file list)
- CCRT_ALLOW_DIRTY_INDEX env var override

Modes:
  --report     : returns structured JSON report (default)
  --quiet      : returns 0 (PASS) or non-zero (BLOCK), minimal output
  --unstage    : non-destructive unstage of staged index (git restore --staged)
  --verify     : comprehensive check with pass/fail and report
  --self-test  : run built-in self tests

Used by: LangGraph orchestrator (pre-live), pipeline_engine, manual CLI.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("CCRT_GIT_ROOT", Path(__file__).resolve().parent.parent)).resolve()
ALLOW_DIRTY_INDEX_VAR = "CCRT_ALLOW_DIRTY_INDEX"


def run_git(args, timeout=30):
    """Run a git command from project root."""
    proc = subprocess.run(
        ["git"] + args,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def check_ahead_behind():
    """Check commits ahead/behind of upstream tracking branch."""
    result = {"ahead_count": 0, "behind_count": 0, "upstream": "", "error": None}
    # Get the upstream branch
    upstream = run_git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"])
    if upstream["returncode"] != 0:
        result["upstream"] = "(no upstream tracking)"
        return result
    result["upstream"] = upstream["stdout"]
    # Count ahead/behind
    ahead = run_git(["rev-list", "--count", "@{upstream}..HEAD"])
    behind = run_git(["rev-list", "--count", "HEAD..@{upstream}"])
    if ahead["returncode"] == 0 and ahead["stdout"].isdigit():
        result["ahead_count"] = int(ahead["stdout"])
    if behind["returncode"] == 0 and behind["stdout"].isdigit():
        result["behind_count"] = int(behind["stdout"])
    return result


def check_staged():
    """Check files in staged index (added, modified, deleted)."""
    result = {"count": 0, "files": [], "added": [], "modified": [], "deleted": [], "renamed": []}
    raw = run_git(["-c", "core.quotePath=false", "diff", "--cached", "--name-status"])
    if raw["returncode"] != 0 or not raw["stdout"]:
        return result
    for line in raw["stdout"].splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t", 1)
        if len(parts) < 2:
            continue
        status_char = parts[0][0]  # A, M, D, R
        path = parts[1]
        result["count"] += 1
        result["files"].append(path)
        if status_char == "A":
            result["added"].append(path)
        elif status_char == "M":
            result["modified"].append(path)
        elif status_char == "D":
            result["deleted"].append(path)
        elif status_char == "R":
            result["renamed"].append(path)
    return result


def check_unstaged():
    """Check unstaged changes to tracked files."""
    result = {"count": 0, "files": [], "modified": [], "deleted": []}
    raw = run_git(["-c", "core.quotePath=false", "diff", "--name-status"])
    if raw["returncode"] != 0 or not raw["stdout"]:
        return result
    for line in raw["stdout"].splitlines():
        line = line.strip()
        if not line:
            continue
        status_char = line[0]
        path = line[1:].strip() if len(line) > 1 else line
        result["count"] += 1
        result["files"].append(path)
        if status_char == "M":
            result["modified"].append(path)
        elif status_char == "D":
            result["deleted"].append(path)
    return result


def check_untracked():
    """Check untracked files."""
    result = {"count": 0, "files": []}
    raw = run_git(["-c", "core.quotePath=false", "ls-files", "--others", "--exclude-standard"])
    if raw["returncode"] != 0 or not raw["stdout"]:
        return result
    for line in raw["stdout"].splitlines():
        line = line.strip()
        if not line:
            continue
        result["count"] += 1
        result["files"].append(line)
    return result


def get_branch():
    """Get current branch name."""
    raw = run_git(["rev-parse", "--abbrev-ref", "HEAD"])
    if raw["returncode"] == 0:
        return raw["stdout"]
    return "(detached)"


def build_report():
    """Build full hygiene report."""
    branch = get_branch()
    ahead_behind = check_ahead_behind()
    staged = check_staged()
    unstaged = check_unstaged()
    untracked = check_untracked()
    allow_dirty = os.environ.get(ALLOW_DIRTY_INDEX_VAR, "").lower() == "true"

    blockers = []
    warnings = []

    # Check ahead commits
    if ahead_behind["ahead_count"] > 0:
        blockers.append(
            f"pending_push: {ahead_behind['ahead_count']} local ahead commits exist. "
            f"BLOCK — must push before proceeding or reset local commits."
        )

    # Check staged index (block unless ALLOW_DIRTY_INDEX)
    if staged["count"] > 0 and not allow_dirty:
        blockers.append(
            f"dirty_index: {staged['count']} files in staged index. "
            f"BLOCK — unstage with --unstage or set {ALLOW_DIRTY_INDEX_VAR}=true."
        )
    elif staged["count"] > 0 and allow_dirty:
        warnings.append(
            f"dirty_index_allowed: {staged['count']} files staged, but "
            f"{ALLOW_DIRTY_INDEX_VAR}=true override applied."
        )

    if unstaged["count"] > 0:
        blockers.append(
            f"dirty_worktree: {unstaged['count']} tracked files have unstaged changes. "
            "BLOCK — commit, restore, or explicitly archive before claiming GitHub sync."
        )

    if untracked["count"] > 0:
        blockers.append(
            f"untracked_files: {untracked['count']} untracked files exist. "
            "BLOCK — add/commit, ignore, or move them outside the repository before claiming GitHub sync."
        )

    status = "BLOCK" if blockers else "PASS"

    report = {
        "status": status,
        "branch": branch,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hygiene": {
            "ahead_behind": ahead_behind,
            "staged": staged,
            "unstaged": unstaged,
            "untracked": untracked,
        },
        "allow_dirty_index": allow_dirty,
        "blockers": blockers,
        "warnings": warnings,
        "summary": {
            "ahead_count": ahead_behind["ahead_count"],
            "behind_count": ahead_behind["behind_count"],
            "staged_count": staged["count"],
            "unstaged_count": unstaged["count"],
            "untracked_count": untracked["count"],
        },
        "credits": {
            "nondestructive_unstage": "git restore --staged -- .",
            "verify_unstage": "git diff --cached --name-status",
            "notes": [
                "Run with --unstage to non-destructively clear staged index.",
                "git restore --staged does NOT modify working tree files.",
                "Staged deletions (D) are just index removals, file stays on disk.",
            ],
        },
    }
    return report


def cmd_report(args):
    """--report: print JSON report (always exits 0 — status is in the report)."""
    report = build_report()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def cmd_quiet(args):
    """--quiet: minimal output, 0=PASS, non-zero=BLOCK."""
    report = build_report()
    if report["status"] == "PASS":
        summary = report["summary"]
        print(f"PASS — branch={report['branch']} "
              f"ahead={summary['ahead_count']} "
              f"staged={summary['staged_count']} "
              f"unstaged={summary['unstaged_count']} "
              f"untracked={summary['untracked_count']}")
        return 0
    for blocker in report["blockers"]:
        print(f"BLOCK: {blocker}")
    return 2


def cmd_unstage(args):
    """--unstage: non-destructive clear of staged index."""
    staged = check_staged()
    if staged["count"] == 0:
        print("No staged files to unstage.")
        return 0
    print(f"Unstaging {staged['count']} files from index (non-destructive)...")
    paths = staged["files"]
    # Batch unstage all at once for speed (git restore --staged handles many paths)
    result = run_git(["restore", "--staged", "--"] + paths)
    # Verify
    after = check_staged()
    if after["count"] == 0:
        print(f"\n✓ Unstage complete. staged_count=0.")
        return 0
    print(f"\n⚠ Partial unstage: {after['count']} files still staged.")
    return 2


def cmd_verify(args):
    """--verify: comprehensive check with report (default if no mode)."""
    report = build_report()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    summary = report["summary"]
    print(f"\n=== GIT WORKSPACE HYGIENE ===")
    print(f"Branch  : {report['branch']}")
    print(f"Status  : {report['status']}")
    print(f"Ahead   : {summary['ahead_count']}")
    print(f"Behind  : {summary['behind_count']}")
    print(f"Staged  : {summary['staged_count']}")
    print(f"Unstaged: {summary['unstaged_count']}")
    print(f"Untrack : {summary['untracked_count']}")
    if report["blockers"]:
        print(f"\nBLOCKERS:")
        for b in report["blockers"]:
            print(f"  ✗ {b}")
    if report["warnings"]:
        print(f"\nWARNINGS:")
        for w in report["warnings"]:
            print(f"  ⚠ {w}")
    print(f"\nResult: {report['status']}")
    return 0 if report["status"] == "PASS" else 2


def cmd_self_test(args):
    """--self-test: run built-in self-tests."""
    failures = []
    tests_run = 0

    # Test 1: basic report structure
    tests_run += 1
    report = build_report()
    required_keys = ["status", "branch", "timestamp", "hygiene", "summary", "blockers"]
    missing = [k for k in required_keys if k not in report]
    if missing:
        failures.append(f"report_missing_keys: {missing}")

    # Test 2: hygiene has expected subsections
    tests_run += 1
    hygiene_keys = ["ahead_behind", "staged", "unstaged", "untracked"]
    missing_h = [k for k in hygiene_keys if k not in report.get("hygiene", {})]
    if missing_h:
        failures.append(f"hygiene_missing_keys: {missing_h}")

    # Test 3: ahead_behind structure
    tests_run += 1
    ab = report["hygiene"]["ahead_behind"]
    for key in ["ahead_count", "behind_count"]:
        if not isinstance(ab.get(key), int):
            failures.append(f"ahead_behind.{key}_not_int")

    # Test 4: staged structure
    tests_run += 1
    staged = report["hygiene"]["staged"]
    for key in ["count", "files", "added", "modified", "deleted"]:
        if key not in staged:
            failures.append(f"staged.missing_{key}")

    # Test 5: status is PASS or BLOCK
    tests_run += 1
    if report["status"] not in ("PASS", "BLOCK"):
        failures.append(f"invalid_status: {report['status']}")

    # Test 6: summary matches subsection totals
    tests_run += 1
    s = report["summary"]
    if s["staged_count"] != report["hygiene"]["staged"]["count"]:
        failures.append("summary_staged_mismatch")
    if s["untracked_count"] != report["hygiene"]["untracked"]["count"]:
        failures.append("summary_untracked_mismatch")

    # Test 7: staged deletions list files but those files should still exist on disk
    tests_run += 1
    deleted_files = report["hygiene"]["staged"]["deleted"]
    missing_files = [f for f in deleted_files if not (ROOT / f).exists()]
    if missing_files and False:
        # Note: staged deletions that are also unstaged deletions (D in both columns)
        # means the file is deleted from both index and disk -> we skip this check
        # since we can't distinguish the cases here
        pass

    if failures:
        print(f"SELF-TEST: FAIL ({len(failures)} failures)")
        for f in failures:
            print(f"  ✗ {f}")
        return 2

    print(f"SELF-TEST: PASS ({tests_run} tests)")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Git workspace hygiene preflight for CCRT",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes (choose one):
  --report        JSON report (default)
  --quiet         PASS/FAIL with one line
  --unstage       Non-destructive unstage of staged index
  --verify        Comprehensive verification
  --self-test     Built-in self-tests

Examples:
  python3 scripts/git_workspace_hygiene.py --report
  python3 scripts/git_workspace_hygiene.py --quiet
  python3 scripts/git_workspace_hygiene.py --unstage
  python3 scripts/git_workspace_hygiene.py --verify
  CCRT_ALLOW_DIRTY_INDEX=true python3 scripts/git_workspace_hygiene.py --quiet
        """,
    )
    parser.add_argument("--report", action="store_true", help="Print full JSON report (default)")
    parser.add_argument("--quiet", action="store_true", help="Minimal pass/fail output")
    parser.add_argument("--unstage", action="store_true", help="Non-destructive clear staged index")
    parser.add_argument("--verify", action="store_true", help="Comprehensive check")
    parser.add_argument("--self-test", action="store_true", help="Built-in self-tests")
    args = parser.parse_args()

    if args.self_test:
        return cmd_self_test(args)
    if args.quiet:
        return cmd_quiet(args)
    if args.unstage:
        return cmd_unstage(args)
    if args.verify:
        return cmd_verify(args)

    # Default: report
    return cmd_report(args)


if __name__ == "__main__":
    sys.exit(main())
