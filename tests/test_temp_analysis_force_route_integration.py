#!/usr/bin/env python3
"""Integration tests for temporary-analysis force route wiring."""

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestTemporaryAnalysisForceRouteIntegration(unittest.TestCase):
    def test_flow_routes_contains_force_route(self):
        data = json.loads((ROOT / "00_项目地基/05_流程与角色/flow_routes.json").read_text(encoding="utf-8"))
        route = data["g0_g6_routing_contract"]["issue_routes"]["temporary_analysis_force_route"]
        self.assertEqual(route["flow_code"], "F-ANALYSIS")
        self.assertTrue(route["block_if_precheck_not_used"])
        self.assertIn("scripts/check_temp_analysis_force_route.py", route["required_precheck"])
        self.assertIn("render_temp_analysis_response.py", route["required_backend_chain"])

    def test_role_matrix_blocks_direct_temp_analysis_answer(self):
        data = json.loads((ROOT / "00_项目地基/05_流程与角色/role_matrix.json").read_text(encoding="utf-8"))
        self.assertIn("砺石", data["flow_role_mapping"]["F-ANALYSIS"])
        contract = data["role_boundary_contract"]["temporary_analysis_force_route"]
        self.assertTrue(contract["forbid_direct_role_answer"])
        self.assertTrue(contract["d07_v1_2_lishi_integrated_by_default"])

    def test_stage_gate_g0_requires_force_route_precheck(self):
        data = json.loads((ROOT / "00_项目地基/05_流程与角色/stage_gate_policy.json").read_text(encoding="utf-8"))
        g0 = data["g0_g6_stage_contract"]["stages"]["G0"]
        joined = json.dumps(g0, ensure_ascii=False)
        self.assertIn("scripts/check_temp_analysis_force_route.py", joined)
        self.assertIn("TEMP_ANALYSIS_REQUIRED", joined)

    def test_orchestrator_classifies_temp_analysis_before_generic_analysis(self):
        path = ROOT / "代码文件/tools/ccrt_langgraph_orchestrator.py"
        spec = importlib.util.spec_from_file_location("ccrt_langgraph_orchestrator", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        flow, reason = module.classify_requirement("东睦股份今天放量上涨怎么看")
        self.assertEqual(flow, "F-ANALYSIS")
        self.assertIn("TEMP_ANALYSIS_REQUIRED", reason)
        self.assertIn("TemporaryAnalysisBrief", reason)


if __name__ == "__main__":
    unittest.main()
