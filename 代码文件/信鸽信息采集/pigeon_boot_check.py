#!/usr/bin/env python3
"""信鸽开机自检 — 检测当日采集是否漏执行，漏则补齐

Replaces pigeon_boot_check.ps1. macOS compatible.
Code level: L1
"""
import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent.parent)
SCRIPT_DIR = os.path.join(ROOT, "代码文件", "信鸽信息采集")
DATA_DIR = os.path.join(ROOT, "重点股票", "消息面数据")
BOOT_LOG = os.path.join(DATA_DIR, "boot_check.log")

today = date.today().isoformat()
events_file = os.path.join(DATA_DIR, f"{today}_events.json")
os.makedirs(DATA_DIR, exist_ok=True)


def boot_log(level, msg):
    ts = date.today().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} [{level}] {msg}"
    print(line)
    with open(BOOT_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def main():
    # Check if already collected today
    if os.path.exists(events_file):
        boot_log("INFO", f"今日采集已完成: {events_file}")
        boot_log("INFO", "开机自检通过，跳过采集。")
        return 0

    boot_log("INFO", f"今日采集缺失 ({today})，开机补采启动...")

    # Holiday check
    config_path = os.path.join(SCRIPT_DIR, "pigeon_config.json")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        schedule = config.get("schedule", {})
        if schedule.get("skip_holidays"):
            holidays_file = os.path.join(ROOT, schedule.get("holidays_file", ""))
            if os.path.exists(holidays_file):
                with open(holidays_file, "r", encoding="utf-8") as f:
                    if today in f.read():
                        boot_log("INFO", f"今日为节假日 ({today})，跳过采集。")
                        return 0
    else:
        boot_log("WARN", f"配置文件不存在: {config_path}，使用默认参数继续。")

    # Run collector
    boot_log("INFO", "启动信鸽采集: pigeon_collector.py")
    collector = os.path.join(SCRIPT_DIR, "pigeon_collector.py")
    if not os.path.exists(collector):
        boot_log("ERROR", f"采集脚本不存在: {collector}")
        return 2

    result = subprocess.run([sys.executable, collector], capture_output=True, text=True, cwd=ROOT)
    summary = "\n".join(result.stdout.strip().split("\n")[-5:]) if result.stdout else result.stderr
    boot_log("INFO", f"采集完成 | ExitCode={result.returncode} | {summary}")

    if result.returncode == 0:
        boot_log("INFO", "开机补采成功。")
    elif result.returncode == 1:
        boot_log("WARN", "开机补采部分完成(部分源失败)。")
    else:
        boot_log("ERROR", "开机补采失败(全部源不可用)。")

    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
