#!/usr/bin/env python3
"""
build_daily_report_release_worktree.py — 创建干净 release worktree（G5/G6 发布载体）

功能：
1. 读取当前工作区 git status，仅提取 RELEASE_ALLOWED 文件的变化。
2. 创建独立 git worktree，只复制允许文件。
3. 在 worktree 内运行 scope gate 确认干净。
4. 生成 evidence manifest。

不修改当前脏工作区，不删除任何文件。

用法：
  python3 scripts/build_daily_report_release_worktree.py
  python3 scripts/build_daily_report_release_worktree.py --dry-run
  python3 scripts/build_daily_report_release_worktree.py --branch my-branch
  python3 scripts/build_daily_report_release_worktree.py --json
"""
import argparse
import json
import shutil
import subprocess as _subprocess
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from fnmatch import fnmatch

ROOT = Path(__file__).resolve().parents[1]
TZ_SHANGHAI = timezone(timedelta(hours=8))

# 必须与 check_daily_report_release_scope.py 的 RELEASE_ALLOWED_PATTERNS 完全一致
RELEASE_ALLOWED_FILES = [
    "scripts/run_daily_report_html_only.py",
    "scripts/run_daily_data_retry_once.py",
    "scripts/run_daily_production_pipeline.py",
    "scripts/check_daily_d07_v12_contract.py",
    "scripts/check_daily_release_gate.py",
    "scripts/check_runtime_dependency_readiness.py",
    "scripts/daily_d07_contract_builder.py",
    "scripts/verify_daily_production_closure.py",
    "scripts/check_daily_report_release_scope.py",
    "scripts/build_daily_report_release_worktree.py",
    "tests/test_daily_report_artifact_isolation.py",
    "tests/test_daily_report_promote_safety.py",
    "tests/test_daily_report_d07_gate.py",
    "tests/test_daily_retry_no_d07_bypass.py",
    "tests/test_daily_production_dry_run.py",
    "tests/test_daily_report_release_scope.py",
    "tests/test_daily_report_release_worktree_builder.py",
]


def log(msg, level="INFO"):
    print(f"[{level}] {msg}", file=sys.stderr)


def now_str():
    return datetime.now(TZ_SHANGHAI).strftime("%Y%m%d-%H%M%S")


def parse_status_paths(status_text):
    """Parse git status --porcelain=v1 output and return list of changed file paths.

    Example input:
      " M scripts/run_daily_report_html_only.py\\n?? tests/test_new.py\\n M docs/keystock-dashboard/app.js"

    Returns list of file paths (status prefix removed).

    Note: status_text must preserve porcelain formatting where each line starts
    with exactly 2 status characters followed by a space, e.g. " M filename".
    Do NOT strip leading whitespace from the status text — that shifts offsets.
    """
    paths = []
    for raw_line in status_text.split("\n"):
        stripped = raw_line.strip()
        if not stripped:
            continue
        # porcelain=v1 format: XY FILENAME where X=index, Y=worktree status
        # XY always occupies positions [0:2], position [2] is space separator.
        # Filename starts at [3:].
        if len(raw_line) < 4:
            continue
        path = raw_line[3:].strip()
        if path:
            paths.append(path)
    return paths


def changed_release_files(root=None):
    """Get list of RELEASE_ALLOWED files that have actual changes in the working tree.

    Executes git status and filters to only RELEASE_ALLOWED_FILES.
    Returns list of changed file paths.
    """
    if root is None:
        root = ROOT
    result = _subprocess.run(
        ["git", "-c", "core.quotePath=false",
         "status", "--porcelain=v1", "--untracked-files=all"],
        capture_output=True, text=True, timeout=30, cwd=str(root),
    )
    if result.returncode != 0:
        raise SystemExit(f"git status failed: {result.stderr}")

    changed = []
    for path in parse_status_paths(result.stdout):
        # Only include files that match RELEASE_ALLOWED_FILES exactly
        if path in RELEASE_ALLOWED_FILES:
            changed.append(path)
    return sorted(changed)


def create_release_worktree(branch=None, worktree_dir=None):
    """Create a git worktree for the release.

    Returns (branch_name, worktree_dir).
    """
    timestamp = now_str()

    if branch is None:
        branch = f"codex/daily-report-auto-fix-{timestamp}"
    if worktree_dir is None:
        worktree_dir = Path(tempfile.gettempdir()) / f"daily-report-release-{timestamp}"

    worktree_path = Path(worktree_dir)
    if worktree_path.exists():
        raise SystemExit(f"Worktree directory already exists: {worktree_dir}")

    log(f"Creating worktree: branch={branch}, dir={worktree_dir}")
    result = _subprocess.run(
        ["git", "worktree", "add", "-b", branch, str(worktree_path), "HEAD"],
        capture_output=True, text=True, timeout=30, cwd=str(ROOT),
    )
    if result.returncode != 0:
        raise SystemExit(f"git worktree add failed: {result.stderr}")

    log(f"Worktree created at {worktree_dir}")
    return branch, worktree_dir


def copy_release_files(files, worktree_dir):
    """Copy release-allowed files from ROOT to worktree_dir.

    Only copies files that exist in the source. Raises SystemExit if any
    source file is in the delete (D) state, which is unsupported.
    """
    wt_path = Path(worktree_dir)
    copied = []

    for filepath in files:
        src = ROOT / filepath
        dst = wt_path / filepath

        # If source doesn't exist, this is a delete — unsupported
        if not src.exists():
            raise SystemExit(
                f"DELETE_NOT_ALLOWED: {filepath} does not exist in source. "
                f"Deletion of release-allowed files is not supported."
            )

        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dst))
        copied.append(filepath)
        log(f"  Copied: {filepath}")

    return copied


