"""Cross-file stock pool consistency checker.

Code level: L0 (tool/data)
Checks that all known stock pool references match pigeon_config.json (the single source of truth).
"""
import json
import os
import sys
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PIGEON_CONFIG = os.path.join(ROOT, "代码文件", "信鸽信息采集", "pigeon_config.json")
DAILY_CMD = os.path.join(ROOT, ".claude", "commands", "日报.md")
BATCH_PDF = os.path.join(ROOT, "代码文件", "tools", "batch_gen_keystock_pdfs.py")
DAILY_PARSER = os.path.join(ROOT, "代码文件", "重点股票", "Invoke-DailyReportParser.py")


def load_authoritative_pool():
    with open(PIGEON_CONFIG, 'r', encoding='utf-8') as f:
        data = json.load(f)
    stocks = data.get("target_stocks", data) if isinstance(data, dict) else data
    if isinstance(stocks, dict):
        stocks = stocks.get("target_stocks", [])
    return {s["code"] for s in stocks if isinstance(s, dict) and "code" in s}


def check_daily_cmd(expected_count: int):
    """Check 日报.md for hardcoded stock count references."""
    if not os.path.exists(DAILY_CMD):
        return {"file": DAILY_CMD, "status": "MISSING", "detail": "文件不存在"}

    with open(DAILY_CMD, 'r', encoding='utf-8') as f:
        content = f.read()

    hardcoded = re.findall(r'[8８]\s*(?:只|份|个)', content)
    if hardcoded:
        return {
            "file": DAILY_CMD,
            "status": "FAIL",
            "detail": f"仍含硬编码数字: {hardcoded}"
        }
    return {"file": DAILY_CMD, "status": "PASS", "detail": "零硬编码"}


def check_batch_pdf(expected_codes: set):
    """Check batch_gen_keystock_pdfs.py stocks list."""
    if not os.path.exists(BATCH_PDF):
        return {"file": BATCH_PDF, "status": "MISSING", "detail": "文件不存在"}

    with open(BATCH_PDF, 'r', encoding='utf-8') as f:
        content = f.read()

    # Extract stock codes from STOCKS list
    codes_in_file = set(re.findall(r'"(\d{6})_', content))
    missing = expected_codes - codes_in_file
    extra = codes_in_file - expected_codes

    if missing or extra:
        return {
            "file": BATCH_PDF,
            "status": "WARN",
            "detail": f"与pigeon_config不一致: 缺失={missing}, 多余={extra}"
        }
    return {"file": BATCH_PDF, "status": "PASS", "detail": "一致"}


def check_daily_parser(expected_codes: set):
    """Check Invoke-DailyReportParser.py STOCK_MAP."""
    if not os.path.exists(DAILY_PARSER):
        return {"file": DAILY_PARSER, "status": "MISSING", "detail": "文件不存在"}

    with open(DAILY_PARSER, 'r', encoding='utf-8') as f:
        content = f.read()

    codes_in_file = set(re.findall(r"'(\d{6})'", content))
    missing = expected_codes - codes_in_file
    extra = codes_in_file - expected_codes

    if missing or extra:
        return {
            "file": DAILY_PARSER,
            "status": "FAIL",
            "detail": f"STOCK_MAP与pigeon_config不一致: 缺失={missing}, 多余={extra}"
        }
    return {"file": DAILY_PARSER, "status": "PASS", "detail": f"{len(codes_in_file)}只一致"}


def main():
    quiet = "--quiet" in sys.argv

    try:
        expected = load_authoritative_pool()
    except Exception as e:
        print(json.dumps({"consistent": False, "error": str(e)}, ensure_ascii=False))
        sys.exit(1)

    if not quiet:
        print(f"权威源 pigeon_config.json: {len(expected)}只")

    results = [
        check_daily_cmd(len(expected)),
        check_batch_pdf(expected),
        check_daily_parser(expected),
    ]

    failures = [r for r in results if r["status"] == "FAIL"]
    warnings = [r for r in results if r["status"] == "WARN"]

    if not quiet:
        for r in results:
            icon = "✅" if r["status"] == "PASS" else ("⚠️" if r["status"] == "WARN" else "❌")
            print(f"{icon} {os.path.basename(r['file'])}: {r['detail']}")

    consistent = len(failures) == 0
    output = {
        "consistent": consistent,
        "authoritative_count": len(expected),
        "results": results,
        "failures": len(failures),
        "warnings": len(warnings),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2) if not quiet else "")
    sys.exit(0 if consistent else 1)


if __name__ == "__main__":
    main()
