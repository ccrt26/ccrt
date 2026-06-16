"""测试原子发布契约 — staging → final + run_id 一致性。"""
import json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from 代码文件.重点股票.product_eval.product_api_bundle import ProductApiBundleService


class TestAtomicPublishContract(unittest.TestCase):
    """原子发布契约测试。"""

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
        summary = self.svc.build_all(base, out, docs)
        return summary, docs, out

    def test_canonical_bundle_pointer_exists(self):
        """构建后 bundle_index.json (current pointer) 存在。"""
        with tempfile.TemporaryDirectory() as tmp:
            summary, docs, out = self._build(tmp)
            self.assertTrue(os.path.exists(os.path.join(docs, "bundle_index.json")))
            self.assertTrue(os.path.exists(os.path.join(docs, "run_manifest.json")))
            bi = json.load(open(os.path.join(docs, "bundle_index.json")))
            self.assertIn("run_id", bi)
            self.assertIn("current_bundle_path", bi)

    def test_final_files_exist_after_publish(self):
        """发布后 docs data 和 out 中文件存在。"""
        with tempfile.TemporaryDirectory() as tmp:
            summary, docs, out = self._build(tmp)
            for fname in ["bundle_index.json", "run_manifest.json", "stock_pool.json", "dashboard.json"]:
                self.assertTrue(os.path.exists(os.path.join(docs, fname)), f"docs {fname} 缺失")
                self.assertTrue(os.path.exists(os.path.join(out, fname)), f"out {fname} 缺失")

    def test_run_id_consistency_across_files(self):
        """所有顶层 JSON 的 run_id 与 bundle_index 一致。"""
        with tempfile.TemporaryDirectory() as tmp:
            summary, docs, out = self._build(tmp)
            bi = json.load(open(os.path.join(docs, "bundle_index.json")))
            bi_run_id = bi["run_id"]
            for fname in ["stock_pool.json", "dashboard.json", "stocks.json", "run_state.json"]:
                fpath = os.path.join(docs, fname)
                if os.path.exists(fpath):
                    data = json.load(open(fpath))
                    self.assertEqual(data.get("run_id"), bi_run_id,
                                     f"{fname} run_id 不一致")

    def test_per_stock_files_exist_after_publish(self):
        """stocks/600114/detail.json、chart_data.json、evidence.json 发布后存在。"""
        with tempfile.TemporaryDirectory() as tmp:
            summary, docs, out = self._build(tmp)
            for sf in ["detail.json", "chart_data.json", "evidence.json"]:
                path = os.path.join(docs, "stocks", "600114", sf)
                self.assertTrue(os.path.exists(path), f"docs stocks/600114/{sf} 缺失")
                path_out = os.path.join(out, "stocks", "600114", sf)
                self.assertTrue(os.path.exists(path_out), f"out stocks/600114/{sf} 缺失")

    def test_bundle_index_last_commit(self):
        """bundle_index.json 写入成功。"""
        with tempfile.TemporaryDirectory() as tmp:
            summary, docs, out = self._build(tmp)
            bi = json.load(open(os.path.join(docs, "bundle_index.json")))
            self.assertIn("files", bi)
            self.assertGreater(len(bi["files"]), 5)


if __name__ == "__main__":
    unittest.main()