def run_scope_gate(worktree_dir, allow_generated_evidence=False):
    """Run check_daily_report_release_scope.py in the worktree dir.

    If allow_generated_evidence is True, passes --allow-generated-evidence
    so that release evidence files (运行产物/daily_report_release/evidence/**)
    do not BLOCK the gate.
    Returns the parsed JSON result.
    """
    python = sys.executable
    scope_gate = Path(worktree_dir) / "scripts" / "check_daily_report_release_scope.py"
    if not scope_gate.exists():
        raise SystemExit(f"Scope gate not found in worktree: {scope_gate}")

    cmd = [python, str(scope_gate), "--json"]
    if allow_generated_evidence:
        cmd.append("--allow-generated-evidence")

    result = _subprocess.run(
        cmd,
        capture_output=True, text=True, timeout=30, cwd=worktree_dir,
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise SystemExit(f"Scope gate output parse failed: {result.stdout}")

    if payload.get("overall") != "PASS":
        raise SystemExit(
            f"Scope gate BLOCK in worktree: {payload.get('reason', 'unknown')}"
        )

    log(f"Scope gate PASS in worktree")
    return payload


def write_manifest(branch, worktree_dir, copied_files, scope_result):
    """Write release worktree evidence manifest."""
    manifest = {
        "release_type": "daily_report_auto_fix",
        "branch": branch,
        "worktree_dir": str(worktree_dir),
        "source_root": str(ROOT),
        "copied_files": sorted(copied_files),
        "scope_result": scope_result,
        "created_at": datetime.now(TZ_SHANGHAI).isoformat(),
    }
    evidence_dir = Path(worktree_dir) / "运行产物" / "daily_report_release" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = evidence_dir / "release_worktree_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log(f"Manifest written: {manifest_path}")
    return str(manifest_path)


def main():
    ap = argparse.ArgumentParser(description="日报自动化修复 — 干净 release worktree 构建")
    ap.add_argument("--branch", default=None, help="worktree 分支名（自动生成）")
    ap.add_argument("--worktree-dir", default=None, help="worktree 目录（自动生成到 /private/tmp）")
    ap.add_argument("--dry-run", action="store_true", help="仅输出允许文件，不创建 worktree")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    # Step 1: Get changed release-allowed files
    files = changed_release_files()
    if not files:
        msg = "NO_RELEASE_ALLOWED_CHANGES: no release-allowed files have changes"
        if args.json:
            print(json.dumps({"overall": "SKIP", "reason": msg}, ensure_ascii=False, indent=2))
        else:
            print(msg)
        return 0

    if args.dry_run:
        output = {
            "overall": "DRY_RUN",
            "dry_run": True,
            "changed_release_files": files,
            "total": len(files),
        }
        if args.json:
            print(json.dumps(output, ensure_ascii=False, indent=2))
        else:
            print(f"DRY_RUN: {len(files)} file(s) would be copied")
            for f in files:
                print(f"  {f}")
        return 0

    # Step 2: Create worktree
    branch, worktree_dir = create_release_worktree(
        branch=args.branch, worktree_dir=args.worktree_dir
    )

    # Step 3: Copy files
    try:
        copied = copy_release_files(files, worktree_dir)
    except SystemExit as e:
        if args.json:
            print(json.dumps({"overall": "BLOCK", "reason": str(e)}, ensure_ascii=False, indent=2))
        else:
            log(str(e), "BLOCK")
        return 2

    # Step 4: Run scope gate in worktree
    try:
        scope_result = run_scope_gate(worktree_dir)
    except SystemExit as e:
        if args.json:
            print(json.dumps({
                "overall": "BLOCK",
                "stage": "pre_manifest_scope_gate",
                "reason": str(e),
            }, ensure_ascii=False, indent=2))
        else:
            log(str(e), "BLOCK")
        return 2

    # Step 5: Write manifest
    manifest_path = write_manifest(branch, worktree_dir, copied, scope_result)

    # Step 6: Re-run scope gate after manifest; release evidence is allowed
    # only here after the manifest has been written.
    try:
        post_manifest_scope = run_scope_gate(worktree_dir, allow_generated_evidence=True)
    except SystemExit as e:
        if args.json:
            print(json.dumps({
                "overall": "BLOCK",
                "stage": "post_manifest_scope_gate",
                "reason": str(e),
                "manifest_path": str(manifest_path),
            }, ensure_ascii=False, indent=2))
        else:
            log(str(e), "BLOCK")
        return 2

    output = {
        "overall": "PASS",
        "branch": branch,
        "worktree_dir": str(worktree_dir),
        "copied_files": sorted(copied),
        "pre_manifest_scope_gate_result": scope_result.get("overall", "UNKNOWN"),
        "post_manifest_scope_gate_result": post_manifest_scope.get("overall", "UNKNOWN"),
        "manifest_path": str(manifest_path),
        "source_root": str(ROOT),
    }

    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(f"\n=== Release Worktree Created ===")
        print(f"  Branch: {branch}")
        print(f"  Dir: {worktree_dir}")
        print(f"  Files: {len(copied)}")
        print(f"  Manifest: {manifest_path}")
        print(f"  Status: PASS" if scope_result["overall"] == "PASS" else f"  Status: {scope_result['overall']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
