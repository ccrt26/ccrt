#!/usr/bin/env python3
"""release_gate.py — 发布闸门聚合检查。

串联6项事前阻断闸门，全部PASS才输出RELEASE_READY。
任一FAIL输出BLOCK且exit≠0。

闸门链:
  G1: pre-commit-check.py (A-J all checks)
  G2: check_checklist.py (清单合规+全团签章)
  G3: check_redlines.py (红线合规)
  G4: verify_deployment.py (部署条件)
  G5: PDF版式检查 (情墨目检替代，检查临时PDF审阅版/)
  G6: Web dry-run (检查docs/deep_analysis齐全性)
"""
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")
RELEASE_LOG = os.path.join(PROJECT_ROOT, "logs", "release_gate_approved.json")


def run_gate(name, cmd, cwd=None):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                timeout=120, cwd=cwd or PROJECT_ROOT)
        passed = result.returncode == 0
        output = (result.stdout + result.stderr)[:2000]
        return passed, output
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT (120s)"
    except Exception as e:
        return False, str(e)


def check_g5_pdf_style():
    temp_dir = os.path.join(PROJECT_ROOT, "临时PDF审阅版")
    if not os.path.isdir(temp_dir):
        return True, "G5 PASS: 无临时PDF审阅版/ (非发布阶段跳过)"
    pdf_files = [f for f in os.listdir(temp_dir) if f.endswith(".pdf")]
    if not pdf_files:
        return False, "G5 BLOCK: 临时PDF审阅版/ 无PDF文件 (情墨需产出审阅版)"
    return True, f"G5 PASS: 临时PDF审阅版/ 含 {len(pdf_files)} 个PDF"


def check_g6_web_dryrun():
    docs_dir = os.path.join(PROJECT_ROOT, "docs", "deep_analysis")
    if not os.path.isdir(docs_dir):
        return False, "G6 BLOCK: docs/deep_analysis/ 目录不存在"
    stock_dirs = [d for d in os.listdir(docs_dir)
                  if os.path.isdir(os.path.join(docs_dir, d))]
    complete = 0
    incomplete = []
    for sd in stock_dirs:
        sd_path = os.path.join(docs_dir, sd)
        try:
            files = os.listdir(sd_path)
        except Exception:
            continue
        has_html = any(f.endswith(".html") for f in files)
        has_pdf = any(f.endswith(".pdf") for f in files)
        if has_html and has_pdf:
            complete += 1
        else:
            incomplete.append(sd)
    if incomplete:
        return False, f"G6 BLOCK: {len(incomplete)}只股票缺HTML/PDF: {', '.join(incomplete[:5])}"
    return True, f"G6 PASS: {complete}只股票HTML+PDF齐全"


def main():
    results = {}
    all_passed = True

    # Find latest checklist for G2/G4
    checklist_dir = os.path.join(PROJECT_ROOT, "logs", "checklist")
    latest_checklist = None
    if os.path.isdir(checklist_dir):
        checklists = sorted([
            f for f in os.listdir(checklist_dir) if f.endswith(".json")
        ], reverse=True)
        if checklists:
            latest_checklist = os.path.join(checklist_dir, checklists[0])

    gates = [
        ("G1_precommit", ["python3", os.path.join(PROJECT_ROOT, ".claude", "hooks", "pre-commit-check.py")]),
    ]
    if latest_checklist:
        gates.append(("G2_checklist", ["python3", os.path.join(SCRIPTS_DIR, "check_checklist.py"), latest_checklist]))
    else:
        results["G2_checklist"] = {"passed": True, "output": "G2 SKIP: 无清单文件"}
    gates.append(("G3_redline", ["python3", os.path.join(PROJECT_ROOT, "代码文件", "规则红线", "check_redlines.py")]))
    if latest_checklist:
        gates.append(("G4_deploy", ["python3", os.path.join(SCRIPTS_DIR, "verify_deployment.py"), latest_checklist]))
    else:
        results["G4_deploy"] = {"passed": True, "output": "G4 SKIP: 无清单文件"}

    print("=" * 60)
    print("  发布闸门聚合检查 (Release Gate)")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print()

    for name, cmd in gates:
        print(f"[{name}] 执行中...")
        passed, output = run_gate(name, cmd)
        results[name] = {"passed": passed, "output": output[:500]}
        status = "PASS" if passed else "BLOCK"
        print(f"[{status}] {name}")
        if not passed:
            if name == "G4_deploy" and "清单G段为空" in output:
                print(f"       [INFO] 清单无部署项，跳过G4")
                results[name] = {"passed": True, "output": "G4 SKIP: 清单无G段部署项"}
            else:
                print(f"       {output[:200]}")
                all_passed = False
        print()

    print("[G5_pdf_style] 执行中...")
    g5_ok, g5_msg = check_g5_pdf_style()
    results["G5_pdf_style"] = {"passed": g5_ok, "output": g5_msg}
    status = "PASS" if g5_ok else "BLOCK"
    print(f"[{status}] G5_pdf_style: {g5_msg}")
    if not g5_ok:
        all_passed = False
    print()

    print("[G6_web_dryrun] 执行中...")
    g6_ok, g6_msg = check_g6_web_dryrun()
    results["G6_web_dryrun"] = {"passed": g6_ok, "output": g6_msg}
    status = "PASS" if g6_ok else "BLOCK"
    print(f"[{status}] G6_web_dryrun: {g6_msg}")
    if not g6_ok:
        all_passed = False
    print()

    os.makedirs(os.path.dirname(RELEASE_LOG), exist_ok=True)
    gate_result = {
        "timestamp": datetime.now().isoformat(),
        "gate_status": "RELEASE_READY" if all_passed else "BLOCKED",
        "approved": all_passed,
        "signer": None,
        "results": results,
    }
    with open(RELEASE_LOG, "w", encoding="utf-8") as f:
        json.dump(gate_result, f, indent=2, ensure_ascii=False)

    print("=" * 60)
    if all_passed:
        print("  RELEASE_READY — 全部闸门通过，允许覆盖正式目录")
    else:
        blocked = [k for k, v in results.items() if not v["passed"]]
        print(f"  BLOCKED — {len(blocked)}个闸门未通过: {', '.join(blocked)}")
    print("=" * 60)

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
