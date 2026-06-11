#!/usr/bin/env python3
"""CCRT Git Guard — minimal test suite.

Runs without pytest. Covers classification, bad-base blocking, and CLI plumbing.
"""
import json
import subprocess
import sys
from pathlib import Path

# Allow import from scripts/ at project root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.git_guard.ccrt_github_guard import check_upstream, classify  # noqa: E402


def run_cmd(args):
    return subprocess.run(
        [sys.executable, "-m", "scripts.git_guard", *args],
        capture_output=True,
        text=True,
    )


def test_classify():
    """Classification patterns must match correctly."""
    cases = [
        ("logs/a.log", "runtime"),
        ("x/y/z.pyc", "runtime"),
        ("x/__pycache__/foo.cpython-39.pyc", "runtime"),
        ("代码文件/数据/l2_cache/l2_cache.db", "runtime"),
        ("代码文件/数据/l2_cache/l2_cache.db-wal", "runtime"),
        ("代码文件/数据/l2_cache/backup/l2_cache_20260611_092901.db.gz", "runtime"),
        ("代码文件/数据/l2_cache/last_update.json", "runtime"),
        ("代码文件/数据/l2_cache/operation_log.jsonl", "runtime"),
        ("代码文件/数据/l2_cache/shadow_diff_log.jsonl", "runtime"),
        ("docs/daily_reports/000001/report.html", "report"),
        ("重点股票/股票报告/a/b.md", "report"),
        ("重点股票/股票报告/x.md", "report"),
        ("每日荐股/股票报告/y.pdf", "report"),
        ("重点股票/深度分析/深度分析报告/z.pdf", "report"),
        ("重点股票/汇总/summary.md", "report"),
        ("scripts/git_guard/ccrt_github_guard.py", "code"),
        ("scripts/foo.py", "code"),
        ("代码文件/lib/something.py", "code"),
        ("tools/foo.py", "code"),
        ("统一解读/v1/interpreter.py", "code"),
        ("模拟交易/交易引擎/engine.py", "code"),
        (".github/workflows/git_guard.yml", "governance"),
        ("CLAUDE.md", "governance"),
        ("scripts/config.json", "config"),
        ("scripts/deploy.sh", "config"),
        ("rules.ps1", "config"),
        ("docs/report.docx", "document"),
        ("data.csv", "document"),
    ]
    for path, expected in cases:
        result = classify(path)
        assert result == expected, f"classify({path!r}) = {result!r}, expected {expected!r}"
    print(f"  classify: {len(cases)} cases PASS")


def test_ready_bad_base():
    """ready --base does-not-exist must return non-zero and output BLOCK."""
    result = run_cmd(["ready", "--base", "does-not-exist", "--json"])
    assert result.returncode != 0, f"expected non-zero, got {result.returncode}"
    assert "BLOCK" in result.stdout or "BLOCK" in result.stderr, (
        f"expected BLOCK in output, got stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    print("  ready --base does-not-exist: BLOCK PASS")


def test_upstream_match():
    """Feature branch should not treat origin/master as matching upstream."""
    mismatch = check_upstream("codex-github-upload-guard", "origin/master")
    assert mismatch.status == "WARN"
    matched = check_upstream("codex-github-upload-guard", "origin/codex-github-upload-guard")
    assert matched.status == "PASS"
    print("  upstream match: PASS")


def test_snapshot():
    """snapshot --json must return 0 and valid JSON."""
    result = run_cmd(["snapshot", "--json"])
    assert result.returncode == 0, f"snapshot failed: {result.stderr}"
    data = json.loads(result.stdout)
    assert "branch" in data
    assert "working_tree" in data
    print(f"  snapshot: branch={data['branch']} working_tree={len(data['working_tree'])} PASS")


def test_classify_cli():
    """classify --json must return 0 and valid JSON."""
    result = run_cmd(["classify", "--json"])
    assert result.returncode == 0, f"classify failed: {result.stderr}"
    data = json.loads(result.stdout)
    assert isinstance(data, list)
    print(f"  classify --json: {len(data)} entries PASS")


def main():
    print("test_git_guard:")
    test_classify()
    test_ready_bad_base()
    test_upstream_match()
    test_snapshot()
    test_classify_cli()
    print("test_git_guard: PASS")


if __name__ == "__main__":
    main()
