"""
Future Function Gate 专向测试。

验证：
  1. kline 正常数据 → PASS
  2. mock 未来数据 → BLOCK（任何 > cutoff 的数据）
  3. 无 K 线数据 → PASS（无数据可漏）
  4. backtest 集成 → future_function_risk 反映 future_function_check
"""

import sys
import os
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from 代码文件.重点股票.product_eval.feature_service import FeatureSnapshotService  # noqa: E402
from 代码文件.重点股票.product_eval.backtest_engine import BacktestEngine  # noqa: E402
from 代码文件.重点股票.product_eval import data_source as ds  # noqa: E402


class TestFutureFunctionGate(unittest.TestCase):
    """未来函数闸门测试"""

    def setUp(self):
        self.fs = FeatureSnapshotService()
        self.be = BacktestEngine()

    def test_001_normal_kline_pass(self):
        """正常 K 线（无超 cutoff 数据）→ PASS。"""
        ff = self.fs._check_future_function(
            ds.get_kline_until("600114", "20260616"),
            "20260616",
        )
        self.assertEqual(ff["as_of_check"], "PASS",
                         "正常 K 线数据应 PASS")

    def test_002_mock_future_data_block(self):
        """mock 未来数据 → BLOCK。"""
        mock_rows = [{"_date_norm": "20260620"}]
        ff = self.fs._check_future_function(mock_rows, "20260616")
        self.assertFalse(ff["passed"], "mock 未来数据必须 failed")
        self.assertEqual(ff["as_of_check"], "BLOCK",
                         "未来数据必须 BLOCK")

    def test_003_mock_future_data_one_day(self):
        """即使仅多 1 天数据也 BLOCK。"""
        mock_rows = [{"_date_norm": "20260617"}]
        ff = self.fs._check_future_function(mock_rows, "20260616")
        self.assertEqual(ff["as_of_check"], "BLOCK",
                         "仅多 1 天也必须 BLOCK")

    def test_004_no_data_pass(self):
        """无 K 线数据 → PASS（无数据可漏）。"""
        ff = self.fs._check_future_function([], "20260616")
        self.assertEqual(ff["as_of_check"], "PASS",
                         "无 K 线数据应 PASS")

    def test_005_backtest_block_on_future_data(self):
        """backtest 检测到未来函数时 BLOCK。"""
        with patch.object(self.fs, "_check_future_function") as mock_ff:
            mock_ff.return_value = {
                "passed": False,
                "max_data_date": "20260620",
                "as_of_check": "BLOCK",
                "details": "mock: 未来函数 BLOCK",
            }
            # 这时 backtest 的 feature_service 使用同一 fs
            engine = BacktestEngine(feature_service=self.fs)
            result = engine.run_backtest(
                rule_id="TECH_MA20_BREAK_STOP_LOSS",
                stock_code="600114",
                stock_name="东睦股份",
                as_of_date="20260616",
            )
            self.assertEqual(result["overall_status"], "BLOCK",
                             "未来函数 BLOCK 时回测必须 BLOCK")

    def test_006_future_function_gate_no_warn(self):
        """未来函数检查不应有 WARN 灰色地带（仅 PASS 或 BLOCK）。"""
        test_cases = [
            (ds.get_kline_until("600114", "20260616"), "20260616"),
            ([], "20260616"),
            ([{"_date_norm": "20260617"}], "20260616"),
            ([{"_date_norm": "20261231"}], "20260616"),
        ]
        for rows, cutoff in test_cases:
            ff = self.fs._check_future_function(rows, cutoff)
            self.assertIn(ff["as_of_check"], ["PASS", "BLOCK"],
                          f"未来函数检查不应有 WARN: cutoff={cutoff}, rows={rows}")


if __name__ == "__main__":
    unittest.main()
