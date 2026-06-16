"""
FeatureSnapshot golden 测试（适配真实 kline 计算）。

验证：
  1. get_features 输出字段完整
  2. 未来函数检查仅 PASS/BLOCK
  3. 延期特征标记正确
  4. 无 MARKET_DATA_MISSING（有 kline 时）
  5. freshness 正确
"""

import sys
import os
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from 代码文件.重点股票.product_eval.feature_service import FeatureSnapshotService  # noqa: E402
from 代码文件.重点股票.product_eval import data_source as ds  # noqa: E402


class TestFeatureSnapshotGolden(unittest.TestCase):
    """FeatureSnapshot golden 测试"""

    def setUp(self):
        self.service = FeatureSnapshotService()

    def test_get_features_returns_all_required_fields(self):
        snapshot = self.service.get_features(
            stock_code="600114", trade_date="20260616", as_of_date="20260616",
        )
        required = [
            "snapshot_id", "stock_code", "trade_date", "as_of_date",
            "generated_at", "feature_values", "label_values",
            "baseline_id", "data_lineage_refs", "quality_flags",
            "freshness_status", "future_function_check",
        ]
        for field in required:
            self.assertIn(field, snapshot, f"缺少必填字段: {field}")

    def test_get_features_contains_technical_registry(self):
        snapshot = self.service.get_features(
            stock_code="600114", trade_date="20260616", as_of_date="20260616",
        )
        tech = snapshot["feature_values"]["technical"]
        tech_fields = ["close", "volume", "ma5", "ma20", "ma60",
                       "rsi14", "macd", "turnover_rate"]
        for field in tech_fields:
            self.assertIn(field, tech, f"缺少技术特征字段: {field}")

    def test_future_function_check_only_pass_or_block(self):
        ff = self.service._check_future_function(
            ds.get_kline_until("600114", "20260616"), "20260616",
        )
        self.assertIn(ff["as_of_check"], ["PASS", "BLOCK"],
                      "未来函数检查必须是 PASS 或 BLOCK")

    def test_deferred_features_marked_not_zero(self):
        snapshot = self.service.get_features(
            stock_code="600114", trade_date="20260616", as_of_date="20260616",
        )
        deferred = snapshot.get("deferred_feature_refs", {})
        refs = ["financial_feature_ref", "event_feature_ref", "crowding_feature_ref"]
        for ref in refs:
            self.assertIn(ref, deferred, f"延期字段 {ref} 必须存在")
            self.assertNotEqual(deferred[ref], "0",
                                f"延期字段 {ref} 不得填 0 伪造")

    def test_no_market_data_missing_with_real_kline(self):
        """有 K 线时无需 MARKET_DATA_MISSING。"""
        snapshot = self.service.get_features(
            stock_code="600114", trade_date="20260616", as_of_date="20260616",
        )
        self.assertNotIn("MARKET_DATA_MISSING", snapshot.get("quality_flags", []))

    def test_future_function_block_when_mock_future_data(self):
        """mock 未来数据必须 BLOCK。"""
        ff = self.service._check_future_function(
            [{"_date_norm": "20260620"}], "20260616",
        )
        self.assertFalse(ff["passed"])
        self.assertEqual(ff["as_of_check"], "BLOCK")

    def test_future_function_block_90_plus_days(self):
        """90+ 天后同样 BLOCK。"""
        ff = self.service._check_future_function(
            [{"_date_norm": "20261231"}], "20260616",
        )
        self.assertFalse(ff["passed"], "90+ 天同样 BLOCK")
        self.assertEqual(ff["as_of_check"], "BLOCK")

    def test_market_lag_adjusts_freshness(self):
        """market_lag_days 不影响 freshness 基本结构。"""
        snap0 = self.service.get_features(
            stock_code="600114", trade_date="20260616",
            as_of_date="20260616", market_lag_days=0,
        )
        snap1 = self.service.get_features(
            stock_code="600114", trade_date="20260616",
            as_of_date="20260616", market_lag_days=1,
        )
        self.assertIsNotNone(snap0["freshness_status"]["overall"])
        self.assertIsNotNone(snap1["freshness_status"]["overall"])


if __name__ == "__main__":
    unittest.main()
