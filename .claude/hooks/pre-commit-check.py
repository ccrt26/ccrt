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
        for pat in [
            r'(?:[Vv]ersion|版本)\s*(?:\*\*)?\s*[：:]\s*v?(\d+\.\d+(?:\.\d+)?)',
            r'(?m)^\s*>?\s*(?:文件版本|文档版本|内部版本)\s*(?:\*\*)?\s*[：:]\s*v?(\d+\.\d+(?:\.\d+)?)'
        ]:
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
    staged_set = set(staged_files)

    def _rel_path(abspath):
        """Convert absolute path to path relative to PROJECT_ROOT."""
        try:
            return os.path.relpath(abspath, PROJECT_ROOT)
        except Exception:
            return abspath

    def _is_staged(abspath):
        """Check if a file is in the staged set."""
        rp = _rel_path(abspath)
        return rp in staged_set or os.path.basename(abspath) in staged_set or any(
            rp.endswith(s) or s.endswith(rp) for s in staged_set
        )

    # E1: Agent file line count and size (aligned with check_E.py)
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
            is_staged = _is_staged(af)
            if line_count > 250:
                sev = "BLOCK" if is_staged else "WARN"
                tag = "E1" if is_staged else "E1-HISTORICAL"
                log(sev, f"{tag} {sev}: {name} — {line_count} lines (>250)"
                    + ("" if is_staged else " [历史超限，需专项拆分，不阻断本次提交]"))
            elif line_count > 200:
                log("WARN", f"E1 WARN: {name} — {line_count} lines (>200)")
            else:
                log("PASS", f"E1 PASS: {name} ({line_count} lines)")

            size_kb = file_size / 1024
            if size_kb > 12:
                sev = "BLOCK" if is_staged else "WARN"
                tag = "E2" if is_staged else "E2-HISTORICAL"
                log(sev, f"{tag} {sev}: {name} — {size_kb:.1f}KB (>12KB)"
                    + ("" if is_staged else " [历史超限，需专项拆分，不阻断本次提交]"))
            elif size_kb > 10:
                log("WARN", f"E2 WARN: {name} — {size_kb:.1f}KB (>10KB)")
            else:
                log("PASS", f"E2 PASS: {name} ({size_kb:.1f}KB)")
    else:
        log("WARN", "E1/E2: Agent directory not found")

    # E1b: Command file line count and size (aligned with check_E.py)
    cmd_dir = os.path.join(PROJECT_ROOT, ".claude", "commands")
    if os.path.isdir(cmd_dir):
        for entry in os.scandir(cmd_dir):
            if not entry.is_file() or not entry.name.endswith(".md"):
                continue
            cf = entry.path
            try:
                with open(cf, "r", encoding="utf-8") as f:
                    line_count = sum(1 for _ in f)
                file_size = os.path.getsize(cf)
            except Exception:
                continue
            name = entry.name
            is_staged = _is_staged(cf)
            if line_count > 40:
                sev = "BLOCK" if is_staged else "WARN"
                tag = "E1b" if is_staged else "E1b-HISTORICAL"
                log(sev, f"{tag} {sev}: {name} — {line_count} lines (>40)"
                    + ("" if is_staged else " [历史超限，需专项拆分，不阻断本次提交]"))
            elif line_count > 35:
                log("WARN", f"E1b WARN: {name} — {line_count} lines (>35)")
            else:
                log("PASS", f"E1b PASS: {name} ({line_count} lines)")

            size_kb = file_size / 1024
            if size_kb > 2:
                sev = "BLOCK" if is_staged else "WARN"
                tag = "E2b" if is_staged else "E2b-HISTORICAL"
                log(sev, f"{tag} {sev}: {name} — {size_kb:.1f}KB (>2KB)"
                    + ("" if is_staged else " [历史超限，需专项拆分，不阻断本次提交]"))
            else:
                log("PASS", f"E2b PASS: {name} ({size_kb:.1f}KB)")

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

    import os as _os
    any_blocked = False
    run_id = _os.environ.get("CLAUDE_CURRENT_RUN_ID", "")
    for cf in staged_code:
        auth = pipeline_auth.test_pipeline_authorization(cf, PROJECT_ROOT, run_id=run_id)
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


