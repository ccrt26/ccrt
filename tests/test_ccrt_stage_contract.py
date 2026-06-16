import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "00_项目地基" / "05_流程与角色" / "stage_gate_policy.json"

class TestCCRTStageContract(unittest.TestCase):
    def test_stage_contract_gate_passes(self):
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_ccrt_stage_contract.py"), "--json"],
            cwd=str(ROOT),
            text=True,
            capture_output=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["result"], "PASS")

    def test_g0_g6_primary_owners(self):
        data = json.loads(POLICY.read_text(encoding="utf-8"))
        stages = data["g0_g6_stage_contract"]["stages"]
        expected = {
            "G0": "阿黑",
            "G1": "腰子",
            "G2": "情墨",
            "G3": "红结",
            "G4": "新安",
            "G5": "旧影",
            "G6": "腰子",
        }
        actual = {gate: stages[gate]["primary_owner"] for gate in expected}
        self.assertEqual(actual, expected)

    def test_every_stage_has_outputs_evidence_and_block_rules(self):
        data = json.loads(POLICY.read_text(encoding="utf-8"))
        stages = data["g0_g6_stage_contract"]["stages"]
        for gate, stage in stages.items():
            self.assertTrue(stage["required_outputs"], gate)
            self.assertTrue(stage["required_evidence"], gate)
            self.assertTrue(stage["block_conditions"], gate)

if __name__ == "__main__":
    unittest.main()
