"""Tests for check_runtime_dependency_readiness.py — fully offline, no network, no package installs."""
import unittest
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_runtime_dependency_readiness import check_package, run_check

REQUIREMENTS_PRODUCTION = ROOT / "requirements-production.txt"


class TestRuntimeDependencyReadiness(unittest.TestCase):
    def test_check_package_importable_stdlib(self):
        """Built-in stdlib modules must be detected as importable."""
        result = check_package("json", "json")
        self.assertTrue(result["importable"])
        self.assertEqual(result["package"], "json")

    def test_check_package_not_importable(self):
        """A non-existent module must be detected as not importable."""
        result = check_package("nonexistent_xyzzy", "nonexistent_xyzzy")
        self.assertFalse(result["importable"])

    def test_check_package_returns_description(self):
        """Description must be preserved in the result."""
        result = check_package("tushare", "tushare", description="tushare_history_sync")
        self.assertEqual(result["description"], "tushare_history_sync")

    def test_run_check_daily_production_structure(self):
        """run_check must return the correct structure."""
        result = run_check("daily_production")
        self.assertIn("overall", result)
        self.assertIn("runtime", result)
        self.assertIn("checks", result)
        self.assertIn("findings", result)
        self.assertEqual(result["runtime"], "daily_production")
        self.assertIsInstance(result["checks"], list)
        self.assertIsInstance(result["findings"], list)

    def test_run_check_daily_production_contains_tushare_and_markdown(self):
        """daily_production checks must include tushare and markdown."""
        result = run_check("daily_production")
        packages = {c["package"] for c in result["checks"]}
        self.assertIn("tushare", packages)
        self.assertIn("markdown", packages)

    def test_run_check_unknown_runtime(self):
        """An unknown runtime must return empty checks."""
        result = run_check("unknown_runtime")
        self.assertEqual(result["checks"], [])
        self.assertEqual(result["runtime"], "unknown_runtime")

    # ── requirements-production.txt specifier validation ──────────────

    def _read_tushare_specifier(self):
        """Parse the tushare version specifier from requirements-production.txt."""
        text = REQUIREMENTS_PRODUCTION.read_text(encoding="utf-8")
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("tushare"):
                # extract everything after "tushare", e.g. ">=1.4,<2.0"
                spec = line[len("tushare"):].strip()
                return spec
        self.fail("tushare line not found in requirements-production.txt")

    def test_tushare_specifier_allows_1_4_29(self):
        """The tushare constraint in requirements-production.txt must allow
        version 1.4.29 (the highest pip-installable version)."""
        try:
            from packaging.specifiers import SpecifierSet
        except ImportError:
            self.skipTest("packaging module not available")
        spec_str = self._read_tushare_specifier()
        spec = SpecifierSet(spec_str)
        self.assertIn(
            "1.4.29", spec,
            f"tushare specifier '{spec_str}' does not allow version 1.4.29",
        )

    def test_tushare_specifier_rejects_unreleased_major(self):
        """The tushare constraint must reject version 2.0 (major version cap)."""
        try:
            from packaging.specifiers import SpecifierSet
        except ImportError:
            self.skipTest("packaging module not available")
        spec_str = self._read_tushare_specifier()
        spec = SpecifierSet(spec_str)
        self.assertNotIn(
            "2.0.0", spec,
            f"tushare specifier '{spec_str}' allows version 2.0.0 (should be capped)",
        )


if __name__ == "__main__":
    unittest.main()
