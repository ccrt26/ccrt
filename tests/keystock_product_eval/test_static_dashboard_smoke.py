"""前端静态驾驶舱冒烟测试"""
import os, sys, unittest

class TestStaticDashboardSmoke(unittest.TestCase):
    def test_index_exists(self):
        self.assertTrue(os.path.exists("docs/keystock-dashboard/index.html"))
    def test_css_exists(self):
        self.assertTrue(os.path.exists("docs/keystock-dashboard/app.css"))
    def test_js_exists(self):
        self.assertTrue(os.path.exists("docs/keystock-dashboard/app.js"))
    def test_data_dir_exists(self):
        self.assertTrue(os.path.isdir("docs/keystock-dashboard/data/"))
    def test_html_has_views(self):
        with open("docs/keystock-dashboard/index.html") as f:
            html = f.read()
        for vid in ["view-dashboard", "view-stocks", "view-detail", "view-deep", "view-daily", "view-rules"]:
            self.assertIn(vid, html, f"视图 {vid} 在 HTML 中缺失")

if __name__ == "__main__":
    unittest.main()
