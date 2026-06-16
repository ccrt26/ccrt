"""EvidenceTraceIndex 测试"""
import json, os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from 代码文件.重点股票.product_eval.evidence_trace_index import EvidenceTraceIndexService

class TestEvidenceTraceIndex(unittest.TestCase):
    def setUp(self):
        self.svc = EvidenceTraceIndexService("/tmp")
    def test_build_default(self):
        r = self.svc.build_evidence_index("600114", "东睦股份", "20260616")
        self.assertEqual(r["stock_code"], "600114")
        self.assertIn("decision_id", r)
        self.assertGreater(len(r["evidence_items"]), 0)
    def test_derive_from_missing_backtest(self):
        r = self.svc.derive_from_backtest("/nonexistent.json")
        self.assertIsNone(r)

if __name__ == "__main__":
    unittest.main()
