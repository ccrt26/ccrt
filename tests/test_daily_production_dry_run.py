import json
import os
import subprocess
import sys
import tempfile
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

    def test_dry_run_exposes_batch_data_collector_planned_command(self):
        """dry-run must expose the planned batch_data_collector command with --date."""
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts/run_daily_production_pipeline.py"), "--date", "20990101", "--dry-run"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=30
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertIn("planned_commands", payload)
        self.assertIn("batch_data_collector", payload["planned_commands"])
        cmd = payload["planned_commands"]["batch_data_collector"]
        self.assertIn("--date", cmd)
        self.assertIn("20990101", cmd)

class TestWritePreflightBlockBlocker(unittest.TestCase):
    """Unit tests for write_preflight_block ready_json.blocker field consistency."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        scripts_dir = ROOT / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))

    def _get_module(self):
        """Import run_daily_production_pipeline with production/status dirs patched to tmpdir."""
        import run_daily_production_pipeline as mod
        mod.PRODUCTION_DIR = self.tmpdir
        mod.STATUS_DIR = self.tmpdir
        return mod

    def test_blocker_default_step_name(self):
        """Default step_name='runtime_secret_preflight' sets blocker to that value."""
        mod = self._get_module()
        _, ready_path = mod.write_preflight_block("20990101", "test block", {})
        ready = json.loads(ready_path.read_text())
        self.assertEqual(ready["blocker"], ["runtime_secret_preflight"])

    def test_blocker_follows_explicit_step_name(self):
        """Explicit step_name='runtime_dependency_preflight' sets blocker to that value."""
        mod = self._get_module()
        _, ready_path = mod.write_preflight_block(
            "20990101", "test block", {},
            step_name="runtime_dependency_preflight"
        )
        ready = json.loads(ready_path.read_text())
        self.assertEqual(ready["blocker"], ["runtime_dependency_preflight"])

    def test_blocker_consistent_with_manifest_step(self):
        """manifest.step and ready_json.blocker must be consistent for any step_name."""
        mod = self._get_module()
        for step_name in ("runtime_secret_preflight", "runtime_dependency_preflight"):
            manifest_path, ready_path = mod.write_preflight_block(
                "20990101", "test block", {},
                step_name=step_name
            )
            manifest = json.loads(manifest_path.read_text())
            ready = json.loads(ready_path.read_text())
            self.assertEqual(manifest["steps"][0]["step"], ready["blocker"][0])
            self.assertEqual(manifest["steps"][0]["step"], step_name)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)


class TestSubprocessEnv(unittest.TestCase):
    """Tests for subprocess_env() PYTHONPATH injection."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        scripts_dir = ROOT / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))

    def test_subprocess_env_contains_pythonpath(self):
        """subprocess_env() must inject PYTHONPATH with user site-packages."""
        import run_daily_production_pipeline as mod
        mod.RUNTIME_HOME = self.tmpdir / "runtime_home"
        env = mod.subprocess_env()
        self.assertIn("PYTHONPATH", env,
                       "subprocess_env() must set PYTHONPATH")
        self.assertIn("site-packages", env["PYTHONPATH"],
                       "PYTHONPATH must point to user site-packages")
        self.assertIn("HOME", env)
        self.assertIn(str(mod.RUNTIME_HOME), env["HOME"])

    def test_subprocess_env_pythonpath_is_valid(self):
        """PYTHONPATH from subprocess_env() must be an importable directory."""
        import run_daily_production_pipeline as mod
        mod.RUNTIME_HOME = self.tmpdir / "runtime_home"
        env = mod.subprocess_env()
        pp = env["PYTHONPATH"]
        path = pp.split(os.pathsep)[0]
        self.assertTrue(Path(path).is_dir(),
                        f"PYTHONPATH first entry must be a directory: {path}")

    def test_dependency_readiness_works_with_pipeline_env(self):
        """check_runtime_dependency_readiness with --pipeline-env must find installed packages."""
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_runtime_dependency_readiness.py"),
             "--runtime", "daily_production", "--json", "--pipeline-env"],
            capture_output=True, text=True, timeout=30, cwd=str(ROOT)
        )
        self.assertEqual(result.returncode, 0,
                         f"Dependency check must PASS: {result.stdout}")
        payload = json.loads(result.stdout)
        self.assertEqual(payload["overall"], "PASS")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)


