#!/usr/bin/env python3
"""
run_daily_production_pipeline.py — 每日数据生产闭环入口 v1.0

串联：token加载 → tushare同步 → 数据采集 → 评分 → 物料化 → 日报 → 归档 → ready

用法:
  python3 scripts/run_daily_production_pipeline.py --date 20260612
  python3 scripts/run_daily_production_pipeline.py --date 20260612 --dry-run
"""
import argparse, json, os, site, subprocess, sys, time, traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from check_runtime_dependency_readiness import run_check as dep_run_check
from runtime_secret_loader import DEFAULT_PRIVATE_ENV, TUSHARE_TOKEN, load_secret

TZ_SHANGHAI = timezone(timedelta(hours=8))
PRODUCTION_DIR = ROOT / "logs" / "daily_production"
STATUS_DIR = ROOT / "logs" / "daily_data_retry" / "status"
DATA_DIR = ROOT / "代码文件" / "数据"
HISTORY_DIR = ROOT / "历史数据"
MANIFEST_DIR = ROOT / "历史数据" / "manifest"
TOKEN_FILE = DEFAULT_PRIVATE_ENV
SIGNAL_PATH = ROOT / ".claude" / "signal_daily_report.json"
TARGETS_PATH = ROOT / "00_项目地基" / "02_权威注册表" / "daily_report_targets.json"
RUNTIME_HOME = ROOT / "logs" / "runtime_home"

def now():
    return datetime.now(TZ_SHANGHAI).isoformat()

def subprocess_env():
    """Keep child process caches/temp files inside the workspace.

    Also inject PYTHONPATH with the user site-packages directory so that
    subprocesses can find installed packages (markdown, tushare, etc.)
    even though HOME is redirected to RUNTIME_HOME.
    """
    env = os.environ.copy()
    RUNTIME_HOME.mkdir(parents=True, exist_ok=True)
    env["HOME"] = str(RUNTIME_HOME)
    env.setdefault("XDG_CACHE_HOME", str(RUNTIME_HOME / ".cache"))
    env.setdefault("TUSHARE_CACHE_DIR", str(RUNTIME_HOME / "tushare"))

    # Inject real user site-packages into PYTHONPATH so subprocess
    # can import packages despite the fake HOME.
    try:
        user_sp = site.getusersitepackages()
        if user_sp and os.path.isdir(user_sp):
            existing = env.get("PYTHONPATH", "")
            if existing:
                env["PYTHONPATH"] = user_sp + os.pathsep + existing
            else:
                env["PYTHONPATH"] = user_sp
    except Exception:
        pass

    return env

def load_token():
    """加载 TUSHARE_TOKEN：环境变量优先，再读私有文件"""
    token, meta = load_secret(TUSHARE_TOKEN, private_env=TOKEN_FILE, allow_process_env=True)
    if not token:
        return None, meta.get("reason", "missing_runtime_env:TUSHARE_TOKEN"), meta
    os.environ[TUSHARE_TOKEN] = token
    return token, None, meta

def write_preflight_block(date_str, blocker, meta, step_name="runtime_secret_preflight"):
    """Persist preflight BLOCK evidence even when production cannot start."""
    step = {
        "step": step_name,
        "command": "load runtime secret metadata",
        "started_at": now(),
        "finished_at": now(),
        "duration_sec": 0,
        "returncode": 2,
        "status": "BLOCK",
        "stdout_tail": [blocker],
        "stderr_tail": [],
        "output_files": [],
        "metadata": meta,
    }
    manifest = {
        "flow": "run_daily_production_pipeline",
        "date": date_str,
        "run_at": now(),
        "overall": "BLOCK",
        "dry_run": False,
        "steps": [step],
        "status_split": {
            "data_ready": "BLOCK",
            "report_ready": "BLOCK",
            "archive_ready": "BLOCK",
            "canonical_ready": "BLOCK",
            "quality_ready": "BLOCK",
            "closure_ready": "BLOCK",
        },
    }
    ready_data = {
        "date": date_str,
        "ready": False,
        "ready_at": now(),
        "pipeline_status": "BLOCK",
        "data_ready": "BLOCK",
        "report_ready": "BLOCK",
        "archive_ready": "BLOCK",
        "canonical_ready": "BLOCK",
        "quality_ready": "BLOCK",
        "closure_ready": "BLOCK",
        "blocker": [step_name],
    }
    manifest_path = PRODUCTION_DIR / f"{date_str}_manifest.json"
    ready_path = STATUS_DIR / f"{date_str}.ready.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    with open(ready_path, "w", encoding="utf-8") as f:
        json.dump(ready_data, f, ensure_ascii=False, indent=2)
    return manifest_path, ready_path

