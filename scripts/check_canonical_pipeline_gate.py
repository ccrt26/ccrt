#!/usr/bin/env python3
"""
check_canonical_pipeline_gate.py — 第6-C阶段：canonical发布前总闸门

串联验证：
1. canonical shadow check
2. report golden diff
3. canonical render
4. canonical render diff

任一子闸门非0 → 总闸门 BLOCK，exit 2
全部通过 → CANONICAL_PIPELINE_GATE: PASS，exit 0

约束：不得 import golden_master_diff.py / sync_report_json.py
禁止 shell=True
"""

import argparse
import json
import os
import subprocess
import sys


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
REPORT_BASE = os.path.join(PROJECT_ROOT, "重点股票", "股票报告")


CHECKS = [
    {"id": "shadow_check", "script": "check_canonical_report_shadow.py",
     "args_fmt": ["--all", "--date", "{date}", "--canonical-dir", "{canonical_dir}"]},
    {"id": "report_golden_diff", "script": "check_report_golden_diff.py",
     "args_fmt": ["--all", "--date", "{date}", "--canonical-dir", "{canonical_dir}"]},
    {"id": "canonical_render", "script": "render_report_from_canonical.py",
     "args_fmt": ["--all", "--date", "{date}", "--canonical-dir", "{canonical_dir}", "--out-dir", "{render_dir}"]},
    {"id": "canonical_render_diff", "script": "check_canonical_render_diff.py",
     "args_fmt": ["--all", "--date", "{date}", "--render-dir", "{render_dir}"]},
]


def check_render_dir_safe(render_dir: str):
    """检查 render-dir 是否位于正式报告目录内"""
    real_render = os.path.realpath(os.path.abspath(render_dir))
    real_report = os.path.realpath(os.path.abspath(REPORT_BASE))
    if real_render == real_report or real_render.startswith(real_report + os.sep):
        return False
    return True


def run_check(script_name: str, args_list: list) -> dict:
    """运行一个子闸门。返回 {"exit_code": int, "stdout": str, "stderr": str}"""
    script_path = os.path.join(SCRIPT_DIR, script_name)
    cmd = [sys.executable, script_path] + args_list
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return {
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
    except subprocess.TimeoutExpired:
        return {"exit_code": -1, "stdout": "", "stderr": "TIMEOUT"}
    except FileNotFoundError:
        return {"exit_code": -1, "stdout": "", "stderr": f"NOT_FOUND: {script_path}"}


def main():
    parser = argparse.ArgumentParser(description="canonical发布前总闸门")
    parser.add_argument("--date", type=str, required=True, help="交易日 YYYYMMDD")
    parser.add_argument("--canonical-dir", type=str, required=True, help="canonical 目录")
    parser.add_argument("--render-dir", type=str, required=True, help="渲染输出目录")
    parser.add_argument("--json", action="store_true", help="JSON 输出")

    args = parser.parse_args()
    date = args.date.replace("-", "")

    # render-dir 安全检查
    if not check_render_dir_safe(args.render_dir):
        if args.json:
            out = {
                "gate": "canonical_pipeline_gate",
                "date": date,
                "verdict": "BLOCK",
                "summary": {"total_checks": 0, "pass": 0, "block": 1},
                "checks": [],
                "error": "禁止写入正式报告目录",
            }
            print(json.dumps(out, ensure_ascii=False, indent=2))
        else:
            print("CANONICAL_PIPELINE_GATE: BLOCK")
            print("  - 禁止写入正式报告目录")
        sys.exit(2)

    results = []
    all_pass = True

    for check_def in CHECKS:
        check_id = check_def["id"]
        script_name = check_def["script"]
        args_fmt = check_def["args_fmt"]

        # 格式化参数
        formatted = [a.replace("{date}", date).replace("{canonical_dir}", args.canonical_dir)
                      .replace("{render_dir}", args.render_dir) for a in args_fmt]

        result = run_check(script_name, formatted)
        status = "PASS" if result["exit_code"] == 0 else "BLOCK"
        if status == "BLOCK":
            all_pass = False

        results.append({
            "id": check_id,
            "status": status,
            "exit_code": result["exit_code"],
        })

        if not args.json:
            if result["stdout"].strip():
                for line in result["stdout"].strip().splitlines():
                    print(f"  [{check_id}] {line}")
            if result["stderr"].strip():
                for line in result["stderr"].strip().splitlines():
                    print(f"  [{check_id}] {line}", file=sys.stderr)
    verdict = "PASS" if all_pass else "BLOCK"
    total = len(results)
    passed = sum(1 for r in results if r["status"] == "PASS")
    blocked = sum(1 for r in results if r["status"] == "BLOCK")

    if args.json:
        out = {
            "gate": "canonical_pipeline_gate",
            "date": date,
            "verdict": verdict,
            "summary": {"total_checks": total, "pass": passed, "block": blocked},
            "checks": results,
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(f"\nCANONICAL_PIPELINE_GATE: {verdict}")
        print(f"  total_checks={total} pass={passed} block={blocked}")

    sys.exit(0 if all_pass else 2)


if __name__ == "__main__":
    main()
