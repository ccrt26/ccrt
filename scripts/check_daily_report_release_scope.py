#!/usr/bin/env python3
"""
check_daily_report_release_scope.py — 日报自动化修复发布范围闸门（G5/G6 前置）

职责：
1. 读取 git status --porcelain=v1 --untracked-files=all 或 --status-file 提供的清单。
2. 将变更文件分成五类：
   - RELEASE_ALLOWED：日报自动化修复允许范围
   - NEVER_RELEASE：dashboard、product_api 等永远不得放行
   - EVIDENCE_ALLOWED：运行产物/daily_report_release/evidence/**（需 --allow-generated-evidence）
   - GENERATED_BLOCK：logs、运行产物、历史 manifest（默认 BLOCK）
   - BLOCK：其他未授权文件（兜底）
3. NEVER_RELEASE 永远 BLOCK，即使传 --allow-generated-evidence 也不能 PASS。
4. EVIDENCE_ALLOWED 仅在传 --allow-generated-evidence 时可 PASS。
5. 输出 JSON 含 overall / allowed_files / blocked_files / generated_files / evidence_files / never_release_files / reason / status_lines。

用法：
  python3 scripts/check_daily_report_release_scope.py
  python3 scripts/check_daily_report_release_scope.py --allow-generated-evidence
  python3 scripts/check_daily_report_release_scope.py --status-file /tmp/scope.txt
  python3 scripts/check_daily_report_release_scope.py --status-file /tmp/scope.txt --json
"""
import argparse
import codecs
import json
import subprocess
import sys
from fnmatch import fnmatch
from pathlib import Path

# ===== 日报自动化发布允许文件 =====
# 只包含本次日报自动化修复包的文件
RELEASE_ALLOWED_PATTERNS = [
    # 核心日报链路脚本
    "scripts/run_daily_report_html_only.py",
    "scripts/run_daily_data_retry_once.py",
    "scripts/run_daily_production_pipeline.py",
    "scripts/check_daily_d07_v12_contract.py",
    "scripts/check_daily_release_gate.py",
    "scripts/check_runtime_dependency_readiness.py",
    "scripts/daily_d07_contract_builder.py",
    "scripts/verify_daily_production_closure.py",
    # 本 scope gate + worktree builder
    "scripts/check_daily_report_release_scope.py",
    "scripts/build_daily_report_release_worktree.py",
    # 测试文件
    "tests/test_daily_report_artifact_isolation.py",
    "tests/test_daily_report_promote_safety.py",
    "tests/test_daily_report_d07_gate.py",
    "tests/test_daily_retry_no_d07_bypass.py",
    "tests/test_daily_production_dry_run.py",
    "tests/test_daily_report_release_scope.py",
    "tests/test_daily_report_release_worktree_builder.py",
]

# ===== 永远不得放行 =====
# 即使传 --allow-generated-evidence 也不能 PASS
NEVER_RELEASE_PATTERNS = [
    ".claude/signal_alert.json",
    "docs/keystock-dashboard/*",
    "docs/keystock-dashboard/app.js",
    "docs/keystock-dashboard/index.html",
    "docs/keystock-dashboard/app.css",
    "docs/keystock-dashboard/data/*",
    "docs/keystock-dashboard/data/*/*",
    "docs/keystock-dashboard/data/*/*/*",
    "product_api/*",
    "product_api/*/*",
    "生产产品/*",
    "重点股票产品化后评估/*",
    "运行产物/重点股票产品化后评估/*",
    "运行产物/重点股票产品化后评估/*/*",
]

# ===== 生成/临时产物（默认 BLOCK） =====
# logs、运行产物（除 EVIDENCE 外）、历史数据/manifest 等
GENERATED_BLOCK_PATTERNS = [
    "logs/*",
    "运行产物/*",
    "历史数据/*",
    "历史数据/manifest/*",
    "00_项目地基/*",
]

# ===== 证据放行（需 --allow-generated-evidence） =====
# 仅 release worktree 构建时生成的证据文件
EVIDENCE_ALLOWED_PATTERNS = [
    "运行产物/daily_report_release/evidence/*",
    "运行产物/daily_report_release/evidence/*/*",
]


def _decode_escaped_path(raw_path):
    """Decode a git path that may contain octal \\ooo escape sequences.

    Git with core.quotePath=true (default) escapes non-ASCII bytes in paths
    as \\ooo octal sequences, wrapped in quotes.
    This function strips surrounding quotes and decodes octal, or passes
    through raw UTF-8 paths unchanged.
    """
    path = raw_path.strip()
    # Remove surrounding quotes if present
    if len(path) >= 2 and path.startswith('"') and path.endswith('"'):
        path = path[1:-1]
    # If no backslash escapes (octal \ooo), the path is raw UTF-8 — pass through
    if '\\' not in path:
        return path
    # Decode octal escape sequences: \344\273\243 = 代 (UTF-8 bytes)
    try:
        decoded = codecs.decode(path, 'unicode_escape')
        return decoded.encode('latin-1').decode('utf-8')
    except (ValueError, UnicodeEncodeError, UnicodeDecodeError, LookupError):
        return path


