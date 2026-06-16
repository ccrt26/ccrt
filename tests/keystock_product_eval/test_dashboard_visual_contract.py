"""验证驾驶舱 UI 结构和视觉契约（会话四增强）"""
import os, unittest, re


class TestDashboardVisualContract(unittest.TestCase):
    """驾驶舱 UI 结构验证"""

    def setUp(self):
        self.html_path = "docs/keystock-dashboard/index.html"

    def test_html_exists(self):
        self.assertTrue(os.path.exists(self.html_path))

    def test_has_sidebar_structure(self):
        """应有侧边导航 (sidebar class)。"""
        html = open(self.html_path, encoding="utf-8").read()
        self.assertIn("sidebar", html, "缺少 sidebar 导航结构")

    def test_has_app_shell(self):
        """应有 app-shell 容器。"""
        html = open(self.html_path, encoding="utf-8").read()
        self.assertIn("app-shell", html)

    def test_has_five_views(self):
        """应有 5 个视图容器。"""
        html = open(self.html_path, encoding="utf-8").read()
        for vid in ["view-dashboard", "view-stocks", "view-deep", "view-daily", "view-rules"]:
            self.assertIn(vid, html, f"视图 {vid} 缺失")

    def test_has_detail_bundle_evidence_containers(self):
        """HTML 必须包含详情、状态闸门、证据、bundle状态、图表容器。"""
        html = open(self.html_path, encoding="utf-8").read()
        for cid in ["view-detail", "bundle-status", "status-gate",
                    "block-reasons", "position-public", "chart-area", "evidence"]:
            self.assertIn(cid, html, f"HTML 缺少容器: {cid}")

    def test_has_css_js_links(self):
        """应有 app.css 和 app.js 引用。"""
        html = open(self.html_path, encoding="utf-8").read()
        self.assertIn("app.css", html)
        self.assertIn("app.js", html)
        self.assertNotIn("CDN", html, "不应引用外部 CDN")
        self.assertNotIn("https://", html, "不应联网")

    def test_has_sidebar_nav(self):
        """必须有侧边导航。"""
        html = open(self.html_path, encoding="utf-8").read()
        sidebar_nav = bool(re.search(r'sidebar.*a.*data-view', html, re.DOTALL))
        self.assertTrue(sidebar_nav, "页面必须使用侧边导航")

    def test_checker_not_unconditional_pass(self):
        """checker 不得无条件返回 visual_contract_status: PASS。"""
        checker_path = "scripts/check_keystock_dashboard_productization.py"
        if os.path.exists(checker_path):
            src = open(checker_path, encoding="utf-8").read()
            self.assertNotIn('"visual_contract_status": "PASS"', src,
                             "visual_contract_status 不得写死 PASS")

    def test_css_no_placeholder(self):
        """CSS 不应包含占位符样式。"""
        css_path = "docs/keystock-dashboard/app.css"
        if os.path.exists(css_path):
            css = open(css_path, encoding="utf-8").read()
            self.assertNotIn("chart-placeholder", css, "CSS 包含 chart-placeholder")

    def test_css_overflow_wrap(self):
        """CSS 应包含 overflow-wrap 或 word-break 以支持长路径。"""
        css_path = "docs/keystock-dashboard/app.css"
        if os.path.exists(css_path):
            css = open(css_path, encoding="utf-8").read()
            self.assertTrue("overflow-wrap" in css or "word-break" in css,
                            "CSS 应包含 overflow-wrap 或 word-break 换行支持")

    def test_css_mobile_media_query(self):
        """CSS 应包含移动端 media query。"""
        css_path = "docs/keystock-dashboard/app.css"
        if os.path.exists(css_path):
            css = open(css_path, encoding="utf-8").read()
            self.assertIn("@media", css, "CSS 应包含媒体查询")
            self.assertIn("max-width", css, "CSS 应包含 max-width 媒体查询")

    def test_status_code_styles_present(self):
        """CSS 应包含 FORMAL/OBSERVATION/SHADOW/BLOCKED 样式。"""
        css_path = "docs/keystock-dashboard/app.css"
        if os.path.exists(css_path):
            css = open(css_path, encoding="utf-8").read()
            for s in ["formal", "observation", "shadow", "blocked",
                      "data-stale", "date-divergence", "rule-warn", "position-unavailable"]:
                self.assertIn(s, css, f"CSS 缺少状态样式: {s}")


if __name__ == "__main__":
    unittest.main()
