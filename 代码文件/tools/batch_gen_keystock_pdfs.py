"""Batch generate all 8 key stock PDFs from MD reports with preflight checks.

Code level: L0 (tool/data)
Design doc: 审计报告/架构设计/design_md_to_pdf_toolchain.md
"""
import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from convert_md_to_pdf import convert, find_edge

BASE_MD = r"c:\Users\34269\Documents\Claude\股票分析\临时报告"
BASE_PDF = r"c:\Users\34269\Documents\Claude\股票分析\重点股票\股票报告"

STOCKS = [
    ("600036_招商银行_深度分析_20260525.md", "招商银行(600036)",
     "招商银行(600036)分析报告__20260525.pdf"),
    ("600584_长电科技_深度分析_20260525.md", "长电科技(600584)",
     "长电科技(600584)分析报告__20260525.pdf"),
    ("603019_中科曙光_深度分析_20260525.md", "中科曙光(603019)",
     "中科曙光(603019)分析报告__20260525.pdf"),
    ("601689_拓普集团_深度分析_20260525.md", "拓普集团(601689)",
     "拓普集团(601689)分析报告__20260525.pdf"),
    ("000967_盈峰环境_深度分析_20260525.md", "盈峰环境(000967)",
     "盈峰环境(000967)分析报告__20260525.pdf"),
    ("601727_上海电气_深度分析_20260525.md", "上海电气(601727)",
     "上海电气(601727)分析报告__20260525.pdf"),
    ("600114_东睦股份_深度分析_20260525.md", "东睦股份(600114)",
     "东睦股份(600114)分析报告__20260525.pdf"),
    ("301075_多瑞医药_深度分析_20260525.md", "多瑞医药(301075)",
     "多瑞医药(301075)分析报告__20260525.pdf"),
]


def preflight():
    """Check date consistency across all 8 MD reports.

    Verifies: (a) all report date lines say 2026年5月25日
              (b) all filenames contain 20260525
    Returns (ok: bool, report: str).
    """
    errors = []
    for md_name, _, _ in STOCKS:
        md_path = os.path.join(BASE_MD, md_name)
        if not os.path.exists(md_path):
            errors.append(f"MISSING: {md_name}")
            continue

        # Check filename date
        if "20260525" not in md_name:
            errors.append(f"FILENAME DATE: {md_name}")

        # Check report date line
        with open(md_path, 'r', encoding='utf-8') as f:
            head = f.read(500)
        if "2026年5月25日" not in head:
            errors.append(f"REPORT DATE: {md_name}")

    if errors:
        print("[PREFLIGHT] FAIL — date inconsistency detected:")
        for e in errors:
            print(f"  - {e}")
        return False, "\n".join(errors)

    print("[PREFLIGHT] PASS — all 8 reports dated 2026-05-25")
    return True, "OK"


if __name__ == "__main__":
    # Gate: date consistency check
    ok, report = preflight()
    if not ok:
        print("\nAborting: fix date inconsistencies before generating PDFs.")
        sys.exit(1)

    edge = find_edge()
    success = 0
    fail = 0

    for md_name, subdir, pdf_name in STOCKS:
        md_path = os.path.join(BASE_MD, md_name)
        pdf_dir = os.path.join(BASE_PDF, subdir)
        os.makedirs(pdf_dir, exist_ok=True)
        pdf_path = os.path.join(pdf_dir, pdf_name)
        print(f"\n[{subdir}] {md_name}")
        if convert(md_path, pdf_path, edge):
            success += 1
        else:
            fail += 1

    print(f"\n{'='*50}")
    print(f"Done: {success} OK, {fail} FAIL")
    sys.exit(0 if fail == 0 else 1)
