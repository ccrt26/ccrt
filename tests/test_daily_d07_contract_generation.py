#!/usr/bin/env python3
"""
test_daily_d07_contract_generation.py — D07 contract generation tests

Tests that build_daily_d07_contract() produces valid D07_v1.2 output.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from daily_d07_contract_builder import build_daily_d07_contract


# Sample data for 600114 20260616
SAMPLE_DATE = "20260616"
SAMPLE_CODE = "600114"
SAMPLE_NAME = "东睦股份"

SAMPLE_K = {
    "date": "2026-06-16",
    "open": 42.12,
    "close": 41.88,
    "high": 42.50,
    "low": 41.50,
    "volume": 8500000,
}

SAMPLE_F = {
    "date": "2026-06-16",
    "super_large_net": 120.0,
    "large_net": -80.0,
    "medium_net": -30.0,
    "small_net": -10.0,
    "main_force_net": 40.0,
}

SAMPLE_BL = {
    "baseline_id": "600114_W2026W25",
    "key_support_price": 38.00,
    "key_pressure_price": 46.44,
    "ma20_support_price": 41.20,
    "stop_loss_price": 37.15,
    "target_price": 46.44,
    "core_thesis": "东睦股份核心逻辑",
    "valid_until": "2026-06-27",
    "key_levels": {
        "S1": 38.00,
        "R1": 46.44,
        "stop_loss_new": 41.50,
        "stop_loss_held": 37.15,
    },
    "position_cap": "600股@39.42",
}

SAMPLE_P0 = {
    "t1_action": "持有待涨，不主动加仓",
    "current_position_cap": "600股@39.42",
    "triggered_position_cap": "站稳46.44且主力流出收窄后再评估",
    "key_buy_point": "先看38.00能否收回，再看46.44能否站稳",
    "new_position_stop_loss": "41.50下破不新开",
    "held_position_stop_loss": "短线41.50；中线37.15",
    "forbidden_actions": [
        "46.44以上不追高",
        "主力流出未收窄不加仓",
        "跌破41.50不补仓",
        "跌破37.15或核心反证出现则移出/否决",
    ],
    "confidence_level": "中",
    "action_change": "maintain",
    "one_line_conclusion": "东睦股份收41.88，低于关键压力46.44；主力+40万，先看38.00能否收回，再看46.44能否站稳。",
}

SAMPLE_ROLES = {
    "山猫_宏观": {"板块相位": "主升调整", "解读": "电力设备板块相位为主升调整，对东睦股份是背景支撑。"},
    "信鸽_事件": {"解读": "东睦股份当日未触发强制否决事件。"},
    "玉夜_数据": {"解读": "6月16日收41.88，成交量8.5万手，主力+40万。"},
    "流金_风控": {"综合灯": "yellow", "综合灯显示": "黄灯", "解读": "未站稳46.44前不扩大仓位，跌破41.50先控风险。"},
    "青山_信号": {"解读": "价格低于46.44，信号只支持跟踪，不支持追高。"},
    "腰子_整合": {"解读": "东睦股份收41.88，低于关键压力46.44；主力+40万，先看38.00能否收回，再看46.44能否站稳。"},
}

SAMPLE_SYNTHESIS = {}
objs = ["p0_action","baseline_interpretation","kline_interpretation","market_sector_interpretation",
        "fund_flow_interpretation","risk_interpretation","event_interpretation",
        "signal_interpretation","tomorrow_plan","t5_outlook"]
for obj in objs:
    SAMPLE_SYNTHESIS[obj] = {
        "data_fact": f"{SAMPLE_NAME} {SAMPLE_DATE} 收{SAMPLE_K['close']}",
        "interpretation": f"价格未站稳",
        "action_impact": "持有待涨，不主动加仓",
        "trigger_condition": f"收回38.00并站稳46.44",
        "invalidation_condition": f"跌破41.50或跌破37.15",
        "confidence": "中",
    }


def build_default(**overrides):
    kwargs = {
        "date": SAMPLE_DATE,
        "code": SAMPLE_CODE,
        "name": SAMPLE_NAME,
        "k": SAMPLE_K,
        "f": SAMPLE_F,
        "bl": SAMPLE_BL,
        "p0": SAMPLE_P0,
        "roles": SAMPLE_ROLES,
        "daily_synthesis": SAMPLE_SYNTHESIS,
        "degraded_items": [],
        "support": 38.00,
        "pressure": 46.44,
        "stop": 37.15,
        "phase": "主升调整",
        "industry": "电力设备",
        "baseline_id": "600114_W2026W25",
    }
    kwargs.update(overrides)
    return build_daily_d07_contract(**kwargs)


class TestD07ContractBuilder(unittest.TestCase):

    def test_full_field_set(self):
        """Builder returns all REQUIRED_TOP_LEVEL fields."""
        result = build_default()
        required = [
            "framework_version", "logic_version", "interpretation_id",
            "conclusion_strength", "hypotheses", "evidence_gap_requests",
            "rule_refs", "knowledge_refs", "d07_interpretation",
            "unified_interpretation", "role_interpretations",
        ]
        for field in required:
            self.assertIn(field, result, f"Missing required field: {field}")

    def test_framework_version(self):
        result = build_default()
        self.assertEqual(result["framework_version"], "D07_v1.2")

    def test_logic_version_contains_v3_6_3(self):
        result = build_default()
        self.assertIn("v3.6.3", str(result["logic_version"]))

    def test_interpretation_id_format(self):
        result = build_default()
        iid = result["interpretation_id"]
        self.assertRegex(iid, r"^INT-\d{8}-\d{6}-[a-z0-9]{6}$")

    def test_hypotheses_min_2(self):
        result = build_default()
        self.assertGreaterEqual(len(result["hypotheses"]), 2)

    def test_hypotheses_has_risk(self):
        """At least one hypothesis is a reverse/risk hypothesis."""
        result = build_default()
        statements = " ".join(h["statement"] for h in result["hypotheses"])
        self.assertTrue(any(kw in statements for kw in ["跌破", "风险", "走弱", "止损"]))

    def test_rule_refs_contains_required(self):
        result = build_default()
        refs = result["rule_refs"]
        for required in ("D07_v1.2", "U-9", "U-10"):
            self.assertIn(required, refs)

    def test_conclusion_strength_not_keding_when_margin_degraded(self):
        """With margin degradation, conclusion_strength must not be '可定性'."""
        result = build_default(degraded_items=["margin(T+1延迟,最新20260615)"])
        self.assertNotEqual(result["conclusion_strength"], "可定性")
        self.assertIn(result["conclusion_strength"], ["数据不足", "风险假设", "倾向判断"])

    def test_evidence_gap_requests_on_margin_degraded(self):
        """Margin degradation triggers open field_missing gap."""
        result = build_default(degraded_items=["margin(T+1延迟,最新20260615)"])
        gaps = result["evidence_gap_requests"]
        self.assertTrue(any(
            g.get("gap_type") == "field_missing" and g.get("status") == "open"
            for g in gaps
        ))

    def test_interpretation_id_consistency(self):
        """interpretation_id must match d07_interpretation.interpretation_id."""
        result = build_default()
        self.assertEqual(
            result["interpretation_id"],
            result["d07_interpretation"]["interpretation_id"],
        )

    def test_role_interpretations_complete(self):
        """All 6 roles have 职责/解读/结论."""
        roles = build_default()["role_interpretations"]
        required_roles = ["山猫_宏观", "信鸽_事件", "玉夜_数据", "流金_风控", "青山_信号", "腰子_整合"]
        for role_name in required_roles:
            self.assertIn(role_name, roles, f"Missing role: {role_name}")
            for field in ("职责", "解读", "结论"):
                self.assertIn(field, roles[role_name],
                              f"{role_name} missing field: 职责/解读/结论")

    def test_daily_discussion_materialized(self):
        """daily_discussion has status == materialized."""
        roles = build_default()["role_interpretations"]
        dd = roles.get("daily_discussion", {})
        self.assertEqual(dd.get("status"), "materialized")

    def test_d07_interpretation_action_bias(self):
        """600114 should have action_bias=HOLD."""
        d07 = build_default()["d07_interpretation"]
        self.assertEqual(d07["action_bias"], "HOLD")

    def test_result_must_not_contain_buy_sell(self):
        """Should not produce BUY/SELL for daily report."""
        d07 = build_default()["d07_interpretation"]
        self.assertNotIn(d07["action_bias"], ("BUY", "SELL"))

    def test_data_fact_no_conclusion_words(self):
        """data_fact must not contain conclusion-tainted words."""
        d07 = build_default()["d07_interpretation"]
        df = d07.get("data_fact", {})
        text = json.dumps(df, ensure_ascii=False)
        banned = ["建议", "看好", "推荐", "买入", "卖出", "值得", "机会"]
        for word in banned:
            self.assertNotIn(word, text, f"data_fact contains banned word: {word}")

    def test_d07_passes_validator(self):
        """d07_interpretation must pass validate_interpretation.py --json (not BLOCK)."""
        result = build_default()
        d07_obj = result["d07_interpretation"]
        validator = ROOT / "统一解读" / "validate_interpretation.py"

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
            json.dump(d07_obj, tmp, ensure_ascii=False)
            tmp_path = Path(tmp.name)
        try:
            proc = subprocess.run(
                [sys.executable, str(validator), str(tmp_path), "--json"],
                cwd=str(ROOT), text=True, capture_output=True, timeout=60,
            )
            try:
                payload = json.loads(proc.stdout) if proc.stdout else {}
            except json.JSONDecodeError:
                payload = {"parse_error": proc.stdout, "stderr": proc.stderr}
            overall = payload.get("overall", "UNKNOWN")
            if overall == "BLOCK":
                schema_errs = payload.get("schema_validation", {}).get("errors", [])
                u9 = payload.get("u9", {})
                u10 = payload.get("u10", {})
                d07_checks = payload.get("d07_v12_checks", [])
                err_msg = f"Validator BLOCK. Schema: {schema_errs}. U9: {u9}. U10: {u10}. D07: {d07_checks}. Stderr: {proc.stderr[:200]}"
                self.fail(err_msg)
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_supporting_evidence_min_2(self):
        d07 = build_default()["d07_interpretation"]
        self.assertGreaterEqual(len(d07.get("supporting_evidence", [])), 2)

    def test_counter_evidence_min_1(self):
        d07 = build_default()["d07_interpretation"]
        self.assertGreaterEqual(len(d07.get("counter_evidence", [])), 1)

    def test_invalidation_condition_min_15(self):
        d07 = build_default()["d07_interpretation"]
        ic = d07.get("invalidation_condition", "")
        self.assertGreaterEqual(len(ic), 15)

    def test_rule_refs_in_d07_non_empty(self):
        d07 = build_default()["d07_interpretation"]
        self.assertTrue(len(d07.get("rule_refs", [])) >= 1)

    def test_knowledge_refs_in_d07_has_registered_ids(self):
        """d07_interpretation's knowledge_refs should reference registered IDs."""
        d07 = build_default()["d07_interpretation"]
        krefs = d07.get("knowledge_refs", [])
        self.assertTrue(len(krefs) > 0, "d07_interpretation knowledge_refs should not be empty")
        # Verify at least one is from the registered DAILY_KNOWLEDGE_REFS
        registry_path = ROOT / "统一解读" / "knowledge_registry.json"
        if registry_path.exists():
            reg_data = json.loads(registry_path.read_text(encoding="utf-8"))
            reg_ids = {e["knowledge_id"] for e in reg_data.get("entries", [])}
            for kid in krefs:
                self.assertIn(kid, reg_ids, f"knowledge_id {kid} not in registry")

    def test_hypotheses_have_structure(self):
        """Each hypothesis should have hypothesis_id, statement, status."""
        for h in build_default()["hypotheses"]:
            for f in ("hypothesis_id", "statement", "status"):
                self.assertIn(f, h, f"hypothesis missing {f}")


if __name__ == "__main__":
    unittest.main()
