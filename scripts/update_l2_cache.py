#!/usr/bin/env python3
"""
update_l2_cache.py — L2 SQLite 每日增量更新脚本（v1.0）

每日增量更新 L2 缓存，含哨兵写入、DB 备份和 checksum 验证。
支持 --dry-run 模式验证输入，不写 DB/backup/sentinel。

用法:
  python3 scripts/update_l2_cache.py --date 20260605 --dry-run
  python3 scripts/update_l2_cache.py --date 20260605

退出码:
  0 = PASS
  1 = WARN（部分失败）
  2 = BLOCK（DB 不存在或关键失败）
"""
import argparse
import gzip
import hashlib
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = ROOT / "代码文件" / "数据" / "l2_cache" / "l2_cache.db"
BACKUP_DIR = ROOT / "代码文件" / "数据" / "l2_cache" / "backup"
SENTINEL_PATH = ROOT / "代码文件" / "数据" / "l2_cache" / "last_update.json"
LOG_PATH = ROOT / "代码文件" / "数据" / "l2_cache" / "operation_log.jsonl"


def log(msg, level="INFO"):
    print(f"[{level}] {msg}")


def write_operation_log(action, status, detail=""):
    """追加操作日志到 operation_log.jsonl。"""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "status": status,
        "detail": detail,
    }
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def backup_db(db_path, backup_dir, dry_run=False):
    """备份 DB 到 backup/ 目录（gzip 压缩）。"""
    if not db_path.exists():
        log(f"DB 不存在，跳过备份: {db_path}", "WARN")
        return None

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"l2_cache_{ts}.db.gz"
    backup_path = backup_dir / backup_name

    if dry_run:
        log(f"[DRY-RUN] 备份: {db_path} → {backup_path}")
        return str(backup_path)

    os.makedirs(str(backup_dir), exist_ok=True)
    try:
        with open(db_path, "rb") as src:
            with gzip.open(str(backup_path), "wb") as dst:
                shutil.copyfileobj(src, dst)
        log(f"备份完成: {backup_path} ({backup_path.stat().st_size} bytes)")
        write_operation_log("backup", "OK", str(backup_path))
        return str(backup_path)
    except (OSError, shutil.Error) as e:
        log(f"备份失败: {e}", "WARN")
        write_operation_log("backup", "FAIL", str(e))
        return None


