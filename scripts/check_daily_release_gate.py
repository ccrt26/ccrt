#!/usr/bin/env python3
"""
check_daily_release_gate.py — 日报发布聚合闸门

顺序执行6项检查，任一FAIL则BLOCK发布。
用法:
    python3 scripts/check_daily_release_gate.py --date 20260603

Code level: L2
"""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECKS = [
    ("P0-A: 基线权威性",       ["scripts/check_baseline_authority.py", "--all", "--date"]),
    ("P0-B: 数值源一致性",     ["scripts/check_numeric_source_consistency.py", "--all", "--date"]),
    ("P0-C: 新鲜度退化",       ["scripts/check_freshness_degradation.py", "--all", "--date"]),
    ("P0-D: MD/Sidecar一致性", ["scripts/check_md_sidecar_consistency.py", "--all", "--date"]),
    ("P0-E: 日报样式锁定",     ["scripts/check_daily_report_style.py", "--date"]),
    ("P0-F: 协作解读完整性",   ["scripts/check_daily_collaborative_interpretation.py", "--date"]),
    ("P0-G: 日报内容完整度",   ["scripts/check_daily_data_completeness.py", "--all-pool", "--date"]),
    ("P0-H: 渲染一致性",       ["scripts/check_daily_render_contract.py", "--date"]),
    ("P0-I: 全团解读质量",     ["scripts/check_daily_interpretation_quality.py", "--date"]),
]


def run_check(label, cmd):
    full_cmd = [sys.executable] + cmd
    try:
        proc = subprocess.run(full_cmd, capture_output=True, text=True, timeout=120, cwd=str(ROOT))
        if proc.returncode == 0:
            print(f"  ✅ {label}")
            return True
        else:
            print(f"  ❌ {label}")
            for line in proc.stdout.split("\n")[-5:]:
                if line.strip():
                    print(f"     {line.strip()}")
            for line in proc.stderr.split("\n")[-3:]:
                if line.strip():
                    print(f"     ERR: {line.strip()}")
            return False
    except subprocess.TimeoutExpired:
        print(f"  ⏰ {label}: 超时")
        return False
    except FileNotFoundError:
        print(f"  ❌ {label}: 脚本不存在")
        return False


def main():
    parser = argparse.ArgumentParser(description="日报发布聚合闸门")
    parser.add_argument("--date", required=True, help="日期 YYYYMMDD")
    args = parser.parse_args()

    date = args.date
    print(f"\n=== 日报发布闸门 [{date}] ===\n")

    passed = 0
    failed = 0
    for label, cmd_base in CHECKS:
        cmd = cmd_base + [date]
        ok = run_check(label, cmd)
        if ok:
            passed += 1
        else:
            failed += 1

    print(f"\n结果: {passed}通过 / {failed}失败 / {len(CHECKS)}总计")
    if failed > 0:
        print("BLOCK: 存在失败的检查项，修复后重试")
        sys.exit(2)
    else:
        print("PASS: 全部闸门通过，允许发布")
        sys.exit(0)


if __name__ == "__main__":
    main()
