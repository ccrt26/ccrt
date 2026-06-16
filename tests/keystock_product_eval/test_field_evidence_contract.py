"""Session3 v3: field_evidence 最终契约测试。"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from 代码文件.重点股票.product_eval.product_api_bundle import ProductApiBundleService


REQUIRED_FIELD_EVIDENCE = {
    "dashboard.json": [
        "overall_status", "conclusion_status", "as_of_date", "blocks", "warnings",
        "status_gate.data_status", "status_gate.decision_blockers",
        "status_gate.status_gate_source_refs",
    ],
    "stock_pool.json": [
        "members.600114.stock_code", "members.600114.stock_name",
        "members.600114.status", "members.600114.data_status",
        "members.600114.evidence_status",
    ],
    "stocks.json": [
        "stocks.600114.stock_code", "stocks.600114.stock_name",
        "stocks.600114.close", "stocks.600114.change_pct",
        "stocks.600114.actual_trade_date", "stocks.600114.data_freshness_status",
        "stocks.600114.conclusion_status", "stocks.600114.user_visible_status",
    ],
    "today_decisions.json": [
        "trade_date", "conclusion_status", "user_visible_status",
        "user_position.position_status", "market_today.close", "market_today.ma5",
        "market_today.ma20", "rule_health_status", "decision_blockers",
        "primary_action", "confidence",
    ],
    "chart_data.json": [
        "stock_code", "source_last_date", "feature_snapshot_actual_date",
        "data_date_divergence", "ohlc", "ma5", "ma20", "ma60",
    ],
    "evidence_index.json": ["evidence_items"],
    "stocks/600114/detail.json": [
        "stock_code", "stock_name", "market_today.close", "market_today.ma5",
        "market_today.ma20", "status_gate.data_status",
        "status_gate.decision_blockers", "rule_health_summary.overall_status",
        "position_public_view.position_status", "evidence_summary",
        "decision_blockers",
    ],
    "stocks/600114/chart_data.json": [
        "stock_code", "source_last_date", "feature_snapshot_actual_date",
        "data_date_divergence", "ohlc", "ma5", "ma20", "ma60",
    ],
    "stocks/600114/evidence.json": ["evidence_items"],
}


class TestFieldEvidenceContract(unittest.TestCase):
    def _build(self, tmp):
        base = os.path.join(tmp, "base")
        out = os.path.join(tmp, "out")
        docs = os.path.join(tmp, "docs")
        for d in ["inventory", "backtests", "feature_snapshots", "status"]:
            os.makedirs(os.path.join(base, d), exist_ok=True)
        with open(os.path.join(base, "inventory", "keystock_system_inventory.json"), "w") as f:
            json.dump({"daily_report_sidecars": {"count": 10}}, f)
        ProductApiBundleService().build_all(base, out, docs)
        return docs

    def test_required_field_evidence_exists_and_is_referential(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs = self._build(tmp)
            ev = json.load(open(os.path.join(docs, "stocks", "600114", "evidence.json")))
            evidence_ids = {item["evidence_id"] for item in ev["evidence_items"]}

            for rel_path, keys in REQUIRED_FIELD_EVIDENCE.items():
                data = json.load(open(os.path.join(docs, rel_path)))
                field_evidence = data.get("field_evidence", {})
                for key in keys:
                    self.assertIn(key, field_evidence, f"{rel_path} missing {key}")
                    entry = field_evidence[key]
                    self.assertTrue(entry.get("evidence_refs"), f"{rel_path}:{key} no evidence_refs")
                    self.assertTrue(entry.get("source_refs"), f"{rel_path}:{key} no source_refs")
                    for evidence_ref in entry["evidence_refs"]:
                        self.assertIn(evidence_ref, evidence_ids, f"{rel_path}:{key} bad evidence_ref")

    def test_business_values_are_not_wrapped(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs = self._build(tmp)
            chart = json.load(open(os.path.join(docs, "chart_data.json")))
            decisions = json.load(open(os.path.join(docs, "today_decisions.json")))
            stocks = json.load(open(os.path.join(docs, "stocks.json")))

            self.assertIsInstance(chart.get("ohlc"), list)
            self.assertNotIsInstance(decisions.get("market_today", {}).get("close"), dict)
            self.assertNotIsInstance(stocks["stocks"][0].get("close"), dict)

    def test_field_paths_do_not_use_array_indexes(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs = self._build(tmp)
            for rel_path in REQUIRED_FIELD_EVIDENCE:
                data = json.load(open(os.path.join(docs, rel_path)))
                for key in data.get("field_evidence", {}):
                    self.assertNotIn("[0]", key)


if __name__ == "__main__":
    unittest.main()
