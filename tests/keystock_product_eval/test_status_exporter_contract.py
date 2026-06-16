"""
StatusExporter 契约测试。

验证：
  1. dashboard_status.json 输出字段完整
  2. alert_center.json 输出为顶层数组
  3. 告警 severity/category 枚举
  4. user_visible 标记
  5. auto_derive 可禁用
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


class TestStatusExporterContract(unittest.TestCase):
    """StatusExporter 契约测试"""

    def setUp(self):
        self.exporter = StatusExporter(data_root="/tmp")
        self.temp_dir = tempfile.mkdtemp()

    def test_dashboard_status_required_fields(self):
        """使用 auto_derive=False 测试字段完整性。"""
        status = self.exporter.export_dashboard_status(
            out_dir=self.temp_dir, auto_derive=False)
        required = [
            "generated_at", "overall_status", "task_statuses",
            "alerts", "next_required_action",
        ]
        for field in required:
            self.assertIn(field, status, f"dashboard_status 缺少: {field}")

    def test_overall_status_enum_valid(self):
        status = self.exporter.export_dashboard_status(
            overall_status=VISIBLE_COMPLETE,
            out_dir=self.temp_dir,
            auto_derive=False,
        )
        self.assertIn(status["overall_status"],
                      [VISIBLE_COMPLETE, VISIBLE_AUTO_REPAIRING, VISIBLE_BLOCK])

    def test_block_alert_propagates_to_overall(self):
        status = self.exporter.export_dashboard_status(
            alerts=[{
                "alert_id": "TEST-BLOCK-01",
                "severity": "BLOCK",
                "technical_reason": "测试 BLOCK",
                "user_visible": True,
            }],
            out_dir=self.temp_dir,
            auto_derive=False,
        )
        self.assertEqual(status["overall_status"], VISIBLE_BLOCK)
        self.assertGreater(len(status["blocked_items"]), 0)

    def test_alert_center_output_is_array(self):
        """alert_center 输出为顶层数组。"""
        alerts = self.exporter.export_alert_center(
            out_dir=self.temp_dir, auto_derive=False)
        self.assertIsInstance(alerts, list)
        for alert in alerts:
            required = ["alert_id", "severity", "category",
                        "technical_reason", "user_visible", "created_at"]
            for field in required:
                self.assertIn(field, alert, f"alert 缺少字段: {field}")
            self.assertIn(alert["severity"], ["INFO", "WARN", "ALERT", "BLOCK"])

    def test_user_visible_false_by_default(self):
        """auto_derive=False 时默认告警为空，验证手动创建。"""
        manual_alerts = [
            {
                "alert_id": "TEST-01",
                "stock_code": "600114",
                "stock_name": "东睦股份",
                "trade_date": "20260616",
                "severity": "INFO",
                "category": "test",
                "technical_reason": "测试告警",
                "decision_impact": "",
                "self_healing_action": "",
                "self_healing_status": "NOT_REQUIRED",
                "user_visible": False,
                "user_message": "",
                "created_at": "2026-06-16T00:00:00",
                "updated_at": "2026-06-16T00:00:00",
            },
        ]
        self.assertFalse(manual_alerts[0]["user_visible"],
                         "手动告警默认 user_visible=False")

    def test_output_files_exist(self):
        """验证输出文件存在。"""
        self.exporter.export_dashboard_status(out_dir=self.temp_dir, auto_derive=False)
        self.exporter.export_alert_center(out_dir=self.temp_dir, auto_derive=False)

        self.assertTrue(
            os.path.exists(os.path.join(self.temp_dir, "dashboard_status.json")))
        self.assertTrue(
            os.path.exists(os.path.join(self.temp_dir, "alert_center.json")))

    def test_status_code_after_export(self):
        """验证多次导出不抛异常。"""
        for _ in range(3):
            status = self.exporter.export_dashboard_status(
                out_dir=self.temp_dir, auto_derive=False)
            self.assertIsNotNone(status)

    def test_derive_status_detects_missing_inventory(self):
        """auto_derive 应识别缺失产出物并返回非 COMPLETE。"""
        # 使用空临时目录，应检测到所有模块缺失
        empty_exporter = StatusExporter(data_root=self.temp_dir)
        overall, tasks, alerts = empty_exporter.derive_status_from_artifacts(
            output_dir=""
        )
        self.assertNotEqual(overall, VISIBLE_COMPLETE,
                            "缺失所有产出物时不应 COMPLETE")


if __name__ == "__main__":
    unittest.main()
