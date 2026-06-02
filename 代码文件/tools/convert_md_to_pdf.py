"""Convert Markdown deep analysis report to PDF via HTML + Edge headless.

Usage:
    python convert_md_to_pdf.py <input.md> <output.pdf>

Code level: L0 (tool/data)
Design doc: 审计报告/架构设计/design_md_to_pdf_toolchain.md
"""
import os
import re
import sys
import time
import subprocess
import markdown

# ── Brand CSS (报告样式基线_v1.2) ──────────────────────────
CSS = """
@page { size: A4; margin: 15mm 18mm; }
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: "Microsoft YaHei", "微软雅黑", "SimHei", sans-serif;
    color: #333; font-size: 13px; line-height: 1.7;
    padding: 15mm 18mm; max-width: 210mm; margin: 0 auto;
}
h1 { font-size: 22px; color: #1a1a2e; border-bottom: 2px solid #1a1a2e;
     padding-bottom: 8px; margin: 0 0 12px 0; }
h2 { font-size: 17px; color: #16213e; border-bottom: 1.5px solid #16213e;
     padding-bottom: 5px; margin: 20px 0 10px 0; }
h3 { font-size: 14px; color: #333; margin: 14px 0 6px 0; }
h4 { font-size: 13px; color: #555; margin: 10px 0 4px 0; }
blockquote { background: #f0f2f5; border-left: 4px solid #1a1a2e;
             padding: 8px 14px; margin: 10px 0; font-size: 12px; color: #555; }
table { width: 100%; border-collapse: collapse; margin: 10px 0 16px;
        font-size: 12px; page-break-inside: avoid; }
th { background: #1a1a2e; color: #fff; padding: 7px 10px;
     text-align: center; font-weight: normal; }
td { padding: 5px 10px; border: 1px solid #ddd; text-align: center; }
tr:nth-child(even) { background: #f8f9fa; }
strong { color: #16213e; }
pre { font-family: "Microsoft YaHei", "微软雅黑", "SimHei", sans-serif;
      font-size: 12px; margin: 8px 0; white-space: pre-wrap; }
code { background: #f0f2f5; padding: 1px 5px; border-radius: 3px; font-size: 12px;
       font-family: "Microsoft YaHei", "微软雅黑", "SimHei", sans-serif; }
hr { border: none; border-top: 1px solid #e0e0e0; margin: 16px 0; }
p { margin: 5px 0; }
ul, ol { margin: 5px 0 5px 20px; }
li { margin: 2px 0; }
.disclaimer { font-size: 11px; color: #999; border-top: 1px solid #eee;
              margin-top: 24px; padding-top: 10px; }
"""


def find_edge():
    """Locate a Chromium-family browser executable. Returns None if not found."""
    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def normalize_markdown_tables(md_text):
    """Remove blank lines that split contiguous Markdown table rows.

    Some AI-generated reports insert a blank line between every table row.
    Python-Markdown then treats each row as a paragraph instead of a table,
    which makes the PDF drift away from the 2026-05-29 baseline layout.
    """
    lines = md_text.splitlines()
    out = []
    for i, line in enumerate(lines):
        if line.strip() == "" and out:
            prev = out[-1].strip()
            j = i + 1
            while j < len(lines) and lines[j].strip() == "":
                j += 1
            nxt = lines[j].strip() if j < len(lines) else ""
            if (
                prev.startswith("|")
                and prev.endswith("|")
                and nxt.startswith("|")
                and nxt.endswith("|")
            ):
                continue
        out.append(line)
    return "\n".join(out)


def md_to_html_body(md_text):
    """Convert markdown text to styled HTML body."""
    md_text = normalize_markdown_tables(md_text)
    html = markdown.markdown(md_text, extensions=['tables', 'fenced_code'])
    html = re.sub(r'(<table>)', r'<div style="overflow-x:auto;">\1', html)
    html = re.sub(r'(</table>)', r'\1</div>', html)
    return html


def convert(md_path, pdf_path, edge_path=None):
    """Convert single MD file to PDF via HTML intermediate + Edge headless.

    Returns True on success, False on failure.
    Side effect: writes an .html file alongside the .pdf for debugging.
    """
    if not os.path.exists(md_path):
        print(f"  ERROR: MD not found: {md_path}")
        return False

    edge = edge_path or find_edge()
    if not edge:
        print("  ERROR: Edge browser not found")
        return False

    with open(md_path, 'r', encoding='utf-8') as f:
        md_text = f.read()

    title_match = re.search(r'^#\s+(.+)$', md_text, re.MULTILINE)
    title = title_match.group(1) if title_match else "深度分析报告"

    body_html = md_to_html_body(md_text)
    full_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>{title}</title>
<style>{CSS}</style>
</head>
<body>
{body_html}
<p class="disclaimer">免责声明：以上分析基于公开数据和分析框架，仅供参考，不构成投资建议。市场有风险，投资需谨慎。</p>
</body>
</html>"""

    html_path = pdf_path.replace('.pdf', '.html')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(full_html)

    os.makedirs(os.path.dirname(pdf_path), exist_ok=True)

    html_uri = "file:///" + os.path.abspath(html_path).replace("\\", "/")
    cmd = [
        edge, "--headless", "--disable-gpu",
        f"--print-to-pdf={os.path.abspath(pdf_path)}",
        "--no-pdf-header-footer",
        html_uri,
    ]
    subprocess.run(cmd, capture_output=True, timeout=30)
    time.sleep(1.5)

    if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 5000:
        size_kb = os.path.getsize(pdf_path) / 1024
        print(f"  OK: {os.path.basename(pdf_path)} ({size_kb:.0f} KB)")
        return True
    else:
        print(f"  FAIL: PDF not generated or too small")
        return False


if __name__ == '__main__':
    if len(sys.argv) >= 3:
        ok = convert(sys.argv[1], sys.argv[2])
        sys.exit(0 if ok else 1)
    else:
        print("Usage: python convert_md_to_pdf.py <input.md> <output.pdf>")
        sys.exit(1)
