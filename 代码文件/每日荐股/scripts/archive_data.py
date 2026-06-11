#!/usr/bin/env python3
"""archive_data.py — 每日数据归档 + L3 周级快照 (macOS Python 移植)

双模式：
  - daily（默认）：从 代码文件/数据/ 归档当日产出到 历史数据/ 对应子目录。
    保留策略：每目录最新60个文件 + 90天过期清理。
  - weekly-snapshot：将周级快照写入 历史数据/04_原始数据/{year}/ 永久保留，
    仅审计追溯用途，不被程序常规读取。

L3 年目录不受 90 天清理影响，保护目录列表见 ARCHIVE_PROTECTED_DIRS。

Code level: L0
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = ROOT / "代码文件" / "数据"
ARCHIVE_ROOT = ROOT / "历史数据"
SCRIPTS_DIR = ROOT / "代码文件" / "每日荐股" / "scripts"
LOG_FILE = SCRIPTS_DIR / f"workflow_{datetime.now().strftime('%Y%m')}.log"

KEEP_LATEST = 60
RETENTION_DAYS = 90
SAFE_FLOOR = 10  # 安全底线：每个目录至少保留10个文件

# L3 年目录保护：以下子目录下的年目录（如 04_原始数据/2026/）受保护
# 保护逻辑见 is_protected_yearly_dir() — 只保护年子目录，不保护整个根目录
ARCHIVE_PROTECTED_DIRS = ["04_原始数据"]

# 归档映射: (源文件, 目标子目录, 是否必须)
ARCHIVE_MAP = [
    ("data_full.json",        "04_原始数据", True),
    ("data_scored.json",      "04_原始数据", True),
    ("data_final.json",       "04_原始数据", True),
    ("score_history.jsonl",   "04_原始数据", True),
    ("dynamic_pool.json",     "05_参考数据", True),
    ("sector_data.json",      "05_参考数据", False),
    ("industry_map.json",     "05_参考数据", False),
    ("eastmoney_sector_map.json", "05_参考数据", False),
    # Post-evaluation products
    ("../../每日荐股/事后评估/eval_result_{date}.json", "02_评估数据", False),
    ("../../每日荐股/事后评估/records.csv", "02_评估数据", False),
    ("../../每日荐股/事后评估/summary.csv", "02_评估数据", False),
]

# 周级快照文件映射: (源文件子名, 目标文件名模式, 是否必须)
WEEKLY_SNAPSHOT_FILES = [
    ("data_full.json",     "w{week:02d}_{date}_data_full.json",     True),
    ("data_scored.json",   "w{week:02d}_{date}_data_scored.json",   True),
    ("data_final.json",    "w{week:02d}_{date}_data_final.json",    True),
    ("score_history.jsonl","w{week:02d}_{date}_score_history.jsonl",True),
]


def log(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}][ARCHIVE][{level}] {msg}"
    print(line)
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def validate_json_file(path, required=True):
    """预校验 JSON 文件合法性（utf-8-sig）。非法 JSON 禁止归档。"""
    if not path.exists():
        return True  # 文件不存在由调用方处理，这里只校验存在的文件
    if path.suffix.lower() != ".json":
        return True  # 非 JSON 文件跳过
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            json.load(f)
        return True
    except (json.JSONDecodeError, ValueError) as e:
        if required:
            log(f"BLOCK: required JSON 非法 → {path}: {e}", "BLOCK")
        else:
            log(f"WARN: optional JSON 非法，跳过归档 → {path}: {e}", "WARN")
        return False


def preflight_required(date_label):
    """预检所有 required 文件。任一缺失或非法 → 不归档，return 2。"""
    problems = []
    for src_name, subdir, required in ARCHIVE_MAP:
        if not required:
            continue
        src_name_resolved = src_name.replace('{date}', date_label)
        if src_name_resolved.startswith('../../'):
            src = (DATA_DIR / src_name_resolved).resolve()
        else:
            src = DATA_DIR / src_name_resolved
        if not src.exists():
            problems.append(f"required 文件不存在: {src}")
        elif not validate_json_file(src, required=True):
            problems.append(f"required JSON 非法: {src}")
    if problems:
        for p in problems:
            log(p, "BLOCK")
        log("BLOCK: required 文件预检失败，禁止归档（不复制任何文件）", "BLOCK")
        return False
    return True


def archive_file(src_name, subdir, date_label, required=True):
    # Support {date} template and relative paths
    src_name_resolved = src_name.replace('{date}', date_label)
    if src_name_resolved.startswith('../../'):
        src = (DATA_DIR / src_name_resolved).resolve()
    else:
        src = DATA_DIR / src_name_resolved

    if not src.exists():
        if required:
            log(f"文件不存在，跳过: {src}", "WARN")
        return False

    # 预校验 JSON 合法性 — 禁止归档非法 JSON
    if not validate_json_file(src, required=required):
        return False  # 非法 JSON 不归档，required 时已计入 _required_failures

    dst_dir = ARCHIVE_ROOT / subdir
    dst_dir.mkdir(parents=True, exist_ok=True)
    stem, ext = os.path.splitext(os.path.basename(src_name_resolved))
    dst_name = f"{date_label}_{stem}{ext}"
    dst = dst_dir / dst_name

    # If destination already exists and same size, skip
    if dst.exists() and dst.stat().st_size == src.stat().st_size:
        return True

    shutil.copy2(src, dst)
    log(f"归档: {os.path.basename(src_name_resolved)} → {subdir}/{dst_name}")
    return True


def is_protected_yearly_dir(subdir, file_path):
    """判断 file_path 是否位于 L3 年目录下（如 04_原始数据/2026/）。
    只保护年子目录内的文件，不保护整个根目录。"""
    for protected in ARCHIVE_PROTECTED_DIRS:
        if subdir == protected and file_path.parent != (ARCHIVE_ROOT / subdir):
            # file_path 位于子目录中（如 04_原始数据/2026/xxx.json）
            return True
    return False


def clean_old(subdir, days=RETENTION_DAYS):
    """清理过期文件。L3 年目录下的文件跳过。"""
    d = ARCHIVE_ROOT / subdir
    if not d.is_dir():
        return
    cutoff = datetime.now() - timedelta(days=days)
    deleted = 0
    for f in d.glob("*"):
        if not f.is_file():
            continue  # 跳过子目录（含 L3 年目录）
        if is_protected_yearly_dir(subdir, f):
            continue  # L3 年目录内的文件跳过清理
        if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
            f.unlink()
            deleted += 1
    if deleted:
        log(f"清理 {subdir}: 删除{deleted}个过期文件(>{days}天)")


def trim_to_latest(subdir, keep=KEEP_LATEST):
    """裁剪至最新 keep 个文件。只处理文件，跳过目录（含 L3 年目录）。"""
    d = ARCHIVE_ROOT / subdir
    if not d.is_dir():
        return
    # 只处理文件，跳过子目录（如 2026/）
    files = sorted(
        [p for p in d.iterdir() if p.is_file() and not is_protected_yearly_dir(subdir, p)],
        key=lambda p: p.stat().st_mtime, reverse=True
    )
    keep = max(keep, SAFE_FLOOR)
    for f in files[keep:]:
        f.unlink()
    if len(files) > keep:
        log(f"裁剪 {subdir}: 保留最新{keep}个，删除{len(files) - keep}个")


# ── 周级快照 ─────────────────────────────────────────────

def is_last_trading_day_of_week(date_str):
    """判断 date_str（YYYY-MM-DD）是否为当周最后交易日。
    简化实现：周五返回 True。"""
    from datetime import date as dt_date
    try:
        d = dt_date.fromisoformat(date_str)
        return d.weekday() == 4  # Friday
    except (ValueError, TypeError):
        return False


def compute_file_sha256(path):
    """计算文件的 SHA256 校验和。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def write_archive_manifest(year_dir, entries):
    """生成 archive_manifest.sha256。"""
    lines = []
    for e in entries:
        lines.append(f"{e['sha256']}  {e['relpath']}  {e['size']}  {e['date']}")
    manifest_path = year_dir / "archive_manifest.sha256"
    manifest_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log(f"写入 archive_manifest.sha256: {len(entries)} 条目")


