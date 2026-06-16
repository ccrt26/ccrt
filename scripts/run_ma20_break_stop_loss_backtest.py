#!/usr/bin/env python3
"""
重点股票产品化后评估 — MA20 破位止损单规则回测脚本。

基于本地 kline_cache 进行真实 MA20 破位检测和回测统计。

用法：
  python3 scripts/run_ma20_break_stop_loss_backtest.py \\
    --code 600114 --as-of-date 20260616 \\
    --out-dir "运行产物/重点股票产品化后评估/backtests"
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from 代码文件.重点股票.product_eval.backtest_engine import BacktestEngine  # noqa: E402
from 代码文件.重点股票.product_eval import data_source as ds  # noqa: E402


def main():
    parser = argparse.ArgumentParser(
        description="重点股票产品化 — MA20 破位止损回测"
    )
    parser.add_argument("--code", required=True, help="股票代码")
    parser.add_argument("--as-of-date", required=True, help="回溯截止日期 YYYYMMDD")
    parser.add_argument(
        "--out-dir",
        default="运行产物/重点股票产品化后评估/backtests",
        help="输出目录",
    )
    args = parser.parse_args()

    stock_codes = args.code.split(",")
    stock_names = {"600114": "东睦股份", "600519": "贵州茅台", "000858": "五粮液"}

    for code in stock_codes:
        name = stock_names.get(code, code)

        # 检查 kline_cache
        rows = ds.get_kline_until(code, args.as_of_date)
        if not rows:
            print(f"[BACKTEST] ⛔ {code}: 无 K 线数据，跳过")
            continue
        print(f"[BACKTEST] {code}: {len(rows)} 行 K 线数据（{rows[0].get('_date_norm')} ~ {rows[-1].get('_date_norm')}）")

        engine = BacktestEngine()
        result = engine.run_backtest(
            rule_id="TECH_MA20_BREAK_STOP_LOSS",
            stock_code=code,
            stock_name=name,
            as_of_date=args.as_of_date,
            out_dir=args.out_dir,
        )

        print(f"[BACKTEST] {code}: 规则={result['rule_id']}, 总体状态={result['overall_status']}")
        for label, win in result.get("windows", {}).items():
            print(f"[BACKTEST]   {label}: 样本数={win.get('sample_count', 0)}, "
                  f"H/M/P={win.get('hit_count',0)}/{win.get('miss_count',0)}/"
                  f"{win.get('partial_count',0)}, "
                  f"胜率={win.get('win_rate','N/A')}, "
                  f"状态={win.get('overall_status')}")


if __name__ == "__main__":
    main()
