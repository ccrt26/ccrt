#!/usr/bin/env python3
import json
import sqlite3
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "代码文件/数据"
DB = DATA / "l2_cache/l2_cache.db"

def read_json(path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))

def rows_from_kline_cache():
    src = DATA / "kline_cache"
    rows = []
    if not src.exists():
        return rows
    for p in sorted(src.glob("*.json")):
        code = p.stem
        payload = read_json(p)
        records = payload.get("data") if isinstance(payload, dict) else payload
        if not isinstance(records, list):
            continue
        for item in records:
            if not isinstance(item, dict):
                continue
            trade_date = item.get("date") or item.get("trade_date") or item.get("day")
            close = item.get("close") or item.get("KClose")
            if not trade_date or close is None:
                continue
            rows.append({
                "code": code,
                "trade_date": str(trade_date),
                "open": item.get("open"),
                "high": item.get("high"),
                "low": item.get("low"),
                "close": close,
                "volume": item.get("volume"),
                "amount": item.get("amount") or 0,
                "source_path": str(p),
            })
    return rows

def main():
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("""
    CREATE TABLE IF NOT EXISTS kline (
      code TEXT NOT NULL,
      trade_date TEXT NOT NULL,
      open REAL,
      high REAL,
      low REAL,
      close REAL,
      volume INTEGER,
      amount REAL,
      adjust_flag TEXT NOT NULL DEFAULT 'forward',
      source_tier TEXT NOT NULL DEFAULT 'L1',
      source_path TEXT,
      quality_flag TEXT NOT NULL DEFAULT 'unknown',
      quality_reason TEXT,
      checksum TEXT,
      created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
      updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
      PRIMARY KEY(code, trade_date, adjust_flag)
    )
    """)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = rows_from_kline_cache()
    for r in rows:
        con.execute("""
        INSERT OR REPLACE INTO kline(
          code, trade_date, open, high, low, close, volume, amount,
          adjust_flag, source_tier, source_path, quality_flag, quality_reason, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'forward', 'L1', ?, 'pending_review', 'local_kline_cache bootstrap', ?)
        """, (
            r["code"], r["trade_date"], r["open"], r["high"], r["low"], r["close"],
            r["volume"], r["amount"], r["source_path"], now
        ))
    con.commit()
    total = con.execute("SELECT COUNT(*) FROM kline").fetchone()[0]
    con.close()
    meta = {
        "updated_at": now,
        "rows_loaded": len(rows),
        "kline_total": total,
        "target_table": "kline",
        "source": "local_kline_cache",
        "quality_flag": "pending_review"
    }
    (DATA / "l2_cache/last_update.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"PASS build_l2_cache target=kline rows_loaded={len(rows)} total={total}")

if __name__ == "__main__":
    main()
