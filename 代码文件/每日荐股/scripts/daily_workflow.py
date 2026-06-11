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


def run_data_only(date_str):
    """数据链专用模式：只做数据获取、沉淀、加工、校验、健康检查、归档，不生成报告。

    执行顺序：
      build_dynamic_pool → batch_data_collector → data_full 校验(utf-8-sig+trade_date匹配)
      → materialize 缓存派生 → update_l2_cache → DQ-Gate
      → check_daily_data_chain_health → archive_data
    不执行：
      scoring_engine / gen_daily_html / inject_dq_status / key stock analysis
    """
    date_compact = date_str.replace("-", "")
    log(f"===== Starting Data-Only Pipeline ({date_str}) =====")

    # Phase 1: Build dynamic pool — hard fail 代替静默继续
    log("[1/7] Building dynamic pool...")
    pool_py = SCRIPTS_DIR / "build_dynamic_pool.py"
    if not pool_py.exists():
        log("build_dynamic_pool.py 不存在 — aborting", "ERROR")
        write_record(date_str, "data_only", "FAILED", notes="build_dynamic_pool.py missing")
        return False
    pool_result = subprocess.run(["python3", str(pool_py)], capture_output=True, text=True, cwd=str(ROOT))
    if pool_result.returncode != 0:
        log(f"build_dynamic_pool exit={pool_result.returncode} — aborting", "ERROR")
        if pool_result.stderr:
            log(f"  stderr: {pool_result.stderr.strip()[:500]}", "ERROR")
        write_record(date_str, "data_only", "FAILED", notes=f"build_dynamic_pool exit={pool_result.returncode}")
        return False
    log("Dynamic pool built")

    # Phase 2: Batch data collection — 传 DAILY_TARGET_DATE 环境变量
    log("[2/7] Collecting batch data...")
    collector_py = SCRIPTS_DIR / "batch_data_collector.py"
    if not collector_py.exists():
        log("batch_data_collector.py 不存在 — 禁止使用旧 data_full.json, aborting", "ERROR")
        write_record(date_str, "data_only", "FAILED", notes="batch_data_collector.py missing")
        return False

    collector_env = os.environ.copy()
    collector_env["DAILY_TARGET_DATE"] = date_compact
    result = subprocess.run(["python3", str(collector_py)], capture_output=True, text=True,
                            cwd=str(ROOT), env=collector_env)
    if result.stdout:
        for line in result.stdout.strip().split("\n"):
            log(f"[batch_data] {line}")
    if result.stderr:
        for line in result.stderr.strip().split("\n"):
            if line.strip():
                log(f"[batch_data:err] {line}", "WARN")
    if result.returncode != 0:
        log(f"batch_data_collector exit={result.returncode} — aborting", "ERROR")
        write_record(date_str, "data_only", "FAILED", notes=f"batch_data exit={result.returncode}")
        return False
    for keyword in ("Traceback", "ImportError", "JSONDecodeError", "ValueError"):
        if keyword in result.stderr:
            log(f"batch_data_collector stderr 含 {keyword} — aborting", "ERROR")
            write_record(date_str, "data_only", "FAILED", notes=f"batch_data stderr:{keyword}")
            return False

    # Phase 2.2: Validate data_full.json (utf-8-sig) — trade_date 必须等于目标日期
    log("[2.2/7] Validating data_full.json...")
    data_full_path = DATA_DIR / "data_full.json"
    if not data_full_path.exists():
        log("data_full.json 不存在 — aborting", "ERROR")
        write_record(date_str, "data_only", "FAILED", notes="data_full.json missing")
        return False
    try:
        with open(data_full_path, "r", encoding="utf-8-sig") as f:
            df = json.load(f)
        meta = df.get("_Meta", {})
        trade_date = (meta.get("trade_date") or "").replace("-", "")
        stocks = df.get("Stocks", [])
        if not trade_date:
            log("data_full.json _Meta.trade_date 为空 — aborting", "ERROR")
            write_record(date_str, "data_only", "FAILED", notes="data_full.json trade_date empty")
            return False
        if trade_date != date_compact:
            log(f"data_full.json trade_date={trade_date} ≠ 目标日期={date_compact} — aborting", "ERROR")
            write_record(date_str, "data_only", "FAILED", notes=f"data_full trade_date mismatch: {trade_date} vs {date_compact}")
            return False
        if not stocks:
            log("data_full.json Stocks 为空 — aborting", "ERROR")
            write_record(date_str, "data_only", "FAILED", notes="data_full.json Stocks empty")
            return False
        log(f"data_full.json: {len(stocks)} stocks, trade_date={trade_date}")
    except (json.JSONDecodeError, ValueError) as e:
        log(f"data_full.json 非法 JSON: {e} — aborting", "ERROR")
        write_record(date_str, "data_only", "FAILED", notes=f"data_full.json invalid: {e}")
        return False

    # Phase 2.3: Materialize authoritative cache
    log("[2.3/7] Materializing authoritative cache...")
    mat_script = ROOT / "scripts" / "materialize_daily_authoritative_cache.py"
    if mat_script.exists():
        mat_result = subprocess.run(["python3", str(mat_script), "--date", date_compact],
                                    capture_output=True, text=True, cwd=str(ROOT))
        if mat_result.returncode == 0:
            log("Cache materialization completed")
        else:
            log(f"Cache materialization FAILED (exit={mat_result.returncode}) — aborting", "ERROR")
            if mat_result.stderr:
                for line in mat_result.stderr.strip().split("\n"):
                    if line.strip():
                        log(f"  [materialize:err] {line}", "ERROR")
            write_record(date_str, "data_only", "FAILED", notes=f"materialize exit={mat_result.returncode}")
            return False
    else:
        log("materialize_daily_authoritative_cache.py not found — aborting", "ERROR")
        write_record(date_str, "data_only", "FAILED", notes="materialize script missing")
        return False

    # Phase 2.4: L2 日增量更新
    log("[2.4/7] Updating L2 cache...")
    l2_script = ROOT / "scripts" / "update_l2_cache.py"
    if l2_script.exists():
        l2_result = subprocess.run(
            ["python3", str(l2_script), "--date", date_compact],
            capture_output=True, text=True, cwd=str(ROOT)
        )
        if l2_result.stdout:
            for line in l2_result.stdout.strip().split("\n"):
                log(f"[l2_update] {line}")
        if l2_result.stderr:
            for line in l2_result.stderr.strip().split("\n"):
                if line.strip():
                    log(f"[l2_update:err] {line}", "WARN")
        if l2_result.returncode != 0:
            log(f"update_l2_cache FAILED (exit={l2_result.returncode}) — aborting", "ERROR")
            write_record(date_str, "data_only", "FAILED", notes=f"update_l2_cache exit={l2_result.returncode}")
            return False
        log("L2 cache update completed")
    else:
        log("update_l2_cache.py not found — aborting", "ERROR")
        write_record(date_str, "data_only", "FAILED", notes="update_l2_cache.py missing")
        return False

    # Phase 2.5: D04 健康验收 — L2 写入后立即验证
    log("[2.5/7] D04 health check after L2 update...")
    d04_health = ROOT / "scripts" / "check_d04_health.py"
    if d04_health.exists():
        d04_result = subprocess.run(
            ["python3", str(d04_health), "--dry-run"],
            capture_output=True, text=True, cwd=str(ROOT)
        )
        if d04_result.stdout:
            for line in d04_result.stdout.strip().split("\n"):
                log(f"[d04_health] {line}")
        if d04_result.returncode != 0:
            log(f"D04 health check FAILED (exit={d04_result.returncode}) — aborting", "ERROR")
            write_record(date_str, "data_only", "FAILED",
                         notes=f"d04_health exit={d04_result.returncode}")
            return False
        log("D04 health check PASS after L2 update")
    else:
        log("check_d04_health.py not found — aborting", "ERROR")
        write_record(date_str, "data_only", "FAILED",
                     notes="check_d04_health.py missing")
        return False

    # Phase 2.6: Data quality gate
    log("[2.6/7] Data quality check...")
    dq_gate = ROOT / "代码文件" / "监督机制" / "check_data_quality.py"
    if dq_gate.exists():
        result = subprocess.run(["python3", str(dq_gate)], capture_output=True, text=True, cwd=str(ROOT))
        dq_report_path = DATA_DIR / "data_quality_report.json"
        if dq_report_path.exists():
            with open(dq_report_path, encoding="utf-8") as f:
                dq = json.load(f)
            overall = dq.get("overall", "UNKNOWN")
            blocked = dq.get("blocked", False)
            log(f"DQ-Gate: {overall} | {len(dq.get('issues', []))} issues | blocked={blocked}")
            if blocked:
                log("DQ-Gate FAIL — pipeline blocked.", "ERROR")
                for issue in dq.get("issues", []):
                    log(f"  [{issue['severity']}] {issue['id']}: {issue['desc']}", "ERROR")
                write_record(date_str, "data_only", "BLOCKED", notes=f"DQ-Gate FAIL: {len(dq.get('issues', []))} issues")
                return False
            elif overall == "WARN":
                log("DQ-Gate WARN — continuing with warnings", "WARN")
                for issue in dq.get("issues", []):
                    log(f"  [{issue['severity']}] {issue['id']}: {issue['desc']}", "WARN")
        else:
            log("DQ-Gate: report not found — aborting", "ERROR")
            write_record(date_str, "data_only", "FAILED", notes="DQ report missing")
            return False
    else:
        log("DQ-Gate: check_data_quality.py not found, skipping", "WARN")

    # Phase 2.7: Health check (archive 前执行)
    log("[2.7/7] Data chain health check...")
    hc_script = ROOT / "scripts" / "check_daily_data_chain_health.py"
    if hc_script.exists():
        hc_result = subprocess.run(["python3", str(hc_script), "--date", date_compact],
                                   capture_output=True, text=True, cwd=str(ROOT))
        if hc_result.stdout:
            for line in hc_result.stdout.strip().split("\n"):
                log(f"[healthcheck] {line}")
        if hc_result.returncode != 0:
            log(f"Health check FAILED (exit={hc_result.returncode}) — aborting", "ERROR")
            write_record(date_str, "data_only", "FAILED", notes=f"healthcheck exit={hc_result.returncode}")
            return False
        log("Data chain health check PASS")
    else:
        log("check_daily_data_chain_health.py not found — aborting", "ERROR")
        write_record(date_str, "data_only", "FAILED", notes="healthcheck script missing")
        return False

    # Phase 3.5: Archive data (最后执行)
    log("[3.5/7] Archiving data...")
    archive_py = SCRIPTS_DIR / "archive_data.py"
    if archive_py.exists():
        result = subprocess.run(["python3", str(archive_py), "--date", date_str],
                                capture_output=True, text=True, cwd=str(ROOT))
        if result.stdout:
            for line in result.stdout.strip().split("\n"):
                log(f"[archive] {line}")
        if result.returncode != 0:
            log(f"archive_data exit={result.returncode} — aborting", "ERROR")
            write_record(date_str, "data_only", "FAILED", notes=f"archive_data exit={result.returncode}")
            return False

    write_record(date_str, "data_only", "SUCCESS", notes="data-only pipeline done")
    log("===== Data-Only Pipeline Complete =====")
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
        # 硬阻断：returncode != 0 → 失败
        if result.returncode != 0:
            log(f"batch_data_collector exit={result.returncode} — aborting", "ERROR")
            write_record(date_str, mode, "FAILED", notes=f"batch_data_collector exit={result.returncode}")
            return False
        # 硬阻断：stderr 含严重错误关键词
        for keyword in ("Traceback", "ImportError", "JSONDecodeError", "ValueError"):
            if keyword in result.stderr:
                log(f"batch_data_collector stderr 含 {keyword} — aborting", "ERROR")
                write_record(date_str, mode, "FAILED", notes=f"batch_data stderr:{keyword}")
                return False

    # Phase 2.2: 立即校验 data_full.json 完整性
    log("[2.2/7] Validating data_full.json...")
    data_full_path = DATA_DIR / "data_full.json"
    if not data_full_path.exists():
        log("data_full.json 不存在 — aborting", "ERROR")
        write_record(date_str, mode, "FAILED", notes="data_full.json missing")
        return False
    try:
        with open(data_full_path, "r", encoding="utf-8") as f:
            df = json.load(f)
        meta = df.get("_Meta", {})
        trade_date = meta.get("trade_date", "")
        stocks = df.get("Stocks", [])
        if not trade_date:
            log("data_full.json _Meta.trade_date 为空 — aborting", "ERROR")
            write_record(date_str, mode, "FAILED", notes="data_full.json trade_date empty")
            return False
        if not stocks:
            log("data_full.json Stocks 为空 — aborting", "ERROR")
            write_record(date_str, mode, "FAILED", notes="data_full.json Stocks empty")
            return False
        log(f"data_full.json: {len(stocks)} stocks, trade_date={trade_date}")
    except (json.JSONDecodeError, ValueError) as e:
        log(f"data_full.json 非法 JSON: {e} — aborting", "ERROR")
        write_record(date_str, mode, "FAILED", notes=f"data_full.json invalid: {e}")
        return False

    # Phase 2.3: 权威缓存派生 — 硬阻断（替代原 non-blocking 逻辑）
    log("[2.3/7] Materializing authoritative cache...")
    mat_script = ROOT / "scripts" / "materialize_daily_authoritative_cache.py"
    if mat_script.exists():
        mat_result = subprocess.run(["python3", str(mat_script), "--date", date_str.replace("-", "")],
                                    capture_output=True, text=True, cwd=str(ROOT))
        if mat_result.returncode == 0:
            log("Cache materialization completed (authoritative source)")
        else:
            log(f"Cache materialization FAILED (exit={mat_result.returncode}) — aborting", "ERROR")
            if mat_result.stderr:
                for line in mat_result.stderr.strip().split("\n"):
                    if line.strip():
                        log(f"  [materialize:err] {line}", "ERROR")
            write_record(date_str, mode, "FAILED", notes=f"materialize exit={mat_result.returncode}")
            return False
    else:
        log("materialize_daily_authoritative_cache.py not found — aborting", "ERROR")
        write_record(date_str, mode, "FAILED", notes="materialize script missing")
        return False

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
            log("DQ-Gate: report not found — aborting (data quality check required)", "ERROR")
            write_record(date_str, mode, "FAILED", notes="DQ report missing")
            return False
    else:
        log("DQ-Gate: check_data_quality.py not found, skipping", "WARN")

    # Phase 3: Scoring engine
    log("[3/7] Running scoring engine...")
    scoring = LOGIC_DIR / "scoring_engine_v2.py"
    if scoring.exists():
        result = subprocess.run(["python3", str(scoring), "--date", date_str], capture_output=True, text=True, cwd=str(ROOT))
        if result.returncode != 0:
            log(f"scoring_engine_v2 exit={result.returncode} — aborting", "ERROR")
            if result.stderr:
                log(f"  stderr: {result.stderr.strip()[:500]}", "ERROR")
            write_record(date_str, mode, "FAILED", notes=f"scoring_engine_v2 exit={result.returncode}")
            return False
        log("Scoring completed")

    # Phase 3.5: Backfill returns
    backfill = SCRIPTS_DIR / "backfill_returns.py"
    if backfill.exists():
        subprocess.run(["python3", str(backfill)], cwd=str(ROOT))

    # Phase 4: Generate report
    log("[4/7] Generating report...")
    gen_html = LOGIC_DIR / "gen_daily_html.py"
    if gen_html.exists():
        result = subprocess.run(["python3", str(gen_html), "--date", date_str], capture_output=True, text=True, cwd=str(ROOT))
        if result.returncode != 0:
            log(f"gen_daily_html exit={result.returncode} — aborting", "ERROR")
            if result.stderr:
                log(f"  stderr: {result.stderr.strip()[:500]}", "ERROR")
            write_record(date_str, mode, "FAILED", notes=f"gen_daily_html exit={result.returncode}")
            return False
        log("Report generated")

    # Phase 4.1: Inject DQ status into reports
    log("[4.1/7] Injecting DQ status into reports...")
    inject_dq = SCRIPTS_DIR / "inject_dq_status.py"
    if inject_dq.exists():
        result = subprocess.run(["python3", str(inject_dq)], capture_output=True, text=True, cwd=str(ROOT))
        if result.returncode != 0:
            log(f"inject_dq_status exit={result.returncode} — aborting", "ERROR")
            if result.stderr:
                log(f"  stderr: {result.stderr.strip()[:500]}", "ERROR")
            write_record(date_str, mode, "FAILED", notes=f"inject_dq_status exit={result.returncode}")
            return False
        log("DQ status injected")

    # Phase 5: Key stock analysis
    log("[5/7] Key stock analysis — delegated to 腰子")
    # Key stock analysis is AI-driven, triggered by scheduled task

    # Phase 6: Archive data
    log("[6/7] Archiving data...")
    archive_py = SCRIPTS_DIR / "archive_data.py"
    if archive_py.exists():
        result = subprocess.run(["python3", str(archive_py), "--date", date_str], capture_output=True, text=True, cwd=str(ROOT))
        if result.returncode != 0:
            log(f"archive_data exit={result.returncode} — aborting", "ERROR")
            if result.stderr:
                log(f"  stderr: {result.stderr.strip()[:500]}", "ERROR")
            write_record(date_str, mode, "FAILED", notes=f"archive_data exit={result.returncode}")
            return False

    write_record(date_str, mode, "SUCCESS", notes=f"Daily analysis done, report dir: {REPORT_DIR}")
    log("===== Daily Stock Analysis Complete =====")
    return True


def main():
    parser = argparse.ArgumentParser(description="TieLv Daily Workflow")
    parser.add_argument("--mode", required=True, choices=["daily", "eval", "daily_latest", "data_only"],
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
    elif args.mode == "data_only":
        success = run_data_only(args.date)
    else:
        success = run_daily(args.date, args.mode)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
