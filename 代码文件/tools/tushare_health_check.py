#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tushare API 健康巡检脚本
=========================
每日检查：API连通性/Token有效性/数据完整性/缓存新鲜度

用法：
    python tushare_health_check.py              # 全量检查
    python tushare_health_check.py --quick       # 仅连通性+Token
    python tushare_health_check.py --report      # 输出巡检报告
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "数据", "tushare")
MANIFEST_PATH = os.path.join(DATA_DIR, "manifest.json")
TUSHARE_TOKEN = os.environ.get("TUSHARE_TOKEN", "")

KEY_STOCKS = ["600114", "603019", "301075", "601689", "000967", "601727", "002230", "603092"]

TTL_HOURS = {
    "daily_basic": 6, "moneyflow": 24, "margin_detail": 24,
    "hk_hold": 24, "holder_number": 168, "pledge": 24,
    "share_float": 24, "fina_indicator": 168, "forecast": 168,
    "fina_mainbz": 168, "block_trade": 24,
}

RESULTS = []


def check(msg, status, detail=""):
    symbol = {"PASS": "✓", "FAIL": "✗", "WARN": "⚠"}.get(status, "?")
    RESULTS.append({"check": msg, "status": status, "detail": detail})
    print(f"  {symbol} {msg}" + (f" — {detail}" if detail else ""))


def check_connectivity():
    """检查API连通性"""
    try:
        import tushare as ts
        ts.set_token(TUSHARE_TOKEN)
        pro = ts.pro_api()
        df = pro.daily(ts_code="600114.SH", start_date="20260520", end_date="20260528")
        if df is not None and len(df) > 0:
            check("API连通性", "PASS", f"600114日线返回{len(df)}条")
            return True
        else:
            check("API连通性", "FAIL", "返回空数据")
            return False
    except Exception as e:
        check("API连通性", "FAIL", str(e)[:80])
        return False


def check_token():
    """检查Token有效性"""
    if not TUSHARE_TOKEN:
        check("Token配置", "FAIL", "TUSHARE_TOKEN未设置")
        return False
    check("Token配置", "PASS", f"已设置({len(TUSHARE_TOKEN)}字符)")
    return True


def check_data_completeness():
    """检查8只重点股票的数据完整性"""
    if not os.path.exists(MANIFEST_PATH):
        check("数据完整性", "WARN", "manifest.json不存在，需先运行tushare_history_sync.py")
        return

    with open(MANIFEST_PATH, "r") as f:
        manifest = json.load(f)

    stocks_data = manifest.get("stocks", {})
    missing = []
    for code in KEY_STOCKS:
        if code not in stocks_data:
            missing.append(f"{code}(无数据)")
        else:
            data_types = stocks_data[code].get("data", {})
            empty = [t for t, d in data_types.items() if d.get("records", 0) == 0]
            if empty:
                missing.append(f"{code}({','.join(empty)}无数据)")

    if missing:
        check("数据完整性", "FAIL", "; ".join(missing[:4]))
    else:
        check("数据完整性", "PASS", f"{len(KEY_STOCKS)}只重点股票数据完整")


def check_cache_freshness():
    """检查缓存新鲜度"""
    if not os.path.exists(MANIFEST_PATH):
        return

    with open(MANIFEST_PATH, "r") as f:
        manifest = json.load(f)

    try:
        updated = datetime.fromisoformat(manifest.get("updated", "2000-01-01"))
        age_hours = (datetime.now() - updated.replace(tzinfo=None)).total_seconds() / 3600
    except Exception:
        check("缓存新鲜度", "WARN", "无法解析更新时间")
        return

    stale = []
    for api_type, ttl in TTL_HOURS.items():
        if age_hours > ttl:
            stale.append(f"{api_type}({age_hours:.0f}h>{ttl}h)")

    if stale:
        check("缓存新鲜度", "WARN", f"可能过期: {'; '.join(stale[:3])}")
    else:
        check("缓存新鲜度", "PASS", f"最近更新{age_hours:.1f}小时前")


def check_storage_size():
    """检查存储空间"""
    total_size = 0
    for root, dirs, files in os.walk(DATA_DIR):
        for f in files:
            total_size += os.path.getsize(os.path.join(root, f))
    size_mb = total_size / (1024 * 1024)
    if size_mb > 500:
        check("存储空间", "WARN", f"{size_mb:.1f}MB")
    else:
        check("存储空间", "PASS", f"{size_mb:.1f}MB")


def generate_report():
    """生成巡检报告"""
    total = len(RESULTS)
    passed = sum(1 for r in RESULTS if r["status"] == "PASS")
    failed = sum(1 for r in RESULTS if r["status"] == "FAIL")
    warned = sum(1 for r in RESULTS if r["status"] == "WARN")

    report = {
        "timestamp": datetime.now().isoformat(),
        "summary": {"total": total, "pass": passed, "fail": failed, "warn": warned},
        "overall": "PASS" if failed == 0 else "FAIL",
        "details": RESULTS,
    }

    report_path = os.path.join(DATA_DIR, "health_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n巡检报告: {report_path}")
    print(f"总结: {passed}PASS / {failed}FAIL / {warned}WARN → 总体: {report['overall']}")
    return report


def main():
    parser = argparse.ArgumentParser(description="Tushare API健康巡检")
    parser.add_argument("--quick", action="store_true", help="快速检查(仅连通性+Token)")
    parser.add_argument("--report", action="store_true", help="生成巡检报告文件")
    args = parser.parse_args()

    print(f"Tushare API 健康巡检 — {datetime.now().isoformat()}")
    print(f"数据目录: {DATA_DIR}")

    check_token()
    check_connectivity()

    if not args.quick:
        check_data_completeness()
        check_cache_freshness()
        check_storage_size()

    if args.report:
        generate_report()

    failed = sum(1 for r in RESULTS if r["status"] == "FAIL")
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
