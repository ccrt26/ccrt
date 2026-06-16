#!/usr/bin/env python3
"""
构建产品 API 包。所有证据字段从真实校验结果生成，不得硬编码 PASS/COMPLETE。
"""

import argparse
import json
import os
import sys
import subprocess
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from 代码文件.重点股票.product_eval.product_api_bundle import ProductApiBundleService


def run_checker(docs_dir: str, data_dir: str) -> dict:
    """运行 productization checker 获取验证结果。"""
    checker = os.path.join(os.path.dirname(__file__), "check_keystock_dashboard_productization.py")
    if not os.path.exists(checker):
        return {"overall": "SKIP", "findings": [], "reason": "checker script not found"}
    result = subprocess.run(
        [sys.executable, checker, "--docs-dir", docs_dir, "--data-dir", data_dir],
        capture_output=True, text=True, cwd=os.path.join(os.path.dirname(__file__), ".."),
    )
    try:
        return json.loads(result.stdout.strip())
    except Exception:
        return {"overall": "ERROR", "findings": [result.stdout[-500:]], "reason": "checker output parse failed"}


def main():
    parser = argparse.ArgumentParser(description="构建产品 API 包")
    parser.add_argument("--base-dir", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--docs-data-dir", required=True)
    parser.add_argument("--evidence-out", default=None)
    parser.add_argument("--review-candidate-out", default=None)
    parser.add_argument("--archive-out", default=None)
    args = parser.parse_args()

    svc = ProductApiBundleService()
    summary = svc.build_all(args.base_dir, args.out_dir, args.docs_data_dir)

    print(f"[API] products: {summary.get('dashboard_overall')}, stocks={summary.get('stocks_count')}")
    print(f"[API] data_truth={summary.get('data_truth_status')}")

    now = datetime.now(timezone.utc).isoformat()

    # 运行 checker
    checker_result = run_checker(
        os.path.dirname(args.docs_data_dir),
        args.docs_data_dir,
    )

    has_block = (
        checker_result.get("overall", "ERROR") != "PASS"
        or any(f.get("status") == "BLOCK" for f in checker_result.get("findings", []))
    )

    if args.evidence_out:
        ev = {
            "phase": "Phase 2/3 productization repair",
            "stage": "G4 self-check candidate",
            "generated_at": now,
            "checker_result": checker_result if checker_result.get("overall") != "SKIP" else "NOT_RUN",
            "test_results": "verification required: run pytest separately",
            "fake_data_hits": checker_result.get("fake_data_hits", []),
            "hardcoded_decision_hits": checker_result.get("hardcoded_decision_hits", []),
            "block_status": has_block,
            "supersedes": "phase2_3_productization_g4_self_check_candidate.json",
        }
        os.makedirs(os.path.dirname(args.evidence_out), exist_ok=True)
        with open(args.evidence_out, "w", encoding="utf-8") as f:
            json.dump(ev, f, ensure_ascii=False, indent=2)
        print(f"[API] G4: {args.evidence_out}")

    if args.review_candidate_out:
        review = {
            "phase": "Phase 2/3 productization repair",
            "stage": "G5 review candidate",
            "generated_at": now,
            "checker_result": checker_result.get("overall", "SKIP"),
            "data_truth_status": summary.get("data_truth_status"),
            "blocks": [f for f in checker_result.get("findings", []) if f.get("status") == "BLOCK"],
            "warns": [f for f in checker_result.get("findings", []) if f.get("status") != "BLOCK"],
            "supersedes": "phase2_3_productization_g5_review_candidate.json",
        }
        os.makedirs(os.path.dirname(args.review_candidate_out), exist_ok=True)
        with open(args.review_candidate_out, "w", encoding="utf-8") as f:
            json.dump(review, f, ensure_ascii=False, indent=2)
        print(f"[API] G5: {args.review_candidate_out}")

    if args.archive_out:
        archive_status = "BLOCK" if has_block else "COMPLETE"
        archive = {
            "phase": "Phase 2/3 productization repair",
            "stage": "G6 archive",
            "generated_at": now,
            "archive_status": archive_status,
            "user_visible_status": "BLOCK" if has_block else "COMPLETE",
            "checker_overall": checker_result.get("overall", "SKIP"),
            "data_truth_status": summary.get("data_truth_status"),
            "supersedes": "phase2_3_productization_g6_archive.json",
            "repo_status": "verify git diff before finalizing",
        }
        os.makedirs(os.path.dirname(args.archive_out), exist_ok=True)
        with open(args.archive_out, "w", encoding="utf-8") as f:
            json.dump(archive, f, ensure_ascii=False, indent=2)
        print(f"[API] G6 ({archive_status}): {args.archive_out}")


if __name__ == "__main__":
    main()
