#!/usr/bin/env python3
"""
run_daily_production_pipeline.py — 每日数据生产闭环入口 v1.0

串联：token加载 → tushare同步 → 数据采集 → 评分 → 物料化 → 日报 → 归档 → ready

用法:
  python3 scripts/run_daily_production_pipeline.py --date 20260612
  python3 scripts/run_daily_production_pipeline.py --date 20260612 --dry-run
"""
import argparse, json, os, subprocess, sys, time, traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TZ_SHANGHAI = timezone(timedelta(hours=8))
PRODUCTION_DIR = ROOT / "logs" / "daily_production"
STATUS_DIR = ROOT / "logs" / "daily_data_retry" / "status"
DATA_DIR = ROOT / "代码文件" / "数据"
HISTORY_DIR = ROOT / "历史数据"
MANIFEST_DIR = ROOT / "历史数据" / "manifest"
TOKEN_FILE = Path.home() / ".ccrt" / "tielv.env"

def now():
    return datetime.now(TZ_SHANGHAI).isoformat()

def load_token():
    """加载 TUSHARE_TOKEN：环境变量优先，再读私有文件"""
    token = os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        if TOKEN_FILE.exists():
            with open(TOKEN_FILE) as f:
                for line in f:
                    if line.startswith("TUSHARE_TOKEN="):
                        token = line.split("=", 1)[1].strip()
                        break
    if not token:
        return None, "missing_runtime_env:TUSHARE_TOKEN"
    os.environ["TUSHARE_TOKEN"] = token
    return token, None

def run_step(name, cmd, cwd=None, timeout_s=120):
    """运行一步并返回执行记录"""
    started = now()
    step = {"step": name, "command": " ".join(str(c) for c in cmd), "started_at": started}
    try:
        r = subprocess.run(cmd, cwd=str(cwd or ROOT), capture_output=True, text=True, timeout=timeout_s)
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
        print(json.dumps({
            "flow": "run_daily_production_pipeline",
            "date": date_str,
            "dry_run": True,
            "would_run": planned_steps,
            "would_write": [],
            "guarantee": "dry-run returns before token loading, subprocess execution, ready/manifest writes, data/archive/report writes"
        }, ensure_ascii=False, indent=2))
        return 0

    os.makedirs(PRODUCTION_DIR, exist_ok=True)
    os.makedirs(STATUS_DIR, exist_ok=True)
    os.makedirs(MANIFEST_DIR, exist_ok=True)

    # Step 0: 加载 token
    token, err = load_token()
    if err:
        print(json.dumps({"flow": "run_daily_production_pipeline", "date": date_str, "error": err}, ensure_ascii=False))
        sys.exit(2)

    steps = []

    # Step 1: tushare 历史数据同步
    steps.append(run_step("tushare_sync", [PY, str(ROOT/"代码文件"/"tools"/"tushare_history_sync.py"), "--daily"], timeout_s=180))

    # Step 2: 动态池构建
    steps.append(run_step("build_dynamic_pool", [PY, str(ROOT/"代码文件"/"每日荐股"/"scripts"/"build_dynamic_pool.py")], timeout_s=30))

    # Step 3: batch_data_collector（含增量K线，带 --date）
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

    # Step 6: 日报生成（可选）
    if not args.skip_report:
        report_cmd = [PY, str(ROOT/"scripts"/"run_daily_report_html_only.py"), "--date", date_str, "--write"]
        report_step = run_step("daily_report", report_cmd, timeout_s=300)
        steps.append(report_step)

        if report_step.get("status") == "PASS":
            shadow_dir = ROOT / "logs" / "canonical_shadow" / date_str
            steps.append(run_step(
                "canonical_shadow_build",
                [PY, str(ROOT/"scripts"/"build_canonical_report.py"), "--all", "--date", date_str, "--out-dir", str(shadow_dir)],
                timeout_s=120
            ))
            steps.append(run_step(
                "canonical_shadow_gate",
                [PY, str(ROOT/"scripts"/"check_canonical_report_shadow.py"), "--all", "--date", date_str, "--canonical-dir", str(shadow_dir), "--json"],
                timeout_s=120
            ))
        else:
            steps.append({
                "step": "canonical_shadow_build",
                "command": "SKIP: daily_report not PASS",
                "started_at": now(),
                "finished_at": now(),
                "duration_sec": 0,
                "returncode": 0,
                "status": "SKIP",
                "stdout_tail": ["daily_report not PASS"],
                "stderr_tail": [],
                "output_files": []
            })
            steps.append({
                "step": "canonical_shadow_gate",
                "command": "SKIP: daily_report not PASS",
                "started_at": now(),
                "finished_at": now(),
                "duration_sec": 0,
                "returncode": 0,
                "status": "SKIP",
                "stdout_tail": ["daily_report not PASS"],
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
              "--json-output", str(PRODUCTION_DIR / f"{date_str}_closure_verify.json")]
    steps.append(run_step("closure_verify", cv_cmd, timeout_s=30))

    # 汇总 — 拆分 data_ready / report_ready / archive_ready / quality_ready / closure_ready
    data_steps_names = {"tushare_sync", "build_dynamic_pool", "batch_data_collector", "scoring_engine",
                        "nan_cleanup_and_meta", "materialize_cache"}
    data_ready = all(s["status"] == "PASS" for s in steps if s["step"] in data_steps_names)
    report_ready = any(s["status"] == "PASS" for s in steps if s["step"] == "daily_report")
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

    all_pass = data_ready and report_ready and archive_ready and av_ready and canonical_ready and (quality_ready == "PASS") and (closure_ready == "PASS")
    manifest = {
        "flow": "run_daily_production_pipeline",
        "date": date_str,
        "run_at": now(),
        "overall": "PASS" if all_pass else "WARN" if any(s["status"] == "WARN" for s in steps) else "BLOCK",
        "dry_run": args.dry_run,
        "steps": steps,
        "status_split": {
            "data_ready": "PASS" if data_ready else "BLOCK",
            "report_ready": "PASS" if report_ready else "BLOCK",
            "archive_ready": "PASS" if archive_ready else "BLOCK",
            "canonical_ready": "PASS" if canonical_ready else "BLOCK",
            "quality_ready": quality_ready,
            "closure_ready": closure_ready,
        }
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

    sys.exit(0 if all_pass else (2 if manifest["overall"] == "BLOCK" else 1))

if __name__ == "__main__":
    main()
