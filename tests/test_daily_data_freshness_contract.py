"""Contract tests for daily data freshness gate (F-FIX-DATA-FRESHNESS-20260616).

Tests the core fix for the P0 root cause: stale moneyflow data being
mistaken for fresh, and retry/closure/DQ not catching the gap.

No real network or market data dependency. Uses importlib + mocking + temp files.
"""
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parents[1]


def _import_from_path(rel_path, module_name):
    """Import a module from file path."""
    path = ROOT / rel_path
    # Add parent dirs to sys.path for local imports
    parent_dir = str(path.parent)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    # Also add the 监督机制 dir for dq_issue_classifier
    supervision_dir = str(ROOT / "代码文件" / "监督机制")
    if supervision_dir not in sys.path:
        sys.path.insert(0, supervision_dir)
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    mod = importlib.util.module_from_spec(spec)
    mod.__file__ = str(path)
    spec.loader.exec_module(mod)
    return mod


class TestCachedDataSourceFreshness(unittest.TestCase):
    """CachedDataSource L1 freshness gate — the P0 root cause fix."""

    @classmethod
    def setUpClass(cls):
        cls.cds_mod = _import_from_path(
            "代码文件/lib/cached_data_source.py",
            "cached_data_source"
        )
        # Need to set ROOT to a temp dir for test isolation
        cls.cds_mod.TUSHARE_DIR = Path(tempfile.mkdtemp())

    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp())
        self.moneyflow_dir = self.tmp_dir / "moneyflow"
        self.moneyflow_dir.mkdir(parents=True, exist_ok=True)
        # Override the module-level TUSHARE_DIR
        self.cds_mod.TUSHARE_DIR = self.tmp_dir

    def _make_moneyflow_file(self, code, dates):
        """Create a moneyflow file with given trade_dates."""
        path = self.moneyflow_dir / f"{code}.json"
        records = [{"trade_date": d, "net_mf_amount": 100.0} for d in dates]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(records, f)
        return path

    def test_moneyflow_fresh_when_max_date_equals_target(self):
        """P0: moneyflow max_date == target_date → fresh."""
        self._make_moneyflow_file("600114", ["20260616", "20260615"])
        ds = self.cds_mod.CachedDataSource(target_date="20260616")
        result = ds.get_moneyflow("600114")
        self.assertEqual(result["freshness"], "fresh")
        self.assertEqual(result["source"], "tushare-local")

    def test_moneyflow_stale_when_max_date_below_target(self):
        """P0: moneyflow max_date < target_date → stale, not fresh."""
        self._make_moneyflow_file("600114", ["20260615"])
        ds = self.cds_mod.CachedDataSource(target_date="20260616")
        result = ds.get_moneyflow("600114")
        self.assertEqual(result["freshness"], "stale",
                         "Stale moneyflow must NOT be marked fresh")
        self.assertEqual(result["source"], "tushare-local-stale",
                         "Source must be tushare-local-stale for stale data")
        self.assertIn("max_date=20260615 < target_date=20260616",
                      result.get("stale_reason", ""))

    def test_moneyflow_stale_counts_not_tushare_hit(self):
        """P0: stale moneyflow should NOT increment tushare_hit stat."""
        self._make_moneyflow_file("600114", ["20260615"])
        ds = self.cds_mod.CachedDataSource(target_date="20260616")
        ds.get_moneyflow("600114")
        self.assertEqual(ds.stats["tushare_hit"], 0,
                         "Stale data must not count as tushare_hit")
        self.assertEqual(ds.stats["stale_count"], 1,
                         "Stale data must increment stale_count")

    def test_moneyflow_no_target_date_backward_compat(self):
        """Without target_date, existing behavior unchanged (fresh)."""
        self._make_moneyflow_file("600114", ["20260615"])
        ds = self.cds_mod.CachedDataSource()  # no target_date
        result = ds.get_moneyflow("600114")
        self.assertEqual(result["freshness"], "fresh",
                         "No target_date → old behavior: file exists = fresh")

    def test_daily_basic_freshness_check(self):
        """P0: daily_basic also has target_date gate."""
        path = self.tmp_dir / "daily_basic"
        path.mkdir(parents=True, exist_ok=True)
        records = [{"trade_date": "20260615"}]
        with open(path / "600114.json", "w", encoding="utf-8") as f:
            json.dump(records, f)
        ds = self.cds_mod.CachedDataSource(target_date="20260616")
        result = ds.get_daily_basic("600114")
        self.assertEqual(result["freshness"], "stale",
                         "Stale daily_basic must be stale")

    def test_moneyflow_no_file_returns_unavailable(self):
        """No moneyflow file at all → miss."""
        ds = self.cds_mod.CachedDataSource(target_date="20260616")
        result = ds.get_moneyflow("NOTEXIST")
        self.assertEqual(result["freshness"], "stale")
        self.assertEqual(result["source"], "unavailable")

    def test_moneyflow_env_target_date(self):
        """DAILY_TARGET_DATE env var used when no constructor arg."""
        self._make_moneyflow_file("600114", ["20260615"])
        with patch.dict(os.environ, {"DAILY_TARGET_DATE": "20260616"}):
            ds = self.cds_mod.CachedDataSource()
            result = ds.get_moneyflow("600114")
            self.assertEqual(result["freshness"], "stale")


