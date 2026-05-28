"""Batch generate PDFs for all key stock deep analysis reports — MD → HTML → Edge headless PDF."""
import subprocess, os, time
import markdown

base = r"c:\Users\34269\Documents\Claude\股票分析\临时报告"

reports = [
    "601689_拓普集团_深度分析_20260525",
    "301075_多瑞医药_深度分析_20260525",
    "603019_中科曙光_深度分析_20260525",
    "600036_招商银行_深度分析_20260525",
    "000967_盈峰环境_深度分析_20260525",
    "601727_上海电气_深度分析_20260525",
    "600584_长电科技_深度分析_20260525",
]

css = """
body {
    font-family: "Microsoft YaHei", "SimSun", sans-serif;
    font-size: 12pt;
    line-height: 1.8;
    color: #222;
    max-width: 800px;
    margin: 0 auto;
    padding: 40px;
}
h1 { font-size: 20pt; border-bottom: 2px solid #1a1a2e; padding-bottom: 8px; color: #1a1a2e; }
h2 { font-size: 15pt; color: #16213e; margin-top: 30px; border-bottom: 1px solid #ddd; padding-bottom: 5px; }
h3 { font-size: 13pt; color: #333; margin-top: 20px; }
table { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 10pt; }
th { background: #1a1a2e; color: #fff; padding: 6px 8px; text-align: left; }
td { border: 1px solid #ddd; padding: 5px 8px; }
tr:nth-child(even) { background: #f8f8f8; }
code { font-family: "Microsoft YaHei", monospace; font-size: 10pt; background: #f0f0f0; padding: 2px 4px; }
pre { background: #f4f4f4; padding: 12px; border-left: 3px solid #1a1a2e; overflow-x: auto; font-size: 10pt; line-height: 1.5; }
blockquote { border-left: 3px solid #ccc; padding-left: 16px; color: #666; margin: 12px 0; }
strong { color: #1a1a2e; }
hr { border: none; border-top: 1px solid #eee; margin: 30px 0; }
p { margin: 8px 0; }
"""

edge_options = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\google-chrome.exe",
    r"C:\Program Files\Microsoft\Edge\Application\google-chrome.exe",
]
edge = None
for p in edge_options:
    if os.path.exists(p):
        edge = p
        break
if not edge:
    print("Edge not found!")
    exit(1)

for name in reports:
    md_path = os.path.join(base, f"{name}.md")
    html_path = os.path.join(base, f"{name}.html")
    pdf_path = os.path.join(base, f"{name}.pdf")

    if not os.path.exists(md_path):
        print(f"[SKIP] {name} — MD not found")
        continue

    # MD → HTML
    with open(md_path, "r", encoding="utf-8") as f:
        md_content = f.read()
    body = markdown.markdown(md_content, extensions=["tables", "fenced_code"])
    full_html = f"<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><style>{css}</style></head><body>{body}</body></html>"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(full_html)

    # HTML → PDF via Edge
    html_uri = "file:///" + html_path.replace("\\", "/")
    cmd = [edge, "--headless", "--disable-gpu", f"--print-to-pdf={pdf_path}", "--no-pdf-header-footer", html_uri]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    time.sleep(1.5)

    if os.path.exists(pdf_path):
        size_kb = os.path.getsize(pdf_path) / 1024
        print(f"[OK] {name} → {size_kb:.0f} KB")
    else:
        print(f"[FAIL] {name} — rc={result.returncode}")

print("\nDone!")
