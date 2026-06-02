#!/usr/bin/env python3
"""注入DQ闸门状态到日报HTML — daily_workflow Phase 4.1"""
import json, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = ROOT / "代码文件" / "数据"
REPORT_DIR = ROOT / "每日荐股" / "股票报告"
KEYSTOCK_DIR = ROOT / "重点股票" / "股票报告"


def get_dq_status():
    """读取DQ报告，生成状态行HTML"""
    dq_path = DATA_DIR / "data_quality_report.json"
    if not dq_path.exists():
        return None

    with open(dq_path) as f:
        dq = json.load(f)

    overall = dq.get("overall", "UNKNOWN")
    issues = dq.get("issues", [])
    metrics = dq.get("metrics", {})

    emoji = {"PASS": "🟢", "WARN": "🟡", "FAIL": "🔴"}.get(overall, "⚪")
    label = {"PASS": "正常", "WARN": "警告", "FAIL": "阻断"}.get(overall, "未知")

    # 构建状态文本
    status_parts = [
        f"缓存{metrics.get('cache_hit_rate','?')}%",
        f"行情{metrics.get('quote_coverage','?')}%",
        f"财务{metrics.get('financial_coverage','?')}%",
        f"资金流{metrics.get('fundflow_coverage','?')}%",
    ]

    status_line = f"{emoji} DQ-Gate: {label} | {' | '.join(status_parts)} | {len(issues)}个问题"

    # 如果有问题，列出
    issue_lines = ""
    if issues:
        issue_lines = "<br>".join(
            f"  [{i['severity']}] {i['id']}: {i['desc']}" for i in issues
        )
        status_line += f"<br>{issue_lines}"

    return {
        "overall": overall,
        "blocked": dq.get("blocked", False),
        "html": status_line,
    }


def inject_into_html(html_path, status):
    """往HTML日报底部注入DQ状态行"""
    if not html_path.exists():
        return False

    with open(html_path, encoding="utf-8") as f:
        content = f.read()

    # 在 </body> 之前注入
    dq_block = f"""
<div style="background:#fff;border-radius:10px;padding:16px 22px;margin:18px 0;box-shadow:0 1px 6px rgba(0,0,0,.06);font-size:13px;line-height:1.8">
<div style="font-weight:700;margin-bottom:8px;color:#1a1a2e">数据质量闸门 (DQ-Gate)</div>
<div style="font-size:12px">{status['html']}</div>
</div>
"""

    if "</body>" in content:
        content = content.replace("</body>", dq_block + "\n</body>")
    elif "</html>" in content:
        content = content.replace("</html>", dq_block + "\n</html>")
    else:
        content += dq_block

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(content)

    return True


def main():
    status = get_dq_status()
    if not status:
        print("[DQ-Inject] No DQ report found, skip")
        return

    print(f"[DQ-Inject] DQ status: {status['overall']} | blocked={status['blocked']}")

    # 注入到每日荐股报告
    from datetime import date
    today = date.today().isoformat().replace("-", "")
    report_path = REPORT_DIR / f"daily_report_{today}.html"
    if report_path.exists():
        inject_into_html(report_path, status)
        print(f"[DQ-Inject] Injected into daily report: {report_path.name}")
    else:
        # Try yesterday
        from datetime import timedelta
        yesterday = (date.today() - timedelta(days=1)).isoformat().replace("-", "")
        report_path = REPORT_DIR / f"daily_report_{yesterday}.html"
        if report_path.exists():
            inject_into_html(report_path, status)
            print(f"[DQ-Inject] Injected into daily report: {report_path.name}")
        else:
            print(f"[DQ-Inject] No daily report found for {today} or {yesterday}")

    # 注入到重点股票日报（最近日期的）
    for stock_dir in KEYSTOCK_DIR.iterdir():
        if not stock_dir.is_dir():
            continue
        # 找最新的日报HTML
        daily_files = sorted(stock_dir.glob("*日报_*.html"), reverse=True)
        if daily_files:
            inject_into_html(daily_files[0], status)
    print(f"[DQ-Inject] Injected into key stock reports")

    # 输出状态文本供其他用途
    print(f"[DQ-Inject] Status line: {status['html']}")


if __name__ == "__main__":
    main()
