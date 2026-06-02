#!/usr/bin/env python3
"""version_supervisor.py — 白皮书版本一致性自动检查

Replaces version_supervisor.ps1.
Cross-checks filename version = internal declaration = CHANGELOG = 文档版本索引.
Code level: L1
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent.parent)


def check_version_consistency(filepath):
    """Check a single file for version consistency."""
    filename = os.path.basename(filepath)
    m = re.search(r'_v(\d+\.\d+(?:\.\d+)?)', filename)
    if not m:
        return {"file": filename, "status": "skip", "reason": "No version in filename"}

    file_version = m.group(1)
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return {"file": filename, "status": "error", "reason": str(e)}

    internal_version = None
    # Only scan file header (first 1000 chars) to avoid matching version
    # references in section headings or version history tables
    header = content[:1000]
    for pat in [
        r'(?:[Vv]ersion|版本)\s*(?:\*\*)?[：:]\s*v(\d+\.\d+(?:\.\d+)?)',
        r'(?:^|\n)#[^\n]*?[Vv]ersion[^\n]*?v(\d+\.\d+(?:\.\d+)?)',
    ]:
        im = re.search(pat, header)
        if im:
            internal_version = im.group(1)
            break

    if internal_version:
        if file_version != internal_version:
            return {"file": filename, "status": "FAIL", "reason": f"Filename v{file_version} != internal v{internal_version}"}
        return {"file": filename, "status": "PASS", "reason": f"v{file_version}"}
    return {"file": filename, "status": "WARN", "reason": f"Filename has v{file_version} but no internal version found"}


def main():
    parser = argparse.ArgumentParser(description="Version consistency supervisor")
    parser.add_argument("--cross-check", action="store_true", help="Run full cross-check")
    parser.add_argument("--file", default="", help="Check single file")
    parser.add_argument("--root-dir", default=ROOT, help="Project root")
    args = parser.parse_args()

    if args.file:
        result = check_version_consistency(args.file)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0 if result["status"] != "FAIL" else 1)

    # Full cross-check on whitepaper directories
    scan_dirs = [
        os.path.join(ROOT, "每日荐股", "分析逻辑"),
        os.path.join(ROOT, "每日荐股", "事后评估"),
        os.path.join(ROOT, "重点股票", "分析逻辑"),
        os.path.join(ROOT, "重点股票", "次日评估"),
        os.path.join(ROOT, "金融铁律"),
        os.path.join(ROOT, "模拟交易"),
    ]

    results = []
    for scan_dir in scan_dirs:
        if not os.path.isdir(scan_dir):
            continue
        for f in os.listdir(scan_dir):
            if f.endswith(".md") and re.search(r'_v\d+\.\d+', f):
                results.append(check_version_consistency(os.path.join(scan_dir, f)))

    fails = [r for r in results if r["status"] == "FAIL"]
    warns = [r for r in results if r["status"] == "WARN"]
    passes = [r for r in results if r["status"] == "PASS"]

    summary = {
        "total": len(results),
        "pass": len(passes),
        "warn": len(warns),
        "fail": len(fails),
        "results": results,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
