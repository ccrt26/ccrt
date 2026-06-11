#!/usr/bin/env python3
"""
rebuild_score_history.py — 从 L3 归档重建评分历史到 L2（v1.0）

遍历 历史数据/04_原始数据/ 中的 *_data_scored.json 文件，
提取 Recommendations 数组中每只股票的 TotalScore/Score/Rank 写入 L2 score_history 表。

用法:
  python3 scripts/rebuild_score_history.py --dry-run
  python3 scripts/rebuild_score_history.py

退出码:
  0 = PASS
  1 = WARN（部分文件解析失败）
  2 = BLOCK（严重错误）
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
ARCHIVE_ROOT = ROOT / "历史数据" / "04_原始数据"
SENTINEL_PATH = ROOT / "代码文件" / "数据" / "l2_cache" / "last_update.json"
ALL_TABLES = ["kline", "score_history", "returns", "financials",
              "macro", "risk_metrics", "historical_percentiles"]


def log(msg, level="INFO"):
    print(f"[{level}] {msg}")


def scan_archive_files(archive_root, date_from=None, date_to=None):
    """扫描归档目录，返回 (date_compact, path) 列表。"""
    files = []
    for path in sorted(archive_root.iterdir()):
        name = path.name
        if name.endswith("_data_scored.json"):
            date_str = name[:8]
            if date_from and date_str < date_from:
                continue
            if date_to and date_str > date_to:
                continue
            files.append((date_str, path))
    return files


def extract_scores_from_json(path):
    """从 data_scored.json 中提取评分数据。返回 rows 列表。"""
    rows = []
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log(f"  JSON 解析失败: {path.name}: {e}", "WARN")
        return rows

    scored = data.get("Recommendations") or data.get("AllStocks") or []
    if not isinstance(scored, list):
        log(f"  WARN: {path.name} 无 Recommendations 数组", "WARN")
        return rows

    for item in scored:
        code = str(item.get("Code") or item.get("code", ""))
        score = item.get("TotalScore") or item.get("Score")
        rank = item.get("Rank")
        bucket = item.get("SectorPhase") or item.get("sector_phase", "")

        if not code or score is None:
            continue

        rows.append({
            "code": code,
            "score": float(score) if score is not None else None,
            "rank": int(rank) if rank is not None else None,
            "bucket": str(bucket) if bucket else "",
        })
    return rows


def write_sentinel(db_path):
    """写入哨兵文件（含各表行数和 DB 大小）。dry-run 不调用。"""
    sentinel = {
        "status": "OK",
        "script": "rebuild_score_history.py",
        "db_size": os.path.getsize(db_path) if db_path and os.path.exists(db_path) else 0,
        "table_rows": {},
        "updated_at": datetime.now().isoformat(),
    }
    if db_path and os.path.exists(db_path):
        try:
            conn = sqlite3.connect(str(db_path))
            for t in ALL_TABLES:
                try:
                    sentinel["table_rows"][t] = \
                        conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                except sqlite3.Error:
                    sentinel["table_rows"][t] = -1
            conn.close()
        except Exception as e:
            log(f"Sentinel row count failed: {e}", "WARN")
    os.makedirs(os.path.dirname(SENTINEL_PATH), exist_ok=True)
    with open(SENTINEL_PATH, "w", encoding="utf-8") as f:
        json.dump(sentinel, f, indent=2, ensure_ascii=False)
    log(f"Sentinel written: {SENTINEL_PATH}")


def rebuild(archive_root, db_path, date_from=None, date_to=None, dry_run=False):
    """执行重建。"""
    files = scan_archive_files(archive_root, date_from, date_to)
    log(f"找到 {len(files)} 个归档评分文件")

    total_rows = 0
    total_files = 0

    for date_str, path in files:
        rows = extract_scores_from_json(path)
        if not rows:
            continue

        total_rows += len(rows)
        total_files += 1

        if dry_run:
            log(f"  [DRY-RUN] {path.name}: {len(rows)} 行评分, date={date_str}")
            continue

        conn = sqlite3.connect(str(db_path))
        try:
            count = 0
            for r in rows:
                conn.execute("""
                    INSERT INTO score_history (code, trade_date, score_type, score, rank, bucket,
                                               source_tier, source_path)
                    VALUES (?, ?, 'daily', ?, ?, ?, 'L3', ?)
                    ON CONFLICT(code, trade_date, score_type) DO UPDATE SET
                        score=excluded.score, rank=excluded.rank, bucket=excluded.bucket,
                        source_path=excluded.source_path, updated_at=datetime('now','localtime')
                """, (r["code"], date_str, r["score"], r["rank"], r["bucket"], str(path)))
                count += 1
            conn.commit()
            log(f"  {path.name}: {count} 行写入")
        except sqlite3.Error as e:
            log(f"  DB 写入失败 {path.name}: {e}", "WARN")
        finally:
            conn.close()

    if dry_run:
        log(f"[DRY-RUN] 预计重建: {total_rows} 行, 来自 {total_files} 个文件")
    else:
        log(f"重建完成: {total_rows} 行, 来自 {total_files} 个文件")
    return total_rows


def main():
    parser = argparse.ArgumentParser(description="从 L3 归档重建评分历史到 L2")
    parser.add_argument("--archive-root", default=str(ARCHIVE_ROOT), help="L3 归档根目录")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH), help="SQLite 路径")
    parser.add_argument("--dry-run", action="store_true", help="仅统计可重建行数，不写 DB")
    parser.add_argument("--date-from", default=None, help="起始日期 YYYYMMDD")
    parser.add_argument("--date-to", default=None, help="截止日期 YYYYMMDD")
    args = parser.parse_args()

    archive_root = Path(args.archive_root)
    db_path = Path(args.db_path)

    if not archive_root.exists():
        log(f"归档目录不存在: {archive_root}", "BLOCK")
        return 2

    log(f"====== rebuild_score_history.py (dry_run={args.dry_run}) ======")
    rebuild(archive_root, db_path, args.date_from, args.date_to, args.dry_run)
    if not args.dry_run:
        write_sentinel(db_path)
    log("====== rebuild_score_history.py PASS ======")
    return 0


if __name__ == "__main__":
    sys.exit(main())
