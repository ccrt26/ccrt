#!/usr/bin/env python3
"""Formalize 2026-05-29 key-stock deep analysis reports.

Hard rule: deep-analysis PDFs are generated only through
Markdown -> original CSS HTML -> Chrome PDF. Do not use ReportLab here.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = ROOT / "代码文件" / "tools"
DEEP_DIR = ROOT / "重点股票" / "深度分析" / "深度分析报告"
DATE = "20260529"

sys.path.insert(0, str(TOOLS_DIR))
from convert_md_to_pdf import convert, find_edge, normalize_markdown_tables  # noqa: E402

STOCKS = [
    ("600114", "东睦股份"),
    ("603019", "中科曙光"),
    ("301075", "多瑞医药"),
    ("601689", "拓普集团"),
    ("000967", "盈峰环境"),
    ("601727", "上海电气"),
    ("002230", "科大讯飞"),
    ("603092", "德力佳"),
    ("300736", "百邦科技"),
    ("300450", "先导智能"),
]

FORBIDDEN = [
    "baseline_id",
    "baseline_date",
    "valid_until",
    "G5",
    "G6",
    "G7",
    "G8",
    "delta_vs_baseline",
    "decision_impact",
    "score_history",
    "signal_evaluator",
    "risk_flags",
    "risk_factors",
    "not_applicable_reason",
    "数据增强补充",
    "日报承接",
]

CODEX_DIR = ROOT / "重点股票" / "深度分析" / "临时PDF审阅版" / "20260601_codex_full"
CODEX_DONGMU_MD = CODEX_DIR / "东睦股份(600114)_深度分析_保留原版增强_codex_20260601.md"
CODEX_DONGMU_JSON = CODEX_DIR / "东睦股份(600114)_系统附录_codex_20260601.json"


def paths_for(code: str, name: str) -> dict[str, Path]:
    stock_dir = DEEP_DIR / f"{name}({code})"
    stem = f"{name}({code})深度分析报告_{DATE}"
    return {
        "dir": stock_dir,
        "md": stock_dir / f"{stem}.md",
        "html": stock_dir / f"{stem}.html",
        "pdf": stock_dir / f"{stem}.pdf",
        "json": stock_dir / f"{stem}_系统附录.json",
    }


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def backup(path: Path, backup_root: Path) -> None:
    if not path.exists():
        return
    dest = backup_root / path.relative_to(ROOT)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest)


def normalize_md(path: Path, backup_root: Path) -> None:
    original = read_text(path)
    normalized = normalize_markdown_tables(original)
    lines = normalized.splitlines()
    out: list[str] = []
    blank = 0
    for line in lines:
        if line.strip() == "":
            blank += 1
            if blank <= 1:
                out.append(line)
        else:
            blank = 0
            out.append(line)
    normalized = "\n".join(out).rstrip() + "\n"
    if normalized != original:
        backup(path, backup_root)
        write_text(path, normalized)


def check_forbidden_text(path: Path) -> list[str]:
    text = read_text(path)
    return [term for term in FORBIDDEN if term in text]


def html_table_stats(path: Path) -> tuple[int, int]:
    html = read_text(path)
    return html.count("<table"), html.count("<p>|")


def pdf_forbidden(path: Path) -> list[str]:
    try:
        from pypdf import PdfReader
    except Exception:
        return []
    text = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    return [term for term in FORBIDDEN if term in text]


def pdf_producer(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except Exception:
        return ""
    meta = PdfReader(str(path)).metadata or {}
    return str(meta.get("/Producer", ""))


def copy_dongmu_codex(p: dict[str, Path], backup_root: Path) -> None:
    if not CODEX_DONGMU_MD.exists():
        raise FileNotFoundError(f"Codex 东睦母版不存在: {CODEX_DONGMU_MD}")
    backup(p["md"], backup_root)
    shutil.copy2(CODEX_DONGMU_MD, p["md"])
    if CODEX_DONGMU_JSON.exists():
        backup(p["json"], backup_root)
        shutil.copy2(CODEX_DONGMU_JSON, p["json"])


def sync_docs() -> None:
    script = ROOT / "代码文件" / "信鸽信息采集" / "generate_portal.py"
    subprocess.run([sys.executable, str(script)], cwd=str(ROOT), check=True)


def deploy_web() -> None:
    script = ROOT / "代码文件" / "tools" / "deploy_web.py"
    subprocess.run([sys.executable, str(script)], cwd=str(ROOT), check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Formalize 10 key-stock deep reports for 20260529")
    parser.add_argument("--execute", action="store_true", help="Overwrite formal files")
    parser.add_argument("--deploy", action="store_true", help="Deploy web after docs sync")
    parser.add_argument("--no-portal", action="store_true", help="Skip docs portal sync")
    args = parser.parse_args()

    print("=== 20260529 重点股票深度分析正式化 ===")
    print(f"MODE: {'EXECUTE' if args.execute else 'DRY-RUN'}")
    print("PDF route: Markdown -> original CSS HTML -> Chrome PDF")

    if not args.execute:
        for code, name in STOCKS:
            p = paths_for(code, name)
            print(f"  {name}({code}): {'OK' if p['md'].exists() else 'MISSING'} {p['md']}")
        print("\nDry-run done. Add --execute to overwrite formal files.")
        return 0

    browser = find_edge()
    if not browser:
        print("FAIL: Chrome/Edge executable not found", file=sys.stderr)
        return 2
    print(f"Browser: {browser}")

    backup_root = ROOT / "临时报告" / f"formalize_20260529_backup_{time.strftime('%Y%m%d_%H%M%S')}"
    backup_root.mkdir(parents=True, exist_ok=True)
    print(f"Backup: {backup_root}")

    failures: list[str] = []
    results: list[dict[str, object]] = []

    for code, name in STOCKS:
        p = paths_for(code, name)
        print(f"\n[{name}({code})]")
        if not p["md"].exists():
            failures.append(f"{name}({code}) missing MD")
            print("  FAIL missing MD")
            continue
        for key in ("md", "html", "pdf", "json"):
            backup(p[key], backup_root)

        if code == "600114":
            copy_dongmu_codex(p, backup_root)
            print("  Copied Codex-confirmed Dongmu MD/JSON")

        normalize_md(p["md"], backup_root)

        bad_md = check_forbidden_text(p["md"])
        if bad_md:
            failures.append(f"{name}({code}) forbidden in MD: {bad_md}")
            print(f"  FAIL forbidden in MD: {bad_md}")
            continue

        if not convert(str(p["md"]), str(p["pdf"]), edge_path=browser):
            failures.append(f"{name}({code}) PDF generation failed")
            continue

        bad_html = check_forbidden_text(p["html"])
        bad_pdf = pdf_forbidden(p["pdf"])
        tables, pipe_p = html_table_stats(p["html"])
        producer = pdf_producer(p["pdf"])

        if bad_html:
            failures.append(f"{name}({code}) forbidden in HTML: {bad_html}")
        if bad_pdf:
            failures.append(f"{name}({code}) forbidden in PDF: {bad_pdf}")
        if tables <= 0:
            failures.append(f"{name}({code}) table_count=0")
        if pipe_p > 0:
            failures.append(f"{name}({code}) pipe paragraph count={pipe_p}")
        if "ReportLab" in producer:
            failures.append(f"{name}({code}) PDF producer is ReportLab")

        status = "FAIL" if any(x.startswith(f"{name}({code})") for x in failures) else "PASS"
        result = {
            "code": code,
            "name": name,
            "status": status,
            "tables": tables,
            "pipe_paragraphs": pipe_p,
            "pdf_kb": round(p["pdf"].stat().st_size / 1024),
            "producer": producer,
        }
        results.append(result)
        print(f"  {status}: tables={tables}, pipe_p={pipe_p}, pdf={result['pdf_kb']}KB, producer={producer}")

    if failures:
        print("\n=== FAILURES ===")
        for item in failures:
            print(f"  - {item}")
        print("\nPortal/deploy skipped.")
        return 1

    if not args.no_portal:
        print("\n=== Sync docs portal ===")
        sync_docs()
        for code, _ in STOCKS:
            for fn in ("report.html", "report.pdf"):
                out = ROOT / "docs" / "deep_analysis" / code / DATE / fn
                if not out.exists():
                    print(f"FAIL: docs missing {out}", file=sys.stderr)
                    return 1
        print("docs/deep_analysis synced.")

    if args.deploy:
        print("\n=== Deploy web ===")
        deploy_web()
    else:
        print("\nDeploy skipped. Rerun with --deploy after CF env vars are ready.")

    print("\n=== SUMMARY ===")
    for r in results:
        print(f"{r['name']}({r['code']}): {r['status']} tables={r['tables']} pdf={r['pdf_kb']}KB")
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
