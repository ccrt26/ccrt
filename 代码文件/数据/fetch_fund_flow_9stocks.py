# LEGACY_ONLY_DO_NOT_USE_IN_DAILY_REPORT — Eastmoney API已废弃，请使用Tushare moneyflow
# 此脚本保留仅供历史参考，禁止在日报流程中调用
#!/usr/bin/env python3
"""玉夜数据采集脚本 — 9只股票四档资金 2026-06-01"""
import urllib.request, json, time, os, sys

CODES = ['601727','603019','301075','601689','000967','002230','603092','300450','300736']
NAMES = {'601727':'上海电气','603019':'中科曙光','301075':'多瑞医药','601689':'拓普集团','000967':'盈峰环境','002230':'科大讯飞','603092':'德力佳','300450':'先导智能','300736':'百邦科技'}
DIR = os.path.dirname(os.path.abspath(__file__))
FUND_DIR = os.path.join(DIR, 'fund_flow_cache')
ALL_FILE = os.path.join(FUND_DIR, '20260601_all.json')

os.makedirs(FUND_DIR, exist_ok=True)
results = {}
if os.path.exists(ALL_FILE):
    with open(ALL_FILE) as f:
        results = json.load(f)

remaining = [c for c in CODES if c not in results or results[c].get('main_force_net', 0) == 0]
if not remaining:
    print('ALL_DONE: 全部9只已采集')
    sys.exit(0)

print(f'REMAINING: {len(remaining)}/{len(CODES)} — {remaining}')

for code in remaining:
    time.sleep(20)
    prefix = '0' if code.startswith(('0','3')) else '1'
    url = f'https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get?secid={prefix}.{code}&fields1=f1,f2,f3&fields2=f51,f52,f53,f54,f55,f56&lmt=3'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://data.eastmoney.com/'})
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read().decode('utf-8'))
        klines = d.get('data', {}).get('klines', [])
        if klines:
            latest = klines[-1].split(',')
            record = {'date': latest[0], 'main_force_net': int(latest[1]), 'small_net': int(latest[2]), 'mid_net': int(latest[3]), 'large_net': int(latest[4]), 'super_large_net': int(latest[5])}
            results[code] = record
            cache_file = os.path.join(FUND_DIR, f'{code}.json')
            cached = []
            if os.path.exists(cache_file):
                with open(cache_file) as f:
                    cached = json.load(f)
            if not any(r.get('date') == record['date'] for r in cached):
                cached.append(record)
            with open(cache_file, 'w') as f:
                json.dump(cached, f, ensure_ascii=False)
            sl = record['super_large_net']/10000
            lg = record['large_net']/10000
            print(f'  OK {code} {NAMES[code]}: 超大单{sl:+,.0f}万 大单{lg:+,.0f}万')
        else:
            print(f'  EMPTY {code} {NAMES[code]}')
    except Exception as e:
        print(f'  FAIL {code} {NAMES[code]}: {str(e)[:50]}')

with open(ALL_FILE, 'w') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

remaining_after = [c for c in CODES if c not in results or results[c].get('main_force_net', 0) == 0]
print(f'RESULT: {len(results)}/9 collected, {len(remaining_after)} remaining')
if remaining_after:
    sys.exit(1)
else:
    # All done — write signal for 阿黑
    signal_file = os.path.join(os.path.dirname(DIR), '..', '.claude', 'signal_fund_flow_ready.json')
    os.makedirs(os.path.dirname(signal_file), exist_ok=True)
    with open(signal_file, 'w') as f:
        json.dump({'signal': 'fund_flow_ready', 'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'), 'stocks': len(results)}, f)
    print('SIGNAL: fund_flow_ready — 阿黑可开始重新生成日报')
    sys.exit(0)
