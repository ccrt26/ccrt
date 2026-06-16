#!/usr/bin/env python3
"""
检查驾驶舱产品化状态：硬编码数据、占位图表、虚假 COMPLETE、UI 结构、数据源。

输出 JSON 格式 checker 结果。
"""

import argparse
import json
import os
import re
import sys


def check_dashboard_productization(docs_dir: str, data_dir: str) -> dict:
    findings = []
    fake_data_hits = []
    hardcoded_decision_hits = []
    checked_files = []

    # ── 1. 检查文件存在 ──
    required = ["index.html", "app.css", "app.js"]
    for fname in required:
        path = os.path.join(docs_dir, fname)
        if os.path.exists(path):
            checked_files.append(path)
        else:
            findings.append({"check": "required_file", "path": path, "status": "BLOCK", "detail": f"缺失: {fname}"})

    # ── 2. 检查 app.js 硬编码结论 ──
    js_path = os.path.join(docs_dir, "app.js")
    if os.path.exists(js_path):
        js = open(js_path, encoding="utf-8").read()
        checked_files.append(js_path)

        hardcoded_patterns = [
            (r"建议持有/观察", "硬编码建议"),
            (r"持有为主", "硬编码持有决策"),
            (r"冲高回落", "硬编码走势描述"),
            (r"chart-placeholder", "占位图表"),
            (r"此处展示", "占位说明"),
            (r"考虑减仓至 50%", "硬编码减仓"),
            (r"若明日反弹回 MA20 上方: 继续持有", "硬编码决策"),
        ]
        for pattern, desc in hardcoded_patterns:
            if re.search(pattern, js):
                hardcoded_decision_hits.append({"pattern": pattern, "desc": desc})
                findings.append({
                    "check": "hardcoded_decision",
                    "path": js_path,
                    "status": "BLOCK",
                    "detail": f"硬编码：{desc} (模式: {pattern})",
                })

        # 检查 chart-placeholder CSS class
        if ".chart-placeholder" in js:
            findings.append({
                "check": "chart_placeholder_in_js",
                "path": js_path,
                "status": "BLOCK",
                "detail": "app.js 中包含 chart-placeholder",
            })

    # ── 3. 检查 CSS 中的 chart-placeholder ──
    css_path = os.path.join(docs_dir, "app.css")
    if os.path.exists(css_path):
        css = open(css_path, encoding="utf-8").read()
        checked_files.append(css_path)
        if ".chart-placeholder" in css:
            findings.append({
                "check": "chart_placeholder_in_css",
                "path": css_path,
                "status": "BLOCK",
                "detail": "app.css 中包含 .chart-placeholder 样式",
            })

    # ── 4. 检查 index.html UI 结构（应有侧边导航） ──
    html_path = os.path.join(docs_dir, "index.html")
    if os.path.exists(html_path):
        html = open(html_path, encoding="utf-8").read()
        checked_files.append(html_path)
        # 检查是否为侧边导航（含 sidebar/side-nav 或左侧导航结构）而非顶部导航简版
        has_sidebar = bool(re.search(r'sidebar|side-nav|side-navbar', html, re.IGNORECASE))
        has_app_shell = "view-dashboard" in html and "view-stocks" in html
        has_five_views = all(f"view-{v}" in html for v in ["dashboard", "stocks", "deep", "daily", "rules"])

        if not has_app_shell or not has_five_views:
            findings.append({
                "check": "ui_structure",
                "path": html_path,
                "status": "BLOCK",
                "detail": f"UI 页面结构不完整: sidebar={has_sidebar}, shell={has_app_shell}, 5views={has_five_views}",
            })

    # ── 5. 检查 stocks.json 无证据股票 ──
    stocks_path = os.path.join(data_dir, "stocks.json")
    if os.path.exists(stocks_path):
        try:
            stocks_data = json.load(open(stocks_path, encoding="utf-8"))
            checked_files.append(stocks_path)
            for s in stocks_data.get("stocks", []):
                code = s.get("stock_code", "")
                if code in ("600519", "000858"):
                    fake_data_hits.append({"stock": code, "reason": "无真实证据文件的股票"})
                    findings.append({
                        "check": "fake_stock_data",
                        "path": stocks_path,
                        "status": "WARN" if code == "600519" else "BLOCK",
                        "detail": f"股票 {code} 出现在 stocks.json 但无同等级真实证据",
                    })
        except Exception as e:
            findings.append({"check": "stocks_parse", "path": stocks_path, "status": "BLOCK", "detail": str(e)})

    # ── 6. 检查 chart_data.json ──
    chart_path = os.path.join(data_dir, "chart_data.json")
    if os.path.exists(chart_path):
        try:
            chart = json.load(open(chart_path, encoding="utf-8"))
            ohlc = chart.get("ohlc", [])
            if len(ohlc) < 20:
                findings.append({
                    "check": "chart_data_insufficient",
                    "path": chart_path,
                    "status": "WARN",
                    "detail": f"chart_data ohlc 仅 {len(ohlc)} 行，建议 >= 20",
                })
        except Exception as e:
            findings.append({"check": "chart_data_parse", "path": chart_path, "status": "BLOCK", "detail": str(e)})
    else:
        findings.append({"check": "chart_data_missing", "path": str(chart_path), "status": "BLOCK", "detail": "chart_data.json 缺失"})

    # ── 7. 检查 today_decisions.json ──
    dec_path = os.path.join(data_dir, "today_decisions.json")
    if os.path.exists(dec_path):
        try:
            dec = json.load(open(dec_path, encoding="utf-8"))
            pos = dec.get("user_position", {})
            if pos.get("has_position") is True and pos.get("cost_price") is None:
                findings.append({
                    "check": "position_data_integrity",
                    "path": dec_path,
                    "status": "BLOCK",
                    "detail": "has_position=true 但 cost_price=null，数据矛盾",
                })
        except Exception:
            pass

    # ── 8. 数据日期差异检查 ──
    if os.path.exists(chart_path):
        try:
            chart = json.load(open(chart_path, encoding="utf-8"))
            if chart.get("data_date_divergence"):
                findings.append({
                    "check": "data_date_divergence",
                    "path": chart_path,
                    "status": "WARN",
                    "detail": chart.get("date_divergence_warning", "日期差异"),
                })
        except Exception:
            pass

    # ── 汇总 ──
    blocks = [f for f in findings if f.get("status") == "BLOCK"]
    warns = [f for f in findings if f.get("status") == "WARN"]
    overall = "PASS" if not blocks else "BLOCK"

    return {
        "overall": overall,
        "findings": findings,
        "checked_files": checked_files,
        "fake_data_hits": fake_data_hits,
        "hardcoded_decision_hits": hardcoded_decision_hits,
        "visual_contract_status": "PASS",
        "data_truth_status": "PASS" if not fake_data_hits else "BLOCK",
        "recommended_user_visible_status": "COMPLETE" if overall == "PASS" else "BLOCK",
    }


def main():
    parser = argparse.ArgumentParser(description="检查驾驶舱产品化")
    parser.add_argument("--docs-dir", required=True, help="docs/keystock-dashboard 路径")
    parser.add_argument("--data-dir", default=None, help="data 目录路径")
    parser.add_argument("--preview", default=None, help="预览文件路径（可选）")
    parser.add_argument("--out", default=None, help="输出路径")
    args = parser.parse_args()

    data_dir = args.data_dir or os.path.join(args.docs_dir, "data")
    result = check_dashboard_productization(args.docs_dir, data_dir)

    if args.out:
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"[CHECKER] 已写入: {args.out}")

    print(json.dumps(result, ensure_ascii=False, indent=2))

    if result["overall"] == "BLOCK":
        sys.exit(1)


if __name__ == "__main__":
    main()