# ── Check I: Dispatcher Authority Boundary ─────────────
def check_i_dispatcher_boundary():
    """Check that 阿黑 has not exceeded authority boundaries.

    Scans pipeline_active.json for:
    - 阿黑 acting as signer for other roles
    - 阿黑 advancing stages they shouldn't
    - 阿黑 executing --complete
    """
    log("PASS", "===== Check I: Dispatcher Authority Boundary (阿黑越权检查) =====")
    token_path = os.path.join(PROJECT_ROOT, ".claude", "pipeline_active.json")
    if not os.path.exists(token_path):
        log("PASS", "I PASS: No pipeline token")
        return

    try:
        with open(token_path, "r", encoding="utf-8") as f:
            token = json.load(f)
    except Exception:
        log("PASS", "I PASS: Token unreadable")
        return

    violations = []

    # Cutoff: violations before this date are historical (WARN); after are BLOCK
    from datetime import timezone as _tz
    CUTOFF = "2026-06-01T07:30:00+00:00"

    # Scan engine_events for 阿黑 advance/complete actions
    eng_file = os.path.join(PROJECT_ROOT, "logs", "engine", "engine_events.jsonl")
    if os.path.exists(eng_file):
        try:
            with open(eng_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        rec = json.loads(line.strip())
                    except Exception:
                        continue
                    if rec.get("actor") != "阿黑":
                        continue
                    action = rec.get("event_type", rec.get("action", ""))
                    if action in ("advance", "complete"):
                        ts = rec.get("timestamp", "")
                        sev = "WARN" if ts < CUTOFF else "BLOCK"
                        violations.append((sev, f"阿黑越权执行{action}: {rec.get('run_id', '?')}"))
        except Exception:
            pass

    # Scan signature_events for 阿黑代签
    sig_file = os.path.join(PROJECT_ROOT, "logs", "signatures", "signature_events.jsonl")
    if os.path.exists(sig_file):
        try:
            with open(sig_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        rec = json.loads(line.strip())
                    except Exception:
                        continue
                    if rec.get("actor") != "阿黑":
                        continue
                    role = rec.get("role", "")
                    if role != "阿黑":
                        ts = rec.get("timestamp", "")
                        sev = "WARN" if ts < CUTOFF else "BLOCK"
                        violations.append((sev, f"阿黑代签{role}: {rec.get('run_id', '?')}"))
        except Exception:
            pass

    # (Run-level scan removed: engine_events above already catches 阿黑 advance/complete.
    #  The old loop here flagged ALL completed runs regardless of who completed them,
    #  causing false blocks on runs completed by 旧影/其他角色.)

    # Report violations — BLOCK on new violations, WARN on historical
    if violations:
        has_block = any(sev == "BLOCK" for sev, _ in violations)
        for sev, msg in violations:
            log(sev, f"I {sev}: {msg}")
        if has_block:
            log("BLOCK", "阿黑越权操作被阻断。阿黑只能建run+分派责任人+阻断不合规。")
        else:
            log("PASS", "I PASS: 阿黑权限边界正常 (历史违规已记录WARN)")
    else:
        log("PASS", "I PASS: 阿黑权限边界正常")


# ── Check J: Formal Report Directory Protection ─────────
def check_j_formal_report_protection(staged_files):
    """Protect 重点股票/深度分析/深度分析报告/ from direct writes.

    Files in the formal report directory require release_gate PASS
    before they can be committed.
    """
    log("PASS", "===== Check J: Formal Report Directory Protection =====")
    formal_dir = "重点股票/深度分析/深度分析报告/"
    formal_files = [f for f in staged_files
                    if f.replace("\\", "/").startswith(formal_dir)
                    and os.path.exists(os.path.join(PROJECT_ROOT, f))]  # skip deletions

    if not formal_files:
        log("PASS", "J PASS: 无正式报告目录文件")
        return

    log("WARN", f"J 检测到正式报告目录文件 ({len(formal_files)}个):")
    for ff in formal_files:
        log("WARN", f"  - {ff}")

    # Check for release_gate approval
    release_gate_path = os.path.join(PROJECT_ROOT, "logs", "release_gate_approved.json")
    if not os.path.exists(release_gate_path):
        log("BLOCK", f"J BLOCK: 正式报告目录写入需release_gate签字。请运行 release_gate.py")
        return

    try:
        with open(release_gate_path, "r", encoding="utf-8") as f:
            gate = json.load(f)
        if gate.get("approved") and gate.get("gate_status") == "RELEASE_READY":
            log("PASS", f"J PASS: release_gate已批准 (签字人: {gate.get('signer', 'unknown')})")
        else:
            log("BLOCK", f"J BLOCK: release_gate未批准 (status={gate.get('gate_status', 'unknown')})")
    except Exception:
        log("BLOCK", "J BLOCK: release_gate批准文件损坏")


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
    check_i_dispatcher_boundary()
    check_j_formal_report_protection(staged_files)

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
