"""Tests for run_daily_report_html_only.py — fmt_num helper and ma20=None fix.

Verifies:
1. fmt_num() handles None → fallback string, number → formatted string
2. generate_one() does not crash when ma20_support_price is None (core bug fix)
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class TestFmtNum(unittest.TestCase):
    """Unit tests for the fmt_num() safe formatting helper."""

    @classmethod
    def setUpClass(cls):
        if str(ROOT / "scripts") not in sys.path:
            sys.path.insert(0, str(ROOT / "scripts"))
        import run_daily_report_html_only as m
        cls.mod = m

    def test_number_default_format(self):
        self.assertEqual(self.mod.fmt_num(10.5), "10.50")

    def test_number_zero(self):
        self.assertEqual(self.mod.fmt_num(0.0), "0.00")

    def test_none_default_fallback(self):
        self.assertEqual(self.mod.fmt_num(None), "—")

    def test_none_custom_fallback(self):
        self.assertEqual(self.mod.fmt_num(None, fallback="未提供"), "未提供")

    def test_integer_value(self):
        self.assertEqual(self.mod.fmt_num(5), "5.00")

    def test_custom_format(self):
        self.assertEqual(self.mod.fmt_num(10.555, fmt=".1f"), "10.6")


class TestGenerateOneNoneMa20(unittest.TestCase):
    """generate_one must not crash when ma20_support_price is None."""

    @classmethod
    def setUpClass(cls):
        if str(ROOT / "scripts") not in sys.path:
            sys.path.insert(0, str(ROOT / "scripts"))

    def setUp(self):
        # Create a temp dir for signal file and mock report output
        self.tmpdir = Path(tempfile.mkdtemp())
        signal_dir = self.tmpdir / ".claude"
        signal_dir.mkdir(parents=True)
        signal_path = signal_dir / "signal_daily_report.json"
        signal_path.write_text(json.dumps({
            "date": "20260615",
            "data_ready": True,
            "signal": "daily_report",
            "mode": "daily",
            "pipeline_mode": True,
            "source": "test",
            "timestamp": "2026-06-15T00:00:00",
        }, ensure_ascii=False))

        import run_daily_report_html_only as m
        self.mod = m
        self._orig_signal = m.SIGNAL
        self._orig_report_dir = m.REPORT_DIR
        m.SIGNAL = signal_path
        m.REPORT_DIR = self.tmpdir / "mock_reports"

    def tearDown(self):
        self.mod.SIGNAL = self._orig_signal
        self.mod.REPORT_DIR = self._orig_report_dir
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_baseline(self, _code, _name, _date):
        """Return resolved + baseline WITHOUT ma20_support_price."""
        resolved = {
            "baseline_id": "999999_W2026W25",
            "result": "PASS",
            "baseline_file": str(self.tmpdir / "fake_baseline.json"),
            "valid_until": "2026-07-01",
        }
        bl = {
            "key_support_price": 10.0,
            "key_pressure_price": 12.5,
            "stop_loss_price": 9.0,
            "target_price": 13.0,
            "core_thesis": "测试基线",
            "valid_until": "2026-07-01",
            "key_fields": {},
        }
        return resolved, bl

    def test_no_typeerror_on_missing_ma20(self):
        """generate_one completes without TypeError when ma20_support_price is None."""
        with (
            patch.object(self.mod, "resolve_baseline") as mock_resolve,
            patch.object(self.mod, "row_by_date") as mock_row,
            patch.object(self.mod, "latest_row") as mock_latest,
            patch.object(self.mod, "sector_phase") as mock_sector,
            patch.object(self.mod, "load_signal_winrate") as mock_swr,
        ):
            mock_resolve.side_effect = self._make_baseline
            mock_row.side_effect = [
                {"date": "2026-06-15", "open": 11.0, "close": 11.2, "high": 11.5, "low": 10.8, "volume": 50000000},
                {"date": "2026-06-15", "super_large_net": 100, "large_net": -50, "medium_net": -30, "small_net": -20, "main_force_net": 50},
            ]
            mock_latest.return_value = {"trade_date": "2026-06-12"}
            mock_sector.return_value = ("测试行业", "振荡")
            mock_swr.return_value = {
                "usable": True, "total_samples": 30,
                "avg_t1_winrate": 60.0, "avg_t5_winrate": 55.0,
                "low_sample": False, "signal_count": 5,
            }

            result = self.mod.generate_one("20260615", "999999", "测试")

        self.assertIn("baseline_id", result)
        self.assertEqual(result["baseline_id"], "999999_W2026W25")

    def test_output_contains_fallback_for_ma20(self):
        """Generated md output contains fallback text for missing ma20."""
        with (
            patch.object(self.mod, "resolve_baseline") as mock_resolve,
            patch.object(self.mod, "row_by_date") as mock_row,
            patch.object(self.mod, "latest_row") as mock_latest,
            patch.object(self.mod, "sector_phase") as mock_sector,
            patch.object(self.mod, "load_signal_winrate") as mock_swr,
        ):
            mock_resolve.side_effect = self._make_baseline
            mock_row.side_effect = [
                {"date": "2026-06-15", "open": 11.0, "close": 11.2, "high": 11.5, "low": 10.8, "volume": 50000000},
                {"date": "2026-06-15", "super_large_net": 100, "large_net": -50, "medium_net": -30, "small_net": -20, "main_force_net": 50},
            ]
            mock_latest.return_value = {"trade_date": "2026-06-12"}
            mock_sector.return_value = ("测试行业", "振荡")
            mock_swr.return_value = {
                "usable": True, "total_samples": 30,
                "avg_t1_winrate": 60.0, "avg_t5_winrate": 55.0,
                "low_sample": False, "signal_count": 5,
            }

            result = self.mod.generate_one("20260615", "999999", "测试")

        # Read the generated md file from mock report dir and check for ma20 fallback
        report_dir = self.mod.REPORT_DIR / "测试(999999)"
        md_path = report_dir / "测试(999999)日报_20260615.md"
        self.assertTrue(md_path.exists(), f"md file not found at {md_path}")
        md_content = md_path.read_text(encoding="utf-8")
        self.assertIn("未提供", md_content, "MA20缺失时应显示'未提供'")
        self.assertNotIn("NoneType", md_content, "md内不应出现NoneType异常")

    def test_output_contains_baseline_id(self):
        """Generated md/sidecar contains expected baseline_id."""
        with (
            patch.object(self.mod, "resolve_baseline") as mock_resolve,
            patch.object(self.mod, "row_by_date") as mock_row,
            patch.object(self.mod, "latest_row") as mock_latest,
            patch.object(self.mod, "sector_phase") as mock_sector,
            patch.object(self.mod, "load_signal_winrate") as mock_swr,
        ):
            mock_resolve.side_effect = self._make_baseline
            mock_row.side_effect = [
                {"date": "2026-06-15", "open": 11.0, "close": 11.2, "high": 11.5, "low": 10.8, "volume": 50000000},
                {"date": "2026-06-15", "super_large_net": 100, "large_net": -50, "medium_net": -30, "small_net": -20, "main_force_net": 50},
            ]
            mock_latest.return_value = {"trade_date": "2026-06-12"}
            mock_sector.return_value = ("测试行业", "振荡")
            mock_swr.return_value = {
                "usable": True, "total_samples": 30,
                "avg_t1_winrate": 60.0, "avg_t5_winrate": 55.0,
                "low_sample": False, "signal_count": 5,
            }

            result = self.mod.generate_one("20260615", "999999", "测试")

        self.assertEqual(result["baseline_id"], "999999_W2026W25")

    def test_fallback_note_after_ma20_table_row(self):
        """Verifies that the MA20 row in the md uses the fallback."""
        with (
            patch.object(self.mod, "resolve_baseline") as mock_resolve,
            patch.object(self.mod, "row_by_date") as mock_row,
            patch.object(self.mod, "latest_row") as mock_latest,
            patch.object(self.mod, "sector_phase") as mock_sector,
            patch.object(self.mod, "load_signal_winrate") as mock_swr,
        ):
            mock_resolve.side_effect = self._make_baseline
            mock_row.side_effect = [
                {"date": "2026-06-15", "open": 11.0, "close": 11.2, "high": 11.5, "low": 10.8, "volume": 50000000},
                {"date": "2026-06-15", "super_large_net": 100, "large_net": -50, "medium_net": -30, "small_net": -20, "main_force_net": 50},
            ]
            mock_latest.return_value = {"trade_date": "2026-06-12"}
            mock_sector.return_value = ("测试行业", "振荡")
            mock_swr.return_value = {
                "usable": True, "total_samples": 30,
                "avg_t1_winrate": 60.0, "avg_t5_winrate": 55.0,
                "low_sample": False, "signal_count": 5,
            }

            result = self.mod.generate_one("20260615", "999999", "测试")

        report_dir = self.mod.REPORT_DIR / "测试(999999)"
        md_path = report_dir / "测试(999999)日报_20260615.md"
        md_content = md_path.read_text(encoding="utf-8")
        self.assertIn("MA20支撑", md_content)
        self.assertNotIn("None", md_content)


if __name__ == "__main__":
    unittest.main()
