#!/usr/bin/env python3
import json
import sqlite3
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "代码文件/数据"
DB = DATA / "l2_cache/l2_cache.db"

def main():
    src = DATA / "score_history.jsonl"
    rows = []
    if src.exists():
        for line in src.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            code = item.get("code")
            trade_date = item.get("date") or item.get("trade_date")
            score = item.get("TotalScore") or item.get("score")
            if code and trade_date and score is not None:
                rows.append((str(code), str(trade_date), "daily", float(score), json.dumps(item, ensure_ascii=False)))

    con = sqlite3.connect(DB)
    con.execute("""
    CREATE TABLE IF NOT EXISTS score_history (
      code TEXT NOT NULL,
      trade_date TEXT NOT NULL,
      score_type TEXT NOT NULL DEFAULT 'daily',
      score REAL,
      rank INTEGER,
      bucket TEXT,
      source_tier TEXT NOT NULL DEFAULT 'L3',
      source_path TEXT,
      quality_flag TEXT NOT NULL DEFAULT 'unknown',
      quality_reason TEXT,
      raw_json TEXT,
      created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
      updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
      PRIMARY KEY(code, trade_date, score_type)
    )
    """)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for code, trade_date, score_type, score, raw_json in rows:
        con.execute("""
        INSERT OR REPLACE INTO score_history(
          code, trade_date, score_type, score, source_tier, source_path,
          quality_flag, quality_reason, raw_json, updated_at
        )
        VALUES (?, ?, ?, ?, 'L3', ?, 'pending_review', 'rebuilt from score_history.jsonl', ?, ?)
        """, (code, trade_date, score_type, score, str(src), raw_json, now))
    con.commit()
    total = con.execute("SELECT COUNT(*) FROM score_history").fetchone()[0]
    con.close()

    out = DATA / "l2_cache/score_history_index.json"
    out.write_text(json.dumps({
        "rebuilt_at": now,
        "source": str(src.relative_to(ROOT)),
        "rows_loaded": len(rows),
        "score_history_total": total,
        "target_table": "score_history"
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"PASS rebuild_score_history target=score_history rows_loaded={len(rows)} total={total}")

if __name__ == "__main__":
    main()