def write_signal_daily_report(date_str, data_ready):
    """写 signal_daily_report.json — 日报前置信号，仅写入必检字段。
    data_ready=true 仅当所有数据步骤 PASS；否则写 false 防止日报越界生成。
    """
    signal = {
        "signal": "daily_report",
        "timestamp": now(),
        "data_ready": bool(data_ready),
        "date": date_str,
        "mode": "daily",
        "pipeline_mode": True,
        "source": "run_daily_production_pipeline",
    }
    SIGNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SIGNAL_PATH, "w", encoding="utf-8") as f:
        json.dump(signal, f, ensure_ascii=False, indent=2)
    return str(SIGNAL_PATH)

def run_step(name, cmd, cwd=None, timeout_s=120):
    """运行一步并返回执行记录"""
    started = now()
    step = {"step": name, "command": " ".join(str(c) for c in cmd), "started_at": started}
    try:
        r = subprocess.run(cmd, cwd=str(cwd or ROOT), capture_output=True, text=True, timeout=timeout_s, env=subprocess_env())
        step["finished_at"] = now()
        step["duration_sec"] = round((datetime.fromisoformat(step["finished_at"]) - datetime.fromisoformat(started)).total_seconds(), 1)
        step["returncode"] = r.returncode
        step["stdout_tail"] = r.stdout.strip().split("\n")[-5:] if r.stdout else []
        step["stderr_tail"] = r.stderr.strip().split("\n")[-5:] if r.stderr else []
        step["status"] = "PASS" if r.returncode == 0 else "BLOCK"
        step["output_files"] = []
    except subprocess.TimeoutExpired:
        step["finished_at"] = now()
        step["duration_sec"] = timeout_s
        step["returncode"] = -1
        step["stdout_tail"] = []
        step["stderr_tail"] = [f"TIMEOUT after {timeout_s}s"]
        step["status"] = "BLOCK"
    return step

def check_baseline_preflight(date_str, targets_path=None):
    """对 daily_report_targets.json active_targets 检查各股票是否有唯一有效 baseline。
    Returns dict: {status: "PASS"|"BLOCK"|"SKIP", reason: str, results: list}
    """
    if targets_path is None:
        targets_path = TARGETS_PATH
    if not targets_path.exists():
        return {"status": "BLOCK", "reason": "daily_report_targets.json not found", "results": []}
    try:
        targets = json.loads(targets_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return {"status": "BLOCK", "reason": f"failed to read targets: {e}", "results": []}
    active = [t for t in targets.get("active_targets", []) if t.get("enabled", False)]
    if not active:
        return {"status": "SKIP", "reason": "no active targets", "results": []}
    all_results = []
    for t in active:
        code = str(t["code"])
        name = t["name"]
        cmd = [sys.executable, str(ROOT / "scripts" / "resolve_current_baseline.py"),
               "--code", code, "--name", name, "--date", date_str, "--json"]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30, env=subprocess_env())
            data = json.loads(r.stdout)
            all_results.extend(data if isinstance(data, list) else [data])
        except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
            all_results.append({
                "stock_code": code, "stock_name": name,
                "result": "BLOCK", "reason": f"subprocess error: {str(e)[:200]}",
            })
    blockers = [r for r in all_results if r.get("result") != "PASS"]
    if blockers:
        reasons = "; ".join(
            f"{b['stock_code']}:{b.get('stock_name','')}:{b.get('reason','?')}" for b in blockers
        )
        return {"status": "BLOCK", "reason": f"baseline preflight BLOCK: {reasons}", "results": all_results}
    return {"status": "PASS", "reason": "", "results": all_results}

