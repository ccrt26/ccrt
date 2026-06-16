"""
BacktestEngine 负向测试。

验证：
  1. 有真实 K 线时回测产生样本，不 BLOCK
  2. 不支持的规则 → BLOCK
  3. 质量闸门字段完整
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from 代码文件.重点股票.product_eval.backtest_engine import BacktestEngine  # noqa: E402
from 代码文件.重点股票.product_eval import MIN_SAMPLES_REQUIRED  # noqa: E402


class TestBacktestNegativeFutureFunction(unittest.TestCase):
    """回测负向测试"""

    def setUp(self):
        self.engine = BacktestEngine()

    def test_unsupported_rule_returns_block(self):
        """不支持的规则 BLOCK。"""
        result = self.engine.run_backtest(
            rule_id="UNSUPPORTED_RULE_X",
            stock_code="600114",
            stock_name="东睦股份",
            as_of_date="20260616",
        )
        self.assertEqual(result["overall_status"], "BLOCK")
        self.assertIn("不支持的规则", result.get("error", ""))

    def test_min_samples_constant_is_reasonable(self):
        self.assertGreaterEqual(MIN_SAMPLES_REQUIRED, 2)

    def test_backtest_not_block_with_real_kline(self):
        """有真实 K 线时回测不应 BLOCK。"""
        result = self.engine.run_backtest(
            rule_id="TECH_MA20_BREAK_STOP_LOSS",
            stock_code="600114",
            stock_name="东睦股份",
            as_of_date="20260616",
        )
        self.assertNotEqual(result["overall_status"], "BLOCK",
                            "有真实 K 线时不应 BLOCK")
        total_samples = sum(
            w.get("sample_count", 0) for w in result.get("windows", {}).values()
        )
        self.assertGreater(total_samples, 0, "必须产生真实样本")

    def test_quality_gates_fields_present(self):
        """质量闸门字段完整。"""
        result = self.engine.run_backtest(
            rule_id="TECH_MA20_BREAK_STOP_LOSS",
            stock_code="600114",
            stock_name="东睦股份",
            as_of_date="20260616",
        )
        for label, win in result.get("windows", {}).items():
            gates = win.get("quality_gates", {})
            required = ["data_visibility_proven", "sample_sufficient",
                        "has_rule_version", "future_function_risk",
                        "output_reproducible"]
            for field in required:
                self.assertIn(field, gates,
                              f"窗口 {label} 质量闸门缺少字段 {field}")
            self.assertIsInstance(gates["future_function_risk"], bool)


if __name__ == "__main__":
    unittest.main()
