#!/usr/bin/env python3
"""
第5.5-C: 运行时入口权威检查闸门

检查:
  1. runtime_entry_registry.json 合法且包含必需 entries
  2. win_legacy_migration_register.json 合法且包含必需 mappings
  3. daily_workflow.py 中 collector_ps 是否已阻断 (PS1→Python deferred → BLOCK)
  4. 现役目录中 E 级 PS1 (有Python替代) 是否被 registry 登记
  5. Windows Task Scheduler 注册脚本是否被标记 forbidden_current_runtime
  6. 不扫描 _win32_legacy/

用法:
  python3 scripts/check_runtime_entry_authority.py --all
  python3 scripts/check_runtime_entry_authority.py --all --json

退出码:
  0 = PASS
  1 = 脚本异常
  2 = 任一 BLOCK
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = PROJECT_ROOT / "00_项目地基" / "06_调度与运行" / "runtime_entry_registry.json"
LEGACY_REG_PATH = PROJECT_ROOT / "00_项目地基" / "06_调度与运行" / "win_legacy_migration_register.json"
WORKFLOW_PY = PROJECT_ROOT / "代码文件" / "每日荐股" / "scripts" / "daily_workflow.py"

# Known PS1 files with Python replacements (active dirs)
KNOWN_FORBIDDEN_PS1 = [
    "代码文件/每日荐股/scripts/daily_workflow.ps1",
    "代码文件/每日荐股/scripts/batch_data_collector.ps1",
    "代码文件/信鸽信息采集/pigeon_collector.ps1",
    "代码文件/监督机制/pipeline_engine.ps1",
    "代码文件/监督机制/run_full_audit.ps1",
]
KNOWN_FORBIDDEN_SCHEDULER_PS1 = [
    "代码文件/每日荐股/scripts/register_tasks.ps1",
    "代码文件/每日荐股/scripts/setup_scheduler.ps1",
    "代码文件/信鸽信息采集/register_pigeon_scheduler.ps1",
]


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def make_check(check_id, field, status, expected, actual, message):
    return {"check_id": check_id, "field": field, "status": status,
            "expected": expected, "actual": actual, "message": message}


def check_all():
    checks = []
    result = "PASS"

    # C1: registry JSON valid
    c1_pass = True
    if not REGISTRY_PATH.exists():
        c1_pass = False
        checks.append(make_check("C1", "registry", "BLOCK", "文件存在", "缺失", "runtime_entry_registry.json 不存在"))
    else:
        try:
            reg = load_json(REGISTRY_PATH)
            entries = reg.get("entries", [])
            entry_keys = [e.get("entry") for e in entries]
            checks.append(make_check("C1", "registry", "PASS", "合法JSON", f"{len(entries)} entries", ""))
        except Exception as e:
            c1_pass = False
            checks.append(make_check("C1", "registry", "BLOCK", "合法JSON", str(e), "runtime_entry_registry.json 解析失败"))
    if not c1_pass:
        result = "BLOCK"

    # C2: legacy registry valid
    c2_pass = True
    if not LEGACY_REG_PATH.exists():
        c2_pass = False
        checks.append(make_check("C2", "legacy_registry", "BLOCK", "文件存在", "缺失", "win_legacy_migration_register.json 不存在"))
    else:
        try:
            leg = load_json(LEGACY_REG_PATH)
            leg_entries = leg.get("entries", [])
            checks.append(make_check("C2", "legacy_registry", "PASS", "合法JSON", f"{len(leg_entries)} entries", ""))
        except Exception as e:
            c2_pass = False
            checks.append(make_check("C2", "legacy_registry", "BLOCK", "合法JSON", str(e), "win_legacy_migration_register.json 解析失败"))
    if not c2_pass:
        result = "BLOCK"

    # Early return if C1 or C2 failed
    if result == "BLOCK":
        return {"result": result, "checks": checks}

    # C3: Required entries in registry
    required_entries = ["generate_launchd.py", "launchd", "daily_workflow.py", "batch_data_collector.py", "daily_orchestrator.py"]
    missing = [r for r in required_entries if r not in entry_keys]
    if missing:
        result = "BLOCK"
        checks.append(make_check("C3", "registry_entries", "BLOCK", str(required_entries), f"缺 {missing}", f"registry 缺必需 entry: {missing}"))
    else:
        checks.append(make_check("C3", "registry_entries", "PASS", str(required_entries), str(required_entries), ""))

    # C4: Forbidden scheduler scripts marked in registry
    for sched_ps1 in KNOWN_FORBIDDEN_SCHEDULER_PS1:
        path_s = sched_ps1.replace("代码文件/", "")
        ps1_path = PROJECT_ROOT / sched_ps1
        if ps1_path.exists():
            registered = any(e.get("entry") == os.path.basename(sched_ps1) and
                            "forbidden" in e.get("status", "").lower()
                            for e in entries)
            if not registered:
                result = "BLOCK"
                checks.append(make_check("C4", f"scheduler:{sched_ps1}", "BLOCK",
                                          "registry 标记为 forbidden_current_runtime",
                                          "未在 registry 中注册为 forbidden",
                                          f"{sched_ps1} 存在于现役目录但 registry 未标记为 forbidden"))
    if not any(c["check_id"] == "C4" and c["status"] == "BLOCK" for c in checks):
        checks.append(make_check("C4", "scheduler_ps1", "PASS", "全部标记", "全部标记", ""))

    # C5: Forbidden PS1 with Python replacement
    for f_ps1 in KNOWN_FORBIDDEN_PS1:
        ps1_path = PROJECT_ROOT / f_ps1
        if ps1_path.exists():
            registered = any(e.get("legacy_path") == f_ps1 for e in leg_entries)
            if not registered:
                result = "BLOCK"
                checks.append(make_check("C5", f"legacy:{f_ps1}", "BLOCK",
                                          "win_legacy_migration_register 已登记",
                                          "未登记",
                                          f"{f_ps1} 存在于现役目录但未在 win_legacy_migration_register 中登记"))

    if not any(c["check_id"] == "C5" and c["status"] == "BLOCK" for c in checks):
        checks.append(make_check("C5", "legacy_ps1", "PASS", "全部登记", "全部登记", ""))

    # C6: daily_workflow.py must not allow PS1 fallback
    if WORKFLOW_PY.exists():
        wf_text = WORKFLOW_PY.read_text(encoding="utf-8", errors="ignore")
        if "PS1→Python deferred" in wf_text:
            result = "BLOCK"
            checks.append(make_check("C6", "collector_ps_fallback", "BLOCK",
                                      "PS1 fallback 已被阻止",
                                      "仍存在 PS1→Python deferred",
                                      "daily_workflow.py 中仍包含 PS1 fallback 路径"))
        elif "sys.exit(1)" in wf_text and "collector_ps" in wf_text:
            checks.append(make_check("C6", "collector_ps_fallback", "PASS", "已阻断", "sys.exit(1)", ""))
        else:
            result = "BLOCK"
            checks.append(make_check("C6", "collector_ps_fallback", "BLOCK",
                                      "collector_ps 已被阻断", "未确认阻断",
                                      "daily_workflow.py 中 collector_ps 阻断状态无法确定"))
    else:
        result = "BLOCK"
        checks.append(make_check("C6", "collector_ps_fallback", "BLOCK", "文件存在", "缺失", "daily_workflow.py 不存在"))

    return {"result": result, "checks": checks}


def format_text(res):
    lines = []
    lines.append(f"{'='*60}")
    lines.append(f" 运行时入口权威检查")
    lines.append(f"{'='*60}")
    lines.append(f"  总结果: {res['result']}")
    lines.append("")
    for chk in res.get("checks", []):
        icon = {"PASS": "✅", "BLOCK": "❌"}.get(chk["status"], "❓")
        lines.append(f"  {icon} {chk['check_id']} {chk['field']}: {chk['status']}")
        if chk.get("message"):
            lines.append(f"     消息: {chk['message']}")
    pass_c = sum(1 for c in res["checks"] if c["status"] == "PASS")
    block_c = sum(1 for c in res["checks"] if c["status"] == "BLOCK")
    lines.append(f"\n  明细: ✅PASS={pass_c} ❌BLOCK={block_c} / TOTAL={len(res['checks'])}")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="第5.5-C: 运行时入口权威检查闸门")
    parser.add_argument("--all", action="store_true", help="全量检查")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    if not args.all:
        parser.error("需要 --all")

    res = check_all()

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(format_text(res))

    return 0 if res["result"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
