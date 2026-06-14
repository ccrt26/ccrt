import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class TestDailyProductionDryRun(unittest.TestCase):
    def test_dry_run_returns_before_real_steps(self):
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts/run_daily_production_pipeline.py"), "--date", "20990101", "--dry-run"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=30
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["would_write"], [])
        self.assertIn("would_run", payload)
        self.assertNotIn("steps_summary", payload)
        self.assertIn("returns before token loading", payload["guarantee"])

if __name__ == "__main__":
    unittest.main()
