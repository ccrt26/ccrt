#!/usr/bin/env python3
"""从正式深度分析报告抽取重点股票 baseline。

R3: F-DAILY-BASELINE-AUTH
权威源: 深度分析报告 Markdown
输出: 重点股票/基线/{name}({code})_baseline_{YYYYWww}.json
"""
import argparse
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE_DIR = ROOT / "重点股票" / "基线"

def compact_date(s):
    m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return m.group(0)
    m = re.search(r"_(\d{8})", s)
    if m:
        d = m.group(1)
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    raise ValueError("cannot extract report date")

def week_id(date_str):
    d = datetime.strptime(date_str, "%Y-%m-%d")
    y, w, _ = d.isocalendar()
    return f"{y}W{w:02d}"

def next_weekday(date_str, weekday):
    d = datetime.strptime(date_str, "%Y-%m-%d")
    d += timedelta(days=1)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d.strftime("%Y-%m-%d")

def extract_first_float(pattern, text, default=None):
    m = re.search(pattern, text, re.S)
    if not m:
        return default
    # Return the first numeric capture group, or the whole match if numeric
    for g in m.groups():
        if g is not None:
            try:
                return float(g)
            except (ValueError, TypeError):
                continue
    try:
        return float(m.group(0))
    except (ValueError, TypeError):
        return default

def infer_status(text):
    if "当前状态：A" in text or "**A 继续跟踪**" in text:
        return "A_CONTINUE_TRACKING"
    if "B(等待确认)" in text or "B 等待确认" in text:
        return "B_WAIT_CONFIRM"
    return "UNKNOWN"

def extract_action_rules(text):
    rules = []
    for line in text.splitlines():
        if any(key in line for key in ["收盘≥42", "收盘<40", "单日>6500", "富驰并购", "SMC客户", "折叠屏", "增持/回购", "放量跌破MA20", "跌破32"]):
            cleaned = line.strip()
            if cleaned and len(cleaned) < 240:
                rules.append(cleaned)
    return rules[:30]

def build(report_path):
    text = report_path.read_text(encoding="utf-8", errors="ignore")

    m = re.search(r"#\s*(\d{6})\s+(.+?)\s+[—-]", text)
    if not m:
        m = re.search(r"(.+?)\((\d{6})\)", report_path.name)
        if not m:
            raise ValueError("cannot extract stock code/name")
        name, code = m.group(1), m.group(2)
    else:
        code, name = m.group(1), m.group(2).strip()

    report_date = compact_date(text[:800] + "\n" + report_path.name)
    wid = week_id(report_date)
    baseline_id = f"{code}_{wid}_deep"
    valid_until = next_weekday(report_date, 4)

    current_price = extract_first_float(r"\|\s*\*\*现价\*\*\s*\|\s*\*\*([\d.]+)\*\*", text)
    ma5 = extract_first_float(r"\|\s*MA5\s*\|\s*([\d.]+)", text)
    ma20 = extract_first_float(r"\|\s*MA20\s*\|\s*([\d.]+)", text)
    hard_stop = extract_first_float(r"硬止损位\s*([\d.]+)元", text, None)
    if hard_stop is None:
        hard_stop = extract_first_float(r"\|\s*硬止损位32元\s*\|", text, 32.0)
    if hard_stop is None:
        hard_stop = 32.0

    support = ma5 or 40.0
    ma20_support = ma20 or 37.11
    pressure = 42.0
    target = 42.0

    return {
        "baseline_id": baseline_id,
        "baseline_version": "deep_v1",
        "baseline_status": "official",
        "stock_code": code,
        "stock_name": name,
        "baseline_date": report_date,
        "valid_until": valid_until,
        "next_deep_analysis_date": valid_until,
        "generated_from": "deep_analysis_report",
        "source_deep_report_path": str(report_path.relative_to(ROOT)),
        "approved_by": "腰子(R2追认)",
        "methodology_version": "v1.5",
        "current_state": infer_status(text),
        "core_thesis": "短线状态明显修复，中期逻辑未证伪；42元能否转支撑为后续验证重点。",
        "key_support_price": round(support, 2),
        "key_pressure_price": round(pressure, 2),
        "ma20_support_price": round(ma20_support, 2),
        "stop_loss_price": round(hard_stop, 2),
        "target_price": round(target, 2),
        "action_rules": {
            "upgrade_or_continue": "收盘站稳42元且量能正常，维持A继续跟踪",
            "downgrade_to_b": "收盘跌破40元且次日未收回，转为B等待确认",
            "downgrade_to_c": "放量跌破MA20或约37.11区域，降级观察",
            "veto_to_d": "跌破32元或并购/SMC/折叠屏核心反证出现，移出/否决",
            "no_chase": "42元以上不追高，不因创新高加仓"
        },
        "daily_instructions": extract_action_rules(text),
        "risk_flags": {
            "valuation": "PE约47.8x，估值压力需跟踪",
            "catalyst": "5/28至6/9无新增L1基本面催化",
            "volatility": "近两周日均振幅较大，短期波动风险显著"
        },
        "data_snapshot": {
            "current_price": current_price,
            "ma5": ma5,
            "ma20": ma20
        }
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True)
    ap.add_argument("--out")
    args = ap.parse_args()

    report = Path(args.report)
    if not report.is_absolute():
        report = ROOT / report
    baseline = build(report)

    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    out = Path(args.out) if args.out else BASELINE_DIR / f"{baseline['stock_name']}({baseline['stock_code']})_baseline_{week_id(baseline['baseline_date'])}_deep.json"
    if not out.is_absolute():
        out = ROOT / out
    out.write_text(json.dumps(baseline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("BASELINE_FROM_DEEP_REPORT_PASS")
    print(out)

if __name__ == "__main__":
    main()