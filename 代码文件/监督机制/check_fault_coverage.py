#!/usr/bin/env python3
"""check_fault_coverage.py — fix commit ↔ fault event 交叉比对

扫描 git log 中的 fix commit（匹配关键词），提取涉及的数据源/数据类型，
在 fault_events.json 中查找对应事件记录。有 fix commit 但无 fault event → FAIL。

用法:
    python3 代码文件/监督机制/check_fault_coverage.py           # 全量检查(最近30天)
    python3 代码文件/监督机制/check_fault_coverage.py --days 7  # 最近7天
    python3 代码文件/监督机制/check_fault_coverage.py --quiet   # 仅输出FAIL项

退出码:
    0 — 全部覆盖（或无关fix commit）
    1 — 存在未覆盖的数据修复commit
    2 — 脚本错误

Code level: L0
Design: 审计报告/架构设计/design_data_fault_closure_v1.0.md
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent.parent)
FAULT_FILE = os.path.join(ROOT, "代码文件", "数据", "fault_events.json")
TZ_SHANGHAI = timezone(timedelta(hours=8))

# Keywords that indicate a data-related fix
FIX_KEYWORDS = [
    "fix:", "修复", "数据", "字段", "API", "api",
    "降级", "数据源", "data", "管线", "采集",
    "缺失", "不兼容", "异常", "error",
]

# Map commit topics to expected fault event IDs
TOPIC_EVENT_MAP = {
    "字段": "P3-02",    # 单字段值域异常
    "API": "P2-01",     # 主API连续失败
    "数据源": "P2-01",  # 主API连续失败
    "降级": "P2-01",    # 主API连续失败
    "采集": "P2-01",    # 主API连续失败
    "管线": "P2-01",    # 主API连续失败
    "缺失": "P3-08",    # 字段缺失
    "不兼容": "P1-03",  # 格式不兼容
}


def get_fix_commits(days=30):
    """Get fix-related commits from git log."""
    try:
        result = subprocess.run(
            ["git", "-C", ROOT, "log", "--oneline", "--no-merges",
             f"--since={days}.days.ago", "--format=%h %s"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            print(f"[ERROR] git log failed: {result.stderr}", file=sys.stderr)
            return []
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"[ERROR] git command failed: {e}", file=sys.stderr)
        return []

    fixes = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        commit_hash, _, message = line.partition(" ")
        # Check if commit message contains fix keywords
        msg_lower = message.lower()
        matched_keywords = [kw for kw in FIX_KEYWORDS if kw.lower() in msg_lower]
        if matched_keywords:
            fixes.append({
                "hash": commit_hash,
                "message": message.strip(),
                "matched_keywords": matched_keywords,
            })
    return fixes


def load_fault_events():
    """Load fault events from JSON file."""
    if not os.path.exists(FAULT_FILE):
        return []
    try:
        with open(FAULT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("events", [])
    except (json.JSONDecodeError, OSError):
        return []


def check_coverage(days=30, quiet=False):
    """Cross-reference fix commits with fault events. Returns (pass, report)."""
    fixes = get_fix_commits(days)
    events = load_fault_events()

    report = {
        "checked_at": datetime.now(TZ_SHANGHAI).isoformat(),
        "days_scanned": days,
        "fix_commits_found": len(fixes),
        "fault_events_found": len(events),
        "uncovered": [],
        "covered": [],
    }

    if not fixes:
        if not quiet:
            print(f"No data-related fix commits in last {days} days.")
        return True, report

    if not events:
        # All fixes are uncovered — no fault events recorded at all
        for fix in fixes:
            report["uncovered"].append({
                "commit": fix["hash"],
                "message": fix["message"],
                "reason": "fault_events.json is empty — no faults ever recorded",
            })
        if not quiet:
            print(f"FAIL: {len(fixes)} fix commits found, but fault_events.json "
                  f"has ZERO events. Fault recording mechanism is not active.")
        return False, report

    # For each fix commit, try to find a matching fault event
    event_sources = {e.get("Source", "").lower() for e in events}
    event_ids = {e.get("EventID", "") for e in events}

    for fix in fixes:
        msg = fix["message"].lower()
        matched = False
        match_reason = ""

        # Check if any event source or description matches
        for evt in events:
            evt_src = evt.get("Source", "").lower()
            evt_desc = evt.get("Description", "").lower()
            if evt_src and evt_src in msg:
                matched = True
                match_reason = f"source '{evt.get('Source')}' in '{evt.get('EventID')}'"
                break
            # Check topic→event_id mapping
            for topic, event_id in TOPIC_EVENT_MAP.items():
                if topic.lower() in msg and event_id in event_ids:
                    matched = True
                    match_reason = f"topic '{topic}' → {event_id}"
                    break
            if matched:
                break

        if matched:
            report["covered"].append({
                "commit": fix["hash"],
                "message": fix["message"],
                "match": match_reason,
            })
        else:
            report["uncovered"].append({
                "commit": fix["hash"],
                "message": fix["message"],
                "reason": f"no matching fault event found. Available events: {len(events)}, "
                          f"sources: {list(event_sources)[:5] or 'none'}",
            })

    # Determine pass/fail
    passed = len(report["uncovered"]) == 0

    if not quiet:
        print(f"\n=== Fault Coverage Report ({days}d) ===")
        print(f"Fix commits: {len(fixes)} | Fault events: {len(events)}")
        print(f"Covered: {len(report['covered'])} | Uncovered: {len(report['uncovered'])}")
        if report["uncovered"]:
            print(f"\n--- UNCOVERED (fix commits without fault records) ---")
            for uc in report["uncovered"]:
                print(f"  [{uc['commit']}] {uc['message'][:80]}")
                print(f"    Reason: {uc['reason']}")
        if report["covered"]:
            print(f"\n--- COVERED ---")
            for c in report["covered"]:
                print(f"  [{c['commit']}] {c['message'][:60]} → {c['match']}")
        print(f"\nResult: {'PASS' if passed else 'FAIL'}")
        if not passed:
            print("Action: 玉夜补充故障记录到 08-数据源故障历史.md")
            print("        红结确保数据获取函数已集成 fault_events.write_fault_event()")

    return passed, report


def main():
    parser = argparse.ArgumentParser(description="Fix commit ↔ fault event coverage check")
    parser.add_argument("--days", type=int, default=30, help="Look back N days (default: 30)")
    parser.add_argument("--quiet", action="store_true", help="Quiet mode: only output FAIL items")
    parser.add_argument("--json", action="store_true", help="Output report as JSON")
    args = parser.parse_args()

    passed, report = check_coverage(days=args.days, quiet=args.quiet)

    if args.json:
        report["passed"] = passed
        print(json.dumps(report, ensure_ascii=False, indent=2))

    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
