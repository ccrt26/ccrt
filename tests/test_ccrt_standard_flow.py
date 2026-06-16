import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class TestCCRTStandardFlow(unittest.TestCase):
    def test_standard_flow_total_gate_passes(self):
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_ccrt_standard_flow.py"), "--json"],
            cwd=str(ROOT),
            text=True,
            capture_output=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["result"], "PASS")
        self.assertEqual(payload["summary"]["role_boundary"], "PASS")
        self.assertEqual(payload["summary"]["stage_contract"], "PASS")
        self.assertEqual(payload["summary"]["flow_routing"], "PASS")

    def test_standard_flow_plain_output(self):
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_ccrt_standard_flow.py")],
            cwd=str(ROOT),
            text=True,
            capture_output=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("RESULT: PASS", proc.stdout)

if __name__ == "__main__":
    unittest.main()
