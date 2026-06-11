#!/usr/bin/env python3
"""validate_krm_task_router_v1_0.py — 路由表校验"""

import json, hashlib
from pathlib import Path

ROOT = Path("/Users/ccrt/ccrt")
ROUTER = ROOT / "00_项目地基/07_知识进化/knowledge/routing/krm_task_router_v1.0.json"
REPORT = ROOT / "00_项目地基/07_知识进化/knowledge/reports/krm_task_router_validation_v1.0.json"
MANIFEST = ROOT / "00_项目地基/07_知识进化/knowledge/manifest.json"

REQUIRED_ROUTES = [
    "flow_issue","knowledge_routing_issue","financial_redline","evidence_quality_issue",
    "signal_validity_issue","event_catalyst_issue","macro_environment_issue",
    "integration_decision_issue","post_evaluation_issue","output_format_issue",
]

REQUIRED_FIELDS = ["label","triggers","must_read","optional_read","deep_read","owner_roles","decision_limit"]

OWNER_MAP = {
    "financial_redline":"流金","evidence_quality_issue":"玉夜","signal_validity_issue":"青山",
    "event_catalyst_issue":"信鸽","macro_environment_issue":"山猫","integration_decision_issue":"腰子",
}

FLOW_FILES = [
    "00_项目地基/05_流程与角色/L1_FLOW_流程路由与阶段门_v1.0.md",
    "00_项目地基/05_流程与角色/L1_ROLE_角色唤醒与输出规范_v1.0.md",
    "00_项目地基/05_流程与角色/L1_TASK_阶段派单与执行模板_v1.0.md",
]

def main():
    result = {
        "stage": "G3-KRM-TASK-ROUTER-v1.0",
        "result": "PASS",
        "route_count": 0,
        "missing_routes": [],
        "bad_required_fields": [],
        "bad_must_read_paths": [],
        "bad_deep_read_paths": [],
        "warn_optional_missing": [],
        "bad_owner_role_mapping": [],
        "bad_legacy_path_usage": [],
        "result_reason": "",
    }

    if not ROUTER.exists():
        result["result"] = "BLOCK"
        result["result_reason"] = "router 不存在"
        writef(REPORT, json.dumps(result, ensure_ascii=False, indent=2))
        return

    router = json.loads(ROUTER.read_text(encoding="utf-8"))
    routes = router.get("routes", {})
    result["route_count"] = len(routes)

    # Missing routes
    for rid in REQUIRED_ROUTES:
        if rid not in routes:
            result["missing_routes"].append(rid)

    for rid, route in routes.items():
        for field in REQUIRED_FIELDS:
            if field not in route:
                result["bad_required_fields"].append(f"{rid}: missing {field}")

        for field in ["must_read", "deep_read"]:
            for raw in route.get(field, []):
                if ".claude/agents" in raw and "-知识库" in raw:
                    result["bad_legacy_path_usage"].append(f"{rid}: {raw}")
                if not (ROOT / raw).exists():
                    (result["bad_must_read_paths"] if field == "must_read" else result["bad_deep_read_paths"]).append(f"{rid}: {raw}")

        for raw in route.get("optional_read", []):
            if ".claude/agents" in raw and "-知识库" in raw:
                result["bad_legacy_path_usage"].append(f"{rid}: {raw}")
            if not (ROOT / raw).exists():
                result["warn_optional_missing"].append(f"{rid}: {raw}")

        if len(route.get("triggers", [])) < 3:
            result["bad_required_fields"].append(f"{rid}: < 3 triggers")

        if len(route.get("owner_roles", [])) < 1:
            result["bad_required_fields"].append(f"{rid}: no owner_roles")

    # Owner role mapping
    for rid, expected in OWNER_MAP.items():
        if expected not in routes.get(rid, {}).get("owner_roles", []):
            result["bad_owner_role_mapping"].append(f"{rid}: missing {expected}")

    # flow_issue must include FLOW/ROLE/TASK
    for f in FLOW_FILES:
        if f not in routes.get("flow_issue", {}).get("must_read", []):
            result["bad_must_read_paths"].append(f"flow_issue: missing {f}")

    # post_evaluation must include B层 adapter + KUC schema
    pe = routes.get("post_evaluation_issue", {})
    must_pe = pe.get("must_read", [])
    if not any("L2_ADAPTER_B层" in x for x in must_pe):
        result["bad_must_read_paths"].append("post_evaluation_issue: missing B层 adapter")
    if not any("KnowledgeUpdateCandidate" in x for x in must_pe):
        result["bad_must_read_paths"].append("post_evaluation_issue: missing KUC schema")

    # Determine result
    reasons = []
    if result["missing_routes"]: reasons.append("missing_routes")
    if result["bad_must_read_paths"]: reasons.append("bad_must_read_paths")
    if result["bad_deep_read_paths"]: reasons.append("bad_deep_read_paths")
    if result["bad_owner_role_mapping"]: reasons.append("bad_owner_role_mapping")
    if result["bad_legacy_path_usage"]: reasons.append("bad_legacy_path_usage")
    if result["bad_required_fields"]: reasons.append("bad_required_fields")

    if reasons:
        result["result"] = "BLOCK"
        result["result_reason"] = "; ".join(reasons)
    else:
        result["result"] = "PASS"
        result["result_reason"] = "所有检查通过"

    writef(REPORT, json.dumps(result, ensure_ascii=False, indent=2))
    print(f"Validation: {result['result']}")
    return result

def writef(p, s):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s.rstrip() + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
