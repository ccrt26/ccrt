"""Tests for batch_data_collector.py --date contract.

No real network or market data dependency. Uses importlib + mocking.
"""
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
COLLECTOR_PY = ROOT / "代码文件" / "每日荐股" / "scripts" / "batch_data_collector.py"


class TestBatchDataCollectorDateContract(unittest.TestCase):
    """batch_data_collector.py --date argument contract tests, fully mocked."""

    @classmethod
    def setUpClass(cls):
        """Load module once from file path."""
        spec = importlib.util.spec_from_file_location(
            "batch_data_collector", str(COLLECTOR_PY)
        )
        cls.bdc_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.bdc_mod)
        # Save reference to _cache for stats access
        cls._cache = cls.bdc_mod._cache

    def setUp(self):
        """Create temp pool/output, patch all 6 collect functions."""
        self.tmp_dir_obj = tempfile.TemporaryDirectory()
        self.tmp_dir = self.tmp_dir_obj.name
        self.pool_path = os.path.join(self.tmp_dir, "test_pool.json")
        self.output_path = os.path.join(self.tmp_dir, "test_output.json")

        test_pool = {"Stocks": [{"Code": "000001", "Name": "PingAn"}], "stocks": []}
        with open(self.pool_path, "w", encoding="utf-8") as f:
            json.dump(test_pool, f)

        # Patch all 6 network-dependent functions
        patcher_quotes = patch.object(self.bdc_mod, "collect_quotes", return_value={})
        patcher_klines = patch.object(self.bdc_mod, "collect_klines", return_value={})
        patcher_fin = patch.object(self.bdc_mod, "collect_financials", return_value={})
        patcher_ff = patch.object(self.bdc_mod, "collect_fund_flows", return_value={})
        patcher_margin = patch.object(self.bdc_mod, "collect_margins", return_value={})
        patcher_sector = patch.object(self.bdc_mod, "collect_sectors", return_value={})

        self.mocks = {
            "quotes": patcher_quotes.start(),
            "klines": patcher_klines.start(),
            "financials": patcher_fin.start(),
            "fund_flows": patcher_ff.start(),
            "margins": patcher_margin.start(),
            "sectors": patcher_sector.start(),
        }
        self.addCleanup(patcher_quotes.stop)
        self.addCleanup(patcher_klines.stop)
        self.addCleanup(patcher_fin.stop)
        self.addCleanup(patcher_ff.stop)
        self.addCleanup(patcher_margin.stop)
        self.addCleanup(patcher_sector.stop)

        # Clean env
        self._old_env_date = os.environ.pop("DAILY_TARGET_DATE", None)

    def tearDown(self):
        self.tmp_dir_obj.cleanup()
        if self._old_env_date is not None:
            os.environ["DAILY_TARGET_DATE"] = self._old_env_date

    def _run_main(self, extra_args):
        """Run module main() with given extra CLI args and temp pool/output."""
        test_args = (
            ["batch_data_collector.py", "--pool", self.pool_path,
             "--output", self.output_path] + extra_args
        )
        with patch.object(sys, "argv", test_args):
            try:
                self.bdc_mod.main()
                return 0
            except SystemExit as e:
                return e.code

    def _load_output(self):
        with open(self.output_path, encoding="utf-8") as f:
            return json.load(f)

    def test_date_arg_yyyymmdd(self):
        """--date YYYYMMDD must be accepted and flow into metadata."""
        rc = self._run_main(["--date", "20990101"])
        self.assertEqual(rc, 0)
        meta = self._load_output().get("_Meta", {})
        self.assertEqual(meta.get("target_date"), "2099-01-01")
        self.assertEqual(meta.get("date_source"), "cli_arg")

    def test_date_arg_hyphen(self):
        """--date YYYY-MM-DD must be accepted."""
        rc = self._run_main(["--date", "2099-01-01"])
        self.assertEqual(rc, 0)
        meta = self._load_output().get("_Meta", {})
        self.assertEqual(meta.get("target_date"), "2099-01-01")

    def test_env_var_date_fallback(self):
        """DAILY_TARGET_DATE env var must be used when --date not passed."""
        os.environ["DAILY_TARGET_DATE"] = "20991231"
        rc = self._run_main([])
        self.assertEqual(rc, 0)
        meta = self._load_output().get("_Meta", {})
        self.assertEqual(meta.get("target_date"), "2099-12-31")
        self.assertEqual(meta.get("date_source"), "env_DAILY_TARGET_DATE")

    def test_without_date_kline_fallback(self):
        """Without --date or env, collector runs (kline_detection fallback)."""
        rc = self._run_main([])
        self.assertEqual(rc, 0)
        data = self._load_output()
        self.assertIn("Stocks", data)
        self.assertIn("_Meta", data)
        self.assertEqual(data["_Meta"].get("date_source"), "kline_detection")

    def test_skip_kline_compatible_with_date(self):
        """--skip-kline and --date must be compatible."""
        rc = self._run_main(["--date", "20990101", "--skip-kline"])
        self.assertEqual(rc, 0)
        meta = self._load_output().get("_Meta", {})
        self.assertEqual(meta.get("target_date"), "2099-01-01")
        self.assertEqual(meta.get("date_source"), "cli_arg")

    def test_invalid_date_format_hard_fail(self):
        """Invalid --date format (non-YYYYMMDD) must hard-fail with sys.exit(1)."""
        rc = self._run_main(["--date", "not-a-date"])
        self.assertNotEqual(rc, 0)

    def test_invalid_date_length_hard_fail(self):
        """Wrong-length --date must hard-fail (e.g. 209901, 8 chars required)."""
        rc = self._run_main(["--date", "209901"])
        self.assertNotEqual(rc, 0)

    def test_metadata_contract(self):
        """--date must flow into trade_date and data_date."""
        rc = self._run_main(["--date", "20990101"])
        self.assertEqual(rc, 0)
        meta = self._load_output().get("_Meta", {})
        self.assertEqual(meta.get("trade_date"), "2099-01-01")
        self.assertEqual(meta.get("data_date"), "2099-01-01")

    def test_env_invalid_date_not_hard_fail(self):
        """Invalid DAILY_TARGET_DATE env value must WARN, not hard-fail (env not CLI)."""
        os.environ["DAILY_TARGET_DATE"] = "invalid"
        rc = self._run_main([])
        self.assertEqual(rc, 0)  # No sys.exit for env var
        meta = self._load_output().get("_Meta", {})
        # Invalid env was ignored; date_source falls back to kline_detection
        self.assertEqual(meta.get("date_source"), "kline_detection")
        # target_date must be empty (no valid date from ignored env)
        self.assertEqual(meta.get("target_date"), "")

    def test_output_has_correct_structure(self):
        """Output JSON must have _Meta with categories_collected."""
        rc = self._run_main(["--date", "20990101"])
        self.assertEqual(rc, 0)
        data = self._load_output()
        self.assertIn("Stocks", data)
        self.assertIn("Financials", data)
        self.assertIn("FundFlows", data)
        self.assertIn("Margins", data)
        self.assertIn("Sectors", data)
        self.assertIn("categories_collected", data.get("_Meta", {}))


class TestBatchDataCollectorContractSource(unittest.TestCase):
    """Source-level contract checks (no execution, no network)."""

    def setUp(self):
        self.source = COLLECTOR_PY.read_text(encoding="utf-8")

    def test_source_has_date_parser(self):
        """Source must contain --date argument definition."""
        self.assertIn('parser.add_argument("--date"', self.source)

    def test_source_normalizes_date(self):
        """Source must normalize date with replace('-', '')."""
        self.assertIn('date_compact = date_arg.replace("-", "")', self.source)

    def test_source_supports_env_var(self):
        """Source must check DAILY_TARGET_DATE env var as fallback."""
        self.assertIn("DAILY_TARGET_DATE", self.source)

    def test_source_invalid_date_hard_fail(self):
        """Source must hard-fail on explicit invalid --date (sys.exit, not silent)."""
        self.assertIn("if args.date:", self.source)


if __name__ == "__main__":
    unittest.main()
