"""Batch convert all key stock HTML reports to PDF."""
import subprocess
import os
import time
import glob

base = r"C:\Users\34269\Documents\Claude\股票分析\重点股票\股票报告"

edge_options = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]
edge = None
for p in edge_options:
    if os.path.exists(p):
        edge = p
        break

if not edge:
    print("Edge not found!")
    exit(1)

# Find all 分析报告__20260522.html files
html_files = []
for root, dirs, files in os.walk(base):
    for f in files:
        if f.endswith("分析报告__20260522.html"):
            html_files.append(os.path.join(root, f))

print(f"Found {len(html_files)} HTML files to convert")

for html_path in sorted(html_files):
    pdf_path = html_path.replace(".html", ".pdf")
    html_uri = "file:///" + html_path.replace("\\", "/")

    stock_name = os.path.basename(os.path.dirname(html_path))
    print(f"\nConverting: {stock_name}...")

    cmd = [
        edge,
        "--headless",
        "--disable-gpu",
        f"--print-to-pdf={pdf_path}",
        "--no-pdf-header-footer",
        html_uri,
    ]

    result = subprocess.run(cmd, capture_output=True, timeout=30)
    time.sleep(1.5)

    if os.path.exists(pdf_path):
        size_kb = os.path.getsize(pdf_path) / 1024
        print(f"  OK: {os.path.basename(pdf_path)} ({size_kb:.0f} KB)")
    else:
        print(f"  FAIL: rc={result.returncode}")

print("\nDone!")
