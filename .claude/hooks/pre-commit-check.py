#!/usr/bin/env python3
"""pre-commit-check.py — Git pre-commit self-check script.

Replaces pre-commit-check.ps1. Runs before each git commit:
  Check A: Version consistency (filename vs internal declaration)
  Check B: Garbage files detection
  Check C: .md → .docx sync check
  Check D: Commit message format
  Check E: Token budget gate (agent file sizes, print() count, large files)
  Check F: Code file write protection (pipeline authorization)
  Check G: PDF deletion protection (红线§1.7)

Code level: L2 (infrastructure, pre-commit gate)
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ── Import shared auth module ─────────────────────────
HOOK_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(HOOK_DIR / "shared"))
import pipeline_auth  # noqa: E402

PROJECT_ROOT = str(HOOK_DIR.parent.parent)
LOG_FILE = HOOK_DIR / "pre-commit.log"

has_error = False


def log(level, message):
    """Write a log line to stdout and log file."""
    global has_error
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{level}] [{timestamp}] {message}"
    print(line)
    if level in ("ERROR", "BLOCK"):
        has_error = True
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def get_staged_files():
    """Return list of staged file paths from git diff --cached --name-only."""
    try:
        result = subprocess.run(
            ["git", "-c", "core.quotepath=false", "diff", "--cached", "--name-only"],
            capture_output=True, text=True, cwd=PROJECT_ROOT
        )
        return [f.strip() for f in result.stdout.split("\n") if f.strip()]
    except Exception:
        return []


def get_new_files():
    """Return list of newly added (A) staged files."""
    try:
        result = subprocess.run(
            ["git", "-c", "core.quotepath=false", "diff", "--cached", "--diff-filter=A", "--name-only"],
            capture_output=True, text=True, cwd=PROJECT_ROOT
        )
        return [f.strip() for f in result.stdout.split("\n") if f.strip()]
    except Exception:
        return []


def get_deleted_files():
    """Return list of deleted (D) staged files."""
    try:
        result = subprocess.run(
            ["git", "-c", "core.quotepath=false", "diff", "--cached", "--diff-filter=D", "--name-only"],
            capture_output=True, text=True, cwd=PROJECT_ROOT
        )
        return [f.strip() for f in result.stdout.split("\n") if f.strip()]
    except Exception:
        return []


def get_commit_message():
    """Read the commit message from .git/COMMIT_EDITMSG if available."""
    msg_file = os.path.join(PROJECT_ROOT, ".git", "COMMIT_EDITMSG")
    try:
        with open(msg_file, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""


# ── Check A: Version Consistency ──────────────────────
def check_a_version_consistency(staged_files):
    log("PASS", "===== Check A: Version Consistency =====")
    staged_md_ps1 = [f for f in staged_files if re.search(r'\.(md|ps1|py)$', f)]

    for filepath in staged_md_ps1:
        filename = os.path.basename(filepath)
        m = re.search(r'_v(\d+\.\d+(?:\.\d+)?)', filename)
        if not m:
            continue
        file_version = m.group(1)

        full_path = os.path.join(PROJECT_ROOT, filepath)
        if not os.path.exists(full_path):
            log("WARN", f"File not found: {filepath}")
            continue

        try:
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            log("WARN", f"Cannot read file: {filepath}")
            continue

        internal_version = None
        for pat in [r'[Vv]ersion[：:]\s*v(\d+\.\d+(?:\.\d+)?)',
                     r'(?:^|\n)#[^\n]*v(\d+\.\d+(?:\.\d+)?)',
                     r'(?m)^.{0,200}v(\d+\.\d+(?:\.\d+)?)']:
            im = re.search(pat, content)
            if im:
                internal_version = im.group(1)
                break

        if internal_version:
            if file_version != internal_version:
                log("ERROR", f"Version mismatch: {filename} — filename v{file_version}, internal v{internal_version}")
            else:
                log("PASS", f"Version match: {filename} (v{file_version})")
        else:
            log("WARN", f"Filename has v{file_version} but no internal version found: {filename}")


# ── Check B: Garbage Files ────────────────────────────
def check_b_garbage_files(staged_files):
    log("PASS", "===== Check B: Garbage Files =====")
    patterns = [r'^null$', r'\.tmp$', r'\.temp$', r'^~\$', r'/data_cache/']
    garbage = []
    for f in staged_files:
        if any(re.search(p, f) for p in patterns):
            garbage.append(f)
    if garbage:
        log("WARN", "Garbage files detected:")
        for gf in garbage:
            log("WARN", f"  - {gf}")
    else:
        log("PASS", "No garbage files")


# ── Check C: Document Completeness ───────────────────
def check_c_doc_completeness(staged_files):
    log("PASS", "===== Check C: Document Completeness =====")
    staged_md = [f for f in staged_files if f.endswith(".md")]
    for md_file in staged_md:
        docx_file = re.sub(r'\.md$', '.docx', md_file)
        docx_full = os.path.join(PROJECT_ROOT, docx_file)
        if os.path.exists(docx_full):
            if docx_file not in staged_files:
                log("WARN", f".md modified but .docx not staged: {md_file} -> {docx_file}")
            else:
                log("PASS", f".md and .docx synced: {md_file}")
        else:
            log("PASS", f"No .docx counterpart, skip: {md_file}")


# ── Check D: Commit Message Format ────────────────────
def check_d_commit_msg():
    log("PASS", "===== Check D: Commit Message Format =====")
    msg = get_commit_message()
    if not msg:
        log("PASS", "Commit message unavailable (pre-commit stage, skipped)")
        return
    first_line = msg.split("\n")[0].strip()
    if re.match(r'^(feat|fix|docs|chore|refactor|test|deploy|auto):', first_line):
        log("PASS", f"Commit message format OK: {first_line}")
    elif first_line == "":
        log("WARN", "Commit message is empty")
    else:
        log("WARN", f"Commit message format invalid (expected feat|fix|docs|chore|refactor|test:): {first_line}")


# ── Check E: Token Budget Gate ───────────────────────
def _count_effective_prints(filepath):
    """Count print() calls excluding docstrings and comments."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return 0
    count = 0
    in_docstring = False
    for raw_line in lines:
        trimmed = raw_line.strip()
        if not trimmed:
            continue

        # Track triple-quoted docstrings
        triple_count = raw_line.count('"""') + raw_line.count("'''")
        if triple_count % 2 == 1:
            in_docstring = not in_docstring
            continue
        if triple_count >= 2:
            continue
        if in_docstring:
            continue
        if trimmed.startswith("#"):
            continue
        count += len(re.findall(r'\bprint\s*\(', raw_line))
    return count