class TestWriteSignalDailyReport(unittest.TestCase):
    """Unit tests for write_signal_daily_report."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        scripts_dir = ROOT / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))

    def _get_module(self):
        """Import run_daily_production_pipeline with SIGNAL_PATH patched to tmpdir."""
        import run_daily_production_pipeline as mod
        mod.SIGNAL_PATH = self.tmpdir / "signal_daily_report.json"
        return mod

    def test_signal_write_data_ready_true(self):
        """write_signal_daily_report with data_ready=True writes correct fields."""
        mod = self._get_module()
        mod.write_signal_daily_report("20990101", True)
        sig = json.loads((self.tmpdir / "signal_daily_report.json").read_text(encoding="utf-8"))
        self.assertEqual(sig["signal"], "daily_report")
        self.assertEqual(sig["date"], "20990101")
        self.assertTrue(sig["data_ready"])
        self.assertEqual(sig["mode"], "daily")
        self.assertTrue(sig["pipeline_mode"])
        self.assertEqual(sig["source"], "run_daily_production_pipeline")
        self.assertIn("timestamp", sig)

    def test_signal_write_data_ready_false(self):
        """write_signal_daily_report with data_ready=False writes data_ready=false."""
        mod = self._get_module()
        mod.write_signal_daily_report("20990101", False)
        sig = json.loads((self.tmpdir / "signal_daily_report.json").read_text(encoding="utf-8"))
        self.assertEqual(sig["date"], "20990101")
        self.assertFalse(sig["data_ready"])

    def test_signal_write_different_dates(self):
        """write_signal_daily_report correctly tracks multiple dates."""
        mod = self._get_module()
        mod.write_signal_daily_report("20260101", True)
        sig1 = json.loads((self.tmpdir / "signal_daily_report.json").read_text(encoding="utf-8"))
        self.assertEqual(sig1["date"], "20260101")

        mod.write_signal_daily_report("20261231", True)
        sig2 = json.loads((self.tmpdir / "signal_daily_report.json").read_text(encoding="utf-8"))
        self.assertEqual(sig2["date"], "20261231")
        self.assertNotEqual(sig1["date"], sig2["date"])

    def test_signal_write_overwrites_previous(self):
        """write_signal_daily_report overwrites previous signal (only one file exists)."""
        mod = self._get_module()
        mod.write_signal_daily_report("20990101", False)
        mod.write_signal_daily_report("20990102", True)
        sig = json.loads((self.tmpdir / "signal_daily_report.json").read_text(encoding="utf-8"))
        self.assertEqual(sig["date"], "20990102")
        self.assertTrue(sig["data_ready"])

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)


class TestBaselinePreflight(unittest.TestCase):
    """Unit tests for check_baseline_preflight."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        if str(ROOT / "scripts") not in sys.path:
            sys.path.insert(0, str(ROOT / "scripts"))

    def _get_module(self):
        import run_daily_production_pipeline as mod
        return mod

    def test_no_targets_file_returns_block(self):
        """Missing targets file returns BLOCK."""
        mod = self._get_module()
        result = mod.check_baseline_preflight("20990101", self.tmpdir / "nonexistent.json")
        self.assertEqual(result["status"], "BLOCK")
        self.assertIn("not found", result["reason"])

    def test_empty_active_targets_returns_skip(self):
        """No active targets returns SKIP."""
        mod = self._get_module()
        p = self.tmpdir / "targets.json"
        p.write_text(json.dumps({"active_targets": []}), encoding="utf-8")
        result = mod.check_baseline_preflight("20990101", p)
        self.assertEqual(result["status"], "SKIP")
        self.assertIn("no active targets", result["reason"])

    def test_block_when_target_missing_baseline(self):
        """Active target without valid baseline returns BLOCK."""
        mod = self._get_module()
        p = self.tmpdir / "targets.json"
        p.write_text(json.dumps({
            "active_targets": [{"code": "999999", "name": "测试", "enabled": True}]
        }), encoding="utf-8")
        result = mod.check_baseline_preflight("20990101", p)
        self.assertEqual(result["status"], "BLOCK")
        self.assertIn("BLOCK", result["reason"])
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["results"][0]["result"], "BLOCK")

    def test_disabled_target_skipped(self):
        """Disabled target should not trigger BLOCK."""
        mod = self._get_module()
        p = self.tmpdir / "targets.json"
        p.write_text(json.dumps({
            "active_targets": [
                {"code": "999999", "name": "DisabledStock", "enabled": False}
            ]
        }), encoding="utf-8")
        result = mod.check_baseline_preflight("20990101", p)
        self.assertEqual(result["status"], "SKIP")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)


class TestClosureVerifySelfLockFix(unittest.TestCase):
    """Verify closure_verify --pipeline-internal flag fixes self-lock."""

    def test_closure_verifier_exposes_pipeline_internal_flag(self):
        """--pipeline-internal must be a recognized argument."""
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts/verify_daily_production_closure.py"), "--help"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=30
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("--pipeline-internal", proc.stdout)

    def test_pipeline_uses_pipeline_internal_closure_verify(self):
        """pipeline must pass --pipeline-internal to closure_verify."""
        src = (ROOT / "scripts/run_daily_production_pipeline.py").read_text(encoding="utf-8")
        self.assertIn("--pipeline-internal", src)


class TestBaselinePreflightDryRun(unittest.TestCase):
    """Verify baseline_preflight appears in dry-run planned_steps."""

    def test_dry_run_includes_baseline_preflight(self):
        """dry-run must include baseline_preflight in would_run."""
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts/run_daily_production_pipeline.py"), "--date", "20990101", "--dry-run"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=30
        )
        self.assertEqual(proc.returncode, 0)
        payload = json.loads(proc.stdout)
        self.assertIn("baseline_preflight", payload["would_run"])

    def test_dry_run_does_not_write_when_preflight_blocked(self):
        """dry-run must not write any files even if baseline_preflight would BLOCK."""
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts/run_daily_production_pipeline.py"), "--date", "20990101", "--dry-run"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=30
        )
        self.assertEqual(proc.returncode, 0)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["would_write"], [])


if __name__ == "__main__":
    unittest.main()
