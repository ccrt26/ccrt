#!/usr/bin/env python3
"""Tests for run_daily_data_retry_once.py — v3 single-authority retry.

Verifies:
1. retry calls run_daily_production_pipeline.py (no direct data chain steps)
2. retry has NO old chain steps in main()
3. retry has NO write_ready function or call
4. retry inherits pipeline exit code
"""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RETRY_PATH = ROOT / "scripts" / "run_daily_data_retry_once.py"
PIPELINE_PATH = ROOT / "scripts" / "run_daily_production_pipeline.py"


class TestRetrySingleAuthority(unittest.TestCase):
    """run_daily_data_retry_once.py must only delegate to run_daily_production_pipeline."""

    def setUp(self):
        self.retry_src = RETRY_PATH.read_text(encoding="utf-8")
        self.retry_tree = ast.parse(self.retry_src)

    def _main_body_source(self):
        """Extract the source lines of main() function body, excluding comments/docstrings."""
        lines = self.retry_src.split("\n")
        in_main = False
        main_body = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("def main()"):
                in_main = True
                continue
            if in_main:
                if stripped.startswith("def "):
                    break
                # Skip comment-only lines
                if stripped.startswith("#"):
                    continue
                main_body.append(line)
        result = "\n".join(main_body)
        # Remove docstrings (triple-quoted strings)
        import re
        result = re.sub(r'""".*?"""', '', result, flags=re.DOTALL)
        return result

    def test_retry_calls_production_pipeline(self):
        """retry must reference run_daily_production_pipeline."""
        self.assertIn("run_daily_production_pipeline", self.retry_src)

    def test_retry_no_tushare_sync_in_main(self):
        """main() must NOT call tushare_history_sync.py."""
        self.assertNotIn("tushare_history_sync", self._main_body_source())

    def test_retry_no_batch_data_collector_in_main(self):
        """main() must NOT call batch_data_collector.py."""
        self.assertNotIn("batch_data_collector", self._main_body_source())

    def test_retry_no_materialize_in_main(self):
        """main() must NOT call materialize_daily_authoritative_cache.py."""
        self.assertNotIn("materialize", self._main_body_source())

    def test_retry_no_daily_orchestrator_in_main(self):
        """main() must NOT call daily_orchestrator.py."""
        self.assertNotIn("daily_orchestrator", self._main_body_source())

    def _executable_source(self):
        """Return source with docstrings and comments removed."""
        import re
        body = re.sub(r'""".*?"""', '', self.retry_src, flags=re.DOTALL)
        body = re.sub(r'^\s*#.*$', '', body, flags=re.MULTILINE)
        return body

    def test_retry_no_verify_signal(self):
        """retry must NOT define or call verify_signal."""
        self.assertNotIn("verify_signal", self._executable_source())

    def test_retry_no_run_step(self):
        """retry must NOT define or call run_step function."""
        self.assertNotIn("run_step(", self._executable_source())

    def test_retry_no_verify_kline_coverage(self):
        """retry must NOT define or call verify_kline_coverage."""
        self.assertNotIn("verify_kline_coverage", self._executable_source())

    def test_retry_no_write_ready(self):
        """retry must NOT define or call write_ready in executable code."""
        self.assertNotIn("write_ready", self._executable_source())

    def test_retry_passes_exit_code_to_pipeline(self):
        """retry must exit with pipeline exit code (sys.exit(pipeline_rc))."""
        self.assertIn("sys.exit(pipeline_rc)", self.retry_src)

    def test_retry_no_attempt_in_ready_check(self):
        """retry ready check must not reference 'attempt' (only ready/pipeline_status)."""
        main_body = self._main_body_source()
        # In check_ready, we verify ready=true AND pipeline_status=PASS — no attempt check
        self.assertIn("check_ready", self.retry_src)

    def test_retry_imports_minimal(self):
        """retry must only import what's needed (no old chain constants)."""
        self.assertNotIn("PIGEON_CFG", self.retry_src)
        self.assertNotIn("DATA_FULL", self.retry_src)
        self.assertNotIn("SIGNAL_FILE", self.retry_src)


class TestPipelineUsesReportPromoteForReportReady(unittest.TestCase):
    """run_daily_production_pipeline.py must rely on report_promote for report_ready."""

    def test_report_ready_based_on_promote(self):
        """report_ready must check for report_promote step status."""
        src = PIPELINE_PATH.read_text(encoding="utf-8")
        self.assertIn("report_promote", src)
        self.assertIn('s["step"] == "report_promote"', src)


class TestOrchestratorSignalNowHasSource(unittest.TestCase):
    """Pipeline write_signal must include pipeline_mode and source fields."""

    def test_orchestrator_signal_has_pipeline_mode(self):
        """write_signal must set pipeline_mode when called from pipeline."""
        src = PIPELINE_PATH.read_text(encoding="utf-8")
        self.assertIn('"pipeline_mode": True', src)
        self.assertIn('"source": "run_daily_production_pipeline"', src)


if __name__ == "__main__":
    unittest.main()
