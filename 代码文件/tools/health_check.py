#!/usr/bin/env python3
"""health_check.py — 数据健康检测

Replaces health_check.ps1.
API connectivity + data completeness + backfill coverage check.
Outputs JSON health report. L3阻断时 exit 1.
Code level: L1

P2+P4 upgrade (2026-05-28): per-source health persistence + hourly mode.
"""
import argparse
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent.parent)
DATA_DIR = os.path.join(ROOT, "代码文件", "数据")
HEALTH_FILES = {
    "tencent": os.path.join(DATA_DIR, ".tencent_health.json"),
    "sina": os.path.join(DATA_DIR, ".sina_health.json"),
    "eastmoney": os.path.join(DATA_DIR, ".eastmoney_health.json"),
}
TZ_SHANGHAI = timezone(timedelta(hours=8))


def persist_health(source, source_id, status, latency_ms, messages):
    """Write per-source health file for 1+2 architecture compliance."""
    health_file = HEALTH_FILES.get(source)
    if not health_file:
        return
    now = datetime.now(TZ_SHANGHAI).isoformat()
    try:
        with open(health_file, "r", encoding="utf-8") as f:
            prev = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        prev = {"ConsecutiveFails": 0, "LastSuccess": None}

    fails = prev.get("ConsecutiveFails", 0)
    last_success = prev.get("LastSuccess")
    if status == "ok":
        fails = 0
        last_success = now
    else:
        fails += 1

    record = {
        "Source": source,
        "SourceId": source_id,
        "LastCheck": now,
        "LatencyMs": latency_ms,
        "Status": status,
        "ConsecutiveFails": fails,
        "LastSuccess": last_success,
        "TTL": 3600,
    }
    with open(health_file, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)


def check_api_connectivity(persist=False):
    """Check primary and backup API endpoints. Returns per-source results."""
    results = {"sources": {}}
    messages = []
    flag = "normal"

    # Tencent quote API [1]
    t_start = time.time()
    t_status, t_latency, t_msg = "down", 0, ""
    try:
        req = urllib.request.Request("http://qt.gtimg.cn/q=sh000001")
        resp = urllib.request.urlopen(req, timeout=3)
        t_latency = round((time.time() - t_start) * 1000)
        content = resp.read().decode("gbk", errors="replace")
        if "sh000001" in content:
            t_status, t_msg = "ok", f"腾讯API[1]正常 ({t_latency}ms)"
        else:
            t_status, t_msg = "degraded", "腾讯API[1]响应异常"
            flag = "degraded"
    except Exception as e:
        t_status, t_msg = "down", f"腾讯API[1]不可达: {e}"
        flag = "degraded"
    messages.append(t_msg)
    results["sources"]["tencent"] = {"status": t_status, "latency_ms": t_latency}
    if persist:
        persist_health("tencent", "[1]", t_status, t_latency, [t_msg])

    # Sina API [2]
    s_start = time.time()
    s_status, s_latency, s_msg = "down", 0, ""
    try:
        req = urllib.request.Request("http://hq.sinajs.cn/list=sh000001")
        resp = urllib.request.urlopen(req, timeout=3)
        s_latency = round((time.time() - s_start) * 1000)
        content = resp.read().decode("gbk", errors="replace")
        if "上证指数" in content:
            s_status, s_msg = "ok", f"新浪API[2]备源可用 ({s_latency}ms)"
        else:
            s_status, s_msg = "degraded", "新浪API[2]响应异常"
    except Exception as e:
        s_status, s_msg = "down", f"新浪API[2]不可达: {e}"
    messages.append(s_msg)
    results["sources"]["sina"] = {"status": s_status, "latency_ms": s_latency}
    if persist:
        persist_health("sina", "[2]", s_status, s_latency, [s_msg])

    # EastMoney API [3]
    e_start = time.time()
    e_status, e_latency, e_msg = "down", 0, ""
    try:
        req = urllib.request.Request("https://datacenter.eastmoney.com/api/data/get")
        urllib.request.urlopen(req, timeout=3)
        e_latency = round((time.time() - e_start) * 1000)
        e_status, e_msg = "ok", f"东财API[3]正常 ({e_latency}ms)"
    except Exception as e:
        e_status, e_msg = "down", f"东财API[3]不可达: {e}"
        flag = "degraded"
    messages.append(e_msg)
    results["sources"]["eastmoney"] = {"status": e_status, "latency_ms": e_latency}
    if persist:
        persist_health("eastmoney", "[3]", e_status, e_latency, [e_msg])

    results["flag"] = flag
    results["messages"] = messages
    return results


def check_data_file(data_file):
    """Check data file existence and basic integrity."""
    results = {}
    if not data_file or not os.path.exists(data_file):
        return {"data_file": {"exists": False, "flag": "blocked", "message": f"数据文件不存在: {data_file}"}}

    try:
        with open(data_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return {"data_file": {"exists": True, "valid": False, "flag": "blocked", "message": f"JSON解析失败: {e}"}}

    stock_count = len(data.get("quotes", {})) or len(data.get("stocks", [])) or 0
    results["data_file"] = {
        "exists": True, "valid": True,
        "stock_count": stock_count,
        "keys": list(data.keys()),
        "flag": "normal" if stock_count > 0 else "degraded",
    }
    return results


def main():
    parser = argparse.ArgumentParser(description="Data health check")
    parser.add_argument("--mode", default="boot", choices=["boot", "hourly", "daily_sim", "key_stock", "eval"])
    parser.add_argument("--data-file", default="", help="Data file to check")
    parser.add_argument("--root-dir", default=ROOT, help="Project root")
    parser.add_argument("--output-html", default="", help="Output HTML report path")
    parser.add_argument("--persist", action="store_true", help="Persist per-source health files")
    args = parser.parse_args()

    result = {
        "CheckedAt": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "Mode": args.mode,
        "Flag": "normal",
        "AlertLevel": "L0",
        "Passed": True,
        "Messages": [],
    }

    # API connectivity (always run; persist if requested)
    persist = args.persist or args.mode == "hourly"
    api_results = check_api_connectivity(persist=persist)
    result["T0_Status"] = {"flag": api_results.get("flag", "normal"),
                           "messages": api_results.get("messages", []),
                           "sources": api_results.get("sources", {})}
    for msg in api_results.get("messages", []):
        result["Messages"].append(msg)
    if api_results.get("flag") == "degraded":
        result["Flag"] = "degraded"

    # Hourly mode: only API check, skip data file validation
    if args.mode == "hourly":
        result["Mode"] = "hourly"
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result["Flag"] == "blocked":
            sys.exit(1)
        return

    # Data file check (skip for boot/hourly)
    if args.mode not in ("boot", "hourly"):
        data_results = check_data_file(args.data_file)
        result["T1_Status"] = data_results.get("data_file", {})
        df = data_results.get("data_file", {})
        if df.get("flag") == "blocked":
            result["Flag"] = "blocked"
            result["AlertLevel"] = "L3"
            result["Passed"] = False
            result["Messages"].append(df.get("message", ""))

    # Final determination
    if result["Flag"] == "blocked":
        result["AlertLevel"] = "L3"
        result["Passed"] = False
    elif result["Flag"] == "degraded":
        result["AlertLevel"] = "L2"

    print(json.dumps(result, ensure_ascii=False, indent=2))

    if result["Flag"] == "blocked":
        sys.exit(1)


if __name__ == "__main__":
    main()
