#!/usr/bin/env python3
"""generate_launchd.py — macOS launchd 统一调度注册器（铁律量化唯一入口）

macOS 当前唯一调度注册器。禁止使用 crontab、GitHub Actions schedule、PS1 注册。
所有定时任务通过本脚本注册到 launchd。

真实状态模型: 不再仅凭 plist 文件存在判定 INSTALLED，
而是综合 plist 存在 + launchd 加载状态 -> MISSING / PLIST_ONLY / LOADED / BROKEN。

Usage:
    python3 generate_launchd.py --list                      # list all scheduled tasks
    python3 generate_launchd.py --install all                # install all tasks
    python3 generate_launchd.py --install <task_name>        # install a specific task
    python3 generate_launchd.py --uninstall <task_name>      # uninstall a task
    python3 generate_launchd.py --status                     # show real status of all tasks
    python3 generate_launchd.py --verify <task_name>         # verify task installed & loaded

--verify 退出码:
  0 = plist 存在 + launchd 已加载 + 参数正确
  2 = 任一条件不满足

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


def _expected_args(task_def):
    """Return the full expected ProgramArguments list for a task definition."""
    return [task_def["command"]] + task_def["args"]


def _check_program_arguments_match(plist, task_def):
    """Check if plist ProgramArguments match task definition. Returns (bool, reason)."""
    installed_args = plist.get("ProgramArguments", [])
    expected = _expected_args(task_def)
    installed_str = " ".join(installed_args)
    expected_str = " ".join(expected)
    for exp in expected:
        if exp not in installed_str:
            return False, (
                f"ProgramArguments mismatch\n"
                f"  installed: {installed_str}\n"
                f"  expected:  {expected_str}"
            )
    return True, ""


def _launchctl_print(label):
    """Run launchctl print gui/<uid>/<label> to check if job is loaded.

    Returns (returncode, stdout, stderr).
    launchctl print is more authoritative than launchctl list for confirm loading.
    """
    uid = os.getuid()
    return subprocess.run(
        ["launchctl", "print", f"gui/{uid}/{label}"],
        capture_output=True, text=True
    )


def get_real_status(label, task_name=None):
    """Get real status of a launchd task.

    Uses `launchctl print gui/<uid>/<label>` for loading check — more authoritative
    than `launchctl list <label>`.

    If task_name is provided, validates ProgramArguments against TASK_DEFS.

    Returns one of:
      LOADED     — plist exists, launchd has loaded it, ProgramArguments match
      PLIST_ONLY — plist file exists but launchd has NOT loaded it
      MISSING    — plist file does not exist
      BROKEN     — plist exists but args don't match definition, or plist unparseable
    """
    plist_path = PLIST_DIR / f"{label}.plist"
    if not plist_path.exists():
        return "MISSING"

    # Check if plist is parseable
    try:
        with open(plist_path, "rb") as f:
            plist = plistlib.load(f)
    except Exception:
        return "BROKEN"

    # If task_name provided, validate ProgramArguments
    if task_name is not None and task_name in TASK_DEFS:
        match, _ = _check_program_arguments_match(plist, TASK_DEFS[task_name])
        if not match:
            return "BROKEN"

    # Check if loaded in launchd via launchctl print (gui domain)
    result = _launchctl_print(label)
    if result.returncode == 0:
        return "LOADED"
    return "PLIST_ONLY"


def main_verify(task_name):
    """Verify a task is properly installed, loaded, and has correct arguments.

    Outputs JSON with detailed status fields. Exits 0 on pass, 2 on failure.
    """
    if task_name not in TASK_DEFS:
        emit(json.dumps({
            "task": task_name,
            "error": "unknown_task",
            "status": "UNKNOWN",
            "reason": f"Unknown task: {task_name}",
        }, ensure_ascii=False))
        sys.exit(2)

    defn = TASK_DEFS[task_name]
    label = f"{LABEL_PREFIX}{defn['label_suffix']}"
    plist_path = PLIST_DIR / f"{label}.plist"

    plist_exists = plist_path.exists()
    launchd_loaded = False
    program_arguments_match = False
    status = "MISSING"
    reason = ""

    if not plist_exists:
        status = "MISSING"
        reason = f"plist not found at {plist_path}"
    else:
        # Check ProgramArguments
        try:
            with open(plist_path, "rb") as f:
                plist = plistlib.load(f)
            match, mismatch_reason = _check_program_arguments_match(plist, defn)
            program_arguments_match = match
            if not match:
                status = "BROKEN"
                reason = mismatch_reason
        except Exception as e:
            status = "BROKEN"
            reason = f"plist unparseable: {e}"

        # Check launchd loading (only if plist is structurally valid)
        if not reason:
            result = _launchctl_print(label)
            launchd_loaded = result.returncode == 0
            if launchd_loaded:
                status = "LOADED"
                reason = ""
            else:
                status = "PLIST_ONLY"
                reason = f"plist exists but NOT loaded in launchd"

    output = {
        "task": task_name,
        "label": label,
        "uid": os.getuid(),
        "plist_exists": plist_exists,
        "launchd_loaded": launchd_loaded,
        "program_arguments_match": program_arguments_match,
        "status": status,
        "reason": reason,
    }
    emit(json.dumps(output, ensure_ascii=False, indent=2))

    if status == "LOADED":
        sys.exit(0)
    else:
        sys.exit(2)


def main_repair(task_name):
    """Repair a task by reinstalling plist and loading into launchd.

    After repair, runs verify. If verify still fails, exits 2.
    """
    if task_name not in TASK_DEFS:
        emit(json.dumps({"task": task_name, "error": "unknown_task", "status": "UNKNOWN"}))
        sys.exit(2)

    defn = TASK_DEFS[task_name]
    path = install_task(task_name, defn)

    emit(f"\nVerifying after repair...")
    main_verify(task_name)
    # main_verify exits 0 or 2


def show_status():
    """Display real status (MISSING/PLIST_ONLY/LOADED/BROKEN) of all tasks."""
    emit(f"{'Task':<25} {'Status':<12} {'Schedule'}")
    emit("-" * 65)
    for name, defn in TASK_DEFS.items():
        label = f"{LABEL_PREFIX}{defn['label_suffix']}"
        if defn.get("interval"):
            sched_desc = f"每 {defn['interval']}s"
        elif defn.get("schedule"):
            sched_desc = str(defn["schedule"][:2])
        else:
            sched_desc = "-"
        status = get_real_status(label, task_name=name)
        emit(f"{name:<25} {status:<12} {sched_desc}")

    # Summary: count jobs per status
    emit()
    counts = {"LOADED": 0, "PLIST_ONLY": 0, "MISSING": 0, "BROKEN": 0}
    for name, defn in TASK_DEFS.items():
        label = f"{LABEL_PREFIX}{defn['label_suffix']}"
        s = get_real_status(label, task_name=name)
        counts[s] = counts.get(s, 0) + 1
    emit(f"Total: {sum(counts.values())} | "
         f"LOADED={counts['LOADED']} "
         f"PLIST_ONLY={counts['PLIST_ONLY']} "
         f"MISSING={counts['MISSING']} "
         f"BROKEN={counts['BROKEN']}")


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
    parser.add_argument("--status", action="store_true", help="Show real status of all tasks")
    parser.add_argument("--verify", default="", help="Verify a task is installed & loaded (JSON output, exits 0 or 2)")
    parser.add_argument("--repair", default="", help="Reinstall and verify a task (exits 0 if OK, 2 if repair fails)")
    args = parser.parse_args()

    if args.list:
        list_tasks()
        return

    if args.verify:
        main_verify(args.verify)
        return  # main_verify calls sys.exit internally

    if args.repair:
        main_repair(args.repair)
        return  # main_repair calls sys.exit via main_verify

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

    if not args.install and not args.uninstall and not args.status and not args.list and not args.verify and not args.repair:
        parser.print_help()


if __name__ == "__main__":
    main()
