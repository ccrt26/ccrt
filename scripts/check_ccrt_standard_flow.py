#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CHECKS = [
    {
        "name": "role_boundary",
        "command": [sys.executable, str(ROOT / "scripts" / "check_ccrt_role_boundary.py"), "--json"],
    },
    {
        "name": "stage_contract",
        "command": [sys.executable, str(ROOT / "scripts" / "check_ccrt_stage_contract.py"), "--json"],
    },
    {
        "name": "flow_routing",
        "command": [sys.executable, str(ROOT / "scripts" / "check_ccrt_flow_routing.py"), "--json"],
    },
]

def run_check(item):
    proc = subprocess.run(
        item["command"],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
    )
    parsed = None
    parse_error = ""
    if proc.stdout.strip():
        try:
            parsed = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            parse_error = str(exc)

    result = "PASS"
    if proc.returncode != 0:
        result = "BLOCK"
    if parsed and parsed.get("result") != "PASS":
        result = "BLOCK"
    if parse_error:
        result = "BLOCK"

    return {
        "name": item["name"],
        "result": result,
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
        "parsed": parsed,
        "parse_error": parse_error,
    }

def main():
    parser = argparse.ArgumentParser(description="CCRT standard G0-G6 total gate")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    checks = [run_check(item) for item in CHECKS]
    final = "PASS" if all(c["result"] == "PASS" for c in checks) else "BLOCK"

    payload = {
        "result": final,
        "gate": "ccrt_standard_flow",
        "checks": checks,
        "summary": {
            "role_boundary": next(c["result"] for c in checks if c["name"] == "role_boundary"),
            "stage_contract": next(c["result"] for c in checks if c["name"] == "stage_contract"),
            "flow_routing": next(c["result"] for c in checks if c["name"] == "flow_routing"),
        },
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for c in checks:
            print(f"{c['result']}: {c['name']}")
        print(f"RESULT: {final}")

    return 0 if final == "PASS" else 2

if __name__ == "__main__":
    raise SystemExit(main())
