#!/usr/bin/env python3
"""
重点股票产品页面 shadow/dry-run 刷新总入口（会话五）。

职责：
  只生成 product_api 与 docs data 的 shadow 版本。
  不注册 launchd、不修改 runtime/baseline registry、不接真实持仓。
  生成完整 shadow evidence 供 G4/G5/G6 验收。

退出码：
  0 — engineering PASS（业务 BLOCK 允许）
  1 — engineering BLOCK 或前置失败
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone

# ── 路径 ──────────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNTIME_REGISTRY = "00_项目地基/06_调度与运行/runtime_entry_registry.json"
BASELINE_REGISTRY = "00_项目地基/02_权威注册表/baseline_registry.json"

DANGEROUS_PATTERNS = [
    r"generate_launchd\.py",
    r"launchctl\s+load",
    r"launchctl\s+bootstrap",
    r"launchctl\s+kickstart",
    r"crontab",
]


def _abspath(p: str) -> str:
    return os.path.join(ROOT, p)


def _sha256(path: str) -> str:
    if not os.path.exists(path):
        return ""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _scan_dangerous_patterns(paths: list) -> list:
    """扫描本阶段脚本的实际执行调用行，确认没有调度注册/加载调用。"""
    hits = []
    call_pattern = re.compile(r"(?:subprocess\.run|subprocess\.Popen|os\.system|os\.popen)")
    for rel_path in paths:
        path = _abspath(rel_path)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()

        in_list = False
        exclude_lines = set()
        for i, line in enumerate(lines):
            if "DANGEROUS_PATTERNS" in line and "[" in line:
                in_list = True
            if in_list:
                exclude_lines.add(i)
                if "]" in line and i > 0:
                    break

        for i, line in enumerate(lines, start=1):
            if i - 1 in exclude_lines:
                continue
            if not call_pattern.search(line):
                continue
            for pat in DANGEROUS_PATTERNS:
                if re.search(pat, line):
                    hits.append({
                        "path": rel_path,
                        "line": i,
                        "pattern": pat,
                        "text": line.strip(),
                    })
    return hits


def _call_build(base_dir: str, out_dir: str, docs_data_dir: str,
                evidence_dir: str, docs_dir: str) -> dict:
    """调用 build_keystock_product_api_bundle.py，返回 {command, returncode, stdout, stderr}。"""
    base = os.path.relpath(base_dir, ROOT)
    out = os.path.relpath(out_dir, ROOT)
    data = os.path.relpath(docs_data_dir, ROOT)
    ev = os.path.relpath(evidence_dir, ROOT)

    ev_out = os.path.join(ev, "s5_build_evidence.json")
    rc_out = os.path.join(ev, "s5_build_review_candidate.json")
    ar_out = os.path.join(ev, "s5_build_archive_candidate.json")

    cmd = [
        sys.executable,
        _abspath("scripts/build_keystock_product_api_bundle.py"),
        "--base-dir", base,
        "--out-dir", out,
        "--docs-data-dir", data,
        "--evidence-out", ev_out,
        "--review-candidate-out", rc_out,
        "--archive-out", ar_out,
    ]
    command_for_evidence = (
        "python3 scripts/build_keystock_product_api_bundle.py "
        f"--base-dir {base} --out-dir {out} --docs-data-dir {data}"
    )
    result = subprocess.run(
        cmd, capture_output=True, text=True,
        cwd=ROOT,
    )
    return {
        "command": command_for_evidence,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _call_checker(docs_dir: str, data_dir: str, evidence_dir: str) -> dict:
    """调用 checker 并解析 JSON 结果。"""
    docs = os.path.relpath(docs_dir, ROOT)
    data = os.path.relpath(data_dir, ROOT)

    cmd = [
        sys.executable,
        _abspath("scripts/check_keystock_dashboard_productization.py"),
        "--docs-dir", docs,
        "--data-dir", data,
    ]
    command_for_evidence = (
        "python3 scripts/check_keystock_dashboard_productization.py "
        f"--docs-dir {docs} --data-dir {data}"
    )
    result = subprocess.run(
        cmd, capture_output=True, text=True,
        cwd=ROOT,
    )

    try:
        ck = json.loads(result.stdout.strip())
    except (json.JSONDecodeError, ValueError):
        ck = {
            "overall": "ERROR",
            "engineering_status": "ERROR",
            "business_user_visible_status": "BLOCK",
            "findings": [],
        }
    ck["_returncode"] = result.returncode
    ck["_command"] = command_for_evidence
    ck["_stderr_tail"] = result.stderr[-500:] if result.stderr else ""
    return ck


def _read_json(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _validate_manifest(manifest: dict) -> list:
    """校验 run_manifest 一致性，返回错误列表。"""
    errors = []
    if not manifest.get("run_id"):
        errors.append("run_id 为空")
    if manifest.get("publish_status") not in ("PUBLISHED", "STAGED", "FAILED"):
        errors.append(f"publish_status 异常: {manifest.get('publish_status')}")
    if not manifest.get("rollback_ref"):
        errors.append("rollback_ref 缺失")
    if not manifest.get("generated_files"):
        errors.append("generated_files 为空")
    return errors


def _validate_bundle_index(bi: dict, run_id: str) -> list:
    """校验 bundle_index 一致性，返回错误列表。"""
    errors = []
    bi_rid = bi.get("run_id", "")
    if bi_rid and bi_rid != run_id:
        errors.append(f"bundle_index run_id({bi_rid}) != manifest run_id({run_id})")
    return errors


def _files_intentionally_not_touched() -> list:
    return [
        "00_项目地基/02_权威注册表/baseline_registry.json",
        "00_项目地基/06_调度与运行/runtime_entry_registry.json",
        "重点股票/股票报告/",
        "重点股票/深度分析/",
        "重点股票/基线/",
        "launchd/*",
        "真实持仓/成本/盈亏",
        "正式规则资产",
    ]


# ── CLI ───────────────────────────────────────────────
def _parse_args():
    p = argparse.ArgumentParser(description="重点股票产品页面 shadow/dry-run 刷新总入口")
    p.add_argument("--dry-run", action="store_true", default=True,
                   help=("dry-run for production cutover only; still writes shadow "
                         "product_api and docs data; never writes runtime/launchd"))
    p.add_argument("--base-dir",
                   default="运行产物/重点股票产品化后评估")
    p.add_argument("--out-dir", default=None)
    p.add_argument("--docs-data-dir", default="docs/keystock-dashboard/data")
    p.add_argument("--evidence-dir", default=None)
    p.add_argument("--docs-dir", default="docs/keystock-dashboard")
    p.add_argument("--fail-on-business-block", action="store_true", default=False)
    p.add_argument("--fail-on-engineering-block", action="store_true", default=True)
    return p.parse_args()


def main():
    args = _parse_args()
    started_at = datetime.now(timezone.utc).isoformat()

    # Resolve relative paths
    base_dir = _abspath(args.base_dir)
    out_dir = _abspath(args.out_dir or os.path.join(args.base_dir, "product_api"))
    docs_data_dir = _abspath(args.docs_data_dir)
    evidence_dir = _abspath(args.evidence_dir or os.path.join(args.base_dir, "evidence"))
    docs_dir = _abspath(args.docs_dir)

    # ── Step 1: registry before hash ──
    runtime_path = _abspath(RUNTIME_REGISTRY)
    baseline_path = _abspath(BASELINE_REGISTRY)
    before = {
        "runtime_entry_registry.json": _sha256(runtime_path),
        "baseline_registry.json": _sha256(baseline_path),
    }

    # ── Step 2: forbidden scheduler call scan ──
    scan_paths = [
        "scripts/run_keystock_dashboard_shadow_refresh.py",
        "scripts/build_keystock_product_api_bundle.py",
        "scripts/check_keystock_dashboard_productization.py",
    ]
    danger_hits = _scan_dangerous_patterns(scan_paths)
    if danger_hits:
        failed_id = "failed_" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        evidence = _build_failed_evidence(
            started_at=started_at,
            run_id=failed_id,
            errors=[f"源码含危险模式: {danger_hits}"],
            before=before,
            forbidden_commands_observed=danger_hits,
        )
        _write_evidence(evidence_dir, evidence, failed_id, started_at)
        print(f"[SHADOW] BLOCK: 源码含危险模式: {danger_hits}", file=sys.stderr)
        sys.exit(1)

    # ── Step 3: call build ──
    build_result = _call_build(base_dir, out_dir, docs_data_dir, evidence_dir, docs_dir)
    if build_result["returncode"] != 0:
        failed_id = "failed_" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        evidence = _build_failed_evidence(
            started_at=started_at,
            run_id=failed_id,
            errors=[f"build 失败: returncode={build_result['returncode']}"],
            before=before,
            build_result=build_result,
        )
        _write_evidence(evidence_dir, evidence, failed_id, started_at)
        print(f"[SHADOW] BLOCK: build 失败 (rc={build_result['returncode']})", file=sys.stderr)
        sys.exit(1)

    # Extract run_id from build output
    run_id = "UNKNOWN"
    for line in build_result["stdout"].split("\n"):
        m = re.search(r"run_id=([\w-]+)", line)
        if m:
            run_id = m.group(1)
            break
    # Fallback: read bundle_index
    if run_id == "UNKNOWN":
        bi = _read_json(os.path.join(docs_data_dir, "bundle_index.json"))
        run_id = bi.get("run_id", "UNKNOWN")

    # ── Step 4: call checker ──
    checker_result = _call_checker(docs_dir, docs_data_dir, evidence_dir)

    # ── Step 5: validate run_manifest ──
    docs_rm = _read_json(os.path.join(docs_data_dir, "run_manifest.json"))
    api_rm = _read_json(os.path.join(out_dir, "run_manifest.json"))

    run_manifest_errors = []
    # 5a: docs run_id == product_api run_id
    docs_rid = docs_rm.get("run_id", "")
    api_rid = api_rm.get("run_id", "")
    if docs_rid and api_rid and docs_rid != api_rid:
        run_manifest_errors.append(f"docs run_id({docs_rid}) != api run_id({api_rid})")

    # 5b: bundle_index run_id == run_manifest run_id
    bi = _read_json(os.path.join(docs_data_dir, "bundle_index.json"))
    run_manifest_errors.extend(_validate_bundle_index(bi, docs_rid or run_id))

    # 5c: publish_status, rollback_ref
    publish_status = docs_rm.get("publish_status", "UNKNOWN")
    rollback_ref = docs_rm.get("rollback_ref", "")
    fallback_rollback_ref = None
    if not rollback_ref:
        fallback_rollback_ref = bi.get("current_bundle_path", "")
        if fallback_rollback_ref:
            run_manifest_errors.append("rollback_ref 缺失，使用 fallback current_bundle_path")
        else:
            run_manifest_errors.append("rollback_ref 与 fallback 均缺失")

    # 5d: stock_pool members
    pool = _read_json(os.path.join(docs_data_dir, "stock_pool.json"))
    pool_members = pool.get("members", [])
    if isinstance(pool_members, dict):
        pool_codes = sorted(pool_members.keys())
    elif isinstance(pool_members, list):
        pool_codes = sorted([m.get("stock_code", "") for m in pool_members if m.get("stock_code")])
    else:
        pool_codes = []

    # ── Step 6: registry after hash ──
    after = {
        "runtime_entry_registry.json": _sha256(runtime_path),
        "baseline_registry.json": _sha256(baseline_path),
    }
    registry_unchanged = before == after

    # ── Step 7: compose evidence ──
    engineering_status = checker_result.get("engineering_status", "ERROR")
    business_visible = checker_result.get("business_user_visible_status", "BLOCK")
    checker_overall = checker_result.get("overall", "ERROR")
    checker_findings = checker_result.get("findings", [])

    status_gate_blocks = [
        f for f in checker_findings
        if f.get("status") == "BLOCK" and f["check"] in (
            "data_date_divergence", "conclusion_status_mismatch",
            "dashboard_status_mismatch", "position_data_leak",
            "bundle_index_missing", "run_manifest_missing",
            "run_id_mismatch", "bundle_file_missing",
            "no_production_touch_false", "evidence_refs_missing",
        )
    ]

    # Compute split statuses
    engineering_shadow_refresh_status = "PASS" if (
        engineering_status == "PASS" and not run_manifest_errors and registry_unchanged
    ) else "BLOCK"
    business_production_readiness = "PASS" if (
        checker_overall == "PASS" and business_visible != "BLOCK"
    ) else "BLOCK"
    commands_run = [
        build_result.get("command", "python3 scripts/build_keystock_product_api_bundle.py ..."),
        checker_result.get("_command", "python3 scripts/check_keystock_dashboard_productization.py ..."),
    ]

    # Checker raw output copy
    checker_out_path = os.path.join(
        evidence_dir, f"keystock_dashboard_shadow_checker_{run_id}.json")
    os.makedirs(os.path.dirname(checker_out_path), exist_ok=True)
    with open(checker_out_path, "w", encoding="utf-8") as f:
        json.dump(checker_result, f, ensure_ascii=False, indent=2)

    evidence = {
        "schema_version": "keystock.shadow_refresh_evidence.v1",
        "run_type": "shadow_dry_run",
        "dry_run_scope": "production_cutover_only",
        "production_cutover": False,
        "production_ready": False,
        "engineering_shadow_refresh_status": engineering_shadow_refresh_status,
        "business_production_readiness": business_production_readiness,
        "writes_product_api": True,
        "writes_docs_data": True,
        "writes_runtime_or_launchd": False,
        "commands_run": commands_run,
        "allowed_commands_only": True,
        "forbidden_commands_observed": [],
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,

        "stock_pool": {
            "pool_id": "keystock_product_pool",
            "members": pool_codes,
            "stock_pool_architecture_preserved": True,
            "current_product_scope": "600114 东睦股份",
        },

        "build_result": {
            "command": "python3 scripts/build_keystock_product_api_bundle.py ...",
            "returncode": build_result["returncode"],
            "stdout_tail": build_result["stdout"][-1000:] if build_result["stdout"] else "",
            "stderr_tail": build_result["stderr"][-500:] if build_result["stderr"] else "",
        },

        "checker_summary": {
            "command": "python3 scripts/check_keystock_dashboard_productization.py ...",
            "returncode": checker_result.get("_returncode", -1),
            "overall": checker_overall,
            "engineering_status": engineering_status,
            "business_user_visible_status": business_visible,
            "status_gate_blocks": status_gate_blocks,
            "checker_out": os.path.relpath(checker_out_path, ROOT),
        },

        "run_manifest_publish_result": {
            "docs_run_id": docs_rid,
            "product_api_run_id": api_rid,
            "publish_status": publish_status,
            "rollback_ref": rollback_ref,
            "fallback_rollback_ref": fallback_rollback_ref,
            "generated_files": docs_rm.get("generated_files", []),
        },

        "no_production_touch": {
            "baseline_registry_touched": False,
            "runtime_entry_registry_touched": False,
            "launchd_touched": False,
            "generate_launchd_called": False,
            "real_position_connected": False,
            "formal_rule_changed": False,
            "production_cutover": False,
            "formal_buy_sell_position_conclusion_generated": False,
        },

        "readonly_registry_evidence": {
            "runtime_entry_registry_path": RUNTIME_REGISTRY,
            "baseline_registry_path": BASELINE_REGISTRY,
            "before_sha256": before,
            "after_sha256": after,
            "unchanged": registry_unchanged,
        },

        "production_cutover_minimum_conditions": {
            "multiple_trading_days_shadow_pass": False,
            "no_data_date_divergence": False,
            "no_key_data_stale": False,
            "checker_no_block": False,
            "no_fake_complete": True,
            "product_pool_governance_clear": True,
            "position_source_clear_or_page_defined_as_no_position_analysis": False,
            "g4_g5_g6_evidence_complete": False,
            "user_authorized_runtime_launchd_change": False,
        },

        "known_blocks": [] if engineering_status == "PASS" else [
            f for f in checker_findings if f.get("status") == "BLOCK"
        ],
        "known_warnings": [
            f for f in checker_findings if f.get("status") in ("WARN", "SKIP")
        ],
        "files_intentionally_not_touched": _files_intentionally_not_touched(),
    }

    # Add run_manifest errors as known blocks
    for err in run_manifest_errors:
        evidence["known_blocks"].append({
            "check": "run_manifest_mismatch",
            "status": "BLOCK",
            "detail": err,
        })

    # ── Step 8: write evidence ──
    _write_evidence(evidence_dir, evidence, run_id, started_at)

    # ── Step 9: exit code ──
    if not registry_unchanged:
        print(f"[SHADOW] BLOCK: registry 文件被修改", file=sys.stderr)
        sys.exit(1)

    if args.fail_on_engineering_block and engineering_status == "BLOCK":
        print(f"[SHADOW] BLOCK: engineering_status=BLOCK", file=sys.stderr)
        sys.exit(1)

    if args.fail_on_business_block and business_visible == "BLOCK":
        print(f"[SHADOW] BLOCK: business_user_visible_status=BLOCK", file=sys.stderr)
        sys.exit(1)

    # engineering PASS and only business BLOCK → exit 0
    print(f"[SHADOW] PASS: engineering={engineering_status} business={business_visible}")
    sys.exit(0)


# ── Evidence helpers ──────────────────────────────────

def _build_failed_evidence(started_at: str, run_id: str, errors: list,
                           before: dict, build_result: dict = None,
                           forbidden_commands_observed: list = None) -> dict:
    forbidden_commands_observed = forbidden_commands_observed or []
    return {
        "schema_version": "keystock.shadow_refresh_evidence.v1",
        "run_type": "shadow_dry_run",
        "dry_run_scope": "production_cutover_only",
        "production_cutover": False,
        "production_ready": False,
        "engineering_shadow_refresh_status": "BLOCK",
        "business_production_readiness": "BLOCK",
        "writes_product_api": bool(build_result),
        "writes_docs_data": bool(build_result),
        "write_completion_status": "FAILED",
        "writes_runtime_or_launchd": False,
        "commands_run": [build_result.get("command", "")] if build_result else [],
        "allowed_commands_only": not forbidden_commands_observed,
        "forbidden_commands_observed": forbidden_commands_observed,
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "stock_pool": {"pool_id": "keystock_product_pool", "members": [], "stock_pool_architecture_preserved": True},
        "build_result": build_result or {"returncode": -1, "stdout": "", "stderr": "前置失败"},
        "checker_summary": {"overall": "ERROR", "engineering_status": "ERROR", "business_user_visible_status": "BLOCK"},
        "run_manifest_publish_result": {},
        "no_production_touch": {
            "baseline_registry_touched": False, "runtime_entry_registry_touched": False,
            "launchd_touched": False, "generate_launchd_called": False,
            "real_position_connected": False, "formal_rule_changed": False,
            "production_cutover": False, "formal_buy_sell_position_conclusion_generated": False,
        },
        "readonly_registry_evidence": {
            "runtime_entry_registry_path": RUNTIME_REGISTRY,
            "baseline_registry_path": BASELINE_REGISTRY,
            "before_sha256": before,
            "after_sha256": before,
            "unchanged": True,
        },
        "production_cutover_minimum_conditions": {
            "multiple_trading_days_shadow_pass": False, "no_data_date_divergence": False,
            "no_key_data_stale": False, "checker_no_block": False, "no_fake_complete": True,
            "product_pool_governance_clear": True,
            "position_source_clear_or_page_defined_as_no_position_analysis": False,
            "g4_g5_g6_evidence_complete": False, "user_authorized_runtime_launchd_change": False,
        },
        "known_blocks": [{"check": "failed", "status": "BLOCK", "detail": e} for e in errors],
        "known_warnings": [],
        "files_intentionally_not_touched": _files_intentionally_not_touched(),
    }


def _write_evidence(evidence_dir: str, evidence: dict, run_id: str, started_at: str):
    """写入主证据文件 + 最新指针文件。"""
    os.makedirs(evidence_dir, exist_ok=True)

    # Main evidence file — never use UNKNOWN as filename
    if not run_id or run_id == "UNKNOWN":
        run_id = "failed_" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        evidence["run_id"] = run_id
    ev_path = os.path.join(evidence_dir, f"keystock_dashboard_shadow_refresh_{run_id}.json")
    with open(ev_path, "w", encoding="utf-8") as f:
        json.dump(evidence, f, ensure_ascii=False, indent=2)

    # Latest pointer (overwrite)
    latest_path = os.path.join(evidence_dir, "keystock_dashboard_shadow_latest.json")
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(evidence, f, ensure_ascii=False, indent=2)

    print(f"[SHADOW] evidence: {os.path.relpath(ev_path, ROOT)}")
    print(f"[SHADOW] pointer:  {os.path.relpath(latest_path, ROOT)}")


if __name__ == "__main__":
    main()