def _decode_git_path(line):
    """Extract and decode the file path from a git status --porcelain line."""
    if len(line) < 3:
        return None
    raw_path = line[3:].strip()
    return _decode_escaped_path(raw_path)


def _path_matches_any(path, patterns):
    """Check if path matches any glob pattern in patterns list."""
    for pattern in patterns:
        if fnmatch(path, pattern):
            return True
    return False


def load_git_status(base_dir, status_file=None):
    """Load git status lines from file or by running git status.

    Uses core.quotePath=false so non-ASCII paths come through as raw UTF-8.
    When reading from a status_file, expects raw UTF-8 paths (not octal escaped).
    """
    lines = []
    if status_file:
        with open(status_file, "r", encoding="utf-8") as f:
            lines = [line.rstrip("\n") for line in f.readlines()]
    else:
        result = subprocess.run(
            ["git", "-c", "core.quotePath=false",
             "status", "--porcelain=v1", "--untracked-files=all"],
            capture_output=True, text=True, timeout=30,
            cwd=base_dir,
        )
        if result.returncode != 0:
            return [], f"git status failed: {result.stderr}"
        lines = result.stdout.rstrip("\n").split("\n") if result.stdout.strip() else []
    return lines, None


def classify_file(path):
    """Classify a single file path with priority ordering.

    Priority:
    1. NEVER_RELEASE — always BLOCK, even with --allow-generated-evidence
    2. RELEASE_ALLOWED — always ALLOW
    3. EVIDENCE_ALLOWED — ALLOW only with --allow-generated-evidence
    4. GENERATED_BLOCK — BLOCK (always, even with --allow-generated-evidence)
    5. Everything else — BLOCK

    Returns one of ('ALLOW', 'NEVER_RELEASE', 'GENERATED', 'EVIDENCE', 'BLOCK').
    """
    path = path.replace("\\", "/")

    # Priority 1: NEVER_RELEASE (always blocked, even with flag)
    if _path_matches_any(path, NEVER_RELEASE_PATTERNS):
        return "NEVER_RELEASE"

    # Priority 2: RELEASE_ALLOWED (always allowed)
    if _path_matches_any(path, RELEASE_ALLOWED_PATTERNS):
        return "ALLOW"

    # Priority 3: EVIDENCE_ALLOWED (allow with flag)
    if _path_matches_any(path, EVIDENCE_ALLOWED_PATTERNS):
        return "EVIDENCE"

    # Priority 4: GENERATED_BLOCK (always blocked)
    if _path_matches_any(path, GENERATED_BLOCK_PATTERNS):
        return "GENERATED"

    # Priority 5: everything else is BLOCK
    return "BLOCK"


