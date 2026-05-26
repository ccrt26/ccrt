"""Batch convert v2 daily brief MD files to PDF via Edge headless."""
import os, subprocess, re, sys

base = '重点股票/股票报告'
stocks = [
    ('中科曙光', '603019'),
    ('拓普集团', '601689'),
    ('东睦股份', '600114'),
    ('多瑞医药', '301075'),
    ('盈峰环境', '000967'),
    ('上海电气', '601727'),
    ('长电科技', '600584'),
]

CSS = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<style>
body { font-family: "Microsoft YaHei", sans-serif; font-size: 12pt; line-height: 1.8; color: #333; max-width: 800px; margin: 0 auto; padding: 20px; }
h1 { color: #1a1a2e; font-size: 20pt; border-bottom: 3px solid #1a1a2e; padding-bottom: 8px; }
h2 { color: #16213e; font-size: 15pt; border-bottom: 2px solid #16213e; padding-bottom: 5px; margin-top: 24px; }
h3 { color: #16213e; font-size: 13pt; margin-top: 18px; }
p { margin: 6px 0; }
table { border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 10pt; }
th { background: #1a1a2e; color: white; padding: 8px 6px; text-align: center; }
td { border: 1px solid #ccc; padding: 6px; }
tr:nth-child(even) { background: #f8f8f8; }
blockquote { border-left: 4px solid #e74c3c; background: #fff5f5; padding: 8px 16px; margin: 12px 0; }
blockquote p { margin: 4px 0; }
ul { margin: 6px 0; padding-left: 24px; }
li { margin: 2px 0; line-height: 1.6; }
strong { color: #1a1a2e; }
a { color: #16213e; }
hr { border: none; border-top: 1px solid #ddd; margin: 20px 0; }
</style>
</head>
<body>
__CONTENT__
</body>
</html>"""


def _inline_format(text):
    """Apply bold and link formatting to inline text."""
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2">\1</a>', text)
    return text


def _is_table_row(line):
    return '|' in line and line.strip().startswith('|')


def _is_alignment_row(cells):
    return all(re.match(r'^:?-+:?$', c) for c in cells)


def md_to_html(md_text):
    """Convert markdown to HTML with proper state-machine parsing."""
    lines = md_text.split('\n')
    result = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Empty line → skip (HTML collapsing handles spacing)
        if not stripped:
            result.append('')
            i += 1
            continue

        # HR: standalone --- line (NOT inside tables)
        if re.match(r'^---\s*$', stripped):
            result.append('<hr>')
            i += 1
            continue

        # Headers
        m = re.match(r'^#### (.+)$', stripped)
        if m:
            result.append(f'<h4>{_inline_format(m.group(1))}</h4>')
            i += 1
            continue
        m = re.match(r'^### (.+)$', stripped)
        if m:
            result.append(f'<h3>{_inline_format(m.group(1))}</h3>')
            i += 1
            continue
        m = re.match(r'^## (.+)$', stripped)
        if m:
            result.append(f'<h2>{_inline_format(m.group(1))}</h2>')
            i += 1
            continue
        m = re.match(r'^# (.+)$', stripped)
        if m:
            result.append(f'<h1>{_inline_format(m.group(1))}</h1>')
            i += 1
            continue

        # Tables: group consecutive table rows
        if _is_table_row(line):
            result.append('<table>')
            first_row = True
            while i < len(lines) and _is_table_row(lines[i]):
                cells = [c.strip() for c in lines[i].split('|')[1:-1]]
                if _is_alignment_row(cells):
                    i += 1
                    continue
                tag = 'th' if first_row else 'td'
                result.append('<tr>' + ''.join(
                    f'<{tag}>{_inline_format(c)}</{tag}>' for c in cells
                ) + '</tr>')
                first_row = False
                i += 1
            result.append('</table>')
            continue

        # Blockquotes: group consecutive > lines into one blockquote
        if stripped.startswith('> '):
            bq_lines = []
            while i < len(lines) and lines[i].strip().startswith('> '):
                bq_lines.append(lines[i].strip()[2:])  # remove '> '
                i += 1
            content = '<br>'.join(_inline_format(l) for l in bq_lines)
            result.append(f'<blockquote><p>{content}</p></blockquote>')
            continue

        # Unordered lists: group consecutive - items
        if re.match(r'^- (.+)$', stripped):
            result.append('<ul>')
            while i < len(lines) and re.match(r'^- (.+)$', lines[i].strip()):
                item_text = re.match(r'^- (.+)$', lines[i].strip()).group(1)
                result.append(f'<li>{_inline_format(item_text)}</li>')
                i += 1
            result.append('</ul>')
            continue

        # Plain text → wrap in paragraph
        result.append(f'<p>{_inline_format(stripped)}</p>')
        i += 1

    html = '\n'.join(result)
    return CSS.replace('__CONTENT__', html)


def main():
    date_str = '20260526'
    success = 0
    for name, code in stocks:
        md_path = os.path.join(base, f'{name}({code})', f'重点关注股票日报_{date_str}.md')
        if not os.path.exists(md_path):
            print(f'SKIP {name}({code}): MD not found')
            continue

        with open(md_path, 'r', encoding='utf-8') as f:
            md_content = f.read()

        html = md_to_html(md_content)
        html_path = os.path.join(base, f'{name}({code})', f'重点关注股票日报_{date_str}.html')
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html)

        pdf_path = os.path.join(base, f'{name}({code})', f'重点关注股票日报_{date_str}.pdf')
        abs_html = os.path.abspath(html_path)
        abs_pdf = os.path.abspath(pdf_path)

        msedge = r'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
        cmd = f'"{msedge}" --headless --disable-gpu --no-pdf-header-footer --print-to-pdf="{abs_pdf}" "file:///{abs_html}"'
        r = subprocess.run(cmd, shell=True, capture_output=True, timeout=30)

        if r.returncode == 0 and os.path.exists(pdf_path):
            size_kb = os.path.getsize(pdf_path) / 1024
            print(f'[OK] {name}({code}): PDF {size_kb:.0f}KB')
            success += 1
        else:
            err = r.stderr.decode('utf-8', errors='ignore')[:300]
            print(f'[FAIL] {name}({code}): ret={r.returncode} err={err}')

    print(f'\nDone: {success}/{len(stocks)} PDFs generated')


if __name__ == '__main__':
    main()
