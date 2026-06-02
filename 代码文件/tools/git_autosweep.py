#!/usr/bin/env python3
"""git_autosweep.py — 每小时自动Git巡检脚本

扫描未提交变更，分类为 auto（数据/报告/配置）和 pipeline（代码文件）。
默认 report-only 模式：只分析和输出报告，不执行任何 git 操作。
须显式 --commit 才提交，须显式 --push 才推送。

用法:
  python3 代码文件/tools/git_autosweep.py              # report-only
  python3 代码文件/tools/git_autosweep.py --commit      # 提交
  python3 代码文件/tools/git_autosweep.py --commit --push  # 提交+推送

退出码: 0=成功或无变更, 1=错误
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
    r'^\.claude/hooks/', r'^\.claude/commands/', r'^\.claude/agents/',
]

PIPELINE_DIRS = [
    r'^代码文件/', r'^模拟交易/交易引擎/', r'^模拟交易/否决审查/',
    r'^模拟交易/分析/', r'^模拟交易/共享模块/', r'^模拟交易/展示/', r'^模拟交易/工具/',
]

PIPELINE_EXTENSIONS = {'.py', '.ps1', '.psm1', '.bat'}


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
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def acquire_lock():
    if LOCK_FILE.exists():
        age = time.time() - LOCK_FILE.stat().st_mtime
        if age < 600:
            return False
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOCK_FILE.write_text(datetime.now().isoformat())
    return True


def release_lock():
    try:
        LOCK_FILE.unlink()
    except FileNotFoundError:
        pass


def run_git(args, timeout=30):
    result = subprocess.run(
        ["git"] + args, cwd=str(ROOT),
        capture_output=True, text=True, timeout=timeout
    )
    return result


def get_changed_files():
    result = run_git(["-c", "core.quotepath=false", "status", "--porcelain"])
    if result.returncode != 0:
        return []
    files = set()
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        # Format: XY filename (X=staged status, Y=unstaged status)
        # Status chars are at positions 0-1, filename starts at position 3
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
    auto_files = []
    pipeline_files = []

    for f in files:
        normalized = f.replace("\\", "/")
        ext = os.path.splitext(f)[1].lower()

        # Check if pipeline: code extension + pipeline directory
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

    return auto_files, pipeline_files


def check_pipeline_token():
    if not PIPELINE_TOKEN.exists():
        return False
    try:
        token = json.loads(PIPELINE_TOKEN.read_text(encoding="utf-8"))
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
        write_log("FAILED", category="auto", error=result.stderr.strip())
        return []

    hash_result = run_git(["log", "-1", "--format=%h"])
    commit_hash = hash_result.stdout.strip()
    write_log("COMMITTED", commit_hash=commit_hash, file_count=len(safe), category="auto")
    return [{"category": "auto", "hash": commit_hash, "files": len(safe)}]


def commit_pipeline_files(files, dry_run):
    if not files:
        return []

    if not check_pipeline_token():
        write_log("SKIPPED", file_count=len(files), category="pipeline",
                  error="No active pipeline token")
        return []

    if dry_run:
        can_commit = check_pipeline_token()
        print(f"[DRY-RUN] Pipeline files {len(files)} (canCommit={can_commit}):")
        for f in files:
            print(f"  {f}")
        return [{"category": "pipeline", "hash": "", "files": len(files)}]

    for f in files:
        run_git(["add", "--", f])

    check = run_git(["diff", "--cached", "--name-only"])
    if not check.stdout.strip():
        return []

    ts = datetime.now().strftime("%Y%m%d-%H%M")
    result = run_git(["commit", "-m", f"auto: sweep — 代码文件管线提交 [{ts}]"], timeout=60)
    if result.returncode != 0:
        write_log("FAILED", category="pipeline", error=result.stderr.strip())
        return []

    hash_result = run_git(["log", "-1", "--format=%h"])
    commit_hash = hash_result.stdout.strip()
    write_log("COMMITTED", commit_hash=commit_hash, file_count=len(files), category="pipeline")
    return [{"category": "pipeline", "hash": commit_hash, "files": len(files)}]


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
        print(json.dumps({"success": True, "mode": "report-only", "commits": [], "push_success": False, "error": "Lock active"}))
        return

    try:
        os.chdir(str(ROOT))

        files = get_changed_files()
        if not files:
            write_log("CLEAN")
            print(json.dumps({"success": True, "mode": "report-only", "commits": [], "push_success": False, "error": ""}))
            return

        auto_files, pipeline_files = classify_files(files)

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
        print(f"===============================\n")

        if not args.commit:
            output = {
                "success": True,
                "mode": "report-only",
                "commits": [],
                "push_success": False,
                "auto_files": len(auto_files),
                "pipeline_files": len(pipeline_files),
            }
            print(json.dumps(output, ensure_ascii=False))
            return

        # --commit mode
        dry_run = not args.commit
        results = []
        results.extend(commit_auto_files(auto_files, dry_run))
        results.extend(commit_pipeline_files(pipeline_files, dry_run))

        push_ok = False
        if args.push and results:
            push_ok = push_to_remote()

        output = {
            "success": True,
            "mode": "commit",
            "commits": results,
            "push_success": push_ok,
            "auto_files": len(auto_files),
            "pipeline_files": len(pipeline_files),
        }
        print(json.dumps(output, ensure_ascii=False))

    finally:
        release_lock()


if __name__ == "__main__":
    main()
