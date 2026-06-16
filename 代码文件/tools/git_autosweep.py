#!/usr/bin/env python3
"""git_autosweep.py — 每小时自动Git巡检脚本

扫描未提交变更，分类为 auto（数据/报告/配置）和 pipeline（代码文件）。
默认 report-only 模式：只分析和输出报告，不执行任何 git 操作。
须显式 --commit 才提交，须显式 --push 才推送。

用法:
  python3 代码文件/tools/git_autosweep.py              # report-only
  python3 代码文件/tools/git_autosweep.py --commit      # 提交
  python3 代码文件/tools/git_autosweep.py --commit --push  # 提交+推送

退出码:
  0 — clean workspace, 或成功提交/推送
  2 — 有 pipeline 文件但无 token、commit 失败、push 失败、或 workspace 仍 dirty

输出字段:
  success, mode, commits, push_success
  blocked_reason     — 如果失败，阻塞原因
  workspace_dirty_before — 操作前是否有未提交变更
  workspace_dirty_after  — 操作后是否仍有未提交变更
  exit_policy        — "no_changes" / "report_only" / "commit_only" / "commit_push"
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
_TEST_REPO = None  # Override for isolated-repo unit tests; set before calling run_git
TEST_LOCK_DIR = None  # Optional override for lock dir; if set, LOCK_FILE lives here
TEST_LOG_DIR = None    # Optional override for log dir; if set, LOG_FILE lives here
LOCK_FILE = ROOT / ".claude" / "sweep.lock"
LOG_FILE = ROOT / "临时报告" / "git_autocommit.log"
PIPELINE_TOKEN = ROOT / ".claude" / "pipeline_active.json"

FORBIDDEN_PATTERNS = [
    r'\.env$', r'\.env\.', r'credentials\.(json|txt|yml|yaml|env|conf)$',
    r'secret\.(json|txt|yml|yaml)$', r'password', r'(?:^|[/\\])token\.(json|txt|yml|yaml|env)$',
    r'\.pem$', r'\.key$', r'\.pfx$', r'\.p12$', r'private_key', r'privatekey',
    r'id_rsa', r'id_ed25519', r'id_ecdsa', r'\.htpasswd$', r'oauth',
    r'service_account\.json$', r'settings\.local\.json$',
]

AUTO_COMMIT_PATHS = [
    r'^\.claude/im_queue/', r'^\.claude/knowledge/', r'^\.claude/pipeline_history/',
    r'^\.claude/regen/', r'^\.claude/sweep\.lock$',
    r'^临时报告/', r'^历史数据/', r'^审计报告/',
    r'^重点股票/股票报告/', r'^重点股票/深度分析/',
    r'^重点股票/次日评估/', r'^重点股票/预判记录/', r'^重点股票/消息面数据/',
    r'^每日荐股/股票报告/', r'^每日荐股/评估报告/',
    r'^模拟交易/持仓记录/', r'^模拟交易/每日快照/', r'^模拟交易/绩效报告/',
    r'^项目成员/', r'^CLAUDE\.md$',
]

AUTO_COMMIT_BLOCKED = [
    r'^\.claude/settings\.json$', r'^\.claude/settings\.local\.json$',
    r'^\.claude/scheduled_tasks\.json$', r'^\.claude/pipeline_active\.json$',
    r'^\.claude/hooks/', r'^\.claude/commands/.*\.(json|local|secret|token|key)$',
    r'^\.claude/agents/.*\.(json|local|secret|token|key)$',
]

PIPELINE_DIRS = [
    r'^代码文件/', r'^模拟交易/交易引擎/', r'^模拟交易/否决审查/',
    r'^模拟交易/分析/', r'^模拟交易/共享模块/', r'^模拟交易/展示/', r'^模拟交易/工具/',
]

# Directories where ALL files are treated as engineering code (token-gated).
# Protected files are tracked separately from pipeline files in output fields.
PROTECTED_DIRS = [
    r'^scripts/', r'^tests/', r'^\.github/',
]

# Extensions that make a file in PIPELINE_DIRS count as pipeline content.
# PROTECTED_DIRS files are always protected regardless of extension.
PIPELINE_EXTENSIONS = {'.py', '.json', '.yaml', '.yml', '.toml', '.ps1', '.psm1', '.bat'}


def _effective_root():
    """Return the effective repo root, using _TEST_REPO when set for isolation."""
    return _TEST_REPO or ROOT


def _effective_lock_file():
    """Return the effective lock file path, overridden in test mode."""
    if _TEST_REPO is not None:
        return _TEST_REPO / ".claude" / "sweep.lock"
    return LOCK_FILE


def _effective_log_file():
    """Return the effective log file path, overridden in test mode."""
    if _TEST_REPO is not None:
        log_dir = _TEST_REPO / "临时报告"
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir / "git_autocommit.log"
    return LOG_FILE


def _effective_token_path():
    """Return the effective pipeline token path, overridden in test mode."""
    if _TEST_REPO is not None:
        return _TEST_REPO / ".claude" / "pipeline_active.json"
    return PIPELINE_TOKEN


def write_log(status, commit_hash="", file_count=0, category="", error=""):
    entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "module": "sweep",
        "status": status,
        "commit_hash": commit_hash,
        "files_count": file_count,
        "category": category,
        "error": error,
    }
    log_file = _effective_log_file()
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def acquire_lock():
    lock_file = _effective_lock_file()
    if lock_file.exists():
        age = time.time() - lock_file.stat().st_mtime
        if age < 600:
            return False
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    lock_file.write_text(datetime.now().isoformat())
    return True


def release_lock():
    try:
        _effective_lock_file().unlink()
    except FileNotFoundError:
        pass


def run_git(args, timeout=30, _cwd=None):
    """Run a git command.  * _cwd* overrides the repo root for testing."""
    repo = _cwd or _TEST_REPO or ROOT
    result = subprocess.run(
        ["git"] + args, cwd=str(repo),
        capture_output=True, text=True, timeout=timeout
    )
    return result


def unstage_files(files, _cwd=None):
    """Restore *files* from the staging area without touching the working tree.

    Calling this on files not currently staged is a safe no-op.
    """
    for f in files:
        run_git(["restore", "--staged", "--", f], _cwd=_cwd)


def get_changed_files():
    result = run_git(["-c", "core.quotepath=false", "status", "--porcelain"])
    if result.returncode != 0:
        return []
    files = set()
    for line in result.stdout.strip().split("\n"):
        if not line.rstrip():
            continue
        # Format: XY filename (X=staged status, Y=unstaged status)
        # XY is always 2 chars (may include leading space for unstaged-only)
        # Do NOT strip the line — would remove leading space from ' M' etc.
        # Path starts at position 3 (after XY + separator space)
        path = line[3:].strip()
        # Handle renames (format: "R  old -> new")
        if " -> " in path:
            path = path.split(" -> ")[-1]
        if path:
            files.add(path)
    return list(files)


def is_forbidden(filepath):
    normalized = filepath.replace("\\", "/")
    for pat in FORBIDDEN_PATTERNS:
        if re.search(pat, normalized):
            return True
    return False


def classify_files(files):
    """Classify changed files into auto, pipeline, and protected categories.

    Returns (auto_files, pipeline_files, protected_files):
      auto_files       — data/reports/configs, can be auto-committed without token
      pipeline_files   — 代码文件/* with code extensions, need pipeline token
      protected_files  — scripts/, tests/, .github/ (all extensions), need pipeline token
    """
    auto_files = []
    pipeline_files = []
    protected_files = []

    for f in files:
        normalized = f.replace("\\", "/")

        # Check if under PROTECTED_DIRS (all files, all extensions)
        is_protected = False
        for dir_pat in PROTECTED_DIRS:
            if re.search(dir_pat, normalized):
                is_protected = True
                break

        if is_protected:
            protected_files.append(f)
            continue

        # Check if pipeline: code extension + pipeline directory
        ext = os.path.splitext(f)[1].lower()
        is_pipeline = False
        if ext in PIPELINE_EXTENSIONS:
            for dir_pat in PIPELINE_DIRS:
                if re.search(dir_pat, normalized):
                    is_pipeline = True
                    break

        if is_pipeline:
            pipeline_files.append(f)
        else:
            auto_files.append(f)

    return auto_files, pipeline_files, protected_files


def check_pipeline_token():
    token_path = _effective_token_path()
    if not token_path.exists():
        return False
    try:
        token = json.loads(token_path.read_text(encoding="utf-8"))
        if not token.get("active"):
            return False
        executor = token.get("executor", "")
        return executor in ("红结", "红枫")
    except (json.JSONDecodeError, KeyError):
        return False


def is_auto_blocked(filepath):
    """Check if file matches AUTO_COMMIT_BLOCKED patterns."""
    normalized = filepath.replace("\\", "/")
    for pat in AUTO_COMMIT_BLOCKED:
        if re.search(pat, normalized):
            return True
    return False


def is_git_ignored(filepath):
    """Check if a file is matched by .gitignore rules.

    This catches runtime data files (data_full.json, tushare/, etc.) that
    were tracked before being added to .gitignore and should not be auto-committed.
    """
    result = run_git(["check-ignore", "--", filepath])
    return result.returncode == 0


def commit_auto_files(files, dry_run):
    if not files:
        return []

    # E5 filter
    blocked = []
    safe = []
    for f in files:
        if is_forbidden(f):
            blocked.append(f)
        elif is_auto_blocked(f):
            blocked.append(f)
        elif is_git_ignored(f):
            blocked.append(f)
        else:
            safe.append(f)

    if blocked:
        write_log("BLOCKED", file_count=len(blocked), category="auto",
                  error="BLOCKED: " + ", ".join(blocked))

    if not safe:
        return []

    if dry_run:
        print(f"[DRY-RUN] Auto-commit {len(safe)} files:")
        for f in safe:
            print(f"  {f}")
        return [{"category": "auto", "hash": "", "files": len(safe)}]

    # Stage files
    for f in safe:
        run_git(["add", "--", f])

    # PDF deletion guard (红线§1.7)
    result = run_git(["-c", "core.quotepath=false", "diff", "--cached", "--diff-filter=D", "--name-only"])
    deleted_pdfs = [f for f in result.stdout.strip().split("\n") if f.strip().endswith(".pdf")]
    if deleted_pdfs:
        for pdf in deleted_pdfs:
            run_git(["restore", "--staged", "--", pdf])
        write_log("PDF_BLOCKED", file_count=len(deleted_pdfs), category="auto",
                  error="PDF删除拦截(红线§1.7): " + ", ".join(deleted_pdfs))

    # Check if anything left staged
    check = run_git(["diff", "--cached", "--name-only"])
    if not check.stdout.strip():
        return []

    # Commit (no --no-verify: pre-commit hook must run)
    ts = datetime.now().strftime("%Y%m%d-%H%M")
    result = run_git(["commit", "-m", f"auto: sweep — 数据/报告/配置自动同步 [{ts}]"], timeout=60)
    if result.returncode != 0:
        unstage_files(safe)
        write_log("FAILED", category="auto", error=result.stderr.strip())
        return []

    hash_result = run_git(["log", "-1", "--format=%h"])
    commit_hash = hash_result.stdout.strip()
    write_log("COMMITTED", commit_hash=commit_hash, file_count=len(safe), category="auto")
    return [{"category": "auto", "hash": commit_hash, "files": len(safe)}]


def commit_code_files(files, category, dry_run):
    """Commit code files that require a pipeline token.

    *category* is "pipeline" or "protected" (used in logging).
    Both categories require an active pipeline token.
    """
    if not files:
        return []

    if not check_pipeline_token():
        write_log("SKIPPED", file_count=len(files), category=category,
                  error="No active pipeline token")
        return []

    if dry_run:
        can_commit = check_pipeline_token()
        print(f"[DRY-RUN] {category} files {len(files)} (canCommit={can_commit}):")
        for f in files:
            print(f"  {f}")
        return [{"category": category, "hash": "", "files": len(files)}]

    for f in files:
        run_git(["add", "--", f])

    check = run_git(["diff", "--cached", "--name-only"])
    if not check.stdout.strip():
        return []

    cat_label = "管线提交" if category == "pipeline" else "受保护工程"
    ts = datetime.now().strftime("%Y%m%d-%H%M")
    result = run_git(["commit", "-m", f"auto: sweep — {cat_label} [{ts}]"], timeout=60)
    if result.returncode != 0:
        unstage_files(files)
        write_log("FAILED", category=category, error=result.stderr.strip())
        return []

    hash_result = run_git(["log", "-1", "--format=%h"])
    commit_hash = hash_result.stdout.strip()
    write_log("COMMITTED", commit_hash=commit_hash, file_count=len(files), category=category)
    return [{"category": category, "hash": commit_hash, "files": len(files)}]


def push_to_remote():
    result = run_git(["push", "origin"], timeout=120)
    if result.returncode == 0:
        write_log("PUSHED")
        return True
    else:
        write_log("PUSH_FAILED", error=result.stderr.strip())
        return False


def main():
    parser = argparse.ArgumentParser(description="Git auto-sweep — hourly scan (report-only by default)")
    parser.add_argument("--commit", action="store_true", help="Actually commit (default: report-only)")
    parser.add_argument("--push", action="store_true", help="Push after commit (requires --commit)")
    args = parser.parse_args()

    if not acquire_lock():
        write_log("SKIPPED", error="Lock active (<10min)")
        output = {
            "success": False,
            "mode": "report-only",
            "commits": [],
            "push_success": False,
            "blocked_reason": "lock active (<10min)",
            "workspace_dirty_before": False,
            "workspace_dirty_after": False,
            "exit_policy": "locked",
        }
        print(json.dumps(output, ensure_ascii=False))
        sys.exit(2)

    try:
        os.chdir(str(_effective_root()))

        files = get_changed_files()
        workspace_dirty_before = len(files) > 0

        if not files:
            write_log("CLEAN")
            output = {
                "success": True,
                "mode": "report-only",
                "commits": [],
                "push_success": False,
                "blocked_reason": "",
                "workspace_dirty_before": False,
                "workspace_dirty_after": False,
                "exit_policy": "no_changes",
                "auto_files": 0,
                "pipeline_files": 0,
                "protected_files": 0,
            }
            print(json.dumps(output, ensure_ascii=False))
            return  # exit 0 clean

        auto_files, pipeline_files, protected_files = classify_files(files)
        token_required_files = pipeline_files + protected_files

        # Show what would happen
        print(f"\n=== Git Auto-Sweep 巡检报告 ===")
        print(f"auto 文件 ({len(auto_files)}):")
        for f in auto_files[:20]:
            blocked = is_forbidden(f) or is_auto_blocked(f)
            tag = " [BLOCKED]" if blocked else ""
            print(f"  {f}{tag}")
        if len(auto_files) > 20:
            print(f"  ... 共 {len(auto_files)} 个")
        print(f"pipeline 文件 ({len(pipeline_files)}):")
        for f in pipeline_files[:10]:
            print(f"  {f}")
        if len(pipeline_files) > 10:
            print(f"  ... 共 {len(pipeline_files)} 个")
        print(f"protected 文件 ({len(protected_files)}):")
        for f in protected_files[:10]:
            print(f"  {f}")
        if len(protected_files) > 10:
            print(f"  ... 共 {len(protected_files)} 个")
        print(f"===============================\n")

        if not args.commit:
            output = {
                "success": True,
                "mode": "report-only",
                "commits": [],
                "push_success": False,
                "blocked_reason": "",
                "workspace_dirty_before": workspace_dirty_before,
                "workspace_dirty_after": True,
                "exit_policy": "report_only",
                "auto_files": len(auto_files),
                "pipeline_files": len(pipeline_files),
                "protected_files": len(protected_files),
            }
            print(json.dumps(output, ensure_ascii=False))
            return

        # --commit mode
        exit_policy = "commit_push" if args.push else "commit_only"

        # Pre-check: token-required files without token
        blocked_reason = ""
        if token_required_files and not check_pipeline_token():
            blocked_reason = "pipeline/protected files blocked (no active pipeline token)"
            for f in token_required_files:
                write_log("SKIPPED", file_count=1, category="code",
                          error=f"No active pipeline token: {f}")

        results = []
        commit_attempted = False
        if not blocked_reason:
            auto_done = commit_auto_files(auto_files, dry_run=False)
            if auto_done:
                results.extend(auto_done)
                commit_attempted = True
            pipe_done = commit_code_files(pipeline_files, "pipeline", dry_run=False)
            if pipe_done:
                results.extend(pipe_done)
                commit_attempted = True
            prot_done = commit_code_files(protected_files, "protected", dry_run=False)
            if prot_done:
                results.extend(prot_done)
                commit_attempted = True

        push_ok = False
        if args.push and results:
            push_ok = push_to_remote()

        # Post-check: workspace still dirty?
        dirty_after = get_changed_files()
        workspace_dirty_after = len(dirty_after) > 0

        # Determine success — fail-closed: any uncertainty = failure
        success = True
        if blocked_reason:
            success = False
        elif token_required_files and not check_pipeline_token():
            success = False
            blocked_reason = "pipeline/protected token revoked during commit"
        elif commit_attempted and not results:
            success = False
            blocked_reason = "commit failed (no commits created)"
        elif args.push and not push_ok:
            success = False
            blocked_reason = "push failed"
        elif workspace_dirty_after:
            success = False
            blocked_reason = "workspace still dirty after commit"

        output = {
            "success": success,
            "mode": "commit",
            "commits": results,
            "push_success": push_ok,
            "blocked_reason": blocked_reason,
            "workspace_dirty_before": workspace_dirty_before,
            "workspace_dirty_after": workspace_dirty_after,
            "exit_policy": exit_policy,
            "auto_files": len(auto_files),
            "pipeline_files": len(pipeline_files),
            "protected_files": len(protected_files),
        }
        print(json.dumps(output, ensure_ascii=False))

        if not success:
            # Unstage any leftover staged files on failure
            staged_after = run_git(["diff", "--cached", "--name-only"])
            if staged_after.stdout.strip():
                leftovers = staged_after.stdout.strip().split("\n")
                unstage_files(leftovers)
            sys.exit(2)

    finally:
        release_lock()


if __name__ == "__main__":
    main()
