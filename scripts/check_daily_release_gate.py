#!/usr/bin/env python3
"""
check_daily_release_gate.py — 日报发布聚合闸门

顺序执行8项检查(P0-A~P0-H)，任一FAIL则BLOCK发布。
用法:
    python3 scripts/check_daily_release_gate.py --date 20260603

Code level: L2
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ACTIVE_TARGETS_PATH = ROOT / "00_项目地基" / "02_权威注册表" / "daily_report_targets.json"
_REPORT_OVERRIDE = os.environ.get("REPORT_ROOT_OVERRIDE")
REPORT_DIR = Path(_REPORT_OVERRIDE) if _REPORT_OVERRIDE else ROOT / "重点股票" / "股票报告"

CHECKS = [
    ("P0-A: 基线权威性",       ["scripts/check_baseline_authority.py", "--all", "--date"]),
    ("P0-B: 数值源一致性",     ["scripts/check_numeric_source_consistency.py", "--all", "--date"]),
    ("P0-C: 新鲜度退化",       ["scripts/check_freshness_degradation.py", "--all", "--date"]),
    ("P0-D: MD/Sidecar一致性", ["scripts/check_md_sidecar_consistency.py", "--all", "--date"]),
    ("P0-E: 日报样式锁定",     ["scripts/check_daily_report_style.py", "--date"]),
    ("P0-F: 协作解读完整性",   ["scripts/check_daily_collaborative_interpretation.py", "--date"]),
    ("P0-G: 日报内容完整度",   ["scripts/check_daily_data_completeness.py", "--all-pool", "--date"]),
    ("P0-H: D07合同检查",      ["scripts/check_daily_d07_v12_contract.py", "--date", "--all"]),
]

# Per-active-target check templates (for --active-only mode).
# Uses {code} and {name} placeholders replaced per active target, then date appended.
CHECKS_ACTIVE = [
    ("P0-A: 基线权威性",       ["scripts/check_baseline_authority.py", "--code", "{code}", "--name", "{name}", "--date"]),
    ("P0-B: 数值源一致性",     ["scripts/check_numeric_source_consistency.py", "--code", "{code}", "--name", "{name}", "--date"]),
    ("P0-C: 新鲜度退化",       ["scripts/check_freshness_degradation.py", "--code", "{code}", "--name", "{name}", "--date"]),
    ("P0-D: MD/Sidecar一致性", ["scripts/check_md_sidecar_consistency.py", "--code", "{code}", "--name", "{name}", "--date"]),
    ("P0-E: 日报样式锁定",     ["INLINE"]),   # handled inline below
    ("P0-F: 协作解读完整性",   ["scripts/check_daily_collaborative_interpretation.py", "--date", "--active-only"]),
    ("P0-G: 日报内容完整度",   ["scripts/check_daily_data_completeness.py", "--code", "{code}", "--name", "{name}", "--date"]),
    ("P0-H: D07合同检查",      ["PER_TARGET"]),  # handled per active target below
]

CHECK_COUNT = len(CHECKS)


def load_active_targets():
    """Load enabled active targets from daily_report_targets.json."""
    if not ACTIVE_TARGETS_PATH.exists():
        return []
    try:
        cfg = json.loads(ACTIVE_TARGETS_PATH.read_text(encoding="utf-8"))
        return [
            {"code": str(t["code"]), "name": t["name"]}
            for t in cfg.get("active_targets", [])
            if t.get("enabled", True)
        ]
    except (json.JSONDecodeError, OSError, KeyError):
        return []


def _subprocess_env():
    """Propagate REPORT_ROOT_OVERRIDE to sub-checkers if set."""
    env = os.environ.copy()
    if _REPORT_OVERRIDE:
        env["REPORT_ROOT_OVERRIDE"] = _REPORT_OVERRIDE
    return env


def run_check(label, cmd):
    full_cmd = [sys.executable] + cmd
    try:
        proc = subprocess.run(full_cmd, capture_output=True, text=True, timeout=120, cwd=str(ROOT), env=_subprocess_env())
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


def run_check_per_target(label, cmd_template, targets, date):
    """Run a sub-check per active target. cmd_template has {code}/{name} placeholders."""
    passed = 0
    failed = []
    for t in targets:
        cmd = [sys.executable] + [x.replace("{code}", t["code"]).replace("{name}", t["name"]) for x in cmd_template] + [date]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=str(ROOT), env=_subprocess_env())
            if proc.returncode == 0:
                passed += 1
            else:
                tail = proc.stdout.strip().split("\n")[-2:] if proc.stdout else []
                failed.append(f"{t['name']}({t['code']})")
                for line in tail:
                    if line.strip():
                        print(f"     {line.strip()}")
        except subprocess.TimeoutExpired:
            failed.append(f"{t['name']}({t['code']}) 超时")
    if failed:
        print(f"  ❌ {label}")
        for f in failed:
            print(f"     BLOCK: {f}")
        return False
    print(f"  ✅ {label} ({len(targets)}/{len(targets)})")
    return True


def check_style_active_only(date_str, targets):
    """Inline P0-E style check for active targets (check_daily_report_style.py lacks --code)."""
    issues = []
    for t in targets:
        code = t["code"]
        name = t["name"]
        prefix = f"{name}({code})日报_{date_str}"
        sd = REPORT_DIR / f"{name}({code})"
        for ext, label in [(".md", "MD"), (".json", "JSON"), (".html", "HTML")]:
            p = sd / f"{prefix}{ext}"
            if not p.exists():
                issues.append(f"{name}({code}): {label}缺失")
                continue
            if ext == ".html":
                html = p.read_text(encoding="utf-8", errors="ignore")
                if "font-size: 12px" not in html:
                    issues.append(f"{name}({code}): HTML缺少table font-size 12px")
                if p.stat().st_size < 5000:
                    issues.append(f"{name}({code}): HTML过小({p.stat().st_size} bytes)")
    if issues:
        print(f"  ❌ P0-E: 日报样式锁定")
        for i in issues:
            print(f"     {i}")
        return False
    print(f"  ✅ P0-E: 日报样式锁定 ({len(targets)}/{len(targets)})")
    return True


def main():
    parser = argparse.ArgumentParser(description="日报发布聚合闸门")
    parser.add_argument("--date", required=True, help="日期 YYYYMMDD")
    parser.add_argument("--active-only", action="store_true",
                        help="只检查 daily_report_targets.json 活跃目标，不检查全池")
    args = parser.parse_args()

    date = args.date

    if args.active_only:
        targets = load_active_targets()
        if not targets:
            print(f"\n=== 日报发布闸门 [{date}] (活跃目标模式) ===\n")
            print("  ⚠️ 无活跃目标，跳过所有检查")
            print(f"\n结果: 0通过 / 0失败 / {CHECK_COUNT}总计")
            print("SKIP: 无活跃日报目标")
            sys.exit(0)

        print(f"\n=== 日报发布闸门 [{date}] (活跃目标模式) ===\n")
        print(f"活跃目标: {', '.join(t['name']+'('+t['code']+')' for t in targets)}\n")

        passed = 0
        failed = 0

        # P0-A to P0-D: per active target
        for label, cmd_base in CHECKS_ACTIVE[:4]:
            ok = run_check_per_target(label, cmd_base, targets, date)
            if ok:
                passed += 1
            else:
                failed += 1

        # P0-E: inline style check
        ok = check_style_active_only(date, targets)
        if ok:
            passed += 1
        else:
            failed += 1

        # P0-F: collaborative interpretation with --active-only
        cmd = ["scripts/check_daily_collaborative_interpretation.py", "--date", date, "--active-only"]
        ok = run_check("P0-F: 协作解读完整性 (active)", cmd)
        if ok:
            passed += 1
        else:
            failed += 1

        # P0-G: per active target
        ok = run_check_per_target("P0-G: 日报内容完整度",
                                   ["scripts/check_daily_data_completeness.py", "--code", "{code}", "--name", "{name}", "--date"],
                                   targets, date)
        if ok:
            passed += 1
        else:
            failed += 1

        # P0-H: D07 contract per active target
        ok = run_check_per_target("P0-H: D07合同检查",
                                   ["scripts/check_daily_d07_v12_contract.py", "--code", "{code}", "--name", "{name}", "--date"],
                                   targets, date)
        if ok:
            passed += 1
        else:
            failed += 1

    else:
        print(f"\n=== 日报发布闸门 [{date}] ===\n")

        for label, cmd_base in CHECKS:
            cmd = cmd_base + [date]
            ok = run_check(label, cmd)
            if ok:
                passed += 1
            else:
                failed += 1

    total_checks = CHECK_COUNT
    print(f"\n结果: {passed}通过 / {failed}失败 / {total_checks}总计")
    if failed > 0:
        print("BLOCK: 存在失败的检查项，修复后重试")
        sys.exit(2)
    else:
        print("PASS: 全部闸门通过，允许发布")
        sys.exit(0)


if __name__ == "__main__":
    main()
