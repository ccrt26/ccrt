#!/usr/bin/env python3
"""write_structured_conclusion.py — 报告结构化JSON伴生写入。

在生成HTML/PDF报告的同时，写入同名JSON文件。

用法:
    python3 write_structured_conclusion.py --output report.html \
        --type daily_rec --code 601689 --name 拓普集团 --date 2026-05-31 \
        --direction bullish --action buy --confidence 0.75 \
        --buy 50.0 --stop 45.0 --target 60.0 \
        --summary "均线多头排列，资金持续流入"

    python3 write_structured_conclusion.py --from-stdin   # 从stdin读取JSON

Code level: L1
"""
import argparse
import json
import os
import sys
from datetime import datetime


def build_conclusion(args):
    return {
        "report_meta": {
            "report_type": args.type,
            "report_date": args.date,
            "stock_code": args.code,
            "stock_name": args.name,
            "strategy_version": args.strategy_version or "v1.0",
            "generated_at": datetime.now().isoformat(),
        },
        "conclusion": {
            "direction": args.direction,
            "action": args.action,
            "confidence": args.confidence,
            "summary": args.summary or "",
        },
        "price_targets": {
            "buy_price": args.buy,
            "stop_loss": args.stop,
            "target_price": args.target,
            "price_source": args.price_source or "[1]",
        },
        "conditions": {
            "trigger_conditions": json.loads(args.trigger_conditions) if args.trigger_conditions else [],
            "forbid_conditions": json.loads(args.forbid_conditions) if args.forbid_conditions else [],
            "counter_evidence": json.loads(args.counter_evidence) if args.counter_evidence else [],
            "expiry_conditions": json.loads(args.expiry_conditions) if args.expiry_conditions else [],
        },
        "evidence": {
            "key_evidence": json.loads(args.key_evidence) if args.key_evidence else [],
            "risk_factors": json.loads(args.risk_factors) if args.risk_factors else [],
            "data_sources": json.loads(args.data_sources) if args.data_sources else [],
        },
        "signals": {
            "triggered": json.loads(args.signals) if args.signals else [],
            "vetoed": [],
        },
        "decision_impact": {
            "scoring_fields": [],
            "veto_fields": [],
            "downgrade_fields": [],
            "position_fields": [],
            "stop_loss_fields": [],
        },
    }


def write_json(data, output_path):
    json_path = output_path.replace(".html", ".json").replace(".pdf", ".json")
    os.makedirs(os.path.dirname(json_path) or ".", exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"结构化JSON已写入: {json_path}")


def main():
    parser = argparse.ArgumentParser(description="报告结构化JSON伴生写入")
    parser.add_argument("--output", required=True, help="HTML/PDF报告路径")
    parser.add_argument("--type", default="daily_rec",
                        choices=["daily_rec", "key_stock_daily", "deep_analysis"])
    parser.add_argument("--code", default="", help="股票代码")
    parser.add_argument("--name", default="", help="股票名称")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--direction", default="neutral",
                        choices=["bullish", "neutral", "bearish", "forbid"])
    parser.add_argument("--action", default="wait",
                        choices=["buy", "hold", "reduce", "clear", "wait"])
    parser.add_argument("--confidence", type=float, default=0.5)
    parser.add_argument("--buy", type=float, help="买入价")
    parser.add_argument("--stop", type=float, help="止损价")
    parser.add_argument("--target", type=float, help="目标价")
    parser.add_argument("--summary", default="", help="人话结论(≤100字)")
    parser.add_argument("--strategy-version", default="v1.0")
    parser.add_argument("--price-source", default="[1]")
    parser.add_argument("--trigger-conditions", help="JSON数组")
    parser.add_argument("--forbid-conditions", help="JSON数组")
    parser.add_argument("--counter-evidence", help="JSON数组")
    parser.add_argument("--expiry-conditions", help="JSON数组")
    parser.add_argument("--key-evidence", help="JSON数组")
    parser.add_argument("--risk-factors", help="JSON数组")
    parser.add_argument("--data-sources", help="JSON数组")
    parser.add_argument("--signals", help="JSON数组")
    parser.add_argument("--from-stdin", action="store_true", help="从stdin读取完整JSON")
    args = parser.parse_args()

    if args.from_stdin:
        data = json.load(sys.stdin)
    else:
        data = build_conclusion(args)

    write_json(data, args.output)


if __name__ == "__main__":
    main()
