#!/usr/bin/env python3
"""
build_l2_cache.py — L2 SQLite 一次性构建脚本（v1.0）

创建 L2 历史分析缓存的 7 表 schema，并从 kline_cache 和 L3 归档加载历史数据。
支持 --dry-run 验证 schema plan 和预计 upsert 行数，不写 DB。

用法:
  python3 scripts/build_l2_cache.py --dry-run --init-empty-tables
  python3 scripts/build_l2_cache.py --init-empty-tables
  python3 scripts/build_l2_cache.py --dry-run --date-from 2026-01-01

退出码:
  0 = PASS
  1 = 部分失败
  2 = BLOCK（schema 创建失败）
"""
import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = ROOT / "代码文件" / "数据" / "l2_cache" / "l2_cache.db"
KLINE_DIR = ROOT / "代码文件" / "数据" / "kline_cache"
ARCHIVE_ROOT = ROOT / "历史数据" / "04_原始数据"
SENTINEL_PATH = ROOT / "代码文件" / "数据" / "l2_cache" / "last_update.json"


# ── Schema ─────────────────────────────────────────────────

SCHEMA_SQL = """
-- K 线历史（前复权）
CREATE TABLE IF NOT EXISTS kline (
    code          TEXT NOT NULL,
    trade_date    TEXT NOT NULL,
    open          REAL,
    high          REAL,
    low           REAL,
    close         REAL,
    volume        INTEGER,
    amount        REAL,
    adjust_flag   TEXT NOT NULL DEFAULT 'forward',
    source_tier   TEXT NOT NULL DEFAULT 'L1',
    source_path   TEXT,
    quality_flag  TEXT NOT NULL DEFAULT 'unknown',
    quality_reason TEXT,
    checksum      TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    PRIMARY KEY (code, trade_date, adjust_flag)
);

-- 评分历史
CREATE TABLE IF NOT EXISTS score_history (
    code          TEXT NOT NULL,
    trade_date    TEXT NOT NULL,
    score_type    TEXT NOT NULL DEFAULT 'daily',
    score         REAL,
    rank          INTEGER,
    bucket        TEXT,
    source_tier   TEXT NOT NULL DEFAULT 'L3',
    source_path   TEXT,
    quality_flag  TEXT NOT NULL DEFAULT 'unknown',
    quality_reason TEXT,
    raw_json      TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    PRIMARY KEY (code, trade_date, score_type)
);

-- 收益表（IC 计算）
CREATE TABLE IF NOT EXISTS returns (
    code          TEXT NOT NULL,
    trade_date    TEXT NOT NULL,
    horizon       TEXT NOT NULL,
    return_pct    REAL,
    benchmark_return_pct REAL,
    source_tier   TEXT NOT NULL DEFAULT 'L1',
    quality_flag  TEXT NOT NULL DEFAULT 'unknown',
    created_at    TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    PRIMARY KEY (code, trade_date, horizon)
);

-- 财务指标
CREATE TABLE IF NOT EXISTS financials (
    code          TEXT NOT NULL,
    report_period TEXT NOT NULL,
    metric        TEXT NOT NULL,
    value         REAL,
    unit          TEXT,
    source_tier   TEXT NOT NULL DEFAULT 'tushare',
    quality_flag  TEXT NOT NULL DEFAULT 'unknown',
    created_at    TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    PRIMARY KEY (code, report_period, metric)
);

-- 宏观数据
CREATE TABLE IF NOT EXISTS macro (
    indicator     TEXT NOT NULL,
    trade_date    TEXT NOT NULL,
    value         REAL,
    unit          TEXT,
    source_tier   TEXT NOT NULL DEFAULT 'manual',
    quality_flag  TEXT NOT NULL DEFAULT 'unknown',
    created_at    TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    PRIMARY KEY (indicator, trade_date)
);

-- 风控预计算
CREATE TABLE IF NOT EXISTS risk_metrics (
    code          TEXT NOT NULL,
    trade_date    TEXT NOT NULL,
    metric        TEXT NOT NULL,
    value         REAL,
    window        TEXT,
    source_tier   TEXT NOT NULL DEFAULT 'L2',
    quality_flag  TEXT NOT NULL DEFAULT 'unknown',
    created_at    TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    PRIMARY KEY (code, trade_date, metric, window)
);

-- 历史分位数
CREATE TABLE IF NOT EXISTS historical_percentiles (
    code          TEXT NOT NULL,
    trade_date    TEXT NOT NULL,
    metric        TEXT NOT NULL,
    percentile    REAL,
    window        TEXT,
    source_tier   TEXT NOT NULL DEFAULT 'L2',
    quality_flag  TEXT NOT NULL DEFAULT 'unknown',
    created_at    TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    PRIMARY KEY (code, trade_date, metric, window)
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_kline_code ON kline(code);
CREATE INDEX IF NOT EXISTS idx_kline_date ON kline(trade_date);
CREATE INDEX IF NOT EXISTS idx_kline_code_date ON kline(code, trade_date);
CREATE INDEX IF NOT EXISTS idx_score_history_code ON score_history(code);
CREATE INDEX IF NOT EXISTS idx_score_history_date ON score_history(trade_date);
"""


