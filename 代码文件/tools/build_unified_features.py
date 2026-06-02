#!/usr/bin/env python3
"""build_unified_features.py — 构建统一特征表。

从data_full.json + data_scored.json + score_history.jsonl构建，
写入unified_features.jsonl。

用法:
    python3 build_unified_features.py                    # 构建最新
    python3 build_unified_features.py --date 2026-05-30  # 指定日期
    python3 build_unified_features.py --rebuild           # 全量重建

Code level: L1
"""
import argparse
import sys
import os
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent.parent)
sys.path.insert(0, os.path.join(ROOT, "代码文件", "数据"))
from unified_feature_store import build_from_sources, save_features


def main():
    parser = argparse.ArgumentParser(description="构建统一特征表")
    parser.add_argument("--date", help="目标日期 YYYY-MM-DD")
    parser.add_argument("--rebuild", action="store_true", help="全量重建（暂不支持，Phase 2）")
    args = parser.parse_args()

    if args.rebuild:
        print("WARN: --rebuild 暂不支持，Phase 2 实现。使用 --date 构建单日。")
        sys.exit(1)

    features = build_from_sources(target_date=args.date)
    save_features(features)
    print(f"统一特征表已构建: {len(features)} 条记录")


if __name__ == "__main__":
    main()
