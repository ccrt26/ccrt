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

  # 正式账本为空时自动回退 fixture
  python3 scripts/run_forward_eval_scan.py \\
    --as-of-date 20260616 \\
    --fixture-if-empty \\
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


FIXTURE_DEFAULT = "运行产物/重点股票产品化后评估/forward_eval/fixtures/placeholder_due_ledger.jsonl"


def _run_with_ledger(ledger_dir: str, as_of_date: str, out_dir: str) -> list:
    """用指定 ledger 执行扫描。"""
    ledger = PredictionLedger(ledger_dir)
    evaluator = ForwardEval(ledger)
    return evaluator.scan_due_predictions(
        as_of_date=as_of_date,
        out_dir=out_dir,
    )


def _run_with_fixture(fixture_path: str, as_of_date: str, out_dir: str) -> list:
    """用 fixture ledger 执行扫描（不污染正式账本）。"""
    if not os.path.exists(fixture_path):
        print(f"[FORWARD_EVAL] ⛔ fixture ledger 不存在: {fixture_path}")
        sys.exit(1)

    tmp_dir = tempfile.mkdtemp(prefix="ccrt_forward_eval_fixture_")
    tmp_ledger_path = os.path.join(tmp_dir, "prediction_ledger.jsonl")
    shutil.copy2(fixture_path, tmp_ledger_path)
    print(f"[FORWARD_EVAL] 使用 fixture ledger: {fixture_path} → {tmp_ledger_path}")

    results = _run_with_ledger(tmp_dir, as_of_date, out_dir)
    shutil.rmtree(tmp_dir, ignore_errors=True)
    return results


def _print_results(results: list):
    if not results:
        print("[FORWARD_EVAL] 无到期判断")
        return

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
    parser.add_argument(
        "--fixture-if-empty",
        action="store_true",
        default=False,
        help="若正式账本无到期判断，自动使用 fixture ledger",
    )
    args = parser.parse_args()

    # 情况 1：明确指定 fixture-ledger
    if args.fixture_ledger:
        results = _run_with_fixture(args.fixture_ledger, args.as_of_date, args.out_dir)
        _print_results(results)
        return

    # 情况 2：先用正式 ledger
    results = _run_with_ledger(args.ledger_dir, args.as_of_date, args.out_dir)

    # 情况 3：正式空且 --fixture-if-empty
    if not results and args.fixture_if_empty:
        print("[FORWARD_EVAL] 正式账本无到期，回退 fixture ledger")
        results = _run_with_fixture(FIXTURE_DEFAULT, args.as_of_date, args.out_dir)

    _print_results(results)


if __name__ == "__main__":
    main()
