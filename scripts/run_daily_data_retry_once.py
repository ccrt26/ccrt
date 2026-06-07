#!/usr/bin/env python3
"""
run_daily_data_retry_once.py — v1.1 单次数据获取重试（P3-B 补修）

P3-B 补修：
- 新增 batch_data_collector 步骤以补 K-line 数据。
- 新增 K-line 覆盖率校验（v3.6 兼容，exit 2 if <8/10）。

旧链: tushare_history_sync --daily → materialize → daily_orchestrator --mode daily
     ↑ 原链缺 K-line 回补，data_full.json 不会被刷新，retry 永远无法解 BLOCK。

新链: tushare_history_sync --daily → batch_data_collector → materialize → daily_orchestrator
     ↑ batch_data_collector 从 Sina/K 线 API 重建 data_full.json，materialize 再从 data_full 派生 kline_cache。

用法:
  python3 scripts/run_daily_data_retry_once.py --date 20260604 --attempt 1

退出码:
  0 = ready.json 已存在 或 本次成功（含 K-line 覆盖 >=8/10）
  2 = 任一环节失败 或 K-line 覆盖 <8/10
"""
import argparse, json, os, subprocess, sys, fcntl
from datetime import datetime, timezone
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent)
STATUS_DIR = os.path.join(ROOT, "logs", "daily_data_retry", "status")
SIGNAL_FILE = os.path.join(ROOT, ".claude", "signal_daily_report.json")
PIGEON_CFG = os.path.join(ROOT, "代码文件", "信鸽信息采集", "pigeon_config.json")
DATA_FULL = os.path.join(ROOT, "代码文件", "数据", "data_full.json")


def log(msg, level="INFO"):
    print(f"[{level}] {msg}")


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
    rp = os.path.join(STATUS_DIR, f"{date_str}.ready.json")
    if os.path.exists(rp):
        with open(rp) as f:
            rd = json.load(f)
        log(f"READY_EXISTS: attempt={rd.get('attempt')} at {rd.get('ready_at')}", "SKIP")
        return True
    return False


def verify_signal(date_str):
    """Check if signal is ready for the date."""
    if not os.path.exists(SIGNAL_FILE):
        log("SIGNAL_NOT_FOUND", "BLOCK")
        return False
    try:
        with open(SIGNAL_FILE) as f:
            sig = json.load(f)
    except Exception as e:
        log(f"SIGNAL_PARSE_FAIL: {e}", "BLOCK")
        return False
    if sig.get("date") != date_str:
        log(f"SIGNAL_DATE_MISMATCH: signal={sig.get('date')} expected={date_str}", "BLOCK")
        return False
    if not sig.get("data_ready", False):
        log(f"SIGNAL_NOT_READY: data_ready=false", "BLOCK")
        return False
    # Check stock coverage
    try:
        with open(PIGEON_CFG) as f:
            cfg = json.load(f)
    except Exception as e:
        log(f"PIGEON_CFG_PARSE_FAIL: {e}", "BLOCK")
        return False
    targets = cfg.get("target_stocks", [])
    pool_codes = set(str(s.get("code", "")) for s in targets if s.get("code"))
    sig_codes = set(sig.get("stocks_daily_data", {}).keys())
    missing = pool_codes - sig_codes
    if missing:
        log(f"SIGNAL_MISSING_STOCKS: signal缺 {missing}", "BLOCK")
        return False
    return True


def run_step(script, args, label, timeout=300):
    """Run a subprocess step."""
    full_script = os.path.join(ROOT, script)
    if not os.path.exists(full_script):
        log(f"SCRIPT_NOT_FOUND: {full_script}", "BLOCK")
        return False
    cmd = [sys.executable, full_script] + args
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=ROOT)
        if proc.returncode == 0:
            log(f"[OK] {label}")
            return True
        else:
            log(f"[BLOCK] {label} exit={proc.returncode}", "BLOCK")
            for line in (proc.stdout or "").split("\n")[-3:]:
                if line.strip(): log(f"  {line.strip()}", "FAIL")
            return False
    except subprocess.TimeoutExpired:
        log(f"[TIMEOUT] {label} (timeout={timeout}s)", "BLOCK")
        return False
    except Exception as e:
        log(f"[ERROR] {label}: {e}", "BLOCK")
        return False


