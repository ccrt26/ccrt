#!/usr/bin/env python3
"""git_autocommit.py — Git auto-commit shared module

Replaces git_autocommit.ps1 / git_autopush.ps1 / git_autosweep.ps1 / git_sweep.ps1.
Safety-checked git add + commit + push called at end of pipeline stages.
Code level: L1
"""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent.parent)

FORBIDDEN_PATTERNS = [
    r'\.env$', r'\.env\.', r'credentials\.(json|txt|yml|yaml|env|conf)$',
    r'secret\.(json|txt|yml|yaml)$', r'password', r'(?:^|[/\\])token\.(json|txt|yml|yaml|env)$',
    r'\.pem$', r'\.key$', r'\.pfx$', r'\.p12$', r'private_key', r'privatekey',
    r'id_rsa', r'id_ed25519', r'id_ecdsa', r'\.htpasswd$', r'oauth',
    r'service_account\.json$', r'settings\.local\.json$',
]

MODULE_PREFIX = {
    "daily_pick": "daily:",
    "deep_analysis": "deploy:",
    "daily_brief": "brief:",
    "post_eval": "eval:",
    "data_pipeline": "auto:",
    "pipeline_eng": "pipeline:",
    "engineering": "engineering:",
}


def check_forbidden(paths):
    """Check paths against E5 forbidden patterns."""
    for p in paths:
        for pat in FORBIDDEN_PATTERNS:
            if re.search(pat, p.replace("\\", "/")):
                return False, f"Forbidden pattern '{pat}' matched: {p}"
    return True, ""


def git_autocommit(module, paths, message, dry_run=False, push=False):
    """Safety-checked git add + commit [+ push].

    dry_run=True: NO staging, NO committing, NO pushing. Only computes
    which paths exist, which would be staged, and returns structured result.

    Returns JSON-serializable dict.
    """
    result = {"success": False, "dry_run": dry_run, "files_count": 0, "error": ""}

    # Validate paths
    ok, err = check_forbidden(paths)
    if not ok:
        result["error"] = err
        return result

    # Resolve which paths exist and would be staged
    would_stage = []
    for p in paths:
        abs_p = os.path.join(ROOT, p)
        if os.path.exists(abs_p):
            would_stage.append(p)
        else:
            # Also check if git already tracks it (for deletions etc.)
            try:
                proc = subprocess.run(
                    ["git", "ls-files", "--", p],
                    cwd=ROOT, capture_output=True, text=True, timeout=10
                )
                if proc.stdout.strip():
                    would_stage.append(p)
            except Exception:
                pass

    if not would_stage:
        result["success"] = True
        result["error"] = "No valid paths to stage"
        return result

    result["files_count"] = len(would_stage)
    result["would_stage"] = would_stage

    if dry_run:
        result["success"] = True
        result["error"] = f"DRY RUN: would stage and commit {len(would_stage)} file(s)"
        return result

    # ── Normal (non-dry-run) path below ──

    # Stage
    try:
        subprocess.run(["git", "add"] + would_stage, cwd=ROOT, capture_output=True, timeout=30)
    except Exception as e:
        result["error"] = str(e)
        return result

    # Check if there's anything to commit
    try:
        status = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=ROOT, capture_output=True, text=True, timeout=10
        )
        staged = [f for f in status.stdout.strip().split("\n") if f.strip()]
        if not staged:
            result["success"] = True
            result["error"] = "Nothing to commit (working tree clean)"
            return result
        result["files_count"] = len(staged)
    except Exception as e:
        result["error"] = str(e)
        return result

    # Build commit message
    prefix = MODULE_PREFIX.get(module, "auto:")
    full_msg = f"{prefix} {message}"

    # Commit (never --no-verify; pre-commit hook must run)
    commit_cmd = ["git", "commit", "-m", full_msg]
    try:
        proc = subprocess.run(commit_cmd, cwd=ROOT, capture_output=True, text=True, timeout=60)
        if proc.returncode != 0:
            result["error"] = proc.stderr.strip()
            return result
        hash_proc = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=10
        )
        result["commit_hash"] = hash_proc.stdout.strip()[:8]
    except Exception as e:
        result["error"] = str(e)
        return result

    # Push if requested
    if push:
        try:
            subprocess.run(["git", "push"], cwd=ROOT, capture_output=True, timeout=60)
        except Exception as e:
            result["error"] = f"Commit OK but push failed: {e}"
            result["success"] = True
            return result

    result["success"] = True
    return result


def main():
    parser = argparse.ArgumentParser(description="Git auto-commit with safety checks")
    parser.add_argument("--module", required=True, choices=list(MODULE_PREFIX.keys()))
    parser.add_argument("--paths", nargs="+", default=[], help="Paths to stage")
    parser.add_argument("--message", default="auto commit", help="Commit message")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--push", action="store_true")
    args = parser.parse_args()

    result = git_autocommit(
        args.module, args.paths, args.message,
        dry_run=args.dry_run,
        push=args.push,
    )
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
