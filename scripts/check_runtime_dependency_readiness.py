#!/usr/bin/env python3
"""Check production runtime Python package dependencies.

Checks that required packages are importable in a subprocess environment
that matches the pipeline child process setup (altered HOME, PYTHONPATH).

Usage:
  python3 scripts/check_runtime_dependency_readiness.py --json
  python3 scripts/check_runtime_dependency_readiness.py --runtime daily_production --json
"""

import argparse
import json
import os
import subprocess
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


def check_package(package_name, import_name, description="", python_executable=None, env=None):
    """Return check dict: whether *import_name* can be imported in a subprocess.

    When *env* is provided, the subprocess runs with that environment to
    simulate the pipeline child process (altered HOME, PYTHONPATH, etc.).
    """
    code = f"import {import_name}; print('OK')"
    py = python_executable or sys.executable
    try:
        proc = subprocess.run(
            [py, "-c", code],
            capture_output=True, text=True, timeout=15,
            env=env,
        )
        ok = (proc.returncode == 0 and "OK" in proc.stdout)
        return {
            "package": package_name,
            "importable": ok,
            "description": description,
            "python": py,
            "env_home": env.get("HOME", "?") if env else "(inherited)",
        }
    except (subprocess.TimeoutExpired, OSError) as e:
        return {
            "package": package_name,
            "importable": False,
            "description": description,
            "error": str(e),
            "env_home": env.get("HOME", "?") if env else "(inherited)",
        }


def run_check(runtime="daily_production", python_executable=None, env=None):
    """Run all registered package checks for *runtime*.

    Args:
        runtime: Profile name.
        python_executable: Python binary to use in subprocess (default: sys.executable).
        env: Environment dict for subprocess (default: None = inherit parent env).
    """
    packages = PRODUCTION_PACKAGES.get(runtime, {})
    descriptions = PRODUCTION_PACKAGES_DESC.get(runtime, {})
    checks = [
        check_package(
            pkg_name, import_name, descriptions.get(pkg_name, ""),
            python_executable=python_executable, env=env,
        )
        for pkg_name, import_name in packages.items()
    ]

    missing = [c for c in checks if not c["importable"]]
    findings = []
    for c in missing:
        detail = f"package '{c['package']}' not importable"
        if c["description"]:
            detail += f" (needed by: {c['description']})"
        if c.get("env_home"):
            detail += f" [env HOME={c['env_home']}]"
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
    parser.add_argument("--pipeline-env", action="store_true",
                        help="Simulate pipeline subprocess_env() for a more realistic check")
    args = parser.parse_args()

    env = None
    if args.pipeline_env:
        # Simulate what run_daily_production_pipeline.subprocess_env() does
        env = os.environ.copy()
        # Set PYTHONPATH to include user site-packages so subprocess
        # can find installed packages even when HOME is overridden
        try:
            import site
            user_sp = site.getusersitepackages()
            if user_sp and os.path.isdir(user_sp):
                existing = env.get("PYTHONPATH", "")
                if existing:
                    env["PYTHONPATH"] = user_sp + os.pathsep + existing
                else:
                    env["PYTHONPATH"] = user_sp
        except Exception:
            pass

    result = run_check(args.runtime, python_executable=sys.executable, env=env)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Runtime dependency readiness: {result['overall']}")
        for chk in result["checks"]:
            status = "OK" if chk["importable"] else "MISSING"
            print(f"  - {chk['package']}: {status}")
            if chk.get("env_home"):
                print(f"    HOME={chk['env_home']}")
        for finding in result["findings"]:
            print(f"  BLOCK: {finding}")

    return 0 if result["overall"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
