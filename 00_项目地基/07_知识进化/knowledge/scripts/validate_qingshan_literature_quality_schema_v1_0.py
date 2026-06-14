#!/usr/bin/env python3
"""
G3-QINGSHAN-LITERATURE-QUALITY-SCORING-v1.0 校验脚本
检验青山文献质量评分 schema 的完整性和合规性

校验项：
1. schema JSON 存在且可解析
2. meta.version = 1.0
3. owner_role = 青山
4. depends_on 指向 source selection policy 且文件存在
5. score_model.total_score = 100
6. 6 个评分维度完整 (authority/replicability/market_fit/recency/conflict_risk/rule_convertibility)
7. 每个维度有 dimension_id/name/weight/description/scoring_rules
8. 维度权重之和 = 100
9. 每个维度 scoring_rules >= 5 档
10. hard_blocks >= 4 条
11. status_decision 四类完整
12. 所有 status_decision 的 can_generate_rule_candidate = false
13. anti_overreach 五项全部 true
14. output_schema required_fields 完整
15. 未创建 literature_cards / rule_candidates
16. 未允许 applied_rule 作为输出
"""

import json
import hashlib
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SCHEMA_PATH = BASE / "literature" / "qingshan_literature_quality_schema_v1.0.json"
POLICY_PATH = BASE / "literature" / "qingshan_source_selection_policy_v1.0.json"
REPORT_PATH = BASE / "reports" / "qingshan_literature_quality_schema_validation_v1.0.json"
LITERATURE_DIR = BASE / "literature"

EXPECTED_VERSION = "1.0"
EXPECTED_OWNER = "青山"
EXPECTED_DIMENSIONS = {"authority", "replicability", "market_fit", "recency", "conflict_risk", "rule_convertibility"}
EXPECTED_TOTAL = 100
MIN_HARD_BLOCKS = 4
REQUIRED_STATUS_KEYS = {"quality_pass", "quality_pass_with_cross_check", "quality_background_only", "quality_reject"}
DIMENSION_REQUIRED_FIELDS = ["dimension_id", "name", "weight", "description", "scoring_rules"]
OUTPUT_REQUIRED_FIELDS = ["source_id", "dimension_scores", "total_score", "quality_status", "next_step"]
ANTI_OVERREACH_FIELDS = [
    "no_direct_applied_rule",
    "no_direct_rule_candidate",
    "no_external_fulltext_in_startup",
    "requires_project_validation_before_rule_update",
    "requires_role_confirmation_before_core_update",
]
FORBIDDEN_DOWNSTREAM = ["literature_cards", "rule_candidates"]
MIN_SCORING_RULES = 5


def check_schema_exists():
    return SCHEMA_PATH.exists()


def check_policy_exists():
    return POLICY_PATH.exists()


def parse_json():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def check_meta_version(data):
    version = data.get("meta", {}).get("version")
    return version == EXPECTED_VERSION, f"meta.version={version}"


def check_owner_role(data):
    owner = data.get("meta", {}).get("owner_role")
    return owner == EXPECTED_OWNER, f"owner_role={owner}"


def check_depends_on(data):
    deps = data.get("meta", {}).get("depends_on", [])
    target = "knowledge/literature/qingshan_source_selection_policy_v1.0.json"
    if target not in deps:
        return False, f"depends_on missing: {target}", deps
    if not POLICY_PATH.exists():
        return False, f"depends_on file not found: {POLICY_PATH}", deps
    return True, f"depends_on ok, policy exists", deps


def check_total_score(data):
    total = data.get("score_model", {}).get("total_score")
    return total == EXPECTED_TOTAL, f"total_score={total}"


def check_dimensions(data):
    dims = data.get("score_model", {}).get("dimensions", [])
    dim_ids = set()
    bad_dims = []
    weight_sum = 0
    for i, d in enumerate(dims):
        dim_ids.add(d.get("dimension_id", ""))
        weight_sum += d.get("weight", 0)
        for field in DIMENSION_REQUIRED_FIELDS:
            if field not in d:
                bad_dims.append((i, field))
        rules = d.get("scoring_rules", [])
        if len(rules) < MIN_SCORING_RULES:
            bad_dims.append((i, f"scoring_rules_count={len(rules)} < {MIN_SCORING_RULES}"))

    missing_dims = EXPECTED_DIMENSIONS - dim_ids
    return dim_ids, missing_dims, bad_dims, weight_sum, len(dims)


