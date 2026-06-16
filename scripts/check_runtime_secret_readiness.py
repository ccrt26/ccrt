#!/usr/bin/env python3
"""Check production runtime secrets without printing secret values."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from runtime_secret_loader import DEFAULT_PRIVATE_ENV, TUSHARE_TOKEN, check_secret_readiness

RUNTIME_REQUIREMENTS = {
    "daily_production": [TUSHARE_TOKEN],
}


def run_check(runtime, private_env=DEFAULT_PRIVATE_ENV, launchd_compatible=True):
    required = RUNTIME_REQUIREMENTS.get(runtime)
    if not required:
        return {
            "overall": "BLOCK",
            "runtime": runtime,
            "checks": [],
            "findings": [f"unknown runtime: {runtime}"],
        }

    checks = [
        check_secret_readiness(name, private_env=private_env, launchd_compatible=launchd_compatible)
        for name in required
    ]
    findings = []
    for chk in checks:
        if chk.get("status") != "PASS":
            findings.append(chk.get("reason") or f"{chk.get('name')} not ready")

    return {
        "overall": "PASS" if not findings else "BLOCK",
        "runtime": runtime,
        "launchd_compatible": launchd_compatible,
        "checks": checks,
        "findings": findings,
    }


def main():
    parser = argparse.ArgumentParser(description="Runtime secret readiness gate")
    parser.add_argument("--runtime", default="daily_production", choices=sorted(RUNTIME_REQUIREMENTS))
    parser.add_argument("--private-env", default=str(DEFAULT_PRIVATE_ENV))
    parser.add_argument("--allow-process-env", action="store_true",
                        help="For manual diagnostics only; production launchd checks ignore shell env.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = run_check(
        args.runtime,
        private_env=Path(args.private_env),
        launchd_compatible=not args.allow_process_env,
    )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Runtime secret readiness: {result['overall']}")
        for chk in result["checks"]:
            print(f"- {chk['name']}: {chk['status']} source={chk.get('source')}")
        for finding in result["findings"]:
            print(f"BLOCK: {finding}")

    return 0 if result["overall"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
