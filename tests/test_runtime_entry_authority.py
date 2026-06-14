import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class TestRuntimeEntryAuthority(unittest.TestCase):
    def test_runtime_authority_passes_and_wrapper_registered(self):
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts/check_runtime_entry_authority.py"), "--all", "--json"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=60
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

        registry = json.loads((ROOT / "00_项目地基/06_调度与运行/runtime_entry_registry.json").read_text(encoding="utf-8"))
        entries = {e["entry"]: e for e in registry["entries"]}
        self.assertEqual(entries["run_daily_data_pipeline_today.py"].get("status"), "active_wrapper")
        self.assertEqual(entries["run_daily_data_pipeline_today.py"].get("delegates_to"), "run_daily_production_pipeline.py")
        self.assertEqual(entries["run_daily_production_pipeline.py"].get("authority"), "daily_production_pipeline_entry")

if __name__ == "__main__":
    unittest.main()
