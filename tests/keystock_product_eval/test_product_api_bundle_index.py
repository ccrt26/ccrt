"""测试 bundle_index.json 结构契约。"""
import json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from 代码文件.重点股票.product_eval.product_api_bundle import (
    ProductApiBundleService, SCHEMA_VERSION, BUNDLE_VERSION,
)


class TestProductApiBundleIndex(unittest.TestCase):
    """bundle_index 契约测试。"""

    def setUp(self):
        self.svc = ProductApiBundleService()

    def _build(self, tmp):
        base = os.path.join(tmp, "base")
        out = os.path.join(tmp, "out")
        docs = os.path.join(tmp, "docs")
        os.makedirs(base)
        for d in ["inventory", "backtests", "feature_snapshots", "status"]:
            os.makedirs(os.path.join(base, d))
        with open(os.path.join(base, "inventory", "keystock_system_inventory.json"), "w") as f:
            json.dump({"daily_report_sidecars": {"count": 10}}, f)
        return self.svc.build_all(base, out, docs), docs

    def test_bundle_index_exists(self):
        """bundle_index.json 存在。"""
        with tempfile.TemporaryDirectory() as tmp:
            _, docs = self._build(tmp)
            self.assertTrue(os.path.exists(os.path.join(docs, "bundle_index.json")))

    def test_bundle_index_lists_required_files(self):
        """bundle_index 列出全部 required 文件。"""
        with tempfile.TemporaryDirectory() as tmp:
            _, docs = self._build(tmp)
            bi = json.load(open(os.path.join(docs, "bundle_index.json")))
            required_paths = {f["path"] for f in bi.get("files", []) if f.get("required")}
            self.assertIn("stock_pool.json", required_paths)
            self.assertIn("dashboard.json", required_paths)
            self.assertIn("stocks.json", required_paths)
            self.assertIn("run_state.json", required_paths)

    def test_required_files_exist(self):
        """bundle_index 中标记 required 的文件真实存在。"""
        with tempfile.TemporaryDirectory() as tmp:
            _, docs = self._build(tmp)
            bi = json.load(open(os.path.join(docs, "bundle_index.json")))
            for f_entry in bi.get("files", []):
                if f_entry.get("required"):
                    fpath = os.path.join(docs, f_entry["path"])
                    self.assertTrue(os.path.exists(fpath), f"required 文件缺失: {f_entry['path']}")

    def test_bundle_index_has_run_id(self):
        """bundle_index 包含 run_id。"""
        with tempfile.TemporaryDirectory() as tmp:
            _, docs = self._build(tmp)
            bi = json.load(open(os.path.join(docs, "bundle_index.json")))
            self.assertTrue(bi.get("run_id"))

    def test_bundle_index_has_schema_version(self):
        """bundle_index 包含 schema_version。"""
        with tempfile.TemporaryDirectory() as tmp:
            _, docs = self._build(tmp)
            bi = json.load(open(os.path.join(docs, "bundle_index.json")))
            self.assertEqual(bi.get("schema_version"), SCHEMA_VERSION)

    def test_bundle_index_stock_code_from_pool(self):
        """stock_code 来源于 stock_pool。"""
        with tempfile.TemporaryDirectory() as tmp:
            _, docs = self._build(tmp)
            bi = json.load(open(os.path.join(docs, "bundle_index.json")))
            stock_files = [f for f in bi.get("files", []) if f.get("stock_code")]
            for f in stock_files:
                self.assertEqual(f["stock_code"], "600114")

    def test_per_stock_files_listed(self):
        """stocks/600114/ 下的三个文件被列出。"""
        with tempfile.TemporaryDirectory() as tmp:
            _, docs = self._build(tmp)
            bi = json.load(open(os.path.join(docs, "bundle_index.json")))
            paths = {f["path"] for f in bi.get("files", [])}
            for sf in ["stocks/600114/detail.json", "stocks/600114/chart_data.json", "stocks/600114/evidence.json"]:
                self.assertIn(sf, paths, f"bundle_index 缺少 {sf}")


if __name__ == "__main__":
    unittest.main()
