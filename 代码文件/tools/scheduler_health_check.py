#!/usr/bin/env python3
"""scheduler_health_check.py — 调度系统心跳监控

每30分钟由crontab触发。检查关键进程/数据新鲜度/磁盘空间。
异常写日志，不发送通知（通知由人工或Claude Code处理）。

用法:
    python3 代码文件/tools/scheduler_health_check.py

退出码:
    0 — 全部健康
    1 — 有WARN项
    2 — 有FAIL项

Code level: L0
Design: 审计报告/架构设计/design_scheduling_separation_v1.0.md
"""
import json
import os
import shutil
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent.parent)
SCRIPTS_DIR = os.path.join(ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from runtime_secret_loader import TUSHARE_TOKEN, check_secret_readiness

TZ_SHANGHAI = timezone(timedelta(hours=8))
LOG_DIR = os.path.join(ROOT, "每日荐股", "运营记录")
DATA_DIR = os.path.join(ROOT, "代码文件", "数据")
EVENTS_DB = os.path.join(ROOT, "重点股票", "消息面数据", "events_db.json")
SIGNAL_DIR = os.path.join(ROOT, ".claude")

# Expected crontab entries (minimum count)
EXPECTED_CRON_COUNT = 5

CHECK_ITEMS = []


def ensure_dirs():
    os.makedirs(LOG_DIR, exist_ok=True)


def log(msg, level="INFO"):
    timestamp = datetime.now(TZ_SHANGHAI).strftime("%Y-%m-%d %H:%M:%S")
    today = datetime.now(TZ_SHANGHAI).strftime("%Y%m%d")
    log_file = os.path.join(LOG_DIR, f"health_check_{today}.log")
    line = f"[{timestamp}][{level}] {msg}"
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def check(name):
    """Decorator-style registry for check items."""
    def decorator(fn):
        CHECK_ITEMS.append((name, fn))
        return fn
    return decorator


@check("disk_space")
def check_disk_space():
    """Check remaining disk space > 1GB."""
    usage = shutil.disk_usage(ROOT)
    free_gb = usage.free / (1024 ** 3)
    if free_gb < 1.0:
        return "FAIL", f"Low disk space: {free_gb:.1f}GB free"
    if free_gb < 5.0:
        return "WARN", f"Disk space: {free_gb:.1f}GB free"
    return "PASS", f"Disk: {free_gb:.1f}GB free"


@check("runtime_secret_readiness")
def check_runtime_secret_readiness():
    """Check launchd-visible secrets before scheduled production runs."""
    status = check_secret_readiness(TUSHARE_TOKEN, launchd_compatible=True)
    if status.get("status") == "PASS":
        return "PASS", f"{TUSHARE_TOKEN} available via {status.get('source')}"
    return "FAIL", status.get("reason", f"{TUSHARE_TOKEN} unavailable for launchd")


@check("data_cache_freshness")
def check_data_cache_freshness():
    """Check data cache directory has recent files (trading days only)."""
    now = datetime.now(TZ_SHANGHAI)
    if now.weekday() >= 5:
        return "SKIP", "Weekend, skipping cache freshness check"

    if not os.path.isdir(DATA_DIR):
        return "FAIL", f"Data dir not found: {DATA_DIR}"

    cutoff = now.timestamp() - 86400  # 24 hours
    recent = 0
    for entry in os.listdir(DATA_DIR):
        fpath = os.path.join(DATA_DIR, entry)
        if os.path.isfile(fpath) and not entry.startswith("."):
            if os.path.getmtime(fpath) >= cutoff:
                recent += 1

    if recent == 0:
        return "FAIL", "No cache files updated in last 24h"
    if recent < 3:
        return "WARN", f"Only {recent} cache files updated in last 24h"
    return "PASS", f"{recent} cache files updated in last 24h"


@check("events_db_freshness")
def check_events_db_freshness():
    """Check events_db.json has been updated recently (trading days only)."""
    now = datetime.now(TZ_SHANGHAI)
    if now.weekday() >= 5:
        return "SKIP", "Weekend, skipping events DB check"

    if not os.path.exists(EVENTS_DB):
        return "WARN", "events_db.json not found"

    mtime = os.path.getmtime(EVENTS_DB)
    age_hours = (now.timestamp() - mtime) / 3600

    if age_hours > 72:
        return "FAIL", f"events_db last updated {age_hours:.0f}h ago"
    if age_hours > 48:
        return "WARN", f"events_db last updated {age_hours:.0f}h ago"
    return "PASS", f"events_db updated {age_hours:.0f}h ago"


@check("signal_stale")
def check_signal_stale():
    """Check for stale signal files that Claude Code hasn't processed."""
    if not os.path.isdir(SIGNAL_DIR):
        return "SKIP", "Signal dir not found"

    now = datetime.now(TZ_SHANGHAI)
    today = now.strftime("%Y%m%d")
    stale_signals = []
    ignored_historical = 0
    for entry in os.listdir(SIGNAL_DIR):
        if not entry.startswith("signal_") or not entry.endswith(".json"):
            continue
        fpath = os.path.join(SIGNAL_DIR, entry)
        mtime = os.path.getmtime(fpath)
        age_hours = (now.timestamp() - mtime) / 3600
        if age_hours > 4:
            signal_date = ""
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                signal_date = str(payload.get("date") or payload.get("trade_date") or "")
            except (OSError, json.JSONDecodeError):
                signal_date = ""
            if signal_date and signal_date != today:
                ignored_historical += 1
                continue
            stale_signals.append(f"{entry} ({age_hours:.0f}h)")

    if stale_signals:
        return "WARN", f"Stale signals: {', '.join(stale_signals)}"
    if ignored_historical:
        return "PASS", f"No current stale signals; ignored {ignored_historical} historical signal(s)"
    return "PASS", "No stale signals"


def main():
    ensure_dirs()
    now = datetime.now(TZ_SHANGHAI)
    log(f"Health check started at {now.strftime('%H:%M:%S')}")

    results = []
    has_fail = False
    has_warn = False

    for name, fn in CHECK_ITEMS:
        try:
            status, detail = fn()
        except Exception as e:
            status, detail = "ERROR", str(e)

        results.append((name, status, detail))
        if status == "FAIL":
            has_fail = True
        elif status == "WARN":
            has_warn = True

    # Summary log
    for name, status, detail in results:
        log(f"[{status}] {name}: {detail}")

    # Determine exit code
    if has_fail:
        log("Health check: FAIL", "ERROR")
        sys.exit(2)
    elif has_warn:
        log("Health check: WARN")
        sys.exit(1)
    else:
        log("Health check: PASS", "OK")
        sys.exit(0)


if __name__ == "__main__":
    main()
