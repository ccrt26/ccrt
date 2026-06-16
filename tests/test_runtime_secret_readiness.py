import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from runtime_secret_loader import TUSHARE_TOKEN, check_secret_readiness, parse_env_file


class TestRuntimeSecretReadiness(unittest.TestCase):
    def test_parse_export_style_env_file(self):
        with tempfile.TemporaryDirectory() as td:
            env_file = Path(td) / "tielv.env"
            env_file.write_text('export TUSHARE_TOKEN="abc123"\n', encoding="utf-8")
            self.assertEqual(parse_env_file(env_file)[TUSHARE_TOKEN], "abc123")

    def test_launchd_compatible_requires_private_file(self):
        with tempfile.TemporaryDirectory() as td:
            env_file = Path(td) / "missing.env"
            status = check_secret_readiness(TUSHARE_TOKEN, private_env=env_file, launchd_compatible=True)
            self.assertEqual(status["status"], "BLOCK")
            self.assertFalse(status["launchd_compatible"])

    def test_check_script_passes_with_private_file(self):
        with tempfile.TemporaryDirectory() as td:
            env_file = Path(td) / "tielv.env"
            env_file.write_text("TUSHARE_TOKEN=abc123\n", encoding="utf-8")
            proc = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "check_runtime_secret_readiness.py"),
                    "--runtime",
                    "daily_production",
                    "--private-env",
                    str(env_file),
                    "--json",
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["overall"], "PASS")
            self.assertNotIn("abc123", proc.stdout)


if __name__ == "__main__":
    unittest.main()