# ── 辅助 ─────────────────────────────────────────────────

def log(msg, level="INFO"):
    print(f"[{level}] {msg}")


def connect_db(db_path, dry_run=False):
    """连接或创建 DB。dry-run 模式返回 None。"""
    if dry_run:
        return None
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def create_schema(conn, dry_run=False):
    """创建 7 表 schema + 索引。"""
    if dry_run:
        log("SCHEMA PLAN (dry-run):")
        for stmt in SCHEMA_SQL.strip().split(";"):
            s = stmt.strip()
            if s and s.upper().startswith("CREATE"):
                log(f"  {s[:80]}...")
        log(f"  Tables: kline, score_history, returns, financials, macro, risk_metrics, historical_percentiles")
        log(f"  Indexes: idx_kline_code, idx_kline_date, idx_kline_code_date, idx_score_history_code, idx_score_history_date")
        return True
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        log("Schema created: 7 tables + 5 indexes")
        return True
    except sqlite3.Error as e:
        log(f"Schema creation failed: {e}", "BLOCK")
        return False


# ── 数据加载 ─────────────────────────────────────────────

def load_l1_kline_rows(kline_dir, date_from=None, date_to=None, limit_code=None):
    """从 kline_cache/{code}.json 加载 K 线数据。返回 rows 列表。"""
    code_dirs = [d for d in kline_dir.iterdir() if d.suffix == ".json"]
    total = 0
    for path in sorted(code_dirs):
        code = path.stem
        if limit_code and code != limit_code:
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                entries = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            log(f"  KLINE SKIP {code}: {e}", "WARN")
            continue
        for row in entries:
            td = row.get("date", "")
            if date_from and td < date_from:
                continue
            if date_to and td > date_to:
                continue
            total += 1
    return total


def upsert_kline(conn, kline_dir, date_from=None, date_to=None, limit_code=None):
    """从 kline_cache 加载并 upsert 到 L2 kline 表。"""
    code_dirs = sorted([d for d in kline_dir.iterdir() if d.suffix == ".json"])
    upserted = 0
    skipped = 0
    for path in code_dirs:
        code = path.stem
        if limit_code and code != limit_code:
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                entries = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            log(f"  KLINE SKIP {code}: {e}", "WARN")
            skipped += 1
            continue
        count = 0
        for row in entries:
            td = row.get("date", "")
            if date_from and td < date_from:
                continue
            if date_to and td > date_to:
                continue
            try:
                conn.execute("""
                    INSERT INTO kline (code, trade_date, open, high, low, close, volume, amount,
                                       adjust_flag, source_tier, source_path, quality_flag)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'forward', 'L1', ?, 'unknown')
                    ON CONFLICT(code, trade_date, adjust_flag) DO UPDATE SET
                        open=excluded.open, high=excluded.high, low=excluded.low,
                        close=excluded.close, volume=excluded.volume, amount=excluded.amount,
                        source_path=excluded.source_path, updated_at=datetime('now','localtime')
                """, (code, td, row.get("open"), row.get("high"), row.get("low"),
                      row.get("close"), row.get("volume"), row.get("amount", 0),
                      str(path)))
                count += 1
            except sqlite3.Error as e:
                log(f"  KLINE UPSERT ERR {code}/{td}: {e}", "WARN")
        if count:
            conn.commit()
            upserted += count
            log(f"  KLINE {code}: {count} rows upserted")
    return upserted