def check_scope(base_dir=None, allow_generated=False, status_file=None):
    """Main scope check logic.

    Returns dict with overall/allowed_files/blocked_files/generated_files/
    evidence_files/never_release_files/reason/status_lines.
    """
    if base_dir is None:
        base_dir = str(Path.cwd())

    lines, error = load_git_status(base_dir, status_file)
    if error:
        return {
            "overall": "BLOCK",
            "reason": error,
            "allowed_files": [],
            "blocked_files": [],
            "generated_files": [],
            "evidence_files": [],
            "never_release_files": [],
            "status_lines": [],
        }

    if not lines or (len(lines) == 1 and lines[0] == ""):
        return {
            "overall": "PASS",
            "reason": "no changes detected",
            "allowed_files": [],
            "blocked_files": [],
            "generated_files": [],
            "evidence_files": [],
            "never_release_files": [],
            "status_lines": [],
        }

    allowed_files = []
    blocked_files = []
    generated_files = []
    evidence_files = []
    never_release_files = []
    decoded_lines = []

    for line in lines:
        if not line.strip():
            continue
        path = _decode_git_path(line)
        if path is None:
            continue
        decoded_lines.append({"raw": line, "path": path})

        classification = classify_file(path)

        if classification == "ALLOW":
            allowed_files.append(path)
        elif classification == "NEVER_RELEASE":
            never_release_files.append(path)
        elif classification == "EVIDENCE":
            evidence_files.append(path)
        elif classification == "GENERATED":
            generated_files.append(path)
        else:
            blocked_files.append(path)

    # Determine overall: NEVER_RELEASE → BLOCK unconditionally
    if never_release_files:
        reason = (
            f"BLOCK: {len(never_release_files)} never-release file(s) present. "
            f"These files can never be part of a daily report release. "
            f"Allowed: {len(allowed_files)}, Blocked: {len(blocked_files)}, "
            f"Generated: {len(generated_files)}, Evidence: {len(evidence_files)}, "
            f"NeverRelease: {len(never_release_files)}"
        )
        return {
            "overall": "BLOCK",
            "reason": reason,
            "allowed_files": sorted(allowed_files),
            "blocked_files": sorted(blocked_files),
            "generated_files": sorted(generated_files),
            "evidence_files": sorted(evidence_files),
            "never_release_files": sorted(never_release_files),
            "status_lines": decoded_lines,
        }

    if blocked_files:
        reason = (
            f"BLOCK: {len(blocked_files)} file(s) outside allowed scope. "
            f"Allowed: {len(allowed_files)}, Generated: {len(generated_files)}, "
            f"Evidence: {len(evidence_files)}, Blocked: {len(blocked_files)}"
        )
        return {
            "overall": "BLOCK",
            "reason": reason,
            "allowed_files": sorted(allowed_files),
            "blocked_files": sorted(blocked_files),
            "generated_files": sorted(generated_files),
            "evidence_files": sorted(evidence_files),
            "never_release_files": sorted(never_release_files),
            "status_lines": decoded_lines,
        }

    if generated_files:
        reason = (
            f"BLOCK: {len(generated_files)} generated/artifact file(s) not allowed. "
            f"These cannot be included in a daily report release."
        )
        return {
            "overall": "BLOCK",
            "reason": reason,
            "allowed_files": sorted(allowed_files),
            "blocked_files": sorted(blocked_files),
            "generated_files": sorted(generated_files),
            "evidence_files": sorted(evidence_files),
            "never_release_files": sorted(never_release_files),
            "status_lines": decoded_lines,
        }

    if evidence_files and not allow_generated:
        reason = (
            f"BLOCK: {len(evidence_files)} evidence file(s) need "
            f"--allow-generated-evidence. Use this flag only for release worktree "
            f"evidence at 运行产物/daily_report_release/evidence/**."
        )
        return {
            "overall": "BLOCK",
            "reason": reason,
            "allowed_files": sorted(allowed_files),
            "blocked_files": sorted(blocked_files),
            "generated_files": sorted(generated_files),
            "evidence_files": sorted(evidence_files),
            "never_release_files": sorted(never_release_files),
            "status_lines": decoded_lines,
        }

    reason = f"PASS: {len(allowed_files)} allowed file(s)"
    if evidence_files:
        reason += f", {len(evidence_files)} evidence file(s) (allowed by --allow-generated-evidence)"

    return {
        "overall": "PASS",
        "reason": reason,
        "allowed_files": sorted(allowed_files),
        "blocked_files": sorted(blocked_files),
        "generated_files": sorted(generated_files),
        "evidence_files": sorted(evidence_files),
        "never_release_files": sorted(never_release_files),
        "status_lines": decoded_lines,
    }


def main():
    ap = argparse.ArgumentParser(description="日报自动化修复发布范围闸门")
    ap.add_argument("--status-file", help="从文件读取 git status 输出（用于测试）")
    ap.add_argument("--base-dir", default=None, help="项目根目录（默认当前目录）")
    ap.add_argument("--allow-generated-evidence", action="store_true",
                    help=("仅允许 运行产物/daily_report_release/evidence/** 放行。"
                          "不得放行 dashboard/product_api/logs/manifest。"))
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    result = check_scope(
        base_dir=args.base_dir,
        allow_generated=args.allow_generated_evidence,
        status_file=args.status_file,
    )

    if args.json or not args.status_file:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Overall: {result['overall']}")
        print(f"Reason: {result['reason']}")
        if result["allowed_files"]:
            print(f"\nAllowed ({len(result['allowed_files'])}): {', '.join(result['allowed_files'])}")
        if result["blocked_files"]:
            print(f"\nBlocked ({len(result['blocked_files'])}): {', '.join(result['blocked_files'])}")
        if result["generated_files"]:
            print(f"\nGenerated ({len(result['generated_files'])}): {', '.join(result['generated_files'])}")
        if result["evidence_files"]:
            print(f"\nEvidence ({len(result['evidence_files'])}): {', '.join(result['evidence_files'])}")
        if result["never_release_files"]:
            print(f"\nNeverRelease ({len(result['never_release_files'])}): {', '.join(result['never_release_files'])}")

    if result["overall"] == "BLOCK":
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
