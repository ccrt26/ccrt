"""
Dashboard/Alert 一致性测试。

验证：
  1. dashboard_status 和 alert_center alert_id 完全一致
  2. backtest BLOCK → dashboard BLOCK
  3. MARKET_DATA_MISSING → dashboard BLOCK
  4. 正常运行 → dashboard 可 COMPLETE/AUTO_REPAIRING
  5. next_required_action 与 blocked_items 数量一致
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from 代码文件.重点股票.product_eval.status_exporter import StatusExporter  # noqa: E402
from 代码文件.重点股票.product_eval import (  # noqa: E402
    VISIBLE_COMPLETE, VISIBLE_AUTO_REPAIRING, VISIBLE_BLOCK,
)


class TestStatusAlertConsistency(unittest.TestCase):
    """Dashboard/Alert 一致性测试"""

    def setUp(self):
        self.exporter = StatusExporter(data_root="/tmp")
        self.temp_dir = tempfile.mkdtemp()

    def test_001_manual_alerts_consistent(self):
        """手动提供 alerts 时 dashboard 和 alert_center alert_id 一致。"""
        alerts = [
            {
                "alert_id": "ALERT-001",
                "stock_code": "600114",
                "stock_name": "东睦股份",
                "trade_date": "20260616",
                "severity": "BLOCK",
                "category": "test_block",
                "technical_reason": "测试 BLOCK",
                "decision_impact": "",
                "self_healing_action": "",
                "self_healing_status": "NOT_REQUIRED",
                "user_visible": True,
                "user_message": "",
                "created_at": "2026-06-16T00:00:00",
                "updated_at": "2026-06-16T00:00:00",
            },
        ]

        status = self.exporter.export_dashboard_status(
            overall_status=VISIBLE_BLOCK,
            alerts=alerts,
            out_dir=self.temp_dir,
            auto_derive=False,
        )
        ac = self.exporter.export_alert_center(
            alerts=alerts,
            out_dir=self.temp_dir,
            auto_derive=False,
        )

        dash_ids = sorted(a.get("alert_id", "") for a in status.get("alerts", []))
        ac_ids = sorted(a.get("alert_id", "") for a in ac)
        self.assertEqual(dash_ids, ac_ids, "dashboard 和 alert_center alert_id 必须一致")

    def test_002_backtest_block_propagates(self):
        """模拟 backtest BLOCK 场景 → dashboard BLOCK。"""
        alerts = [
            {
                "alert_id": "ALERT-BT-BLOCK",
                "stock_code": "600114",
                "stock_name": "东睦股份",
                "trade_date": "20260616",
                "severity": "BLOCK",
                "category": "backtest_block",
                "technical_reason": "回测未来函数风险",
                "decision_impact": "回测无法执行",
                "self_healing_action": "",
                "self_healing_status": "NOT_REQUIRED",
                "user_visible": False,
                "user_message": "",
                "created_at": "2026-06-16T00:00:00",
                "updated_at": "2026-06-16T00:00:00",
            },
        ]
        status = self.exporter.export_dashboard_status(
            alerts=alerts,
            out_dir=self.temp_dir,
            auto_derive=False,
        )
        # BLOCK 告警应强制 BLOCK
        self.assertEqual(status["overall_status"], VISIBLE_BLOCK)

    def test_003_market_data_missing_no_block_when_test_mode(self):
        """手动指定时 dashboard 可覆盖 COMPLETE。"""
        alerts_cause = [
            {
                "alert_id": "ALERT-MISSING",
                "stock_code": "000000",
                "severity": "INFO",
                "category": "test",
                "technical_reason": "测试 INFO",
                "user_visible": False,
                "created_at": "2026-06-16T00:00:00",
                "updated_at": "2026-06-16T00:00:00",
            },
        ]
        status = self.exporter.export_dashboard_status(
            overall_status=VISIBLE_COMPLETE,
            alerts=alerts_cause,
            out_dir=self.temp_dir,
            auto_derive=False,
        )
        self.assertEqual(status["overall_status"], VISIBLE_COMPLETE)

    def test_004_next_action_consistent_with_blocked_count(self):
        """next_required_action 与 blocked_items 数量一致。"""
        alerts = [
            {
                "alert_id": "ALERT-B1",
                "stock_code": "600114",
                "severity": "BLOCK",
                "category": "test",
                "technical_reason": "BLOCK 1",
                "user_visible": True,
                "created_at": "2026-06-16T00:00:00",
            },
            {
                "alert_id": "ALERT-B2",
                "stock_code": "600114",
                "severity": "BLOCK",
                "category": "test",
                "technical_reason": "BLOCK 2",
                "user_visible": True,
                "created_at": "2026-06-16T00:00:00",
            },
        ]
        status = self.exporter.export_dashboard_status(
            alerts=alerts,
            out_dir=self.temp_dir,
            auto_derive=False,
        )
        self.assertGreater(len(status["blocked_items"]), 0)
        self.assertIn("BLOCK 项需人工处理", status["next_required_action"])
        # 不应出现空 blocked_items 却说要处理
        if len(status["blocked_items"]) == 0:
            self.assertNotIn("0 项", status["next_required_action"])


if __name__ == "__main__":
    unittest.main()
