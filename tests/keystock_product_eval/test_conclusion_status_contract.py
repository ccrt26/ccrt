"""测试 ConclusionStatusService 契约。"""
import json, os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from 代码文件.重点股票.product_eval.conclusion_status import (
    ConclusionStatusService, BLOCKED, FORMAL, SHADOW, OBSERVATION,
    VISIBLE_BLOCK, VISIBLE_COMPLETE, VISIBLE_AUTO_REPAIRING,
    DATA_FRESH, DATA_STALE, DATA_DIVERGED, DATA_MISSING,
    DECISION_AVAILABLE, DECISION_BLOCKED, DECISION_OBSERVATION_ONLY,
)


class TestConclusionStatusContract(unittest.TestCase):
    """ConclusionStatusService 结构契约。"""

    def setUp(self):
        self.svc = ConclusionStatusService()

    def test_output_contains_required_fields(self):
        """输出包含所有必填字段。"""
        result = self.svc.evaluate(
            stock_code="600114", stock_name="东睦股份", trade_date="20260616",
        )
        required = [
            "stock_code", "stock_name", "trade_date", "generated_at", "run_mode",
            "conclusion_status", "user_visible_status", "data_status",
            "decision_status", "decision_blockers", "warning_reasons",
            "blocking_reasons", "status_gate_source_refs",
        ]
        for field in required:
            self.assertIn(field, result, f"缺少字段: {field}")

    def test_status_gate_source_refs_has_required_fields(self):
        """status_gate_source_refs 包含所有引用字段。"""
        result = self.svc.evaluate(
            stock_code="600114", stock_name="东睦股份", trade_date="20260616",
        )
        refs = result["status_gate_source_refs"]
        required = [
            "freshness_status", "data_date_divergence",
            "source_last_date", "feature_snapshot_actual_date",
            "rule_health_status", "evidence_status", "position_status",
        ]
        for field in required:
            self.assertIn(field, refs, f"缺少引用字段: {field}")

    def test_conclusion_status_constants_valid(self):
        """所有结论状态常量有效。"""
        valid = {BLOCKED, FORMAL, SHADOW, OBSERVATION}
        result = self.svc.evaluate(
            stock_code="600114", stock_name="东睦股份", trade_date="20260616",
        )
        self.assertIn(result["conclusion_status"], valid)

    def test_decision_status_constants_valid(self):
        """所有决策状态常量有效。"""
        valid = {DECISION_AVAILABLE, DECISION_BLOCKED, DECISION_OBSERVATION_ONLY}
        result = self.svc.evaluate(
            stock_code="600114", stock_name="东睦股份", trade_date="20260616",
        )
        self.assertIn(result["decision_status"], valid)

    def test_user_visible_status_constants_valid(self):
        """所有用户可见状态常量有效。"""
        valid = {VISIBLE_COMPLETE, VISIBLE_AUTO_REPAIRING, VISIBLE_BLOCK}
        result = self.svc.evaluate(
            stock_code="600114", stock_name="东睦股份", trade_date="20260616",
        )
        self.assertIn(result["user_visible_status"], valid)

    def test_blocking_reasons_matches_decision_blockers(self):
        """blocking_reasons 应与 decision_blockers 一致。"""
        result = self.svc.evaluate(
            stock_code="600114", stock_name="东睦股份", trade_date="20260616",
            freshness_status="STALE",
            data_date_divergence=True,
            rule_health_status="WARN",
            position_status="UNAVAILABLE",
        )
        self.assertEqual(result["blocking_reasons"], result["decision_blockers"])


if __name__ == "__main__":
    unittest.main()
