#!/usr/bin/env python3
"""
P0-H: 渲染一致性闸门 — 检查日报 HTML/PDF 与渲染管线合规。

支持 --html-only 跳过 PDF 检查以适配 HTML-only 自动生成模式。

用法:
  python3 scripts/check_daily_render_contract.py --date 20260604
  python3 scripts/check_daily_render_contract.py --date 20260604 --code 600114
  python3 scripts/check_daily_render_contract.py --date 20260611 --code 600114 --html-only
"""
import argparse, json, os, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "重点股票" / "股票报告"
PIGEON_CFG = ROOT / "代码文件" / "信鸽信息采集" / "pigeon_config.json"


def get_pool():
    stocks = []
    if PIGEON_CFG.exists():
        try:
            cfg = json.loads(PIGEON_CFG.read_text(encoding="utf-8"))
            for s in cfg.get("target_stocks", []):
                c = str(s.get("code", ""))
                n = s.get("name", "")
                if c and n:
                    stocks.append((c, n))
            if stocks:
                return stocks
        except Exception:
            pass
    # Fallback to report dirs
    for subdir in sorted(REPORT_DIR.iterdir()):
        if not subdir.is_dir():
            continue
        m = re.match(r'(.+)\((\d{6})\)', subdir.name)
        if m:
            stocks.append((m.group(2), m.group(1)))
    return stocks


def check_one(code, name, date_str, issues, html_only=False):
    prefix = f"{name}({code})日报_{date_str}"
    sd = REPORT_DIR / f"{name}({code})"

    # H1: All files exist
    required_exts = [(".md", "MD"), (".json", "JSON"), (".html", "HTML")]
    if not html_only:
        required_exts.append((".pdf", "PDF"))
    for ext, label in required_exts:
        if not (sd / f"{prefix}{ext}").exists():
            issues.append(f"H1:{code} {label}缺失")

    # H2/H3: HTML check
    html_path = sd / f"{prefix}.html"
    if html_path.exists():
        html = html_path.read_text(encoding="utf-8", errors="ignore")
        if "padding: 15mm 18mm" not in html:
            issues.append(f"H2:{code} HTML缺失convert_md_to_pdf body padding")
        if "font-size: 12px" not in html:
            issues.append(f"H2:{code} HTML缺失table font-size 12px")
        if '<div class="page"' in html or '.page{' in html:
            issues.append(f"H3:{code} HTML含禁止的.page手写布局")
        if html_path.stat().st_size < 5000:
            issues.append(f"H8:{code} HTML过小({html_path.stat().st_size} bytes)")

    # H4: MD table column consistency
    md_path = sd / f"{prefix}.md"
    if md_path.exists():
        md = md_path.read_text(encoding="utf-8", errors="ignore")
        lines = md.split("\n")
        for i, line in enumerate(lines):
            if line.startswith("|") and not line.startswith("|:"):
                cols = len([c for c in line.split("|") if c.strip() or c.strip() == ""])
                if i > 0:
                    prev = lines[i-1]
                    if prev.startswith("|") and not prev.startswith("|:"):
                        prev_cols = len([c for c in prev.split("|") if c.strip() or c.strip() == ""])
                        if cols != prev_cols:
                            issues.append(f"H4:{code} MD L{i+1}列数{cols}≠L{i}列数{prev_cols}")
                            break

    # H5: JSON fund_flow mirrors MD
    json_path = sd / f"{prefix}.json"
    if json_path.exists() and md_path.exists():
        try:
            sj = json.loads(json_path.read_text(encoding="utf-8"))
            ff = sj.get("fund_flow_4level", {}) or {}
            mf_disp = str(ff.get("main_force_display", ""))
            md = md_path.read_text(encoding="utf-8", errors="ignore")
            if mf_disp and mf_disp not in md.replace("**", ""):
                issues.append(f"H5:{code} JSON fund_flow={mf_disp}未出现在MD")
        except Exception:
            pass

    # H6: HTML mtime > MD mtime
    if md_path.exists() and html_path.exists():
        if html_path.stat().st_mtime < md_path.stat().st_mtime:
            issues.append(f"H6:{code} HTML早于MD(MD更新后HTML未重建)")

    # H7/H8: PDF checks; skipped in html_only mode
    pdf_path = sd / f"{prefix}.pdf"
    if not html_only:
        if html_path.exists() and pdf_path.exists():
            if pdf_path.stat().st_mtime < html_path.stat().st_mtime:
                issues.append(f"H7:{code} PDF早于HTML")
        if pdf_path.exists():
            sz = pdf_path.stat().st_size
            if sz < 102400:
                issues.append(f"H8:{code} PDF仅{sz//1024}KB(<100KB)")


def check_all(date_str, html_only=False):
    issues = []
    stocks = get_pool()
    if not stocks:
        issues.append("H0:空股票池")
        return issues
    for code, name in stocks:
        check_one(code, name, date_str, issues, html_only=html_only)
    return issues


def check_single(code, date_str, html_only=False):
    issues = []
    for c, n in get_pool():
        if c == code:
            check_one(c, n, date_str, issues, html_only=html_only)
            return issues
    issues.append(f"H0:股票{code}未找到")
    return issues


def main():
    ap = argparse.ArgumentParser(description="P0-H: 渲染一致性闸门")
    ap.add_argument("--date", required=True)
    ap.add_argument("--code", default="", help="单票模式")
    ap.add_argument("--html-only", action="store_true", help="跳过PDF检查")
    args = ap.parse_args()

    if args.code:
        issues = check_single(args.code, args.date, html_only=args.html_only)
    else:
        issues = check_all(args.date, html_only=args.html_only)

    if issues:
        for i in issues:
            print(f"  ❌ {i}")
        print(f"\n结果: {len(issues)} BLOCK")
        sys.exit(2)
    else:
        check_type = f"({args.code})" if args.code else ""
        suffix = " [HTML-only]" if args.html_only else ""
        print(f"✅ P0-H: 渲染一致性检查通过{check_type}{suffix}")
        sys.exit(0)


if __name__ == "__main__":
    main()
