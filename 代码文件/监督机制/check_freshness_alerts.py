#!/usr/bin/env python3
"""
check_freshness_alerts.py — 管线数据新鲜度巡检

检查6项关键数据产物的新鲜度，超出TTL则告警。
每日盘前(8:00)由cron触发，非交易日跳过。

产出: 重点股票/次日评估/freshness_report_{date}.json

Code level: L2
"""
import json
import os
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT / "代码文件" / "数据"
TUSHARE_DIR = DATA_DIR / "tushare"
KLINE_DIR = DATA_DIR / "kline_cache"
EVAL_DIR = ROOT / "重点股票" / "次日评估"
REPORT_DIR = ROOT / "重点股票" / "股票报告"

TODAY = date.today()
TODAY_STR = TODAY.strftime("%Y%m%d")
TODAY_ISO = TODAY.isoformat()

# TTL配置（小时）
TTL = {
    "data_full": 48,          # 管线快照（含上周数据可接受）
    "eval_data": 24,          # 评估数据必须在当天有
    "kline_cache": 24,        # K线缓存应在收盘后更新
    "tushare_moneyflow": 24,  # 资金流向日频
    "tushare_daily_basic": 24, # 每日指标日频
    "daily_report": 24,       # 日报应在当天生成
}


def is_trading_day(check_date=None):
    """调用is_market_open.py判断是否交易日"""
    if check_date is None:
        check_date = TODAY_ISO
    script = ROOT / "代码文件" / "每日荐股" / "scripts" / "is_market_open.py"
    if not script.exists():
        return True  # 脚本不存在则默认是交易日
    holiday_file = ROOT / "每日荐股" / "运营记录" / "holidays_2026.csv"
    args = ["python3", str(script), check_date]
    if holiday_file.exists():
        args += [f"--holiday={holiday_file}"]
    result = subprocess.run(args, capture_output=True, text=True, timeout=10)
    return result.returncode == 0


def check_data_full():
    """检查data_full.json的新鲜度"""
    path = DATA_DIR / "data_full.json"
    if not path.exists():
        return {"status": "FAIL", "detail": "文件不存在"}
    mtime = datetime.fromtimestamp(os.path.getmtime(path))
    age_h = (datetime.now() - mtime).total_seconds() / 3600
    if age_h > TTL["data_full"]:
        return {"status": "WARN", "detail": f"最后更新{mtime.strftime('%m-%d %H:%M')}，距今{age_h:.0f}h"}
    return {"status": "PASS", "detail": f"新鲜({age_h:.0f}h内更新)"}


def check_eval_data():
    """检查今天评估数据是否生成"""
    for prefix in ["", "评估数据_"]:
        for ext in [".json"]:
            path = EVAL_DIR / f"{prefix}{TODAY_STR}{ext}"
            if path.exists():
                try:
                    with open(path) as f:
                        data = json.load(f)
                    stocks = data.get("Stocks", data.get("stocks", []))
                    sc = data.get("meta", {}).get("stock_count", len(stocks))
                    if sc >= 10:
                        return {"status": "PASS", "detail": f"已生成，{sc}只股票"}
                    else:
                        return {"status": "WARN", "detail": f"已生成但仅{sc}/10只股票"}
                except Exception as e:
                    return {"status": "WARN", "detail": f"文件存在但解析失败: {e}"}
    # 也试最近一个交易日
    for d in range(1, 5):
        test = (TODAY - __import__("datetime").timedelta(days=d)).strftime("%Y%m%d")
        for prefix in ["", "评估数据_"]:
            path = EVAL_DIR / f"{prefix}{test}{'.json'}"
            if path.exists():
                return {"status": "WARN", "detail": f"最新为{test}（非今日）"}
    return {"status": "FAIL", "detail": "最近5天均无评估数据"}


