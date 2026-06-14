#!/usr/bin/env python3
"""
G3-QINGSHAN-SOURCE-SELECTION-v1.0 校验脚本
检验青山资料来源选择规则 JSON 的完整性和合规性

校验项：
1. JSON 可解析
2. meta.version = 1.0
3. owner_role = 青山
4. selection_principle 包含关键声明
5. source_classes 包含 S/A/B/C/D
6. must_have_gates >= 5
7. 每个 gate 有 gate_id/name/rule/block_if_missing
8. preferred_candidate_pool >= 8
9. 每个 source 有必填字段
10. 无 only_allowed / whitelist_only / exclusive=true
11. decision_output 完整
12. 未创建 literature_cards / rule_candidates
"""

import json
import hashlib
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
POLICY_PATH = BASE / "literature" / "qingshan_source_selection_policy_v1.0.json"
REPORT_PATH = BASE / "reports" / "qingshan_source_selection_validation_v1.0.json"
LITERATURE_DIR = BASE / "literature"

EXPECTED_VERSION = "1.0"
EXPECTED_OWNER = "青山"
EXPECTED_SOURCE_CLASSES = {"S", "A", "B", "C", "D"}
MIN_GATES = 5
MIN_PREFERRED = 8

PREFERRED_REQUIRED_FIELDS = [
    "source_id", "name", "class_hint", "source_type",
    "why_preferred", "allowed_use", "not_allowed_use", "not_exclusive"
]

PRINCIPLE_KEYWORDS = [
    ("来源准入规则优先于候选池", "来源准入规则优先于候选池"),
    ("候选池不是白名单", "候选池不是白名单"),
    ("外部资料不得进入启动上下文", "外部资料不得进入启动上下文"),
    ("禁止直接 applied", "禁止"),
    ("禁止直接 applied(direct_rule)", "applied"),
]

FORBIDDEN_KEYWORDS = ["only_allowed", "whitelist_only"]
FORBIDDEN_EXCLUSIVE_PATTERN = '"exclusive": true'  # 精确匹配,不误伤 not_exclusive

FORBIDDEN_DOWNSTREAM = ["literature_cards", "rule_candidates"]


def check_policy_exists():
    return POLICY_PATH.exists()


