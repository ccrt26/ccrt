import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROLE_MATRIX = ROOT / "00_项目地基" / "05_流程与角色" / "role_matrix.json"

class TestCCRTRoleBoundary(unittest.TestCase):
    def test_role_boundary_gate_passes(self):
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_ccrt_role_boundary.py"), "--json"],
            cwd=str(ROOT),
            text=True,
            capture_output=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["result"], "PASS")

    def test_stage_owners_are_project_roles(self):
        data = json.loads(ROLE_MATRIX.read_text(encoding="utf-8"))
        roles = {r["role"] for r in data["roles"]}
        owners = data["role_boundary_contract"]["stage_owners"]
        for gate_roles in owners.values():
            for role in gate_roles:
                self.assertIn(role, roles)

    def test_ahei_cannot_implement_or_audit(self):
        data = json.loads(ROLE_MATRIX.read_text(encoding="utf-8"))
        ahei = data["role_boundary_contract"]["role_rules"]["阿黑"]
        self.assertNotIn("G3", ahei["allowed_gates"])
        self.assertNotIn("G4", ahei["allowed_gates"])
        self.assertNotIn("G5", ahei["allowed_gates"])
        self.assertFalse(ahei["can_sign_for_others"])

if __name__ == "__main__":
    unittest.main()
