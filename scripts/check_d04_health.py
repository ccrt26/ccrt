#!/usr/bin/env python3
"""
check_d04_health.py — D04 运维健康检查脚本（v1.0）

检查 L2 缓存层各维度的健康状态：
  - L2 目录结构
  - DB 存在性和 schema
  - DB integrity_check
  - 哨兵文件新鲜度
  - 备份目录状态
  - 生产入口未被切换为读 D04

用法:
  python3 scripts/check_d04_health.py
  python3 scripts/check_d04_health.py --dry-run
  python3 scripts/check_d04_health.py --dry-run --json
  python3 scripts/check_d04_health.py --strict

退出码:
  0 = HEALTHY
  1 = WARN（部分异常）
  2 = UNHEALTHY（严重问题）
"""
import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
L2_DIR = ROOT / "代码文件" / "数据" / "l2_cache"
DEFAULT_DB_PATH = L2_DIR / "l2_cache.db"
SENTINEL_PATH = L2_DIR / "last_update.json"
BACKUP_DIR = L2_DIR / "backup"
# 只检查 UnifiedDataSource / D04 / l2_cache 的直接引用
# cached_data_source 是旧正常依赖，不视为生产切换信号
PROTECTED_IMPORTS = [
    "from unified_data_source import",
    "import unified_data_source",
    "代码文件/数据/l2_cache/",
]

ALL_TABLES = ["kline", "score_history", "returns", "financials",
              "macro", "risk_metrics", "historical_percentiles"]

# 各表最小预期行数（空表为 0）
MIN_ROWS = {
    "kline": 0,
    "score_history": 0,
    "returns": 0,
    "financials": 0,
    "macro": 0,
    "risk_metrics": 0,
    "historical_percentiles": 0,
}


def log(msg, level="INFO"):
    print(f"[{level}] {msg}")


def check_l2_dir(dry_run=False):
    """检查 L2 目录是否存在。"""
    if not L2_DIR.exists():
        return ("L2_DIR", "WARN" if dry_run else "BLOCK",
                f"L2 目录不存在: {L2_DIR}")
    items = [p.name for p in L2_DIR.iterdir()]
    return ("L2_DIR", "PASS", f"L2 目录存在, {len(items)} 项")


def check_db_exists(db_path, dry_run=False):
    """检查 DB 文件是否存在。"""
    if not db_path.exists():
        return ("DB_EXISTS", "WARN" if dry_run else "BLOCK",
                f"DB 不存在: {db_path}")
    return ("DB_EXISTS", "PASS", f"DB 存在 ({db_path.stat().st_size} bytes)")


def check_schema(conn):
    """检查 7 表是否都存在。"""
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    existing = {t[0] for t in tables}
    missing = [t for t in ALL_TABLES if t not in existing]
    if missing:
        return ("SCHEMA", "WARN", f"缺表: {', '.join(missing)}")
    return ("SCHEMA", "PASS", f"7 表全部存在")


def check_integrity(conn, strict=False):
    """执行 PRAGMA integrity_check。"""
    rows = conn.execute("PRAGMA integrity_check").fetchall()
    if len(rows) == 1 and rows[0][0] == "ok":
        return ("INTEGRITY", "PASS", "integrity_check: ok")
    return ("INTEGRITY", "BLOCK" if strict else "WARN",
            f"integrity_check 失败: {rows}")


