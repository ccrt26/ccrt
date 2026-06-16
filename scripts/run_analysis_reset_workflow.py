#!/usr/bin/env python3
"""
分析重置工作流（dry-run 样例）。不修改任何正式数据。

用法：
  python3 scripts/run_analysis_reset_workflow.py \\
    --stock-code 600114 \\
    --trade-date 20260616 \\
    --reason "phase2_3_productization_smoke" \\
    --dry-run \\
    --out "运行产物/重点股票产品化后评估/product_api/analysis_reset_workflow_dry_run.json"
"""

import argparse
import json
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from 代码文件.重点股票.product_eval.analysis_reset_workflow import AnalysisResetWorkflowService  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="分析重置工作流（dry-run）")
    parser.add_argument("--stock-code", required=True, help="股票代码")
    parser.add_argument("--trade-date", required=True, help="交易日 YYYYMMDD")
    parser.add_argument("--reason", default="phase2_3_smoke", help="重置原因")
    parser.add_argument("--dry-run", action="store_true", default=True, help="dry-run 模式")
    parser.add_argument("--out", required=True, help="输出路径")
    args = parser.parse_args()

    svc = AnalysisResetWorkflowService()
    result = svc.execute_dry_run(
        stock_code=args.stock_code,
        stock_name="东睦股份",
        trade_date=args.trade_date,
        reason=args.reason,
    )

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"[RESET] 已写入: {args.out}")
    print(f"[RESET] workflow_status={result.get('workflow_status')}")
    print(f"[RESET] dry_run={result.get('dry_run')}")
    steps_status = {s["step_name"]: s["status"] for s in result.get("steps", [])}
    for name, status in steps_status.items():
        print(f"[RESET]   {name}: {status}")


if __name__ == "__main__":
    main()