def compute_checksum(db_path):
    """计算 DB 的 SHA256 校验和。"""
    if not db_path.exists():
        return None
    h = hashlib.sha256()
    with open(db_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def write_sentinel(status, db_path=None, checksum_val=None):
    """写入哨兵 JSON。"""
    sentinel = {
        "status": status,
        "script": "update_l2_cache.py",
        "db_size": os.path.getsize(db_path) if db_path and db_path.exists() else 0,
        "sha256": checksum_val or "",
        "table_rows": {},
        "updated_at": datetime.now().isoformat(),
    }
    if db_path and db_path.exists():
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
            log(f"行数统计失败: {e}", "WARN")
    os.makedirs(os.path.dirname(SENTINEL_PATH), exist_ok=True)
    with open(SENTINEL_PATH, "w", encoding="utf-8") as f:
        json.dump(sentinel, f, indent=2, ensure_ascii=False)


def run_update(args):
    """执行增量更新。"""
    db_path = Path(args.db_path)
    backup_dir = Path(args.backup_dir) if args.backup_dir else BACKUP_DIR

    # 解析日期
    date_str = str(args.date).replace("-", "") if args.date else ""
    if not date_str:
        date_str = datetime.now().strftime("%Y%m%d")

    log(f"====== update_l2_cache.py (date={date_str}, dry_run={args.dry_run}) ======")

    kline_dir = Path(args.kline_dir) if args.kline_dir else ROOT / "代码文件" / "数据" / "kline_cache"

    # Dry-run 验证（DB 不存在时仍可完成计划检查）
    if args.dry_run:
        log(f"[DRY-RUN] 增量更新计划 (date={date_str})")
        if db_path.exists():
            log(f"[DRY-RUN] DB 存在: {db_path}")
        else:
            log(f"[DRY-RUN] DB 不存在: {db_path}（实写前需先运行 build_l2_cache.py）")
        if kline_dir.exists():
            expected_codes = sorted([d.stem for d in kline_dir.iterdir() if d.suffix == ".json"])
            log(f"[DRY-RUN] 将处理 {len(expected_codes)} 只股票的 K 线增量")
        else:
            log(f"[DRY-RUN] kline_dir 不存在: {kline_dir}", "WARN")
        log(f"[DRY-RUN] 将写哨兵: {SENTINEL_PATH}")
        log(f"[DRY-RUN] 将备份到: {backup_dir / f'l2_cache_{date_str}_*.db.gz'}")
        log(f"[DRY-RUN] 将计算 checksum (SHA256)")
        log(f"[DRY-RUN] 不写 DB / 不写 backup / 不写 sentinel")
        return 0

    # 实写检查：DB 必须存在
    if not db_path.exists():
        log(f"DB 不存在: {db_path}。请先运行 build_l2_cache.py", "BLOCK")
        return 2

    # 实写模式
    # 1. 备份 — 失败则阻断
    if not args.skip_backup:
        backup_result = backup_db(db_path, backup_dir)
        if backup_result is None:
            log("备份失败，阻断 DB 写入", "BLOCK")
            write_sentinel("BLOCK", db_path)
            write_operation_log("backup", "FAIL", "阻断: 备份返回 None，跳过 DB 写入")
            return 1

    # 2. 增量更新 kline（实际从 L1 kline_cache 或 data_full 读取）
    kline_dir = Path(args.kline_dir) if args.kline_dir else ROOT / "代码文件" / "数据" / "kline_cache"
    if not kline_dir.exists():
        log(f"kline_cache 目录不存在: {kline_dir}", "WARN")
        write_sentinel("WARN", db_path)
        return 1

    upserted = 0
    upsert_errors = 0
    conn = sqlite3.connect(str(db_path))
    try:
        for path in sorted(kline_dir.iterdir()):
            if path.suffix != ".json":
                continue
            code = path.stem
            if args.limit_code and code != args.limit_code:
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    entries = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                log(f"  SKIP {code}: {e}", "WARN")
                continue
            count = 0
            for row in entries:
                td = row.get("date", "").replace("-", "")
                if td == date_str:
                    try:
                        conn.execute("""
                            INSERT INTO kline (code, trade_date, open, high, low, close, volume, amount,
                                               adjust_flag, source_tier, source_path, quality_flag)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'forward', 'L1', ?, 'unknown')
                            ON CONFLICT(code, trade_date, adjust_flag) DO UPDATE SET
                                open=excluded.open, high=excluded.high, low=excluded.low,
                                close=excluded.close, volume=excluded.volume, amount=excluded.amount,
                                source_path=excluded.source_path, updated_at=datetime('now','localtime')
                        """, (code, row.get("date"), row.get("open"), row.get("high"),
                              row.get("low"), row.get("close"), row.get("volume"),
                              row.get("amount", 0), str(path)))
                        count += 1
                    except sqlite3.Error as e:
                        log(f"  UPSERT ERR {code}: {e}", "WARN")
                        upsert_errors += 1
            if count:
                conn.commit()
                upserted += count
                log(f"  UPDATE {code}: {count} row(s) for {date_str}")
    finally:
        conn.close()

    # 3. 异常累积检查
    if upsert_errors > 0:
        write_sentinel("WARN_PARTIAL", db_path, compute_checksum(db_path))
        write_operation_log("update", "WARN",
                            f"date={date_str} upserted={upserted} errors={upsert_errors}")
        log(f"Update partial: {upserted} rows upserted, {upsert_errors} errors — WARN")
        return 1

    # 4. 哨兵
    chk = compute_checksum(db_path)
    new_status = "OK" if upserted > 0 else "WARN_LOW_DATA"
    write_sentinel(new_status, db_path, chk)
    write_operation_log("update", "OK" if upserted > 0 else "WARN",
                        f"date={date_str} upserted={upserted}")

    log(f"Update complete: {upserted} rows upserted for {date_str} — {'PASS' if upserted > 0 else 'WARN'}")
    return 0 if upserted > 0 else 1


def main():
    parser = argparse.ArgumentParser(description="L2 SQLite 每日增量更新")
    parser.add_argument("--date", default="", help="交易日 YYYYMMDD 或 YYYY-MM-DD（默认当天）")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH), help="SQLite 路径")
    parser.add_argument("--kline-dir", default="", help="kline_cache 目录")
    parser.add_argument("--backup-dir", default="", help="备份目录（默认 backup/）")
    parser.add_argument("--dry-run", action="store_true", help="仅验证输入，不写 DB/backup/sentinel")
    parser.add_argument("--skip-backup", action="store_true", help="跳过每日备份")
    parser.add_argument("--limit-code", default=None, help="限单只股票代码")
    args = parser.parse_args()
    sys.exit(run_update(args))


if __name__ == "__main__":
    main()
