"""测试 PositionAdapter 持仓数据脱敏。"""
import json, os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from 代码文件.重点股票.product_eval.position_adapter import PositionAdapter


class TestPositionDataRedaction(unittest.TestCase):
    """位置数据脱敏测试。"""

    def setUp(self):
        self.adapter = PositionAdapter()

    def test_has_position_false(self):
        """has_position 始终为 False。"""
        pos = self.adapter.get_public_position()
        self.assertFalse(pos["has_position"])

    def test_position_status_unavailable(self):
        """position_status 始终为 UNAVAILABLE。"""
        pos = self.adapter.get_public_position()
        self.assertEqual(pos["position_status"], "UNAVAILABLE")

    def test_cost_price_none(self):
        """cost_price 始终为 None。"""
        pos = self.adapter.get_public_position()
        self.assertIsNone(pos["cost_price"])

    def test_quantity_none(self):
        """quantity 始终为 None。"""
        pos = self.adapter.get_public_position()
        self.assertIsNone(pos["quantity"])

    def test_unrealized_pnl_none(self):
        """unrealized_pnl 始终为 None。"""
        pos = self.adapter.get_public_position()
        self.assertIsNone(pos["unrealized_pnl"])

    def test_unrealized_pnl_pct_none(self):
        """unrealized_pnl_pct 始终为 None。"""
        pos = self.adapter.get_public_position()
        self.assertIsNone(pos["unrealized_pnl_pct"])

    def test_has_market_price_when_provided(self):
        """传入 market_price 时包含该字段。"""
        pos = self.adapter.get_public_position(market_price=16.52)
        self.assertEqual(pos["market_price"], 16.52)

    def test_generated_at_present(self):
        """generated_at 时间戳存在。"""
        pos = self.adapter.get_public_position()
        self.assertIn("generated_at", pos)
        self.assertTrue(pos["generated_at"])

    def test_no_real_position_fields(self):
        """禁止出现真实持仓字段。"""
        pos = self.adapter.get_public_position()
        forbidden = ["real_cost", "real_quantity", "real_pnl", "position_id"]
        for field in forbidden:
            self.assertNotIn(field, pos, f"禁止字段出现: {field}")


if __name__ == "__main__":
    unittest.main()
