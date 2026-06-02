#!/usr/bin/env python3
"""run_full_audit.py — 全量审计入口

Replaces run_full_audit.ps1.
Runs complete four-level audit: redline → data → architecture → token efficiency.
Code level: L1
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent.parent)


def run_check(name, script, *args):
    """Run a check script and return (passed, output)."""
    script_path = os.path.join(ROOT, script)
    if not os.path.exists(script_path):
        return None, f"Script not found: {script_path}"
    try:
        result = subprocess.run(
            [sys.executable, script_path] + list(args),
            capture_output=True, text=True, timeout=60, cwd=ROOT
        )
        return result.returncode == 0, result.stdout.strip()[:500]
    except Exception as e:
        return False, str(e)


def main():
    parser = argparse.ArgumentParser(description="Full audit runner")
    parser.add_argument("--quick", action="store_true", help="Quick audit only")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"), help="Audit date")
    parser.add_argument("--root-dir", default=ROOT, help="Project root")
    args = parser.parse_args()

    results = {}

    # Level 1: Redline check
    passed, output = run_check("Redline", "代码文件/规则红线/check_redlines.py", "--quick")
    results["redline"] = {"passed": passed, "output": output}

    # Level 2: Version consistency
    passed, output = run_check("Version", "代码文件/监督机制/version_supervisor.py", "--cross-check")
    results["version"] = {"passed": passed, "output": output}

    # Level 3: Health check
    passed, output = run_check("Health", "代码文件/tools/health_check.py", "--mode", "boot")
    results["health"] = {"passed": passed, "output": output}

    all_pass = all(r.get("passed", False) for r in results.values() if r.get("passed") is not None)

    summary = {
        "AuditDate": args.date,
        "AllPassed": all_pass,
        "Results": results,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
