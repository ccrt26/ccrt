#!/usr/bin/env python3
"""
重点股票产品化后评估 — 预测账本构建脚本。

从日报 sidecar 中抽取可验证判断，写入 PredictionLedger JSONL。
0 条时也必须生成错误状态 JSONL + ledger_status.json，不得静默成功。

用法：
  python3 scripts/build_prediction_ledger.py \\
    --out-dir "运行产物/重点股票产品化后评估/ledger"

输出：
  运行产物/重点股票产品化后评估/ledger/prediction_ledger.jsonl
  运行产物/重点股票产品化后评估/ledger/ledger_status.json
"""

import argparse
import json
import sys
import os
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from 代码文件.重点股票.product_eval.prediction_ledger import PredictionLedger  # noqa: E402
from 代码文件.重点股票.product_eval.inventory import (  # noqa: E402
    scan_daily_report_sidecars,
    scan_baseline_registry,
)


def main():
    parser = argparse.ArgumentParser(
        description="重点股票产品化 — 预测账本构建"
    )
    parser.add_argument(
        "--out-dir",
        default="运行产物/重点股票产品化后评估/ledger",
        help="JSONL 输出目录",
    )
    args = parser.parse_args()

    ledger = PredictionLedger(args.out_dir)

    # 扫描 sidecar
    sidecars = scan_daily_report_sidecars()
    baseline_info = scan_baseline_registry()

    baseline_id = ""
    if baseline_info.get("status") == "FOUND":
        baseline_data = baseline_info.get("data", {})
        if isinstance(baseline_data, dict):
            baseline_id = baseline_data.get("baseline_id", "")
        elif isinstance(baseline_data, list) and baseline_data:
            baseline_id = baseline_data[0].get("baseline_id", "")

    count = 0
    for sc in sidecars:
        fname = sc.get("file", "")
        name_part = sc.get("stock_dir", "")

        stock_code = ""
        trade_date = ""

        if "(" in name_part and ")" in name_part:
            stock_code = name_part.split("(")[1].rstrip(")")

        # 提取日期：支持 YYYYMMDD 和 YYYY-MM-DD
        import re
        m = re.search(r"_(\d{8})\.json", fname)
        if not m:
            m = re.search(r"_(\d{4}-\d{2}-\d{2})\.json", fname)
        if m:
            trade_date = m.group(1).replace("-", "")

        if not stock_code or not trade_date:
            continue

        record = {
            "source_type": "daily_report",
            "source_report_path": sc.get("path", ""),
            "source_sidecar_path": sc.get("path", ""),
            "stock_code": stock_code,
            "stock_name": name_part.split("(")[0] if "(" in name_part else name_part,
            "trade_date": trade_date,
            "baseline_id": baseline_id,
            "rule_version": "v1.0",
            "data_snapshot_id": f"DS-{trade_date}-{stock_code}",
            "prediction_type": "directional",
            "assertion": f"Phase 1 占位记录 — {stock_code} {trade_date}",
            "horizon": 20,
            "confidence": 0.5,
            "verification_windows": [
                {"label": "T+5", "offset_days": 5},
                {"label": "T+20", "offset_days": 20},
            ],
        }
        ledger.insert(record)
        count += 1

    # 即使 0 条也写入 ledger_status.json
    os.makedirs(args.out_dir, exist_ok=True)
    ledger_count = ledger.count()

    if count == 0:
        ledger_status = "WARN"
        warn_reason = "未找到可解析的日报 sidecar，无记录写入"
    elif count < 5:
        ledger_status = "WARN"
        warn_reason = f"仅写入 {count} 条记录，覆盖率较低"
    else:
        ledger_status = "PASS"
        warn_reason = ""

    status = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sidecar_count": len(sidecars),
        "parsed_count": count,
        "ledger_count": ledger_count,
        "status": ledger_status,
        "reason": warn_reason,
        "ledger_path": os.path.join(args.out_dir, "prediction_ledger.jsonl"),
    }

    status_path = os.path.join(args.out_dir, "ledger_status.json")
    with open(status_path, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)

    print(f"[LEDGER] sidecar_count={len(sidecars)}, parsed={count}, ledger_count={ledger_count}")
    print(f"[LEDGER] status={ledger_status}: {warn_reason}")
    print(f"[LEDGER] ledger_status 已写入: {status_path}")


if __name__ == "__main__":
    main()