def parse_json():
    with open(POLICY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def check_meta_version(data):
    version = data.get("meta", {}).get("version")
    return version == EXPECTED_VERSION, f"meta.version={version}"


def check_owner_role(data):
    owner = data.get("meta", {}).get("owner_role")
    return owner == EXPECTED_OWNER, f"owner_role={owner}"


def check_selection_principle(data):
    sp = data.get("selection_principle", {})
    sp_text = json.dumps(sp, ensure_ascii=False)
    missing = []
    for label, keyword in PRINCIPLE_KEYWORDS:
        if keyword not in sp_text:
            missing.append(label)
    return len(missing) == 0, missing


def check_source_classes(data):
    classes = set(data.get("source_classes", {}).keys())
    missing = EXPECTED_SOURCE_CLASSES - classes
    return missing == EXPECTED_SOURCE_CLASSES, f"missing={missing}" if missing else f"all: {sorted(classes)}", bool(classes == EXPECTED_SOURCE_CLASSES)


def check_source_class_set(data):
    classes = set(data.get("source_classes", {}).keys())
    return bool(classes == EXPECTED_SOURCE_CLASSES), sorted(classes)


def check_gates(data):
    gates = data.get("must_have_gates", [])
    if len(gates) < MIN_GATES:
        return False, f"count={len(gates)} < {MIN_GATES}", gates

    bad_gates = []
    for i, g in enumerate(gates):
        for field in ["gate_id", "name", "rule", "block_if_missing"]:
            if field not in g or g[field] is None:
                bad_gates.append((i, field))

    if bad_gates:
        return False, f"bad_gates={bad_gates}", gates

    return True, f"count={len(gates)}", gates


def check_preferred_pool(data):
    items = data.get("preferred_candidate_pool", [])
    if len(items) < MIN_PREFERRED:
        return False, f"count={len(items)} < {MIN_PREFERRED}", items

    bad_fields = []
    for i, item in enumerate(items):
        for field in PREFERRED_REQUIRED_FIELDS:
            if field not in item:
                bad_fields.append((i, field))

    if bad_fields:
        return False, f"missing_fields={bad_fields}", items

    bad_exclusive = []
    for i, item in enumerate(items):
        if item.get("not_exclusive") is not True:
            bad_exclusive.append((i, item.get("source_id", "?"), f"not_exclusive={item.get('not_exclusive')}"))

    if bad_exclusive:
        return False, f"exclusive_items={bad_exclusive}", items

    return True, f"count={len(items)}, all not_exclusive=True", items


def check_no_forbidden_keywords(data):
    text = json.dumps(data, ensure_ascii=False)
    text_lower = text.lower()
    found = []
    # 检查 only_allowed 和 whitelist_only
    for kw in FORBIDDEN_KEYWORDS:
        if kw.lower() in text_lower:
            found.append(kw)
    # 精确检查 "exclusive": true (不误伤 not_exclusive)
    if FORBIDDEN_EXCLUSIVE_PATTERN in text_lower:
        found.append("exclusive_true")
    return len(found) == 0, found


def check_decision_output(data):
    dec = data.get("decision_output", {})
    has_accepted = "accepted_status" in dec and len(dec["accepted_status"]) > 0
    has_blocked = "blocked_status" in dec and len(dec["blocked_status"]) > 0
    has_next = "next_required_stage" in dec and isinstance(dec["next_required_stage"], str) and len(dec["next_required_stage"]) > 0
    return has_accepted and has_blocked and has_next, {
        "accepted_status": dec.get("accepted_status", []),
        "blocked_status": dec.get("blocked_status", []),
        "next_required_stage": dec.get("next_required_stage", "")
    }


def check_no_downstream_files():
    """检查是否意外创建了 literature_cards 或 rule_candidates 文件"""
    unexpected = []
    if LITERATURE_DIR.exists():
        for f in LITERATURE_DIR.iterdir():
            if any(downstream in f.name.lower() for downstream in FORBIDDEN_DOWNSTREAM):
                unexpected.append(f.name)
    return len(unexpected) == 0, unexpected


def main():
    print("=" * 60)
    print("G3-QINGSHAN-SOURCE-SELECTION-v1.0 校验")
    print("=" * 60)

    all_pass = True
    result_details = {}
    result_reasons = []

    # 1. Policy exists
    exists = check_policy_exists()
    all_pass = all_pass and exists
    result_details["policy_exists"] = exists
    result_reasons.append(f"[{'PASS' if exists else 'FAIL'}] policy_exists: {exists}")

    if not exists:
        print("BLOCK: policy JSON not found")
        sys.exit(1)

    data = parse_json()

    # 2. Version
    version_ok, version_msg = check_meta_version(data)
    all_pass = all_pass and version_ok
    result_details["version_ok"] = version_ok
    result_reasons.append(f"[{'PASS' if version_ok else 'FAIL'}] version: {version_msg}")

    # 3. Owner
    owner_ok, owner_msg = check_owner_role(data)
    all_pass = all_pass and owner_ok
    result_details["owner_ok"] = owner_ok
    result_reasons.append(f"[{'PASS' if owner_ok else 'FAIL'}] owner: {owner_msg}")

    # 4. Selection principle
    principle_ok, principle_missing = check_selection_principle(data)
    all_pass = all_pass and principle_ok
    result_details["principle_ok"] = principle_ok
    result_details["principle_missing"] = principle_missing if not principle_ok else []
    result_reasons.append(f"[{'PASS' if principle_ok else 'FAIL'}] selection_principle: {'missing=' + str(principle_missing) if not principle_ok else 'all ok'}")

    # 5. Source classes
    classes_ok, class_list = check_source_class_set(data)
    source_class_count = len(data.get("source_classes", {}))
    all_pass = all_pass and classes_ok
    result_details["source_classes_ok"] = classes_ok
    result_details["source_classes"] = class_list
    result_reasons.append(f"[{'PASS' if classes_ok else 'FAIL'}] source_classes: {class_list}")

    # 6. Gates
    gates_ok, gates_msg, gates = check_gates(data)
    gate_count = len(gates)
    all_pass = all_pass and gates_ok
    result_details["gates_ok"] = gates_ok
    result_details["gate_count"] = gate_count
    result_reasons.append(f"[{'PASS' if gates_ok else 'FAIL'}] must_have_gates: {gates_msg}")

    # 7. Preferred pool
    pool_ok, pool_msg, items = check_preferred_pool(data)
    preferred_candidate_count = len(items)
    all_pass = all_pass and pool_ok
    result_details["preferred_ok"] = pool_ok
    result_details["preferred_count"] = preferred_candidate_count
    result_reasons.append(f"[{'PASS' if pool_ok else 'FAIL'}] preferred_candidate_pool: {pool_msg}")

    # 8. Bad required fields
    _, _, items = check_preferred_pool(data)
    bad_required_fields = []
    for i, item in enumerate(items):
        for field in PREFERRED_REQUIRED_FIELDS:
            if field not in item:
                bad_required_fields.append({"index": i, "source_id": item.get("source_id", "?"), "field": field})
    result_details["bad_required_fields"] = bad_required_fields
    result_reasons.append(f"[{'PASS' if not bad_required_fields else 'FAIL'}] bad_required_fields: {bad_required_fields if bad_required_fields else 'none'}")

    # 9. Bad exclusive policy
    bad_exclusive = []
    for i, item in enumerate(items):
        if item.get("not_exclusive") is not True:
            bad_exclusive.append({"index": i, "source_id": item.get("source_id", "?"), "not_exclusive_value": item.get("not_exclusive")})
    result_details["bad_exclusive_policy"] = bad_exclusive
    result_reasons.append(f"[{'PASS' if not bad_exclusive else 'FAIL'}] bad_exclusive_policy: {bad_exclusive if bad_exclusive else 'none'}")

    # 10. Direct application policy check
    principle_text = json.dumps(data.get("selection_principle", {}), ensure_ascii=False)
    bad_direct = "applied" not in principle_text
    gate_ids = [g.get("gate_id", "") for g in data.get("must_have_gates", [])]
    has_gate_005 = "QS-SRC-GATE-005" in gate_ids
    direct_policy_ok = (not bad_direct) and has_gate_005
    result_details["bad_direct_application_policy"] = []
    result_details["direct_application_policy_ok"] = direct_policy_ok
    all_pass = all_pass and direct_policy_ok
    result_reasons.append(f"[{'PASS' if direct_policy_ok else 'FAIL'}] direct_application_policy_ok: principle_has_applied={not bad_direct}, gate_005_exists={has_gate_005}")

    # 11. No forbidden keywords
    forb_ok, forb_found = check_no_forbidden_keywords(data)
    all_pass = all_pass and forb_ok
    result_details["forbidden_keywords_found"] = forb_found or []
    result_reasons.append(f"[{'PASS' if forb_ok else 'FAIL'}] forbidden_keywords: {'found=' + str(forb_found) if forb_found else 'none'}")

    # 12. Decision output
    dec_ok, dec_details = check_decision_output(data)
    all_pass = all_pass and dec_ok
    result_details["decision_output_ok"] = dec_ok
    result_details["decision_output"] = dec_details
    result_reasons.append(f"[{'PASS' if dec_ok else 'FAIL'}] decision_output: ok={dec_ok}")

    # 13. No downstream files
    no_down_ok, unexpected_files = check_no_downstream_files()
    all_pass = all_pass and no_down_ok
    result_details["unexpected_downstream_files"] = unexpected_files
    result_reasons.append(f"[{'PASS' if no_down_ok else 'FAIL'}] unexpected_downstream: {unexpected_files if unexpected_files else 'none'}")

    result = "PASS" if all_pass else "WARN"

    report = {
        "stage": "G3-QINGSHAN-SOURCE-SELECTION-v1.0",
        "result": result,
        "policy_exists": exists,
        "source_class_count": source_class_count,
        "gate_count": gate_count,
        "preferred_candidate_count": preferred_candidate_count,
        "bad_required_fields": bad_required_fields,
        "bad_exclusive_policy": bad_exclusive,
        "bad_direct_application_policy": result_details.get("bad_direct_application_policy", []),
        "direct_application_policy_ok": result_details.get("direct_application_policy_ok", False),
        "unexpected_downstream_files": unexpected_files,
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
