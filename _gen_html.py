#!/usr/bin/env python3
import markdown
md_path = r"c:\Users\34269\Documents\Claude\股票分析\重点股票\深度分析\东睦股份(600114)深度分析报告_20260526.md"
html_path = r"c:\Users\34269\Documents\Claude\股票分析\重点股票\深度分析\东睦股份(600114)深度分析报告_20260526.html"
with open(md_path, 'r', encoding='utf-8') as f:
    md_content = f.read()
css = """
<style>
body { font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif; max-width: 960px; margin: 0 auto; padding: 20px; color: #2c3e50; line-height: 1.8; font-size: 15px; }
h1 { color: #1a1a2e; border-bottom: 3px solid #1a1a2e; padding-bottom: 10px; text-align: center; }
h2 { color: #16213e; border-bottom: 2px solid #16213e; padding-bottom: 8px; margin-top: 30px; }
h3 { color: #1a1a2e; margin-top: 20px; }
h4 { color: #2c3e50; margin-top: 15px; }
table { border-collapse: collapse; width: 100%; margin: 15px 0; font-size: 14px; }
th { background: #1a1a2e; color: white; padding: 10px 12px; text-align: center; }
td { border: 1px solid #ddd; padding: 8px 12px; vertical-align: top; }
tr:nth-child(even) { background: #f8f9fa; }
blockquote { border-left: 4px solid #16213e; margin: 15px 0; padding: 10px 20px; background: #f0f3f8; color: #555; }
pre { background: #1a1a2e; color: #e0e0e0; padding: 15px; border-radius: 5px; overflow-x: auto; font-size: 14px; line-height: 1.7; }
pre code { background: none; color: inherit; padding: 0; }
hr { border: none; border-top: 1px solid #ddd; margin: 20px 0; }
@media print { body { font-size: 12px; } h1 { font-size: 22px; } h2 { font-size: 18px; } }
</style>
"""
html_body = markdown.markdown(md_content, extensions=['tables', 'fenced_code', 'codehilite'])
html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>东睦股份(600114)深度分析报告 v1.2 2026-05-26</title>
{css}
</head>
<body>
{html_body}
</body>
</html>"""
with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html)
print(f"HTML: {len(html)} bytes")