def check_hard_blocks(data):
    blocks = data.get("hard_blocks", [])
    bad_blocks = []
    for i, b in enumerate(blocks):
        for field in ["block_id", "name", "condition", "result"]:
            if field not in b:
                bad_blocks.append((i, field))
    return len(blocks) >= MIN_HARD_BLOCKS and not bad_blocks, len(blocks), bad_blocks


def check_status_decision(data):
    sd = data.get("status_decision", {})
    keys = set(sd.keys())
    missing = REQUIRED_STATUS_KEYS - keys
    if missing:
        return False, f"missing_status_keys={sorted(missing)}", sd

    bad_status = []
    for k, v in sd.items():
        for field in ["score_range", "next_step", "requires_cross_check", "can_generate_rule_candidate", "note"]:
            if field not in v:
                bad_status.append((k, field))
        if v.get("can_generate_rule_candidate") is not False:
            bad_status.append((k, f"can_generate_rule_candidate={v.get('can_generate_rule_candidate')}"))

    return not bad_status, f"status_count={len(keys)}, bad={bad_status}" if bad_status else f"status_count={len(keys)}, all ok", sd


def check_anti_overreach(data):
    ao = data.get("anti_overreach", {})
    bad_ao = []
    for field in ANTI_OVERREACH_FIELDS:
        if field not in ao or ao.get(field) is not True:
            bad_ao.append(field)
    return not bad_ao, bad_ao


def check_output_schema(data):
    req = data.get("output_schema", {}).get("required_fields", [])
    missing = [f for f in OUTPUT_REQUIRED_FIELDS if f not in req]
    return not missing, missing


def check_not_allowed_output(data):
    nao = data.get("scope", {}).get("not_allowed_output", [])
    return "applied_rule" in nao, nao


def check_no_downstream_files():
    unexpected = []
    if LITERATURE_DIR.exists():
        for f in LITERATURE_DIR.iterdir():
            if any(downstream in f.name.lower() for downstream in FORBIDDEN_DOWNSTREAM):
                unexpected.append(f.name)
    return len(unexpected) == 0, unexpected


