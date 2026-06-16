#!/usr/bin/env python3
"""Tests for daily_orchestrator — K-line readiness fix (F-SCHEDULE G3 Task 1).

Verifies:
1. check_v36_data_readiness searches ALL kline_cache records, not just kd[-1]
2. Unsorted cache still matches target date correctly
3. Missing date returns False for that stock
4. extract_stock_daily_context sorts kline data by date before taking kd[-4:]
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "代码文件" / "数据"


class TestV36KlineReadinessAnyPosition(unittest.TestCase):
    """check_v36_data_readiness must find target date at any position in kline_cache."""

    def setUp(self):
        # Patch daily_orchestrator paths to test isolation
        self.tmpdir = Path(tempfile.mkdtemp())
        sys.path.insert(0, str(ROOT))
        # Create a minimal pigeon_config with one stock
        self.pigeon_dir = self.tmpdir / "代码文件" / "信鸽信息采集"
        self.pigeon_dir.mkdir(parents=True)
        cfg = {"target_stocks": [{"code": "000001", "name": "测试平安"}]}
        (self.pigeon_dir / "pigeon_config.json").write_text(
            json.dumps(cfg), encoding="utf-8")

        # Create kline_cache dir
        self.kline_dir = self.tmpdir / "代码文件" / "数据" / "kline_cache"
        self.kline_dir.mkdir(parents=True)

        # Create manifest with today's date
        self.manifest_dir = self.tmpdir / "代码文件" / "数据" / "tushare"
        self.manifest_dir.mkdir(parents=True)
        mf = {"updated": datetime.now(timezone.utc).isoformat()}
        (self.manifest_dir / "manifest.json").write_text(
            json.dumps(mf), encoding="utf-8")

    def _patch_module(self):
        """Import daily_orchestrator and patch its ROOT."""
        from 代码文件.tools import daily_orchestrator as mod
        mod.ROOT = str(self.tmpdir)
        mod.DATA_CACHE_DIR = str(self.tmpdir / "代码文件" / "数据")
        mod.HOLIDAY_FILE = str(self.tmpdir / "holidays_2026.csv")
        mf = {"updated": datetime.now(timezone.utc).isoformat()}
        (Path(mod.DATA_CACHE_DIR) / "tushare" / "manifest.json").parent.mkdir(parents=True, exist_ok=True)
        with open(Path(mod.DATA_CACHE_DIR) / "tushare" / "manifest.json", "w") as f:
            json.dump(mf, f)
        return mod

    def test_target_date_not_at_last_position_still_matches(self):
        """Kline data for target date at position 0 (not last) must still match."""
        mod = self._patch_module()
        target_date = "2026-06-16"
        target_compact = "20260616"

        # Write kline with target date at start, older data after (unsorted)
        kd = [
            {"date": "2026-06-16", "open": 10.0, "close": 10.5, "high": 10.8, "low": 9.9, "volume": 1000000, "change_pct": 0.5},
            {"date": "2026-06-15", "open": 9.8, "close": 10.0, "high": 10.2, "low": 9.7, "volume": 800000, "change_pct": 0.2},
            {"date": "2026-06-12", "open": 9.5, "close": 9.8, "high": 10.0, "low": 9.4, "volume": 700000, "change_pct": 0.3},
        ]
        (self.kline_dir / "000001.json").write_text(json.dumps(kd), encoding="utf-8")

        status, detail = mod.check_v36_data_readiness(target_date)
        kbs = detail.get("kline_by_stock", {})
        self.assertIn("000001", kbs)
        self.assertTrue(kbs["000001"].get("match"),
                        f"Target date {target_date} in kline_cache at non-last position should match. Got: {kbs['000001']}")
        self.assertEqual(kbs["000001"].get("matched_date"), target_date)

    def test_target_date_at_last_position_still_matches(self):
        """Kline data for target date at last position (normal case) must still match."""
        mod = self._patch_module()
        target_date = "2026-06-16"

        kd = [
            {"date": "2026-06-12", "open": 9.5, "close": 9.8, "high": 10.0, "low": 9.4, "volume": 700000, "change_pct": 0.3},
            {"date": "2026-06-15", "open": 9.8, "close": 10.0, "high": 10.2, "low": 9.7, "volume": 800000, "change_pct": 0.2},
            {"date": "2026-06-16", "open": 10.0, "close": 10.5, "high": 10.8, "low": 9.9, "volume": 1000000, "change_pct": 0.5},
        ]
        (self.kline_dir / "000001.json").write_text(json.dumps(kd), encoding="utf-8")

        status, detail = mod.check_v36_data_readiness(target_date)
        kbs = detail.get("kline_by_stock", {})
        self.assertTrue(kbs["000001"].get("match"))
        self.assertEqual(kbs["000001"].get("matched_date"), target_date)

    def test_missing_target_date_does_not_match(self):
        """When target date is absent from cache, match must be False."""
        mod = self._patch_module()
        target_date = "2026-06-16"

        kd = [
            {"date": "2026-06-12", "open": 9.5, "close": 9.8, "high": 10.0, "low": 9.4, "volume": 700000, "change_pct": 0.3},
            {"date": "2026-06-15", "open": 9.8, "close": 10.0, "high": 10.2, "low": 9.7, "volume": 800000, "change_pct": 0.2},
        ]
        (self.kline_dir / "000001.json").write_text(json.dumps(kd), encoding="utf-8")

        status, detail = mod.check_v36_data_readiness(target_date)
        kbs = detail.get("kline_by_stock", {})
        self.assertFalse(kbs["000001"].get("match"))
        # Should have a reason explaining the mismatch
        self.assertIn("未找到", kbs["000001"].get("reason", ""))

    def test_extract_stock_daily_context_sorts_kline_data(self):
        """extract_stock_daily_context must sort unsorted kline by date before taking kd[-4:]."""
        mod = self._patch_module()
        target_date = "20260616"

        # Reverse order: newest first
        kd = [
            {"date": "2026-06-16", "open": 10.0, "close": 10.5, "high": 10.8, "low": 9.9, "volume": 1000000, "change_pct": 0.5},
            {"date": "2026-06-15", "open": 9.8, "close": 10.0, "high": 10.2, "low": 9.7, "volume": 800000, "change_pct": 0.2},
            {"date": "2026-06-12", "open": 9.5, "close": 9.8, "high": 10.0, "low": 9.4, "volume": 700000, "change_pct": 0.3},
            {"date": "2026-06-11", "open": 9.3, "close": 9.5, "high": 9.7, "low": 9.2, "volume": 600000, "change_pct": 0.2},
        ]
        (self.kline_dir / "000001.json").write_text(json.dumps(kd), encoding="utf-8")

        ctx = mod.extract_stock_daily_context(target_date)
        self.assertIn("000001", ctx)
        days = ctx["000001"]["days"]
        # After sort, days should be in date-ascending order (oldest first)
        self.assertEqual(len(days), 4)
        # Last day should be 2026-06-16 (most recent)
        self.assertEqual(days[-1]["date"], "2026-06-16")
        # The 4-day window should be the last 4 records after sorting
        self.assertEqual(days[0]["date"], "2026-06-11")
        self.assertEqual(days[-1]["date"], "2026-06-16")

    def test_empty_kline_file_does_not_crash(self):
        """Empty kline cache file must not crash readiness check."""
        mod = self._patch_module()
        target_date = "2026-06-16"

        (self.kline_dir / "000001.json").write_text("[]", encoding="utf-8")

        status, detail = mod.check_v36_data_readiness(target_date)
        kbs = detail.get("kline_by_stock", {})
        self.assertFalse(kbs["000001"].get("match"))

    def test_non_list_kline_does_not_crash(self):
        """Non-list kline cache (e.g. dict) must not crash readiness check."""
        mod = self._patch_module()
        target_date = "2026-06-16"

        (self.kline_dir / "000001.json").write_text('{"error": "bad data"}', encoding="utf-8")

        status, detail = mod.check_v36_data_readiness(target_date)
        kbs = detail.get("kline_by_stock", {})
        self.assertFalse(kbs["000001"].get("match"))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)


class TestV36ReadinessYYYYMMDDSupport(unittest.TestCase):
    """check_v36_data_readiness must support both YYYY-MM-DD and YYYYMMDD date formats."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        sys.path.insert(0, str(ROOT))
        self.pigeon_dir = self.tmpdir / "代码文件" / "信鸽信息采集"
        self.pigeon_dir.mkdir(parents=True)
        cfg = {"target_stocks": [{"code": "000001", "name": "测试平安"}]}
        (self.pigeon_dir / "pigeon_config.json").write_text(
            json.dumps(cfg), encoding="utf-8")
        self.kline_dir = self.tmpdir / "代码文件" / "数据" / "kline_cache"
        self.kline_dir.mkdir(parents=True)

    def _patch_module(self):
        from 代码文件.tools import daily_orchestrator as mod
        mod.ROOT = str(self.tmpdir)
        mod.DATA_CACHE_DIR = str(self.tmpdir / "代码文件" / "数据")
        mod.HOLIDAY_FILE = str(self.tmpdir / "holidays_2026.csv")
        self._create_manifest(mod)
        return mod

    def _create_manifest(self, mod):
        mf_path = Path(mod.DATA_CACHE_DIR) / "tushare" / "manifest.json"
        mf_path.parent.mkdir(parents=True, exist_ok=True)
        with open(mf_path, "w") as f:
            json.dump({"updated": "2026-06-16T12:00:00"}, f)

    def test_compact_date_format(self):
        """YYYYMMDD input must match kline_cache date field."""
        mod = self._patch_module()
        kd = [
            {"date": "2026-06-16", "open": 10.0, "close": 10.5, "high": 10.8, "low": 9.9, "volume": 1000000, "change_pct": 0.5},
        ]
        (self.kline_dir / "000001.json").write_text(json.dumps(kd), encoding="utf-8")

        status, detail = mod.check_v36_data_readiness("20260616")
        kbs = detail.get("kline_by_stock", {})
        self.assertTrue(kbs["000001"].get("match"))

    def test_dash_date_format(self):
        """YYYY-MM-DD input must match kline_cache date field."""
        mod = self._patch_module()
        kd = [
            {"date": "2026-06-16", "open": 10.0, "close": 10.5, "high": 10.8, "low": 9.9, "volume": 1000000, "change_pct": 0.5},
        ]
        (self.kline_dir / "000001.json").write_text(json.dumps(kd), encoding="utf-8")

        status, detail = mod.check_v36_data_readiness("2026-06-16")
        kbs = detail.get("kline_by_stock", {})
        self.assertTrue(kbs["000001"].get("match"))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
