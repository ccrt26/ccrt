"""ProductApiBundle 测试 — 验证真实数据驱动、无样例股票"""
import json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from 代码文件.重点股票.product_eval.product_api_bundle import ProductApiBundleService

class TestProductApiBundle(unittest.TestCase):
    def setUp(self):
        self.svc = ProductApiBundleService("/tmp")

    def test_build_all_stocks_only_real_evidence(self):
        """stocks.json 仅包含 600114。"""
        with tempfile.TemporaryDirectory() as tmp:
            base = os.path.join(tmp, "base")
            out = os.path.join(tmp, "out")
            docs = os.path.join(tmp, "docs")
            os.makedirs(base)
            os.makedirs(os.path.join(base, "inventory"))
            os.makedirs(os.path.join(base, "backtests"))
            os.makedirs(os.path.join(base, "feature_snapshots"))
            os.makedirs(os.path.join(base, "status"))
            with open(os.path.join(base, "inventory", "keystock_system_inventory.json"), "w") as f:
                json.dump({"daily_report_sidecars": {"count": 10}}, f)
            with open(os.path.join(base, "backtests", "backtest_TECH_MA20_BREAK_STOP_LOSS_600114_20260616.json"), "w") as f:
                json.dump({"stock_code":"600114","stock_name":"东睦股份","as_of_date":"20260616","overall_status":"WARN","windows":{}}, f)
            summary = self.svc.build_all(base, out, docs)
            stocks = json.load(open(os.path.join(docs, "stocks.json"), encoding="utf-8"))
            codes = {s.get("stock_code") for s in stocks.get("stocks", [])}
            self.assertNotIn("600519", codes, "无证据股票不得出现")
            self.assertNotIn("000858", codes, "无证据股票不得出现")
            self.assertIn("600114", codes, "600114 应有证据链")
            self.assertIn("files", summary)

    def test_build_all_has_chart_data(self):
        """chart_data.json 应包含 K 线。"""
        with tempfile.TemporaryDirectory() as tmp:
            base = os.path.join(tmp, "base")
            out = os.path.join(tmp, "out")
            docs = os.path.join(tmp, "docs")
            os.makedirs(base)
            for d in ["inventory","backtests","feature_snapshots","status"]:
                os.makedirs(os.path.join(base, d))
            with open(os.path.join(base,"inventory","keystock_system_inventory.json"),"w") as f: json.dump({"daily_report_sidecars":{"count":10}},f)
            self.svc.build_all(base, out, docs)
            chart = json.load(open(os.path.join(docs,"chart_data.json"), encoding="utf-8"))
            self.assertIn("ohlc", chart)
            self.assertIn("ma5", chart)
            self.assertIn("ma20", chart)
            self.assertIn("source_path", chart)

if __name__ == "__main__":
    unittest.main()
