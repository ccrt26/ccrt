#!/usr/bin/env python3
"""check_checklist.py — HMAC 签名审计 (fix3)"""
import sys, json, os, argparse
from log_utils import (
    append_log, checklist_content_hash, hmac_verify, detect_financial_impact, has_l1_or_l2,
    FINANCIAL_PATH_KEYWORDS, FINANCIAL_DESC_KEYWORDS,
)

REQUIRED_FINANCE_ROLES = ["山猫", "信鸽", "玉夜", "流金", "青山"]
REVIEW_1B_ROLES = ["旧影", "新安"]


def check_checklist(cl_path, run_id_override=None, expected_stage=None):
    if not os.path.exists(cl_path):
        print(f"FAIL: 文件不存在: {cl_path}"); sys.exit(1)
    try:
        with open(cl_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"FAIL: JSON非法: {e}"); sys.exit(1)

    rid = run_id_override or data.get("run_id", "UNKNOWN")
    errors = []
    ch = checklist_content_hash(cl_path)
    signoffs = data.get("signoffs", {})
    items = data.get("items", [])

    if not items:
        errors.append("A-F段为空")
    else:
        for idx, item in enumerate(items):
            iid = item.get("id", f"索引{idx}")
            for fld in ["id", "description", "white_paper_ref", "expected_output", "code_level"]:
                if not item.get(fld):
                    errors.append(f"项[{iid}]缺少: {fld}")

    # HMAC 验证所有已有签名
    for role, sig in signoffs.items():
        if not isinstance(sig, dict) or not sig.get("signed"):
            continue
        vs = expected_stage or sig.get("stage", "")
        actor = sig.get("actor", "")
        ok, err = hmac_verify(sig, actor, role, rid, vs, cl_path)
        if not ok:
            errors.append(f"签名[{role}]: {err}")
        # 检测弱签名
        if sig.get("sig_type") != "HMAC-SHA256":
            errors.append(f"签名[{role}]使用弱签名类型({sig.get('sig_type','无')})，已废弃")

    # 情墨
    qm = signoffs.get("情墨", {})
    if not qm.get("signed"):
        errors.append("情墨未签名")

    # 腰子
    if not signoffs.get("腰子", {}).get("signed"):
        errors.append("腰子未签名")

    # L1/L2 → 五角色
    if any(item.get("code_level") in ["L1", "L2"] for item in items):
        for r in REQUIRED_FINANCE_ROLES:
            if not signoffs.get(r, {}).get("signed"):
                errors.append(f"L1/L2变更需{r}签名")

    # review_1b
    if signoffs.get("红结", {}).get("signed"):
        for r in REVIEW_1B_ROLES:
            if not signoffs.get(r, {}).get("signed"):
                errors.append(f"已coding但{r}未签名(review_1b)")

    # financial_impact一致性
    fi = detect_financial_impact(items, data.get("file_budgets", []), "")
    if fi and all(item.get("code_level") == "L0" for item in items):
        errors.append("financial_impact=true但全L0，可能低标，请复核")

    if errors:
        record("FAIL", rid, errors)
        print(f"FAIL: {len(errors)} 个问题")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    record("PASS", rid, [])
    print("PASS: 所有签名有效"); sys.exit(0)


def record(result, rid, reasons):
    append_log("gate", {"run_id": rid, "gate": "gate_1b", "script": "check_checklist.py",
               "trigger": "manual", "commit_sha": os.environ.get("GIT_COMMIT_SHA","unknown"),
               "checks": [{"check_name": "checklist_validation", "result": result}],
               "overall_result": result, "fail_reasons": reasons, "duration_ms": 0})


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="铁律量化 - 档案合规审查 (fix3)")
    p.add_argument("checklist", nargs="?", help="清单路径")
    p.add_argument("--run-id"); p.add_argument("--stage")
    args = p.parse_args()
    if not args.checklist:
        print("用法: python3 check_checklist.py <路径> [--run-id <id>] [--stage <阶段>]"); sys.exit(1)
    check_checklist(args.checklist, args.run_id, args.stage)
