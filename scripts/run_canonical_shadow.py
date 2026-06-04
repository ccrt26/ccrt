#!/usr/bin/env python3
"""
run_canonical_shadow.py — 第6-E阶段：canonical shadow-only 接入

E1 shadow-only 执行器：
1. 构建 canonical: build_canonical_report.py --all
2. 跑总闸门:   check_canonical_pipeline_gate.py

全部通过 → SHADOW_CANONICAL: PASS, exit 0
任一失败 → SHADOW_CANONICAL: BLOCK, exit 2

约束：
- 禁止 shell=True
- 禁止写正式报告目录
- 不修改任何日报/sidecar
- 不进入 E2/E3
"""

import argparse
import json
import os
import subprocess
import sys
import glob


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
REPORT_BASE = os.path.join(PROJECT_ROOT, "重点股票", "股票报告")


def check_render_dir_safe(render_dir: str) -> bool:
    """检查 render-dir 是否位于正式报告目录内"""
    real_render = os.path.realpath(os.path.abspath(render_dir))
    real_report = os.path.realpath(os.path.abspath(REPORT_BASE))
    if real_render == real_report or real_render.startswith(real_report + os.sep):
        return False
    return True


def run_script(script_name: str, args_list: list, timeout: int = 300) -> dict:
    """运行一个子脚本。返回 {"exit_code": int, "stdout": str, "stderr": str}"""
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
    parser = argparse.ArgumentParser(description="canonical shadow-only 接入")
    parser.add_argument("--date", type=str, required=True, help="交易日 YYYYMMDD")
    parser.add_argument("--canonical-dir", type=str, default=None, help="canonical 输出目录（默认 /private/tmp/canonical_reports_{date}）")
    parser.add_argument("--render-dir", type=str, default=None, help="渲染输出目录（默认 /private/tmp/canonical_render_shadow_{date}）")
    parser.add_argument("--json", action="store_true", help="JSON 输出")

    args = parser.parse_args()
    date = args.date.replace("-", "")

    canonical_dir = args.canonical_dir or f"/private/tmp/canonical_reports_{date}"
    render_dir = args.render_dir or f"/private/tmp/canonical_render_shadow_{date}"

    # render-dir 安全检查
    if not check_render_dir_safe(render_dir):
        if args.json:
            out = {
                "gate": "canonical_shadow",
                "date": date,
                "verdict": "BLOCK",
                "checks": [],
                "error": "禁止写入正式报告目录",
            }
            print(json.dumps(out, ensure_ascii=False, indent=2))
        else:
            print("SHADOW_CANONICAL: BLOCK")
            print("  - 禁止写入正式报告目录")
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

    # Step 2: 跑总闸门
    if build_ok:
        gate_result = run_script("check_canonical_pipeline_gate.py",
                                 ["--date", date, "--canonical-dir", canonical_dir, "--render-dir", render_dir],
                                 timeout=300)
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
        checks.append({"id": "pipeline_gate", "status": "BLOCK", "exit_code": -1, "reason": "build_failed"})

    all_pass = all(c["status"] == "PASS" for c in checks)
    verdict = "PASS" if all_pass else "BLOCK"

    if args.json:
        out = {
            "gate": "canonical_shadow",
            "date": date,
            "verdict": verdict,
            "checks": checks,
        }
        if not all_pass:
            out["error"] = "子闸门失败"
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(f"\nSHADOW_CANONICAL: {verdict}")
        for c in checks:
            icon = "✅" if c["status"] == "PASS" else "❌"
            print(f"  {icon} {c['id']}: {c['status']} (exit={c['exit_code']})")

    sys.exit(0 if all_pass else 2)


if __name__ == "__main__":
    main()
