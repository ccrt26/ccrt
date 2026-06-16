"""
ForwardEval 到期扫描测试。

验证：
  1. placeholder assertion → OBSERVE
  2. attribution.primary == prediction_assertion_placeholder
  3. 无旧错误文案
  4. feature_snapshot_id 非空
  5. 账本状态更新正确
  6. future_function BLOCK → outcome BLOCK
"""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from 代码文件.重点股票.product_eval.prediction_ledger import PredictionLedger  # noqa: E402
from 代码文件.重点股票.product_eval.forward_eval import ForwardEval  # noqa: E402


# 禁止出现的旧文案
BANNED_WORDS = ["特征服务占位", "实际行情数据未接入",
                "无行情数据接口", "无行情数据回填"]


class TestForwardEvalDueScan(unittest.TestCase):
    """ForwardEval 到期扫描测试"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.ledger = PredictionLedger(self.temp_dir)
        self._insert_placeholder_records()

    def _insert_placeholder_records(self):
        self.ledger.insert({
            "stock_code": "600114",
            "stock_name": "东睦股份",
            "trade_date": "20260101",
            "source_type": "daily_report",
            "baseline_id": "BL-20260101-600114",
            "prediction_type": "directional",
            "assertion": "Phase 1 占位记录 — 600114 20260101",
            "horizon": 5,
            "confidence": 0.5,
            "verification_windows": [{"label": "T+5", "offset_days": 5}],
        })

    def test_001_placeholder_assertion_returns_observe(self):
        """placeholder assertion → OBSERVE。"""
        evaluator = ForwardEval(self.ledger)
        results = evaluator.scan_due_predictions(as_of_date="20261201")
        self.assertGreater(len(results), 0)
        for r in results:
            if r.get("assertion", "").startswith("Phase 1 占位记录"):
                self.assertEqual(r["outcome"], "OBSERVE",
                                 f"占位 assertion 必须 OBSERVE，得到 {r['outcome']}")

    def test_002_attribution_is_placeholder(self):
        """占位 assertion 的 attribution.primary 为 prediction_assertion_placeholder。"""
        evaluator = ForwardEval(self.ledger)
        results = evaluator.scan_due_predictions(as_of_date="20261201")
        for r in results:
            if r.get("assertion", "").startswith("Phase 1 占位记录"):
                self.assertEqual(
                    r.get("attribution", {}).get("primary"),
                    "prediction_assertion_placeholder",
                )

    def test_003_no_banned_wording(self):
        """结果中不得出现旧错误文案。"""
        evaluator = ForwardEval(self.ledger)
        results = evaluator.scan_due_predictions(as_of_date="20261201")
        text = json.dumps(results, ensure_ascii=False)
        for word in BANNED_WORDS:
            self.assertNotIn(word, text,
                             f"结果中不应出现旧文案: {word}")

    def test_004_feature_snapshot_id_not_empty(self):
        """feature_snapshot_id 非空。"""
        evaluator = ForwardEval(self.ledger)
        results = evaluator.scan_due_predictions(as_of_date="20261201")
        for r in results:
            self.assertTrue(r.get("feature_snapshot_id"),
                            "feature_snapshot_id 必须非空")

    def test_005_actual_metrics_fields_exist(self):
        """actual_metrics 字段存在。"""
        evaluator = ForwardEval(self.ledger)
        results = evaluator.scan_due_predictions(as_of_date="20261201")
        for r in results:
            metrics = r.get("actual_metrics", {})
            self.assertIn("actual_return", metrics)
            self.assertIn("max_drawdown", metrics)
            self.assertIn("relative_return", metrics)

    def test_006_ledger_status_updated(self):
        """评估后账本状态更新。"""
        record = self.ledger.insert({
            "stock_code": "600114",
            "stock_name": "东睦股份",
            "trade_date": "20260101",
            "source_type": "daily_report",
            "baseline_id": "BL-20260101-600114",
            "prediction_type": "directional",
            "assertion": "Phase 1 占位记录 — 状态更新测试",
            "horizon": 5,
            "confidence": 0.5,
            "verification_windows": [{"label": "T+5", "offset_days": 5}],
        })
        ledger_id = record["ledger_id"]

        evaluator = ForwardEval(self.ledger)
        evaluator.scan_due_predictions(as_of_date="20261201")

        updated = self.ledger.get_by_id(ledger_id)
        self.assertIsNotNone(updated)
        self.assertNotEqual(updated["status"], "PENDING",
                            "评估后账本状态应更新")

    def test_007_does_not_delete_history(self):
        """不删除历史账本。"""
        count_before = self.ledger.count()
        evaluator = ForwardEval(self.ledger)
        evaluator.scan_due_predictions(as_of_date="20261201")
        count_after = self.ledger.count()
        self.assertEqual(count_before, count_after)

    def test_008_future_function_block_mock_outcome(self):
        """mock future_function BLOCK → outcome BLOCK。"""
        with patch.object(
            self.ledger, "find_due",
            return_value=[{
                "ledger_id": "TEST-FF-BLOCK",
                "stock_code": "600114",
                "stock_name": "东睦股份",
                "trade_date": "20260101",
                "source_type": "daily_report",
                "baseline_id": "BL-601114",
                "prediction_type": "directional",
                "assertion": "测试未来函数 BLOCK",
                "horizon": 5,
                "confidence": 0.5,
            }],
        ):
            with patch(
                "代码文件.重点股票.product_eval.forward_eval.FeatureSnapshotService.get_features"
            ) as mock_fs:
                mock_fs.return_value = {
                    "snapshot_id": "FS-MOCK-BLOCK",
                    "future_function_check": {
                        "passed": False,
                        "max_data_date": "20260620",
                        "as_of_check": "BLOCK",
                        "details": "mock BLOCK",
                    },
                    "feature_values": {},
                    "label_values": {},
                }
                evaluator = ForwardEval(self.ledger)
                results = evaluator.scan_due_predictions(as_of_date="20261201")
                for r in results:
                    self.assertEqual(r["outcome"], "BLOCK",
                                     "future_function BLOCK mock 应输出 BLOCK")
                    self.assertEqual(
                        r.get("attribution", {}).get("primary"),
                        "future_function_risk",
                    )


class TestForwardEvalCLIFixtureIfEmpty(unittest.TestCase):
    """CLI --fixture-if-empty 空账本兜底路径测试。

    验证：
      - 空 ledger 回退默认 fixture
      - fixture_only 标记正确
      - 正式 ledger 不被污染
    """

    def test_cli_fixture_if_empty_uses_default_fixture_without_polluting_formal_ledger(self):
        import subprocess
        from pathlib import Path

        project_root = Path(__file__).resolve().parents[2]
        fixture_path = (project_root /
                        "运行产物/重点股票产品化后评估/forward_eval/fixtures/placeholder_due_ledger.jsonl")
        self.assertTrue(fixture_path.exists(), "默认 fixture ledger 必须存在")

        with tempfile.TemporaryDirectory() as ledger_dir, tempfile.TemporaryDirectory() as out_dir:
            cmd = [
                sys.executable,
                str(project_root / "scripts/run_forward_eval_scan.py"),
                "--as-of-date", "20260616",
                "--ledger-dir", ledger_dir,
                "--out-dir", out_dir,
                "--fixture-if-empty",
            ]
            proc = subprocess.run(
                cmd, cwd=str(project_root), text=True, capture_output=True, check=False,
            )

            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
            self.assertIn("回退 fixture ledger", proc.stdout)
            self.assertIn("fixture=1", proc.stdout)

            out_path = Path(out_dir) / "forward_eval_20260616.json"
            self.assertTrue(out_path.exists(), "fixture-if-empty 应生成 forward_eval 输出")

            results = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].get("outcome"), "OBSERVE")
            self.assertTrue(
                results[0].get("fixture_only") or results[0].get("source_fixture_ref"),
                "fixture 输出必须携带 fixture 标记",
            )

            formal_ledger_path = Path(ledger_dir) / "prediction_ledger.jsonl"
            if formal_ledger_path.exists():
                content = formal_ledger_path.read_text(encoding="utf-8").strip()
                self.assertEqual(content, "",
                                 "fixture fallback 不得污染传入的空正式 ledger")


if __name__ == "__main__":
    unittest.main()
