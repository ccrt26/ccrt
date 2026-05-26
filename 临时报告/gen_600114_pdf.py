"""Generate PDF for 600114 deep analysis report — MD → HTML → Edge headless PDF."""
import subprocess, os, time

md_path = r"c:\Users\34269\Documents\Claude\股票分析\临时报告\600114_东睦股份_深度分析_20260524.md"
html_path = r"c:\Users\34269\Documents\Claude\股票分析\临时报告\600114_东睦股份_深度分析_20260524.html"
pdf_path = r"c:\Users\34269\Documents\Claude\股票分析\临时报告\600114_东睦股份_深度分析_20260524.pdf"

import markdown

with open(md_path, "r", encoding="utf-8") as f:
    md_content = f.read()

# Convert MD to HTML body
body_html = markdown.markdown(md_content, extensions=["tables", "fenced_code"])

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

full_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<style>{css}</style>
<title>600114 东睦股份 深度分析报告</title>
</head>
<body>
{body_html}
</body>
</html>"""

with open(html_path, "w", encoding="utf-8") as f:
    f.write(full_html)

print(f"HTML written: {html_path} ({len(full_html)} chars)")

# Edge headless PDF
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

print(f"Using Edge: {edge}")

html_uri = "file:///" + html_path.replace("\\", "/")
cmd = [edge, "--headless", "--disable-gpu", f"--print-to-pdf={pdf_path}", "--no-pdf-header-footer", html_uri]
result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
time.sleep(2)

if os.path.exists(pdf_path):
    size_kb = os.path.getsize(pdf_path) / 1024
    print(f"SUCCESS: PDF generated ({size_kb:.0f} KB)")
    print(f"Path: {pdf_path}")
else:
    print(f"FAILED: rc={result.returncode}")
    if result.stderr:
        print(f"Stderr: {result.stderr[:500]}")
