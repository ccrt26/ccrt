"""Batch fetch financial data for all key stocks via 东方财富 RPT_LICO_FN_CPD API."""
import urllib.request
import urllib.parse
import json

stocks = [
    ("603019", "中科曙光"),
    ("301075", "多瑞医药"),
    ("601689", "拓普集团"),
    ("600036", "招商银行"),
    ("000967", "盈峰环境"),
    ("601727", "上海电气"),
    ("600584", "长电科技"),
]

base_url = "https://datacenter.eastmoney.com/securities/api/data/v1/get"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://data.eastmoney.com/",
}

results = {}

for code, name in stocks:
    market = "SZ" if code.startswith(("0", "3")) else "SH"
    secucode = f"{code}.{market}"
    encoded = urllib.parse.quote(secucode)

    url = f"{base_url}?reportName=RPT_LICO_FN_CPD&columns=ALL&filter=(SECUCODE=%22{encoded}%22)&pageSize=8&sortColumns=NOTICE_DATE&sortTypes=-1"

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("success") and data.get("result") and data["result"].get("data"):
                results[code] = data["result"]["data"]
                print(f"[OK] {code} {name} — {len(data['result']['data'])} periods")
            else:
                print(f"[EMPTY] {code} {name} — no data returned")
                results[code] = None
    except Exception as e:
        print(f"[FAIL] {code} {name} — {e}")
        results[code] = None

# Save to JSON
output_path = r"c:\Users\34269\Documents\Claude\股票分析\临时报告\batch_financials.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"\nSaved to {output_path}")

# Print key fields for each stock
key_fields = ["REPORT_DATE", "TOTAL_OPERATE_INCOME", "PARENT_NETPROFIT",
              "WEIGHTAVG_ROE", "XSMLL", "BASIC_EPS", "DEDUCT_BASIC_EPS",
              "MGJYXJJE", "BPS", "NOTICE_DATE"]

for code, name in stocks:
    periods = results.get(code)
    if not periods:
        continue
    print(f"\n=== {code} {name} ===")
    for p in periods[:4]:  # latest 4 periods
        row = {f: p.get(f, "-") for f in key_fields}
        print(f"  {row['REPORT_DATE']} | 营收:{row['TOTAL_OPERATE_INCOME']} | 净利:{row['PARENT_NETPROFIT']} | ROE:{row['WEIGHTAVG_ROE']} | 毛利率:{row['XSMLL']} | EPS:{row['BASIC_EPS']} | 扣非EPS:{row['DEDUCT_BASIC_EPS']} | 经营CF:{row['MGJYXJJE']} | BPS:{row['BPS']}")
