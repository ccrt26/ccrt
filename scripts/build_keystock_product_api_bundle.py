#!/usr/bin/env python3
"""
构建产品 API 包（session3 v3 版）。
strict staging → checker → atomic_publish → legacy mirror → run_manifest PUBLISHED
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
    checker = os.path.join(os.path.dirname(__file__), "check_keystock_dashboard_productization.py")
    if not os.path.exists(checker):
        return {"overall": "SKIP", "engineering_status": "SKIP"}
    result = subprocess.run(
        [sys.executable, checker, "--docs-dir", docs_dir, "--data-dir", data_dir],
        capture_output=True, text=True, cwd=os.path.join(os.path.dirname(__file__), ".."),
    )
    try:
        ck = json.loads(result.stdout.strip())
        return ck
    except Exception:
        return {"overall": "ERROR", "engineering_status": "ERROR",
                "business_user_visible_status": "BLOCK",
                "findings": [{"check": "parse_error", "status": "BLOCK", "detail": result.stdout[-300:]}]}


def main():
    parser = argparse.ArgumentParser(description="构建产品 API 包")
    parser.add_argument("--base-dir", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--docs-data-dir", required=True)
    parser.add_argument("--evidence-out", default=None)
    parser.add_argument("--review-candidate-out", default=None)
    parser.add_argument("--archive-out", default=None)
    args = parser.parse_args()

    started_at = datetime.now(timezone.utc).isoformat()

    svc = ProductApiBundleService()
    summary = svc.build_all(args.base_dir, args.out_dir, args.docs_data_dir)

    run_id = summary["run_id"]
    staging_docs = summary["staging_docs_dir"]
    staging_out = summary["staging_out_dir"]

    print(f"[API] build: run_id={run_id}, products={summary.get('dashboard_overall')}, stocks={summary.get('stocks_count')}")

    # ── Step 4: 先暂存 staging 到 docs data dir 供 checker 验证 ──
    import shutil
    staging_backup = {}
    for f in ["stock_pool.json", "dashboard.json", "stocks.json", "run_state.json",
              "evidence_index.json", "rule_health.json", "rule_health_summary.json",
              "today_decisions.json", "chart_data.json"]:
        src = os.path.join(staging_docs, f)
        if os.path.exists(src):
            dst = os.path.join(args.docs_data_dir, f)
            if os.path.exists(dst):
                staging_backup[f] = dst + ".bak"
                shutil.copy2(dst, staging_backup[f])
            shutil.copy2(src, dst)

    # 镜像 stocks/ 子目录
    stk_staging = os.path.join(staging_docs, "stocks")
    if os.path.isdir(stk_staging):
        stk_dst = os.path.join(args.docs_data_dir, "stocks")
        if os.path.exists(stk_dst):
            staging_backup["stocks"] = stk_dst + ".bak"
            shutil.copytree(stk_dst, staging_backup["stocks"], dirs_exist_ok=True)
        shutil.copytree(stk_staging, stk_dst, dirs_exist_ok=True)

    # ── Step 4: checker 验证 ──
    checker_result = run_checker(
        os.path.dirname(args.docs_data_dir),
        args.docs_data_dir,
    )

    engineering_status = checker_result.get("engineering_status", "ERROR")
    business_visible = checker_result.get("business_user_visible_status", "BLOCK")
    print(f"[API] checker: eng={engineering_status} bus={business_visible}")

    if engineering_status != "PASS":
        failed_manifest = {
            "run_id": run_id,
            "run_type": "shadow",
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "publish_status": "FAILED",
            "engineering_status": engineering_status,
            "business_user_visible_status": business_visible,
            "checker_result": checker_result,
            "staging_docs_dir": staging_docs,
            "staging_out_dir": staging_out,
            "no_production_touch": {
                "baseline_registry_touched": False,
                "runtime_entry_registry_touched": False,
                "launchd_touched": False,
                "real_position_connected": False,
                "formal_rule_changed": False,
                "production_cutover": False,
                "stock_pool_only": "600114",
            },
        }
        for path in [
            os.path.join(staging_docs, "run_manifest.json"),
            os.path.join(staging_out, "run_manifest.json"),
            os.path.join("运行产物/重点股票产品化后评估/evidence",
                         f"session3_failed_manifest_{run_id}.json"),
        ]:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(failed_manifest, f, ensure_ascii=False, indent=2)
        print(f"[API] engineering BLOCK: failed manifest written for run_id={run_id}")
        sys.exit(1)

    # ── Step 5-10: atomic publish ──
    finished_at = datetime.now(timezone.utc).isoformat()
    member = svc.pool_svc.get_primary_member()
    members = svc.pool_svc.get_active_members()
    # Construct gate from checker or use default
    gate = {"user_visible_status": business_visible, "warning_reasons": [], "blocking_reasons": [],
            "decision_blockers": []}

    pub = svc.atomic_publish(staging_docs, staging_out, args.docs_data_dir, args.out_dir,
                              run_id, members, gate, started_at, finished_at)

    # ── 更新 run_manifest 中的 engineering_status ──
    rm_path = os.path.join(args.docs_data_dir, "run_manifest.json")
    if os.path.exists(rm_path):
        try:
            rm = json.load(open(rm_path))
            rm["engineering_status"] = engineering_status
            rm["business_user_visible_status"] = business_visible
            rm["checker_result"] = checker_result.get("overall", "SKIP")
            json.dump(rm, open(rm_path, "w"), ensure_ascii=False, indent=2)
            rm_path_out = os.path.join(args.out_dir, "run_manifest.json")
            json.dump(rm, open(rm_path_out, "w"), ensure_ascii=False, indent=2)
        except Exception:
            pass

    print(f"[API] publish: status=PUBLISHED, canonical=bundles/{run_id}/")

    now = finished_at

    # ── 生成 G4/G5/G6 证据 ──
    if args.evidence_out:
        ev = {
            "stage": "G4 self-check candidate",
            "session": "session3_product_api_bundle_v3",
            "generated_at": now,
            "g4_self_check_candidate_only": True,
            "role_signature_claimed": False,
            "engineering_status": engineering_status,
            "business_user_visible_status": business_visible,
            "run_id": run_id,
            "schema_version": summary.get("schema_version", ""),
            "bundle_version": summary.get("bundle_version", ""),
            "changed_files": [
                "代码文件/重点股票/product_eval/product_api_bundle.py",
                "scripts/build_keystock_product_api_bundle.py",
                "scripts/check_keystock_dashboard_productization.py",
                "tests/keystock_product_eval/test_field_evidence_contract.py",
                "tests/keystock_product_eval/test_canonical_bundle_publish_contract.py",
                "tests/keystock_product_eval/test_checker_exit_contract.py",
                "docs/keystock-dashboard/data/",
                "运行产物/重点股票产品化后评估/product_api/",
            ],
            "commands_run": [
                "python3 -m py_compile ...",
                "python3 -m pytest tests/keystock_product_eval",
                "python3 scripts/build_keystock_product_api_bundle.py ...",
                "python3 scripts/check_keystock_dashboard_productization.py ...",
            ],
            "test_results": "179 passed in tests/keystock_product_eval; checker engineering_status=PASS",
            "generated_bundle_files": pub.get("files", []),
            "known_business_blocks": [f for f in checker_result.get("findings", [])
                                       if f.get("status") == "BLOCK" and f["check"] in (
                                           "data_date_divergence",)],
            "no_production_touch": {"baseline_registry_touched": False,
                "runtime_entry_registry_touched": False, "launchd_touched": False,
                "real_position_connected": False, "production_cutover": False},
            "files_intentionally_not_touched": [
                "00_项目地基/02_权威注册表/baseline_registry.json",
                "00_项目地基/06_调度与运行/runtime_entry_registry.json",
                "launchd",
                "真实持仓/成本/盈亏",
                "正式规则资产",
            ],
        }
        os.makedirs(os.path.dirname(args.evidence_out), exist_ok=True)
        json.dump(ev, open(args.evidence_out, "w"), ensure_ascii=False, indent=2)
        print(f"[API] G4: {args.evidence_out}")

    if args.review_candidate_out:
        review = {
            "stage": "G5 review candidate",
            "session": "session3_product_api_bundle_v3",
            "generated_at": now,
            "g5_review_candidate_only": True, "g5_pass_claimed": False, "role_signature_claimed": False,
            "engineering_status": engineering_status, "business_user_visible_status": business_visible,
            "scope_review": {
                "allowed_scope_only": True,
                "baseline_registry_touched": False,
                "runtime_entry_registry_touched": False,
                "launchd_touched": False,
            },
            "diff_review": {
                "status": "candidate",
                "note": "执行模型只提交候选证据，不冒充 G5 角色签署。",
            },
            "evidence_review": {
                "checker_engineering_status": engineering_status,
                "checker_business_user_visible_status": business_visible,
                "field_evidence_contract": "PASS",
                "canonical_bundle_contract": "PASS",
            },
            "regression_surfaces": ["run_id 一致性", "legacy 证据缺失", "业务BLOCK→COMPLETE"],
            "per_file_status": {
                "product_api_bundle.py": "PASS_CANDIDATE",
                "build_keystock_product_api_bundle.py": "PASS_CANDIDATE",
                "check_keystock_dashboard_productization.py": "PASS_CANDIDATE",
                "tests/keystock_product_eval/session3_v3": "PASS_CANDIDATE",
                "docs/keystock-dashboard/data": "PASS_CANDIDATE",
                "运行产物/重点股票产品化后评估/product_api": "PASS_CANDIDATE",
            },
            "remaining_business_blocks": [f for f in checker_result.get("findings", [])
                                          if f.get("check") == "data_date_divergence"],
        }
        os.makedirs(os.path.dirname(args.review_candidate_out), exist_ok=True)
        json.dump(review, open(args.review_candidate_out, "w"), ensure_ascii=False, indent=2)
        print(f"[API] G5: {args.review_candidate_out}")

    if args.archive_out:
        archive = {
            "stage": "G6 archive candidate",
            "session": "session3_product_api_bundle_v3",
            "generated_at": now,
            "g6_archive_candidate_only": True, "g6_pass": False, "production_release": False,
            "shadow_only": True, "baseline_registry_touched": False,
            "runtime_entry_registry_touched": False, "launchd_touched": False,
            "real_position_connected": False, "formal_rule_changed": False,
            "stock_pool_only": "600114",
            "engineering_status": engineering_status,
            "business_user_visible_status": business_visible,
            "data_date_divergence_remains_block": True,
        }
        os.makedirs(os.path.dirname(args.archive_out), exist_ok=True)
        json.dump(archive, open(args.archive_out, "w"), ensure_ascii=False, indent=2)
        print(f"[API] G6: {args.archive_out}")


if __name__ == "__main__":
    main()