def _has_protection_declaration(filepath):
    """Check if file has a protection declaration in the first 30 lines."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            head = "".join(f.readline() for _ in range(30))
    except Exception:
        return False
    return bool(re.search(r'(?i)LARGE_FILE_PROTECTED|FILE_PROTECTED|#\s*Protected large file|@ProtectionDeclared', head))


def check_e_token_budget(staged_files, new_files):
    log("PASS", "===== Check E: Token Budget Gate =====")

    # E1/E2: Agent file line count and size
    agent_dir = os.path.join(PROJECT_ROOT, ".claude", "agents")
    if os.path.isdir(agent_dir):
        for entry in os.scandir(agent_dir):
            if not entry.is_file() or not entry.name.endswith(".md"):
                continue
            af = entry.path
            try:
                with open(af, "r", encoding="utf-8") as f:
                    line_count = sum(1 for _ in f)
                file_size = os.path.getsize(af)
            except Exception:
                continue
            name = entry.name
            if line_count > 300:
                log("BLOCK", f"E1 BLOCK: {name} — {line_count} lines (>300)")
            elif line_count > 250:
                log("WARN", f"E1 WARN: {name} — {line_count} lines (>250)")
            else:
                log("PASS", f"E1 PASS: {name} ({line_count} lines)")

            size_kb = file_size / 1024
            if size_kb > 15:
                log("BLOCK", f"E2 BLOCK: {name} — {size_kb:.1f}KB (>15KB)")
            elif size_kb > 12:
                log("WARN", f"E2 WARN: {name} — {size_kb:.1f}KB (>12KB)")
            else:
                log("PASS", f"E2 PASS: {name} ({size_kb:.1f}KB)")
    else:
        log("WARN", "E1/E2: Agent directory not found")

    # E3: Python core script print() count
    core_dirs = [
        os.path.join(PROJECT_ROOT, "代码文件", "每日荐股", "分析逻辑"),
        os.path.join(PROJECT_ROOT, "代码文件", "每日荐股", "scripts"),
    ]
    staged_py = [f for f in staged_files if f.endswith(".py")]
    for py_file in staged_py:
        abs_py = os.path.join(PROJECT_ROOT, py_file)
        if not os.path.exists(abs_py):
            continue
        # Check if it's in a core directory
        in_core = any(abs_py.startswith(cd) for cd in core_dirs if os.path.isdir(cd))
        if not in_core:
            continue
        pc = _count_effective_prints(abs_py)
        rel = os.path.relpath(abs_py, PROJECT_ROOT)
        if pc > 12:
            log("BLOCK", f"E3 BLOCK: {rel} — {pc} print() calls (>12)")
        elif pc > 8:
            log("WARN", f"E3 WARN: {rel} — {pc} print() calls (>8)")
        else:
            log("PASS", f"E3 PASS: {rel} ({pc} print() calls)")

    # E4: New large file protection declaration
    for nf in new_files:
        abs_nf = os.path.join(PROJECT_ROOT, nf)
        if not os.path.exists(abs_nf):
            continue
        nf_size = os.path.getsize(abs_nf)
        if nf_size > 500 * 1024:
            if not _has_protection_declaration(abs_nf):
                log("WARN", f"E4 WARN: New large file lacks protection declaration: {nf} ({nf_size / 1024:.1f}KB)")
            else:
                log("PASS", f"E4 PASS: {nf} — protected")

    # E5: Forbidden file patterns
    forbidden_patterns = [
        r'\.env$', r'\.env\.', r'credentials\.(json|txt|yml|yaml|env|conf)$',
        r'secret\.(json|txt|yml|yaml)$', r'password',
        r'(?:^|[/\\])token\.(json|txt|yml|yaml|env)$',
        r'\.pem$', r'\.key$', r'\.pfx$', r'\.p12$',
        r'private_key', r'privatekey', r'id_rsa', r'id_ed25519', r'id_ecdsa',
        r'\.htpasswd$', r'oauth', r'service_account\.json$', r'settings\.local\.json$'
    ]
    for nf in new_files:
        for pat in forbidden_patterns:
            if re.search(pat, nf.replace("\\", "/")):
                log("BLOCK", f"E5 BLOCK: New file matches forbidden pattern '{pat}': {nf}")
                break
    log("PASS", "Check E complete")


# ── Check F: Code File Write Protection ──────────────
def check_f_code_protection(staged_files):
    log("PASS", "===== Check F: Code File Write Protection =====")
    staged_code = []
    for f in staged_files:
        fn = f.replace("\\", "/")
        if any(re.search(pat, fn) for pat in pipeline_auth.PROTECTED_PATHS):
            staged_code.append(f)

    if not staged_code:
        log("PASS", "F1 PASS: No code files staged. Check F skipped.")
        log("PASS", "Check F complete")
        return

    log("PASS", f"Code files staged ({len(staged_code)} files):")
    for cf in staged_code:
        log("PASS", f"  - {cf}")

    # F0: AutoCommit exemption
    all_auto = True
    for cf in staged_code:
        fn = cf.replace("\\", "/")
        is_auto = any(re.search(pat, fn) for pat in pipeline_auth.AUTOCOMMIT_PATHS)
        if not is_auto:
            is_auto = any(re.search(pat, fn) for pat in pipeline_auth.AUTOCOMMIT_EXTENSIONS)
        if not is_auto:
            all_auto = False
            break

    if all_auto:
        log("PASS", "F0 PASS: All staged code files are AutoCommit-exempt. Skipping pipeline check.")
        log("PASS", "Check F complete")
        return

    any_blocked = False
    for cf in staged_code:
        auth = pipeline_auth.test_pipeline_authorization(cf, PROJECT_ROOT)
        if auth["authorized"]:
            log("PASS", f"F PASS: {cf} — {auth['reason']}")
        else:
            log("BLOCK", f"F BLOCK: {cf} — {auth['reason']}")
            any_blocked = True

    if any_blocked:
        log("BLOCK", "Commit rejected. Start pipeline to authorize code file changes.")
    log("PASS", "Check F complete")


# ── Check G: PDF Deletion Protection ─────────────────
def check_g_pdf_protection():
    log("PASS", "===== Check G: PDF Deletion Protection (红线§1.7) =====")
    deleted = get_deleted_files()
    deleted_pdfs = [f for f in deleted if f.endswith(".pdf")]
    if deleted_pdfs:
        for pdf in deleted_pdfs:
            log("BLOCK", f"G BLOCK: PDF删除禁止 (红线§1.7): {pdf}")
    else:
        log("PASS", "G PASS: No PDFs in deleted files")


# ── Check H: Config Consistency (Stock List) ──────────
def check_h_config_consistency():
    log("PASS", "===== Check H: Config Consistency (重点股票名单) =====")
    pigeon_config = os.path.join(PROJECT_ROOT, "代码文件", "信鸽信息采集", "pigeon_config.json")
    key_stocks = os.path.join(PROJECT_ROOT, "代码文件", "数据", "key_stocks.json")

    # Only check if either file is staged
    staged = set(get_staged_files())
    if pigeon_config not in staged and key_stocks not in staged:
        log("PASS", "H SKIP: 配置文件未变更")
        return

    if not os.path.exists(pigeon_config):
        log("WARN", "H WARN: pigeon_config.json 不存在，跳过")
        return
    if not os.path.exists(key_stocks):
        log("BLOCK", "H BLOCK: key_stocks.json 不存在。请运行 sync_key_stocks.py")
        return

    try:
        import json as _json
        with open(pigeon_config, "r", encoding="utf-8") as f:
            pc = _json.load(f)
        with open(key_stocks, "r", encoding="utf-8") as f:
            ks = _json.load(f)
        pigeon_codes = {s["code"] for s in pc.get("target_stocks", [])}
        key_codes = {s["code"] for s in ks.get("stocks", [])}
        only_pigeon = pigeon_codes - key_codes
        only_key = key_codes - pigeon_codes
        if only_pigeon:
            log("BLOCK", f"H BLOCK: key_stocks.json 缺少标的: {only_pigeon}")
        if only_key:
            log("BLOCK", f"H BLOCK: key_stocks.json 多余标的: {only_key}")
        if not only_pigeon and not only_key:
            log("PASS", f"H PASS: 重点股票名单一致 ({len(pigeon_codes)}只)")
    except Exception as e:
        log("BLOCK", f"H BLOCK: 配置一致性检查失败: {e}")


# ── Main ──────────────────────────────────────────────
def main():
    global has_error

    start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"=== Pre-commit check started at {start_time} ===\n")
    except Exception:
        pass

    staged_files = get_staged_files()
    if not staged_files:
        log("PASS", "No staged files, skip check.")
        sys.exit(0)

    new_files = get_new_files()

    check_a_version_consistency(staged_files)
    check_b_garbage_files(staged_files)
    check_c_doc_completeness(staged_files)
    check_d_commit_msg()
    check_e_token_budget(staged_files, new_files)
    check_f_code_protection(staged_files)
    check_g_pdf_protection()
    check_h_config_consistency()

    end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"=== Pre-commit check completed at {end_time} ===\n")
    except Exception:
        pass

    if has_error:
        print()
        print("[ERROR] Pre-commit check failed, blocking commit.")
        sys.exit(1)
    print()
    print("[PASS] Pre-commit check passed.")
    sys.exit(0)


if __name__ == "__main__":
    main()