def load_active_report_targets(targets_path=None):
    """Return enabled daily report targets only; this is the production report scope."""
    if targets_path is None:
        targets_path = TARGETS_PATH
    if not targets_path.exists():
        return []
    try:
        targets = json.loads(targets_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return [t for t in targets.get("active_targets", []) if t.get("enabled", False)]

def run_canonical_shadow_for_active_targets(date_str, py_exe, shadow_dir):
    """Build/check canonical shadows for enabled daily_report_targets.json entries."""
    targets = load_active_report_targets()
    started = now()
    build_step = {
        "step": "canonical_shadow_build",
        "command": "build active daily_report_targets canonical shadows",
        "started_at": started,
        "stdout_tail": [],
        "stderr_tail": [],
        "output_files": [],
    }
    if not targets:
        finished = now()
        build_step.update({
            "finished_at": finished,
            "duration_sec": round((datetime.fromisoformat(finished) - datetime.fromisoformat(started)).total_seconds(), 1),
            "returncode": 0,
            "status": "SKIP",
            "stdout_tail": ["no enabled daily_report_targets"],
        })
        gate_step = dict(build_step)
        gate_step["step"] = "canonical_shadow_gate"
        gate_step["command"] = "SKIP: no enabled daily_report_targets"
        return build_step, gate_step

    shadow_dir.mkdir(parents=True, exist_ok=True)
    build_failures = []
    for target in targets:
        code = str(target["code"])
        name = target["name"]
        out_path = shadow_dir / f"{code}_{date_str}_canonical_report.json"
        cmd = [
            py_exe, str(ROOT / "scripts" / "build_canonical_report.py"),
            "--code", code, "--name", name, "--date", date_str, "--out", str(out_path),
        ]
        try:
            r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=120, env=subprocess_env())
            build_step["stdout_tail"].extend(r.stdout.strip().split("\n")[-3:] if r.stdout else [])
            build_step["stderr_tail"].extend(r.stderr.strip().split("\n")[-3:] if r.stderr else [])
            if r.returncode == 0:
                build_step["output_files"].append(str(out_path))
            else:
                build_failures.append(f"{name}({code}) rc={r.returncode}")
        except subprocess.TimeoutExpired:
            build_failures.append(f"{name}({code}) timeout")

    finished = now()
    build_step.update({
        "finished_at": finished,
        "duration_sec": round((datetime.fromisoformat(finished) - datetime.fromisoformat(started)).total_seconds(), 1),
        "returncode": 0 if not build_failures else 2,
        "status": "PASS" if not build_failures else "BLOCK",
        "stdout_tail": (build_step["stdout_tail"] + [f"active_targets={len(targets)} failures={len(build_failures)}"])[-5:],
        "stderr_tail": (build_step["stderr_tail"] + build_failures)[-5:],
    })

    gate_started = now()
    gate_step = {
        "step": "canonical_shadow_gate",
        "command": "check active daily_report_targets canonical shadows",
        "started_at": gate_started,
        "stdout_tail": [],
        "stderr_tail": [],
        "output_files": [],
    }
    if build_failures:
        gate_finished = now()
        gate_step.update({
            "finished_at": gate_finished,
            "duration_sec": round((datetime.fromisoformat(gate_finished) - datetime.fromisoformat(gate_started)).total_seconds(), 1),
            "returncode": 2,
            "status": "BLOCK",
            "stdout_tail": ["SKIP gate because canonical build failed"],
            "stderr_tail": build_failures[-5:],
        })
        return build_step, gate_step

    gate_failures = []
    for target in targets:
        code = str(target["code"])
        name = target["name"]
        canonical_path = shadow_dir / f"{code}_{date_str}_canonical_report.json"
        cmd = [
            py_exe, str(ROOT / "scripts" / "check_canonical_report_shadow.py"),
            "--code", code, "--name", name, "--date", date_str,
            "--canonical", str(canonical_path), "--json",
        ]
        try:
            r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=120, env=subprocess_env())
            gate_step["stdout_tail"].extend(r.stdout.strip().split("\n")[-3:] if r.stdout else [])
            gate_step["stderr_tail"].extend(r.stderr.strip().split("\n")[-3:] if r.stderr else [])
            if r.returncode != 0:
                gate_failures.append(f"{name}({code}) rc={r.returncode}")
        except subprocess.TimeoutExpired:
            gate_failures.append(f"{name}({code}) timeout")

    gate_finished = now()
    gate_step.update({
        "finished_at": gate_finished,
        "duration_sec": round((datetime.fromisoformat(gate_finished) - datetime.fromisoformat(gate_started)).total_seconds(), 1),
        "returncode": 0 if not gate_failures else 2,
        "status": "PASS" if not gate_failures else "BLOCK",
        "stdout_tail": (gate_step["stdout_tail"] + [f"active_targets={len(targets)} failures={len(gate_failures)}"])[-5:],
        "stderr_tail": (gate_step["stderr_tail"] + gate_failures)[-5:],
    })
    return build_step, gate_step