def check_sentinel(strict=False):
    """检查哨兵文件：status + 新鲜度。"""
    if not SENTINEL_PATH.exists():
        return ("SENTINEL", "WARN", "哨兵文件不存在")
    try:
        with open(SENTINEL_PATH, "r") as f:
            data = json.load(f)
        status = data.get("status", "")
        updated = data.get("updated_at", "")
        if not updated:
            return ("SENTINEL", "WARN", "哨兵无更新时间")

        # status 优先判断
        if status in ("ERROR", "BLOCK", "FAIL"):
            return ("SENTINEL", "BLOCK" if strict else "WARN",
                    f"哨兵 status={status} — 异常状态")
        if status in ("WARN_LOW_DATA", "WARN_PARTIAL", "WARN"):
            return ("SENTINEL", "WARN", f"哨兵 status={status} — 低数据或部分失败")

        # 新鲜度判断
        updated_dt = datetime.fromisoformat(updated)
        if datetime.now() - updated_dt > timedelta(hours=24):
            return ("SENTINEL", "WARN", f"哨兵超过 24h 未更新 (last={updated})")

        if status == "OK":
            return ("SENTINEL", "PASS", f"哨兵新鲜 (status={status})")

        # status 缺失或未知
        return ("SENTINEL", "WARN", f"哨兵 status 缺失或未知: '{status}'")
    except (json.JSONDecodeError, ValueError, OSError) as e:
        return ("SENTINEL", "WARN", f"哨兵解析失败: {e}")


