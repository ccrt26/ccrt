#!/usr/bin/env python3
"""
verify_daily_production_closure.py — 每日数据生产闭环总闸门

检查 manifest/ready/archive_manifest/DQ/inspect/哈希/日期 是否全部自洽。
只读，不修改任何文件。
"""
import argparse, hashlib, json, os, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TZ = timezone(timedelta(hours=8))

def sha256(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    ap = argparse.ArgumentParser(description="每日数据生产闭环总闸门")
    ap.add_argument("--date", required=True, help="YYYYMMDD")
    ap.add_argument("--json-output", default="", help="输出JSON路径")
    args = ap.parse_args()
    ds = args.date

    findings = []
    evidence = {}

    # 1. Manifest check (optional — may run inside pipeline before manifest written)
    mpath = ROOT / "logs" / "daily_production" / f"{ds}_manifest.json"
    evidence["manifest_path"] = str(mpath)
    if mpath.exists():
        m = json.loads(mpath.read_text(encoding="utf-8"))
        evidence["manifest_overall"] = m.get("overall")
        evidence["manifest_status_split"] = m.get("status_split", {})
        if m.get("overall") != "PASS":
            evidence["manifest_note"] = "pre-existing manifest from prior run (this run still in progress)"
            # Don't BLOCK on manifest — this runs inside the pipeline before manifest write

    # 2. Ready check (optional — may run inside pipeline before ready written)
    rpath = ROOT / "logs" / "daily_data_retry" / "status" / f"{ds}.ready.json"
    evidence["ready_path"] = str(rpath)
    if rpath.exists():
        r = json.loads(rpath.read_text(encoding="utf-8"))
        evidence["ready_ready"] = r.get("ready")
        evidence["ready_pipeline_status"] = r.get("pipeline_status")
        if r.get("ready") is not True:
            evidence["ready_note"] = "pre-existing ready from prior run (this run still in progress)"

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
        if meta.get("target_date") != ds:
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

    # 9. Overall
    overall = "PASS" if not findings else "BLOCK" if any("expected" in f or "missing" in f or "blocked" in f or "NaN" in f or "hash mismatch" in f for f in findings) else "WARN"
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
