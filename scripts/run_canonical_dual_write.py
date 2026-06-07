#!/usr/bin/env python3
"""
run_canonical_dual_write.py — 第6-G阶段：E2 dual-write 执行器

E2 dual-write 执行顺序：
1. 构建 canonical: build_canonical_report.py --all
2. 渲染 canonical: render_report_from_canonical.py --all → dual-dir
3. 跑 render diff: check_canonical_render_diff.py --all
4. 跑总闸门:   check_canonical_pipeline_gate.py

全部 PASS → DUAL_WRITE_CANONICAL: PASS, exit 0
任一失败 → DUAL_WRITE_CANONICAL: BLOCK, exit 2 (阻断 E3)
"""

import argparse
import json
import os
import subprocess
import sys


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
REPORT_BASE = os.path.join(PROJECT_ROOT, "重点股票", "股票报告")


def expected_dual_dir(date: str) -> str:
    """返回唯一合法的 dual-write 输出目录"""
    return f"/private/tmp/canonical_dual_write_{date}"


def check_dual_dir_safe(dual_dir: str, date: str) -> bool:
    """
    dual-dir 锁死规则：
    realpath 必须等于 /private/tmp/canonical_dual_write_{date} 或位于其子目录。
    任何其他路径 → 不通过。
    """
    real_dual = os.path.realpath(os.path.abspath(dual_dir))
    real_allowed = os.path.realpath(os.path.abspath(expected_dual_dir(date)))
    if real_dual == real_allowed or real_dual.startswith(real_allowed + os.sep):
        return True
    return False


def run_script(script_name: str, args_list: list, timeout: int = 300) -> dict:
    script_path = os.path.join(SCRIPT_DIR, script_name)
    cmd = [sys.executable, script_path] + args_list
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {"exit_code": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}
    except subprocess.TimeoutExpired:
        return {"exit_code": -1, "stdout": "", "stderr": "TIMEOUT"}
    except FileNotFoundError:
        return {"exit_code": -1, "stdout": "", "stderr": f"NOT_FOUND: {script_path}"}


