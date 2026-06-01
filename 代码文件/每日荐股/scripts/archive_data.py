#!/usr/bin/env python3
"""archive_data.py — 每日数据归档脚本 (macOS Python 移植)

从 代码文件/数据/ 归档当日产出到 历史数据/ 对应子目录。
保留策略：每目录最新60个文件 + 90天过期清理。

Code level: L0
"""
import argparse
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


def trim_to_latest(subdir, keep=KEEP_LATEST):
    d = ARCHIVE_ROOT / subdir
    if not d.is_dir():
        return
    files = sorted(d.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
    keep = max(keep, SAFE_FLOOR)
    for f in files[keep:]:
        f.unlink()
    if len(files) > keep:
        log(f"裁剪 {subdir}: 保留最新{keep}个，删除{len(files) - keep}个")


def clean_old(subdir, days=RETENTION_DAYS):
    d = ARCHIVE_ROOT / subdir
    if not d.is_dir():
        return
    cutoff = datetime.now() - timedelta(days=days)
    deleted = 0
    for f in d.glob("*"):
        if f.is_file() and datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
            f.unlink()
            deleted += 1
    if deleted:
        log(f"清理 {subdir}: 删除{deleted}个过期文件(>{days}天)")


def main():
    parser = argparse.ArgumentParser(description="Daily data archiver")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"),
                        help="Archive date label (YYYY-MM-DD)")
    parser.add_argument("--keep", type=int, default=KEEP_LATEST)
    parser.add_argument("--retention", type=int, default=RETENTION_DAYS)
    args = parser.parse_args()

    date_label = args.date.replace("-", "")
    log(f"===== 开始归档 ({args.date}) =====")

    archived = 0
    for src_name, subdir, required in ARCHIVE_MAP:
        if archive_file(src_name, subdir, date_label, required):
            archived += 1

    # 裁剪+清理
    for subdir in set(sd for _, sd, _ in ARCHIVE_MAP):
        trim_to_latest(subdir, args.keep)
        clean_old(subdir, args.retention)

    log(f"归档完成: {archived}个文件 → {ARCHIVE_ROOT}")
    log("===== 归档结束 =====")
    return 0 if archived >= 4 else 1


if __name__ == "__main__":
    sys.exit(main())
