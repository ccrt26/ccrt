#!/usr/bin/env python3
"""
深度分析 D07_v1.2 + 砺石 method_review 硬闸门。

检查单份MD报告或扫描某日期全部报告，确认必执行项是否落实。
退出码: 0=PASS, 1=WARN, 2=BLOCK
"""
import argparse, json, os, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEEP_REPORT_DIR = ROOT / "重点股票" / "深度分析" / "深度分析报告"

D07_REQUIRED_FIELDS = [
    ("D07_v1.2 声明", r"D07_v1\.2"),
    ("framework_version", r"framework_version"),
    ("多假设/假设表", r"假设|hypotheses"),
    ("反证/反证条件", r"反证条件|counter_evidence"),
    ("证据缺口/evidence_gap", r"证据缺口|evidence_gap"),
    ("结论强度/conclusion_strength", r"结论强度|conclusion_strength"),
    ("长期机构资金证据/long_term", r"长期机构资金|long_term_institutional_evidence"),
    ("失效条件", r"失效条件|invalidation_condition"),
    ("U-9/audit_u9", r"U-9|audit_u9"),
    ("U-10/audit_u10", r"U-10|audit_u10"),
]

LISHI_REQUIRED_FIELDS = [
    ("砺石/LISHI", r"砺石|LISHI"),
    ("method_review", r"method_review"),
    ("推理链检查", r"推理链|D1[^\.]"),
    ("数据可靠性检查", r"数据可靠性|D2[^\.]"),
    ("逻辑一致性检查", r"逻辑一致性|D3[^\.]"),
    ("反证充分性检查", r"反证充分|D4[^\.]"),
    ("集体推理质量检查", r"集体推理|D5[^\.]"),
]

# 砺石不得输出投资方向
LISHI_FORBIDDEN = [
    ("BUY", r"BUY"),
    ("SELL", r"SELL"),
    ("买入", r"买入"),
    ("卖出", r"卖出"),
    ("增持", r"增持(?!.*事实|.*change)"),
    ("减持", r"减持(?!.*事实|.*change)"),
]


def check_report(path, strict=False):
    """返回 (overall, findings)"""
    findings = []
    if not path.exists():
        return "BLOCK", [f"报告不存在: {path}"]

    text = path.read_text(encoding="utf-8")

    # --- D07 检查 ---
    d07_found = 0
    d07_missing = []
    for name, pat in D07_REQUIRED_FIELDS:
        if re.search(pat, text, re.IGNORECASE):
            d07_found += 1
        else:
            d07_missing.append(name)

    if d07_missing:
        missing_str = ", ".join(d07_missing)
        # U-9/U-10 缺失必须 BLOCK
        u9_u10_missing = [m for m in d07_missing if "U-9" in m or "U-10" in m]
        is_core_missing = any("D07_v1.2" in m or "framework" in m or "假设" in m for m in d07_missing)
        if u9_u10_missing:
            findings.append({"check": "D07_v1.2", "result": "BLOCK", "detail": f"U-9/U-10 是必检项: {', '.join(u9_u10_missing)}"})
        elif len(d07_missing) <= 3 and not is_core_missing:
            findings.append({"check": "D07_v1.2", "result": "WARN", "detail": f"缺失 {len(d07_missing)}/{len(D07_REQUIRED_FIELDS)} 项: {missing_str}"})
        else:
            findings.append({"check": "D07_v1.2", "result": "BLOCK", "detail": f"核心 D07 项缺失: {missing_str}"})
    else:
        findings.append({"check": "D07_v1.2", "result": "PASS", "detail": f"全部 {len(D07_REQUIRED_FIELDS)} 项通过"})

    # --- 砺石检查 ---
    lishi_found = 0
    lishi_missing = []
    for name, pat in LISHI_REQUIRED_FIELDS:
        if re.search(pat, text, re.IGNORECASE):
            lishi_found += 1
        else:
            lishi_missing.append(name)

    if lishi_missing:
        lishi_str = ", ".join(lishi_missing)
        if len(lishi_missing) <= 2 and "砺石/LISHI" not in lishi_missing:
            findings.append({"check": "砺石_method_review", "result": "WARN", "detail": f"缺失 {len(lishi_missing)}/{len(LISHI_REQUIRED_FIELDS)} 项: {lishi_str}"})
        else:
            findings.append({"check": "砺石_method_review", "result": "BLOCK", "detail": f"必需项缺失: {lishi_str}"})
    else:
        findings.append({"check": "砺石_method_review", "result": "PASS", "detail": f"全部 {len(LISHI_REQUIRED_FIELDS)} 项通过"})

    # --- 砺石越界检查 ---
    for fname, fpat in LISHI_FORBIDDEN:
        # 只在砺石相关段落中搜索越界表达
        lishi_section = ""
        m = re.search(r"(砺石|method_review|方法审查|LISHI).{1,2000}", text, re.DOTALL)
        if m:
            lishi_section = m.group(0)
        if re.search(fpat, lishi_section, re.IGNORECASE):
            findings.append({"check": "砺石_投资方向越界", "result": "BLOCK", "detail": f"砺石段落含投资方向表达: {fname}"})

    if not any("砺石" in f["check"] for f in findings):
        findings.append({"check": "砺石_method_review", "result": "BLOCK", "detail": "砺石方法审查完全缺失"})

    # --- 总体 ---
    blocks = [f for f in findings if f["result"] == "BLOCK"]
    warns = [f for f in findings if f["result"] == "WARN"]
    overall = "BLOCK" if blocks else ("WARN" if warns else "PASS")
    return overall, findings


