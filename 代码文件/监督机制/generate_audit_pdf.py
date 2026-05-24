#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
铁律量化 · 审计报告PDF生成器
读取 audit_report_*.json → 生成四级审计PDF报告
用法: python generate_audit_pdf.py <json_path> [--output <pdf_path>]
"""

import json, sys, os
from datetime import datetime
from fpdf import FPDF

FONT_PATH = "C:/Windows/Fonts/msyh.ttc"
FONT_BOLD_PATH = "C:/Windows/Fonts/msyhbd.ttc"

BRAND = (26, 26, 46)        # #1a1a2e
GREEN = (39, 174, 96)       # #27ae60
RED = (231, 76, 60)         # #e74c3c
YELLOW = (241, 196, 15)     # #f1c40f
WHITE = (255, 255, 255)
GRAY = (100, 100, 100)
LIGHT_GRAY = (240, 240, 240)

LEVELS = [
    ("第一级 · 目标对齐审视", "月度", "A1-A7 项目产出是否服务核心目标？有没有跑偏？"),
    ("第二级 · 红线执行审计", "每日+每周", "规则红线的每一条是否被真正执行？"),
    ("第三级 · 成本审计", "每周", "API调用/缓存命中/Token消耗/文件膨胀有没有浪费？"),
    ("第四级 · 技术健康审计", "每日+每周", "Section A~G 七大板块 ~45项确定性检查"),
]

class AuditPDF(FPDF):
    def __init__(self):
        super().__init__(orientation='P', unit='mm', format='A4')
        self.add_font("YaHei", "", FONT_PATH)
        self.add_font("YaHei", "B", FONT_BOLD_PATH)
        self.set_auto_page_break(True, 18)

    def header_block(self, timestamp, mode, verdict):
        # Brand bar at top
        self.set_fill_color(*BRAND)
        self.rect(0, 0, 210, 42, 'F')

        self.set_y(10)
        self.set_text_color(*WHITE)
        self.set_font("YaHei", "B", 22)
        self.cell(0, 10, "铁律量化 · 综合审计报告", align='C', new_x="LMARGIN", new_y="NEXT")

        self.set_font("YaHei", "", 11)
        self.set_text_color(200, 200, 200)
        self.cell(0, 7, f"审计时间: {timestamp}    模式: {mode}", align='C', new_x="LMARGIN", new_y="NEXT")

        # Verdict badge
        self.set_y(46)
        v_colors = {"PASS": GREEN, "WARN": YELLOW, "FAIL": RED}
        vc = v_colors.get(verdict, GRAY)
        self.set_fill_color(*vc)
        self.set_text_color(*WHITE)
        self.set_font("YaHei", "B", 16)
        badge_text = {"PASS": "PASS  通过", "WARN": "WARN  警告", "FAIL": "FAIL  不通过"}
        self.cell(0, 11, badge_text.get(verdict, verdict), align='C', fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(6)

    def level_section(self, num, name, freq, desc, checks, level_status):
        self.set_fill_color(*BRAND)
        self.set_text_color(*WHITE)
        self.set_font("YaHei", "B", 13)
        level_title = f"  {name}"
        self.cell(0, 9, level_title, fill=True, new_x="LMARGIN", new_y="NEXT")

        self.set_text_color(*GRAY)
        self.set_font("YaHei", "", 9)
        self.cell(0, 6, f"  频率: {freq}    |    {desc}", new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

        if not checks:
            self.set_text_color(*GRAY)
            self.set_font("YaHei", "", 10)
            self.cell(0, 7, "  (暂无检查数据 — 待下次审计补齐)", new_x="LMARGIN", new_y="NEXT")
            self.ln(3)
            return

        header = ["检查项", "状态", "详情"]
        widths = [80, 24, 86]
        self.set_fill_color(*BRAND)
        self.set_text_color(*WHITE)
        self.set_font("YaHei", "B", 9)
        for i, h in enumerate(header):
            self.cell(widths[i], 7, f" {h}", border=0, fill=True)
        self.ln()

        for i, c in enumerate(checks):
            bg = LIGHT_GRAY if i % 2 == 0 else WHITE
            self.set_fill_color(*bg)
            status = c.get("status", "?")
            sc = {"PASS": GREEN, "WARN": YELLOW, "FAIL": RED}.get(status, GRAY)
            s_text = {"PASS": "PASS", "WARN": "WARN", "FAIL": "FAIL"}.get(status, "?")

            self.set_text_color(0, 0, 0)
            self.set_font("YaHei", "", 8)
            self.cell(widths[0], 6.5, f" {c.get('desc', '?')}", fill=True)

            self.set_text_color(*sc)
            self.set_font("YaHei", "B", 8)
            self.cell(widths[1], 6.5, f" {s_text}", fill=True)

            self.set_text_color(*GRAY)
            self.set_font("YaHei", "", 7.5)
            detail = c.get("detail", "")[:55]
            self.cell(widths[2], 6.5, f" {detail}", fill=True)
            self.ln()
        self.ln(4)

    def summary_table(self, total, n_pass, n_warn, n_fail):
        self.set_fill_color(*BRAND)
        self.set_text_color(*WHITE)
        self.set_font("YaHei", "B", 12)
        self.cell(0, 9, "  审计汇总", fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(3)

        labels = ["总检查项", "PASS  通过", "WARN  警告", "FAIL  失败"]
        values = [str(total), str(n_pass), str(n_warn), str(n_fail)]
        colors = [(0,0,0), GREEN, YELLOW, RED]

        col_w = 46
        self.set_x(14)
        for lbl, val, clr in zip(labels, values, colors):
            self.set_fill_color(245, 245, 245)
            self.set_text_color(*clr)
            self.set_font("YaHei", "B", 14)
            self.cell(col_w, 14, val, fill=True, align='C')
        self.ln()

        self.set_x(14)
        for lbl, _, _ in zip(labels, values, colors):
            self.set_fill_color(245, 245, 245)
            self.set_text_color(*GRAY)
            self.set_font("YaHei", "", 9)
            self.cell(col_w, 6, lbl, fill=True, align='C')
        self.ln(8)

    def footer(self):
        self.set_y(-16)
        self.set_text_color(180, 180, 180)
        self.set_font("YaHei", "", 7)
        self.cell(0, 5, f"铁律量化 旧影审计官 · 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", align='C')


def map_checks_to_levels(checks):
    """Map Section-based checks to the four audit levels."""
    l1, l2, l3, l4 = [], [], [], []

    for c in checks:
        sec = c.get("section", "")
        cid = c.get("id", "")

        if sec == "G" and cid == "1":
            l2.append(c)   # check_redlines → 红线执行
        elif sec in ("A", "B", "C", "D", "E", "F"):
            l4.append(c)   # Sections A-F → 技术健康
        elif sec == "G":
            l4.append(c)   # G-2, G-3 → 技术健康(集成检查)
        else:
            l4.append(c)

    return l1, l2, l3, l4


def get_level_status(checks):
    if not checks:
        return "NONE"
    has_fail = any(c.get("status") == "FAIL" for c in checks)
    has_warn = any(c.get("status") == "WARN" for c in checks)
    if has_fail:
        return "FAIL"
    if has_warn:
        return "WARN"
    return "PASS"


def main():
    if len(sys.argv) < 2:
        print("用法: python generate_audit_pdf.py <audit_json_path> [--output <pdf_path>]")
        sys.exit(1)

    json_path = sys.argv[1]
    output_path = sys.argv[sys.argv.index("--output") + 1] if "--output" in sys.argv else None

    if not os.path.exists(json_path):
        print(f"ERROR: JSON not found: {json_path}")
        sys.exit(1)

    with open(json_path, "r", encoding="utf-8-sig") as f:
        report = json.load(f)

    audit = report.get("audit", {})
    summary = report.get("summary", {})
    checks = report.get("checks", [])
    failures = report.get("failures", [])

    timestamp = audit.get("timestamp", "?")
    mode = audit.get("mode", "?")
    verdict = summary.get("overall_verdict", "?")
    total = summary.get("total_checks", 0)
    n_pass = summary.get("pass", 0)
    n_warn = summary.get("warn", 0)
    n_fail = summary.get("fail", 0)

    l1, l2, l3, l4 = map_checks_to_levels(checks)
    level_data = list(zip(LEVELS, [l1, l2, l3, l4]))

    pdf = AuditPDF()
    pdf.add_page()
    pdf.header_block(timestamp, mode, verdict)

    for i, ((name, freq, desc), l_checks) in enumerate(level_data):
        ls = get_level_status(l_checks) if l_checks else "NONE"
        pdf.level_section(i + 1, name, freq, desc, l_checks, ls)

    # Summary
    pdf.summary_table(total, n_pass, n_warn, n_fail)

    # Failure detail
    if failures:
        pdf.set_fill_color(*BRAND)
        pdf.set_text_color(*WHITE)
        pdf.set_font("YaHei", "B", 10)
        pdf.cell(0, 8, "  需关注的问题", fill=True, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
        pdf.set_text_color(*RED)
        pdf.set_font("YaHei", "", 9)
        for f_item in failures:
            pdf.cell(0, 6, f"  x  {f_item}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)

    if not output_path:
        base = os.path.splitext(json_path)[0]
        output_path = f"{base}.pdf"

    pdf.output(output_path)
    print(f"PDF saved: {output_path}")

    # Return verdict as exit code
    if verdict == "FAIL":
        sys.exit(1)
    elif verdict == "WARN":
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
