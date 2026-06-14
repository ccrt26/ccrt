#!/usr/bin/env python3
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "代码文件/数据"
REG = ROOT / "00_项目地基/02_权威注册表/capability_registry.json"

class UnifiedDataSource:
    capability_id = "C-D04-0001"

    def __init__(self, data_dir=None):
        self.data_dir = Path(data_dir) if data_dir else DATA
        self.db = self.data_dir / "l2_cache/l2_cache.db"

    def load_l1_snapshot(self, name="data_full.json"):
        p = self.data_dir / name
        if not p.exists():
            return {"quality_flag": "invalid", "data": None, "source": str(p)}
        return {"quality_flag": "complete", "data": json.loads(p.read_text(encoding="utf-8")), "source": str(p)}

    def get_kline(self, code, limit=250):
        if not self.db.exists():
            return []
        con = sqlite3.connect(self.db)
        con.row_factory = sqlite3.Row
        try:
            rows = con.execute("""
              SELECT code, trade_date, open, high, low, close, volume, amount,
                     adjust_flag, source_tier, source_path, quality_flag, quality_reason, updated_at
              FROM kline
              WHERE code = ?
              ORDER BY trade_date DESC
              LIMIT ?
            """, (str(code), int(limit))).fetchall()
        finally:
            con.close()
        return [dict(r) for r in rows]

    def get_score_history(self, code, limit=250):
        if not self.db.exists():
            return []
        con = sqlite3.connect(self.db)
        con.row_factory = sqlite3.Row
        try:
            rows = con.execute("""
              SELECT code, trade_date, score_type, score, source_tier, source_path,
                     quality_flag, quality_reason, updated_at
              FROM score_history
              WHERE code = ?
              ORDER BY trade_date DESC
              LIMIT ?
            """, (str(code), int(limit))).fetchall()
        finally:
            con.close()
        return [dict(r) for r in rows]

    def health(self):
        if not self.db.exists():
            return {"status": "BLOCK", "issues": ["missing l2_cache.db"]}
        release_state = "unknown"
        try:
            r = json.loads(REG.read_text(encoding="utf-8"))
            release_state = r.get("capabilities", {}).get("C-D04-0001", {}).get("release_state", "unknown")
        except Exception:
            pass
        issues = []
        con = sqlite3.connect(self.db)
        try:
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "kline" not in tables:
                issues.append("missing kline table")
                kline_rows = 0
                quality_rows = 0
            else:
                kline_rows = con.execute("SELECT COUNT(*) FROM kline").fetchone()[0]
                quality_rows = con.execute(
                    "SELECT COUNT(*) FROM kline WHERE quality_flag IS NOT NULL AND source_tier IS NOT NULL"
                ).fetchone()[0]
                if kline_rows <= 0:
                    issues.append("kline empty")
                if quality_rows <= 0:
                    issues.append("kline missing quality/source metadata")
        finally:
            con.close()
        return {
            "status": "PASS" if not issues else "BLOCK",
            "issues": issues,
            "kline_rows": kline_rows,
            "kline_quality_rows": quality_rows,
            "target_table": "kline",
            "release_state": release_state
        }

if __name__ == "__main__":
    ds = UnifiedDataSource()
    print(json.dumps(ds.health(), ensure_ascii=False, indent=2))