class TestRetryCheckReady(unittest.TestCase):
    """run_daily_data_retry_once.py check_ready() — the P0 amplifier fix."""

    @classmethod
    def setUpClass(cls):
        cls.retry_mod = _import_from_path(
            "scripts/run_daily_data_retry_once.py",
            "run_daily_data_retry_once"
        )

    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp())
        self.status_dir = self.tmp_dir / "status"
        self.status_dir.mkdir(parents=True, exist_ok=True)
        self.retry_mod.STATUS_DIR = str(self.status_dir)

    def _write_ready(self, ready, pipeline_status="PASS"):
        """Write a test ready.json."""
        data = {
            "date": "20260616",
            "ready": ready,
            "pipeline_status": pipeline_status,
            "attempt": 1,
            "ready_at": "2026-06-16T16:30:00+00:00",
        }
        rp = self.status_dir / "20260616.ready.json"
        with open(rp, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def test_ready_true_pass(self):
        """P0: ready=true pipeline_status=PASS → check_ready returns True."""
        self._write_ready(True, "PASS")
        self.assertTrue(self.retry_mod.check_ready("20260616"))

    def test_ready_true_block(self):
        """P0: ready=true but pipeline_status=BLOCK → check_ready returns False."""
        self._write_ready(True, "BLOCK")
        self.assertFalse(self.retry_mod.check_ready("20260616"),
                         "BLOCK pipeline must not be treated as ready")

    def test_ready_false_pass(self):
        """P0: ready=false → check_ready returns False even if pipeline_status=PASS."""
        self._write_ready(False, "PASS")
        self.assertFalse(self.retry_mod.check_ready("20260616"),
                         "ready=false must not be treated as ready")

    def test_ready_false_block(self):
        """P0: the actual 20260616 scenario — ready=false, BLOCK → False."""
        self._write_ready(False, "BLOCK")
        self.assertFalse(self.retry_mod.check_ready("20260616"))

    def test_no_ready_file(self):
        """No ready.json → False."""
        self.assertFalse(self.retry_mod.check_ready("99999999"))


class TestDQFundFlowFreshCoverage(unittest.TestCase):
    """check_data_quality.py fundflow target_date coverage — the P1 amplifier fix."""

    @classmethod
    def setUpClass(cls):
        cls.dq_mod = _import_from_path(
            "代码文件/监督机制/check_data_quality.py",
            "check_data_quality"
        )
        # Store original THRESHOLDS
        cls._orig_daily_targets = cls.dq_mod.DAILY_TARGETS

    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp())
        self.data_dir = self.tmp_dir / "数据"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.dq_mod.DATA_DIR = str(self.data_dir)
        self.dq_mod.KLINE_CACHE_DIR = str(self.data_dir / "kline_cache")
        self.dq_mod.DAILY_TARGETS = str(self.tmp_dir / "daily_report_targets.json")

    def _write_data_full(self, fundflows, target_date="20260616", scope_codes=None):
        """Write a data_full.json with FundFlows section."""
        if scope_codes:
            stocks = [{"Code": c, "Price": 10.0, "KClose": [10.0]*60, "Name": c} for c in scope_codes]
        else:
            stocks = []
        data = {
            "_Meta": {
                "target_date": target_date,
                "trade_date": target_date,
                "cache_stats": {"tushare_hit": 100, "cache_hit": 10,
                                "pipeline_hit": 5, "miss": 20},
            },
            "Stocks": stocks,
            "FundFlows": fundflows,
        }
        with open(self.data_dir / "data_full.json", "w", encoding="utf-8") as f:
            json.dump(data, f)

    def _write_targets(self, codes):
        """Write daily_report_targets.json."""
        targets = {
            "active_targets": [
                {"code": c, "enabled": True} for c in codes
            ]
        }
        with open(self.dq_mod.DAILY_TARGETS, "w", encoding="utf-8") as f:
            json.dump(targets, f)

    def test_fundflow_fresh_coverage_all_present(self):
        """P1: all codes have target_date in FundFlows → fresh coverage 100."""
        self._write_targets(["600114", "603019"])
        self._write_data_full({
            "600114": [{"trade_date": "20260616", "net_mf_amount": 100}],
            "603019": [{"trade_date": "20260616", "net_mf_amount": 200}],
        }, target_date="20260616")
        issues, metrics = self.dq_mod.check_data_full()
        self.assertEqual(metrics.get("fundflow_fresh_coverage"), 100.0)
        self.assertEqual(metrics.get("fundflow_stale_codes"), [])
        self.assertEqual(metrics.get("fundflow_missing_codes"), [])

    def test_fundflow_stale_not_fresh_coverage(self):
        """P1: FundFlows has codes but no target_date → fresh coverage 0, stale."""
        self._write_targets(["600114"])
        self._write_data_full({
            "600114": [{"trade_date": "20260615", "net_mf_amount": 100}],
        }, target_date="20260616")
        issues, metrics = self.dq_mod.check_data_full()
        self.assertEqual(metrics.get("fundflow_fresh_coverage"), 0.0,
                         "No target_date record → fresh coverage must be 0")
        self.assertIn("600114", metrics.get("fundflow_stale_codes", []),
                      "600114 must be in stale_codes")

    def test_fundflow_missing_code(self):
        """P1: code absent from FundFlows → in missing_codes."""
        self._write_targets(["600114", "999999"])
        self._write_data_full({
            "600114": [{"trade_date": "20260616", "net_mf_amount": 100}],
        }, target_date="20260616")
        issues, metrics = self.dq_mod.check_data_full()
        self.assertIn("999999", metrics.get("fundflow_missing_codes", []),
                      "Code without FundFlows entry must be in missing_codes")
        self.assertEqual(metrics.get("fundflow_fresh_coverage"), 50.0)

    def test_fundflow_warn_when_stale_for_active_target(self):
        """P1: stale fundflow for active target must produce DQ-W3 or DQ-W3a."""
        self._write_targets(["600114"])
        self._write_data_full({
            "600114": [{"trade_date": "20260615", "net_mf_amount": 100}],
        }, target_date="20260616")
        issues, _ = self.dq_mod.check_data_full()
        warn_ids = [i["id"] for i in issues]
        has_w3_warn = any("DQ-W3" in iid for iid in warn_ids)
        self.assertTrue(has_w3_warn,
                        "Stale fundflow for active target must produce DQ-W3 warning")


