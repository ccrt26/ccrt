#!/usr/bin/env python3
"""
check_data_utilization.py - 数据运用合规检查 (Pre-Report Gate)
检查分析报告是否按《数据运用优化方案 v1.3》要求引用和使用管线数据。

用法:
  python3 check_data_utilization.py --report <path> --type <depth_analysis|daily>

退出码: 0=PASS, 1=FAIL, 2=脚本异常

L0 代码 — 正则匹配 + 计数，不修改任何文件。
"""
import argparse
import re
import sys
from pathlib import Path


# U-1 阈值: 深度分析 ≥12/19 类, 日报 ≥8/19 类
U1_THRESHOLD = {"depth_analysis": 12, "daily": 8}

# U-2 强制字段: 深度分析 6 项, 日报 4 项 (无质押/杜邦, 由深度分析复用)
U2_FIELDS_DEPTH = {
    "质押风险": r"质押.*(占其持股|占总股本|比例)",
    "杜邦拆解": r"净利率.*周转率.*杠杆|杜邦",
    "板块相位": r"板块相位|SectorPhaseMap|管线.*相位",
    "四档资金": r"超大单.*大单|超大单净额.*大单净额|小单.*净额",
    "PE分位": r"PE.*分位|百分位|历史分位",
    "行业资金": r"行业资金.*[\[（](10|7)[\]）]",
}
U2_FIELDS_DAILY = {
    k: v for k, v in U2_FIELDS_DEPTH.items()
    if k not in ("质押风险", "杜邦拆解")
}

# U-4 阈值
U4_WARN = 0.20
U4_FAIL = 0.50


def load_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def check_u1(text: str, report_type: str) -> dict:
    """U-1: 数据源种类统计"""
    pattern = re.compile(r"\[(\d+[A-Za-z]*)\]|\[tushare\]|\[baostock\]")
    sources = set()
    for m in re.finditer(r"\[(\d+[A-Za-z]*)\]|\[tushare\]|\[baostock\]", text):
        raw = m.group(0)
        sources.add(raw[1:-1].lower())  # 去括号
    count = len(sources)
    threshold = U1_THRESHOLD[report_type]
    return {
        "pass": count >= threshold,
        "count": count,
        "threshold": threshold,
        "sources": sorted(sources),
    }


def check_u2(text: str, report_type: str) -> dict:
    """U-2: 强制字段存在性"""
    fields = U2_FIELDS_DEPTH if report_type == "depth_analysis" else U2_FIELDS_DAILY
    details = {}
    missing = []
    for name, pattern in fields.items():
        found = bool(re.search(pattern, text))
        details[name] = found
        if not found:
            missing.append(name)
    return {
        "pass": len(missing) == 0,
        "total": len(fields),
        "missing": missing,
        "details": details,
    }


def check_u3(text: str) -> dict:
    """U-3: 四档资金结构"""
    has_super_large = bool(re.search(r"超大单", text))
    has_large = bool(re.search(r"大单", text))
    has_structure = has_super_large and has_large
    return {
        "pass": has_structure,
        "has_super_large": has_super_large,
        "has_large": has_large,
    }


def check_u4(text: str) -> dict:
    """U-4: 数据不可获取率"""
    all_refs = len(list(re.finditer(
        r"\[(\d+[A-Za-z]*)\]|\[tushare\]|\[baostock\]", text
    )))
    missing_count = len(re.findall(r"数据不可[获取得]", text))
    # 北向"不可获取"为预期行为，不计入
    northbound_missing = len(re.findall(
        r"北向.*数据不可[获取得]|北向.*不可得",
        text,
    ))
    effective_missing = max(0, missing_count - northbound_missing)
    rate = effective_missing / max(all_refs, 1)
    if rate >= U4_FAIL:
        verdict = "FAIL"
    elif rate >= U4_WARN:
        verdict = "WARN"
    else:
        verdict = "PASS"
    return {
        "pass": verdict != "FAIL",
        "warn": verdict == "WARN",
        "rate": round(rate, 2),
        "total_refs": all_refs,
        "missing_count": effective_missing,
        "verdict": verdict,
    }


def check_report(report_path: str, report_type: str) -> dict:
    text = load_text(report_path)
    u1 = check_u1(text, report_type)
    u2 = check_u2(text, report_type)
    u3 = check_u3(text)
    u4 = check_u4(text)
    overall = u1["pass"] and u2["pass"] and u3["pass"] and u4["pass"]
    failures = []
    if not u1["pass"]:
        failures.append(f"U-1 数据源种类 {u1['count']}/{u1['threshold']}")
    if not u2["pass"]:
        failures.append(f"U-2 强制字段 {u2['total'] - len(u2['missing'])}/{u2['total']} — 缺失: {', '.join(u2['missing'])}")
    if not u3["pass"]:
        failures.append("U-3 四档资金结构缺失")
    if not u4["pass"]:
        failures.append(f"U-4 不可获取率 {u4['rate']:.0%} ≥ {U4_FAIL:.0%}")
    return {
        "pass": overall,
        "u1": u1,
        "u2": u2,
        "u3": u3,
        "u4": u4,
        "failures": failures,
    }


def format_result(result: dict) -> str:
    lines = []
    for key, label, fmt in [
        ("u1", "U-1 数据源种类", lambda r: f"{r['count']}/{r['threshold']}"),
        ("u2", "U-2 强制字段", lambda r: f"{r['total'] - len(r['missing'])}/{r['total']}"),
        ("u3", "U-3 四档资金结构", lambda r: "✓" if r["pass"] else "✗"),
        ("u4", "U-4 不可获取率", lambda r: f"{r['rate']:.0%}"),
    ]:
        r = result[key]
        mark = "✓" if r["pass"] else "✗"
        lines.append(f"{'PASS' if r['pass'] else 'FAIL'}: {label} {fmt(r)} {mark}")
    if result["failures"]:
        lines.append("\n缺失项:")
        for f in result["failures"]:
            lines.append(f"  - {f}")
        missing = result["u2"]["missing"]
        if missing:
            lines.append("\n建议:")
            if "质押风险" in missing:
                lines.append("  - 在 §六 风控段补充: 大股东质押占其持股X%，占总股本X%")
            if "杜邦拆解" in missing:
                lines.append("  - 在 §三.3 盈利能力 ROE 行后补充: 净利率X% × 周转率X × 杠杆乘数X")
            if "板块相位" in missing:
                lines.append("  - 在 §二.2 行业定位段补充: 管线板块相位判断:[XX期]")
            if "四档资金" in missing:
                lines.append("  - 在 §六 风控段将资金表改为四档拆解(超大单/大单/中单/小单)")
    lines.append(f"\n总判定: {'PASS' if result['pass'] else 'FAIL'}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="数据运用合规检查")
    parser.add_argument("--report", required=True, help="报告 .md 文件路径")
    parser.add_argument("--type", required=True, choices=["depth_analysis", "daily"],
                        help="报告类型: depth_analysis (深度分析) / daily (日报)")
    args = parser.parse_args()

    path = Path(args.report)
    if not path.exists():
        print(f"ERROR: 文件不存在: {args.report}")
        sys.exit(2)

    try:
        result = check_report(str(path), args.type)
        print(format_result(result))
        sys.exit(0 if result["pass"] else 1)
    except Exception as e:
        print(f"ERROR: 脚本异常: {e}")
        sys.exit(2)


if __name__ == "__main__":
    main()
