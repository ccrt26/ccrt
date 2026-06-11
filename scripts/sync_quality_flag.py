#!/usr/bin/env python3
"""
sync_quality_flag.py — D03→D04 quality_flag 同步脚本（v1.0）

从 data_quality_report.json 读取质量标记，同步到 L2 各表的 quality_flag 字段。
支持 --dry-run 验证变更行数，不写 DB。

用法:
  python3 scripts/sync_quality_flag.py --table all --dry-run
  python3 scripts/sync_quality_flag.py --table kline

退出码:
  0 = PASS
  1 = WARN（质量报告不存在）
  2 = BLOCK（DB 不存在）
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
QUALITY_REPORT_PATH = ROOT / "代码文件" / "数据" / "data_quality_report.json"
LOG_PATH = ROOT / "代码文件" / "数据" / "l2_cache" / "operation_log.jsonl"

ALL_TABLES = ["kline", "score_history", "returns", "financials",
              "macro", "risk_metrics", "historical_percentiles"]

# quality_flag 有 quality_report 时为 kline 的默认 flag 映射
# unknown = 无质量数据；verified = 已验证；suspect = 可疑
DEFAULT_FLAG = "unknown"


def log(msg, level="INFO"):
    print(f"[{level}] {msg}")


def write_operation_log(action, status, detail=""):
    entry = {
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "status": status,
        "detail": detail,
    }
    os.makedirs(str(LOG_PATH.parent), exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def load_quality_report(path):
    """加载质量报告。不存在时返回 None。"""
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log(f"质量报告解析失败: {e}", "WARN")
        return None


def derive_flag_for_code(code, quality_data):
    """从质量报告推导单只股票的 quality_flag。"""
    if not quality_data:
        return DEFAULT_FLAG

    issues = quality_data.get("issues", [])
    for issue in issues:
        affected = str(issue.get("code", "") or issue.get("stock_code", "") or "")
        if affected == code:
            severity = issue.get("severity", "").lower()
            if severity in ("block", "error"):
                return "suspect"
    return "verified" if quality_data.get("overall", "").lower() in ("pass", "warn") else DEFAULT_FLAG


def table_has_column(conn, table, column):
    """检查表是否有指定列。"""
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == column for r in rows)


def sync_table(conn, table, quality_data, dry_run=False):
    """同步单表的 quality_flag。返回预计变更行数。"""
    # 检查表是否有 code 列（macro 表无 code 字段）
    has_code = table_has_column(conn, table, 'code')
    if not has_code:
        log(f"  [SKIP] {table}: 无 code 列，跳过 quality_flag 同步")
        return 0, 0

    # 先读当前行数
    total = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    if total == 0:
        return 0, 0

    # 统计需要更新的行
    changed = 0
    for row in conn.execute(f"SELECT DISTINCT code FROM {table}"):
        code = row[0]
        new_flag = derive_flag_for_code(code, quality_data)
        current = conn.execute(
            f"SELECT quality_flag FROM {table} WHERE code=? LIMIT 1", (code,)
        ).fetchone()
        if current and current[0] != new_flag:
            count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE code=?", (code,)
            ).fetchone()[0]
            changed += count

    if dry_run:
        log(f"  [DRY-RUN] {table}: {total} 行, 将更新 {changed} 行")
        return 0, changed

    # 实际更新
    updated = 0
    for row in conn.execute(f"SELECT DISTINCT code FROM {table}"):
        code = row[0]
        new_flag = derive_flag_for_code(code, quality_data)
        cur = conn.execute(
            f"UPDATE {table} SET quality_flag=?, updated_at=datetime('now','localtime') WHERE quality_flag!=? AND code=?",
            (new_flag, new_flag, code)
        )
        updated += cur.rowcount
    conn.commit()
    return updated, changed


def main():
    parser = argparse.ArgumentParser(description="D03→D04 quality_flag 同步")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH), help="SQLite 路径")
    parser.add_argument("--quality-report", default=str(QUALITY_REPORT_PATH), help="质量报告路径")
    parser.add_argument("--table", default="all",
                        help="目标表: kline|score_history|...|all")
    parser.add_argument("--dry-run", action="store_true", help="仅打印变更行数，不写 DB")
    args = parser.parse_args()

    db_path = Path(args.db_path)
    qr_path = Path(args.quality_report)

    tables = ALL_TABLES if args.table == "all" else [args.table]

    # Dry-run 模式允许 DB 不存在（仅输出计划）
    if args.dry_run and not db_path.exists():
        log(f"[DRY-RUN] DB 不存在: {db_path}（实写前需先运行 build_l2_cache.py）")
        log(f"[DRY-RUN] 将从 {qr_path} 同步 quality_flag 到 {args.table}")
        log(f"[DRY-RUN] 将使用默认 flag='{DEFAULT_FLAG}'（质量报告不可用时）")
        log(f"[DRY-RUN] 不写 DB")
        log("====== sync_quality_flag.py PASS (dry-run) ======")
        return 0

    if not db_path.exists():
        log(f"DB 不存在: {db_path}", "BLOCK")
        return 2
    quality_data = load_quality_report(qr_path)
    if quality_data is None:
        log(f"质量报告不存在或无法解析: {qr_path}，将使用默认 flag='{DEFAULT_FLAG}'", "WARN")

    log(f"====== sync_quality_flag.py (table={args.table}, dry_run={args.dry_run}) ======")

    conn = sqlite3.connect(str(db_path))
    try:
        total_updated = 0
        total_changed = 0
        for table in tables:
            updated, changed = sync_table(conn, table, quality_data, args.dry_run)
            total_updated += updated
            total_changed += changed

        if args.dry_run:
            log(f"[DRY-RUN] 预计更新 {total_changed} 行（不写 DB）")
        else:
            log(f"同步完成: {total_updated} 行更新")
            write_operation_log("sync_quality_flag", "OK", f"tables={args.table} updated={total_updated}")
    finally:
        conn.close()

    log("====== sync_quality_flag.py PASS ======")
    return 0


if __name__ == "__main__":
    sys.exit(main())
