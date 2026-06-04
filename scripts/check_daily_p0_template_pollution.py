#!/usr/bin/env python3
"""P0模板污染闸门: 检查禁止模板句"""
import argparse, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

BANNED = [
    "默认不买。只有回踩S1",
    "K线出现止跌信号同时满足",
    "后续仍需关注",
    "建议密切跟踪",
    "资金关注度提升",
    "短期有望修复",
    "板块环境不改变结论",
    "信号不能单独触发买入，仅提高观察优先级",
]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    args = ap.parse_args()
    date_compact = args.date.replace("-", "")

    md_files = sorted((ROOT / "重点股票" / "股票报告").glob(f"*/*日报_{date_compact}.md"))
    issues = []
    for mp in md_files:
        text = mp.read_text(encoding="utf-8")
        for phrase in BANNED:
            if phrase in text:
                issues.append(f"{mp.parent.name}: 模板句 '{phrase[:30]}...'")

    if issues:
        print("TEMPLATE_POLLUTION: BLOCK")
        for i in issues:
            print(f"  - {i}")
        return 2
    print("TEMPLATE_POLLUTION: PASS")
    return 0

if __name__ == "__main__":
    sys.exit(main())
