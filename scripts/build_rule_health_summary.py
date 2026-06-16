#!/usr/bin/env python3
"""
构建规则健康摘要。从 Phase 1 后评估产物推导。

用法：
  python3 scripts/build_rule_health_summary.py \\
    --base-dir "运行产物/重点股票产品化后评估" \\
    --out "运行产物/重点股票产品化后评估/product_api/rule_health_summary.json" \\
    --docs-out "docs/keystock-dashboard/data/rule_health.json"
"""

import argparse
import json
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from 代码文件.重点股票.product_eval.rule_health_summary import RuleHealthSummaryService  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="构建规则健康摘要")
    parser.add_argument("--base-dir", required=True, help="运行产物根目录")
    parser.add_argument("--out", required=True, help="输出路径")
    parser.add_argument("--docs-out", required=True, help="前端 rule_health.json 路径")
    args = parser.parse_args()

    bt_path = os.path.join(args.base_dir, "backtests", "backtest_TECH_MA20_BREAK_STOP_LOSS_600114_20260616.json")
    svc = RuleHealthSummaryService()
    result = svc.derive_from_backtest(bt_path)
    if not result:
        result = svc.build_rule_health()

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"[RULES] 已写入: {args.out}")

    os.makedirs(os.path.dirname(args.docs_out), exist_ok=True)
    with open(args.docs_out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"[RULES] 已写入前端: {args.docs_out}")


if __name__ == "__main__":
    main()
