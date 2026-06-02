#!/usr/bin/env python3
"""build_tools.py — Unified document build tools

Replaces: build_docx.ps1 (×3), gen_pdf.ps1, gen_eval_pdf.ps1,
          gen_keystock_pdf.ps1, generate_quality_dashboard.ps1,
          _extract_docx.ps1, gen_monthly_report.ps1, gen_doc_v2.ps1

Thin wrapper around md_to_docx.py and convert_md_to_pdf.py.
Code level: L0
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent.parent)
TOOLS_DIR = os.path.join(ROOT, "代码文件", "tools")


def build_docx(md_path, docx_path=None):
    """Convert .md → .docx using python-docx."""
    if docx_path is None:
        docx_path = md_path.rsplit(".", 1)[0] + ".docx"
    script = os.path.join(TOOLS_DIR, "md_to_docx.py")
    if not os.path.exists(script):
        print(f"ERROR: md_to_docx.py not found at {script}")
        sys.exit(1)
    result = subprocess.run(
        [sys.executable, script, md_path, docx_path],
        capture_output=True, text=True, cwd=ROOT
    )
    if result.returncode != 0:
        print(f"ERROR: {result.stderr}")
        sys.exit(1)
    print(f"DOCX generated: {docx_path}")


def build_pdf(md_path, pdf_path=None):
    """Convert .md → .pdf via HTML + Chrome headless."""
    if pdf_path is None:
        pdf_path = md_path.rsplit(".", 1)[0] + ".pdf"
    script = os.path.join(TOOLS_DIR, "convert_md_to_pdf.py")
    if not os.path.exists(script):
        print(f"ERROR: convert_md_to_pdf.py not found at {script}")
        sys.exit(1)
    result = subprocess.run(
        [sys.executable, script, md_path, pdf_path],
        capture_output=True, text=True, cwd=ROOT
    )
    if result.returncode != 0:
        print(f"ERROR: {result.stderr}")
        sys.exit(1)
    print(f"PDF generated: {pdf_path}")


def build_both(md_path):
    """Build both .docx and .pdf from .md source."""
    build_docx(md_path)
    build_pdf(md_path)


def main():
    parser = argparse.ArgumentParser(description="Unified document build tools")
    parser.add_argument("action", choices=["docx", "pdf", "both"], help="Build target")
    parser.add_argument("input", help="Input .md file path")
    parser.add_argument("--output", "-o", default="", help="Output file path")
    args = parser.parse_args()

    md_path = args.input
    if not os.path.isabs(md_path):
        md_path = os.path.join(ROOT, md_path)
    if not os.path.exists(md_path):
        print(f"ERROR: Input file not found: {md_path}")
        sys.exit(1)

    out_path = args.output if args.output else None

    if args.action == "docx":
        build_docx(md_path, out_path)
    elif args.action == "pdf":
        build_pdf(md_path, out_path)
    elif args.action == "both":
        build_both(md_path)


if __name__ == "__main__":
    main()
