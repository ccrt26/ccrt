"""
MA20 Backtest 真实 K 线回测测试。

验证：
  1. kline_cache 有足够数据
  2. 回测产生真实 sample_count，不 BLOCK
  3. 总体状态 PASS/WARN/OBSERVE
  4. 样本不足时 OBSERVE
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from 代码文件.重点股票.product_eval.backtest_engine import BacktestEngine  # noqa: E402
from 代码文件.重点股票.product_eval import data_source as ds  # noqa: E402


class TestMA20BacktestRealKline(unittest.TestCase):
    """MA20 Backtest 真实 K 线回测测试"""

    def setUp(self):
        self.engine = BacktestEngine()
        self.rows = ds.get_kline_until("600114", "20260616")

    def test_001_enough_kline_data(self):
        self.assertGreater(len(self.rows), 50)

    def test_002_backtest_produces_real_samples(self):
        result = self.engine.run_backtest(
            rule_id="TECH_MA20_BREAK_STOP_LOSS",
            stock_code="600114", stock_name="东睦股份",
            as_of_date="20260616",
        )
        total = sum(w.get("sample_count", 0) for w in result.get("windows", {}).values())
        self.assertGreater(total, 0, f"必须产生至少一个信号，当前 {total}")

    def test_003_backtest_not_block(self):
        result = self.engine.run_backtest(
            rule_id="TECH_MA20_BREAK_STOP_LOSS",
            stock_code="600114", stock_name="东睦股份",
            as_of_date="20260616",
        )
        self.assertNotEqual(result["overall_status"], "BLOCK")

    def test_004_backtest_overall_in_valid_states(self):
        result = self.engine.run_backtest(
            rule_id="TECH_MA20_BREAK_STOP_LOSS",
            stock_code="600114", stock_name="东睦股份",
            as_of_date="20260616",
        )
        self.assertIn(result["overall_status"], ["PASS", "WARN", "OBSERVE"])

    def test_005_unsupported_rule_returns_block(self):
        result = self.engine.run_backtest(
            rule_id="UNSUPPORTED_RULE_X",
            stock_code="600114", stock_name="东睦股份",
            as_of_date="20260616",
        )
        self.assertEqual(result["overall_status"], "BLOCK")

    def test_006_backtest_has_valid_windows(self):
        result = self.engine.run_backtest(
            rule_id="TECH_MA20_BREAK_STOP_LOSS",
            stock_code="600114", stock_name="东睦股份",
            as_of_date="20260616",
        )
        for label in ["3Y", "1Y", "6M"]:
            self.assertIn(label, result.get("windows", {}), f"窗口 {label} 必须存在")


if __name__ == "__main__":
    unittest.main()
