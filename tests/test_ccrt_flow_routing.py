import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLOW_ROUTES = ROOT / "00_项目地基" / "05_流程与角色" / "flow_routes.json"

class TestCCRTFlowRouting(unittest.TestCase):
    def test_flow_routing_gate_passes(self):
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_ccrt_flow_routing.py"), "--json"],
            cwd=str(ROOT),
            text=True,
            capture_output=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["result"], "PASS")

    def test_langgraph_default_off(self):
        data = json.loads(FLOW_ROUTES.read_text(encoding="utf-8"))
        contract = data["g0_g6_routing_contract"]
        self.assertFalse(contract["default_langgraph"])
        self.assertIn("明确", contract["langgraph_enable_condition"])

    def test_key_issue_routes_exist(self):
        data = json.loads(FLOW_ROUTES.read_text(encoding="utf-8"))
        routes = data["g0_g6_routing_contract"]["issue_routes"]
        for key in [
            "data_fetch_or_data_integrity",
            "schedule_or_automation",
            "daily_report",
            "financial_strategy_or_analysis",
            "gate_or_validation",
            "role_process",
        ]:
            self.assertIn(key, routes)

    def test_decision_states_are_three_state(self):
        data = json.loads(FLOW_ROUTES.read_text(encoding="utf-8"))
        states = data["g0_g6_routing_contract"]["decision_states"]
        self.assertEqual(set(states), {"PASS", "WARN", "BLOCK"})

if __name__ == "__main__":
    unittest.main()
