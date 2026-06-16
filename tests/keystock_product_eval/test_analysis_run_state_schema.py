"""AnalysisRunState schema 测试"""
import json, os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from 代码文件.重点股票.product_eval.analysis_run_state import AnalysisRunStateService

class TestAnalysisRunState(unittest.TestCase):
    def setUp(self):
        self.svc = AnalysisRunStateService("/tmp")
    def test_build_default(self):
        r = self.svc.build_run_state("600114", "东睦股份", "20260616")
        self.assertEqual(r["stock_code"], "600114")
        self.assertIn("run_id", r)
        self.assertIn("run_status", r)
    def test_derive_from_missing_inventory(self):
        r = self.svc.derive_from_inventory("600114", "20260616")
        self.assertEqual(r["run_status"], "WARN")

if __name__ == "__main__":
    unittest.main()
