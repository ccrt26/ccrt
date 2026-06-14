#!/usr/bin/env python3
"""
G3-QINGSHAN-LITERATURE-CARD-TO-RULE-CANDIDATE-v1.0 校验脚本
检验文献卡片 → 规则候选流程 JSON 的完整性和合规性
"""
import json, hashlib, sys
from pathlib import Path

STAGE = "G3-QINGSHAN-LITERATURE-CARD-TO-RULE-CANDIDATE-v1.0"

BASE = Path(__file__).resolve().parent.parent
FLOW_PATH = BASE / "literature" / "qingshan_literature_card_to_rule_candidate_flow_v1.0.json"
POLICY_PATH = BASE / "literature" / "qingshan_source_selection_policy_v1.0.json"
SCHEMA_PATH = BASE / "literature" / "qingshan_literature_quality_schema_v1.0.json"
REPORT_PATH = BASE / "reports" / "qingshan_literature_card_to_rule_candidate_flow_validation_v1.0.json"
LIT_DIR = BASE / "literature"

REQUIRED_CARD_FIELDS = [
    "card_id", "source_id", "source_title", "source_type",
    "author_or_institution", "publication_date",
    "source_selection_status", "quality_status",
    "total_score", "hard_block_triggered",
    "extracted_claims", "evidence_units",
    "applicable_market", "sample_scope",
    "method_summary", "limitations",
    "conflict_notes", "qingshan_use_case",
    "traceability", "card_status"
]

REQUIRED_CANDIDATE_FIELDS = [
    "candidate_id", "source_card_id", "owner_role",
    "candidate_type", "target_knowledge_bucket",
    "proposed_rule_summary", "evidence_refs",
    "applicability_scope", "exclusion_conditions",
    "expected_benefit", "risk_of_misuse",
    "validation_requirement", "candidate_status"
]

ALLOW_IDS = [f"ALLOW-{i:03d}" for i in range(1, 11)]
BLOCK_IDS = [f"BLOCK-{i:03d}" for i in range(1, 11)]
RL_IDS = [f"RL-{i:03d}" for i in range(1, 8)]

FORBIDDEN_DOWNSTREAM = ["literature_cards", "rule_candidates"]

