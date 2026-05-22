#!/usr/bin/env python3
"""Convert optimized report HTML to PDF"""
import os
from playwright.sync_api import sync_playwright

root = r"C:\Users\34269\Documents\Claude\股票分析"
html_path = os.path.join(root, "临时回溯", "optimized_report.html")
pdf_path = os.path.join(root, "临时回溯", "optimized_report.pdf")

uri = "file:///" + html_path.replace("\\", "/")
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto(uri)
    page.pdf(path=pdf_path, format="A4", print_background=True,
             margin={"top": "10mm", "bottom": "10mm", "left": "10mm", "right": "10mm"})
    browser.close()

size_kb = os.path.getsize(pdf_path) / 1024
print(f"PDF: {pdf_path} ({size_kb:.1f} KB)")
