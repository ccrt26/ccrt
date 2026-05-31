#!/usr/bin/env python3
"""release_gate.py — 发布闸门聚合检查。

串联8项事前阻断闸门，全部PASS才输出RELEASE_READY。
任一FAIL输出BLOCK且exit≠0。SKIP/NOT_APPLICABLE ≠ PASS。

外层聚合闸门:
  G1: pre-commit-check.py (A-J all checks)
  G2: check_checklist.py (清单合规+全团签章)
  G3: check_redlines.py (红线合规)
  G4: verify_deployment.py (部署条件)
  G5: PDF版式检查 (重点股票/深度分析/临时PDF审阅版/)
  G6: Web dry-run (docs/deep_analysis齐全性)

报告内容闸门 (G7-G8):
  G7: 结构化JSON完整性 (report.json存在+有效)
  G8: 报告内容完整性 (signals/counter_evidence/decision_impact/baseline_linkage)

签字人: 旧影 (signer必须为旧影，不得null)
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
    """G5: PDF版式检查 — 检查 重点股票/深度分析/临时PDF审阅版/ 目录"""
    temp_dir = os.path.join(PROJECT_ROOT, "重点股票", "深度分析", "临时PDF审阅版")
    if not os.path.isdir(temp_dir):
        return False, "G5 BLOCK: 重点股票/深度分析/临时PDF审阅版/ 目录不存在 (情墨需产出审阅版PDF)"
    pdf_files = [f for f in os.listdir(temp_dir) if f.endswith(".pdf")]
    if not pdf_files:
        return False, "G5 BLOCK: 临时PDF审阅版/ 无PDF文件 (情墨需产出审阅版)"
    return True, f"G5 PASS: 临时PDF审阅版/ 含 {len(pdf_files)} 个PDF"


def check_g7_structured_json():
    """G7: 结构化JSON完整性 — 检查深度分析报告report.json"""
    report_dir = os.path.join(PROJECT_ROOT, "重点股票", "深度分析", "深度分析报告")
    if not os.path.isdir(report_dir):
        return False, "G7 BLOCK: 深度分析报告/ 目录不存在"
    # Check for report.json files in stock subdirectories
    json_count = 0
    for entry in os.listdir(report_dir):
        subdir = os.path.join(report_dir, entry)
        if not os.path.isdir(subdir):
            continue
        for f in os.listdir(subdir):
            if f.endswith(".json") and "report" in f.lower():
                try:
                    with open(os.path.join(subdir, f), "r", encoding="utf-8") as fp:
                        json.load(fp)
                    json_count += 1
                except Exception:
                    return False, f"G7 BLOCK: {entry}/{f} JSON无效"
    if json_count == 0:
        return False, "G7 BLOCK: 无有效结构化JSON报告"
    return True, f"G7 PASS: {json_count} 个有效结构化JSON报告"


def check_g8_content_integrity():
    """G8: 报告内容完整性 — signals/counter_evidence/decision_impact/baseline_linkage"""
    report_dir = os.path.join(PROJECT_ROOT, "重点股票", "深度分析", "深度分析报告")
    if not os.path.isdir(report_dir):
        return False, "G8 BLOCK: 深度分析报告/ 目录不存在"

    required_sections = ["signal", "counter_evidence", "decision_impact", "baseline"]
    missing = []
    for entry in os.listdir(report_dir):
        subdir = os.path.join(report_dir, entry)
        if not os.path.isdir(subdir):
            continue
        for f in os.listdir(subdir):
            if not f.endswith(".json") and not f.endswith(".md"):
                continue
            try:
                with open(os.path.join(subdir, f), "r", encoding="utf-8") as fp:
                    content = fp.read().lower()
            except Exception:
                continue
            for section in required_sections:
                if section not in content:
                    missing.append(f"{entry}/{f}:{section}")
    if missing:
        return False, f"G8 BLOCK: {len(missing)}处内容缺失: {', '.join(missing[:5])}"
    return True, f"G8 PASS: 报告内容完整性检查通过"


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
    skips = set()
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
        skips.add("G2_checklist")
        results["G2_checklist"] = {"passed": False, "output": "G2 NOT_APPLICABLE: 无清单文件，无法验证签章"}
    gates.append(("G3_redline", ["python3", os.path.join(PROJECT_ROOT, "代码文件", "规则红线", "check_redlines.py")]))
    if latest_checklist:
        gates.append(("G4_deploy", ["python3", os.path.join(SCRIPTS_DIR, "verify_deployment.py"), latest_checklist]))
    else:
        skips.add("G4_deploy")
        results["G4_deploy"] = {"passed": False, "output": "G4 NOT_APPLICABLE: 无清单文件，无法验证部署条件"}

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
            # G4 with no G-section is NOT_APPLICABLE, not BLOCK
            if name == "G4_deploy" and "清单G段为空" in output:
                skips.add("G4_deploy")
                results[name] = {"passed": False, "output": "G4 NOT_APPLICABLE: 清单无G段部署项(纯基础设施变更)"}
                print(f"       [NOT_APPLICABLE] 清单无部署项，G4不适用")
            else:
                print(f"       {output[:200]}")
                all_passed = False
        print()

    # G5-G6 manual checks
    for gate_name, check_fn, desc in [
        ("G5_pdf_style", check_g5_pdf_style, "PDF版式"),
        ("G6_web_dryrun", check_g6_web_dryrun, "Web dry-run"),
        ("G7_structured_json", check_g7_structured_json, "结构化JSON"),
        ("G8_content_integrity", check_g8_content_integrity, "报告内容完整性"),
    ]:
        print(f"[{gate_name}] 执行中 ({desc})...")
        ok, msg = check_fn()
        results[gate_name] = {"passed": ok, "output": msg}
        status = "PASS" if ok else "BLOCK"
        print(f"[{status}] {gate_name}: {msg}")
        if not ok:
            all_passed = False
        print()

    # Signer must be 旧影; RELEASE_READY only if no BLOCKs and no SKIPs
    signer = "旧影"
    has_skips = len(skips) > 0

    if has_skips:
        all_passed = False

    gate_result = {
        "timestamp": datetime.now().isoformat(),
        "gate_status": "RELEASE_READY" if all_passed else "BLOCKED",
        "approved": all_passed,
        "signer": signer,
        "skip_gates": list(skips) if skips else [],
        "results": results,
    }
    os.makedirs(os.path.dirname(RELEASE_LOG), exist_ok=True)
    with open(RELEASE_LOG, "w", encoding="utf-8") as f:
        json.dump(gate_result, f, indent=2, ensure_ascii=False)

    print("=" * 60)
    if all_passed:
        print(f"  RELEASE_READY — 全部闸门通过，签字人: {signer}")
    else:
        blocked = [k for k, v in results.items() if not v["passed"]]
        print(f"  BLOCKED — {len(blocked)}个闸门未通过: {', '.join(blocked)}")
        if skips:
            print(f"  SKIP/NOT_APPLICABLE: {', '.join(skips)}")
    print(f"  签字人: {signer}")
    print("=" * 60)

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
