#!/usr/bin/env python3
"""
run_daily_data_retry_once.py — v3.0 单次数据重试（P3-B 补修）

v3.0 修复：
- 完全删除旧链路（tushare_sync/batch_data_collector/materialize_cache/orchestrator）
- retry 不再直接写 ready.json
- retry 不再判断 D07/promote/closure，全部委托 run_daily_production_pipeline
- retry 只做：日期解析→ready检查→锁→触发主闭包→继承退出码
- check_ready 只认 ready=true AND pipeline_status=PASS

用法:
  python3 scripts/run_daily_data_retry_once.py --date 20260604 --attempt 1
  python3 scripts/run_daily_data_retry_once.py --date today --attempt 1

退出码:
  0 = ready.json 已存在(True,PASS) 或 主闭包 PASS
  2 = 主闭包失败或异常
"""
import argparse, json, os, subprocess, sys, fcntl
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent)
STATUS_DIR = os.path.join(ROOT, "logs", "daily_data_retry", "status")


def log(msg, level="INFO"):
    print(f"[{level}] {msg}")


def shanghai_today():
    """Return Shanghai date as YYYYMMDD."""
    return (datetime.now(timezone.utc) + timedelta(hours=8)).strftime("%Y%m%d")


def acquire_lock(date_str):
    os.makedirs(STATUS_DIR, exist_ok=True)
    lock_path = os.path.join(STATUS_DIR, f"{date_str}.lock")
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_WRONLY, 0o644)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        os.write(fd, str(os.getpid()).encode())
        return fd
    except (IOError, BlockingIOError):
        if os.path.exists(lock_path):
            log(f"LOCK_HELD: {lock_path} — 另一个 retry 正在运行", "SKIP")
        return None


def release_lock(fd, date_str):
    if fd is not None:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    lock_path = os.path.join(STATUS_DIR, f"{date_str}.lock")
    try:
        os.remove(lock_path)
    except OSError:
        pass


def check_ready(date_str):
    """只在 ready=true AND pipeline_status=PASS 时返回 True。

    BLOCK 状态的 ready.json 不得被视为"已完成"。
    """
    rp = os.path.join(STATUS_DIR, f"{date_str}.ready.json")
    if os.path.exists(rp):
        with open(rp) as f:
            rd = json.load(f)
        is_ready = rd.get("ready") is True
        ps = rd.get("pipeline_status", "")
        if is_ready and ps == "PASS":
            log(f"READY_EXISTS: ready_at={rd.get('ready_at')}", "SKIP")
            return True
        log(f"READY_BLOCK_EXISTS_CONTINUE: ready={rd.get('ready')} pipeline_status={ps}", "WARN")
        return False
    return False


def main():
    ap = argparse.ArgumentParser(description="单次数据重试（仅委托主闭包）")
    ap.add_argument("--date", required=True, help="日期 YYYYMMDD，或 today（自动解析上海日期）")
    ap.add_argument("--attempt", required=True, type=int, help="尝试序号 1/2/3")
    args = ap.parse_args()

    # 解析 today 为上海日期
    date_str = shanghai_today() if args.date == "today" else args.date
    attempt = args.attempt

    log(f"date_str={date_str}, attempt={attempt}")

    # Check if already ready (only true if ready=true AND pipeline_status=PASS)
    if check_ready(date_str):
        sys.exit(0)

    # Acquire lock
    fd = acquire_lock(date_str)
    if fd is None:
        sys.exit(0)  # Another process working on it

    try:
        log(f"=== DATA RETRY attempt {attempt}/3 for {date_str} ===")
        log("retry v3.0: 委托 run_daily_production_pipeline 为单一权威", "OK")

        # Single authority: delegate to production pipeline.
        # retry does NOT call tushare_sync, batch_data_collector, materialize,
        # daily_orchestrator, verify_signal, verify_kline_coverage, or write_ready.
        # D07 check, promote, release gate, closure, ready.json write are all
        # handled internally by the production pipeline.
        pipeline_script = "scripts/run_daily_production_pipeline.py"
        pipeline_path = os.path.join(ROOT, pipeline_script)
        if not os.path.exists(pipeline_path):
            log(f"PRODUCTION_PIPELINE_NOT_FOUND: {pipeline_path}", "BLOCK")
            sys.exit(2)

        pipeline_cmd = [sys.executable, pipeline_path, "--date", date_str]
        log(f"Invoking production pipeline: {' '.join(pipeline_cmd)}")

        pipeline_proc = subprocess.run(
            pipeline_cmd,
            capture_output=True, text=True, timeout=600, cwd=ROOT
        )
        pipeline_rc = pipeline_proc.returncode
        # Print pipeline output for audit trail
        for line in (pipeline_proc.stdout or "").split("\n"):
            if line.strip():
                log(f"  pipeline: {line.strip()}", "INFO")
        for line in (pipeline_proc.stderr or "").split("\n")[-5:]:
            if line.strip():
                log(f"  pipeline_err: {line.strip()}", "INFO")

        if pipeline_rc == 0:
            log(f"PRODUCTION_PIPELINE_PASS: exit={pipeline_rc}", "OK")
            sys.exit(0)
        else:
            log(f"PRODUCTION_PIPELINE_BLOCK: exit={pipeline_rc}", "BLOCK")
            sys.exit(pipeline_rc)  # inherit exit code directly

    except subprocess.TimeoutExpired:
        log("PRODUCTION_PIPELINE_TIMEOUT: 600s exceeded", "BLOCK")
        sys.exit(2)
    except Exception as e:
        log(f"PRODUCTION_PIPELINE_ERROR: {e}", "BLOCK")
        sys.exit(2)
    finally:
        release_lock(fd, date_str)


if __name__ == "__main__":
    main()
