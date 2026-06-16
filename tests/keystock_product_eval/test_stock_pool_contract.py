"""ProductStockPoolService 契约测试。"""
import json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from 代码文件.重点股票.product_eval.stock_pool import ProductStockPoolService
from 代码文件.重点股票.product_eval.product_api_bundle import ProductApiBundleService


class TestStockPoolContract(unittest.TestCase):
    """产品股票池契约测试。"""

    def setUp(self):
        self.svc = ProductStockPoolService()

    def test_pool_members_length_one(self):
        """stock_pool members 长度为 1。"""
        pool = self.svc.build_pool()
        self.assertEqual(len(pool["members"]), 1)

    def test_unique_member_stock_code_600114(self):
        """唯一成员 stock_code 为 600114。"""
        pool = self.svc.build_pool()
        self.assertEqual(pool["members"][0]["stock_code"], "600114")

    def test_unique_member_stock_name_dongmu(self):
        """唯一成员 stock_name 为 东睦股份。"""
        pool = self.svc.build_pool()
        self.assertEqual(pool["members"][0]["stock_name"], "东睦股份")

    def test_member_status_active(self):
        """唯一成员 status 为 active。"""
        pool = self.svc.build_pool()
        self.assertEqual(pool["members"][0]["status"], "active")

    def test_pool_has_schema_version(self):
        """schema_version 存在。"""
        pool = self.svc.build_pool()
        self.assertTrue(pool.get("schema_version"))

    def test_pool_has_pool_version(self):
        """pool_version 存在。"""
        pool = self.svc.build_pool()
        self.assertTrue(pool.get("pool_version"))

    def test_active_members_no_sample_stocks(self):
        """active members 不包含 600519、000858 等样例股票。"""
        active = self.svc.get_active_members()
        codes = {m["stock_code"] for m in active}
        self.assertNotIn("600519", codes)
        self.assertNotIn("000858", codes)

    def test_validate_pool_contract_passes(self):
        """validate_pool_contract 对合法 pool 返回空列表。"""
        pool = self.svc.build_pool()
        errors = self.svc.validate_pool_contract(pool)
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
