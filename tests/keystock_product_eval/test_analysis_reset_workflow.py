"""AnalysisResetWorkflow 测试"""
import json, os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from 代码文件.重点股票.product_eval.analysis_reset_workflow import AnalysisResetWorkflowService

class TestAnalysisResetWorkflow(unittest.TestCase):
    def setUp(self):
        self.svc = AnalysisResetWorkflowService("/tmp")
    def test_dry_run_default(self):
        r = self.svc.execute_dry_run("600114", "东睦股份", "20260616")
        self.assertTrue(r["dry_run"])
        self.assertEqual(r["workflow_status"], "DRY_RUN")
        self.assertGreater(len(r["steps"]), 0)
    def test_dry_run_no_history_deletion(self):
        r = self.svc.create_reset_request("600114", "东睦股份", "20260616", dry_run=True)
        for step in r["steps"]:
            self.assertNotEqual(step["step_name"], "删除历史证据")

if __name__ == "__main__":
    unittest.main()
