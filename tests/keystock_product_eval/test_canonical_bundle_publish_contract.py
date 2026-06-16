"""Session3 v3: canonical bundle 发布契约测试。"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from 代码文件.重点股票.product_eval.product_api_bundle import ProductApiBundleService


class TestCanonicalBundlePublishContract(unittest.TestCase):
    def _build_and_publish(self, tmp):
        base = os.path.join(tmp, "base")
        out = os.path.join(tmp, "out")
        docs = os.path.join(tmp, "docs")
        for d in ["inventory", "backtests", "feature_snapshots", "status"]:
            os.makedirs(os.path.join(base, d), exist_ok=True)
        with open(os.path.join(base, "inventory", "keystock_system_inventory.json"), "w") as f:
            json.dump({"daily_report_sidecars": {"count": 10}}, f)

        svc = ProductApiBundleService()
        summary = svc.build_all(base, out, docs)
        run_id = summary["run_id"]
        svc.atomic_publish(
            summary["staging_docs_dir"], summary["staging_out_dir"], docs, out, run_id,
            svc.pool_svc.get_active_members(),
            {"warning_reasons": [], "blocking_reasons": [], "decision_blockers": []},
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
        )
        return docs, run_id

    def test_current_pointer_and_canonical_bundle_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs, run_id = self._build_and_publish(tmp)
            bi = json.load(open(os.path.join(docs, "bundle_index.json")))
            self.assertEqual(bi["current_bundle_path"], f"bundles/{run_id}/")
            self.assertTrue(os.path.isdir(os.path.join(docs, "bundles", run_id)))

    def test_canonical_top_level_run_ids_are_consistent(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs, run_id = self._build_and_publish(tmp)
            canonical = os.path.join(docs, "bundles", run_id)
            for fname in ["bundle_index.json", "run_manifest.json", "stock_pool.json",
                          "stocks.json", "dashboard.json", "today_decisions.json",
                          "chart_data.json", "evidence_index.json"]:
                data = json.load(open(os.path.join(canonical, fname)))
                self.assertEqual(data.get("run_id"), run_id, fname)

    def test_legacy_files_point_to_canonical(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs, run_id = self._build_and_publish(tmp)
            for fname in ["today_decisions.json", "chart_data.json", "evidence_index.json"]:
                data = json.load(open(os.path.join(docs, fname)))
                self.assertTrue(data.get("legacy_compat"), fname)
                self.assertEqual(data.get("run_id"), run_id, fname)
                self.assertEqual(data.get("canonical_path"), f"bundles/{run_id}/{fname}")


if __name__ == "__main__":
    unittest.main()
