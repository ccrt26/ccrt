#!/usr/bin/env python3
import argparse
import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TZ_SHANGHAI = timezone(timedelta(hours=8))

def today_shanghai():
    return datetime.now(TZ_SHANGHAI).strftime("%Y%m%d")

def is_trading_day(date_str):
    mod_path = ROOT / "代码文件" / "tools" / "daily_orchestrator.py"
    spec = importlib.util.spec_from_file_location("daily_orchestrator_for_calendar", str(mod_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return bool(mod.is_trading_day(date_str))

def main():
    ap = argparse.ArgumentParser(description="Run daily data pipeline for Shanghai today")
    ap.add_argument("--date", default="", help="YYYYMMDD; default Shanghai today")
    ap.add_argument("--attempt", type=int, default=1)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force-non-trading-day", action="store_true")
    args = ap.parse_args()

    date_str = args.date or today_shanghai()
    cmd = [sys.executable, str(ROOT / "scripts" / "run_daily_data_retry_once.py"), "--date", date_str, "--attempt", str(args.attempt)]
    payload = {"date": date_str, "trading_day": is_trading_day(date_str), "command": cmd, "cwd": str(ROOT)}

    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if not payload["trading_day"] and not args.force_non_trading_day:
        print(json.dumps({"skip": "non_trading_day", **payload}, ensure_ascii=False))
        return 0

    return subprocess.run(cmd, cwd=str(ROOT)).returncode

if __name__ == "__main__":
    raise SystemExit(main())
