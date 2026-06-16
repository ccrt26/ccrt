#!/usr/bin/env python3
"""
重点股票产品化后评估 — 特征快照构建脚本。

为指定股票和日期生成特征快照。从本地 kline_cache 读取真实行情数据。

用法：
  python3 scripts/build_feature_snapshot.py \\
    --code 600114 --date 20260616 --as-of-date 20260616 \\
    --out-dir "运行产物/重点股票产品化后评估/feature_snapshots"
"""

import argparse
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from 代码文件.重点股票.product_eval.feature_service import FeatureSnapshotService  # noqa: E402


def main():
    parser = argparse.ArgumentParser(
        description="重点股票产品化 — 特征快照构建"
    )
    parser.add_argument("--code", required=True, help="股票代码")
    parser.add_argument("--date", required=True, help="交易日 YYYYMMDD")
    parser.add_argument("--as-of-date", required=True, help="数据可见性截止日 YYYYMMDD")
    parser.add_argument(
        "--out-dir",
        default="运行产物/重点股票产品化后评估/feature_snapshots",
        help="输出目录",
    )
    parser.add_argument("--market-lag", type=int, default=0, help="行情滞后天数")
    args = parser.parse_args()

    service = FeatureSnapshotService()
    snapshot = service.get_features(
        stock_code=args.code,
        trade_date=args.date,
        as_of_date=args.as_of_date,
        market_lag_days=args.market_lag,
    )

    os.makedirs(args.out_dir, exist_ok=True)
    out_path = os.path.join(
        args.out_dir,
        f"feature_snapshot_{args.code}_{args.date}.json",
    )
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

    tech = snapshot["feature_values"]["technical"]
    ff = snapshot["future_function_check"]
    qf = snapshot.get("quality_flags", [])
    fs = snapshot["freshness_status"]["overall"]

    has_close = "空" if tech.get("close") is None else f"{tech['close']:.2f}"
    has_ma20 = "空" if tech.get("ma20") is None else f"{tech['ma20']:.2f}"

    print(f"[FEATURE] 已写入: {out_path}")
    print(f"[FEATURE] close={has_close}, ma20={has_ma20}, "
          f"freshness={fs}, quality={len(qf)} 项")
    print(f"[FEATURE] actual_trade_date={tech.get('actual_trade_date')}")
    print(f"[FEATURE] 未来函数检查: {ff['as_of_check']} — {ff['details']}")


if __name__ == "__main__":
    main()
