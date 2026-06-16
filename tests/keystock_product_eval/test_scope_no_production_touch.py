"""
生产不触碰范围测试。

验证 product_eval 包不会修改以下生产目录：
  1. 重点股票/股票报告/**
  2. 重点股票/深度分析/**
  3. 00_项目地基/02_权威注册表/baseline_registry.json
  4. 00_项目地基/06_调度与运行/runtime_entry_registry.json
"""

import os
import sys
import unittest
import importlib
import inspect

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

# 导入所有 product_eval 模块
PRODUCTION_PATHS = [
    "重点股票/股票报告",
    "重点股票/深度分析",
    "00_项目地基/02_权威注册表/baseline_registry.json",
    "00_项目地基/06_调度与运行/runtime_entry_registry.json",
]

MODULES = [
    "代码文件.重点股票.product_eval.inventory",
    "代码文件.重点股票.product_eval.prediction_ledger",
    "代码文件.重点股票.product_eval.feature_service",
    "代码文件.重点股票.product_eval.backtest_engine",
    "代码文件.重点股票.product_eval.forward_eval",
    "代码文件.重点股票.product_eval.status_exporter",
]


class TestScopeNoProductionTouch(unittest.TestCase):
    """范围：不触碰生产文件。"""

    def test_production_paths_not_written(self):
        """检查代码中是否包含生产路径写入。"""
        for mod_name in MODULES:
            mod = importlib.import_module(mod_name)
            source = inspect.getsource(mod)
            for prod_path in PRODUCTION_PATHS:
                prod_name = prod_path.rstrip(".json").split("/")[-1]
                for line in source.split("\n"):
                    line_stripped = line.strip()
                    # 只检查写入操作
                    if prod_path in line_stripped and "write" in line_stripped.lower():
                        self.fail(
                            f"{mod_name} 中检测到写入生产路径 '{prod_path}':\n"
                            f"  {line_stripped}"
                        )
                    # 检查 open 写模式
                    if prod_path in line_stripped and ("'w'" in line_stripped or '"w"' in line_stripped):
                        self.fail(
                            f"{mod_name} 中检测到写入生产路径 '{prod_path}':\n"
                            f"  {line_stripped}"
                        )

    def test_inventory_only_reads_no_write(self):
        """inventory.py 只读不写生产文件。

        允许引用生产路径作为扫描/读取参数（如 scan_daily_report_sidecars 的默认参数），
        但不得写入生产路径。"""
        mod = importlib.import_module(MODULES[0])
        source = inspect.getsource(mod)
        for line in source.split("\n"):
            ls = line.strip()
            for prod_path in PRODUCTION_PATHS:
                # 必须在同一行出现生产路径和写入操作才触发
                if prod_path in ls:
                    if "'w'" in ls or '"w"' in ls:  # open 写模式
                        # 排除 JSONL 追加写（非生产目录）
                        if "jsonl" not in ls:
                            self.fail(f"inventory.py 写入生产路径 {prod_path}: {ls}")
                    if 'os.makedirs' in ls and prod_path in ls:
                        self.fail(f"inventory.py 写入生产路径 {prod_path}: {ls}")

    def test_no_production_path_in_init(self):
        """__init__.py 中 PRODUCTION_PATHS 定义正确。"""
        import 代码文件.重点股票.product_eval  # noqa: E402
        self.assertTrue(hasattr(代码文件.重点股票.product_eval, "PRODUCTION_PATHS"))
        for p in PRODUCTION_PATHS:
            self.assertIn(p, 代码文件.重点股票.product_eval.PRODUCTION_PATHS)

    def test_scripts_not_in_production_dir(self):
        """测试脚本不位于生产目录内。"""
        test_dir = os.path.dirname(__file__)
        self.assertNotIn("重点股票/股票报告", test_dir)
        self.assertNotIn("重点股票/深度分析", test_dir)


if __name__ == "__main__":
    unittest.main()
