"""验证驾驶舱 UI 结构和视觉契约"""
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

    def test_has_css_js_links(self):
        """应有 app.css 和 app.js 引用。"""
        html = open(self.html_path, encoding="utf-8").read()
        self.assertIn("app.css", html)
        self.assertIn("app.js", html)
        self.assertNotIn("CDN", html, "不应引用外部 CDN")
        self.assertNotIn("https://", html, "不应联网")

    def test_no_topbar_nav_only(self):
        """不应只有顶部导航（应使用侧边导航）。"""
        html = open(self.html_path, encoding="utf-8").read()
        top_nav = bool(re.search(r'header.*nav.*a.*data-view', html, re.DOTALL))
        sidebar_nav = bool(re.search(r'sidebar.*a.*data-view', html, re.DOTALL))
        if not sidebar_nav:
            self.fail("页面缺少侧边导航")

    def test_css_no_placeholder(self):
        """CSS 不应包含占位符样式。"""
        css_path = "docs/keystock-dashboard/app.css"
        if os.path.exists(css_path):
            css = open(css_path, encoding="utf-8").read()
            self.assertNotIn("chart-placeholder", css, "CSS 包含 chart-placeholder")

if __name__ == "__main__":
    unittest.main()
