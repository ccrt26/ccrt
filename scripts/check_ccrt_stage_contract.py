#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "00_项目地基" / "05_流程与角色" / "stage_gate_policy.json"
ROLE_MATRIX = ROOT / "00_项目地基" / "05_流程与角色" / "role_matrix.json"

EXPECTED_STAGE_OWNERS = {
    "G0": "阿黑",
    "G1": "腰子",
    "G2": "情墨",
    "G3": "红结",
    "G4": "新安",
    "G5": "旧影",
    "G6": "腰子",
}

REQUIRED_OUTPUT_KEYS = {
    "G0": ["flow_code", "required_roles", "allowed_scope", "forbidden_scope"],
    "G1": ["business_position", "data_position", "risk_boundary"],
    "G2": ["technical_plan", "changed_file_plan", "acceptance_commands", "rollback_plan"],
    "G3": ["changed_files", "implementation_summary", "commands_run"],
    "G4": ["test_commands", "test_results", "g4_self_check_candidate"],
    "G5": ["audit_findings", "scope_review", "evidence_review", "role_boundary_review", "g5_result"],
    "G6": ["release_decision", "archive_record", "final_status"],
}

FORBIDDEN_ROLE_NAMES = {"Codex", "DeepSeek", "Claude", "LangGraph", "执行模型"}

def check(status, check_id, message, expected=None, actual=None):
    return {
        "status": status,
        "check_id": check_id,
        "message": message,
        "expected": expected,
        "actual": actual,
    }

def main():
    parser = argparse.ArgumentParser(description="Check CCRT G0-G6 stage contract")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    role_matrix = json.loads(ROLE_MATRIX.read_text(encoding="utf-8"))

    project_roles = {r["role"] for r in role_matrix.get("roles", [])}
    results = []

    contract = policy.get("g0_g6_stage_contract")
    if isinstance(contract, dict):
        results.append(check("PASS", "C1_CONTRACT_EXISTS", "g0_g6_stage_contract 存在"))
    else:
        results.append(check("BLOCK", "C1_CONTRACT_EXISTS", "缺少 g0_g6_stage_contract"))
        contract = {}

    stages = contract.get("stages", {})
    missing_stages = [g for g in EXPECTED_STAGE_OWNERS if g not in stages]
    if not missing_stages:
        results.append(check("PASS", "C2_ALL_STAGES", "G0-G6 阶段齐全"))
    else:
        results.append(check("BLOCK", "C2_ALL_STAGES", "缺少阶段", list(EXPECTED_STAGE_OWNERS), missing_stages))

    owner_errors = []
    for gate, owner in EXPECTED_STAGE_OWNERS.items():
        actual = stages.get(gate, {}).get("primary_owner")
        if actual != owner:
            owner_errors.append(f"{gate}:{actual}")
    if not owner_errors:
        results.append(check("PASS", "C3_PRIMARY_OWNERS", "G0-G6 主责正确"))
    else:
        results.append(check("BLOCK", "C3_PRIMARY_OWNERS", "阶段主责错误", EXPECTED_STAGE_OWNERS, owner_errors))

    non_role_refs = []
    for gate, stage in stages.items():
        refs = [stage.get("primary_owner")] + stage.get("participants", [])
        for ref in refs:
            if ref and ref not in project_roles:
                non_role_refs.append(f"{gate}:{ref}")
            if ref in FORBIDDEN_ROLE_NAMES:
                non_role_refs.append(f"{gate}:tool_as_role:{ref}")
    if not non_role_refs:
        results.append(check("PASS", "C4_ONLY_PROJECT_ROLES", "阶段主责/参与者均为项目角色"))
    else:
        results.append(check("BLOCK", "C4_ONLY_PROJECT_ROLES", "发现非项目角色", sorted(project_roles), non_role_refs))

    output_errors = []
    for gate, required in REQUIRED_OUTPUT_KEYS.items():
        actual = stages.get(gate, {}).get("required_outputs", [])
        missing = [x for x in required if x not in actual]
        if missing:
            output_errors.append(f"{gate}:missing:{missing}")
    if not output_errors:
        results.append(check("PASS", "C5_REQUIRED_OUTPUTS", "每阶段必交产物齐全"))
    else:
        results.append(check("BLOCK", "C5_REQUIRED_OUTPUTS", "阶段必交产物缺失", REQUIRED_OUTPUT_KEYS, output_errors))

    evidence_errors = []
    for gate, stage in stages.items():
        if not stage.get("required_evidence"):
            evidence_errors.append(gate)
    if not evidence_errors:
        results.append(check("PASS", "C6_REQUIRED_EVIDENCE", "每阶段均有证据要求"))
    else:
        results.append(check("BLOCK", "C6_REQUIRED_EVIDENCE", "阶段缺证据要求", None, evidence_errors))

    block_errors = []
    for gate, stage in stages.items():
        if not stage.get("block_conditions"):
            block_errors.append(gate)
    if not block_errors:
        results.append(check("PASS", "C7_BLOCK_CONDITIONS", "每阶段均有 BLOCK 条件"))
    else:
        results.append(check("BLOCK", "C7_BLOCK_CONDITIONS", "阶段缺 BLOCK 条件", None, block_errors))

    global_rules = json.dumps(contract.get("global_rules", []), ensure_ascii=False)
    required_phrases = ["任何任务必须先有 G0", "缺当前阶段 primary_owner 输出", "阿黑代签", "缺证据却 PASS"]
    missing_phrases = [x for x in required_phrases if x not in global_rules]
    if not missing_phrases:
        results.append(check("PASS", "C8_GLOBAL_RULES", "全局阻断规则齐全"))
    else:
        results.append(check("BLOCK", "C8_GLOBAL_RULES", "全局阻断规则缺失", required_phrases, missing_phrases))

    final_status = contract.get("allowed_final_status")
    if final_status == ["COMPLETE", "AUTO_REPAIRING", "BLOCK"]:
        results.append(check("PASS", "C9_FINAL_STATUS", "最终状态三态固定"))
    else:
        results.append(check("BLOCK", "C9_FINAL_STATUS", "最终状态不是三态", ["COMPLETE", "AUTO_REPAIRING", "BLOCK"], final_status))

    final = "PASS" if all(r["status"] == "PASS" for r in results) else "BLOCK"
    payload = {"result": final, "checks": results}

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for r in results:
            print(f"{r['status']}: {r['check_id']} - {r['message']}")
        print(f"RESULT: {final}")

    return 0 if final == "PASS" else 2

if __name__ == "__main__":
    raise SystemExit(main())
