"""
Convert all 8 MD daily reports to HTML + PDF for 2026-05-26.
"""
import markdown, os, subprocess, json

BASE = r'c:\Users\34269\Documents\Claude\股票分析'
REPORT_BASE = os.path.join(BASE, '重点股票', '股票报告')

stocks = [
    ('东睦股份', '600114'),
    ('上海电气', '601727'),
    ('中科曙光', '603019'),
    ('多瑞医药', '301075'),
    ('拓普集团', '601689'),
    ('盈峰环境', '000967'),
    ('科大讯飞', '002230'),
    ('德力佳',   '603092'),
]

CSS = '''*{margin:0;padding:0;box-sizing:border-box}
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
'''

HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
{css}
</style>
</head>
<body>
<div class="report-page">
<div class="header">
<h1>{title}</h1>
<div class="subtitle">2026年5月26日（周一） | 数据截止：5/26收盘 | 版本: v1.2</div>
</div>
{body}
<div class="disclaimer">
<p>⚠️ <strong>风险提示</strong>：本报告由AI自动生成，基于公开数据源和量化分析框架，仅供参考，不构成投资建议。</p>
<p>方法论版本：v1.2 | 管线自动评分已作废，基本面评分由深度分析独立判断。</p>
</div>
</div>
</body>
</html>'''

for name, code in stocks:
    folder = os.path.join(REPORT_BASE, f'{name}({code})')
    md_path = os.path.join(folder, f'{name}({code})日报_20260526.md')
    html_path = os.path.join(folder, f'{name}({code})日报_20260526.html')
    pdf_path = os.path.join(folder, f'{name}({code})日报_20260526.pdf')

    if not os.path.exists(md_path):
        print(f'SKIP {name}: MD not found')
        continue

    # Read MD
    with open(md_path, 'r', encoding='utf-8') as f:
        md_content = f.read()

    # Extract title (first line)
    lines = md_content.split('\n')
    title = lines[0].strip('# ') if lines[0].startswith('#') else f'{name}({code}) 重点分析日报'

    # Convert MD to HTML (remove the first line which is the title since header handles it)
    md_body = '\n'.join(lines[1:])
    html_body = markdown.markdown(md_body, extensions=['tables', 'fenced_code'])

    # Add CSS classes for up/down
    html_body = html_body.replace('>+', '><span class="up">+')
    html_body = html_body.replace('>-', '><span class="down">-')
    # Fix the span closing
    import re
    html_body = re.sub(r'(<span class="up">\+[\d.]+%?)', r'\1</span>', html_body)
    html_body = re.sub(r'(<span class="down">-[\d.]+%?)', r'\1</span>', html_body)

    # Wrap in template
    html = HTML_TEMPLATE.format(title=title, css=CSS, body=html_body)

    # Write HTML
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f'HTML: {html_path}')

    # Print to PDF using Edge
    try:
        abs_html = os.path.abspath(html_path)
        abs_pdf = os.path.abspath(pdf_path)
        result = subprocess.run([
            'msedge', '--headless', '--disable-gpu',
            f'--print-to-pdf={abs_pdf}',
            abs_html
        ], capture_output=True, text=True, timeout=30)
        if os.path.exists(pdf_path):
            size_kb = os.path.getsize(pdf_path) / 1024
            print(f'PDF: {pdf_path} ({size_kb:.0f}KB)')
        else:
            print(f'PDF FAILED: {result.stderr[:200]}')
    except Exception as e:
        print(f'PDF ERROR: {e}')

print('\nDone!')
