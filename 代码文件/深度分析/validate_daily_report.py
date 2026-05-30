#!/usr/bin/env python3
"""
日报质量闸门 v1.0 — 轻量5 P0 + 2 P1
用法:
    python validate_daily_report.py <report.md>
    python validate_daily_report.py --date YYYYMMDD
    python validate_daily_report.py --date YYYYMMDD --alert  # FAIL时写告警信号

Code level: L0
"""
import re, json, os, sys
from datetime import datetime
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent.parent)
SIGNAL_DIR = os.path.join(ROOT, ".claude")
REPORT_BASE = os.path.join(ROOT, "重点股票", "股票报告")

# P0: 5项必过
P0_CHECKS = {
    "盘面速读": r'## 一、今日盘面速读',
    "信号变化": r'## 二、信号变化',
    "基本面/策略触发": r'## 三、基本面|## 四、深度分析',
    "情景应对": r'## 五、明日情景应对',
    "OHLCV四日数据": r'收盘价.*\|.*\|.*\|.*\|',
    "情景应对有动作": r'止损|仓位|不?入场|观望|持有|减仓|清仓|买入|卖出',
}

# P1: 2项可WARN
P1_CHECKS = {
    "资金面数据": r'资金面|主力|北向|融资|净流入|净流出',
    "关键价位表": r'[RS]\d\s*[支撑阻]',
}


def validate_daily_report(report_path):
    """返回 (pass: bool, issues: list, warns: list)。"""
    issues, warns = [], []

    if not os.path.exists(report_path):
        return False, [f"文件不存在: {report_path}"], []

    with open(report_path, 'r', encoding='utf-8') as f:
        text = f.read()

    # P0
    p0_fails = []
    for name, pat in P0_CHECKS.items():
        if not re.search(pat, text):
            p0_fails.append(name)

    if p0_fails:
        issues.append(f"P0缺失: {', '.join(p0_fails)}")

    # P1
    p1_missing = [name for name, pat in P1_CHECKS.items() if not re.search(pat, text)]
    if len(p1_missing) > 1:
        issues.append(f"P1缺失{len(p1_missing)}项(>1): {', '.join(p1_missing)}")
    elif p1_missing:
        warns.append(f"P1缺失1项: {p1_missing[0]}")

    return len(issues) == 0, issues, warns


def validate_date_reports(date_str, write_alert=False):
    """批量校验指定日期的日报。"""
    if not os.path.isdir(REPORT_BASE):
        print(f"ERROR: {REPORT_BASE} not found")
        return 0, 0, 0

    total, passed, failed = 0, 0, 0
    fail_details = []

    for entry in sorted(os.listdir(REPORT_BASE)):
        entry_dir = os.path.join(REPORT_BASE, entry)
        if not os.path.isdir(entry_dir):
            continue
        for fname in sorted(os.listdir(entry_dir)):
            if date_str in fname and fname.endswith('.md') and '日报' in fname:
                path = os.path.join(entry_dir, fname)
                code_m = re.search(r'\((\d{6})\)', fname)
                code = code_m.group(1) if code_m else fname[:6]
                name_m = re.search(r'^(.+?)\(\d{6}\)', fname)
                name = name_m.group(1) if name_m else entry

                ok, issues, warns = validate_daily_report(path)
                total += 1
                if ok:
                    passed += 1
                    status = "PASS"
                    if warns:
                        status += f" (WARN: {'; '.join(warns)})"
                    print(f"  {status}: {code} {name}")
                else:
                    failed += 1
                    print(f"  FAIL: {code} {name} — {'; '.join(issues)}")
                    fail_details.append({
                        "code": code, "name": name,
                        "path": path, "issues": issues
                    })
                break

    print(f"\n闸门结果: {passed} PASS / {failed} FAIL / {total} total")

    if failed and write_alert:
        _write_daily_alert(date_str, fail_details)

    return passed, failed, total


def _write_daily_alert(date_str, fail_details):
    """写告警信号，飞书通知腰子。"""
    alert_file = os.path.join(SIGNAL_DIR, "signal_alert.json")
    payload = {
        "alert": "daily_report_fail",
        "severity": "P2",
        "date": date_str,
        "failed_count": len(fail_details),
        "failures": [{"code": f["code"], "name": f["name"],
                       "issues": f["issues"]} for f in fail_details],
        "recommend": f"腰子人工修复{len(fail_details)}只日报，下一交易日9:00前完成",
        "timestamp": datetime.now().isoformat(),
    }
    os.makedirs(SIGNAL_DIR, exist_ok=True)
    with open(alert_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"\n告警信号已写入: {alert_file}")


def main():
    if '--date' in sys.argv:
        idx = sys.argv.index('--date')
        date_str = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else datetime.now().strftime('%Y%m%d')
        write_alert = '--alert' in sys.argv
        print(f"日报闸门扫描: {date_str}")
        passed, failed, total = validate_date_reports(date_str, write_alert)
        sys.exit(0 if failed == 0 else 1)

    if len(sys.argv) < 2:
        print("Usage: python validate_daily_report.py <report.md>")
        print("       python validate_daily_report.py --date YYYYMMDD [--alert]")
        sys.exit(1)

    ok, issues, warns = validate_daily_report(sys.argv[1])
    if ok:
        print(f"PASS: {sys.argv[1]}")
    else:
        print(f"FAIL: {sys.argv[1]} — {'; '.join(issues)}")
    if warns:
        print(f"WARN: {'; '.join(warns)}")
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
