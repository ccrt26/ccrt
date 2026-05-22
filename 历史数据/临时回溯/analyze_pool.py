"""Analyze stock pool composition"""
import json
from collections import Counter

with open(r'C:\Users\34269\Documents\Claude\股票分析\代码文件\数据\data_final.json', 'r', encoding='utf-8-sig') as f:
    stocks = json.load(f)

# By industry
ind = Counter(s['Industry'] for s in stocks)
print('=== 行业分布 ===')
for k, v in ind.most_common():
    names = [s['Name'] for s in stocks if s['Industry'] == k]
    print('  %-8s (%2d只): %s' % (k, v, ', '.join(names)))

print()
print('=== 整体特征 ===')
prices = [s['Price'] for s in stocks]
print('  价格: %.2f ~ %.2f, 均值 %.2f' % (min(prices), max(prices), sum(prices)/len(prices)))
positive_pe = sum(1 for s in stocks if s['PE'] > 0)
negative_pe = sum(1 for s in stocks if s['PE'] < 0)
print('  PE: %d只盈利, %d只亏损' % (positive_pe, negative_pe))
chgs = [s['ChangePct'] for s in stocks]
print('  当日涨跌: %.2f%% ~ %.2f%%, 均值 %.2f%%' % (min(chgs), max(chgs), sum(chgs)/len(chgs)))
turns = [s['TurnoverRate'] for s in stocks]
print('  换手率: %.1f%% ~ %.1f%%, 均值 %.1f%%' % (min(turns), max(turns), sum(turns)/len(turns)))

# Market cap estimate (rough)
print()
print('=== 风格分布（按价格分层） ===')
high = [s for s in stocks if s['Price'] >= 50]
mid = [s for s in stocks if 15 <= s['Price'] < 50]
low = [s for s in stocks if s['Price'] < 15]
print('  高价股(>=50): %2d只 %s' % (len(high), ', '.join(s['Name'] for s in high)))
print('  中价股(15-50): %2d只 %s' % (len(mid), ', '.join(s['Name'] for s in mid)))
print('  低价股(<15): %2d只 %s' % (len(low), ', '.join(s['Name'] for s in low)))