def write_archive_index(year_dir, manifest_entries, year):
    """生成 archive_index.json。"""
    total_size = sum(e["size"] for e in manifest_entries)
    index = {
        "year": year,
        "description": "L3 永久归档索引——仅审计追溯，不作程序常规读取",
        "snapshot_type": "weekly",
        "generated_at": datetime.now().isoformat(),
        "checksum_algorithm": "sha256",
        "total_files": len(manifest_entries),
        "total_size_bytes": total_size,
        "entries": [
            {
                "filename": e["relpath"],
                "sha256": e["sha256"],
                "source_date": e["date"],
                "size_bytes": e["size"],
            }
            for e in manifest_entries
        ],
    }
    index_path = year_dir / "archive_index.json"
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    log(f"写入 archive_index.json: {len(manifest_entries)} 条目, {total_size} bytes")


def archive_weekly_snapshot(date_label, date_compact, dry_run=False):
    """创建周级永久快照到 L3 年目录。"""
    year = date_compact[:4]
    year_dir = ARCHIVE_ROOT / "04_原始数据" / year
    if not dry_run:
        year_dir.mkdir(parents=True, exist_ok=True)

    # 计算周号
    try:
        d = datetime.strptime(date_compact, "%Y%m%d")
        week_num = d.isocalendar()[1]
    except ValueError:
        week_num = 0

    entries = []
    for src_name, dst_pattern, required in WEEKLY_SNAPSHOT_FILES:
        src = DATA_DIR / src_name
        if not src.exists():
            if required:
                log(f"WEEKLY_SNAPSHOT SKIP: required 文件不存在 {src}", "WARN")
            continue
        if not dry_run:
            # Validate JSON
            if src.suffix.lower() == ".json":
                try:
                    with open(src, "r", encoding="utf-8-sig") as f:
                        json.load(f)
                except (json.JSONDecodeError, ValueError) as e:
                    log(f"WEEKLY_SNAPSHOT SKIP: JSON 非法 {src}: {e}", "WARN")
                    continue

        dst_name = dst_pattern.format(week=week_num, date=date_compact)
        dst = year_dir / dst_name

        if dry_run:
            relpath = str(dst.relative_to(year_dir)) if hasattr(dst, "relative_to") else dst_name
            entries.append({"relpath": relpath, "sha256": "dry-run", "size": src.stat().st_size, "date": date_compact})
            log(f"  [DRY-RUN] 周级快照: {src_name} → {year}/{dst_name}")
            continue

        # 同名目标已存在且 checksum 一致则跳过
        if dst.exists():
            existing_sha = compute_file_sha256(dst)
            src_sha = compute_file_sha256(src)
            if existing_sha == src_sha:
                log(f"  SKIP: {dst_name} — 已存在且 checksum 一致")
                entries.append({"relpath": dst_name, "sha256": src_sha, "size": src.stat().st_size, "date": date_compact})
                continue

        shutil.copy2(src, dst)
        sha = compute_file_sha256(dst)
        entries.append({"relpath": dst_name, "sha256": sha, "size": src.stat().st_size, "date": date_compact})
        log(f"  周级快照: {src_name} → {year}/{dst_name}")

    if not dry_run and entries:
        write_archive_manifest(year_dir, entries)
        write_archive_index(year_dir, entries, year)
        log(f"周级快照完成: {len(entries)} 文件 → {year_dir}")

    return len(entries)


