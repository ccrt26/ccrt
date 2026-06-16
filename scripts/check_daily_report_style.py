#!/usr/bin/env python3
"""check_daily_report_style.py — 日报HTML样式母版检查
检查每份日报HTML是否使用标准母版CSS。
禁止极简CSS、禁止自定义样式、禁止绕过母版。
"""
import argparse, os, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_REPORT_OVERRIDE = os.environ.get("REPORT_ROOT_OVERRIDE")
REPORT_DIR = Path(_REPORT_OVERRIDE) if _REPORT_OVERRIDE else ROOT / "重点股票" / "股票报告"

# 母版CSS关键片段
REQUIRED = [
    ('h1深色底线', r'h1[^{]*\{[^}]*color:\s*#1a1a2e'),
    ('h2深色底线', r'h2[^{]*\{[^}]*color:\s*#16213e'),
    ('blockquote灰底左边线', r'blockquote\s*\{[^}]*background:\s*#f0f2f5'),
    ('table完整样式', r'table\s*\{[^}]*border-collapse:\s*collapse'),
    ('th深色表头', r'th\s*\{[^}]*background:\s*#1a1a2e'),
    ('td边框', r'td\s*\{[^}]*border:\s*1px\s+solid\s+#ddd'),
    ('表格横向容器', r'<div style="overflow-x:auto;"><table>'),

    ('斑马纹', r'tr:nth-child\(even\)\s*\{[^}]*background:\s*#f8f9fa'),
]

# 禁用极简CSS片段
BANNED = [
    ('极简CSS', r'@page\s*\{[^}]*margin:\s*15mm\s+18mm[^}]*\}\*\s*\{[^}]*margin:\s*0[^}]*}[^}]*body\s*\{'),
]

def check_file(path):
    text = path.read_text(encoding='utf-8', errors='ignore')
    issues = []
    
    # 检查母版CSS
    for name, pattern in REQUIRED:
        if not re.search(pattern, text, re.DOTALL):
            issues.append(f'缺失母版CSS: {name}')
    
    # 检查禁用CSS
    for name, pattern in BANNED:
        if re.search(pattern, text, re.DOTALL):
            issues.append(f'禁用CSS: {name}')
    
    # 检查是否有任何style标签
    
    return issues

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', required=True)
    args = ap.parse_args()
    date_compact = args.date.replace('-', '')
    
    html_files = sorted(REPORT_DIR.glob(f'*/*日报_{date_compact}.html'))
    if not html_files:
        print(f'日报_style_check: BLOCK — 未找到 {date_compact} HTML文件')
        return 2
    
    all_pass = True
    for p in html_files:
        issues = check_file(p)
        if issues:
            print(f'{p.parent.name}: BLOCK')
            for i in issues:
                print(f'  - {i}')
            all_pass = False
        else:
            print(f'{p.parent.name}: PASS')
    
    if len(html_files) != 10:
        print(f'日报_style_check: BLOCK — 找到{len(html_files)}份HTML，应为10份')
        return 2
    
    if all_pass:
        print('\n日报_style_check: PASS')
        return 0
    else:
        print('\n日报_style_check: BLOCK')
        return 2

if __name__ == '__main__':
    sys.exit(main())
