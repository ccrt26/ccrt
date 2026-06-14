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
  7. generate_launchd.py 不得包含 print('... trigger') 占位任务
  8. generate_launchd.py 不得包含 .ps1、cron_runner.sh、--mode data_only
  9. .github/workflows/sim_trading.yml 不得包含 schedule:
  10. install_crontab.sh 必须是废弃保护脚本，不得包含 crontab "$TMPFILE"
  11. 当前用户 crontab 如可读取，不得包含 /Users/ccrt/ccrt
  12. ~/Library/LaunchAgents/com.tielv.*.plist 中的 tielv 服务必须在 registry 登记

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
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = PROJECT_ROOT / "00_项目地基" / "06_调度与运行" / "runtime_entry_registry.json"
LEGACY_REG_PATH = PROJECT_ROOT / "00_项目地基" / "06_调度与运行" / "win_legacy_migration_register.json"
WORKFLOW_PY = PROJECT_ROOT / "代码文件" / "每日荐股" / "scripts" / "daily_workflow.py"
GENERATE_LAUNCHD_PY = PROJECT_ROOT / "代码文件" / "每日荐股" / "scripts" / "generate_launchd.py"
SIM_TRADING_YML = PROJECT_ROOT / ".github" / "workflows" / "sim_trading.yml"
INSTALL_CRONTAB_SH = PROJECT_ROOT / "代码文件" / "tools" / "install_crontab.sh"
PLIST_DIR = Path.home() / "Library" / "LaunchAgents"
LABEL_PREFIX = "com.tielv."

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

    # ── C1: registry JSON valid ──────────────────────────
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

    # ── C2: legacy registry valid ────────────────────────
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

    # Early return if C1 or C2 failed (registry data needed for later checks)
    if result == "BLOCK":
        return {"result": result, "checks": checks}

    # ── C3: Required entries in registry ─────────────────
    required_entries = [
        "generate_launchd.py", "launchd", "daily_workflow.py",
        "batch_data_collector.py", "daily_orchestrator.py",
        "feishu_bridge.py", "im_consumer.py", "sim_orchestrator.py",
        "scheduler_health_check.py",
        "git_autosweep.py", "pigeon", "daily_signal", "deep_signal", "post_eval",
    ]
    missing = [r for r in required_entries if r not in entry_keys]
    if missing:
        result = "BLOCK"
        checks.append(make_check("C3", "registry_entries", "BLOCK", str(required_entries), f"缺 {missing}", f"registry 缺必需 entry: {missing}"))
    else:
        checks.append(make_check("C3", "registry_entries", "PASS", str(required_entries), str(required_entries), ""))

    # ── C3b: Daily production wrapper authority ────────────
    prod_entry = next((e for e in entries if e.get("entry") == "run_daily_production_pipeline.py"), None)
    wrapper_entry = next((e for e in entries if e.get("entry") == "run_daily_data_pipeline_today.py"), None)
    c3b_errors = []
    if prod_entry is None:
        c3b_errors.append("run_daily_production_pipeline.py missing")
    else:
        if prod_entry.get("authority") != "daily_production_pipeline_entry":
            c3b_errors.append(f"production authority={prod_entry.get('authority')}")
        if prod_entry.get("status") != "active":
            c3b_errors.append(f"production status={prod_entry.get('status')}")
        prod_path = PROJECT_ROOT / prod_entry.get("path", "")
        if not prod_path.exists():
            c3b_errors.append(f"production path missing: {prod_entry.get('path')}")
    if wrapper_entry is None:
        c3b_errors.append("run_daily_data_pipeline_today.py missing")
    else:
        if wrapper_entry.get("status") != "active_wrapper":
            c3b_errors.append(f"wrapper status={wrapper_entry.get('status')}")
        if wrapper_entry.get("delegates_to") != "run_daily_production_pipeline.py":
            c3b_errors.append(f"wrapper delegates_to={wrapper_entry.get('delegates_to')}")
    if c3b_errors:
        result = "BLOCK"
        checks.append(make_check("C3b", "daily_production_authority", "BLOCK",
                                  "production active + wrapper delegates",
                                  "; ".join(c3b_errors),
                                  "日报生产闭环入口权威关系不成立"))
    else:
        checks.append(make_check("C3b", "daily_production_authority", "PASS",
                                  "production active + wrapper delegates",
                                  "ok",
                                  ""))

    # ── C4: Forbidden scheduler scripts marked in registry ──
    c4_blocked = False
    for sched_ps1 in KNOWN_FORBIDDEN_SCHEDULER_PS1:
        ps1_path = PROJECT_ROOT / sched_ps1
        if ps1_path.exists():
            registered = any(e.get("entry") == os.path.basename(sched_ps1) and
                            "forbidden" in e.get("status", "").lower()
                            for e in entries)
            if not registered:
                c4_blocked = True
                result = "BLOCK"
                checks.append(make_check("C4", f"scheduler:{sched_ps1}", "BLOCK",
                                          "registry 标记为 forbidden_current_runtime",
                                          "未在 registry 中注册为 forbidden",
                                          f"{sched_ps1} 存在于现役目录但 registry 未标记为 forbidden"))
    if not c4_blocked:
        checks.append(make_check("C4", "scheduler_ps1", "PASS", "全部标记", "全部标记", ""))

    # ── C4b: Forbidden macOS entries in registry ─────────
    c4b_blocked = False
    macos_forbidden = ["crontab", "install_crontab.sh", "cron_runner.sh", "GitHub Actions schedule: sim_trading.yml"]
    for fb in macos_forbidden:
        registered = any(e.get("entry") == fb and "forbidden" in e.get("status", "").lower() for e in entries)
        if not registered:
            c4b_blocked = True
            result = "BLOCK"
            checks.append(make_check("C4b", f"forbidden:{fb}", "BLOCK",
                                      "registry 标记为 forbidden_current_runtime",
                                      "未标记",
                                      f"registry 中缺少禁止条目: {fb}"))
    if not c4b_blocked:
        checks.append(make_check("C4b", "macos_forbidden", "PASS", "全部标记", "全部标记", ""))

    # ── C5: Forbidden PS1 with Python replacement ────────
    c5_blocked = False
    for f_ps1 in KNOWN_FORBIDDEN_PS1:
        ps1_path = PROJECT_ROOT / f_ps1
        if ps1_path.exists():
            registered = any(e.get("legacy_path") == f_ps1 for e in leg_entries)
            if not registered:
                c5_blocked = True
                result = "BLOCK"
                checks.append(make_check("C5", f"legacy:{f_ps1}", "BLOCK",
                                          "win_legacy_migration_register 已登记",
                                          "未登记",
                                          f"{f_ps1} 存在于现役目录但未在 win_legacy_migration_register 中登记"))
    if not c5_blocked:
        checks.append(make_check("C5", "legacy_ps1", "PASS", "全部登记", "全部登记", ""))

    # ── C6: daily_workflow.py must not allow PS1 fallback ──
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

    # ── C7: generate_launchd.py no print placeholder tasks ──
    if GENERATE_LAUNCHD_PY.exists():
        gl_text = GENERATE_LAUNCHD_PY.read_text(encoding="utf-8", errors="ignore")
        # Check for print('... trigger') pattern in args (placeholder tasks)
        placeholder = re.findall(r'''print\(['"][^'"]*trigger['"]\)''', gl_text)
        if placeholder:
            result = "BLOCK"
            checks.append(make_check("C7", "generate_launchd_placeholder", "BLOCK",
                                      "没有 print('... trigger') 占位任务",
                                      f"发现 {len(placeholder)} 处占位任务",
                                      f"generate_launchd.py 包含 print trigger 占位: {placeholder}"))
        else:
            checks.append(make_check("C7", "generate_launchd_placeholder", "PASS", "无占位任务", "无占位任务", ""))
    else:
        result = "BLOCK"
        checks.append(make_check("C7", "generate_launchd_placeholder", "BLOCK", "文件存在", "缺失", "generate_launchd.py 不存在"))

    # ── C8: generate_launchd.py no .ps1 / cron_runner.sh / data_only ──
    if GENERATE_LAUNCHD_PY.exists():
        gl_text = GENERATE_LAUNCHD_PY.read_text(encoding="utf-8", errors="ignore")
        forbidden_patterns = [r"\.ps1", r"cron_runner\.sh", r"--mode\s+data_only"]
        found_patterns = []
        for pat in forbidden_patterns:
            if re.search(pat, gl_text):
                found_patterns.append(pat)
        if found_patterns:
            result = "BLOCK"
            checks.append(make_check("C8", "generate_launchd_forbidden_refs", "BLOCK",
                                      "不包含 .ps1 / cron_runner.sh / --mode data_only",
                                      f"发现禁止引用: {found_patterns}",
                                      f"generate_launchd.py 包含禁止的调度引用"))
        else:
            checks.append(make_check("C8", "generate_launchd_forbidden_refs", "PASS", "无禁止引用", "无禁止引用", ""))
    else:
        result = "BLOCK"
        checks.append(make_check("C8", "generate_launchd_forbidden_refs", "BLOCK", "文件存在", "缺失", "generate_launchd.py 不存在"))

    # ── C9: sim_trading.yml no schedule ──────────────────
    if SIM_TRADING_YML.exists():
        yml_text = SIM_TRADING_YML.read_text(encoding="utf-8", errors="ignore")
        if re.search(r"^\s+schedule:", yml_text, re.MULTILINE):
            result = "BLOCK"
            checks.append(make_check("C9", "github_actions_schedule", "BLOCK",
                                      "不包含 schedule:",
                                      "包含 schedule:",
                                      ".github/workflows/sim_trading.yml 仍包含定时调度"))
        else:
            checks.append(make_check("C9", "github_actions_schedule", "PASS", "无 schedule", "无 schedule", ""))
    else:
        result = "BLOCK"
        checks.append(make_check("C9", "github_actions_schedule", "BLOCK", "文件存在", "缺失", "sim_trading.yml 不存在"))

    # ── C10: install_crontab.sh must be deprecated guard ──
    if INSTALL_CRONTAB_SH.exists():
        sh_text = INSTALL_CRONTAB_SH.read_text(encoding="utf-8", errors="ignore")
        if "crontab" in sh_text and "$TMPFILE" in sh_text:
            result = "BLOCK"
            checks.append(make_check("C10", "install_crontab_deprecated", "BLOCK",
                                      "废弃保护脚本（不写 crontab）",
                                      "仍包含 crontab $TMPFILE 写入操作",
                                      "install_crontab.sh 仍然写入 crontab，未改为废弃保护"))
        elif "已废弃" in sh_text:
            checks.append(make_check("C10", "install_crontab_deprecated", "PASS", "废弃保护", "已标记废弃", ""))
        else:
            result = "BLOCK"
            checks.append(make_check("C10", "install_crontab_deprecated", "BLOCK",
                                      "废弃保护脚本",
                                      "未标记废弃",
                                      "install_crontab.sh 未标记为废弃"))
    else:
        result = "BLOCK"
        checks.append(make_check("C10", "install_crontab_deprecated", "BLOCK", "文件存在", "缺失", "install_crontab.sh 不存在"))

    # ── C11: crontab must not contain /Users/ccrt/ccrt ────
    try:
        crontab_proc = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=10)
        if crontab_proc.returncode == 0:
            crontab_text = crontab_proc.stdout
            if "/Users/ccrt/ccrt" in crontab_text:
                result = "BLOCK"
                checks.append(make_check("C11", "crontab_tielv_tasks", "BLOCK",
                                          "crontab 不含 /Users/ccrt/ccrt",
                                          "发现 /Users/ccrt/ccrt 条目",
                                          "crontab 中仍存在铁律量化任务"))
            else:
                checks.append(make_check("C11", "crontab_tielv_tasks", "PASS", "无铁律量化任务", "无铁律量化任务", ""))
        else:
            # No crontab = clean
            checks.append(make_check("C11", "crontab_tielv_tasks", "PASS", "crontab 不可读或空", "空", ""))
    except Exception as e:
        checks.append(make_check("C11", "crontab_tielv_tasks", "PASS", "crontab 不可读", str(e), ""))

    # ── C12: launchd plist services must be in allowed whitelist ──
    ALLOWED_PLIST_LABELS = {
        "com.tielv.git-autosweep",
        "com.tielv.pigeon",
        "com.tielv.daily-signal",
        "com.tielv.deep-signal",
        "com.tielv.post-eval",
        "com.tielv.scheduler-health",
        "com.tielv.sim-trading",
        "com.tielv.feishu-bridge",
        "com.tielv.im-consumer",
    }
    if PLIST_DIR.exists():
        plist_files = list(PLIST_DIR.glob(f"{LABEL_PREFIX}*.plist"))
        unregistered = []
        for plist_path in plist_files:
            label = plist_path.stem  # e.g., com.tielv.git-autosweep
            # Strict whitelist check — no empty string suffix matching
            if label not in ALLOWED_PLIST_LABELS:
                unregistered.append(label)
                continue
            # Also verify that the label corresponds to a registry entry
            suffix = label.replace(LABEL_PREFIX, "", 1)  # e.g., git-autosweep
            registered = any(
                e.get("label_suffix") == suffix
                for e in entries
            )
            if not registered:
                unregistered.append(label)
        if unregistered:
            result = "BLOCK"
            checks.append(make_check("C12", "launchd_registration", "BLOCK",
                                      f"所有 com.tielv.* plist 必须在允许白名单中且在 registry 登记",
                                      f"未通过: {unregistered}",
                                      f"以下 launchd plist 不在白名单或未在 registry 中登记: {unregistered}"))
        else:
            checks.append(make_check("C12", "launchd_registration", "PASS", f"全部 {len(plist_files)} 个已登记", f"全部已登记", ""))
    else:
        checks.append(make_check("C12", "launchd_registration", "PASS", "无 launchd plist", "无 plist 目录", ""))

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
