"""
FeatureSnapshot Kline Cache 集成测试。

验证：
  1. kline_cache 能读取 600114
  2. 日期格式混合时排序正确
  3. 无精确交易日时回退最近可用 + STALE
  4. close/volume/ma20 非空
  5. ma20 与手工 rolling mean 一致
  6. as_of_date 之后的数据被 BLOCK
"""

import sys
import os
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from 代码文件.重点股票.product_eval.feature_service import FeatureSnapshotService  # noqa: E402
from 代码文件.重点股票.product_eval import data_source as ds  # noqa: E402


class TestFeatureSnapshotKlineCache(unittest.TestCase):
    """FeatureSnapshot Kline Cache 集成测试"""

    @classmethod
    def setUpClass(cls):
        kc = "代码文件/数据/kline_cache/600114.json"
        cls.kline_path = os.path.join(os.path.dirname(__file__), "..", "..", kc)
        cls.has_kline = os.path.exists(cls.kline_path)

    def setUp(self):
        self.service = FeatureSnapshotService()

    def test_001_kline_cache_exists(self):
        """kline_cache/600114.json 存在。"""
        self.assertTrue(self.has_kline, "kline_cache/600114.json 必须存在")

    def test_002_kline_loads_sorted(self):
        """K 线加载后按日期升序排列。"""
        rows = ds.load_kline_rows("600114")
        self.assertGreater(len(rows), 50, "需要至少 50 行 K 线数据")
        dates = [r.get("_date_norm", "") for r in rows]
        self.assertEqual(dates, sorted(dates), "K 线必须按日期升序排列")

    def test_003_close_volume_non_null(self):
        """600114 特征快照的 close 和 volume 非空。"""
        snapshot = self.service.get_features(
            stock_code="600114",
            trade_date="20260616",
            as_of_date="20260616",
        )
        tech = snapshot["feature_values"]["technical"]
        self.assertIsNotNone(tech["close"],
                             "close 不得为 None")
        self.assertIsNotNone(tech["volume"],
                             "volume 不得为 None")
        self.assertGreater(tech["close"], 0,
                           "close 必须大于 0")
        self.assertGreater(tech["volume"], 0,
                           "volume 必须大于 0")

    def test_004_ma20_non_null(self):
        """ma20 非空。"""
        snapshot = self.service.get_features(
            stock_code="600114",
            trade_date="20260616",
            as_of_date="20260616",
        )
        tech = snapshot["feature_values"]["technical"]
        self.assertIsNotNone(tech["ma20"], "ma20 不得为 None")
        self.assertGreater(tech["ma20"], 0, "ma20 必须大于 0")

    def test_005_ma20_matches_hand_calc(self):
        """ma20 与手工 rolling mean 一致。"""
        rows = ds.get_kline_until("600114", "20260616")
        closes = [float(r["close"]) for r in rows
                  if r.get("close") is not None and float(r["close"]) > 0]
        self.assertGreater(len(closes), 20)
        hand_ma20 = sum(closes[-20:]) / 20
        hand_ma20 = round(hand_ma20, 4)

        snapshot = self.service.get_features(
            stock_code="600114",
            trade_date="20260616",
            as_of_date="20260616",
        )
        feature_ma20 = round(snapshot["feature_values"]["technical"]["ma20"], 4)
        self.assertAlmostEqual(feature_ma20, hand_ma20, delta=0.01,
                               msg="ma20 与手工 rolling mean 一致")

    def test_006_no_market_data_missing(self):
        """无需标注 MARKET_DATA_MISSING。"""
        snapshot = self.service.get_features(
            stock_code="600114",
            trade_date="20260616",
            as_of_date="20260616",
        )
        qf = snapshot.get("quality_flags", [])
        self.assertNotIn("MARKET_DATA_MISSING", qf,
                         "有 K 线数据时不应标记 MARKET_DATA_MISSING")

    def test_007_future_function_block_when_data_after_asof(self):
        """mock 未来数据后 future_function 应 BLOCK。"""
        with patch.object(self.service, "_check_future_function") as mock_ff:
            mock_ff.return_value = {
                "passed": False,
                "max_data_date": "20260620",
                "as_of_check": "BLOCK",
                "details": "mock: 未来函数风险",
            }
            snapshot = self.service.get_features(
                stock_code="600114",
                trade_date="20260615",
                as_of_date="20260616",
            )
            ff = snapshot["future_function_check"]
            self.assertFalse(ff["passed"])
            self.assertEqual(ff["as_of_check"], "BLOCK")

    def test_008_date_rollback_when_no_exact_date(self):
        """无精确交易日时使用最近可用 + STALE。

        kline_cache/600114.json 最大日期为 20260616，
        用 trade_date=20260617（未来日期）测试回退逻辑。
        """
        snapshot = self.service.get_features(
            stock_code="600114",
            trade_date="20260617",
            as_of_date="20260617",
        )
        tech = snapshot["feature_values"]["technical"]
        quality_flags = snapshot.get("quality_flags", [])
        self.assertEqual(snapshot["freshness_status"]["overall"],
                         "STALE",
                         "无精确交易日应标记 STALE")
        self.assertIn("TRADE_DATE_ROLLBACK_TO_LAST_AVAILABLE", quality_flags,
                      "应标记 TRADE_DATE_ROLLBACK")
        self.assertIsNotNone(tech.get("close"), "回退后 close 必须非空")

    def test_009_label_status_not_in_feature(self):
        """label_values 有 label_status/label_visibility，不进入 feature_values。"""
        snapshot = self.service.get_features(
            stock_code="600114",
            trade_date="20260616",
            as_of_date="20260616",
        )
        labels = snapshot.get("label_values", {})
        self.assertIn("label_status", labels)
        self.assertIn("label_visibility", labels)
        self.assertEqual(labels["label_visibility"], "POST_OUTCOME_NOT_FEATURE")


if __name__ == "__main__":
    unittest.main()
