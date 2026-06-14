#!/usr/bin/env python3
"""Programmatic GitHub upload guard for the CCRT workspace.

The guard turns CCRT role responsibilities into executable checks. It does not
sign for roles; it reports whether each responsibility lane is ready, warning,
or blocking before a branch is uploaded or reviewed.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[2]

DEFAULT_BASE = "origin/master"
MAIN_BRANCHES = {"master", "main"}

RUNTIME_PATTERNS = [
    "*.log",
    "*.tmp",
    "*.temp",
    "*.bak",
    "*.pyc",
    "__pycache__/*",
    "logs/*",
    ".claude/hooks/pre-commit.log",
    ".claude/sessions/*",
    ".claude/projects/*",
    ".claude/telemetry/*",
    "代码文件/数据/l2_cache/*shadow_diff_log.jsonl",
    "代码文件/数据/l2_cache/*.db",
    "代码文件/数据/l2_cache/*.db-*",
    "代码文件/数据/l2_cache/last_update.json",
    "代码文件/数据/l2_cache/operation_log.jsonl",
    "代码文件/数据/l2_cache/shadow_diff_log.jsonl",
    "代码文件/数据/l2_cache/backup/*.db",
    "代码文件/数据/l2_cache/backup/*.db-*",
    "代码文件/数据/l2_cache/backup/*.db.gz",
]

REPORT_PATTERNS = [
    "重点股票/股票报告/*",
    "docs/daily_reports/*",
    "每日荐股/股票报告/*",
    "重点股票/深度分析/深度分析报告/*",
    "重点股票/汇总/*",
]

DATA_PATTERNS = [
    "代码文件/数据/*",
    "历史数据/*",
    "daily_data_pack/*",
    "模拟交易/每日快照/*",
    "模拟交易/绩效报告/*",
    "模拟交易/持仓记录/*",
]

CODE_PATTERNS = [
    "scripts/*.py",
    "scripts/**/*.py",
    "代码文件/**/*.py",
    "tools/*.py",
    "统一解读/**/*.py",
    "模拟交易/**/*.py",
]

GOVERNANCE_PATTERNS = [
    ".github/*",
    ".github/**/*",
    "CLAUDE.md",
]

MAX_DIRTY_FILES = 80
MAX_UNTRACKED_FILES = 20
MAX_SINGLE_FILE_LINES = 5000
MAX_DATA_FILE_LINES = 20000


@dataclass
class Finding:
    lane: str
    status: str
    message: str
    files: List[str] = field(default_factory=list)


@dataclass
class ChangedFile:
    path: str
    status: str = ""
    added: Optional[int] = None
    deleted: Optional[int] = None
    category: str = "other"

    @property
    def total_lines(self) -> int:
        return (self.added or 0) + (self.deleted or 0)


def emit(text: str) -> None:
    sys.stdout.write(text)
    if not text.endswith("\n"):
        sys.stdout.write("\n")


def run_git(args: Sequence[str], check: bool = False) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result


def matches(path: str, patterns: Iterable[str]) -> bool:
    normalized = path.replace("\\", "/")
    for pattern in patterns:
        # Extension-only patterns (no directory separator): check basename recursively
        if "/" not in pattern:
            if fnmatch.fnmatch(normalized, pattern) or fnmatch.fnmatch(
                normalized.rsplit("/", 1)[-1], pattern
            ):
                return True
        # Directory patterns ending with /* or /**: match any depth by prefix
        elif pattern.endswith("/*") or pattern.endswith("/**"):
            prefix = pattern.rstrip("*")
            if normalized.startswith(prefix):
                return True
        elif fnmatch.fnmatch(normalized, pattern):
            return True
    return False


def classify(path: str) -> str:
    if matches(path, RUNTIME_PATTERNS):
        return "runtime"
    if matches(path, REPORT_PATTERNS):
        return "report"
    if matches(path, DATA_PATTERNS):
        return "data"
    if matches(path, CODE_PATTERNS):
        return "code"
    if matches(path, GOVERNANCE_PATTERNS):
        return "governance"
    if path.endswith((".yml", ".yaml", ".json", ".toml", ".sh", ".ps1")):
        return "config"
    if path.endswith((".md", ".docx", ".pdf", ".xlsx", ".csv")):
        return "document"
    return "other"


def current_branch() -> str:
    result = run_git(["branch", "--show-current"])
    return result.stdout.strip()


def upstream_branch() -> str:
    result = run_git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    return result.stdout.strip() if result.returncode == 0 else ""


def ensure_base_ref(base: str) -> None:
    result = run_git(["rev-parse", "--verify", f"{base}^{{commit}}"])
    if result.returncode != 0:
        raise RuntimeError(f"base ref not found or not a commit: {base}")


def parse_porcelain_z(raw: str) -> List[ChangedFile]:
    if not raw:
        return []
    parts = raw.split("\0")
    files: List[ChangedFile] = []
    i = 0
    while i < len(parts):
        entry = parts[i]
        i += 1
        if not entry:
            continue
        status = entry[:2].strip() or entry[:2]
        path = entry[3:]
        if status.startswith("R") or status.startswith("C"):
            if i < len(parts):
                path = parts[i]
                i += 1
        files.append(ChangedFile(path=path, status=status, category=classify(path)))
    return files


def working_tree_changes() -> List[ChangedFile]:
    result = subprocess.run(
        [
            "git",
            "-c",
            "core.quotepath=false",
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
        ],
        cwd=ROOT,
        capture_output=True,
    )
    raw = result.stdout.decode("utf-8", errors="replace")
    return parse_porcelain_z(raw)


def diff_name_status(base: str) -> Dict[str, str]:
    result = run_git(["diff", "--name-status", f"{base}..HEAD"], check=True)
    statuses: Dict[str, str] = {}
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) >= 2:
            statuses[parts[-1]] = parts[0]
    return statuses


def diff_numstat(base: str) -> Dict[str, Tuple[Optional[int], Optional[int]]]:
    result = run_git(["diff", "--numstat", f"{base}..HEAD"], check=True)
    stats: Dict[str, Tuple[Optional[int], Optional[int]]] = {}
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        added = int(parts[0]) if parts[0].isdigit() else None
        deleted = int(parts[1]) if parts[1].isdigit() else None
        stats[parts[2]] = (added, deleted)
    return stats


def branch_changes(base: str) -> List[ChangedFile]:
    ensure_base_ref(base)
    statuses = diff_name_status(base)
    stats = diff_numstat(base)
    paths = sorted(set(statuses) | set(stats))
    changes: List[ChangedFile] = []
    for path in paths:
        added, deleted = stats.get(path, (None, None))
        changes.append(
            ChangedFile(
                path=path,
                status=statuses.get(path, ""),
                added=added,
                deleted=deleted,
                category=classify(path),
            )
        )
    return changes


def summarize_categories(files: Iterable[ChangedFile]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for item in files:
        counts[item.category] = counts.get(item.category, 0) + 1
    return dict(sorted(counts.items()))


def blocked_or_warn(
    status: str, lane: str, message: str, files: Iterable[str] = ()
) -> Finding:
    return Finding(lane=lane, status=status, message=message, files=list(files))


def check_branch(branch: str, allow_main: bool) -> Finding:
    if not branch:
        return blocked_or_warn("BLOCK", "阿黑-任务边界", "当前不在具名分支，禁止上传。")
    if branch in MAIN_BRANCHES and not allow_main:
        return blocked_or_warn(
            "BLOCK", "阿黑-任务边界", f"当前分支是 {branch}，禁止直接上传主线。"
        )
    if branch.startswith("codex/") or branch.startswith("codex-"):
        return blocked_or_warn(
            "PASS", "阿黑-任务边界", f"任务分支合规：{branch}"
        )
    return blocked_or_warn(
        "WARN",
        "阿黑-任务边界",
        f"分支 {branch} 可用，但建议使用 codex/ 或 codex- 前缀。",
    )


def check_working_tree(files: List[ChangedFile], allow_dirty: bool) -> Finding:
    if not files:
        return blocked_or_warn("PASS", "旧影-审计基线", "工作区干净。")
    paths = [f.path for f in files]
    if allow_dirty:
        return blocked_or_warn(
            "WARN",
            "旧影-审计基线",
            f"工作区存在 {len(files)} 个未提交变更。",
            paths[:20],
        )
    return blocked_or_warn(
        "BLOCK",
        "旧影-审计基线",
        f"工作区存在 {len(files)} 个未提交变更，上传前必须清理。",
        paths[:20],
    )


def check_backlog_threshold(files: List[ChangedFile]) -> Finding:
    untracked = [f.path for f in files if f.status == "??"]
    if len(files) > MAX_DIRTY_FILES:
        return blocked_or_warn(
            "BLOCK",
            "阿黑-积压阈值",
            f"工作区变更 {len(files)} 个，超过 {MAX_DIRTY_FILES}。",
            [f.path for f in files[:20]],
        )
    if len(untracked) > MAX_UNTRACKED_FILES:
        return blocked_or_warn(
            "BLOCK",
            "阿黑-积压阈值",
            f"未跟踪文件 {len(untracked)} 个，超过 {MAX_UNTRACKED_FILES}。",
            untracked[:20],
        )
    if files:
        return blocked_or_warn(
            "WARN",
            "阿黑-积压阈值",
            f"工作区有 {len(files)} 个变更、{len(untracked)} 个未跟踪。",
        )
    return blocked_or_warn("PASS", "阿黑-积压阈值", "无本地积压。")


def check_runtime_files(files: List[ChangedFile]) -> Finding:
    runtime = [f.path for f in files if f.category == "runtime"]
    if runtime:
        return blocked_or_warn(
            "BLOCK", "旧影-垃圾文件", "运行日志或临时文件混入变更。", runtime[:30]
        )
    return blocked_or_warn("PASS", "旧影-垃圾文件", "未发现运行日志或临时文件。")


def check_data_size(files: List[ChangedFile]) -> Finding:
    large = []
    for item in files:
        if item.total_lines > MAX_SINGLE_FILE_LINES:
            large.append(f"{item.path} ({item.total_lines} lines)")
        elif item.category == "data" and item.total_lines > MAX_DATA_FILE_LINES:
            large.append(f"{item.path} ({item.total_lines} data lines)")
    if large:
        return blocked_or_warn(
            "WARN",
            "玉夜-数据边界",
            "存在大体量 diff，需在 PR 中说明是否可复现。",
            large[:20],
        )
    data_count = sum(1 for f in files if f.category == "data")
    return blocked_or_warn(
        "PASS", "玉夜-数据边界", f"数据变更数量：{data_count}。"
    )


def check_reports(files: List[ChangedFile], allow_production: bool) -> Finding:
    reports = [f.path for f in files if f.category == "report"]
    if reports and not allow_production:
        return blocked_or_warn(
            "BLOCK",
            "腰子-发布边界",
            "正式报告或发布产物变更未显式放行。",
            reports[:30],
        )
    if reports:
        return blocked_or_warn(
            "WARN",
            "腰子-发布边界",
            "包含正式报告或发布产物，必须人工审阅。",
            reports[:30],
        )
    return blocked_or_warn("PASS", "腰子-发布边界", "未触碰正式报告/发布产物。")


def check_code_scope(files: List[ChangedFile]) -> Finding:
    code_files = [f.path for f in files if f.category == "code"]
    if not code_files:
        return blocked_or_warn("PASS", "情墨-代码影响面", "未触碰代码文件。")
    return blocked_or_warn(
        "WARN",
        "情墨-代码影响面",
        f"代码变更 {len(code_files)} 个，需配套验证。",
        code_files[:30],
    )


def check_validation(files: List[ChangedFile]) -> Finding:
    has_code = any(f.category == "code" for f in files)
    has_test = any(
        "/test" in f.path or f.path.startswith("tests/") or "validate_" in f.path
        for f in files
    )
    if has_code and not has_test:
        return blocked_or_warn(
            "WARN",
            "新安-质量验证",
            "包含代码变更但未发现测试/验证文件同步变更。",
        )
    if has_code:
        return blocked_or_warn(
            "PASS", "新安-质量验证", "代码变更包含测试或验证相关文件。"
        )
    return blocked_or_warn("PASS", "新安-质量验证", "本次无需代码测试配套。")


def check_upstream(branch: str, upstream: str) -> Finding:
    if not upstream:
        return blocked_or_warn(
            "WARN",
            "阿黑-GitHub承接",
            "当前分支尚未设置 upstream，首次上传需 git push -u。",
        )
    expected = f"origin/{branch}" if branch else ""
    if expected and upstream != expected:
        return blocked_or_warn(
            "WARN",
            "阿黑-GitHub承接",
            f"upstream 当前为 {upstream}，推送后应承接到 {expected}。",
        )
    return blocked_or_warn("PASS", "阿黑-GitHub承接", f"已设置 upstream：{upstream}")


def evaluate(args: argparse.Namespace) -> Dict[str, object]:
    branch = current_branch()
    upstream = upstream_branch()
    local_changes = working_tree_changes()
    compare_base = args.base or DEFAULT_BASE
    branch_files = branch_changes(compare_base) if args.compare_branch else []
    combined = branch_files + ([] if args.compare_only else local_changes)
    # When --compare-only is set, skip working tree state checks since the
    # focus is only on what the branch has changed relative to the base.
    wt_skip = args.compare_only

    findings = [
        check_branch(branch, args.allow_main),
        check_upstream(branch, upstream),
        check_working_tree([] if wt_skip else local_changes, args.allow_dirty or wt_skip),
        check_backlog_threshold([] if wt_skip else local_changes),
        check_runtime_files(combined),
        check_reports(combined, args.allow_production),
        check_data_size(branch_files),
        check_code_scope(branch_files),
        check_validation(branch_files),
    ]

    status = "PASS"
    if any(f.status == "BLOCK" for f in findings):
        status = "BLOCK"
    elif any(f.status == "WARN" for f in findings):
        status = "WARN"

    return {
        "status": status,
        "root": str(ROOT),
        "branch": branch,
        "upstream": upstream,
        "base": compare_base,
        "working_tree_count": len(local_changes),
        "branch_change_count": len(branch_files),
        "categories": summarize_categories(branch_files or local_changes),
        "findings": [f.__dict__ for f in findings],
    }


def render_report(report: Dict[str, object], as_json: bool) -> None:
    if as_json:
        emit(json.dumps(report, ensure_ascii=False, indent=2))
        return
    emit(f"CCRT GitHub Guard: {report['status']}")
    emit(
        f"branch={report['branch']} upstream={report['upstream'] or '-'} base={report['base']}"
    )
    emit(
        f"working_tree={report['working_tree_count']} branch_changes={report['branch_change_count']}"
    )
    emit(f"categories={json.dumps(report['categories'], ensure_ascii=False)}")
    for finding in report["findings"]:
        emit(f"[{finding['status']}] {finding['lane']}: {finding['message']}")
        for path in finding.get("files", [])[:8]:
            emit(f"  - {path}")


def command_classify(args: argparse.Namespace) -> int:
    files = (
        branch_changes(args.base or DEFAULT_BASE)
        if args.compare_branch
        else working_tree_changes()
    )
    rows = [
        {"path": f.path, "status": f.status, "category": f.category, "lines": f.total_lines}
        for f in files
    ]
    if args.json:
        emit(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        for r in rows:
            emit(f"{r['category']}\t{r['status']}\t{r['path']}")
    return 0


def command_snapshot(args: argparse.Namespace) -> int:
    snapshot = {
        "root": str(ROOT),
        "branch": current_branch(),
        "upstream": upstream_branch(),
        "working_tree": [f.__dict__ for f in working_tree_changes()],
    }
    if args.json:
        emit(json.dumps(snapshot, ensure_ascii=False, indent=2))
    else:
        emit(json.dumps(snapshot, ensure_ascii=False))
    return 0


def command_ready(args: argparse.Namespace) -> int:
    report = evaluate(args)
    render_report(report, args.json)
    return 1 if report["status"] == "BLOCK" else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CCRT GitHub upload guard")
    sub = parser.add_subparsers(dest="command", required=True)

    ready = sub.add_parser("ready", help="check whether current branch is safe to upload or review")
    ready.add_argument("--base", default=DEFAULT_BASE)
    ready.add_argument("--json", action="store_true")
    ready.add_argument("--allow-dirty", action="store_true")
    ready.add_argument("--allow-main", action="store_true")
    ready.add_argument("--allow-production", action="store_true")
    ready.add_argument("--compare-only", action="store_true", help="只检查分支 diff，忽略工作区状态")
    ready.add_argument("--no-branch-compare", dest="compare_branch", action="store_false")
    ready.set_defaults(func=command_ready, compare_branch=True)

    classify_cmd = sub.add_parser("classify", help="classify changed files")
    classify_cmd.add_argument("--base", default=DEFAULT_BASE)
    classify_cmd.add_argument("--json", action="store_true")
    classify_cmd.add_argument("--branch", dest="compare_branch", action="store_true")
    classify_cmd.set_defaults(func=command_classify, compare_branch=False)

    snapshot = sub.add_parser("snapshot", help="emit current git snapshot")
    snapshot.add_argument("--json", action="store_true")
    snapshot.set_defaults(func=command_snapshot)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    os.chdir(ROOT)
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except RuntimeError as exc:
        emit(f"BLOCK: {exc}")
        return 1
