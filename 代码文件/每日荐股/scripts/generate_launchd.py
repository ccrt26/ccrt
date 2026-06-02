#!/usr/bin/env python3
"""generate_launchd.py — Generate macOS launchd plist for scheduled tasks.

Replaces Windows Task Scheduler registration scripts (register_tasks.ps1, setup_scheduler.ps1).
Generates ~/Library/LaunchAgents/*.plist files for each scheduled task.

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

# ── Task definitions ──────────────────────────────────
# Maps scheduled_tasks.json cron entries to launchd-compatible configs
TASK_DEFS = {
    "daily_brief": {
        "label_suffix": "daily-brief",
        "description": "每日重点股票操作简报 (Mon-Fri 15:37)",
        "cron_hint": "37 15 * * 1-5",
        "command": "python3",
        "args": ["-c", "print('daily brief trigger')"],
        "run_at_load": False,
    },
    "weekly_deep": {
        "label_suffix": "weekly-deep",
        "description": "周度深度分析 (Fri 20:30)",
        "cron_hint": "30 20 * * 5",
        "command": "python3",
        "args": ["-c", "print('weekly deep analysis trigger')"],
        "run_at_load": False,
    },
    "weekly_inspect": {
        "label_suffix": "weekly-inspect",
        "description": "玉夜每周数据巡检 (Mon 09:17)",
        "cron_hint": "17 9 * * 1",
        "command": "python3",
        "args": [str(Path(__file__).resolve().parent.parent.parent / "代码文件" / "数据" / "inspect_data_health.py")],
        "run_at_load": False,
    },
    "git_autosweep": {
        "label_suffix": "git-autosweep",
        "description": "自动Git同步清扫 (hourly at :07)",
        "cron_hint": "7 * * * *",
        "command": "python3",
        "args": [str(Path(__file__).resolve().parent.parent.parent / "代码文件" / "tools" / "git_autosweep.py")],
        "run_at_load": True,
    },
}


def cron_to_launchd(cron_expr):
    """Convert a 5-field cron expression to launchd StartCalendarInterval dict.

    Returns a list of dicts with optional Minute, Hour, Day, Weekday, Month keys.
    For complex expressions (e.g., '*/5'), a simplified approach is used.
    """
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        return None

    minute, hour, dom, month, dow = parts

    interval = {}
    if minute != "*":
        interval["Minute"] = int(minute) if minute.isdigit() else None
    if hour != "*":
        interval["Hour"] = int(hour) if hour.isdigit() else None
    if dom != "*":
        interval["Day"] = int(dom) if dom.isdigit() else None
    if month != "*":
        interval["Month"] = int(month) if month.isdigit() else None
    if dow != "*":
        if "-" in dow:
            # e.g., "1-5" -> weekday array
            pass
        elif "," in dow:
            pass
        else:
            interval["Weekday"] = int(dow) if dow.isdigit() else None

    # For weekday ranges, handle separately
    if dow != "*" and "-" not in dow and "," not in dow:
        interval["Weekday"] = int(dow)
    elif dow == "*":
        pass

    # Clean None values
    interval = {k: v for k, v in interval.items() if v is not None}
    return interval if interval else None


def generate_plist(task_name, task_def, project_root):
    """Generate a launchd plist dict for a task."""
    label = f"{LABEL_PREFIX}{task_def['label_suffix']}"
    calendar = cron_to_launchd(task_def["cron_hint"])

    plist = {
        "Label": label,
        "ProgramArguments": [task_def["command"]] + task_def["args"],
        "WorkingDirectory": project_root,
        "RunAtLoad": task_def.get("run_at_load", False),
        "StandardOutPath": str(Path(project_root) / "代码文件" / "数据" / "logs" / f"{task_def['label_suffix']}.stdout.log"),
        "StandardErrorPath": str(Path(project_root) / "代码文件" / "数据" / "logs" / f"{task_def['label_suffix']}.stderr.log"),
    }

    if calendar:
        plist["StartCalendarInterval"] = calendar

    return plist


def install_task(task_name, task_def, project_root):
    """Write plist file and load into launchd."""
    PLIST_DIR.mkdir(parents=True, exist_ok=True)
    label = f"{LABEL_PREFIX}{task_def['label_suffix']}"
    plist_path = PLIST_DIR / f"{label}.plist"

    plist = generate_plist(task_name, task_def, project_root)
    with open(plist_path, "wb") as f:
        plistlib.dump(plist, f)

    # Unload first if exists, then load
    subprocess.run(["launchctl", "unload", str(plist_path)],
                   capture_output=True)
    result = subprocess.run(["launchctl", "load", str(plist_path)],
                            capture_output=True, text=True)
    if result.returncode == 0:
        print(f"  OK: {label} installed and loaded")
    else:
        print(f"  WARN: {label} plist written but load failed: {result.stderr.strip()}")
    return plist_path


def uninstall_task(task_name, task_def):
    """Unload and remove plist file."""
    label = f"{LABEL_PREFIX}{task_def['label_suffix']}"
    plist_path = PLIST_DIR / f"{label}.plist"

    if plist_path.exists():
        subprocess.run(["launchctl", "unload", str(plist_path)],
                       capture_output=True)
        plist_path.unlink()
        print(f"  OK: {label} uninstalled")
    else:
        print(f"  SKIP: {label} not installed")


def show_status():
    """Display status of all defined tasks."""
    print(f"{'Task':<25} {'Status':<12} {'Schedule'}")
    print("-" * 65)
    for name, defn in TASK_DEFS.items():
        label = f"{LABEL_PREFIX}{defn['label_suffix']}"
        plist_path = PLIST_DIR / f"{label}.plist"
        status = "INSTALLED" if plist_path.exists() else "not installed"
        print(f"{name:<25} {status:<12} {defn['cron_hint']}")

    # Also check launchctl list
    print()
    result = subprocess.run(["launchctl", "list"],
                            capture_output=True, text=True)
    tielv_jobs = [l for l in result.stdout.split("\n") if LABEL_PREFIX in l]
    if tielv_jobs:
        print(f"Active launchd jobs ({len(tielv_jobs)}):")
        for job in tielv_jobs:
            print(f"  {job}")
    else:
        print("No active tielv launchd jobs")


def main():
    parser = argparse.ArgumentParser(description="Manage macOS launchd scheduled tasks")
    parser.add_argument("--list", action="store_true", help="List all defined tasks")
    parser.add_argument("--install", default="", help="Task name to install, or 'all'")
    parser.add_argument("--uninstall", default="", help="Task name to uninstall")
    parser.add_argument("--status", action="store_true", help="Show status of all tasks")
    parser.add_argument("--root", default="", help="Project root path")
    args = parser.parse_args()

    project_root = args.root or str(Path(__file__).resolve().parent.parent.parent)

    if args.list or (not args.install and not args.uninstall and not args.status):
        print("Defined tasks:")
        for name, defn in TASK_DEFS.items():
            print(f"  {name}: {defn['description']} ({defn['cron_hint']})")
        return

    if args.status:
        show_status()
        return

    if args.install:
        if args.install == "all":
            for name, defn in TASK_DEFS.items():
                print(f"Installing {name}...")
                install_task(name, defn, project_root)
        elif args.install in TASK_DEFS:
            install_task(args.install, TASK_DEFS[args.install], project_root)
        else:
            print(f"ERROR: Unknown task: {args.install}")
            sys.exit(1)

    if args.uninstall:
        if args.uninstall in TASK_DEFS:
            uninstall_task(args.uninstall, TASK_DEFS[args.uninstall])
        else:
            print(f"ERROR: Unknown task: {args.uninstall}")
            sys.exit(1)


if __name__ == "__main__":
    main()