def check_kline():
    """检查K线缓存是否包含最新交易日"""
    import glob
    files = list(KLINE_DIR.glob("*.json"))
    if not files:
        return {"status": "FAIL", "detail": "kline_cache目录为空"}
    # 取任意5只股票检查最新日期
    latest_dates = []
    for f in files[:5]:
        try:
            with open(f) as fh:
                data = json.load(fh)
            if isinstance(data, list) and data:
                for d in reversed(data):
                    dt = d.get("date", d.get("day", ""))
                    if dt:
                        latest_dates.append(dt)
                        break
        except Exception:
            pass
    if latest_dates:
        newest = max(latest_dates)
        age = (TODAY_ISO > newest)  # newest is older than today?
        if TODAY_ISO == newest:
            return {"status": "PASS", "detail": f"最新数据: {newest}"}
        else:
            return {"status": "WARN", "detail": f"最新数据: {newest}（非今日）"}
    return {"status": "WARN", "detail": "无法读取K线日期"}


def check_tushare(api_name):
    """检查Tushare某类数据的新鲜度"""
    path = TUSHARE_DIR / api_name
    files = list(path.glob("*.json"))
    if not files:
        return {"status": "FAIL", "detail": f"{api_name}目录无数据"}
    # 取第一个文件检查最新日期
    for f in files[:3]:
        try:
            with open(f) as fh:
                data = json.load(fh)
            if isinstance(data, list):
                for d in reversed(data):
                    for key in ("trade_date", "date", "end_date"):
                        if key in d and d[key]:
                            latest = str(d[key])
                            latest_dt = latest[:10] if "-" in latest else latest
                            if TODAY_STR in latest_dt or TODAY_ISO[:7] in latest_dt:
                                return {"status": "PASS", "detail": f"最新: {latest_dt}"}
                            return {"status": "WARN", "detail": f"最新: {latest_dt}"}
        except Exception:
            pass
    return {"status": "WARN", "detail": f"目录存在但数据日期无法判定"}


def check_daily_report():
    """检查今日日报是否存在"""
    stock_dirs = list(REPORT_DIR.glob("*"))
    if not stock_dirs:
        return {"status": "WARN", "detail": "无股票报告目录"}
    found = 0
    for sdir in stock_dirs[:10]:
        for pat in [f"*{TODAY_STR}*", f"*{TODAY_ISO[:7]}*"]:
            if list(sdir.glob(pat)):
                found += 1
                break
    if found >= 5:
        return {"status": "PASS", "detail": f"已生成({found}只股票有今日报告)"}
    return {"status": "WARN", "detail": f"仅{found}只股票有今日或最近日报"}


def main():
    if not is_trading_day():
        print(f"[INFO] {TODAY_ISO} 非交易日，跳过巡检")
        report = {
            "date": TODAY_STR,
            "is_trading_day": False,
            "checks": {},
            "overall": "SKIP (非交易日)",
        }
    else:
        checks = {
            "data_full": check_data_full(),
            "eval_data": check_eval_data(),
            "kline_cache": check_kline(),
            "tushare_moneyflow": check_tushare("moneyflow"),
            "tushare_daily_basic": check_tushare("daily_basic"),
            "daily_report": check_daily_report(),
        }
        fails = sum(1 for c in checks.values() if c["status"] == "FAIL")
        warns = sum(1 for c in checks.values() if c["status"] == "WARN")
        if fails:
            overall = f"FAIL ({fails}项失败)"
        elif warns:
            overall = f"WARN ({warns}项警告)"
        else:
            overall = "PASS"
        report = {
            "date": TODAY_STR,
            "is_trading_day": True,
            "checks": checks,
            "overall": overall,
        }

        # 显示结果
        print(f"\n=== 管线新鲜度巡检 [{TODAY_ISO}] ===")
        for name, result in checks.items():
            icon = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌"}.get(result["status"], "❓")
            print(f"  {icon} {name:<25} {result['detail']}")
        print(f"\n  总结: {overall}")
        if fails:
            print("  ⚠️ 建议在开盘前修复 FAIL 项")
            sys.exit(1)

    # 写入报告（无论是否交易日）
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    report_path = EVAL_DIR / f"freshness_report_{TODAY_STR}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n  报告: {report_path}")


if __name__ == "__main__":
    main()
