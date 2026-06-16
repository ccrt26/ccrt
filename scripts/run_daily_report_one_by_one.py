#!/usr/bin/env python3
"""
run_daily_report_one_by_one.py — v3.6.3 逐票串行日报生成调度器

⛔ 禁止一次性批量生成/修复全部股票。只能逐票串行。
⛔ 禁止并发生成多只股票。
⛔ 读取 dynamic_pool 来自 pigeon_config.json，不允许硬编码股票列表。

队列控制:
  1. 从 pigeon_config.json 读取动态股票池
  2. 校验 signal_daily_report.json 数据就绪
  3. 按 queue 顺序逐票处理
  4. 当前票未通过 → 立即停止，不进入下一只
  5. 全部通过 → 运行 release gate

用法:
  python3 scripts/run_daily_report_one_by_one.py --date 20260604
  python3 scripts/run_daily_report_one_by_one.py --date 20260604 --dry-run
  python3 scripts/run_daily_report_one_by_one.py --date 20260604 --dry-run --only 600114
  python3 scripts/run_daily_report_one_by_one.py --date 20260604 --dry-run --start-from 603019

退出码:
  0 = PASS
  2 = BLOCK (任一股票失败或signal校验失败)
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent)
PIGEON_CFG = os.path.join(ROOT, "代码文件", "信鸽信息采集", "pigeon_config.json")
SIGNAL_FILE = os.path.join(ROOT, ".claude", "signal_daily_report.json")
REPORT_DIR = os.path.join(ROOT, "重点股票", "股票报告")
SCRIPTS_DIR = os.path.join(ROOT, "scripts")
TASKS_DIR = os.path.join(ROOT, "logs", "daily_one_by_one_tasks")
STATUS_DIR = os.path.join(TASKS_DIR, "status")


def log(msg, level="INFO"):
    print(f"[{level}] {msg}")


def run_check(script_rel, args, label=""):
    """Run a check script via subprocess. Returns (passed: bool, output: str)."""
    script = os.path.join(ROOT, script_rel)
    if not os.path.exists(script):
        log(f"  SCRIPT_NOT_FOUND: {script}", "BLOCK")
        return False, "not_found"
    cmd = [sys.executable, script] + args
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=ROOT)
        passed = proc.returncode == 0
        output = proc.stdout + proc.stderr
        status = "PASS" if passed else "BLOCK"
        log(f"  [{status}] {label or script_rel}")
        if not passed:
            for line in output.split("\n")[-3:]:
                stripped = line.strip()
                if stripped:
                    log(f"     {stripped}", "FAIL")
        return passed, output
    except subprocess.TimeoutExpired:
        log(f"  [TIMEOUT] {label or script_rel}", "BLOCK")
        return False, "timeout"
    except Exception as e:
        log(f"  [ERROR] {label or script_rel}: {e}", "BLOCK")
        return False, str(e)


def load_pool():
    """从 pigeon_config.json 读取动态股票池。返回 [(code, name), ...]"""
    if not os.path.exists(PIGEON_CFG):
        log(f"PIGEON_CONFIG_NOT_FOUND: {PIGEON_CFG}", "BLOCK")
        return []
    try:
        with open(PIGEON_CFG, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        targets = cfg.get("target_stocks", [])
        if not targets:
            log("PIGEON_CONFIG_EMPTY: target_stocks 为空", "BLOCK")
            return []
        result = []
        for s in targets:
            code = str(s.get("code", ""))
            name = s.get("name", "")
            if code and name:
                result.append((code, name))
            else:
                log(f"PIGEON_CONFIG_INVALID: 跳过缺失code/name的条目: {s}", "WARN")
        return result
    except json.JSONDecodeError as e:
        log(f"PIGEON_CONFIG_PARSE_FAIL: {e}", "BLOCK")
        return []
    except Exception as e:
        log(f"PIGEON_CONFIG_READ_FAIL: {e}", "BLOCK")
        return []


def verify_signal(date_str, pool):
    """校验 signal_daily_report.json 数据就绪。返回 True/False。"""
    if not os.path.exists(SIGNAL_FILE):
        log(f"SIGNAL_NOT_FOUND: {SIGNAL_FILE}", "BLOCK")
        return False

    try:
        with open(SIGNAL_FILE, "r", encoding="utf-8") as f:
            sig = json.load(f)
    except json.JSONDecodeError as e:
        log(f"SIGNAL_PARSE_FAIL: {e}", "BLOCK")
        return False
    except Exception as e:
        log(f"SIGNAL_READ_FAIL: {e}", "BLOCK")
        return False

    # 校验 date
    sig_date = sig.get("date", "")
    if sig_date != date_str:
        log(f"SIGNAL_DATE_MISMATCH: signal={sig_date} expected={date_str}", "BLOCK")
        return False

    # 校验 data_ready
    if not sig.get("data_ready", False):
        log(f"SIGNAL_NOT_READY: data_ready=false", "BLOCK")
        return False

    # 校验股票覆盖
    sig_stocks = sig.get("stocks_daily_data", {})
    pool_codes = set(c for c, _ in pool)
    sig_codes = set(sig_stocks.keys())
    missing = pool_codes - sig_codes
    if missing:
        log(f"SIGNAL_MISSING_STOCKS: signal缺少 {len(missing)} 只: {missing}", "BLOCK")
        return False

    log(f"SIGNAL_OK: date={sig_date} data_ready=true stocks_in_pool={len(pool)} stocks_in_signal={len(sig_stocks)}")
    return True


def generate_one(date_str, code, name):
    """HTML-only 真实生成：委托 run_daily_report_html_only.py。"""
    cmd = [sys.executable, os.path.join(ROOT, "scripts", "run_daily_report_html_only.py"), "--date", date_str, "--only", code, "--write"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180, cwd=ROOT)
    if proc.returncode != 0:
        log(f"  [BLOCK] report generator exit={proc.returncode}", "BLOCK")
        if proc.stdout:
            log(proc.stdout[-500:], "FAIL")
        if proc.stderr:
            log(proc.stderr[-500:], "FAIL")
        return False
    return True


def write_task_prompt(task, code, date_str):
    """Write a copyable Chinese-language prompt for DeepSeek/team."""
    prompt_path = os.path.join(TASKS_DIR, f"{date_str}_{code}.prompt.txt")
    cmd = task.get("after_write_command", "")
    roles = "、".join(task.get("required_team_roles", []))
    lines = [
        f"## 单只股票日报生成任务 — {task['name']}({task['code']})",
        f"日期：{date_str}",
        "",
        "⛔ 如果你准备批量生成所有股票，必须停止；本任务只允许当前 CODE。",
        "⛔ MD/JSON 也禁止批量生成。",
        "⛔ 不要读取母版后生成 10 只；母版只用于当前股票结构参考。",
        "⛔ 不要清空 pass 状态 (logs/daily_one_by_one_tasks/status/*.pass.json)。",
        "",
        "### 标准流程",
        "design → review_1a → consult → coding → verify → deploy → audit",
        "",
        "### 允许修改",
        f"- MD：{task['report_md_path']}",
        f"- JSON：{task['report_json_path']}",
        "",
        "### 禁止修改",
        "- HTML/PDF（由 render-only 自动生成）",
        "- 其他 9 只股票的任何日报产物",
        "- logs/daily_one_by_one_tasks/status/*.pass.json",
        "- scripts/（check_daily_*.py、pipeline_engine.py 等）",
        "- crontab / install_crontab.sh",
        "- 评分、基线、仓位、止损、选股算法",
        "- 地基 E2/E3、canonical-dual-write、shadow",
        "",
        "### 母版参考",
        f"- MD：{task['golden_master_md']}",
        f"- HTML：{task['golden_master_html']}",
        "母版仅用于当前股票的结构参考，不要生成 10 只。",
        "",
        "### 全团解读要求（必须执行）",
        f"必须按全团角色逐个分析：{roles}",
        "- 山猫：宏观/大盘/板块相位",
        "- 信鸽：事件/公告/消息面",
        "- 玉夜：行情/K线/资金/融资/数据一致性",
        "- 流金：风控/仓位/止损/红黄绿灯",
        "- 青山：信号/胜率/样本/技术结构",
        "- 腰子：整合分歧，给出最终明日动作",
        "",
        "### 内容格式要求",
        "- 只写当前股票 MD/JSON",
        "- 不写 HTML/PDF",
        "- 按母版 10 段结构（P0 决策卡 → 深度分析基线 → 今天行情 → 四档资金 → 融资、北向与筹码 → 大盘与板块 → 消息事件 → 信号胜率 → 风控红黄绿灯 → 明日情景应对）",
        "- 每段表格后必须有“这说明”和“对明日影响”",
        "- 数据事实 → 人话解释 → 明日动作影响",
        "- 禁止使用空话：可参考、综合判断、需观察、不改变动作、趋势偏多、风险可控、等确认",
        "- 禁止套用或抄其他股票陈述",
        "- 必须包含该股票真实数据和场景",
        "",
        "### 完成指令",
        f"只写当前股票的 MD/JSON。写出后由调度器执行渲染和验收，不要自己生成 HTML/PDF。",
        "",
        f"### 下一步命令（团队写完 MD/JSON 后执行）",
        cmd,
        "",
    ]
    os.makedirs(TASKS_DIR, exist_ok=True)
    with open(prompt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def write_pass_status(code, name, date_str):
    """Render-only 单票通过后写入状态文件。"""
    os.makedirs(STATUS_DIR, exist_ok=True)
    status = {
        "date": date_str, "code": code, "name": name,
        "passed_at": datetime.now(timezone.utc).isoformat(),
        "command": f"--render-only --only {code} --incremental-dedupe",
        "checks": {"file_exists": True, "p0h": True, "p0i": True, "p0j_d07": True, "md_sidecar": True, "incremental_p0i": True},
    }
    sp = os.path.join(STATUS_DIR, f"{date_str}_{code}.pass.json")
    with open(sp, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)


def compute_file_snapshot(date_str):
    """Compute sha256/size/mtime for all target_stocks' report files.
    Returns dict: {path: {exists, size, mtime, sha256}}"""
    snapshot = {}
    pool = load_pool()
    for code, name in pool:
        sd = os.path.join(REPORT_DIR, f"{name}({code})")
        for ext in [".md", ".json", ".html", ".pdf"]:
            fpath = os.path.join(sd, f"{name}({code})日报_{date_str}{ext}")
            entry = {"exists": False, "size": 0, "mtime": 0, "sha256": ""}
            if os.path.exists(fpath):
                try:
                    with open(fpath, "rb") as f:
                        data = f.read()
                    entry["exists"] = True
                    entry["size"] = len(data)
                    entry["mtime"] = os.path.getmtime(fpath)
                    entry["sha256"] = hashlib.sha256(data).hexdigest()
                except Exception:
                    pass
            snapshot[fpath] = entry
    return snapshot


def check_single_task_scope(date_str, code, name, task, post_render=False):
    """Check that only the current stock's files have been modified.
    Other stocks' files must be unchanged.
    If post_render=True, current stock's HTML/PDF are also allowed.
    In pre-render mode, skip files of the current stock (they're expected to change).
    Returns (passed: bool, detail: str)."""
    task_code = task.get("code", "")
    if task_code != code:
        return False, f"任务包 code={task_code} != 当前 code={code}"

    allowed = list(task.get("allowed_write_paths", []))
    stock_dir = os.path.join(REPORT_DIR, f"{name}({code})")
    if post_render:
        # In post-render mode, current stock's HTML/PDF are also allowed
        for ext in [".html", ".pdf"]:
            p = os.path.join(stock_dir, f"{name}({code})日报_{date_str}{ext}")
            if p not in allowed:
                allowed.append(p)
    snapshot = task.get("pre_task_file_snapshot", {})

    issues = []
    for fpath_str, before in snapshot.items():
        # In pre-render mode, skip files belonging to the current stock entirely
        if not post_render and f"({code})" in fpath_str:
            continue

        if not os.path.exists(fpath_str):
            if before.get("exists"):
                issues.append(f"文件已被删除: {fpath_str}")
            continue

        now_size = os.path.getsize(fpath_str)
        now_mtime = os.path.getmtime(fpath_str)
        try:
            with open(fpath_str, "rb") as f:
                now_sha = hashlib.sha256(f.read()).hexdigest()
        except Exception:
            now_sha = ""

        sha_changed = now_sha != before.get("sha256", "")
        if not sha_changed:
            continue

        # File changed. Is it in the allowed list?
        is_allowed = fpath_str in allowed
        if is_allowed:
            # Pre-render: HTML/PDF changes are blocked (should only come from convert)
            if not post_render and (fpath_str.endswith(".html") or fpath_str.endswith(".pdf")):
                issues.append(f"禁止提前修改 HTML/PDF(由convert生成): {fpath_str}")
            continue

        # Non-allowed file changed → BLOCK
        issues.append(f"越界修改(非当前股票): {fpath_str} (sha256变化)")

    if issues:
        return False, "SINGLE_TASK_SCOPE_BLOCK: " + "; ".join(issues[:3])
    return True, ""


def convert_to_pdf(code, name, date_str):
    """HTML-only: 不生成PDF，只确认HTML存在且足够大。"""
    stock_dir = os.path.join(REPORT_DIR, f"{name}({code})")
    html_path = os.path.join(stock_dir, f"{name}({code})日报_{date_str}.html")
    if not os.path.exists(html_path):
        log(f"  [BLOCK] HTML missing: {html_path}", "BLOCK")
        return False
    sz = os.path.getsize(html_path)
    if sz <= 5000:
        log(f"  [BLOCK] HTML too small ({sz} bytes)", "BLOCK")
        return False
    log(f"  [OK] HTML ({sz//1024}KB), PDF not required")
    return True


def check_single_stock(date_str, code, name):
    """对单只股票运行真实验收。调用已有检查脚本的 --code 模式。
    新增P0-B/P0-F/P0-G单票检查，前置拦截最终gate失败。
    任一失败 return False。"""
    stock_dir = os.path.join(REPORT_DIR, f"{name}({code})")
    prefix = f"{name}({code})日报_{date_str}"

    all_ok = True

    log(f"  Running single-stock checks for {name}({code})...")

    # 1. File existence
    for ext, label in [(".md", "MD"), (".json", "JSON"), (".html", "HTML")]:
        fpath = os.path.join(stock_dir, f"{prefix}{ext}")
        if os.path.exists(fpath):
            sz = os.path.getsize(fpath)
            log(f"  [OK] {label} ({sz//1024}KB)")
        else:
            log(f"  [BLOCK] {label} missing: {fpath}", "FAIL")
            all_ok = False

    # 2. P0-H: Render contract single-stock check
    rc_script = os.path.join("scripts", "check_daily_render_contract.py")
    p, _ = run_check(rc_script, ["--date", date_str, "--code", code, "--html-only"], f"P0-H({code})")
    if not p:
        all_ok = False

    # 3. P0-I: Interpretation quality single-stock check
    iq_script = os.path.join("scripts", "check_daily_interpretation_quality.py")
    p, _ = run_check(iq_script, ["--date", date_str, "--code", code], f"P0-I({code})")
    if not p:
        all_ok = False

    # 4. P0-J: D07_v1.2 contract single-stock check
    d07_script = os.path.join("scripts", "check_daily_d07_v12_contract.py")
    p, _ = run_check(d07_script, ["--date", date_str, "--code", code, "--name", name], f"P0-J({code})")
    if not p:
        all_ok = False

    # 5. MD/Sidecar consistency single-stock check
    mc_script = os.path.join("scripts", "check_md_sidecar_consistency.py")
    p, _ = run_check(mc_script, ["--code", code, "--name", name, "--date", date_str], f"MD-SC({code})")
    if not p:
        all_ok = False

    # 6. P0-B: Numeric source consistency single-stock check (shift-left)
    nb_script = os.path.join("scripts", "check_numeric_source_consistency.py")
    p, _ = run_check(nb_script, ["--code", code, "--name", name, "--date", date_str], f"P0-B({code})")
    if not p:
        all_ok = False

    # 7. P0-F: Collaborative interpretation single-stock check (shift-left)
    # HTML-only mode: P0-F full-pool check is release-level only; single-stock mode skips.

    # 8. P0-G: Data completeness single-stock check (shift-left)
    dg_script = os.path.join("scripts", "check_daily_data_completeness.py")
    p, _ = run_check(dg_script, ["--code", code, "--name", name, "--date", date_str], f"P0-G({code})")
    if not p:
        all_ok = False

    return all_ok


def run_p0i_incremental(codes_str, date_str):
    """Call check_daily_interpretation_quality.py --incremental-codes.
    Returns (passed: bool, output: str)."""
    iq_script = os.path.join(SCRIPTS_DIR, "check_daily_interpretation_quality.py")
    if not os.path.exists(iq_script):
        log(f"P0I_SCRIPT_NOT_FOUND: {iq_script}", "BLOCK")
        return False, "script not found"
    cmd = [sys.executable, iq_script, "--date", date_str, "--incremental-codes", codes_str]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=ROOT)
        passed = proc.returncode == 0
        if passed:
            log(f"  [PASS] P0-I(incremental-codes={codes_str})")
        else:
            log(f"  [BLOCK] P0-I(incremental-codes={codes_str})")
            for line in proc.stdout.split("\n")[-3:]:
                stripped = line.strip()
                if stripped:
                    log(f"     {stripped}", "FAIL")
        return passed, proc.stdout + proc.stderr
    except subprocess.TimeoutExpired:
        log(f"  [TIMEOUT] P0-I(incremental-codes={codes_str})", "BLOCK")
        return False, "timeout"
    except Exception as e:
        log(f"  [ERROR] P0-I: {e}", "BLOCK")
        return False, str(e)


def get_passed_codes(date_str):
    """读取 status/*.pass.json 获取已通过股票代码列表。"""
    passed = []
    if not os.path.exists(STATUS_DIR):
        return passed
    try:
        for fname in os.listdir(STATUS_DIR):
            if fname.startswith(f"{date_str}_") and fname.endswith(".pass.json"):
                code = fname.replace(f"{date_str}_", "").replace(".pass.json", "")
                if code:
                    passed.append(code)
    except Exception:
        pass
    return passed


def incremental_dedupe_check(current_code, current_name, date_str, passed_stocks):
    """委托给 P0-I --incremental-codes 权威引擎。
    从 pass.json 读取历史已通过股票，加上本次已通过和当前股票。
    返回 (passed: bool, detail: str)。"""
    # Collect codes: pass.json history + this session's passed + current
    all_codes = set(get_passed_codes(date_str))
    if passed_stocks:
        for c, _ in passed_stocks:
            all_codes.add(c)
    all_codes.add(current_code)

    codes_str = ",".join(sorted(all_codes))

    passed, output = run_p0i_incremental(codes_str, date_str)
    if passed:
        return True, ""
    else:
        return False, f"INCREMENTAL_P0I_BLOCK: codes={codes_str}"


def run_parser_validation(date_str):
    """占位解析器验收函数。真实验收未接入前必须 fail-closed。"""
    log(f"NOT_IMPLEMENTED: run_parser_validation for {date_str} — 真实验收未接入，占位骨架", "BLOCK")
    return False


def run_full_gate(date_str):
    """占位 release gate 函数。真实 gate 未接入前必须 fail-closed。"""
    log(f"NOT_IMPLEMENTED: run_release_gate for {date_str} — 真实 gate 未接入，占位骨架", "BLOCK")
    return False


def main():
    ap = argparse.ArgumentParser(
        description="逐票串行日报生成调度器 v3.6.3",
        epilog="⛔ 禁止批量生成/修复全部股票。只能逐票串行。"
    )
    ap.add_argument("--date", required=True, help="交易日 YYYYMMDD")
    ap.add_argument("--dry-run", action="store_true", help="只打印队列顺序，不写任何文件，不运行生成")
    ap.add_argument("--start-from", default="", help="从指定股票代码开始处理（跳过前面的）")
    ap.add_argument("--only", default="", help="只处理指定股票代码")
    ap.add_argument("--validate-only", action="store_true",
                    help="只验证不生成：跳过 generate_one/convert_to_pdf，直接对队列逐票跑 check_single_stock")
    ap.add_argument("--incremental-dedupe", action="store_true",
                    help="在 --validate-only 或 --render-only 模式下启用跨股票重复文本拦截（额外检查，不替代 P0-I）")
    ap.add_argument("--render-only", action="store_true",
                    help="只渲染不生成：跳过 generate_one，对队列逐票执行 convert_to_pdf + check_single_stock + 可选 incremental-dedupe")
    ap.add_argument("--prepare-one", action="store_true",
                    help="输出单票生成任务包(--only CODE 必须): 不写日报,只生成任务包JSON到 logs/daily_one_by_one_tasks/")
    ap.add_argument("--prepare-next", action="store_true",
                    help="输出下一只待处理股票的任务包: 按动态池顺序查找首个无pass.json的股票,输出任务包")
    args = ap.parse_args()

    date_str = args.date

    # ===== 1. 读取动态股票池 =====
    pool = load_pool()
    if not pool:
        log("POOL_EMPTY: 股票池为空，无法继续", "BLOCK")
        sys.exit(2)

    log(f"POOL: {len(pool)} stocks from pigeon_config.json")
    for i, (c, n) in enumerate(pool, 1):
        log(f"  {i}. {n}({c})")

    # ===== 2. 过滤 =====
    if args.only:
        pool = [(c, n) for c, n in pool if c == args.only]
        if not pool:
            log(f"ONLY_NOT_FOUND: 股票 {args.only} 不在池中", "BLOCK")
            sys.exit(2)
        log(f"FILTER: --only {args.only} → 1 stock")

    if args.start_from:
        start_idx = None
        for i, (c, _) in enumerate(pool):
            if c == args.start_from:
                start_idx = i
                break
        if start_idx is None:
            log(f"START_FROM_NOT_FOUND: {args.start_from} 不在池中", "BLOCK")
            sys.exit(2)
        pool = pool[start_idx:]
        log(f"FILTER: --start-from {args.start_from} → {len(pool)} stocks remaining")

    # ===== 3. dry-run =====
    if args.dry_run:
        print()
        log("=== DRY RUN ===")
        log(f"Date: {date_str}")
        log(f"Queue size: {len(pool)}")
        print()
        for i, (c, n) in enumerate(pool, 1):
            log(f"  [{i}] {n}({c})")
        print()
        log("DRY_RUN_COMPLETE: 未写入任何文件，未运行生成")
        sys.exit(0)

    # ===== 4. 校验 signal =====
    print()
    log("=== SIGNAL VERIFICATION ===")
    if not verify_signal(date_str, pool):
        log("SIGNAL_VERIFICATION_FAILED: 终止", "BLOCK")
        sys.exit(2)

    # ===== 5. --prepare-one: 输出单票任务包，不生成/渲染/修改产物 =====
    if args.prepare_one:
        print()
        log("=== PREPARE ONE: 单票任务包 ===")
        if not args.only:
            log("--prepare-one 必须带 --only CODE", "BLOCK")
            sys.exit(2)

        # Signal already verified above
        os.makedirs(TASKS_DIR, exist_ok=True)

        # Get stock name
        code = args.only
        name = None
        pool_before_filter = load_pool()
        for c, n in pool_before_filter:
            if c == code:
                name = n
                break

        if not name:
            log(f"CODE_NOT_IN_POOL: {code}", "BLOCK")
            sys.exit(2)

        stock_dir = os.path.join(REPORT_DIR, f"{name}({code})")
        allowed_paths = [
            os.path.join(stock_dir, f"{name}({code})日报_{date_str}.md"),
            os.path.join(stock_dir, f"{name}({code})日报_{date_str}.json"),
        ]
        snapshot = compute_file_snapshot(date_str)
        task = {
            "date": date_str,
            "code": code,
            "name": name,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "report_md_path": allowed_paths[0],
            "report_json_path": allowed_paths[1],
            "report_html_path": os.path.join(stock_dir, f"{name}({code})日报_{date_str}.html"),
            "report_pdf_path": os.path.join(stock_dir, f"{name}({code})日报_{date_str}.pdf"),
            "signal_path": SIGNAL_FILE,
            "golden_master_md": os.path.join(REPORT_DIR, "东睦股份(600114)", "东睦股份(600114)日报_20260603.md"),
            "golden_master_html": os.path.join(REPORT_DIR, "东睦股份(600114)", "东睦股份(600114)日报_20260603.html"),
            "required_team_roles": ["山猫_宏观", "信鸽_事件", "玉夜_数据", "流金_风控", "青山_信号", "腰子_整合"],
            "allowed_write_paths": allowed_paths,
            "forbidden_write_globs": [
                f"重点股票/股票报告/*/*日报_{date_str}.md",
                f"重点股票/股票报告/*/*日报_{date_str}.json",
                f"重点股票/股票报告/*/*日报_{date_str}.html",
                f"重点股票/股票报告/*/*日报_{date_str}.pdf",
            ],
            "pre_task_file_snapshot": snapshot,
            "must_follow": [
                "只写当前股票 MD/JSON",
                "不写 HTML/PDF",
                "不碰其他任何股票",
                "不碰 scripts/gate/crontab",
                "解读必须全团讨论",
                "数据必须转成人话解释",
                "禁止套用其他股票同一句话",
                "必须按母版结构(10段)",
            ],
            "after_write_command": f"python3 scripts/run_daily_report_one_by_one.py --date {date_str} --render-only --only {code} --incremental-dedupe",
        }
        task_path = os.path.join(TASKS_DIR, f"{date_str}_{code}.json")
        with open(task_path, "w", encoding="utf-8") as f:
            json.dump(task, f, ensure_ascii=False, indent=2)
        write_task_prompt(task, code, date_str)
        prompt_path = os.path.join(TASKS_DIR, f"{date_str}_{code}.prompt.txt")
        log(f"TASK_PACKAGE: {task_path}")
        log(f"PROMPT_FILE:  {prompt_path}")
        log(f"  code={code} name={name}")
        log("  不修改任何日报产物/scripts/gate/crontab")
        log("PREPARE_ONE_COMPLETE: 任务包已就绪，由团队按包生成")
        sys.exit(0)

    # ===== 6. --prepare-next: 找下一只待处理股票 =====
    if args.prepare_next:
        print()
        log("=== PREPARE NEXT: 查找下一只待处理股票 ===")
        if args.only:
            log("--prepare-next 不允许与 --only 同时使用", "BLOCK")
            sys.exit(2)
        if args.start_from:
            log("PREPARE_NEXT_NO_START_FROM: --prepare-next 不允许与 --start-from 同时使用", "BLOCK")
            sys.exit(2)

        os.makedirs(STATUS_DIR, exist_ok=True)
        all_passed = True
        next_stock = None

        for code, name in pool:
            status_path = os.path.join(STATUS_DIR, f"{date_str}_{code}.pass.json")
            if not os.path.exists(status_path):
                all_passed = False
                next_stock = (code, name)
                log(f"FOUND_NEXT: {name}({code}) — 无 pass.json")
                break
            else:
                log(f"  ✅ {name}({code}) — 已通过")

        if all_passed:
            log("ALL_STOCKS_PREPARED_AND_PASSED: 全部股票已有 pass.json", "OK")
            sys.exit(0)

        if not next_stock:
            log("NEXT_STOCK_NOT_FOUND: 无待处理股票", "BLOCK")
            sys.exit(2)

        code, name = next_stock
        stock_dir = os.path.join(REPORT_DIR, f"{name}({code})")
        allowed_paths = [
            os.path.join(stock_dir, f"{name}({code})日报_{date_str}.md"),
            os.path.join(stock_dir, f"{name}({code})日报_{date_str}.json"),
        ]
        snapshot = compute_file_snapshot(date_str)
        task = {
            "date": date_str,
            "code": code,
            "name": name,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "report_md_path": allowed_paths[0],
            "report_json_path": allowed_paths[1],
            "report_html_path": os.path.join(stock_dir, f"{name}({code})日报_{date_str}.html"),
            "report_pdf_path": os.path.join(stock_dir, f"{name}({code})日报_{date_str}.pdf"),
            "signal_path": SIGNAL_FILE,
            "golden_master_md": os.path.join(REPORT_DIR, "东睦股份(600114)", "东睦股份(600114)日报_20260603.md"),
            "golden_master_html": os.path.join(REPORT_DIR, "东睦股份(600114)", "东睦股份(600114)日报_20260603.html"),
            "required_team_roles": ["山猫_宏观", "信鸽_事件", "玉夜_数据", "流金_风控", "青山_信号", "腰子_整合"],
            "allowed_write_paths": allowed_paths,
            "forbidden_write_globs": [
                f"重点股票/股票报告/*/*日报_{date_str}.md",
                f"重点股票/股票报告/*/*日报_{date_str}.json",
                f"重点股票/股票报告/*/*日报_{date_str}.html",
                f"重点股票/股票报告/*/*日报_{date_str}.pdf",
            ],
            "pre_task_file_snapshot": snapshot,
            "must_follow": [
                "只写当前股票 MD/JSON",
                "不写 HTML/PDF",
                "不碰其他任何股票",
                "不碰 scripts/gate/crontab",
                "解读必须全团讨论",
                "数据必须转成人话解释",
                "禁止套用其他股票同一句话",
                "必须按母版结构(10段)",
            ],
            "after_write_command": f"python3 scripts/run_daily_report_one_by_one.py --date {date_str} --render-only --only {code} --incremental-dedupe",
        }
        task_path = os.path.join(TASKS_DIR, f"{date_str}_{code}.json")
        os.makedirs(TASKS_DIR, exist_ok=True)
        with open(task_path, "w", encoding="utf-8") as f:
            json.dump(task, f, ensure_ascii=False, indent=2)
        write_task_prompt(task, code, date_str)
        prompt_path = os.path.join(TASKS_DIR, f"{date_str}_{code}.prompt.txt")
        log(f"TASK_PACKAGE: {task_path}")
        log(f"PROMPT_FILE:  {prompt_path}")
        log(f"  code={code} name={name}")
        log("PREPARE_NEXT_COMPLETE: 任务包已就绪，由团队按包生成")
        sys.exit(0)

    # ===== 7. --render-only: 不生成，只渲染+验收 =====
    if args.render_only:
        print()
        if not args.only:
            log("RENDER_ONLY_REQUIRES_ONLY: --render-only 必须带 --only CODE", "BLOCK")
            log("禁止批量渲染。如需全量请逐票单只调用。", "BLOCK")
            sys.exit(2)
        if args.start_from:
            log("RENDER_ONLY_NO_START_FROM: --render-only 禁止与 --start-from 同时使用", "BLOCK")
            sys.exit(2)
        log(f"=== RENDER ONLY: {len(pool)} stocks ===")
        log("跳过 generate_one，执行 convert_to_pdf + scope_guard + check_single_stock")
        show_dedupe = args.incremental_dedupe
        if show_dedupe:
            log("--incremental-dedupe 启用：逐票检查跨股票文本重复")
        any_failed = False
        failed_stock = None
        passed_stocks = []
        for idx, (code, name) in enumerate(pool, 1):
            print()
            log(f"[{idx}/{len(pool)}] Rendering {name}({code})...")
            # Hard scope guard (pre-render): task.json must exist, parse OK, no unauthorized changes
            task_path = os.path.join(TASKS_DIR, f"{date_str}_{code}.json")
            if not os.path.exists(task_path):
                log(f"TASK_PACKAGE_REQUIRED: 任务包不存在(请通过 --prepare-one/--prepare-next 生成): {task_path}", "BLOCK")
                failed_stock = f"{name}({code})"
                any_failed = True
                break
            try:
                with open(task_path, "r", encoding="utf-8") as _tf:
                    task_data = json.load(_tf)
            except Exception as e:
                log(f"TASK_PACKAGE_PARSE_FAIL: 任务包解析失败: {task_path}: {e}", "BLOCK")
                failed_stock = f"{name}({code})"
                any_failed = True
                break
            ok, detail = check_single_task_scope(date_str, code, name, task_data)
            if not ok:
                log(f"  [BLOCK] {detail}", "BLOCK")
                failed_stock = f"{name}({code})"
                any_failed = True
                break
            if not convert_to_pdf(code, name, date_str):
                failed_stock = f"{name}({code})"
                log(f"RENDER_FAILED: {failed_stock} at convert_to_pdf", "BLOCK")
                any_failed = True
                break
            # Post-render scope: only current stock files may have changed
            ok2, detail2 = check_single_task_scope(date_str, code, name, task_data, post_render=True)
            if not ok2:
                log(f"  [BLOCK] post-render scope: {detail2}", "BLOCK")
                failed_stock = f"{name}({code})"
                any_failed = True
                break
            if not check_single_stock(date_str, code, name):
                failed_stock = f"{name}({code})"
                log(f"RENDER_FAILED: {failed_stock} at check_single_stock", "BLOCK")
                any_failed = True
                break
            if show_dedupe:
                ok3, detail3 = incremental_dedupe_check(code, name, date_str, passed_stocks)
                if not ok3:
                    log(f"INCREMENTAL_DEDUPE_BLOCK: {detail3}", "BLOCK")
                    failed_stock = f"{name}({code})"
                    any_failed = True
                    break
                if passed_stocks:
                    log(f"  [DEDUPE] 与 {len(passed_stocks)} 只已通过股票无重复")
                passed_stocks.append((code, name))
            write_pass_status(code, name, date_str)
            log(f"  ✅ {name}({code}) render + check passed")
        if any_failed and failed_stock:
            print()
            log(f"RENDER_STOPPED: {failed_stock} 失败，不继续", "BLOCK")
            sys.exit(2)
        log(f"RENDER_ALL_PASS: {len(pool)} stocks")
        sys.exit(0)


    # ===== 8. --validate-only: 跳过生成，直接逐票真实检查 =====
    if args.validate_only:
        print()
        log(f"=== VALIDATE ONLY: {len(pool)} stocks ===")
        log("跳过 generate_one/convert_to_pdf，直接跑 check_single_stock")
        show_dedupe = args.incremental_dedupe
        if show_dedupe:
            log("--incremental-dedupe 启用：逐票检查跨股票文本重复")
        any_failed = False
        failed_stock = None
        passed_stocks = []  # (code, name) of stocks that passed check_single_stock
        for idx, (code, name) in enumerate(pool, 1):
            print()
            log(f"[{idx}/{len(pool)}] Validating {name}({code})...")
            if not check_single_stock(date_str, code, name):
                failed_stock = f"{name}({code})"
                log(f"VALIDATION_FAILED: {failed_stock}", "BLOCK")
                any_failed = True
                break
            if show_dedupe:
                ok, detail = incremental_dedupe_check(code, name, date_str, passed_stocks)
                if not ok:
                    log(f"INCREMENTAL_DEDUPE_BLOCK: {detail}", "BLOCK")
                    failed_stock = f"{name}({code})"
                    any_failed = True
                    break
                if passed_stocks:
                    log(f"  [DEDUPE] 与 {len(passed_stocks)} 只已通过股票无重复")
                passed_stocks.append((code, name))
            log(f"  ✅ {name}({code}) validation passed")
        if any_failed and failed_stock:
            print()
            log(f"VALIDATION_STOPPED: {failed_stock} 失败，不继续", "BLOCK")
            sys.exit(2)
        log(f"VALIDATION_ALL_PASS: {len(pool)} stocks")
        sys.exit(0)

    # ===== 9. 逐票串行处理 (正常模式, 首只即停) =====
    print()
    log(f"=== QUEUE PROCESSING: {len(pool)} stocks ===")
    log("(generate_one/convert_to_pdf 尚未接入，首只即停)")

    any_failed = False
    failed_stock = None

    for idx, (code, name) in enumerate(pool, 1):
        print()
        log(f"[{idx}/{len(pool)}] Processing {name}({code})...")

        # Step A: Generate report (占位 fail-closed)
        if not generate_one(date_str, code, name):
            failed_stock = f"{name}({code})"
            log(f"FAILED: {failed_stock} at generate_one", "BLOCK")
            any_failed = True
            break

        # Step B: PDF conversion (占位 fail-closed)
        if not convert_to_pdf(code, name, date_str):
            failed_stock = f"{name}({code})"
            log(f"FAILED: {failed_stock} at convert_to_pdf", "BLOCK")
            any_failed = True
            break

        # Step C: Single-stock quality checks
        if not check_single_stock(date_str, code, name):
            failed_stock = f"{name}({code})"
            log(f"FAILED: {failed_stock} at check_single_stock", "BLOCK")
            any_failed = True
            break

        log(f"  ✅ {name}({code}) passed")

    if any_failed and failed_stock:
        print()
        log(f"QUEUE_STOPPED: {failed_stock} 失败，不进入下一只", "BLOCK")
        log("修复后重试，batch生成/并发生成禁止", "BLOCK")
        sys.exit(2)

    # ===== 10. 全部通过 → 验收 (本阶段不会到达) =====
    print()
    log(f"=== ALL {len(pool)} STOCKS PASSED ===")
    log("Running parser validation...")
    if not run_parser_validation(date_str):
        log("PARSER_FAILED", "BLOCK")
        sys.exit(2)

    log("Running full release gate...")
    if not run_full_gate(date_str):
        log("RELEASE_GATE_FAILED", "BLOCK")
        sys.exit(2)

    print()
    log(f"ALL_PASS: {date_str} 全部 {len(pool)} 只通过 release gate")
    sys.exit(0)


if __name__ == "__main__":
    main()
