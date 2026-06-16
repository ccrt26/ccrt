"""stock_pool.json schema 版本契约测试与 legacy 兼容性（session3 增强版）。"""
import json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from 代码文件.重点股票.product_eval.stock_pool import ProductStockPoolService
from 代码文件.重点股票.product_eval.product_api_bundle import (
    ProductApiBundleService, SCHEMA_VERSION, BUNDLE_VERSION,
)


class TestSchemaVersionContract(unittest.TestCase):
    """stock_pool.json 结构契约（session3 增强）。"""

    def setUp(self):
        self.svc = ProductStockPoolService()
        self.bundle_svc = ProductApiBundleService()

    def _build(self, tmp):
        base = os.path.join(tmp, "base")
        out = os.path.join(tmp, "out")
        docs = os.path.join(tmp, "docs")
        os.makedirs(base)
        for d in ["inventory", "backtests", "feature_snapshots", "status"]:
            os.makedirs(os.path.join(base, d))
        with open(os.path.join(base, "inventory", "keystock_system_inventory.json"), "w") as f:
            json.dump({"daily_report_sidecars": {"count": 10}}, f)
        return self.bundle_svc.build_all(base, out, docs), docs

    def test_top_level_schema_version(self):
        """stock_pool.json 顶层包含 schema_version。"""
        pool = self.svc.build_pool()
        self.assertIn("schema_version", pool)

    def test_top_level_pool_version(self):
        """stock_pool.json 顶层包含 pool_version。"""
        pool = self.svc.build_pool()
        self.assertIn("pool_version", pool)

    def test_members_is_array(self):
        """members 为数组。"""
        pool = self.svc.build_pool()
        self.assertIsInstance(pool["members"], list)

    def test_member_required_fields(self):
        """每个 member 至少包含 stock_code、stock_name、status、display_order、source_refs。"""
        pool = self.svc.build_pool()
        required = {"stock_code", "stock_name", "status", "display_order", "source_refs"}
        for m in pool["members"]:
            self.assertTrue(required.issubset(m.keys()),
                            f"member {m.get('stock_code')} missing: {required - m.keys()}")

    def test_bundle_output_includes_stock_pool(self):
        """ProductApiBundleService 输出 stock_pool.json。"""
        with tempfile.TemporaryDirectory() as tmp:
            _, docs = self._build(tmp)
            pool_path = os.path.join(docs, "stock_pool.json")
            self.assertTrue(os.path.exists(pool_path), "stock_pool.json 应存在")
            pool = json.load(open(pool_path, encoding="utf-8"))
            self.assertIn("schema_version", pool)
            self.assertIn("pool_version", pool)
            self.assertIn("members", pool)
            self.assertEqual(len(pool["members"]), 1)

    def test_legacy_outputs_still_exist(self):
        """legacy 兼容输出不因新增 bundle 文件破坏。"""
        with tempfile.TemporaryDirectory() as tmp:
            _, docs = self._build(tmp)
            for fname in ["stocks.json", "dashboard.json", "today_decisions.json", "chart_data.json"]:
                self.assertTrue(os.path.exists(os.path.join(docs, fname)),
                                f"legacy {fname} 应仍存在")

    # ──── session3 增强 ────

    def test_all_top_level_json_have_schema_version(self):
        """所有顶层 JSON 包含 schema_version。"""
        with tempfile.TemporaryDirectory() as tmp:
            _, docs = self._build(tmp)
            for fname in ["stock_pool.json", "dashboard.json", "stocks.json", "run_state.json",
                          "today_decisions.json", "chart_data.json", "bundle_index.json", "run_manifest.json"]:
                fpath = os.path.join(docs, fname)
                if os.path.exists(fpath):
                    data = json.load(open(fpath))
                    self.assertIn("schema_version", data, f"{fname} 缺少 schema_version")

    def test_all_top_level_json_have_bundle_version(self):
        """所有顶层 JSON 包含 bundle_version。"""
        with tempfile.TemporaryDirectory() as tmp:
            _, docs = self._build(tmp)
            for fname in ["stock_pool.json", "dashboard.json", "stocks.json", "run_state.json",
                          "today_decisions.json", "chart_data.json", "bundle_index.json", "run_manifest.json"]:
                fpath = os.path.join(docs, fname)
                if os.path.exists(fpath):
                    data = json.load(open(fpath))
                    self.assertIn("bundle_version", data, f"{fname} 缺少 bundle_version")

    def test_all_top_level_json_have_run_id(self):
        """所有顶层 JSON 包含 run_id。"""
        with tempfile.TemporaryDirectory() as tmp:
            _, docs = self._build(tmp)
            for fname in ["stock_pool.json", "dashboard.json", "stocks.json", "run_state.json",
                          "today_decisions.json", "chart_data.json", "bundle_index.json", "run_manifest.json"]:
                fpath = os.path.join(docs, fname)
                if os.path.exists(fpath):
                    data = json.load(open(fpath))
                    self.assertIn("run_id", data, f"{fname} 缺少 run_id")

    def test_legacy_files_have_legacy_compat(self):
        """legacy 文件含 legacy_compat=true。"""
        with tempfile.TemporaryDirectory() as tmp:
            _, docs = self._build(tmp)
            for fname in ["today_decisions.json", "chart_data.json", "evidence_index.json"]:
                fpath = os.path.join(docs, fname)
                if os.path.exists(fpath):
                    data = json.load(open(fpath))
                    self.assertTrue(data.get("legacy_compat"), f"{fname} 缺少 legacy_compat=true")


if __name__ == "__main__":
    unittest.main()