def main():
    parser = argparse.ArgumentParser(description="E2 dual-write 执行器")
    parser.add_argument("--date", type=str, required=True, help="交易日 YYYYMMDD")
    parser.add_argument("--canonical-dir", type=str, default=None, help="canonical 目录（默认 /private/tmp/canonical_reports_{date}）")
    parser.add_argument("--dual-dir", type=str, default=None, help="dual-write 输出目录（默认 /private/tmp/canonical_dual_write_{date}）")
    parser.add_argument("--json", action="store_true", help="JSON 输出")

    args = parser.parse_args()
    date = args.date.replace("-", "")

    canonical_dir = args.canonical_dir or f"/private/tmp/canonical_reports_{date}"
    dual_dir = args.dual_dir or f"/private/tmp/canonical_dual_write_{date}"

    # dual-dir 安全检查
    if not check_dual_dir_safe(dual_dir, date):
        if args.json:
            print(json.dumps({
                "gate": "canonical_dual_write", "date": date,
                "verdict": "BLOCK", "e3_blocked": True,
                "checks": [], "error": f"非法 dual-dir: {dual_dir} — 仅允许 {expected_dual_dir(date)} 或其子目录",
            }, ensure_ascii=False, indent=2))
        else:
            print(f"DUAL_WRITE_CANONICAL: BLOCK — 非法 dual-dir: {dual_dir}")
            print(f"  仅允许 {expected_dual_dir(date)} 或其子目录")
        sys.exit(2)

    checks = []

    # Step 1: 构建 canonical
    build_result = run_script("build_canonical_report.py", ["--all", "--date", date, "--out-dir", canonical_dir], timeout=300)
    build_ok = build_result["exit_code"] == 0
    checks.append({"id": "build_canonical", "status": "PASS" if build_ok else "BLOCK", "exit_code": build_result["exit_code"]})
    if not args.json:
        if build_result["stdout"].strip():
            for line in build_result["stdout"].strip().splitlines():
                print(f"  [build] {line}")
        if build_result["stderr"].strip():
            for line in build_result["stderr"].strip().splitlines():
                print(f"  [build] {line}", file=sys.stderr)

    # Step 2: 渲染 canonical → dual-dir
    if build_ok:
        render_result = run_script("render_report_from_canonical.py", ["--all", "--date", date, "--canonical-dir", canonical_dir, "--out-dir", dual_dir], timeout=300)
        render_ok = render_result["exit_code"] == 0
        checks.append({"id": "canonical_render", "status": "PASS" if render_ok else "BLOCK", "exit_code": render_result["exit_code"]})
        if not args.json:
            if render_result["stdout"].strip():
                for line in render_result["stdout"].strip().splitlines():
                    print(f"  [render] {line}")
            if render_result["stderr"].strip():
                for line in render_result["stderr"].strip().splitlines():
                    print(f"  [render] {line}", file=sys.stderr)
    else:
        checks.append({"id": "canonical_render", "status": "BLOCK", "exit_code": -1, "reason": "build_failed"})

    # Step 3: 跑 render diff
    can_continue = all(c["status"] == "PASS" for c in checks)
    if can_continue:
        diff_result = run_script("check_canonical_render_diff.py", ["--all", "--date", date, "--render-dir", dual_dir], timeout=300)
        diff_ok = diff_result["exit_code"] == 0
        checks.append({"id": "render_diff", "status": "PASS" if diff_ok else "BLOCK", "exit_code": diff_result["exit_code"]})
        if not args.json:
            if diff_result["stdout"].strip():
                for line in diff_result["stdout"].strip().splitlines():
                    print(f"  [diff] {line}")
            if diff_result["stderr"].strip():
                for line in diff_result["stderr"].strip().splitlines():
                    print(f"  [diff] {line}", file=sys.stderr)
    else:
        checks.append({"id": "render_diff", "status": "BLOCK", "exit_code": -1, "reason": "prerequisite_failed"})

    # Step 4: 跑总闸门
    can_continue = all(c["status"] == "PASS" for c in checks)
    if can_continue:
        gate_result = run_script("check_canonical_pipeline_gate.py", ["--date", date, "--canonical-dir", canonical_dir, "--render-dir", dual_dir], timeout=300)
        gate_ok = gate_result["exit_code"] == 0
        checks.append({"id": "pipeline_gate", "status": "PASS" if gate_ok else "BLOCK", "exit_code": gate_result["exit_code"]})
        if not args.json:
            if gate_result["stdout"].strip():
                for line in gate_result["stdout"].strip().splitlines():
                    print(f"  [gate] {line}")
            if gate_result["stderr"].strip():
                for line in gate_result["stderr"].strip().splitlines():
                    print(f"  [gate] {line}", file=sys.stderr)
    else:
        checks.append({"id": "pipeline_gate", "status": "BLOCK", "exit_code": -1, "reason": "prerequisite_failed"})

    all_pass = all(c["status"] == "PASS" for c in checks)
    verdict = "PASS" if all_pass else "BLOCK"

    if args.json:
        out = {
            "gate": "canonical_dual_write",
            "date": date,
            "verdict": verdict,
            "e3_blocked": not all_pass,
            "checks": checks,
        }
        if not all_pass:
            out["error"] = "子闸门失败，E3 blocked"
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(f"\nDUAL_WRITE_CANONICAL: {verdict}")
        for c in checks:
            icon = "✅" if c["status"] == "PASS" else "❌"
            print(f"  {icon} {c['id']}: {c['status']} (exit={c['exit_code']})")
        if not all_pass:
            print("  E3_BLOCKED: true — dual-write 失败，阻断 E3 guarded-cutover")

    sys.exit(0 if all_pass else 2)


if __name__ == "__main__":
    main()