def check_backup_dir():
    """检查备份目录。"""
    if not BACKUP_DIR.exists():
        return ("BACKUP_DIR", "WARN", "备份目录不存在")
    backups = sorted(BACKUP_DIR.glob("*.db*"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not backups:
        return ("BACKUP_DIR", "WARN", "备份目录存在但无备份文件")
    newest = backups[0]
    age = datetime.now() - datetime.fromtimestamp(newest.stat().st_mtime)
    if age > timedelta(days=7):
        return ("BACKUP_DIR", "WARN", f"最新备份已 {age.days} 天前: {newest.name}")
    return ("BACKUP_DIR", "PASS", f"最新备份: {newest.name} ({age.days}d 前)")


def check_no_production_switch():
    """检查日报/深度分析入口是否被切换为读 D04（非阻塞检查）。"""
    report_dirs = [
        ROOT / "代码文件" / "每日荐股" / "scripts",
        ROOT / "代码文件" / "tools",
    ]
    found = []
    for rd in report_dirs:
        if rd.exists():
            for py in rd.glob("*.py"):
                try:
                    text = py.read_text(encoding="utf-8", errors="ignore")
                    for imp in PROTECTED_IMPORTS:
                        if imp in text:
                            found.append(f"{py.name}: {imp}")
                except OSError:
                    pass
    if found:
        return ("PROD_SWITCH", "WARN", f"日报入口引用了 D04 模块: {'; '.join(found)}")
    return ("PROD_SWITCH", "PASS", "生产入口未引用 D04/UnifiedDataSource")


def check_table_rows(conn, min_rows=None):
    """检查各表行数。返回 (check_name, result, message)。"""
    if min_rows is None:
        min_rows = {}
    counts = {}
    issues = []
    for t in ALL_TABLES:
        try:
            cnt = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            counts[t] = cnt
            threshold = min_rows.get(t, 0)
            if cnt < threshold:
                issues.append(f"{t}={cnt} < {threshold}")
        except sqlite3.Error as e:
            counts[t] = -1
            issues.append(f"{t} error: {e}")
    if issues:
        return ("TABLE_ROWS", "WARN", f"行数不足: {'; '.join(issues)}")
    detail = ", ".join(f"{t}={cnt}" for t, cnt in counts.items()) if counts else "空"
    return ("TABLE_ROWS", "PASS", f"各表行数: {detail}")


def check_sentinel_row_consistency(conn):
    """检查哨兵文件中记录的行数与 DB 实际行数是否一致。"""
    if not SENTINEL_PATH.exists():
        return ("SENTINEL_CONSISTENCY", "WARN", "哨兵文件不存在，无法比对行数")
    try:
        with open(SENTINEL_PATH, "r") as f:
            data = json.load(f)
        sentinel_rows = data.get("table_rows", {})
        mismatches = []
        for t in ALL_TABLES:
            try:
                actual = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            except sqlite3.Error:
                continue
            reported = sentinel_rows.get(t, -1)
            if reported >= 0 and reported != actual:
                mismatches.append(f"{t}: 哨兵={reported} DB={actual}")
        if mismatches:
            return ("SENTINEL_CONSISTENCY", "WARN",
                    f"哨兵行数与 DB 不一致: {'; '.join(mismatches)}")
        return ("SENTINEL_CONSISTENCY", "PASS", "哨兵行数与 DB 一致")
    except (json.JSONDecodeError, OSError) as e:
        return ("SENTINEL_CONSISTENCY", "WARN", f"哨兵解析失败: {e}")


def run_health(db_path, dry_run=False, strict=False, output_json=False,
               require_data=False, min_kline_rows=None, min_score_history_rows=None):
    """执行全量健康检查。"""
    checks = []

    checks.append(check_l2_dir(dry_run))
    checks.append(check_db_exists(db_path, dry_run))

    # 构建最小行数要求
    min_rows = {}
    if require_data:
        min_rows["kline"] = min_kline_rows or 1
        min_rows["score_history"] = min_score_history_rows or 1
    else:
        if min_kline_rows is not None:
            min_rows["kline"] = min_kline_rows
        if min_score_history_rows is not None:
            min_rows["score_history"] = min_score_history_rows

    conn = None
    if db_path.exists():
        try:
            conn = sqlite3.connect(str(db_path))
            checks.append(check_schema(conn))
            checks.append(check_integrity(conn, strict))
            checks.append(check_table_rows(conn, min_rows))
            checks.append(check_sentinel_row_consistency(conn))
        except sqlite3.Error as e:
            checks.append(("INTEGRITY", "BLOCK", f"DB 连接失败: {e}"))
        finally:
            if conn:
                conn.close()

    checks.append(check_sentinel(strict))
    checks.append(check_backup_dir())
    checks.append(check_no_production_switch())

    # 汇总
    pass_count = sum(1 for c in checks if c[1] == "PASS")
    warn_count = sum(1 for c in checks if c[1] == "WARN")
    block_count = sum(1 for c in checks if c[1] == "BLOCK")

    overall = "PASS"
    if block_count > 0:
        overall = "BLOCK" if strict else "WARN"
    elif warn_count > 0:
        overall = "WARN"

    if output_json:
        result = {
            "overall": overall,
            "checks": [{"check": c[0], "result": c[1], "message": c[2]} for c in checks],
            "summary": {"PASS": pass_count, "WARN": warn_count, "BLOCK": block_count},
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"{'='*60}")
        print(f" D04 Health Check (dry_run={dry_run}, strict={strict})")
        print(f"{'='*60}")
        for check in checks:
            icon = {"PASS": "✅", "WARN": "⚠️", "BLOCK": "❌"}.get(check[1], "❓")
            print(f"  {icon} {check[0]}: {check[1]} — {check[2]}")
        print(f"\n  ✅PASS={pass_count} ⚠️WARN={warn_count} ❌BLOCK={block_count}")
        print(f"  总体: {overall}")

    if overall == "BLOCK":
        return 2
    elif overall == "WARN":
        return 1
    return 0


def main():
    parser = argparse.ArgumentParser(description="D04 运维健康检查")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH), help="SQLite 路径")
    parser.add_argument("--dry-run", action="store_true",
                        help="DB 不存在时仍允许 PASS/WARN 不 BLOCK")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    parser.add_argument("--strict", action="store_true",
                        help="integrity 或 schema 缺失则 BLOCK")
    parser.add_argument("--require-data", action="store_true",
                        help="要求表有数据（kline/score_history >0 行）")
    parser.add_argument("--min-kline-rows", type=int, default=None,
                        help="kline 表最小行数要求（默认 0）")
    parser.add_argument("--min-score-history-rows", type=int, default=None,
                        help="score_history 表最小行数要求（默认 0）")
    args = parser.parse_args()

    db_path = Path(args.db_path)
    sys.exit(run_health(db_path, args.dry_run, args.strict, args.json,
                        args.require_data, args.min_kline_rows,
                        args.min_score_history_rows))


if __name__ == "__main__":
    main()
