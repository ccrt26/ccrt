#!/usr/bin/env python3
import argparse
import gzip
import json
import shutil
import sqlite3
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "代码文件/数据"
DB = DATA / "l2_cache/l2_cache.db"
REG = ROOT / "00_项目地基/02_权威注册表/capability_registry.json"

def _release_state():
    try:
        r = json.loads(REG.read_text(encoding="utf-8"))
        return r.get("capabilities", {}).get("C-D04-0001", {}).get("release_state", "unknown")
    except Exception:
        return "unknown"

def table_count(con, table):
    return con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

def health_check():
    issues = []
    metrics = {}
    if not DB.exists():
        issues.append("missing l2_cache.db")
    else:
        con = sqlite3.connect(DB)
        try:
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "kline" not in tables:
                issues.append("missing kline table")
            else:
                metrics["kline_rows"] = table_count(con, "kline")
                metrics["kline_quality_rows"] = con.execute(
                    "SELECT COUNT(*) FROM kline WHERE quality_flag IS NOT NULL AND source_tier IS NOT NULL"
                ).fetchone()[0]
                if metrics["kline_rows"] <= 0:
                    issues.append("kline empty")
                if metrics["kline_quality_rows"] <= 0:
                    issues.append("kline missing quality/source metadata")
            if "score_history" in tables:
                metrics["score_history_rows"] = table_count(con, "score_history")
        finally:
            con.close()

    status = "PASS" if not issues else "BLOCK"
    payload = {
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "issues": issues,
        "metrics": metrics,
        "target_table": "kline",
        "release_state": _release_state()
    }
    (DATA / "l2_cache/health.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{status} D04 health_check target=kline issues={issues} metrics={metrics}")
    return 0 if not issues else 1

def backup_db():
    if not DB.exists():
        print("BLOCK missing db")
        return 1
    out = DATA / "l2_cache/backup" / f"l2_cache_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db.gz"
    out.parent.mkdir(parents=True, exist_ok=True)
    with DB.open("rb") as f_in, gzip.open(out, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)
    print(f"PASS backup {out}")
    return 0

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--health-check", action="store_true")
    ap.add_argument("--backup", action="store_true")
    args = ap.parse_args()
    if args.backup:
        return backup_db()
    return health_check()

if __name__ == "__main__":
    raise SystemExit(main())
