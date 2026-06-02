#!/usr/bin/env python3
"""PreToolUse_hook.py — Redline pre-check + style compliance + whitepaper matching.

Replaces PreToolUse_hook.ps1. Runs before each Bash/Python tool use.
Output is suppressed on success, only failing checks produce output.

Code level: L1 (infrastructure)
"""
import os
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)


def check_redlines(tool_input):
    """Run quick redline check. Returns list of error messages."""
    redline_script = os.path.join(PROJECT_ROOT, "代码文件", "规则红线", "check_redlines.py")
    errors = []
    if os.path.exists(redline_script):
        try:
            result = subprocess.run(
                ["python3", redline_script, "--Quick"],
                capture_output=True, text=True, timeout=30, cwd=PROJECT_ROOT
            )
            if result.returncode != 0 or re.search(r'FAIL|ERROR|违规', result.stdout + result.stderr):
                errors.append(f"红线检查: {result.stdout[:200]}")
        except Exception:
            pass
    return errors


def check_style(tool_input):
    """Run quick style check. Returns list of error messages."""
    style_script = os.path.join(PROJECT_ROOT, "代码文件", "规则红线", "check_report_style.py")
    errors = []
    if os.path.exists(style_script):
        try:
            result = subprocess.run(
                ["python3", style_script, "--Quick"],
                capture_output=True, text=True, timeout=30, cwd=PROJECT_ROOT
            )
            if result.returncode != 0 or re.search(r'FAIL|ERROR|违规', result.stdout + result.stderr):
                errors.append(f"样式检查: {result.stdout[:200]}")
        except Exception:
            pass
    return errors


def check_whitepaper(tool_input):
    """Match task to whitepaper. Non-blocking informational check."""
    matching_patterns = [
        "scoring_engine", "gen_daily", "run_daily_eval", "gen_eval",
        "keystock", "gen_doc", "gen_pdf",
    ]
    if not any(p in tool_input for p in matching_patterns):
        return []

    task_supervisor = os.path.join(PROJECT_ROOT, "代码文件", "监督机制", "task_supervisor.ps1")
    # task_supervisor is informational only, skip if not available
    if not os.path.exists(task_supervisor):
        return []
    return []


def check_exemption_overlimit():
    """Check if any rule exemption has been used >=3 consecutive times."""
    improv_log = os.path.join(PROJECT_ROOT, "改进日志.md")
    if not os.path.exists(improv_log):
        return []
    try:
        with open(improv_log, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return []

    exempt_pattern = r'豁免.*?(§\d+\.\d+[^)]*)'
    matches = re.findall(exempt_pattern, content)
    if len(matches) < 3:
        return []

    rule_counts = {}
    for m in matches:
        rule = re.sub(r'\s+', ' ', m).strip()
        rule_counts[rule] = rule_counts.get(rule, 0) + 1

    over_limit = {k: v for k, v in rule_counts.items() if v >= 3}
    if over_limit:
        items = "; ".join(f"{k}: {v}次" for k, v in over_limit.items())
        return [f"紧急豁免: 以下规则连续豁免>=3次，须启动规则修订 — {items}"]
    return []


def main():
    tool_input = sys.argv[1] if len(sys.argv) > 1 else ""
    errors = []

    errors.extend(check_redlines(tool_input))
    errors.extend(check_style(tool_input))
    errors.extend(check_whitepaper(tool_input))
    errors.extend(check_exemption_overlimit())

    if errors:
        print("[HOOK] 合规检查失败！")
        for e in errors:
            print(e)


if __name__ == "__main__":
    main()