class TestClosureFundFlowGate(unittest.TestCase):
    """verify_daily_production_closure.py fund_flow_cache gate — the P1 closure fix."""

    @classmethod
    def setUpClass(cls):
        cls.closure_mod = _import_from_path(
            "scripts/verify_daily_production_closure.py",
            "verify_daily_production_closure"
        )

    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp())
        self.ff_dir = self.tmp_dir / "fund_flow_cache"
        self.ff_dir.mkdir(parents=True, exist_ok=True)
        self.closure_mod.FUND_FLOW_CACHE_DIR = self.ff_dir
        # Only override DATA_FULL_PATH in the module
        self.closure_mod.DATA_FULL_PATH = self.tmp_dir / "data_full.json"

    def _write_targets(self, codes):
        """Write daily_report_targets.json."""
        path = self.tmp_dir / "daily_report_targets.json"
        targets = {
            "active_targets": [
                {"code": c, "enabled": True} for c in codes
            ]
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(targets, f)
        # Need to set DAILY_TARGETS in the module
        self.closure_mod.DAILY_TARGETS = path

    def _write_ff_cache(self, code, dates):
        """Write fund_flow_cache/{code}.json with given dates."""
        records = [{"date": d, "main_force_net": 100.0} for d in dates]
        path = self.ff_dir / f"{code}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(records, f)

    def _write_data_full(self, fundflows):
        """Write data_full.json with FundFlows."""
        data = {"FundFlows": fundflows}
        with open(self.closure_mod.DATA_FULL_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def test_ff_cache_match_all_present(self):
        """All active targets have target_date in fund_flow_cache."""
        self._write_targets(["600114"])
        self._write_ff_cache("600114", ["20260616", "20260615"])
        match, total, missing = self.closure_mod.check_fund_flow_cache_match("20260616", ["600114"])
        self.assertEqual(match, 1)
        self.assertEqual(total, 1)
        self.assertEqual(missing, [])

    def test_ff_cache_missing_target_date(self):
        """Active target missing target_date in fund_flow_cache."""
        self._write_targets(["600114"])
        self._write_ff_cache("600114", ["20260615"])
        match, total, missing = self.closure_mod.check_fund_flow_cache_match("20260616", ["600114"])
        self.assertEqual(match, 0)
        self.assertIn("600114", missing)

    def test_ff_cache_no_file(self):
        """Active target has no fund_flow_cache file."""
        self._write_targets(["600114"])
        match, total, missing = self.closure_mod.check_fund_flow_cache_match("20260616", ["600114"])
        self.assertIn("600114", missing)

    def test_data_full_fundflows_match(self):
        """data_full.FundFlows has target_date for active target."""
        self._write_targets(["600114"])
        self._write_data_full({
            "600114": [{"trade_date": "20260616", "net_mf_amount": 100}]
        })
        match, total, missing = self.closure_mod.check_data_full_fundflows_match("20260616", ["600114"])
        self.assertEqual(match, 1)

    def test_data_full_fundflows_no_target(self):
        """data_full.FundFlows has code but no target_date."""
        self._write_targets(["600114"])
        self._write_data_full({
            "600114": [{"trade_date": "20260615", "net_mf_amount": 100}]
        })
        match, total, missing = self.closure_mod.check_data_full_fundflows_match("20260616", ["600114"])
        self.assertEqual(match, 0)
        self.assertIn("600114", missing)


if __name__ == "__main__":
    unittest.main()
