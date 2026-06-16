#!/usr/bin/env python3
"""
重点股票产品化后评估 — 资产盘点脚本。

用法：
  python3 scripts/build_keystock_product_eval_inventory.py \\
    --out-dir "运行产物/重点股票产品化后评估/inventory"

输出：
  运行产物/重点股票产品化后评估/inventory/keystock_system_inventory.json
"""

import argparse
import sys
import os

# 确保能导入 product_eval
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from 代码文件.重点股票.product_eval.inventory import main as inventory_main  # noqa: E402


def main():
    parser = argparse.ArgumentParser(
        description="重点股票产品化 — 资产盘点"
    )
    parser.add_argument(
        "--out-dir",
        default="运行产物/重点股票产品化后评估/inventory",
        help="输出目录（默认: 运行产物/重点股票产品化后评估/inventory）",
    )
    args = parser.parse_args()

    result = inventory_main(out_dir=args.out_dir)
    print(f"[DONE] 资产盘点完成，共发现 {result['daily_report_sidecars']['count']} 个 sidecar, "
          f"{result['deep_analysis_reports']['count']} 个深度分析报告, "
          f"{result['eval_scripts']['count']} 个后评估脚本")


if __name__ == "__main__":
    main()