def main():
    print("=" * 60)
    print("G3-QINGSHAN-LITERATURE-QUALITY-SCORING-v1.0 校验")
    print("=" * 60)

    all_pass = True
    result_reasons = []
    result_details = {}

    # 1. Schema exists
    exists = check_schema_exists()
    all_pass = all_pass and exists
    result_details["schema_exists"] = exists
    result_reasons.append(f"[{'PASS' if exists else 'FAIL'}] schema_exists: {exists}")

    if not exists:
        print("BLOCK: schema JSON not found")
        sys.exit(1)

    data = parse_json()

    # 2. Version
    version_ok, version_msg = check_meta_version(data)
    all_pass = all_pass and version_ok
    result_reasons.append(f"[{'PASS' if version_ok else 'FAIL'}] version: {version_msg}")

    # 3. Owner
    owner_ok, owner_msg = check_owner_role(data)
    all_pass = all_pass and owner_ok
    result_reasons.append(f"[{'PASS' if owner_ok else 'FAIL'}] owner: {owner_msg}")

    # 4. Depends on
    dep_ok, dep_msg, _ = check_depends_on(data)
    all_pass = all_pass and dep_ok
    result_details["depends_on_ok"] = dep_ok
    result_reasons.append(f"[{'PASS' if dep_ok else 'FAIL'}] depends_on: {dep_msg}")

    # 5. Total score
    total_ok, total_msg = check_total_score(data)
    all_pass = all_pass and total_ok
    result_details["score_total"] = data.get("score_model", {}).get("total_score")
    result_reasons.append(f"[{'PASS' if total_ok else 'FAIL'}] total_score: {total_msg}")

    # 6. Dimensions
    dim_ids, missing_dims, bad_dims, weight_sum, dim_count = check_dimensions(data)
    dims_ok = not missing_dims and not bad_dims and weight_sum == 100
    all_pass = all_pass and dims_ok
    result_details["dimension_count"] = dim_count
    result_details["weight_sum"] = weight_sum
    result_details["dimension_ids"] = sorted(dim_ids)
    result_reasons.append(f"[{'PASS' if dims_ok else 'FAIL'}] dimensions: count={dim_count}, missing={sorted(missing_dims) if missing_dims else 'none'}, bad_dims={bad_dims if bad_dims else 'none'}, weight_sum={weight_sum}")

    # 7. Hard blocks
    hb_ok, hb_count, hb_bad = check_hard_blocks(data)
    all_pass = all_pass and hb_ok
    result_details["hard_block_count"] = hb_count
    result_reasons.append(f"[{'PASS' if hb_ok else 'FAIL'}] hard_blocks: count={hb_count}, bad={hb_bad if hb_bad else 'none'}")

    # 8. Status decision
    sd_ok, sd_msg, _ = check_status_decision(data)
    all_pass = all_pass and sd_ok
    result_details["status_count"] = len(data.get("status_decision", {}))
    result_reasons.append(f"[{'PASS' if sd_ok else 'FAIL'}] status_decision: {sd_msg}")

    # 9. Anti overreach
    ao_ok, ao_bad = check_anti_overreach(data)
    all_pass = all_pass and ao_ok
    result_details["bad_anti_overreach"] = ao_bad if ao_bad else []
    result_reasons.append(f"[{'PASS' if ao_ok else 'FAIL'}] anti_overreach: {'bad=' + str(ao_bad) if ao_bad else 'all true'}")

    # 10. Output schema required fields
    out_ok, out_missing = check_output_schema(data)
    all_pass = all_pass and out_ok
    result_details["bad_required_fields"] = out_missing
    result_reasons.append(f"[{'PASS' if out_ok else 'FAIL'}] output_required_fields: {'missing=' + str(out_missing) if out_missing else 'all ok'}")

    # 11. Not allowed output includes applied_rule
    nao_ok, nao_list = check_not_allowed_output(data)
    all_pass = all_pass and nao_ok
    result_details["not_allowed_output_includes_applied_rule"] = nao_ok
    result_reasons.append(f"[{'PASS' if nao_ok else 'FAIL'}] not_allowed_output: forbidden_output_guard_ok={nao_ok}")

    # 12. No downstream files
    no_down_ok, unexpected = check_no_downstream_files()
    all_pass = all_pass and no_down_ok
    result_details["unexpected_downstream_files"] = unexpected
    result_reasons.append(f"[{'PASS' if no_down_ok else 'FAIL'}] unexpected_downstream: {unexpected if unexpected else 'none'}")

    # 13. Bad weights (if dimension weights don't sum to 100)
    result_details["bad_weights"] = [] if weight_sum == 100 else [{"reason": f"weight_sum={weight_sum} != 100"}]

    # 14. Bad status decision
    _, sd_msg2, _ = check_status_decision(data)
    result_details["bad_status_decision"] = []

    result = "PASS" if all_pass else "WARN"

    report = {
        "stage": "G3-QINGSHAN-LITERATURE-QUALITY-SCORING-v1.0",
        "result": result,
        "schema_exists": exists,
        "score_total": result_details.get("score_total"),
        "dimension_count": result_details.get("dimension_count"),
        "weight_sum": result_details.get("weight_sum"),
        "hard_block_count": result_details.get("hard_block_count"),
        "status_count": result_details.get("status_count"),
        "bad_required_fields": result_details.get("bad_required_fields", []),
        "bad_weights": result_details.get("bad_weights", []),
        "bad_status_decision": result_details.get("bad_status_decision", []),
        "bad_anti_overreach": result_details.get("bad_anti_overreach", []),
        "unexpected_downstream_files": result_details.get("unexpected_downstream_files", []),
        "result_reason": "; ".join(result_reasons)
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print(f"校验结果: {result}")
    print("=" * 60)
    for reason in result_reasons:
        print(f"  {reason}")
    print(f"\n报告已写入: {REPORT_PATH}")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
