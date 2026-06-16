"""RuleHealthSummary 测试"""
import json, os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from 代码文件.重点股票.product_eval.rule_health_summary import RuleHealthSummaryService

class TestRuleHealthSummary(unittest.TestCase):
    def setUp(self):
        self.svc = RuleHealthSummaryService("/tmp")
    def test_build_default(self):
        r = self.svc.build_rule_health()
        self.assertEqual(r["rule_id"], "TECH_MA20_BREAK_STOP_LOSS")
        self.assertIn("rule_status", r)
    def test_derive_from_missing_backtest(self):
        r = self.svc.derive_from_backtest("/nonexistent.json")
        self.assertIsNone(r)

if __name__ == "__main__":
    unittest.main()
