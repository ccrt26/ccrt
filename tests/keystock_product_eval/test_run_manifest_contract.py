"""测试 run_manifest.json 契约。"""
import json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from 代码文件.重点股票.product_eval.product_api_bundle import ProductApiBundleService


class TestRunManifestContract(unittest.TestCase):
    """run_manifest 契约测试。"""

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

    def test_run_manifest_exists(self):
        """run_manifest.json 存在。"""
        with tempfile.TemporaryDirectory() as tmp:
            _, docs = self._build(tmp)
            self.assertTrue(os.path.exists(os.path.join(docs, "run_manifest.json")))

    def test_run_manifest_has_run_id(self):
        """run_manifest 有 run_id。"""
        with tempfile.TemporaryDirectory() as tmp:
            _, docs = self._build(tmp)
            rm = json.load(open(os.path.join(docs, "run_manifest.json")))
            self.assertTrue(rm.get("run_id"))

    def test_run_manifest_has_publish_status(self):
        """run_manifest 有 publish_status。"""
        with tempfile.TemporaryDirectory() as tmp:
            _, docs = self._build(tmp)
            rm = json.load(open(os.path.join(docs, "run_manifest.json")))
            self.assertIn(rm.get("publish_status"), ("PUBLISHED", "PENDING", "FAILED", "STAGED"))

    def test_run_manifest_has_generated_files(self):
        """run_manifest 有 generated_files。"""
        with tempfile.TemporaryDirectory() as tmp:
            _, docs = self._build(tmp)
            rm = json.load(open(os.path.join(docs, "run_manifest.json")))
            self.assertIsInstance(rm.get("generated_files"), list)
            self.assertGreater(len(rm["generated_files"]), 0)

    def test_run_manifest_has_input_refs(self):
        """run_manifest 有 input_refs。"""
        with tempfile.TemporaryDirectory() as tmp:
            _, docs = self._build(tmp)
            rm = json.load(open(os.path.join(docs, "run_manifest.json")))
            self.assertIn("input_refs", rm)

    def test_run_manifest_has_no_production_touch(self):
        """run_manifest 有 no_production_touch 字段。"""
        with tempfile.TemporaryDirectory() as tmp:
            _, docs = self._build(tmp)
            rm = json.load(open(os.path.join(docs, "run_manifest.json")))
            npt = rm.get("no_production_touch", {})
            self.assertIn("baseline_registry_touched", npt)
            self.assertIn("runtime_entry_registry_touched", npt)
            self.assertIn("launchd_touched", npt)
            self.assertIn("real_position_connected", npt)

    def test_run_manifest_has_rollback_ref(self):
        """run_manifest 有 rollback_ref。"""
        with tempfile.TemporaryDirectory() as tmp:
            _, docs = self._build(tmp)
            rm = json.load(open(os.path.join(docs, "run_manifest.json")))
            self.assertTrue(rm.get("rollback_ref"))


if __name__ == "__main__":
    unittest.main()
