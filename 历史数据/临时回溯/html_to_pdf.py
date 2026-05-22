#!/usr/bin/env python3
"""Convert daily report HTML to PDF using Playwright Chromium"""

import os
from playwright.sync_api import sync_playwright

root = r"C:\Users\34269\Documents\Claude\股票分析"
html_path = os.path.join(root, "临时回溯", "daily_report_20260521.html")
pdf_path = os.path.join(root, "临时回溯", "daily_report_20260521.pdf")

uri = "file:///" + html_path.replace("\\", "/")

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto(uri)
    page.pdf(
        path=pdf_path,
        format="A4",
        landscape=True,
        print_background=True,
        margin={"top": "0mm", "bottom": "0mm", "left": "0mm", "right": "0mm"}
    )
    browser.close()

size_kb = os.path.getsize(pdf_path) / 1024
print(f"PDF generated: {pdf_path} ({size_kb:.1f} KB)")
