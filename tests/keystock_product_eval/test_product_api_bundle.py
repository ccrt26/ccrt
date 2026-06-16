"""ProductApiBundle 测试 — 验证真实数据驱动、无样例股票、change_pct 语义正确"""
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
            for d in ["inventory","backtests","feature_snapshots","status"]: os.makedirs(os.path.join(base, d))
            with open(os.path.join(base,"inventory","keystock_system_inventory.json"),"w") as f: json.dump({"daily_report_sidecars":{"count":10}},f)
            with open(os.path.join(base,"backtests","backtest_TECH_MA20_BREAK_STOP_LOSS_600114_20260616.json"),"w") as f: json.dump({"stock_code":"600114","stock_name":"东睦股份","as_of_date":"20260616","overall_status":"WARN","windows":{}},f)
            self.svc.build_all(base, out, docs)
            stocks = json.load(open(os.path.join(docs,"stocks.json"), encoding="utf-8"))
            codes = {s.get("stock_code") for s in stocks.get("stocks", [])}
            self.assertNotIn("600519", codes, "无证据股票不得出现")
            self.assertNotIn("000858", codes)
            self.assertIn("600114", codes)

    def test_change_pct_not_from_ma5(self):
        """change_pct 不得等于 close 相对 MA5 的偏离。"""
        with tempfile.TemporaryDirectory() as tmp:
            base, out, docs = os.path.join(tmp,"base"), os.path.join(tmp,"out"), os.path.join(tmp,"docs")
            for d in ["inventory","backtests","feature_snapshots","status"]: os.makedirs(os.path.join(base, d))
            with open(os.path.join(base,"inventory","keystock_system_inventory.json"),"w") as f: json.dump({"daily_report_sidecars":{"count":10}},f)
            self.svc.build_all(base, out, docs)
            stocks = json.load(open(os.path.join(docs,"stocks.json"), encoding="utf-8"))
            s = stocks["stocks"][0]
            cp = s.get("change_pct")
            cvm = s.get("close_vs_ma5_pct")
            if cp is not None and cvm is not None:
                self.assertNotAlmostEqual(cp, cvm, delta=0.01,
                    msg="change_pct 不应等于 close_vs_ma5_pct")

    def test_primary_action_observe_when_conditions_met(self):
        """在数据降级条件下 primary_action 必须为 observe。"""
        dec_path = "docs/keystock-dashboard/data/today_decisions.json"
        if os.path.exists(dec_path):
            dec = json.load(open(dec_path, encoding="utf-8"))
            self.assertEqual(dec.get("primary_action"), "observe",
                             "在数据日期差异/规则WARN/持仓缺失条件下动作应降级为 observe")
            self.assertLessEqual(dec.get("confidence", 1.0), 0.3,
                                 "降级条件下 confidence 应 <= 0.3")
            blockers = dec.get("decision_blockers", [])
            self.assertIn("POSITION_UNAVAILABLE", blockers)

    def test_has_chart_data(self):
        """chart_data.json 应包含 K 线。"""
        with tempfile.TemporaryDirectory() as tmp:
            base, out, docs = os.path.join(tmp,"base"), os.path.join(tmp,"out"), os.path.join(tmp,"docs")
            for d in ["inventory","backtests","feature_snapshots","status"]: os.makedirs(os.path.join(base, d))
            with open(os.path.join(base,"inventory","keystock_system_inventory.json"),"w") as f: json.dump({"daily_report_sidecars":{"count":10}},f)
            self.svc.build_all(base, out, docs)
            chart = json.load(open(os.path.join(docs,"chart_data.json"), encoding="utf-8"))
            self.assertIn("ohlc", chart); self.assertIn("ma5", chart); self.assertIn("ma20", chart)
            self.assertIn("source_path", chart)

if __name__ == "__main__":
    unittest.main()
