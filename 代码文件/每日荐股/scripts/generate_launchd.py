#!/usr/bin/env python3
"""generate_launchd.py — macOS launchd 统一调度注册器（铁律量化唯一入口）

macOS 当前唯一调度注册器。禁止使用 crontab、GitHub Actions schedule、PS1 注册。
所有定时任务通过本脚本注册到 launchd。

Usage:
    python3 generate_launchd.py --list                  # list all scheduled tasks
    python3 generate_launchd.py --install all            # install all tasks
    python3 generate_launchd.py --install <task_name>    # install a specific task
    python3 generate_launchd.py --uninstall <task_name>  # uninstall a task
    python3 generate_launchd.py --status                 # show status of all tasks

Code level: L1
Design: ADR-3 (launchd not cron)
"""
import argparse
import json
import os
import plistlib
import subprocess
import sys
from pathlib import Path

PLIST_DIR = Path.home() / "Library" / "LaunchAgents"
LABEL_PREFIX = "com.tielv."
PROJECT_ROOT = Path("/Users/ccrt/ccrt")
PROJECT_PYTHON = str(PROJECT_ROOT / ".venv" / "bin" / "python")

# ── Weekday helpers ──────────────────────────────────
WEEKDAYS = [1, 2, 3, 4, 5]  # 周一至周五


def weekday_schedules(hour, minute):
    """Generate StartCalendarInterval dicts for Mon-Fri at given hour:minute."""
    return [{"Hour": hour, "Minute": minute, "Weekday": wd} for wd in WEEKDAYS]


# ── Task definitions ──────────────────────────────────
# Every task here is the sole authoritative schedule definition.
# No other scheduler (crontab, GitHub Actions, Task Scheduler, PS1) may register these.

def emit(message=""):
    sys.stdout.write(str(message) + "\n")


TASK_DEFS = {
    "git_autosweep": {
        "label_suffix": "git-autosweep",
        "description": "自动 Git 同步清扫（每小时 :07）",
        "schedule": [{"Minute": 7}],
        "command": PROJECT_PYTHON,
        "args": [str(PROJECT_ROOT / "代码文件" / "tools" / "git_autosweep.py"), "--commit", "--push"],
        "run_at_load": True,
    },
    "pigeon": {
        "label_suffix": "pigeon",
        "description": "信鸽事件采集（交易日 19:07，周一至周五）",
        "schedule": weekday_schedules(19, 7),
        "command": PROJECT_PYTHON,
        "args": [str(PROJECT_ROOT / "代码文件" / "tools" / "daily_orchestrator.py"), "--mode", "pigeon"],
        "run_at_load": False,
    },
    "daily_signal": {
        "label_suffix": "daily-signal",
        "description": "日报数据链与信号（交易日 16:30，周一至周五）",
        "schedule": weekday_schedules(16, 30),
        "command": PROJECT_PYTHON,
        "args": [str(PROJECT_ROOT / "scripts" / "run_daily_data_pipeline_today.py")],
        "run_at_load": False,
    },
    "deep_signal": {
        "label_suffix": "deep-signal",
        "description": "深度分析信号（周五 20:30）",
        "schedule": [{"Hour": 20, "Minute": 30, "Weekday": 5}],
        "command": PROJECT_PYTHON,
        "args": [str(PROJECT_ROOT / "代码文件" / "tools" / "daily_orchestrator.py"), "--mode", "deep"],
        "run_at_load": False,
    },
    "post_eval": {
        "label_suffix": "post-eval",
        "description": "后评估正式链路（交易日 17:20，周一至周五）",
        "schedule": weekday_schedules(17, 20),
        "command": PROJECT_PYTHON,
        "args": [str(PROJECT_ROOT / "代码文件" / "每日荐股" / "scripts" / "daily_workflow.py"), "--mode", "eval"],
        "run_at_load": False,
    },
    "scheduler_health": {
        "label_suffix": "scheduler-health",
        "description": "调度心跳监控（每小时 :03、:33）",
        "schedule": [{"Minute": 3}, {"Minute": 33}],
        "command": PROJECT_PYTHON,
        "args": [str(PROJECT_ROOT / "代码文件" / "tools" / "scheduler_health_check.py")],
        "run_at_load": True,
    },
    "sim_trading": {
        "label_suffix": "sim-trading",
        "description": "模拟交易引擎开盘执行（交易日 09:45，周一至周五）",
        "schedule": weekday_schedules(9, 45),
        "command": PROJECT_PYTHON,
        "args": [str(PROJECT_ROOT / "模拟交易" / "sim_orchestrator.py")],
        "run_at_load": False,
    },
    "feishu_bridge": {
        "label_suffix": "feishu-bridge",
        "description": "飞书消息桥接（每 30 秒轮询）",
        "interval": 30,
        "command": PROJECT_PYTHON,
        "args": [str(PROJECT_ROOT / "代码文件" / "tools" / "feishu_bridge.py"), "--once"],
        "run_at_load": True,
    },
    "im_consumer": {
        "label_suffix": "im-consumer",
        "description": "IM 消息消费（每 30 秒轮询）",
        "interval": 30,
        "command": PROJECT_PYTHON,
        "args": [str(PROJECT_ROOT / "代码文件" / "tools" / "im_consumer.py"), "--once"],
        "run_at_load": True,
    },
}


