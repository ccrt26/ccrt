#!/usr/bin/env python3
"""sync_report_json.py — 扫描报告目录，为缺少伴生JSON的HTML/PDF报告生成结构化JSON。

用法:
    python3 sync_report_json.py                     # 扫描所有报告目录
    python3 sync_report_json.py --dry-run           # 仅检查，不写入
    python3 sync_report_json.py --file report.html  # 为单份报告生成

可集成到 daily_orchestrator.py --mode sync_json

Code level: L1
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent.parent)
REPORT_DIRS = [
    os.path.join(ROOT, "每日荐股", "股票报告"),
    os.path.join(ROOT, "重点股票", "股票报告"),
]

# Regex patterns to extract metadata from report filenames
PATTERNS = [
    # key_stock: 拓普集团(601689)分析报告__20260529.html
    (re.compile(r"(.+)\((\d{6})\)分析报告__(\d{8})"), "key_stock_daily"),
    # key_stock daily: 上海电气(601727)日报_2026-05-28.html or 上海电气(601727)日报_20260528.html
    (re.compile(r"(.+)\((\d{6})\)日报_(\d{4}-?\d{2}-?\d{2})"), "key_stock_daily"),
    # daily_rec: daily_report_20260528.html
    (re.compile(r"daily_report_(\d{8})"), "daily_rec"),
]


def extract_meta(html_path):
    """从文件路径提取 report_meta。"""
    basename = os.path.basename(html_path)
    for pattern, rtype in PATTERNS:
        m = pattern.search(basename)
        if m:
            if rtype == "daily_rec":
                date_str = m.group(1)
                if len(date_str) == 8:
                    date_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
                return {"report_type": rtype, "report_date": date_str,
                        "stock_code": "000000", "stock_name": "每日荐股汇总"}
            elif rtype in ("key_stock_daily",):
                name = m.group(1)
                code = m.group(2)
                date_str = m.group(3).replace("-", "")
                if len(date_str) == 8:
                    date_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
                return {"report_type": rtype, "report_date": date_str,
                        "stock_code": code, "stock_name": name}
    return None


def build_conclusion_json(meta):
    """构建结构化结论JSON。字段从报告元数据和默认值填充。"""
    return {
        "report_meta": {
            "report_type": meta["report_type"],
            "report_date": meta["report_date"],
            "stock_code": meta.get("stock_code", ""),
            "stock_name": meta.get("stock_name", ""),
            "strategy_version": "v1.0",
            "generated_at": datetime.now().isoformat(),
        },
        "conclusion": {
            "direction": "neutral",
            "action": "wait",
            "confidence": 0.5,
            "summary": f"自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')} — 待AI填充",
        },
        "price_targets": {
            "buy_price": None, "stop_loss": None, "target_price": None,
            "price_source": "[1]",
        },
        "conditions": {
            "trigger_conditions": [],
            "forbid_conditions": [],
            "counter_evidence": ["待填充: 需说明什么情况发生时原判断失效"],
            "expiry_conditions": [],
        },
        "evidence": {
            "key_evidence": [],
            "risk_factors": [],
            "data_sources": ["[1]", "[2]", "[5]"],
        },
        "signals": {
            "triggered": [],
            "vetoed": [],
        },
        "decision_impact": {
            "scoring_fields": [], "veto_fields": [],
            "downgrade_fields": [], "position_fields": [], "stop_loss_fields": [],
        },
    }


def sync_all(dry_run=False):
    created = 0
    skipped = 0

    for base_dir in REPORT_DIRS:
        if not os.path.isdir(base_dir):
            continue
        for root, _, files in os.walk(base_dir):
            for f in files:
                if not (f.endswith(".html") or f.endswith(".pdf")):
                    continue
                html_path = os.path.join(root, f)
                json_path = html_path.replace(".html", ".json").replace(".pdf", ".json")

                if os.path.exists(json_path):
                    skipped += 1
                    continue

                meta = extract_meta(html_path)
                if not meta:
                    continue

                conclusion = build_conclusion_json(meta)
                if not dry_run:
                    os.makedirs(os.path.dirname(json_path), exist_ok=True)
                    with open(json_path, "w", encoding="utf-8") as fh:
                        json.dump(conclusion, fh, ensure_ascii=False, indent=2)
                created += 1
                print(f"  {'[DRY]' if dry_run else 'CREATED'}: {os.path.basename(json_path)}")

    print(f"\n创建: {created}, 跳过(已有JSON): {skipped}")
    return created, skipped


def main():
    parser = argparse.ArgumentParser(description="报告伴生JSON同步")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--file", help="为单份HTML报告生成JSON")
    args = parser.parse_args()

    if args.file:
        meta = extract_meta(args.file)
        if not meta:
            print(f"WARN: 无法从文件名提取元数据: {args.file}")
            sys.exit(1)
        conclusion = build_conclusion_json(meta)
        json_path = args.file.replace(".html", ".json").replace(".pdf", ".json")
        if not args.dry_run:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(conclusion, f, ensure_ascii=False, indent=2)
        print(f"CREATED: {json_path}")
    else:
        sync_all(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
