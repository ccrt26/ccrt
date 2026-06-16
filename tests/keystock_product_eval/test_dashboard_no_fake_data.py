"""验证驾驶舱无硬编码样例数据、无虚假业务结论"""
import json, os, sys, unittest, re

class TestDashboardNoFakeData(unittest.TestCase):
    """验证驾驶舱无硬编码假数据"""

    def setUp(self):
        self.data_dir = "docs/keystock-dashboard/data"
        self.js_path = "docs/keystock-dashboard/app.js"
        self.api_path = "代码文件/重点股票/product_eval/product_api_bundle.py"

    def test_stocks_no_600519_or_000858(self):
        """stocks.json 不得包含无证据股票 (600519/000858)。"""
        path = os.path.join(self.data_dir, "stocks.json")
        if os.path.exists(path):
            data = json.load(open(path, encoding="utf-8"))
            codes = {s.get("stock_code") for s in data.get("stocks", [])}
            bad = {"600519", "000858"} & codes
            self.assertFalse(bad, f"stocks.json 包含无真实证据股票: {bad}")

    def test_no_hardcoded_prices(self):
        """API bundle 不应包含 1800.0 或 145.0 等样例价格。"""
        if os.path.exists(self.api_path):
            src = open(self.api_path, encoding="utf-8").read()
            self.assertNotIn("1800.0", src, "product_api_bundle.py 包含样例价格 1800.0")
            self.assertNotIn("145.0", src, "product_api_bundle.py 包含样例价格 145.0")

    def test_no_hardcoded_decisions_in_js(self):
        """app.js 不应包含硬编码业务结论。"""
        if os.path.exists(self.js_path):
            js = open(self.js_path, encoding="utf-8").read()
            bad_patterns = ["建议持有/观察", "持有为主", "冲高回落", "chart-placeholder", "此处展示"]
            for pat in bad_patterns:
                self.assertNotIn(pat, js, f"app.js 包含硬编码: {pat}")

    def test_no_chart_placeholder_in_css(self):
        """app.css 不应包含 .chart-placeholder。"""
        css_path = "docs/keystock-dashboard/app.css"
        if os.path.exists(css_path):
            css = open(css_path, encoding="utf-8").read()
            self.assertNotIn(".chart-placeholder", css)

    def test_today_decisions_position_honest(self):
        """today_decisions.json 持仓应为 UNAVAILABLE（未接入真实持仓）。"""
        path = os.path.join(self.data_dir, "today_decisions.json")
        if os.path.exists(path):
            dec = json.load(open(path, encoding="utf-8"))
            pos = dec.get("user_position", {})
            self.assertFalse(pos.get("has_position", True), "持仓应显示未接入")
            self.assertIsNone(pos.get("cost_price"), "cost_price 应显示不可用")

    def test_primary_action_degraded(self):
        """数据缺失/规则WARN/持仓缺失时 primary_action=observe, confidence<=0.3。"""
        path = os.path.join(self.data_dir, "today_decisions.json")
        if os.path.exists(path):
            dec = json.load(open(path, encoding="utf-8"))
            action = dec.get("primary_action", "")
            self.assertEqual(action, "observe",
                             f"当前条件下降级动作应为 observe，实际 {action}")
            self.assertLessEqual(dec.get("confidence", 1.0), 0.3,
                                 "confidence 应 <= 0.3")
            blockers = dec.get("decision_blockers", [])
            self.assertIn("POSITION_UNAVAILABLE", blockers,
                          "decision_blockers 应包含 POSITION_UNAVAILABLE")

    def test_chart_data_has_real_ohlc(self):
        """chart_data.json 必须包含真实 K 线数据 (>20 行)。"""
        path = os.path.join(self.data_dir, "chart_data.json")
        if os.path.exists(path):
            chart = json.load(open(path, encoding="utf-8"))
            ohlc = chart.get("ohlc", [])
            self.assertGreater(len(ohlc), 20, f"K 线数据不足 (仅 {len(ohlc)} 行)")

if __name__ == "__main__":
    unittest.main()
