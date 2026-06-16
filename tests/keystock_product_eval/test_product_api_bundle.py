"""ProductApiBundle 测试"""
import json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from 代码文件.重点股票.product_eval.product_api_bundle import ProductApiBundleService

class TestProductApiBundle(unittest.TestCase):
    def setUp(self):
        self.svc = ProductApiBundleService("/tmp")
    def test_build_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = os.path.join(tmp, "base")
            out = os.path.join(tmp, "out")
            docs = os.path.join(tmp, "docs")
            os.makedirs(base)
            os.makedirs(os.path.join(base, "inventory"))
            os.makedirs(os.path.join(base, "backtests"))
            os.makedirs(os.path.join(base, "feature_snapshots"))
            # stub inventory
            with open(os.path.join(base, "inventory", "keystock_system_inventory.json"), "w") as f:
                json.dump({"daily_report_sidecars": {"count": 10}}, f)
            # stub backtest
            with open(os.path.join(base, "backtests", "backtest_TECH_MA20_BREAK_STOP_LOSS_600114_20260616.json"), "w") as f:
                json.dump({"stock_code": "600114", "stock_name": "东睦股份", "as_of_date": "20260616", "overall_status": "WARN", "windows": {}}, f)
            summary = self.svc.build_all(base, out, docs)
            self.assertIn("files", summary)
            for fname in ["dashboard.json", "stocks.json", "run_state.json", "evidence_index.json"]:
                self.assertTrue(os.path.exists(os.path.join(out, fname)), f"{fname} missing")

if __name__ == "__main__":
    unittest.main()
