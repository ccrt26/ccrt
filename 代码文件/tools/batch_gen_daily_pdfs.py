"""Batch convert v3.5 daily report MD files to PDF via HTML + Chrome headless.
Usage: python batch_gen_daily_pdfs.py
Code level: L0 (tool/data)
"""
import os, re, sys, time, subprocess

try:
    import markdown
except ImportError:
    markdown = None

STOCK_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                          '重点股票', '股票报告')

STOCKS = [
    ('东睦股份', '600114'),
    ('中科曙光', '603019'),
    ('多瑞医药', '301075'),
    ('拓普集团', '601689'),
    ('盈峰环境', '000967'),
    ('上海电气', '601727'),
    ('科大讯飞', '002230'),
    ('德力佳', '603092'),
    ('百邦科技', '300736'),
    ('先导智能', '300450'),
]

DATE = '20260529'

# ── v3.5 Daily Report CSS (matches 东睦股份 template) ──
CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:"Microsoft YaHei","微软雅黑",sans-serif;color:#333;background:#f0f2f5;font-size:13px}
.report-page{max-width:210mm;margin:0 auto;background:#fff;padding:15mm 18mm;box-shadow:0 2px 10px rgba(0,0,0,0.1)}
.header{background:linear-gradient(135deg,#1a1a2e,#16213e);color:#fff;padding:32px 30px;border-radius:10px;margin-bottom:20px}
.header h1{font-size:26px;margin-bottom:10px;letter-spacing:1px}
.header .subtitle{font-size:17px;line-height:2.0;opacity:1.0;font-weight:400}
.section{margin:18px 0}
.section h2{font-size:18px;color:#16213e;border-bottom:2px solid #1a1a2e;padding-bottom:6px;margin-bottom:12px}
.section h3{font-size:15px;color:#333;margin:10px 0 6px}
table{width:100%;border-collapse:collapse;font-size:12px;margin:8px 0 14px}
th{background:#1a1a2e;color:#fff;padding:8px 10px;text-align:center;font-weight:600}
td{padding:6px 10px;border:1px solid #e0e0e0;text-align:center}
tr:nth-child(even){background:#f8f9fa}
blockquote{background:#f8f9fa;border-left:4px solid #1a1a2e;padding:10px 14px;margin:10px 0;color:#555;font-size:12.5px}
blockquote p{margin:4px 0}
hr{border:none;border-top:1px solid #ddd;margin:18px 0}
strong{color:#1a1a2e}
.disclaimer{margin-top:24px;border-top:1px solid #ddd;padding-top:12px;font-size:11px;color:#999;line-height:1.8}
.note-box{background:#fff8e1;border-left:4px solid #f39c12;padding:10px 14px;margin:10px 0;font-size:12px}
.warn-box{background:#fde8e8;border-left:4px solid #e74c3c;padding:10px 14px;margin:10px 0;font-size:12px}
.info-box{background:#e8f0fe;border-left:4px solid #2980b9;padding:10px 14px;margin:10px 0;font-size:12px}
.good-box{background:#e8f5e9;border-left:4px solid #27ae60;padding:10px 14px;margin:10px 0;font-size:12px}
.up{color:#e74c3c;font-weight:600}
.down{color:#27ae60;font-weight:600}
h4{font-size:14px;color:#16213e;margin:12px 0 6px}
p{margin:6px 0;line-height:1.6}
ul,ol{margin:6px 0 6px 20px;line-height:1.6}
a{color:#2980b9;text-decoration:none}
@page{margin:12mm 10mm}@media print{body{background:#fff}.report-page{box-shadow:none;padding:8mm 10mm}}
"""


def find_chrome():
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/usr/bin/chromium",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    for name in ["google-chrome", "chromium"]:
        try:
            result = subprocess.run(["which", name], capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass
    return None


def md_to_html_body(md_text):
    """Convert markdown to HTML body."""
    if markdown:
        html = markdown.markdown(md_text, extensions=['tables', 'fenced_code'])
    else:
        html = simple_md_to_html(md_text)
    return html


def simple_md_to_html(text):
    """Basic markdown→HTML fallback (no python markdown lib)."""
    lines = text.split('\n')
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        s = line.strip()

        if not s:
            out.append('')
            i += 1
            continue

        if re.match(r'^---\s*$', s):
            out.append('<hr>')
            i += 1
            continue

        # Headers
        m = re.match(r'^(#{1,6})\s+(.+)$', s)
        if m:
            lvl = len(m.group(1))
            txt = _inline(m.group(2))
            out.append(f'<h{lvl}>{txt}</h{lvl}>')
            i += 1
            continue

        # Tables
        if '|' in s and s.startswith('|'):
            out.append('<table>')
            first = True
            while i < len(lines) and '|' in lines[i] and lines[i].strip().startswith('|'):
                cells = [c.strip() for c in lines[i].split('|')[1:-1]]
                if all(re.match(r'^:?-+:?$', c) for c in cells):
                    i += 1
                    continue
                tag = 'th' if first else 'td'
                out.append('<tr>' + ''.join(f'<{tag}>{_inline(c)}</{tag}>' for c in cells) + '</tr>')
                first = False
                i += 1
            out.append('</table>')
            continue

        # Blockquotes
        if s.startswith('> '):
            bq = []
            while i < len(lines) and lines[i].strip().startswith('> '):
                bq.append(lines[i].strip()[2:])
                i += 1
            content = '<br>'.join(_inline(l) for l in bq)
            out.append(f'<blockquote><p>{content}</p></blockquote>')
            continue

        # Unordered lists
        if re.match(r'^- (.+)$', s):
            out.append('<ul>')
            while i < len(lines) and re.match(r'^- (.+)$', lines[i].strip()):
                it = re.match(r'^- (.+)$', lines[i].strip()).group(1)
                out.append(f'<li>{_inline(it)}</li>')
                i += 1
            out.append('</ul>')
            continue

        # Plain paragraph
        out.append(f'<p>{_inline(s)}</p>')
        i += 1

    return '\n'.join(out)


def _inline(text):
    """Apply inline markdown formatting."""
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2">\1</a>', text)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    return text


def convert_one(md_path, pdf_path):
    """Convert single MD to HTML+PDF. Returns True on success."""
    if not os.path.exists(md_path):
        print(f'  SKIP: MD not found: {md_path}')
        return False

    edge = find_chrome()
    if not edge:
        print('  ERROR: Chrome not found')
        return False

    with open(md_path, 'r', encoding='utf-8') as f:
        md_text = f.read()

    # Extract title from first h1
    title_match = re.search(r'^#\s+(.+)$', md_text, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else '重点分析日报'

    # Extract subtitle from blockquote after h1
    sub_match = re.search(r'^# .+\n\n> \*\*日期\*\*：(.+?)$', md_text, re.MULTILINE)
    subtitle = sub_match.group(1).strip() if sub_match else ''

    body_html = md_to_html_body(md_text)

    full_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>{CSS}</style>
</head>
<body>
<div class="report-page">
<div class="header">
<h1>{title}</h1>
<div class="subtitle">{subtitle}</div>
</div>
{body_html}
</div>
</body>
</html>"""

    # Write HTML
    html_path = pdf_path.replace('.pdf', '.html')
    os.makedirs(os.path.dirname(html_path), exist_ok=True)
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(full_html)

    # Convert to PDF via Edge headless
    abs_html = os.path.abspath(html_path)
    abs_pdf = os.path.abspath(pdf_path)
    html_uri = "file:///" + abs_html.replace("\\", "/")

    cmd = [
        edge, "--headless", "--disable-gpu",
        f"--print-to-pdf={abs_pdf}",
        "--no-pdf-header-footer",
        html_uri,
    ]
    subprocess.run(cmd, capture_output=True, timeout=30)
    time.sleep(1.5)

    if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 5000:
        size_kb = os.path.getsize(pdf_path) / 1024
        print(f'  OK: PDF {size_kb:.0f} KB')
        return True
    else:
        print(f'  FAIL: PDF not generated')
        return False


def main():
    success = 0
    total = len(STOCKS)
    for name, code in STOCKS:
        folder = f'{name}({code})'
        md_path = os.path.join(STOCK_DIR, folder, f'{name}({code})日报_{DATE}.md')
        pdf_path = os.path.join(STOCK_DIR, folder, f'{name}({code})日报_{DATE}.pdf')
        print(f'{name}({code}):')
        if convert_one(md_path, pdf_path):
            success += 1
    print(f'\nDone: {success}/{total} PDFs generated')
    return 0 if success == total else 1


if __name__ == '__main__':
    sys.exit(main())
