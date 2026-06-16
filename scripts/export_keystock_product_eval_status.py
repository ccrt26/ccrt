#!/usr/bin/env python3
"""
重点股票产品化后评估 — 状态/告警导出脚本。

输出 dashboard_status.json 和 alert_center.json。
dashboard 和 alert_center 使用同一份 alerts 对象，alert_id 完全一致。

用法：
  python3 scripts/export_keystock_product_eval_status.py \\
    --out-dir "运行产物/重点股票产品化后评估/status"
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from 代码文件.重点股票.product_eval.status_exporter import StatusExporter  # noqa: E402


def main():
    parser = argparse.ArgumentParser(
        description="重点股票产品化 — 状态/告警导出"
    )
    parser.add_argument(
        "--out-dir",
        default="运行产物/重点股票产品化后评估/status",
        help="输出目录",
    )
    parser.add_argument(
        "--overall-status",
        default=None,
        choices=["COMPLETE", "AUTO_REPAIRING", "BLOCK"],
        help="覆盖总状态（默认自动推导）",
    )
    args = parser.parse_args()

    exporter = StatusExporter()

    # 先推导
    overall, tasks, alerts = exporter.derive_status_from_artifacts()

    # 导出 dashboard（使用同一份 alerts）
    status = exporter.export_dashboard_status(
        overall_status=args.overall_status or overall,
        task_statuses=tasks,
        alerts=alerts,
        out_dir=args.out_dir,
        auto_derive=False,
    )

    # 导出 alert_center（使用同一份 alerts）
    exported_alerts = exporter.export_alert_center(
        alerts=alerts,
        out_dir=args.out_dir,
        auto_derive=False,
    )

    print(f"[STATUS] dashboard.overall_status = {status['overall_status']}")
    print(f"[STATUS] alert_center: {len(exported_alerts)} 条")

    # 验证 alert_id 一致性
    dash_alert_ids = sorted(a.get("alert_id", "") for a in status.get("alerts", []))
    ac_alert_ids = sorted(a.get("alert_id", "") for a in exported_alerts)
    if dash_alert_ids == ac_alert_ids:
        print(f"[STATUS] ✅ dashboard/alert_center alert_id 完全一致")
    else:
        diff1 = set(dash_alert_ids) - set(ac_alert_ids)
        diff2 = set(ac_alert_ids) - set(dash_alert_ids)
        if diff1:
            print(f"[STATUS] ⚠ dashboard 独有的 alert_id: {diff1}")
        if diff2:
            print(f"[STATUS] ⚠ alert_center 独有的 alert_id: {diff2}")

    if status['overall_status'] == 'BLOCK':
        print(f"[STATUS] ⛔ BLOCK — 产出物不完整，需人工处理")
    elif status['overall_status'] == 'AUTO_REPAIRING':
        print(f"[STATUS] ⚠ AUTO_REPAIRING — 数据缺失正在自愈")
    else:
        print(f"[STATUS] ✅ COMPLETE — 主链路可用")

    for a in alerts:
        print(f"[STATUS]   [{a.get('severity')}] {a.get('category')}")


if __name__ == "__main__":
    main()