def verify_kline_coverage(date_str, min_ok=8):
    """P3-B: 验证 data_full.json 中焦点股 K-line 指定日期覆盖率。
    读取 pigeon_config 10 只焦点股，检查每只的 KDate 最新日期是否 == date_str。

    Returns (ok: bool, matched: int, total: int, missing_codes: list)
    """
    if not os.path.exists(DATA_FULL):
        log(f"DATA_FULL_NOT_FOUND: {DATA_FULL}", "BLOCK")
        return False, 0, 0, []
    try:
        with open(DATA_FULL, "r", encoding="utf-8-sig") as f:
            dfull = json.load(f)
    except Exception as e:
        log(f"DATA_FULL_PARSE_FAIL: {e}", "BLOCK")
        return False, 0, 0, []

    if not os.path.exists(PIGEON_CFG):
        log(f"PIGEON_CFG_NOT_FOUND: {PIGEON_CFG}", "BLOCK")
        return False, 0, 0, []

    try:
        with open(PIGEON_CFG, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        targets = cfg.get("target_stocks", [])
        pool_codes = [str(s.get("code", "")) for s in targets if s.get("code")]
    except Exception as e:
        log(f"PIGEON_CFG_PARSE_FAIL: {e}", "BLOCK")
        return False, 0, 0, []

    stocks_map = {}
    for s in dfull.get("Stocks", []):
        c = str(s.get("Code") or s.get("code", ""))
        if c:
            kd = s.get("KDate", [])
            latest = str(kd[-1]).replace("-", "") if kd else ""
            stocks_map[c] = {"name": s.get("Name", s.get("name", c)), "latest_kdate": latest}

    matched = 0
    missing_codes = []
    for code in pool_codes:
        info = stocks_map.get(code)
        if info and info["latest_kdate"] == date_str:
            matched += 1
        else:
            latest_disp = info["latest_kdate"] if info else "NO_DATA"
            name = info["name"] if info else code
            missing_codes.append(f"{code} {name} (latest KDate: {latest_disp})")

    total = len(pool_codes)
    ok = matched >= min_ok
    if ok:
        log(f"KLINE_COVERAGE PASS: {matched}/{total} >= {min_ok}", "OK")
    else:
        log(f"KLINE_COVERAGE FAIL: {matched}/{total} < {min_ok}", "BLOCK")
        for mc in missing_codes:
            log(f"  缺失: {mc}", "BLOCK")
    return ok, matched, total, missing_codes


def write_ready(date_str, attempt):
    os.makedirs(STATUS_DIR, exist_ok=True)
    ready = {
        "date": date_str,
        "ready_at": datetime.now(timezone.utc).isoformat(),
        "attempt": attempt,
        "command_chain": ["tushare_history_sync.py --daily", "batch_data_collector.py", "materialize", "daily_orchestrator --mode daily"],
        "stock_count": 0,
    }
    if os.path.exists(SIGNAL_FILE):
        try:
            sig = json.loads(open(SIGNAL_FILE).read())
            ready["stock_count"] = len(sig.get("stocks_daily_data", {}))
        except Exception:
            pass
    rp = os.path.join(STATUS_DIR, f"{date_str}.ready.json")
    with open(rp, "w") as f:
        json.dump(ready, f, ensure_ascii=False, indent=2)
    log(f"READY_WRITTEN: {rp}")


def main():
    ap = argparse.ArgumentParser(description="单次数据获取重试")
    ap.add_argument("--date", required=True, help="日期 YYYYMMDD")
    ap.add_argument("--attempt", required=True, type=int, help="尝试序号 1/2/3")
    args = ap.parse_args()
    date_str, attempt = args.date, args.attempt

    # Check if already ready
    if check_ready(date_str):
        sys.exit(0)

    # Acquire lock
    fd = acquire_lock(date_str)
    if fd is None:
        sys.exit(0)  # Another process working on it

    success = False
    try:
        log(f"=== DATA RETRY attempt {attempt}/3 for {date_str} ===")

        # Step 1: tushare sync — 补资金/融资/日频辅助数据 (moneyflow/daily_basic/margin_detail)
        if not run_step("代码文件/tools/tushare_history_sync.py", ["--daily"], "tushare_history_sync"):
            sys.exit(2)

        # Step 1.5 (P3-B 补修): batch_data_collector — 重建 data_full.json，从 Sina K线 API 补充 K-line
        if not run_step("代码文件/每日荐股/scripts/batch_data_collector.py", [],
                        "batch_data_collector", timeout=600):
            sys.exit(2)

        # Step 2: materialize cache — 从刷新后的 data_full 派生 kline_cache/fund_flow_cache
        if not run_step("scripts/materialize_daily_authoritative_cache.py", ["--date", date_str], "materialize_cache"):
            sys.exit(2)

        # Step 3: orchestrator signal — v3.6 数据就绪检查 + 日报 signal
        if not run_step("代码文件/tools/daily_orchestrator.py", ["--mode", "daily", "--date", date_str], "daily_orchestrator"):
            sys.exit(2)

        # Step 4 (P3-B 补修): K-line 覆盖率校验 — 在 verify_signal 前直接检查 data_full KDate
        kline_ok, kline_matched, kline_total, kline_missing = verify_kline_coverage(date_str, min_ok=8)
        if not kline_ok:
            log(f"KLINE_COVERAGE BLOCK: {kline_matched}/{kline_total} < 8/10，不写 ready.json。缺失清单见上。", "BLOCK")
            sys.exit(2)

        # Verify signal
        if verify_signal(date_str):
            write_ready(date_str, attempt)
            log(f"DATA_READY: {date_str} attempt {attempt}")
            success = True
        else:
            log("SIGNAL_NOT_READY_AFTER_CHAIN", "BLOCK")

    finally:
        release_lock(fd, date_str)

    sys.exit(0 if success else 2)


if __name__ == "__main__":
    main()
