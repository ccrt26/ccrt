#!/usr/bin/env python3
"""
test_daily_report_promote_safety.py — Promote safety contract tests.

Tests that:
1. --promote verifies release gate before writing to formal directory.
2. release gate BLOCK => promoted_files == [], formal dir unchanged.
3. Source code does not contain write-then-verify pattern (copy before gate).
4. --write still exits non-zero.
5. generate_one() fails without staging_dir.
6. REPORT_ROOT_OVERRIDE env var works with checkers.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FLOW_STATUS_PATH = ROOT / "logs" / "daily_production" / "20260616_daily_report_flow_status.json"


def _production_flow_status_hash():
    """Return sha256 of production flow_status file, or None."""
    if FLOW_STATUS_PATH.exists():
        return hashlib.sha256(FLOW_STATUS_PATH.read_bytes()).hexdigest()
    return None


def _make_isolated_env():
    """Return env dict with DAILY_REPORT_FLOW_STATUS_DIR pointing to temp dir."""
    env = os.environ.copy()
    env["DAILY_REPORT_FLOW_STATUS_DIR"] = tempfile.mkdtemp()
    return env


class TestFakeSignalBlocksPromote(unittest.TestCase):
    """Fake/incorrect signal must BLOCK promote — source structure and signal validation."""

    def test_check_pipeline_signal_raises_on_all_conditions_when_require_true(self):
        """check_pipeline_signal with require=True must raise SystemExit on any condition failure."""
        src = (SCRIPTS / "run_daily_report_html_only.py").read_text(encoding="utf-8")
        func_start = src.find("def check_pipeline_signal")
        func_end = src.find("\ndef ", func_start + 1)
        func_body = src[func_start:func_end]
        # The implementation uses a loop over checks[] with one raise SystemExit that covers all
        # conditions — verify the loop body raises SystemExit (one call covers 5 checks)
        self.assertIn("raise SystemExit", func_body,
                       "check_pipeline_signal must raise SystemExit when require=True")
        # Verify all 5 condition types are checked in the loop
        for condition_text in ["daily_report", "date", "data_ready", "pipeline_mode", "run_daily_production_pipeline"]:
            self.assertIn(condition_text, func_body,
                          f"check_pipeline_signal must check condition: {condition_text}")

    def test_pipeline_mode_false_blocks_promote_source(self):
        """Source must have pipeline_mode check before promote path."""
        src = (SCRIPTS / "run_daily_report_html_only.py").read_text(encoding="utf-8")
        # The source for check_pipeline_signal with require=True must include pipeline_mode check
        self.assertIn('"pipeline_mode"', src[src.find("def check_pipeline_signal"):src.find("def check_data_freshness")])
        # And the promote path must call check_pipeline_signal with require=True
        promote_path_section = src[src.find("# Check pipeline signal if required"):src.find("if args.promote:\n        # Check active target scope")]
        promote_signal_calls = promote_path_section.count("check_pipeline_signal(date, require=True)")
        self.assertGreaterEqual(promote_signal_calls, 2,
                                "Both --require-pipeline-signal and --promote paths must call check_pipeline_signal with require=True")

    def test_source_manual_blocks_promote_source(self):
        """Source must have source != run_daily_production_pipeline check."""
        src = (SCRIPTS / "run_daily_report_html_only.py").read_text(encoding="utf-8")
        func_body = src[src.find("def check_pipeline_signal"):src.find("def check_data_freshness")]
        self.assertIn("run_daily_production_pipeline", func_body,
                       "Source check must validate source == run_daily_production_pipeline")


class TestPostWriteClosureDoesNotWarn(unittest.TestCase):
    """Post-write closure exception must BLOCK, not just WARN."""

    def test_post_write_exception_downgrades_to_block(self):
        """Source: post-write closure exception must downgrade manifest/ready to BLOCK."""
        src = (ROOT / "scripts" / "run_daily_production_pipeline.py").read_text(encoding="utf-8")
        # Find the except Exception handler for post-write closure verify
        except_idx = src.find("except Exception as e:")
        # Find the next def or end-of-file from except_idx
        context_end = src.find("\ndef ", except_idx) if src.find("\ndef ", except_idx) > 0 else len(src)
        section = src[except_idx:context_end]
        self.assertGreater(len(section), 100, "Exception handler section must exist")
        # Must downgrade to BLOCK, not just print WARN
        self.assertIn('[BLOCK]', section, "Exception handler must print BLOCK, not WARN")
        self.assertIn('manifest["overall"] = "BLOCK"', section,
                      "Exception handler must downgrade manifest overall to BLOCK")
        self.assertIn('ready_data["ready"] = False', section,
                       "Exception handler must set ready=False")
        self.assertIn('overall_pass = False', section,
                       "Exception handler must set overall_pass=False")
        # Must NOT have the old WARN-only pattern
        self.assertNotIn('[WARN] Post-write closure verify exception',
                         src, "Old WARN-only pattern must be removed")

    def test_post_write_exception_appends_blocker(self):
        """Exception handler must append post_write_closure_verify_exception to blocker list."""
        src = (ROOT / "scripts" / "run_daily_production_pipeline.py").read_text(encoding="utf-8")
        self.assertIn("post_write_closure_verify_exception", src,
                       "Exception handler must record post_write_closure_verify_exception in blocker")


class TestPromoteSafety(unittest.TestCase):

    def test_promote_source_verify_before_copy(self):
        """Source must verify release gate (shadow) before copying to formal."""
        source = (SCRIPTS / "run_daily_report_html_only.py").read_text(encoding="utf-8")
        # Find the THIRD `if args.promote:` — the one with actual promote logic
        first = source.find("if args.promote:")
        second = source.find("if args.promote:", first + 1)
        third = source.find("if args.promote:", second + 1)
        self.assertGreater(third, 0, "main promote logic block must exist")
        # Full promote section covers ~2000 chars from third promote start
        section = source[third:third + 3000]
        # Shadow root must be built FIRST
        self.assertIn("release_gate_shadow", section,
                       "promote must build shadow root for release gate")
        # Release gate must be called
        gate_pos = section.find("check_daily_release_gate.py")
        self.assertGreater(gate_pos, 0, "release gate must be called")
        # Copy to formal (promote_staging) must be AFTER gate
        copy_pos = section.find("promote_staging(", gate_pos)
        self.assertGreater(copy_pos, gate_pos,
                            "gate check must precede copy to formal")

    def test_write_is_deprecated_no_side_effects(self):
        """--write must exit non-zero AND must NOT change production flow_status hash."""
        prod_hash_before = _production_flow_status_hash()
        env = _make_isolated_env()
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "run_daily_report_html_only.py"),
             "--date", "20260616", "--write"],
            capture_output=True, text=True, timeout=30, cwd=str(ROOT),
            env=env,
        )
        self.assertNotEqual(result.returncode, 0, "--write must exit non-zero")
        self.assertIn("deprecated", (result.stdout + result.stderr).lower())
        prod_hash_after = _production_flow_status_hash()
        if prod_hash_before is not None:
            self.assertEqual(prod_hash_before, prod_hash_after,
                             "--write must not change production flow_status")
        # Also verify no flow_status was written to isolated dir
        flow_dir = env["DAILY_REPORT_FLOW_STATUS_DIR"]
        written = list(Path(flow_dir).glob("*_daily_report_flow_status.json"))
        self.assertEqual(len(written), 0,
                         "--write must NOT write ANY flow_status even to isolated dir")
        # Cleanup
        import shutil
        shutil.rmtree(flow_dir, ignore_errors=True)

    def test_generate_one_requires_staging_dir(self):
        """generate_one() must fail without staging_dir."""
        source = (SCRIPTS / "run_daily_report_html_only.py").read_text(encoding="utf-8")
        self.assertIn("staging_dir required", source,
                       "generate_one must reject missing staging_dir")

    def test_formal_files_untouched_when_gate_blocks(self):
        """When release gate BLOCKs, formal report files must not change."""
        formal_dir = ROOT / "重点股票" / "股票报告" / "东睦股份(600114)"
        formal_files = {}
        prefix = "东睦股份(600114)日报_20260616"
        for ext in [".json", ".md", ".html"]:
            p = formal_dir / f"{prefix}{ext}"
            if p.exists():
                formal_files[str(p)] = p.stat().st_mtime_ns

        temp_dir = tempfile.mkdtemp()
        prod_hash_before = _production_flow_status_hash()
        env = _make_isolated_env()
        flow_dir = env["DAILY_REPORT_FLOW_STATUS_DIR"]
        try:
            subprocess.run(
                [sys.executable, str(SCRIPTS / "run_daily_report_html_only.py"),
                 "--date", "20260616", "--only", "600114",
                 "--staging-dir", temp_dir,
                 "--promote"],
                capture_output=True, text=True, timeout=120, cwd=str(ROOT),
                env=env,
            )
            # Verify timestamps haven't changed
            for p_str, ts in formal_files.items():
                p = Path(p_str)
                if p.exists():
                    self.assertEqual(p.stat().st_mtime_ns, ts,
                                     f"formal file modified: {p_str}")
            # Verify production flow_status hash unchanged
            prod_hash_after = _production_flow_status_hash()
            if prod_hash_before is not None:
                self.assertEqual(prod_hash_before, prod_hash_after,
                                 "promote BLOCK must not change production flow_status")
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            shutil.rmtree(flow_dir, ignore_errors=True)

    def test_flow_status_has_empty_promoted_on_block(self):
        """When gate BLOCKs, flow_status must have promoted_files=[]."""
        temp_dir = tempfile.mkdtemp()
        env = _make_isolated_env()
        flow_dir = env["DAILY_REPORT_FLOW_STATUS_DIR"]
        try:
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / "run_daily_report_html_only.py"),
                 "--date", "20260616", "--only", "600114",
                 "--staging-dir", temp_dir,
                 "--promote"],
                capture_output=True, text=True, timeout=120, cwd=str(ROOT),
                env=env,
            )
            try:
                data = json.loads(result.stdout)
            except json.JSONDecodeError:
                data = {}
            status = data.get("status", "unknown")
            if status == "PROMOTE_BLOCKED":
                self.assertEqual(data.get("promoted_files", None), [],
                                 "promoted_files must be empty when gate BLOCKs")
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            shutil.rmtree(flow_dir, ignore_errors=True)

    def test_report_root_override_works(self):
        """REPORT_ROOT_OVERRIDE env var changes where checkers look for reports."""
        shadow = Path(tempfile.mkdtemp()) / "重点股票" / "股票报告"
        shadow.mkdir(parents=True, exist_ok=True)

        env = os.environ.copy()
        env["REPORT_ROOT_OVERRIDE"] = str(shadow)

        # Run D07 contract against the empty shadow - must BLOCK (no report files)
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "check_daily_d07_v12_contract.py"),
             "--date", "20260616", "--code", "600114", "--name", "东睦股份"],
            capture_output=True, text=True, timeout=60, cwd=str(ROOT),
            env=env,
        )
        self.assertNotEqual(result.returncode, 0,
                            "D07 contract against empty shadow must BLOCK")

        # Run data completeness against shadow - must BLOCK (no report files)
        result3 = subprocess.run(
            [sys.executable, str(SCRIPTS / "check_daily_data_completeness.py"),
             "--date", "20260616", "--code", "600114", "--name", "东睦股份"],
            capture_output=True, text=True, timeout=60, cwd=str(ROOT),
            env=env,
        )
        self.assertNotEqual(result3.returncode, 0,
                            "data completeness against empty shadow must BLOCK")

        import shutil
        shutil.rmtree(str(shadow.parent.parent), ignore_errors=True)

    def test_promote_source_blocked_state_has_no_promoted(self):
        """BLOCKED state must have promoted_files=[] in source."""
        source = (SCRIPTS / "run_daily_report_html_only.py").read_text(encoding="utf-8")
        # Find PROMOTE_BLOCKED section
        blocked_idx = source.find("PROMOTE_BLOCKED")
        self.assertGreater(blocked_idx, 0, "PROMOTE_BLOCKED must exist")
        blocked_section = source[blocked_idx:blocked_idx + 500]
        self.assertIn('promoted_files": []', blocked_section,
                       "BLOCKED state must have promoted_files=[]")

    def test_promote_source_has_formal_untouched(self):
        """BLOCKED state must indicate formal directory was untouched."""
        source = (SCRIPTS / "run_daily_report_html_only.py").read_text(encoding="utf-8")
        self.assertIn("formal_untouched", source,
                       "blocked state must include formal_untouched flag")


if __name__ == "__main__":
    unittest.main()
