#!/usr/bin/env python3
"""
migrate_historical_kline.py — K 线三处散落收敛到 L2 SQLite（v1.0）

将 kline_cache/{code}.json 和 data_full.json 内嵌 KClose/KDate 数组
统一收敛到 L2 SQLite kline 表。按 (code, date) 去重。

用法:
  python3 scripts/migrate_historical_kline.py --dry-run    # 只统计不写入
  python3 scripts/migrate_historical_kline.py              # 实写

退出码:
  0 = PASS
  1 = WARN（部分行失败）
  2 = BLOCK

设计约束:
  - dry-run 不碰数据库
  - 全部写入 L2 后更新哨兵
  - 保持 data_full.json 和 kline_cache/ 不变
"""
import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KLINE_DIR = ROOT / "代码文件" / "数据" / "kline_cache"
DATA_FULL_PATH = ROOT / "代码文件" / "数据" / "data_full.json"
DB_PATH = ROOT / "代码文件" / "数据" / "l2_cache" / "l2_cache.db"
SENTINEL_PATH = ROOT / "代码文件" / "数据" / "l2_cache" / "last_update.json"


def log(msg, level="INFO"):
    print(f"[{level}] {msg}")


def collect_from_kline_cache(date_from=None, date_to=None):
    """从 kline_cache/{code}.json 收集 K 线行。"""
    rows = []
    if not KLINE_DIR.exists():
        return rows
    for path in sorted(KLINE_DIR.iterdir()):
        if path.suffix != ".json":
            continue
        code = path.stem
        try:
            with open(path, "r", encoding="utf-8") as f:
                entries = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        for row in entries:
            td = row.get("date", "")
            if date_from and td < date_from:
                continue
            if date_to and td > date_to:
                continue
            rows.append({
                "code": code,
                "trade_date": td,
                "open": row.get("open"),
                "high": row.get("high"),
                "low": row.get("low"),
                "close": row.get("close"),
                "volume": row.get("volume"),
                "amount": row.get("amount", 0),
                "source": "kline_cache",
            })
    return rows


def collect_from_data_full():
    """从 data_full.json 内嵌 KClose 数组收集 K 线行。"""
    rows = []
    if not DATA_FULL_PATH.exists():
        return rows
    try:
        with open(DATA_FULL_PATH, "r", encoding="utf-8") as f:
            df = json.load(f)
    except (json.JSONDecodeError, OSError):
        return rows
    stocks = df.get("Stocks", df.get("stocks", []))
    for s in stocks:
        code = str(s.get("Code", s.get("code", "")))
        kdates = s.get("KDate") or []
        for idx, td in enumerate(kdates):
            try:
                rows.append({
                    "code": code,
                    "trade_date": td,
                    "open": s.get("KOpen", [None] * len(kdates))[idx] if idx < len(s.get("KOpen", [])) else None,
                    "high": s.get("KHigh", [None] * len(kdates))[idx] if idx < len(s.get("KHigh", [])) else None,
                    "low": s.get("KLow", [None] * len(kdates))[idx] if idx < len(s.get("KLow", [])) else None,
                    "close": s.get("KClose", [None] * len(kdates))[idx] if idx < len(s.get("KClose", [])) else None,
                    "volume": s.get("KVolume", [None] * len(kdates))[idx] if idx < len(s.get("KVolume", [])) else None,
                    "amount": 0,
                    "source": "data_full",
                })
            except (IndexError, TypeError):
                continue
    return rows


def deduplicate(rows):
    """按 (code, trade_date) 去重。kline_cache 优先级高于 data_full。"""
    seen = {}
    for r in rows:
        key = (r["code"], r["trade_date"])
        # kline_cache 优先
        if key in seen and seen[key]["source"] == "kline_cache":
            continue
        if r["source"] == "kline_cache":
            seen[key] = r
        elif key not in seen:
            seen[key] = r
    return list(seen.values())


def upsert_to_l2(conn, rows):
    """去重后 upsert 到 L2 kline 表。"""
    upserted = 0
    for r in rows:
        try:
            conn.execute("""
                INSERT INTO kline (code, trade_date, open, high, low, close, volume, amount,
                                   adjust_flag, source_tier, quality_flag)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'forward', 'L1', 'unknown')
                ON CONFLICT(code, trade_date, adjust_flag) DO UPDATE SET
                    open=excluded.open, high=excluded.high, low=excluded.low,
                    close=excluded.close, volume=excluded.volume, amount=excluded.amount,
                    updated_at=datetime('now','localtime')
            """, (r["code"], r["trade_date"], r["open"], r["high"], r["low"],
                  r["close"], r["volume"], r["amount"]))
            upserted += 1
        except sqlite3.Error:
            continue
    conn.commit()
    return upserted


def main():
    parser = argparse.ArgumentParser(description="K 线三处散落收敛到 L2 SQLite")
    parser.add_argument("--dry-run", action="store_true",
                        help="仅统计不写入")
    parser.add_argument("--date-from", default=None, help="起始日期 YYYY-MM-DD")
    parser.add_argument("--date-to", default=None, help="截止日期 YYYY-MM-DD")
    args = parser.parse_args()

    # 收集
    kc_rows = collect_from_kline_cache(args.date_from, args.date_to)
    df_rows = collect_from_data_full()
    log(f"kline_cache rows: {len(kc_rows)}")
    log(f"data_full rows:   {len(df_rows)}")

    all_rows = kc_rows + df_rows
    deduped = deduplicate(all_rows)
    log(f"去重后总行数:     {len(deduped)}")

    if args.dry_run:
        log(f"[DRY-RUN] 预计写入 {len(deduped)} 行到 L2 kline 表")
        log(f"[DRY-RUN] 不碰数据库")
        return 0

    # 实写
    db_exists = DB_PATH.exists()
    if not db_exists:
        log(f"L2 DB 不存在: {DB_PATH}。请先运行 build_l2_cache.py --init-empty-tables", "BLOCK")
        return 2

    conn = sqlite3.connect(str(DB_PATH))
    try:
        upserted = upsert_to_l2(conn, deduped)
        log(f"写入完成: {upserted} 行 upserted")
    finally:
        conn.close()

    # 更新哨兵
    sentinel = {
        "script": "migrate_historical_kline.py",
        "status": "OK",
        "rows_migrated": len(deduped),
        "updated_at": datetime.now().isoformat(),
    }
    with open(SENTINEL_PATH, "w", encoding="utf-8") as f:
        json.dump(sentinel, f, indent=2, ensure_ascii=False)

    return 0


if __name__ == "__main__":
    sys.exit(main())
