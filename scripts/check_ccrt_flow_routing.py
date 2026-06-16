#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLOW_ROUTES = ROOT / "00_项目地基" / "05_流程与角色" / "flow_routes.json"
ROLE_MATRIX = ROOT / "00_项目地基" / "05_流程与角色" / "role_matrix.json"
STAGE_POLICY = ROOT / "00_项目地基" / "05_流程与角色" / "stage_gate_policy.json"

FORBIDDEN_TOOL_NAMES = {"Codex", "DeepSeek", "Claude", "LangGraph", "执行模型"}
REQUIRED_ISSUE_ROUTES = {
    "data_fetch_or_data_integrity",
    "schedule_or_automation",
    "daily_report",
    "financial_strategy_or_analysis",
    "gate_or_validation",
    "role_process",
    "architecture",
    "eval_or_backfill",
    "knowledge_or_signal",
    "migration_or_archive",
    "feature_delivery",
    "targeted_fix",
}
REQUIRED_STATES = ["PASS", "WARN", "BLOCK"]
REQUIRED_ROUTING_FIELDS = [
    "flow_code",
    "matched_issue_route",
    "route_reason",
    "required_roles",
    "required_gates",
    "langgraph_required",
    "allowed_final_status",
]

def item(status, check_id, message, expected=None, actual=None):
    return {
        "status": status,
        "check_id": check_id,
        "message": message,
        "expected": expected,
        "actual": actual,
    }

def main():
    parser = argparse.ArgumentParser(description="Check CCRT flow routing contract")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    flow = json.loads(FLOW_ROUTES.read_text(encoding="utf-8"))
    role = json.loads(ROLE_MATRIX.read_text(encoding="utf-8"))
    stage = json.loads(STAGE_POLICY.read_text(encoding="utf-8"))

    project_roles = {r["role"] for r in role.get("roles", [])}
    flow_codes = {f["flow_code"] for f in flow.get("flows", [])}
    stage_gates = set(stage.get("g0_g6_stage_contract", {}).get("stages", {}).keys())

    checks = []
    contract = flow.get("g0_g6_routing_contract")
    if isinstance(contract, dict):
        checks.append(item("PASS", "C1_CONTRACT_EXISTS", "g0_g6_routing_contract 存在"))
    else:
        checks.append(item("BLOCK", "C1_CONTRACT_EXISTS", "缺少 g0_g6_routing_contract"))
        contract = {}

    if contract.get("default_langgraph") is False:
        checks.append(item("PASS", "C2_LANGGRAPH_DEFAULT_OFF", "LangGraph 默认关闭"))
    else:
        checks.append(item("BLOCK", "C2_LANGGRAPH_DEFAULT_OFF", "LangGraph 不得默认启用", False, contract.get("default_langgraph")))

    issue_routes = contract.get("issue_routes", {})
    missing_routes = sorted(REQUIRED_ISSUE_ROUTES - set(issue_routes))
    if not missing_routes:
        checks.append(item("PASS", "C3_REQUIRED_ISSUE_ROUTES", "必需问题路由齐全"))
    else:
        checks.append(item("BLOCK", "C3_REQUIRED_ISSUE_ROUTES", "缺少问题路由", sorted(REQUIRED_ISSUE_ROUTES), missing_routes))

    bad_flow_refs = []
    bad_gate_refs = []
    non_project_roles = []
    missing_route_fields = []

    for name, route in issue_routes.items():
        flow_code = route.get("flow_code")
        if flow_code not in flow_codes:
            bad_flow_refs.append(f"{name}:{flow_code}")

        gates = route.get("must_have_gates", [])
        for gate in gates:
            if gate not in stage_gates:
                bad_gate_refs.append(f"{name}:{gate}")

        roles = route.get("required_roles", [])
        for r in roles:
            if r == "问题所属角色":
                continue
            if r not in project_roles:
                non_project_roles.append(f"{name}:{r}")
            if r in FORBIDDEN_TOOL_NAMES:
                non_project_roles.append(f"{name}:tool_as_role:{r}")

        for field in ["flow_code", "keywords", "required_roles", "must_have_gates", "block_if_missing_roles"]:
            if field not in route:
                missing_route_fields.append(f"{name}:{field}")

    if not bad_flow_refs:
        checks.append(item("PASS", "C4_FLOW_REFS", "所有 issue route 引用合法 flow_code"))
    else:
        checks.append(item("BLOCK", "C4_FLOW_REFS", "存在非法 flow_code", sorted(flow_codes), bad_flow_refs))

    if not bad_gate_refs:
        checks.append(item("PASS", "C5_GATE_REFS", "所有 issue route 引用合法 G0-G6"))
    else:
        checks.append(item("BLOCK", "C5_GATE_REFS", "存在非法 gate", sorted(stage_gates), bad_gate_refs))

    if not non_project_roles:
        checks.append(item("PASS", "C6_ONLY_PROJECT_ROLES", "路由角色均为项目角色或问题所属角色占位"))
    else:
        checks.append(item("BLOCK", "C6_ONLY_PROJECT_ROLES", "路由中存在非项目角色", sorted(project_roles), non_project_roles))

    if not missing_route_fields:
        checks.append(item("PASS", "C7_ROUTE_FIELDS", "每条路由字段齐全"))
    else:
        checks.append(item("BLOCK", "C7_ROUTE_FIELDS", "路由字段缺失", None, missing_route_fields))

    states = contract.get("decision_states", {})
    missing_states = [s for s in REQUIRED_STATES if s not in states]
    if not missing_states:
        checks.append(item("PASS", "C8_DECISION_STATES", "PASS/WARN/BLOCK 三态齐全"))
    else:
        checks.append(item("BLOCK", "C8_DECISION_STATES", "判定三态缺失", REQUIRED_STATES, missing_states))

    block_conditions = json.dumps(states.get("BLOCK", {}).get("conditions", []), ensure_ascii=False)
    required_block_phrases = ["缺 G0 路由", "缺阶段 primary_owner 输出", "缺必需角色输出", "阿黑代签", "自写自审", "工具名被写成项目角色"]
    missing_block_phrases = [p for p in required_block_phrases if p not in block_conditions]
    if not missing_block_phrases:
        checks.append(item("PASS", "C9_BLOCK_RULES", "BLOCK 关键场景齐全"))
    else:
        checks.append(item("BLOCK", "C9_BLOCK_RULES", "BLOCK 关键场景缺失", required_block_phrases, missing_block_phrases))

    routing_fields = contract.get("routing_output_required_fields", [])
    missing_output_fields = [f for f in REQUIRED_ROUTING_FIELDS if f not in routing_fields]
    if not missing_output_fields:
        checks.append(item("PASS", "C10_ROUTING_OUTPUT_FIELDS", "G0 路由输出字段齐全"))
    else:
        checks.append(item("BLOCK", "C10_ROUTING_OUTPUT_FIELDS", "G0 路由输出字段缺失", REQUIRED_ROUTING_FIELDS, missing_output_fields))

    priority = contract.get("priority_order", [])
    missing_priorities = sorted(flow_codes - set(priority))
    if not missing_priorities:
        checks.append(item("PASS", "C11_PRIORITY_ORDER", "优先级覆盖全部 flow_code"))
    else:
        checks.append(item("BLOCK", "C11_PRIORITY_ORDER", "优先级缺少 flow_code", sorted(flow_codes), missing_priorities))

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
