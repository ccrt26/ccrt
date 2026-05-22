"""Verify card scores match table scores in the report HTML"""
import re

with open(r'C:\Users\34269\Documents\Claude\股票分析\临时回溯\daily_report_20260521.html', 'r', encoding='utf-8') as f:
    html = f.read()

# Card scores (精选推荐)
card_scores = re.findall(r'c-scr">(\d+)<span>/100', html)
print(f"精选推荐卡片分数: {card_scores}")

# Table section: find all rows between 全部标的评分表 and next section
table_section = html.split('全部标的评分表')[1]
rows = table_section.split('<tr>')

table_totals = []
for row in rows[2:]:  # skip header and empty first split
    tds = row.split('</td>')
    if len(tds) >= 16:
        # TotalScore is at index 15 (0-based)
        total_td = tds[15]
        if '>' in total_td:
            val = total_td.split('>')[-1].strip()
            try:
                table_totals.append(int(val))
            except ValueError:
                pass

print(f"全部标的评分表前5总分: {table_totals[:5]}")

if card_scores == [str(s) for s in table_totals[:5]]:
    print("✅ 完全一致！精选推荐卡片分数 = 全部标的评分表总分")
else:
    print("❌ 不一致")
    print(f"  卡片: {card_scores}")
    print(f"  表格: {table_totals[:5]}")
