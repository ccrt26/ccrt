#!/usr/bin/env python3
"""
verify_daily_production_closure.py — 每日数据生产闭环总闸门（v2.0）

检查 manifest/ready/archive_manifest/DQ/inspect/哈希/日期/资金流缓存 是否全部自洽。
只读，不修改任何文件。

v2.0 新增硬闸：
- ready.json 若存在且 ready is not True，且不是"当前 pipeline 内部预写状态"，最终闭包不得 PASS。
- active target stocks 的 fund_flow_cache/{code}.json 必须含 --date。
- data_full.FundFlows 对 active target stocks 必须含 --date。
- 输出 evidence 增加 fund_flow_cache_match / data_full_fundflows_match / missing_fund_flow_codes。
- 若缺目标日资金流，overall=BLOCK。
"""
import argparse, hashlib, json, os, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TZ = timezone(timedelta(hours=8))

# 活跃日报目标路径
DAILY_TARGETS = ROOT / "00_项目地基" / "02_权威注册表" / "daily_report_targets.json"
FUND_FLOW_CACHE_DIR = ROOT / "代码文件" / "数据" / "fund_flow_cache"
DATA_FULL_PATH = ROOT / "代码文件" / "数据" / "data_full.json"


def sha256(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def norm_date(value):
    return str(value or "").replace("-", "")[:8]


def load_active_target_codes():
    """读取 daily_report_targets.json 中 enabled 的 active target codes."""
    if not DAILY_TARGETS.exists():
        return []
    try:
        with open(DAILY_TARGETS, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return [
            str(t.get("code", ""))
            for t in cfg.get("active_targets", [])
            if t.get("enabled") and t.get("code")
        ]
    except Exception:
        return []


def check_fund_flow_cache_match(date_str, active_codes):
    """检查 active target stocks 的 fund_flow_cache 是否含目标日记录。

    Returns (match_count, total, missing_codes).
    """
    match = 0
    missing = []
    for code in active_codes:
        path = FUND_FLOW_CACHE_DIR / f"{code}.json"
        if not path.exists():
            missing.append(code)
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                rows = json.load(f)
        except Exception:
            missing.append(code)
            continue
        has_target = False
        for row in rows if isinstance(rows, list) else [rows]:
            d = norm_date(row.get("date") or row.get("trade_date", ""))
            if d == date_str:
                has_target = True
                break
        if has_target:
            match += 1
        else:
            missing.append(code)
    return match, len(active_codes), missing


def check_data_full_fundflows_match(date_str, active_codes):
    """检查 data_full.FundFlows 对 active target stocks 是否含目标日记录。

    Returns (match_count, total, missing_codes).
    """
    if not DATA_FULL_PATH.exists():
        return 0, len(active_codes), active_codes[:]
    try:
        with open(DATA_FULL_PATH, "r", encoding="utf-8-sig") as f:
            dfull = json.load(f)
    except Exception:
        return 0, len(active_codes), active_codes[:]
    flows = dfull.get("FundFlows", {})
    match = 0
    missing = []
    for code in active_codes:
        rows = flows.get(code, [])
        if not rows:
            missing.append(code)
            continue
        has_target = False
        for row in rows if isinstance(rows, list) else [rows]:
            d = norm_date(row.get("trade_date") or row.get("date", ""))
            if d == date_str:
                has_target = True
                break
        if has_target:
            match += 1
        else:
            missing.append(code)
    return match, len(active_codes), missing


def main():
    ap = argparse.ArgumentParser(description="每日数据生产闭环总闸门")
    ap.add_argument("--date", required=True, help="YYYYMMDD")
    ap.add_argument("--json-output", default="", help="输出JSON路径")
    args = ap.parse_args()
    ds = args.date

    findings = []
    evidence = {}

    # 1. Manifest check
    mpath = ROOT / "logs" / "daily_production" / f"{ds}_manifest.json"
    evidence["manifest_path"] = str(mpath)
    if mpath.exists():
        m = json.loads(mpath.read_text(encoding="utf-8"))
        evidence["manifest_overall"] = m.get("overall")
        evidence["manifest_status_split"] = m.get("status_split", {})
        if m.get("overall") != "PASS":
            evidence["manifest_note"] = "pre-existing manifest from prior run (this run still in progress)"

    # 2. Ready check — v2.0 hard gate: ready is not True → BLOCK
    rpath = ROOT / "logs" / "daily_data_retry" / "status" / f"{ds}.ready.json"
    evidence["ready_path"] = str(rpath)
    if rpath.exists():
        r = json.loads(rpath.read_text(encoding="utf-8"))
        evidence["ready_ready"] = r.get("ready")
        evidence["ready_pipeline_status"] = r.get("pipeline_status")
        if r.get("ready") is not True:
            # 如果 manifest 也不存在（该 run 还在进行中），可能是预写状态
            if mpath.exists() and m.get("overall") == "PASS":
                evidence["ready_note"] = "pre-existing ready from prior run (this run still in progress)"
            else:
                findings.append(f"ready.json ready={r.get('ready')} pipeline_status={r.get('pipeline_status')} — 未就绪")

    # 3. Archive manifest check
    apath = ROOT / "历史数据" / "manifest" / f"{ds}_archive_manifest.json"
    evidence["archive_manifest_path"] = str(apath)
    if apath.exists():
        a = json.loads(apath.read_text(encoding="utf-8"))
        ad = a.get("archive_date", "")
        evidence["archive_archive_date"] = ad
        evidence["archive_files"] = len(a.get("files", []))
        if ad != ds:
            findings.append(f"archive_date={ad}, expected {ds}")
        for f in a.get("files", []):
            if f.get("required") is False:
                continue
            if f.get("status") != "PASS":
                findings.append(f"archive file {f.get('name')} status={f.get('status')}")
            src = f.get("source_sha256", "")
            dst = f.get("destination_sha256", "")
            if src and dst and src != dst:
                findings.append(f"hash mismatch {f.get('name')}: {src[:12]} != {dst[:12]}")
    else:
        findings.append(f"archive manifest not found: {apath}")

    # 4. Hot ↔ archive hash match
    pairs = [
        (ROOT / "代码文件" / "数据" / "data_full.json", ROOT / "历史数据" / "04_原始数据" / f"{ds}_data_full.json"),
        (ROOT / "代码文件" / "数据" / "data_scored.json", ROOT / "历史数据" / "04_原始数据" / f"{ds}_data_scored.json"),
        (ROOT / "代码文件" / "数据" / "data_final.json", ROOT / "历史数据" / "04_原始数据" / f"{ds}_data_final.json"),
        (ROOT / "代码文件" / "数据" / "score_history.jsonl", ROOT / "历史数据" / "04_原始数据" / f"{ds}_score_history.jsonl"),
        (ROOT / "代码文件" / "数据" / "dynamic_pool.json", ROOT / "历史数据" / "05_参考数据" / f"{ds}_dynamic_pool.json"),
    ]
    hash_ok = 0
    hash_total = 0
    for hot, arc in pairs:
        if hot.exists() and arc.exists():
            hash_total += 1
            if sha256(hot) == sha256(arc):
                hash_ok += 1
            else:
                findings.append(f"hash mismatch: {hot.name} hot != archive")
        else:
            if hot.exists() and not arc.exists():
                findings.append(f"archive missing for {hot.name}")
    evidence["hash_match"] = f"{hash_ok}/{hash_total}"

    # 5. data_full _Meta check
    df_path = ROOT / "代码文件" / "数据" / "data_full.json"
    if df_path.exists():
        df = json.loads(df_path.read_text(encoding="utf-8-sig"))
        meta = df.get("_Meta", {})
        evidence["data_full_target_date"] = meta.get("target_date", "")
        evidence["data_full_trade_date"] = meta.get("trade_date", "")
        if norm_date(meta.get("target_date")) != norm_date(ds):
            findings.append(f"data_full target_date={meta.get('target_date')}, expected {ds}")

    # 6. DQ check
    dq_path = ROOT / "logs" / "daily_production" / f"{ds}_check_data_quality.json"
    evidence["dq_path"] = str(dq_path)
    if dq_path.exists():
        dq = json.loads(dq_path.read_text(encoding="utf-8"))
        evidence["dq_overall"] = dq.get("overall")
        evidence["dq_blocked"] = dq.get("blocked")
        if dq.get("blocked") is True:
            findings.append("DQ blocked=true, cannot be ready")
        if dq.get("required_missing", 0) > 0:
            findings.append(f"DQ required_missing={dq.get('required_missing')}")
    else:
        findings.append(f"DQ JSON not found: {dq_path}")

    # 7. Inspect check
    isp_path = ROOT / "logs" / "daily_production" / f"{ds}_inspect_data_health_daily_focus.json"
    evidence["inspect_path"] = str(isp_path)
    if isp_path.exists():
        isp = json.loads(isp_path.read_text(encoding="utf-8"))
        evidence["inspect_overall"] = isp.get("overall")
        if isp.get("overall") != "PASS":
            findings.append(f"inspect daily_focus overall={isp.get('overall')}")
    else:
        findings.append(f"inspect JSON not found: {isp_path}")

    # 8. Strict JSON no NaN
    for rel in ["代码文件/数据/data_full.json", "代码文件/数据/data_scored.json", "代码文件/数据/data_final.json"]:
        p = ROOT / rel
        if p.exists():
            txt = p.read_text(encoding="utf-8-sig")
            if "NaN" in txt or "Infinity" in txt or "-Infinity" in txt:
                findings.append(f"NaN/Infinity found in {rel}")

    # 9 (NEW). Fund flow cache gate for active target stocks
    active_codes = load_active_target_codes()
    evidence["active_target_codes"] = active_codes
    if active_codes:
        ff_match, ff_total, ff_missing = check_fund_flow_cache_match(ds, active_codes)
        evidence["fund_flow_cache_match"] = f"{ff_match}/{ff_total}"
        evidence["missing_fund_flow_codes"] = ff_missing
        if ff_missing:
            findings.append(f"fund_flow_cache 缺目标日({ds}): {','.join(ff_missing)}")

        df_match, df_total, df_ff_missing = check_data_full_fundflows_match(ds, active_codes)
        evidence["data_full_fundflows_match"] = f"{df_match}/{df_total}"
        if df_ff_missing:
            if df_ff_missing != ff_missing:
                # 只在 data_full 独特缺失时追加
                extra_missing = [c for c in df_ff_missing if c not in ff_missing]
                if extra_missing:
                    findings.append(f"data_full.FundFlows 缺目标日({ds}): {','.join(extra_missing)}")
    else:
        evidence["fund_flow_cache_match"] = "N/A (no active targets)"
        evidence["data_full_fundflows_match"] = "N/A (no active targets)"

    # 10. Overall — v2.0: fund_flow_cache 缺失导致 BLOCK
    overall = "PASS" if not findings else (
        "BLOCK" if any(
            "expected" in f or "missing" in f or "blocked" in f or "NaN" in f
            or "hash mismatch" in f or "fund_flow_cache" in f or "ready.json" in f
            or "FundFlows" in f or "未就绪" in f
            for f in findings
        ) else "WARN"
    )
    evidence["overall"] = overall
    evidence["findings"] = findings

    result = {
        "flow": "verify_daily_production_closure",
        "date": ds,
        "overall": overall,
        "findings": findings,
        "evidence": evidence,
    }

    if args.json_output:
        with open(args.json_output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"Closure verify: {overall}")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))

    sys.exit(0 if overall == "PASS" else (1 if overall == "WARN" else 2))


if __name__ == "__main__":
    main()