def main():
    ap = argparse.ArgumentParser(description="每日数据生产闭环")
    ap.add_argument("--date", required=True, help="YYYYMMDD")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-report", action="store_true", help="跳过日报生成")
    args = ap.parse_args()
    date_str = args.date

    PY = sys.executable
    planned_steps = [
        "tushare_sync",
        "build_dynamic_pool",
        "batch_data_collector",
        "scoring_engine",
        "nan_cleanup_and_meta",
        "materialize_cache",
        "baseline_preflight",
        "daily_report" if not args.skip_report else "daily_report(SKIP)",
        "canonical_shadow_build" if not args.skip_report else "canonical_shadow_build(SKIP)",
        "canonical_shadow_gate" if not args.skip_report else "canonical_shadow_gate(SKIP)",
        "archive",
        "data_quality_gate",
        "data_chain_health",
        "inspect_data_health",
        "strict_json_check",
        "archive_verify",
        "closure_verify",
    ]

    if args.dry_run:
        bdc_dry_cmd = [PY, str(ROOT/"代码文件"/"每日荐股"/"scripts"/"batch_data_collector.py"), "--date", date_str]
        print(json.dumps({
            "flow": "run_daily_production_pipeline",
            "date": date_str,
            "dry_run": True,
            "would_run": planned_steps,
            "planned_commands": {
                "batch_data_collector": " ".join(str(c) for c in bdc_dry_cmd),
            },
            "would_write": [],
            "guarantee": "dry-run returns before token loading, subprocess execution, ready/manifest writes, data/archive/report writes"
        }, ensure_ascii=False, indent=2))
        return 0

    os.makedirs(PRODUCTION_DIR, exist_ok=True)
    os.makedirs(STATUS_DIR, exist_ok=True)
    os.makedirs(MANIFEST_DIR, exist_ok=True)

    # Step 0: 加载 token
    token, err, token_meta = load_token()
    if err:
        manifest_path, ready_path = write_preflight_block(date_str, err, token_meta)
        print(json.dumps({
            "flow": "run_daily_production_pipeline",
            "date": date_str,
            "error": err,
            "manifest_json": str(manifest_path),
            "ready_json": str(ready_path),
        }, ensure_ascii=False))
        sys.exit(2)

    # Step 0b: 生产依赖预检 — 在进入生产步骤前检查所需 Python 包
    # Use subprocess_env() so the check simulates pipeline child process env
    dep_result = dep_run_check(
        "daily_production",
        python_executable=PY,
        env=subprocess_env(),
    )
    if dep_result["overall"] != "PASS":
        blocker = "; ".join(dep_result["findings"])
        manifest_path, ready_path = write_preflight_block(
            date_str, blocker, dep_result,
            step_name="runtime_dependency_preflight"
        )
        print(json.dumps({
            "flow": "run_daily_production_pipeline",
            "date": date_str,
            "error": blocker,
            "blocker": "runtime_dependency_preflight",
            "manifest_json": str(manifest_path),
            "ready_json": str(ready_path),
        }, ensure_ascii=False))
        sys.exit(2)

    steps = []

    # Step 1: tushare 历史数据同步
    steps.append(run_step("tushare_sync", [PY, str(ROOT/"代码文件"/"tools"/"tushare_history_sync.py"), "--daily"], timeout_s=180))

    # Step 2: 动态池构建
    steps.append(run_step("build_dynamic_pool", [PY, str(ROOT/"代码文件"/"每日荐股"/"scripts"/"build_dynamic_pool.py")], timeout_s=30))

    # Step 3: batch_data_collector（含增量K线，显式传 --date）
    bdc = [PY, str(ROOT/"代码文件"/"每日荐股"/"scripts"/"batch_data_collector.py"), "--date", date_str]
    steps.append(run_step("batch_data_collector", bdc, timeout_s=300))

    # Step 4: 评分引擎
    steps.append(run_step("scoring_engine", [PY, str(ROOT/"代码文件"/"每日荐股"/"分析逻辑"/"scoring_engine_v2.py"), "--date", date_str], timeout_s=120))

    # Step 5: NaN 清洗 + _Meta 补齐
    nanfix_step = {
        "step": "nan_cleanup_and_meta",
        "command": "inline python",
        "started_at": now(),
    }
    try:
        import math as _m
        df_path = DATA_DIR / "data_full.json"
        if df_path.exists():
            with open(df_path, encoding="utf-8") as _fh:
                _df = json.load(_fh)
            def _clean(o):
                if isinstance(o, dict): return {k: _clean(v) for k,v in o.items()}
                if isinstance(o, list): return [_clean(v) for v in o]
                if isinstance(o, float) and (_m.isnan(o) or _m.isinf(o)): return None
                return o
            _df = _clean(_df)
            _meta = _df.get("_Meta") or _df.get("meta") or {}
            if isinstance(_meta, dict):
                if "checked_at" not in _meta:
                    _meta["checked_at"] = now()
                if "target_date" not in _meta:
                    _meta["target_date"] = date_str
                if "data_date" not in _meta:
                    _meta["data_date"] = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                _df["_Meta"] = _meta
            with open(df_path, "w", encoding="utf-8") as _fh:
                json.dump(_df, _fh, ensure_ascii=False, allow_nan=False)
            # Verify
            _verify = json.load(open(df_path, encoding="utf-8"))
            _txt = open(df_path, encoding="utf-8").read()
            if "NaN" in _txt or "Infinity" in _txt:
                nanfix_step["status"] = "BLOCK"
                nanfix_step["stdout_tail"] = ["NaN/Infinity still present after cleanup"]
            else:
                nanfix_step["status"] = "PASS"
                nanfix_step["stdout_tail"] = [f"NaN cleaned, _Meta target_date={date_str}"]
        else:
            nanfix_step["status"] = "SKIP"
            nanfix_step["stdout_tail"] = ["data_full.json not found"]
    except Exception as _e:
        nanfix_step["status"] = "BLOCK"
        nanfix_step["stdout_tail"] = [f"nan_cleanup failed: {_e}"]
    nanfix_step["finished_at"] = now()
    nanfix_step["returncode"] = 0 if nanfix_step["status"] == "PASS" else 2
    steps.append(nanfix_step)

    # Step 6: materialize 缓存
    materialize = ROOT / "scripts" / "materialize_daily_authoritative_cache.py"
    if materialize.exists():
        steps.append(run_step("materialize_cache", [PY, str(materialize), "--date", date_str], timeout_s=60))

    # Signal: 日报前置信号 — 在调用日报前写当日 signal_daily_report.json
    # 日报入口校验 sig.date==date 且 data_ready=true，不写会 BLOCK
    if not args.skip_report:
        data_steps_names_pre = {"tushare_sync", "build_dynamic_pool", "batch_data_collector", "scoring_engine",
                                "nan_cleanup_and_meta", "materialize_cache"}
        data_ready_before_report = all(
            s["status"] == "PASS" for s in steps if s["step"] in data_steps_names_pre
        )
        write_signal_daily_report(date_str, data_ready_before_report)
        if not data_ready_before_report:
            print(f"[WARN] signal_daily_report written with data_ready=false (data steps not all PASS)")
        else:
            print(f"[INFO] signal_daily_report written with data_ready=true date={date_str}")

    # Step 7: Baseline authority preflight — 在日报前检查每日目标是否有唯一有效 baseline
    if not args.skip_report:
        preflight = check_baseline_preflight(date_str)
        bl_step = {
            "step": "baseline_preflight",
            "command": "call resolve_current_baseline for each daily_report_target",
            "started_at": now(),
            "finished_at": now(),
            "duration_sec": 0,
            "returncode": 0 if preflight["status"] == "PASS" else (2 if preflight["status"] == "BLOCK" else 0),
            "status": preflight["status"],
            "stdout_tail": [preflight.get("reason", "")] if preflight.get("reason") else ["all active targets have valid baseline"],
            "stderr_tail": [],
            "output_files": [],
        }
        steps.append(bl_step)
        if preflight["status"] == "BLOCK":
            print(f"[BLOCK] baseline_preflight: {preflight['reason']}")

    # Step 8: 日报生成（跳过若 baseline_preflight BLOCK）
    if not args.skip_report:
        _bp_status = next((s.get("status") for s in steps if s["step"] == "baseline_preflight"), None)
        if _bp_status == "BLOCK":
            _skip_now = now()
            for _skip_name in ("daily_report", "canonical_shadow_build", "canonical_shadow_gate"):
                steps.append({
                    "step": _skip_name,
                    "command": "SKIP: baseline_preflight BLOCK",
                    "started_at": _skip_now,
                    "finished_at": _skip_now,
                    "duration_sec": 0,
                    "returncode": 0,
                    "status": "SKIP",
                    "stdout_tail": ["SKIP by baseline_preflight"],
                    "stderr_tail": [],
                    "output_files": [],
                })
        else:
            # Step 8a: 日报 staging 生成
            staging_dir = ROOT / "运行产物" / "daily_report_build" / date_str
            staging_dir.mkdir(parents=True, exist_ok=True)
            staging_cmd = [PY, str(ROOT/"scripts"/"run_daily_report_html_only.py"),
                           "--date", date_str,
                           "--staging-dir", str(staging_dir),
                           "--require-pipeline-signal"]
            report_step = run_step("daily_report_staging", staging_cmd, timeout_s=300)
            steps.append(report_step)

            # Step 8b: 发布闸门 — release gate 检查 active targets
            release_gate_cmd = [PY, str(ROOT/"scripts"/"check_daily_release_gate.py"),
                                "--date", date_str, "--active-only"]
            rg_step = run_step("release_gate", release_gate_cmd, timeout_s=120)
            steps.append(rg_step)

            # Step 8c: 闸门通过后 promote 到正式目录
            if report_step.get("status") == "PASS" and rg_step.get("status") == "PASS":
                promote_cmd = [PY, str(ROOT/"scripts"/"run_daily_report_html_only.py"),
                               "--date", date_str,
                               "--staging-dir", str(staging_dir),
                               "--promote"]
                promote_step = run_step("report_promote", promote_cmd, timeout_s=60)
            else:
                promote_step = {
                    "step": "report_promote",
                    "command": "SKIP: staging/release_gate not PASS",
                    "started_at": now(),
                    "finished_at": now(),
                    "duration_sec": 0,
                    "returncode": 0,
                    "status": "SKIP",
                    "stdout_tail": ["SKIP by staging or release gate"],
                    "stderr_tail": [],
                    "output_files": []
                }
            steps.append(promote_step)

            if promote_step.get("status") == "PASS":
                shadow_dir = ROOT / "logs" / "canonical_shadow" / date_str
                build_step, gate_step = run_canonical_shadow_for_active_targets(date_str, PY, shadow_dir)
                steps.append(build_step)
                steps.append(gate_step)
            else:
                steps.append({
                    "step": "canonical_shadow_build",
                    "command": "SKIP: promote not PASS",
                    "started_at": now(),
                    "finished_at": now(),
                    "duration_sec": 0,
                    "returncode": 0,
                    "status": "SKIP",
                    "stdout_tail": ["SKIP by promote not PASS"],
                    "stderr_tail": [],
                    "output_files": []
                })
                steps.append({
                    "step": "canonical_shadow_gate",
                    "command": "SKIP: promote not PASS",
                    "started_at": now(),
                    "finished_at": now(),
                    "duration_sec": 0,
                    "returncode": 0,
                    "status": "SKIP",
                    "stdout_tail": ["SKIP by promote not PASS"],
                    "stderr_tail": [],
                    "output_files": []
                })

    # Step 9: 归档（带 --date）
    steps.append(run_step("archive", [PY, str(ROOT/"代码文件"/"每日荐股"/"scripts"/"archive_data.py"), "--date", date_str], timeout_s=30))

    # Step 8: DQ-Gate
    dq_json_path = PRODUCTION_DIR / f"{date_str}_check_data_quality.json"
    dq_cmd = [PY, str(ROOT/"代码文件"/"监督机制"/"check_data_quality.py"), "--date", date_str, "--json-output", str(dq_json_path)]
    steps.append(run_step("data_quality_gate", dq_cmd, timeout_s=30))

    # Step 9: 数据链健康检查
    health_cmd = [PY, str(ROOT/"scripts"/"check_daily_data_chain_health.py"), "--date", date_str]
    steps.append(run_step("data_chain_health", health_cmd, timeout_s=30))

    # Step 10: inspect_data_health daily_focus
    inspect_cmd = [PY, str(ROOT/"inspect_data_health.py"), "--no-repair", "--profile", "daily_focus", "--date", date_str,
                   "--json-output", str(PRODUCTION_DIR / f"{date_str}_inspect_data_health_daily_focus.json")]
    steps.append(run_step("inspect_data_health", inspect_cmd, timeout_s=60))

    # Step 11: strict JSON no NaN check (inline)
    strict_step = {"step": "strict_json_check", "command": "inline python", "started_at": now(), "returncode": 0}
    try:
        _df_path = DATA_DIR / "data_full.json"
        _df_txt = _df_path.read_text(encoding="utf-8-sig")
        if "NaN" in _df_txt or "Infinity" in _df_txt or "-Infinity" in _df_txt:
            strict_step["status"] = "BLOCK"
            strict_step["stdout_tail"] = ["BLOCK: NaN/Infinity found in data_full.json"]
            strict_step["returncode"] = 2
        else:
            _df = json.loads(_df_txt)
            _meta = _df.get("_Meta", {})
            strict_step["status"] = "PASS"
            strict_step["stdout_tail"] = [f"PASS: strict JSON, target_date={_meta.get('target_date','?')}"]
    except Exception as _e:
        strict_step["status"] = "BLOCK"
        strict_step["returncode"] = 2
        strict_step["stdout_tail"] = [f"BLOCK: {_e}"]
    strict_step["finished_at"] = now()
    steps.append(strict_step)

    # Step 13: archive_verify — 检查归档哈希
    av_step = {"step": "archive_verify", "command": "inline hash check", "started_at": now()}
    try:
        _am_path = ROOT / "历史数据" / "manifest" / f"{date_str}_archive_manifest.json"
        if _am_path.exists():
            _am = json.loads(_am_path.read_text(encoding="utf-8"))
            _mismatch = []
            for _f in _am.get("files", []):
                if _f.get("required") is False: continue
                if _f.get("status") != "PASS":
                    _mismatch.append(f"{_f.get('name')}: status={_f.get('status')}")
                _src = _f.get("source_sha256", "")
                _dst = _f.get("destination_sha256", "")
                if _src and _dst and _src != _dst:
                    _mismatch.append(f"{_f.get('name')}: hash mismatch")
            if _mismatch:
                av_step["status"] = "BLOCK"
                av_step["returncode"] = 2
                av_step["stdout_tail"] = _mismatch[:5]
            else:
                av_step["status"] = "PASS"
                av_step["returncode"] = 0
                av_step["stdout_tail"] = [f"archive_verify: {len(_am.get('files',[]))} files PASS"]
        else:
            av_step["status"] = "BLOCK"
            av_step["returncode"] = 2
            av_step["stdout_tail"] = [f"archive manifest not found: {_am_path}"]
    except Exception as _e:
        av_step["status"] = "BLOCK"
        av_step["returncode"] = 2
        av_step["stdout_tail"] = [f"archive_verify error: {_e}"]
    av_step["finished_at"] = now()
    steps.append(av_step)

    # Step 14: closure_verify — 总闸门
    cv_cmd = [PY, str(ROOT/"scripts"/"verify_daily_production_closure.py"), "--date", date_str,
              "--json-output", str(PRODUCTION_DIR / f"{date_str}_closure_verify.json"),
              "--pipeline-internal"]
    steps.append(run_step("closure_verify", cv_cmd, timeout_s=30))

    # 汇总 — 拆分 data_ready / report_ready / archive_ready / quality_ready / closure_ready
    data_steps_names = {"tushare_sync", "build_dynamic_pool", "batch_data_collector", "scoring_engine",
                        "nan_cleanup_and_meta", "materialize_cache"}
    data_ready = all(s["status"] == "PASS" for s in steps if s["step"] in data_steps_names)
    # report_ready 必须 only 认 report_promote PASS（含 release gate 前置条件）
    report_ready = any(s["status"] == "PASS" for s in steps if s["step"] == "report_promote")
    archive_ready = any(s["status"] == "PASS" for s in steps if s["step"] == "archive")
    av_ready = any(s["status"] == "PASS" for s in steps if s["step"] == "archive_verify")
    canonical_ready = True if args.skip_report else all(
        any(s["step"] == step and s["status"] == "PASS" for s in steps)
        for step in ["canonical_shadow_build", "canonical_shadow_gate"]
    )

    dq_status = next((s["status"] for s in steps if s["step"] == "data_quality_gate"), "BLOCK")
    dc_status = next((s["status"] for s in steps if s["step"] == "data_chain_health"), "BLOCK")
    isp_status = next((s["status"] for s in steps if s["step"] == "inspect_data_health"), "BLOCK")
    sj_status = next((s["status"] for s in steps if s["step"] == "strict_json_check"), "BLOCK")
    all_quality_pass = all(s == "PASS" for s in [dq_status, dc_status, isp_status, sj_status])
    quality_ready = "PASS" if all_quality_pass else "BLOCK"

    cv_status = next((s["status"] for s in steps if s["step"] == "closure_verify"), "BLOCK")
    closure_ready = "PASS" if cv_status == "PASS" else "BLOCK"

    # Build status_split dict
    status_split = {
        "data_ready": "PASS" if data_ready else "BLOCK",
        "report_ready": "PASS" if report_ready else "BLOCK",
        "release_gate_ready": next((s["status"] for s in steps if s["step"] == "release_gate"), "BLOCK"),
        "canonical_ready": "PASS" if canonical_ready else "BLOCK",
        "archive_ready": "PASS" if archive_ready else "BLOCK",
        "quality_ready": quality_ready,
        "closure_ready": closure_ready,
    }

    # overall = PASS only when ALL status_split items are "PASS"
    all_pass = all(v == "PASS" for v in status_split.values())
    all_pass = all_pass and (True if args.skip_report else canonical_ready)
    # Also check that SKIP items (from skip_report) are accounted for — they're already PASS in the check above
    if args.skip_report:
        # When skip_report is set, report_ready/canonical_ready are not required
        ov_report_checks = {k: v for k, v in status_split.items()
                            if k not in ("report_ready", "canonical_ready", "release_gate_ready")}
        all_pass = all(v == "PASS" for v in ov_report_checks.values())

    manifest = {
        "flow": "run_daily_production_pipeline",
        "date": date_str,
        "run_at": now(),
        "overall": "PASS" if all_pass else "BLOCK",
        "dry_run": args.dry_run,
        "steps": steps,
        "status_split": status_split,
    }

    # 写 ready.json — 仅当 manifest overall == PASS 才 ready:true
    ready_path = STATUS_DIR / f"{date_str}.ready.json"
    overall_pass = (manifest["overall"] == "PASS")
    ready_data = {
        "date": date_str,
        "ready": overall_pass,
        "ready_at": now(),
        "pipeline_status": manifest["overall"],
        "data_ready": "PASS" if data_ready else "BLOCK",
        "report_ready": "SKIP" if args.skip_report else ("PASS" if report_ready else "BLOCK"),
        "archive_ready": "PASS" if archive_ready else "BLOCK",
        "canonical_ready": "SKIP" if args.skip_report else ("PASS" if canonical_ready else "BLOCK"),
        "quality_ready": quality_ready,
        "closure_ready": closure_ready,
        "blocker": [s["step"] for s in steps if s["status"] == "BLOCK"]
    }
    if not args.dry_run:
        with open(ready_path, "w") as f:
            json.dump(ready_data, f, ensure_ascii=False, indent=2)

    # 写 manifest
    manifest_path = PRODUCTION_DIR / f"{date_str}_manifest.json"
    if not args.dry_run:
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

    # 检查 data_full trade_date
    data_full_path = DATA_DIR / "data_full.json"
    trade_date_ok = False
    if data_full_path.exists():
        try:
            with open(data_full_path, encoding="utf-8-sig") as f:
                df = json.load(f)
            meta = df.get("_Meta", df.get("meta", {}))
            actual = str(meta.get("trade_date", "")).replace("-", "")[:8]
            expected = date_str.replace("-", "")[:8]
            trade_date_ok = (actual == expected)
            if not trade_date_ok:
                print(f"[WARN] data_full trade_date={actual}, expected={expected}")
        except Exception as e:
            print(f"[WARN] data_full 读取失败: {e}")

    # === Post-write non-pipeline-internal closure verification ===
    # This runs AFTER manifest/ready are written, so closure_verify
    # can check the full external-ready state without the --pipeline-internal skip.
    # If this fails, downgrade overall and re-write manifest/ready.
    if not args.dry_run:
        cv_post_cmd = [PY, str(ROOT/"scripts"/"verify_daily_production_closure.py"),
                       "--date", date_str]
        try:
            cv_post_proc = subprocess.run(
                cv_post_cmd, capture_output=True, text=True, timeout=30,
                cwd=str(ROOT), env=subprocess_env()
            )
            cv_post_rc = cv_post_proc.returncode
            if cv_post_rc != 0:
                print(f"[BLOCK] Post-write closure verify FAILED (rc={cv_post_rc})")
                for line in (cv_post_proc.stdout or "").split("\n")[-5:]:
                    if line.strip(): print(f"  {line.strip()}")
                # Downgrade overall to BLOCK
                manifest["overall"] = "BLOCK"
                ready_data["ready"] = False
                ready_data["pipeline_status"] = "BLOCK"
                ready_data["closure_ready"] = "BLOCK"
                # Re-write manifest and ready with downgraded status
                with open(manifest_path, "w") as f:
                    json.dump(manifest, f, ensure_ascii=False, indent=2)
                with open(ready_path, "w") as f:
                    json.dump(ready_data, f, ensure_ascii=False, indent=2)
                overall_pass = False
            else:
                print(f"[OK] Post-write closure verify PASS")
        except Exception as e:
                print(f"[BLOCK] Post-write closure verify exception: {e}")
                manifest["overall"] = "BLOCK"
                ready_data["ready"] = False
                ready_data["pipeline_status"] = "BLOCK"
                ready_data["closure_ready"] = "BLOCK"
                if "blocker" in ready_data and isinstance(ready_data["blocker"], list):
                    ready_data["blocker"].append("post_write_closure_verify_exception")
                # Re-write manifest and ready with downgraded status
                try:
                    with open(manifest_path, "w") as f:
                        json.dump(manifest, f, ensure_ascii=False, indent=2)
                    with open(ready_path, "w") as f:
                        json.dump(ready_data, f, ensure_ascii=False, indent=2)
                except OSError:
                    pass
                overall_pass = False

    # 输出
    output = {
        "date": date_str,
        "overall": manifest["overall"],
        "steps_summary": {s["step"]: s["status"] for s in steps},
        "trade_date_ok": trade_date_ok,
        "ready_json": str(ready_path),
        "manifest_json": str(manifest_path),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))

    sys.exit(0 if overall_pass else 2)

if __name__ == "__main__":
    main()