def generate_plist(task_name, task_def):
    """Generate a launchd plist dict for a task."""
    label = f"{LABEL_PREFIX}{task_def['label_suffix']}"
    log_dir = PROJECT_ROOT / "代码文件" / "数据" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    plist = {
        "Label": label,
        "ProgramArguments": [task_def["command"]] + task_def["args"],
        "WorkingDirectory": str(PROJECT_ROOT),
        "RunAtLoad": task_def.get("run_at_load", False),
        "StandardOutPath": str(log_dir / f"{task_def['label_suffix']}.stdout.log"),
        "StandardErrorPath": str(log_dir / f"{task_def['label_suffix']}.stderr.log"),
        "KeepAlive": False,
    }

    if "interval" in task_def:
        # StartInterval-based task (e.g., every 30 seconds)
        plist["StartInterval"] = task_def["interval"]
    elif "schedule" in task_def:
        # StartCalendarInterval-based task
        schedule = task_def["schedule"]
        if isinstance(schedule, list):
            # schedule is already a list of calendar dicts
            plist["StartCalendarInterval"] = [{k: v for k, v in s.items() if v is not None} for s in schedule]
        else:
            # Single dict, wrap in list
            plist["StartCalendarInterval"] = [{k: v for k, v in schedule.items() if v is not None}]

    return plist


def install_task(task_name, task_def):
    """Write plist file and load into launchd."""
    PLIST_DIR.mkdir(parents=True, exist_ok=True)
    label = f"{LABEL_PREFIX}{task_def['label_suffix']}"
    plist_path = PLIST_DIR / f"{label}.plist"

    plist = generate_plist(task_name, task_def)
    with open(plist_path, "wb") as f:
        plistlib.dump(plist, f)

    # Unload first if exists, then load
    subprocess.run(["launchctl", "unload", str(plist_path)],
                   capture_output=True)
    result = subprocess.run(["launchctl", "load", str(plist_path)],
                            capture_output=True, text=True)
    if result.returncode == 0:
        emit(f"  OK: {label} installed and loaded")
    else:
        emit(f"  WARN: {label} plist written but load failed: {result.stderr.strip()}")
    return plist_path


def uninstall_task(task_name, task_def):
    """Unload and remove plist file."""
    label = f"{LABEL_PREFIX}{task_def['label_suffix']}"
    plist_path = PLIST_DIR / f"{label}.plist"

    if plist_path.exists():
        subprocess.run(["launchctl", "unload", str(plist_path)],
                       capture_output=True)
        plist_path.unlink()
        emit(f"  OK: {label} uninstalled")
    else:
        emit(f"  SKIP: {label} not installed")


