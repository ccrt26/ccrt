"""
PredictionLedger schema 测试。

验证：
  1. 必填字段完整
  2. 字段类型正确
  3. 幂等键全覆盖
  4. status 枚举值完整
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

SCHEMA_PATH = "00_项目地基/01_数据契约/prediction_ledger.schema.json"


class TestPredictionLedgerSchema(unittest.TestCase):
    """PredictionLedger schema 测试"""

    @classmethod
    def setUpClass(cls):
        full_path = os.path.join(os.path.dirname(__file__), "..", "..", SCHEMA_PATH)
        with open(full_path, "r") as f:
            cls.schema = json.load(f)

    def test_schema_is_valid_json(self):
        self.assertIn("$schema", self.schema)
        self.assertIn("title", self.schema)

    def test_required_fields(self):
        required = self.schema.get("required", [])
        self.assertIn("ledger_id", required)
        self.assertIn("stock_code", required)
        self.assertIn("trade_date", required)
        self.assertIn("source_type", required)
        self.assertIn("baseline_id", required)
        self.assertIn("prediction_type", required)
        self.assertIn("assertion", required)
        self.assertIn("horizon", required)
        self.assertIn("status", required)
        self.assertIn("created_at", required)

    def test_source_type_enum(self):
        source_type = self.schema["properties"]["source_type"]
        self.assertIn("enum", source_type)
        self.assertIn("deep_analysis", source_type["enum"])
        self.assertIn("daily_report", source_type["enum"])

    def test_prediction_type_enum(self):
        pred_type = self.schema["properties"]["prediction_type"]
        self.assertIn("enum", pred_type)
        all_types = {"directional", "range", "trigger_condition",
                     "risk_warning", "event"}
        self.assertEqual(set(pred_type["enum"]), all_types)

    def test_status_enum(self):
        status = self.schema["properties"]["status"]
        self.assertIn("enum", status)
        all_status = {"PENDING", "DUE", "HIT", "MISS", "PARTIAL",
                      "INSUFFICIENT_DATA", "OBSERVE", "BLOCK"}
        self.assertEqual(set(status["enum"]), all_status)

    def test_trade_date_pattern(self):
        td = self.schema["properties"]["trade_date"]
        self.assertEqual(td["pattern"], "^[0-9]{8}$")

    def test_idempotency_key_fields_exist(self):
        """幂等键所需字段在 properties 中存在。"""
        props = self.schema["properties"]
        idempotent_fields = [
            "stock_code", "trade_date", "source_type",
            "baseline_id", "prediction_type", "horizon", "assertion_hash",
        ]
        for field in idempotent_fields:
            self.assertIn(field, props,
                          f"幂等键字段 {field} 不在 schema 中")

    def test_no_additional_properties(self):
        self.assertTrue(self.schema.get("additionalProperties", True) is False)


if __name__ == "__main__":
    unittest.main()