def main():
    parser = argparse.ArgumentParser(description="Daily data archiver + L3 weekly snapshot")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"),
                        help="Archive date label (YYYY-MM-DD)")
    parser.add_argument("--keep", type=int, default=KEEP_LATEST)
    parser.add_argument("--retention", type=int, default=RETENTION_DAYS)
    parser.add_argument("--mode", choices=["daily", "weekly-snapshot"], default="daily",
                        help="归档模式: daily（默认）=每日归档+清理, weekly-snapshot=周级永久快照到L3年目录")
    parser.add_argument("--dry-run", action="store_true",
                        help="仅打印将执行的操作，不写任何文件")
    args = parser.parse_args()

    date_label = args.date.replace("-", "")
    log(f"===== 开始归档 ({args.date}) mode={args.mode} dry_run={args.dry_run} =====")

    if args.mode == "weekly-snapshot":
        count = archive_weekly_snapshot(date_label, date_label, dry_run=args.dry_run)
        if count == 0:
            log("周级快照: 无可归档文件", "WARN")
        log("===== 归档结束 (weekly-snapshot) =====")
        return 0 if count > 0 else 1

    # 每日归档模式（保留原有行为）
    if not preflight_required(date_label):
        log("===== 归档结束 (BLOCKED) =====")
        return 2

    archived = 0
    for src_name, subdir, required in ARCHIVE_MAP:
        if archive_file(src_name, subdir, date_label, required):
            archived += 1

    # 裁剪+清理（保护目录跳过）
    for subdir in set(sd for _, sd, _ in ARCHIVE_MAP):
        trim_to_latest(subdir, args.keep)
        clean_old(subdir, args.retention)

    log(f"归档完成: {archived}个文件 → {ARCHIVE_ROOT}")
    log("===== 归档结束 =====")
    return 0 if archived >= 4 else 1


if __name__ == "__main__":
    sys.exit(main())
