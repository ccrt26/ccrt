#!/usr/bin/env python3
"""A股交易日判断 — replace is_market_open.ps1.

判断指定日期（默认今天）是否为A股交易日。
排除周末、排除中国法定节假日。支持外部CSV配置。

Usage:
    python3 is_market_open.py                  # check today
    python3 is_market_open.py 2026-05-22       # check specific date
    python3 is_market_open.py --holiday holidays_2026.csv

Exit code: 0=交易日, 1=非交易日
Code level: L1
"""
import argparse
import csv
import os
import sys
from datetime import date, timedelta

# ── Built-in 2026 China holidays ──────────────────────
BUILTIN_HOLIDAYS = {
    "2026-01-01",                                          # New Year
    "2026-02-16", "2026-02-17", "2026-02-18",
    "2026-02-19", "2026-02-20",                            # Spring Festival
    "2026-04-06",                                          # Qingming
    "2026-05-01", "2026-05-04", "2026-05-05",              # Labor Day
    "2026-06-19",                                          # Dragon Boat
    "2026-10-01", "2026-10-02", "2026-10-05",
    "2026-10-06", "2026-10-07", "2026-10-08",              # National Day + Mid-Autumn
}

BUILTIN_MAKEUP = set()  # Saturday/Sunday makeup workdays (none configured for 2026 yet)


def is_market_open(check_date, holiday_file=None):
    """Return True if check_date is an A-share trading day."""
    # Weekend check
    if check_date.weekday() >= 5:  # Saturday=5, Sunday=6
        return False

    date_str = check_date.isoformat()

    holidays = set(BUILTIN_HOLIDAYS)
    makeup = set(BUILTIN_MAKEUP)

    # Load external holiday file if provided
    if holiday_file and os.path.exists(holiday_file):
        try:
            with open(holiday_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    d = row.get("Date", "").strip()
                    t = row.get("Type", "").strip().lower()
                    if t == "holiday":
                        holidays.add(d)
                    elif t == "makeup":
                        makeup.add(d)
        except Exception as e:
            print(f"WARNING: Holiday file read failed, using built-in: {e}", file=sys.stderr)

    # Makeup workday overrides holiday
    if date_str in makeup:
        return True

    if date_str in holidays:
        return False

    return True


def main():
    parser = argparse.ArgumentParser(description="Check if a date is an A-share trading day")
    parser.add_argument("date", nargs="?", default=date.today().isoformat(),
                        help="Date to check (yyyy-MM-dd), default today")
    parser.add_argument("--holiday", default="", help="Path to holidays CSV file")
    args = parser.parse_args()

    try:
        check_date = date.fromisoformat(args.date)
    except ValueError:
        print(f"ERROR: Invalid date format: {args.date}", file=sys.stderr)
        sys.exit(2)

    result = is_market_open(check_date, args.holiday)
    print("true" if result else "false")
    sys.exit(0 if result else 1)


if __name__ == "__main__":
    main()