def scan_date(date_str):
    date_dir = DEEP_REPORT_DIR
    results = {}
    for report_path in date_dir.rglob(f"*{date_str}.md"):
        if "G4自检" in report_path.name or "样稿" in report_path.name:
            continue
        code_match = re.search(r"(\d{6})", report_path.name)
        code = code_match.group(1) if code_match else "unknown"
        overall, findings = check_report(report_path)
        results[code] = {"path": str(report_path), "overall": overall, "findings": findings}
    return results


def main():
    parser = argparse.ArgumentParser(description="深度分析 D07+砺石 硬闸门")
    parser.add_argument("--report", default="", help="单份MD报告路径")
    parser.add_argument("--date", default="", help="YYYYMMDD 扫描全部报告")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    if args.report:
        p = Path(args.report)
        if not p.exists():
            p = ROOT / args.report
        if not p.exists():
            print(f"BLOCK: 报告不存在 {args.report}")
            sys.exit(2)
        overall, findings = check_report(p)
    elif args.date:
        results = scan_date(args.date)
        if not results:
            print(f"BLOCK: 未找到 {args.date} 的深度分析报告" if not args.json else json.dumps({"overall":"BLOCK","findings":[{"detail":f"未找到 {args.date} 的深度分析报告"}]},ensure_ascii=False))
            sys.exit(2)
        all_pass = all(r["overall"] == "PASS" for r in results.values())
        overall = "PASS" if all_pass else "BLOCK"
        findings = [{"stock": k, "overall": v["overall"], "findings": v["findings"]} for k, v in results.items()]
    else:
        parser.print_help()
        sys.exit(2)

    output = {"overall": overall, "findings": findings}
    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(f"Deep D07+砺石 Gate: {overall}")
        if isinstance(findings, list):
            for f in findings:
                if isinstance(f, dict) and "stock" in f:
                    print(f"  {f['stock']}: {f['overall']}")
                    for sub in f.get("findings", []):
                        print(f"    [{sub['result']}] {sub['check']}: {sub['detail'][:80]}")
                else:
                    print(f"  [{f['result']}] {f['check']}: {f['detail'][:80]}")

    sys.exit(0 if overall == "PASS" else (1 if overall == "WARN" else 2))


if __name__ == "__main__":
    main()