def main():
    all_pass = True
    reasons = []
    details = {}

    exists = FLOW_PATH.exists()
    all_pass = all_pass and exists
    details["flow_exists"] = exists
    reasons.append(f"[{'PASS' if exists else 'FAIL'}] flow_exists: {exists}")
    if not exists:
        print("BLOCK: flow JSON not found"); sys.exit(1)

    data = json.loads(FLOW_PATH.read_text(encoding="utf-8"))

    # depends_on checks
    deps = set(data.get("meta", {}).get("depends_on", []))
    dep_targets = {
        "knowledge/literature/qingshan_source_selection_policy_v1.0.json",
        "knowledge/literature/qingshan_literature_quality_schema_v1.0.json"
    }
    dep_ok = dep_targets.issubset(deps)
    all_pass = all_pass and dep_ok
    reasons.append(f"[{'PASS' if dep_ok else 'FAIL'}] depends_on: both source selection and quality schema present={dep_ok}")
    details["depends_on_complete"] = dep_ok

    # depends_on files exist
    dep_files_exist = POLICY_PATH.exists() and SCHEMA_PATH.exists()
    all_pass = all_pass and dep_files_exist
    reasons.append(f"[{'PASS' if dep_files_exist else 'FAIL'}] depends_on_files_exist: {dep_files_exist}")

    # LiteratureCard required fields
    card_fields = set(data.get("literature_card_schema", {}).get("required_fields", []))
    card_fields_ok = all(f in card_fields for f in REQUIRED_CARD_FIELDS)
    missing_card = sorted(set(REQUIRED_CARD_FIELDS) - card_fields)
    all_pass = all_pass and card_fields_ok
    details["missing_card_fields"] = missing_card
    reasons.append(f"[{'PASS' if card_fields_ok else 'FAIL'}] literature_card_fields: missing={missing_card}")

    # Card initial status
    card_init = data.get("literature_card_schema", {}).get("initial_status", "")
    card_init_ok = card_init == "card_draft"
    all_pass = all_pass and card_init_ok
    reasons.append(f"[{'PASS' if card_init_ok else 'FAIL'}] literature_card_initial_status: {card_init}")

    # RuleCandidate required fields
    cand_fields = set(data.get("rule_candidate_schema", {}).get("required_fields", []))
    cand_fields_ok = all(f in cand_fields for f in REQUIRED_CANDIDATE_FIELDS)
    missing_cand = sorted(set(REQUIRED_CANDIDATE_FIELDS) - cand_fields)
    all_pass = all_pass and cand_fields_ok
    details["missing_candidate_fields"] = missing_cand
    reasons.append(f"[{'PASS' if cand_fields_ok else 'FAIL'}] rule_candidate_fields: missing={missing_cand}")

    # Candidate initial status
    cand_init = data.get("rule_candidate_schema", {}).get("initial_status", "")
    cand_init_ok = cand_init == "candidate_draft"
    all_pass = all_pass and cand_init_ok
    reasons.append(f"[{'PASS' if cand_init_ok else 'FAIL'}] rule_candidate_initial_status: {cand_init}")

    # Allow generation conditions
    allow_conds = [c.get("id", "") for c in data.get("allow_generation_conditions", [])]
    allow_ids_ok = all(aid in allow_conds for aid in ALLOW_IDS)
    all_pass = all_pass and allow_ids_ok
    reasons.append(f"[{'PASS' if allow_ids_ok else 'FAIL'}] allow_generation_conditions: 10 expected, {len(allow_conds)} found")
    details["allow_generation_count"] = len(allow_conds)

    # Block generation conditions
    block_conds = [c.get("id", "") for c in data.get("block_generation_conditions", [])]
    block_ids_ok = all(bid in block_conds for bid in BLOCK_IDS)
    all_pass = all_pass and block_ids_ok
    reasons.append(f"[{'PASS' if block_ids_ok else 'FAIL'}] block_generation_conditions: 10 expected, {len(block_conds)} found")
    details["block_generation_count"] = len(block_conds)

    # Diversion rules
    diversion = data.get("diversion_rules", [])
    diversion_ok = len(diversion) >= 5
    targets = set(d.get("target", "") for d in diversion)
    expected_targets = {"role_capability_rules", "parameter_candidate", "counterexample_candidate", "literature_background", "reject_or_hold"}
    diversion_target_ok = expected_targets.issubset(targets)
    all_pass = all_pass and diversion_ok and diversion_target_ok
    reasons.append(f"[{'PASS' if diversion_ok and diversion_target_ok else 'FAIL'}] diversion_rules: count={len(diversion)}, targets_complete={diversion_target_ok}")

    # Redlines
    redlines = [r.get("id", "") for r in data.get("redlines", [])]
    rl_ids_ok = all(rid in redlines for rid in RL_IDS)
    all_pass = all_pass and rl_ids_ok
    reasons.append(f"[{'PASS' if rl_ids_ok else 'FAIL'}] redlines: 7 expected, {len(redlines)} found")

    # Anti overreach
    ao = data.get("anti_overreach", {})
    ao_fields = [
        "no_direct_active_rule_from_literature",
        "no_direct_core_knowledge_update",
        "no_external_fulltext_in_startup",
        "no_auto_pass_for_authority",
        "no_auto_pass_for_high_score",
        "requires_project_validation",
        "requires_qingshan_confirmation",
        "requires_yaozi_confirmation_for_trading_redlines"
    ]
    ao_ok = all(ao.get(f) is True for f in ao_fields)
    all_pass = all_pass and ao_ok
    bad_ao = [f for f in ao_fields if ao.get(f) is not True]
    details["bad_anti_overreach"] = bad_ao
    reasons.append(f"[{'PASS' if ao_ok else 'FAIL'}] anti_overreach: all_true={ao_ok}")

    # No downstream files
    unexpected = []
    if LIT_DIR.exists():
        for f in LIT_DIR.iterdir():
            if any(ds in f.name.lower() for ds in FORBIDDEN_DOWNSTREAM):
                unexpected.append(f.name)
    no_down_ok = len(unexpected) == 0
    all_pass = all_pass and no_down_ok
    details["unexpected_downstream_files"] = unexpected
    reasons.append(f"[{'PASS' if no_down_ok else 'FAIL'}] unexpected_downstream: {unexpected if unexpected else 'none'}")

    result = "PASS" if all_pass else "WARN"

    report = {
        "stage": STAGE,
        "result": result,
        "flow_exists": exists,
        "depends_on_complete": dep_ok and dep_files_exist,
        "literature_card_fields_complete": card_fields_ok,
        "rule_candidate_fields_complete": cand_fields_ok,
        "initial_status_ok": card_init_ok and cand_init_ok,
        "allow_generation_count": len(allow_conds),
        "block_generation_count": len(block_conds),
        "diversion_rule_count": len(diversion),
        "redline_count": len(redlines),
        "anti_overreach_ok": ao_ok,
        "bad_anti_overreach": bad_ao,
        "unexpected_downstream_files": unexpected,
        "result_reason": "; ".join(reasons)
    }

    REPORTS_DIR = BASE / "reports"
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print(f"{STAGE} 校验")
    print("=" * 60)
    print(f"校验结果: {result}")
    for r in reasons:
        print(f"  {r}")
    print(f"\n报告已写入: {REPORT_PATH}")
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
