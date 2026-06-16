#!/usr/bin/env python3
"""
重点股票产品化后评估 — 前向到期扫描脚本。

自动发现到期判断，评估结果并更新账本状态。

用法：
  python3 scripts/run_forward_eval_scan.py \\
    --as-of-date 20260616 \\
    --out-dir "运行产物/重点股票产品化后评估/forward_eval"

  # 使用 fixture ledger 生成验证产物
  python3 scripts/run_forward_eval_scan.py \\
    --as-of-date 20260616 \\
    --fixture-ledger "运行产物/重点股票产品化后评估/forward_eval/fixtures/placeholder_due_ledger.jsonl" \\
    --out-dir "运行产物/重点股票产品化后评估/forward_eval"
"""

import argparse
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from 代码文件.重点股票.product_eval.prediction_ledger import PredictionLedger  # noqa: E402
from 代码文件.重点股票.product_eval.forward_eval import ForwardEval  # noqa: E402


def main():
    parser = argparse.ArgumentParser(
        description="重点股票产品化 — 前向到期扫描"
    )
    parser.add_argument("--as-of-date", required=True, help="评估日期 YYYYMMDD")
    parser.add_argument(
        "--out-dir",
        default="运行产物/重点股票产品化后评估/forward_eval",
        help="输出目录",
    )
    parser.add_argument(
        "--ledger-dir",
        default="运行产物/重点股票产品化后评估/ledger",
        help="正式账本目录",
    )
    parser.add_argument(
        "--fixture-ledger",
        default=None,
        help="fixture JSONL 路径（用于生成验证产物，不覆盖正式账本）",
    )
    args = parser.parse_args()

    if args.fixture_ledger:
        # 使用 fixture ledger — 复制到临时目录执行
        if not os.path.exists(args.fixture_ledger):
            print(f"[FORWARD_EVAL] ⛔ fixture ledger 不存在: {args.fixture_ledger}")
            sys.exit(1)

        tmp_dir = tempfile.mkdtemp(prefix="ccrt_forward_eval_fixture_")
        # 复制 fixture JSONL 到临时 ledger 目录
        tmp_ledger_path = os.path.join(tmp_dir, "prediction_ledger.jsonl")
        shutil.copy2(args.fixture_ledger, tmp_ledger_path)
        print(f"[FORWARD_EVAL] 使用 fixture ledger: {args.fixture_ledger} → {tmp_ledger_path}")

        ledger = PredictionLedger(tmp_dir)
        evaluator = ForwardEval(ledger)
        results = evaluator.scan_due_predictions(
            as_of_date=args.as_of_date,
            out_dir=args.out_dir,
        )
        # 清理临时目录
        shutil.rmtree(tmp_dir, ignore_errors=True)
    else:
        ledger = PredictionLedger(args.ledger_dir)
        evaluator = ForwardEval(ledger)
        results = evaluator.scan_due_predictions(
            as_of_date=args.as_of_date,
            out_dir=args.out_dir,
        )

    if results:
        outcomes = {}
        fixture_count = 0
        for r in results:
            o = r.get("outcome", "UNKNOWN")
            outcomes[o] = outcomes.get(o, 0) + 1
            if r.get("fixture_only") or r.get("source_fixture_ref"):
                fixture_count += 1
        print(f"[FORWARD_EVAL] 到期评估完成: {len(results)} 条 (fixture={fixture_count})")
        for k, v in outcomes.items():
            print(f"[FORWARD_EVAL]   {k}: {v} 条")
    else:
        print("[FORWARD_EVAL] 无到期判断")


if __name__ == "__main__":
    main()
