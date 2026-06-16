#!/usr/bin/env python3
"""Check production runtime Python package dependencies.

Checks that required packages are importable without actually loading
production code or connecting to any external service.  Designed for
offline testing — no network, no package installation, no real production
data reads.

Usage:
  python3 scripts/check_runtime_dependency_readiness.py --json
  python3 scripts/check_runtime_dependency_readiness.py --runtime daily_production --json
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Runtime key -> { package_name: import_name }
PRODUCTION_PACKAGES = {
    "daily_production": {
        "tushare": "tushare",
        "markdown": "markdown",
    },
}

PRODUCTION_PACKAGES_DESC = {
    "daily_production": {
        "tushare": "tushare_history_sync",
        "markdown": "daily_report (markdown -> html)",
    },
}


def check_package(package_name, import_name, description=""):
    """Return check dict: whether *import_name* can be imported."""
    try:
        __import__(import_name)
        return {
            "package": package_name,
            "importable": True,
            "description": description,
        }
    except ImportError:
        return {
            "package": package_name,
            "importable": False,
            "description": description,
        }


def run_check(runtime="daily_production"):
    """Run all registered package checks for *runtime*."""
    packages = PRODUCTION_PACKAGES.get(runtime, {})
    descriptions = PRODUCTION_PACKAGES_DESC.get(runtime, {})
    checks = [
        check_package(pkg_name, import_name, descriptions.get(pkg_name, ""))
        for pkg_name, import_name in packages.items()
    ]

    missing = [c for c in checks if not c["importable"]]
    findings = []
    for c in missing:
        detail = f"package '{c['package']}' not importable"
        if c["description"]:
            detail += f" (needed by: {c['description']})"
        findings.append(detail)

    return {
        "overall": "PASS" if not findings else "BLOCK",
        "runtime": runtime,
        "checks": checks,
        "findings": findings,
    }


def main():
    parser = argparse.ArgumentParser(description="Runtime dependency readiness gate")
    parser.add_argument("--runtime", default="daily_production",
                        help="Runtime profile (default: daily_production)")
    parser.add_argument("--json", action="store_true",
                        help="Output JSON")
    args = parser.parse_args()

    result = run_check(args.runtime)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Runtime dependency readiness: {result['overall']}")
        for chk in result["checks"]:
            status = "OK" if chk["importable"] else "MISSING"
            print(f"  - {chk['package']}: {status}")
        for finding in result["findings"]:
            print(f"  BLOCK: {finding}")

    return 0 if result["overall"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
