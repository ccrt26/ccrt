#!/usr/bin/env python3
"""daily_workflow.py — Daily stock analysis orchestrator.

Replaces daily_workflow.ps1. Modes: daily | eval | daily_latest.

Code level: L1
"""
import argparse
import csv
import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
SCRIPTS_DIR = ROOT / "代码文件" / "每日荐股" / "scripts"
LOGIC_DIR = ROOT / "代码文件" / "每日荐股" / "分析逻辑"
REPORT_DIR = ROOT / "每日荐股" / "股票报告"
EVAL_DIR = ROOT / "每日荐股" / "事后评估"
DATA_DIR = ROOT / "代码文件" / "数据"
TOOLS_DIR = ROOT / "代码文件" / "tools"
HOLIDAY_FILE = ROOT / "每日荐股" / "运营记录" / "holidays_2026.csv"
RECORD_FILE = ROOT / "每日荐股" / "运营记录" / "workflow_records.csv"
LOG_FILE = SCRIPTS_DIR / f"workflow_{datetime.now().strftime('%Y%m')}.log"


def log(msg, level="INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}][{level}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def write_record(date_str, mode, status, report_name="", ver_before="", ver_after="", notes=""):
    exists = RECORD_FILE.exists()
    with open(RECORD_FILE, "a", encoding="utf-8") as f:
        if not exists:
            f.write("Date,Mode,Status,ReportName,VersionBefore,VersionAfter,Notes\n")
        f.write(f"{date_str},{mode},{status},{report_name},{ver_before},{ver_after},{notes}\n")


def is_trading_day(check_date):
    """Check if date is an A-share trading day."""
    market_script = SCRIPTS_DIR / "is_market_open.py"
    holiday_arg = [f"--holiday={HOLIDAY_FILE}"] if HOLIDAY_FILE.exists() else []
    result = subprocess.run(
        ["python3", str(market_script), check_date] + holiday_arg,
        capture_output=True, cwd=str(ROOT)
    )
    return result.returncode == 0


def run_eval(date_str):
    """Post-evaluation mode — find latest trading day and evaluate."""
    log("===== Starting Post-Evaluation =====")

    # Find most recent trading day
    eval_date = date.fromisoformat(date_str)
    for _ in range(30):
        eval_date = eval_date - timedelta(days=1)
        if is_trading_day(eval_date.isoformat()):
            break
    else:
        log("Cannot find recent trading day within 30 days", "ERROR")
        return False

    eval_date_str = eval_date.isoformat()
    log(f"Eval target date: {eval_date_str}")

    # Pre-eval: Backfill historical returns
    backfill = SCRIPTS_DIR / "backfill_returns.py"
    if backfill.exists():
        subprocess.run(["python3", str(backfill)], cwd=str(ROOT))
        log("Backfill complete")

    # Run evaluation via run_daily_eval.py
    eval_py = SCRIPTS_DIR / "run_daily_eval.py"
    if not eval_py.exists():
        log("FATAL: run_daily_eval.py not found at {}".format(eval_py), "ERROR")
        write_record(date_str, "eval", "FAILED", notes="run_daily_eval.py missing")
        return False

    result = subprocess.run(["python3", str(eval_py), "--date", eval_date_str], cwd=str(ROOT))
    if result.returncode == 0:
        log("Eval completed successfully", "OK")
        write_record(date_str, "eval", "SUCCESS", notes="eval done, 0 alerts")
    elif result.returncode == 1:
        log("Eval completed with alerts (non-blocking)", "WARN")
        write_record(date_str, "eval", "SUCCESS", notes="eval done, alerts present")
    else:
        log("Eval FAILED (exit={})".format(result.returncode), "ERROR")
        write_record(date_str, "eval", "FAILED", notes="eval exit={}".format(result.returncode))
        return False

    # Archive eval results to 历史数据
    archive_py = SCRIPTS_DIR / "archive_data.py"
    if archive_py.exists():
        subprocess.run(["python3", str(archive_py), "--date", eval_date_str.replace("-", "")],
                       cwd=str(ROOT))
        log("Eval results archived")
    log("===== Post-Evaluation Complete =====")
    return True


def run_daily(date_str, mode):
    """Daily stock analysis pipeline (7 phases)."""
    log(f"===== Starting Daily Stock Analysis ({mode}) =====")

    # Phase 1: Build dynamic pool
    log("[1/7] Building dynamic pool...")
    pool_py = SCRIPTS_DIR / "build_dynamic_pool.py"
    if pool_py.exists():
        subprocess.run(["python3", str(pool_py)], cwd=str(ROOT))
        log("Dynamic pool built")

    # Phase 2: Batch data collection
    log("[2/7] Collecting batch data...")
    collector_py = SCRIPTS_DIR / "batch_data_collector.py"
    collector_ps = SCRIPTS_DIR / "batch_data_collector.ps1"
    if collector_py.exists():
        result = subprocess.run(["python3", str(collector_py)], capture_output=True, text=True, cwd=str(ROOT))
        if result.stdout:
            for line in result.stdout.strip().split("\n"):
                log(f"[batch_data] {line}")
        if result.stderr:
            for line in result.stderr.strip().split("\n"):
                if line.strip():
                    log(f"[batch_data:err] {line}", "WARN")
    elif collector_ps.exists():
        log("BLOCK: batch_data_collector.ps1 found in active directory — Python replacement exists. "
            "Remove or rename the .ps1 file or migrate to Python version.", "BLOCK")
        sys.exit(1)

    # Phase 2.5: Data quality gate
    log("[2.5/7] Data quality check...")
    dq_gate = ROOT / "代码文件" / "监督机制" / "check_data_quality.py"
    if dq_gate.exists():
        result = subprocess.run(["python3", str(dq_gate)], capture_output=True, text=True, cwd=str(ROOT))
        dq_report_path = DATA_DIR / "data_quality_report.json"
        if dq_report_path.exists():
            with open(dq_report_path) as f:
                dq = json.load(f)
            overall = dq.get("overall", "UNKNOWN")
            blocked = dq.get("blocked", False)
            log(f"DQ-Gate: {overall} | {len(dq.get('issues', []))} issues | blocked={blocked}")
            if blocked:
                log("DQ-Gate FAIL — pipeline blocked. Fix data issues and re-run.", "ERROR")
                for issue in dq.get("issues", []):
                    log(f"  [{issue['severity']}] {issue['id']}: {issue['desc']}", "ERROR")
                write_record(date_str, mode, "BLOCKED", notes=f"DQ-Gate FAIL: {len(dq.get('issues', []))} issues")
                return False
            elif overall == "WARN":
                log("DQ-Gate WARN — continuing with warnings", "WARN")
                for issue in dq.get("issues", []):
                    log(f"  [{issue['severity']}] {issue['id']}: {issue['desc']}", "WARN")
        else:
            log("DQ-Gate: report not found, skipping check", "WARN")
    else:
        log("DQ-Gate: check_data_quality.py not found, skipping", "WARN")

    # Phase 3: Scoring engine
    log("[3/7] Running scoring engine...")
    scoring = LOGIC_DIR / "scoring_engine_v2.py"
    if scoring.exists():
        subprocess.run(["python3", str(scoring), "--date", date_str], cwd=str(ROOT))
        log("Scoring completed")

    # Phase 3.5: Backfill returns
    backfill = SCRIPTS_DIR / "backfill_returns.py"
    if backfill.exists():
        subprocess.run(["python3", str(backfill)], cwd=str(ROOT))

    # Phase 4: Generate report
    log("[4/7] Generating report...")
    gen_html = LOGIC_DIR / "gen_daily_html.py"
    if gen_html.exists():
        subprocess.run(["python3", str(gen_html), "--date", date_str], cwd=str(ROOT))
        log("Report generated")

    # Phase 4.1: Inject DQ status into reports
    log("[4.1/7] Injecting DQ status into reports...")
    inject_dq = SCRIPTS_DIR / "inject_dq_status.py"
    if inject_dq.exists():
        subprocess.run(["python3", str(inject_dq)], cwd=str(ROOT))
        log("DQ status injected")

    # Phase 5: Key stock analysis
    log("[5/7] Key stock analysis — delegated to 腰子")
    # Key stock analysis is AI-driven, triggered by scheduled task

    # Phase 6: Archive data
    log("[6/7] Archiving data...")
    archive_py = SCRIPTS_DIR / "archive_data.py"
    if archive_py.exists():
        subprocess.run(["python3", str(archive_py), "--date", date_str], cwd=str(ROOT))

    write_record(date_str, mode, "SUCCESS", notes=f"Daily analysis done, report dir: {REPORT_DIR}")
    log("===== Daily Stock Analysis Complete =====")
    return True


def main():
    parser = argparse.ArgumentParser(description="TieLv Daily Workflow")
    parser.add_argument("--mode", required=True, choices=["daily", "eval", "daily_latest"],
                        help="Workflow mode")
    parser.add_argument("--date", default=date.today().isoformat(),
                        help="Target date (yyyy-MM-dd), default today")
    parser.add_argument("--skip-market-check", action="store_true",
                        help="Skip market open check (testing)")
    parser.add_argument("--log-only", action="store_true", help="Log only, skip execution")
    args = parser.parse_args()

    # Market open check
    if not args.skip_market_check:
        if not is_trading_day(args.date):
            log(f"{args.date} is not a trading day, skip", "SKIP")
            write_record(args.date, args.mode, "SKIPPED", notes="Not a trading day")
            sys.exit(0)
        log(f"{args.date} is a trading day, proceeding")

    if args.log_only:
        log(f"[LogOnly] Mode={args.mode}, Date={args.date}")
        sys.exit(0)

    if args.mode == "eval":
        success = run_eval(args.date)
    else:
        success = run_daily(args.date, args.mode)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