def show_status():
    """Display status of all defined tasks."""
    emit(f"{'Task':<25} {'Status':<12} {'Schedule'}")
    emit("-" * 65)
    for name, defn in TASK_DEFS.items():
        label = f"{LABEL_PREFIX}{defn['label_suffix']}"
        plist_path = PLIST_DIR / f"{label}.plist"
        if defn.get("interval"):
            sched_desc = f"每 {defn['interval']}s"
        elif defn.get("schedule"):
            sched_desc = str(defn["schedule"][:2])
        else:
            sched_desc = "-"
        status = "INSTALLED" if plist_path.exists() else "not installed"
        emit(f"{name:<25} {status:<12} {sched_desc}")

    # Also check launchctl list
    emit()
    result = subprocess.run(["launchctl", "list"],
                            capture_output=True, text=True)
    tielv_jobs = [l for l in result.stdout.split("\n") if LABEL_PREFIX in l]
    if tielv_jobs:
        emit(f"Active launchd jobs ({len(tielv_jobs)}):")
        for job in tielv_jobs:
            emit(f"  {job}")
    else:
        emit("No active tielv launchd jobs")


def list_tasks():
    """Print a formatted list of all defined tasks."""
    emit("铁律量化 launchd 调度任务清单")
    emit(f"{'='*60}")
    for name, defn in TASK_DEFS.items():
        if defn.get("interval"):
            sched = f"每 {defn['interval']} 秒"
        elif defn.get("schedule"):
            scheds = defn["schedule"]
            if not isinstance(scheds, list):
                scheds = [scheds]
            # Generate a compact summary string
            parts_list = []
            for s in scheds:
                p = []
                if "Hour" in s and "Minute" in s:
                    p.append(f"{s['Hour']:02d}:{s['Minute']:02d}")
                elif "Minute" in s and "Hour" not in s:
                    p.append(f":{s['Minute']:02d}")
                if "Weekday" in s:
                    wd_map = {1: "周一", 2: "周二", 3: "周三", 4: "周四", 5: "周五"}
                    p.append(wd_map.get(s["Weekday"], f"周{s['Weekday']}"))
                parts_list.append(" ".join(p))
            # De-duplicate and shorten
            sched = ", ".join(sorted(set(parts_list)))
        else:
            sched = "-"
        cmd_short = " ".join(defn["args"][-2:]) if len(defn["args"]) > 1 else defn["args"][0]
        emit(f"  {name:<20} {sched:<30} {defn['description']}")
    emit()


def main():
    parser = argparse.ArgumentParser(description="铁律量化 macOS launchd 统一调度注册器（唯一入口）")
    parser.add_argument("--list", action="store_true", help="List all defined tasks")
    parser.add_argument("--install", default="", help="Task name to install, or 'all'")
    parser.add_argument("--uninstall", default="", help="Task name to uninstall")
    parser.add_argument("--status", action="store_true", help="Show status of all tasks")
    args = parser.parse_args()

    if args.list:
        list_tasks()
        return

    if args.status:
        show_status()
        return

    if args.install:
        if args.install == "all":
            for name, defn in TASK_DEFS.items():
                emit(f"Installing {name}...")
                install_task(name, defn)
        elif args.install in TASK_DEFS:
            install_task(args.install, TASK_DEFS[args.install])
        else:
            emit(f"ERROR: Unknown task: {args.install}")
            sys.exit(1)

    if args.uninstall:
        if args.uninstall == "all":
            for name, defn in TASK_DEFS.items():
                emit(f"Uninstalling {name}...")
                uninstall_task(name, defn)
        elif args.uninstall in TASK_DEFS:
            uninstall_task(args.uninstall, TASK_DEFS[args.uninstall])
        else:
            emit(f"ERROR: Unknown task: {args.uninstall}")
            sys.exit(1)

    if not args.install and not args.uninstall and not args.status and not args.list:
        parser.print_help()


if __name__ == "__main__":
    main()
