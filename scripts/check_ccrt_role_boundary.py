#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROLE_MATRIX = ROOT / "00_项目地基" / "05_流程与角色" / "role_matrix.json"

EXPECTED_ROLES = {
    "阿黑", "腰子", "山猫", "信鸽", "玉夜", "流金", "青山", "砺石",
    "情墨", "千光", "红枫", "新安", "红结", "旧影"
}

REQUIRED_STAGE_OWNERS = {
    "G0": ["阿黑"],
    "G1": ["腰子"],
    "G2": ["情墨"],
    "G3": ["红结"],
    "G4": ["新安"],
    "G5": ["旧影"],
    "G6": ["腰子", "阿黑"],
}

FORBIDDEN_TOOL_NAMES = ["Codex", "DeepSeek", "Claude", "LangGraph", "执行模型"]

def result(status, check_id, message, expected=None, actual=None):
    return {
        "status": status,
        "check_id": check_id,
        "message": message,
        "expected": expected,
        "actual": actual,
    }

def main():
    parser = argparse.ArgumentParser(description="Check CCRT G0-G6 role boundary contract")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    checks = []
    data = json.loads(ROLE_MATRIX.read_text(encoding="utf-8"))
    text = ROLE_MATRIX.read_text(encoding="utf-8")

    roles = {r.get("role") for r in data.get("roles", [])}
    if roles == EXPECTED_ROLES:
        checks.append(result("PASS", "C1_ROLE_SET", "14 个项目角色完整"))
    else:
        checks.append(result("BLOCK", "C1_ROLE_SET", "角色集合不一致", sorted(EXPECTED_ROLES), sorted(roles)))

    boundary = data.get("role_boundary_contract")
    if isinstance(boundary, dict):
        checks.append(result("PASS", "C2_CONTRACT_EXISTS", "role_boundary_contract 存在"))
    else:
        checks.append(result("BLOCK", "C2_CONTRACT_EXISTS", "缺少 role_boundary_contract"))

    if isinstance(boundary, dict) and boundary.get("stage_owners") == REQUIRED_STAGE_OWNERS:
        checks.append(result("PASS", "C3_STAGE_OWNERS", "G0-G6 阶段主责正确"))
    else:
        checks.append(result(
            "BLOCK",
            "C3_STAGE_OWNERS",
            "G0-G6 阶段主责不符合标准",
            REQUIRED_STAGE_OWNERS,
            boundary.get("stage_owners") if isinstance(boundary, dict) else None,
        ))

    role_rules = boundary.get("role_rules", {}) if isinstance(boundary, dict) else {}
    missing_rules = sorted(EXPECTED_ROLES - set(role_rules))
    if not missing_rules:
        checks.append(result("PASS", "C4_ROLE_RULES_COMPLETE", "每个角色都有边界规则"))
    else:
        checks.append(result("BLOCK", "C4_ROLE_RULES_COMPLETE", "缺少角色边界规则", sorted(EXPECTED_ROLES), missing_rules))

    forbidden_hits = []
    for word in FORBIDDEN_TOOL_NAMES:
        if word in text:
            forbidden_hits.append(word)
    purpose = boundary.get("purpose", "") if isinstance(boundary, dict) else ""
    allowed_mentions = {"Codex", "DeepSeek", "Claude", "LangGraph"}
    real_hits = [w for w in forbidden_hits if w not in allowed_mentions or "不得写成项目角色" not in purpose]
    if not real_hits:
        checks.append(result("PASS", "C5_NO_TOOL_AS_ROLE", "执行工具未被写成项目角色"))
    else:
        checks.append(result("BLOCK", "C5_NO_TOOL_AS_ROLE", "执行工具被写成项目角色或主责", "无", real_hits))

    ah = role_rules.get("阿黑", {})
    ah_block = []
    for gate in ["G3", "G4", "G5"]:
        if gate in ah.get("allowed_gates", []):
            ah_block.append(gate)
    if ah.get("can_sign_for_others") is not False:
        ah_block.append("can_sign_for_others_not_false")
    if not ah_block:
        checks.append(result("PASS", "C6_AHEI_BOUNDARY", "阿黑禁止 G3/G4/G5 和代签"))
    else:
        checks.append(result("BLOCK", "C6_AHEI_BOUNDARY", "阿黑边界错误", "不得 G3/G4/G5/代签", ah_block))

    required_primary = {
        "红结": "G3",
        "新安": "G4",
        "旧影": "G5",
        "情墨": "G2",
        "腰子": "G6",
    }
    primary_errors = []
    for role, gate in required_primary.items():
        actual = role_rules.get(role, {}).get("primary_gate")
        if actual != gate:
            primary_errors.append(f"{role}:{actual}")
    if not primary_errors:
        checks.append(result("PASS", "C7_PRIMARY_GATES", "关键角色主责阶段正确"))
    else:
        checks.append(result("BLOCK", "C7_PRIMARY_GATES", "关键角色主责阶段错误", required_primary, primary_errors))

    hard_rules = boundary.get("hard_block_rules", []) if isinstance(boundary, dict) else []
    required_rule_keywords = ["阿黑代签", "G3", "G5", "Codex", "DeepSeek", "Claude", "LangGraph"]
    hard_rule_text = json.dumps(hard_rules, ensure_ascii=False)
    missing_keywords = [kw for kw in required_rule_keywords if kw not in hard_rule_text]
    if not missing_keywords:
        checks.append(result("PASS", "C8_HARD_BLOCK_RULES", "硬阻断规则覆盖关键越权场景"))
    else:
        checks.append(result("BLOCK", "C8_HARD_BLOCK_RULES", "硬阻断规则缺少关键场景", required_rule_keywords, missing_keywords))

    final = "PASS" if all(c["status"] == "PASS" for c in checks) else "BLOCK"
    payload = {"result": final, "checks": checks}

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for c in checks:
            print(f"{c['status']}: {c['check_id']} - {c['message']}")
        print(f"RESULT: {final}")

    return 0 if final == "PASS" else 2

if __name__ == "__main__":
    raise SystemExit(main())
