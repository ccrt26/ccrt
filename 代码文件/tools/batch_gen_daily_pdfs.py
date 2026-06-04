#!/usr/bin/env python3
"""batch_gen_daily_pdfs.py — v3.6.3 批量日报PDF生成器
用法: python3 batch_gen_daily_pdfs.py --date YYYYMMDD
股票池从 pigeon_config.json 读取，PDF通过 convert_md_to_pdf.convert 生成。
"""
import argparse, json, os, sys
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent.parent)
REPORT_DIR = os.path.join(ROOT, "重点股票", "股票报告")
PIGEON_CFG = os.path.join(ROOT, "代码文件", "信鸽信息采集", "pigeon_config.json")

def load_pool():
    """Read stock pool from pigeon_config.json"""
    if not os.path.exists(PIGEON_CFG):
        print("BLOCK: pigeon_config.json not found")
        sys.exit(2)
    try:
        with open(PIGEON_CFG, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        targets = cfg.get("target_stocks", [])
        if not targets:
            print("BLOCK: target_stocks empty")
            sys.exit(2)
        return [(str(s["code"]), s["name"]) for s in targets]
    except Exception as e:
        print(f"BLOCK: pigeon_config parse failed: {e}")
        sys.exit(2)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    args = ap.parse_args()
    date_str = args.date

    pool = load_pool()
    print(f"Stock pool: {len(pool)} stocks from pigeon_config.json")

    # Import convert from the unified entry point
    sys.path.insert(0, os.path.join(ROOT, "代码文件", "tools"))
    from convert_md_to_pdf import convert

    success = 0
    for code, name in pool:
        md_path = os.path.join(REPORT_DIR, f"{name}({code})", f"{name}({code})日报_{date_str}.md")
        pdf_path = os.path.join(REPORT_DIR, f"{name}({code})", f"{name}({code})日报_{date_str}.pdf")
        if not os.path.exists(md_path):
            print(f"  SKIP {code} {name}: MD not found")
            continue
        ok = convert(md_path, pdf_path)
        if ok:
            success += 1

    print(f"\nDone: {success}/{len(pool)} PDFs generated")

if __name__ == "__main__":
    main()
