"""Convert key stock HTML report to PDF using Edge headless."""
import subprocess
import os
import time

html = r"C:\Users\34269\Documents\Claude\股票分析\重点股票\汇总\重点股票分析报告_20260522.html"
pdf = r"C:\Users\34269\Documents\Claude\股票分析\重点股票\汇总\重点股票分析报告_20260522.pdf"

print(f"HTML: {html}")
print(f"HTML exists: {os.path.exists(html)}")
print(f"Existing PDF: {os.path.exists(pdf)}, size: {os.path.getsize(pdf)/1024:.0f}KB")

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

print(f"Found Edge: {edge}")

html_uri = "file:///" + html.replace("\\", "/")
cmd = [
    edge,
    "--headless",
    "--disable-gpu",
    f"--print-to-pdf={pdf}",
    "--no-pdf-header-footer",
    html_uri,
]

print(f"Running Edge headless...")
result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
time.sleep(3)

if os.path.exists(pdf):
    size_kb = os.path.getsize(pdf) / 1024
    print(f"SUCCESS: PDF generated ({size_kb:.0f} KB)")
    print(f"Path: {pdf}")
else:
    print(f"FAILED: rc={result.returncode}")
    if result.stderr:
        print(f"Stderr: {result.stderr[:500]}")
