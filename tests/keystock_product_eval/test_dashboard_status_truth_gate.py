"""测试状态闸门——阻止假 COMPLETE。"""
import json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from 代码文件.重点股票.product_eval.conclusion_status import (
    ConclusionStatusService, BLOCKED, FORMAL, SHADOW, OBSERVATION,
    VISIBLE_BLOCK, VISIBLE_COMPLETE, VISIBLE_AUTO_REPAIRING,
)


class TestDashboardStatusTruthGate(unittest.TestCase):
    """状态闸门真实性测试。"""

    def setUp(self):
        self.svc = ConclusionStatusService(run_mode="shadow")

    def test_date_divergence_blocks_visible(self):
        """DATA_DATE_DIVERGENCE 导致 user_visible_status=BLOCK。"""
        result = self.svc.evaluate(
            stock_code="600114", stock_name="东睦股份", trade_date="20260616",
            data_date_divergence=True,
        )
        self.assertEqual(result["user_visible_status"], VISIBLE_BLOCK)

    def test_data_stale_blocks_visible(self):
        """DATA_STALE 导致 user_visible_status=BLOCK。"""
        result = self.svc.evaluate(
            stock_code="600114", stock_name="东睦股份", trade_date="20260616",
            freshness_status="STALE",
        )
        self.assertEqual(result["user_visible_status"], VISIBLE_BLOCK)

    def test_rule_health_warn_blocks_visible(self):
        """RULE_HEALTH_WARN 导致 user_visible_status=BLOCK。"""
        result = self.svc.evaluate(
            stock_code="600114", stock_name="东睦股份", trade_date="20260616",
            rule_health_status="WARN",
        )
        self.assertEqual(result["user_visible_status"], VISIBLE_BLOCK)

    def test_position_unavailable_adds_blocker(self):
        """POSITION_UNAVAILABLE 出现在 blockers 中。"""
        result = self.svc.evaluate(
            stock_code="600114", stock_name="东睦股份", trade_date="20260616",
            position_status="UNAVAILABLE",
        )
        self.assertIn("POSITION_UNAVAILABLE", result["decision_blockers"])

    def test_all_blockers_present(self):
        """四个标准 blockers 全部出现。"""
        result = self.svc.evaluate(
            stock_code="600114", stock_name="东睦股份", trade_date="20260616",
            freshness_status="STALE",
            data_date_divergence=True,
            rule_health_status="WARN",
            position_status="UNAVAILABLE",
        )
        self.assertIn("DATA_STALE", result["decision_blockers"])
        self.assertIn("DATA_DATE_DIVERGENCE", result["decision_blockers"])
        self.assertIn("RULE_HEALTH_WARN", result["decision_blockers"])
        self.assertIn("POSITION_UNAVAILABLE", result["decision_blockers"])
        self.assertEqual(result["conclusion_status"], BLOCKED)
        self.assertEqual(result["user_visible_status"], VISIBLE_BLOCK)

    def test_shadow_mode_default_blocked(self):
        """shadow 模式默认 BLOCKED（无明确 blocker 时仍为 SHADOW 而非 FORMAL）。"""
        result = self.svc.evaluate(
            stock_code="600114", stock_name="东睦股份", trade_date="20260616",
            freshness_status="FRESH",
            rule_health_status="PASS",
            position_status="AVAILABLE",
        )
        self.assertEqual(result["conclusion_status"], SHADOW)

    def test_formal_only_when_all_clear(self):
        """仅当全部清除且 run_mode=formal 时为 FORMAL。"""
        svc = ConclusionStatusService(run_mode="formal")
        result = svc.evaluate(
            stock_code="600114", stock_name="东睦股份", trade_date="20260616",
            freshness_status="FRESH",
            rule_health_status="PASS",
            position_status="AVAILABLE",
        )
        self.assertEqual(result["conclusion_status"], FORMAL)
        self.assertEqual(result["user_visible_status"], VISIBLE_COMPLETE)
        self.assertEqual(result["decision_status"], "AVAILABLE")


if __name__ == "__main__":
    unittest.main()