# ── 哨兵 ─────────────────────────────────────────────────

def write_sentinel(path, db_path=None):
    """写入哨兵文件（含表行数和 DB 大小）。"""
    sentinel = {
        "status": "OK",
        "script": "build_l2_cache.py",
        "db_size": os.path.getsize(db_path) if db_path and os.path.exists(db_path) else 0,
        "table_rows": {},
        "updated_at": datetime.now().isoformat(),
    }
    if db_path and os.path.exists(db_path):
        try:
            conn = sqlite3.connect(str(db_path))
            for t in ["kline", "score_history", "returns", "financials",
                       "macro", "risk_metrics", "historical_percentiles"]:
                try:
                    sentinel["table_rows"][t] = \
                        conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                except sqlite3.Error:
                    sentinel["table_rows"][t] = -1
            conn.close()
        except Exception as e:
            log(f"Sentinel row count failed: {e}", "WARN")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sentinel, f, indent=2, ensure_ascii=False)
    log(f"Sentinel written: {path}")


# ── Main ─────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="L2 SQLite 一次性构建脚本")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH), help="SQLite 路径")
    parser.add_argument("--kline-dir", default=str(KLINE_DIR), help="kline_cache 目录")
    parser.add_argument("--archive-root", default=str(ARCHIVE_ROOT), help="L3 归档根目录")
    parser.add_argument("--dry-run", action="store_true", help="仅打印 schema plan 与预计行数，不写 DB")
    parser.add_argument("--init-empty-tables", action="store_true", help="创建 7 表 schema（含空表）")
    parser.add_argument("--date-from", default=None, help="起始日期 YYYY-MM-DD")
    parser.add_argument("--date-to", default=None, help="截止日期 YYYY-MM-DD")
    parser.add_argument("--limit-code", default=None, help="限单只股票代码")
    args = parser.parse_args()

    db_path = Path(args.db_path)
    kline_dir = Path(args.kline_dir)
    archive_root = Path(args.archive_root)

    log(f"====== build_l2_cache.py (dry_run={args.dry_run}) ======")

    # Step 1: Schema
    conn = connect_db(db_path, dry_run=args.dry_run)
    if not create_schema(conn, dry_run=args.dry_run):
        return 2

    if args.init_empty_tables and not args.dry_run:
        log("Init empty tables: schema already created above")
        write_sentinel(SENTINEL_PATH, db_path if not args.dry_run else None)
        log("====== build_l2_cache.py PASS (empty schema) ======")
        return 0

    # Step 2: Count kline rows (dry-run: just count; real: upsert)
    if args.dry_run:
        total = load_l1_kline_rows(kline_dir, args.date_from, args.date_to, args.limit_code)
        log(f"KLINE: {total} rows would be upserted from kline_cache (dry-run)")
        if args.limit_code:
            log(f"  (filter: limit_code={args.limit_code})")
        if args.date_from or args.date_to:
            log(f"  (filter: date_from={args.date_from}, date_to={args.date_to})")
        log("====== build_l2_cache.py PASS (dry-run) ======")
        return 0

    # Real execution
    if not kline_dir.exists():
        log(f"kline_cache 目录不存在: {kline_dir}", "WARN")
        log("跳过 K 线加载，仅创建空 schema")
        write_sentinel(SENTINEL_PATH, db_path)
        log("====== build_l2_cache.py PASS (empty schema) ======")
        return 0

    upserted = upsert_kline(conn, kline_dir, args.date_from, args.date_to, args.limit_code)
    log(f"KLINE upserted: {upserted} rows")

    write_sentinel(SENTINEL_PATH, db_path)
    log(f"====== build_l2_cache.py PASS (upserted={upserted}) ======")
    return 0


if __name__ == "__main__":
    sys.exit(main())
