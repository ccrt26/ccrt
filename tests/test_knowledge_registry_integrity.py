import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class TestKnowledgeRegistryIntegrity(unittest.TestCase):
    def test_registry_validate_passes(self):
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts/knowledge_registry_check.py"), "--validate"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=30
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

if __name__ == "__main__":
    unittest.main()
