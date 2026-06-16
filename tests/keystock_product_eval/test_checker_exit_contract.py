"""Session3 v3: checker 退出码绑定 engineering_status。"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from 代码文件.重点股票.product_eval.product_api_bundle import ProductApiBundleService


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CHECKER = os.path.join(ROOT, "scripts", "check_keystock_dashboard_productization.py")


class TestCheckerExitContract(unittest.TestCase):
    def _docs_with_bundle(self, tmp):
        docs_root = os.path.join(tmp, "keystock-dashboard")
        data_dir = os.path.join(docs_root, "data")
        os.makedirs(data_dir, exist_ok=True)
        with open(os.path.join(docs_root, "index.html"), "w") as f:
            f.write("<div class='sidebar'></div><div id='view-dashboard'></div><div id='view-stocks'></div><div id='view-deep'></div><div id='view-daily'></div><div id='view-rules'></div>")
        open(os.path.join(docs_root, "app.css"), "w").close()
        open(os.path.join(docs_root, "app.js"), "w").close()

        base = os.path.join(tmp, "base")
        out = os.path.join(tmp, "out")
        for d in ["inventory", "backtests", "feature_snapshots", "status"]:
            os.makedirs(os.path.join(base, d), exist_ok=True)
        with open(os.path.join(base, "inventory", "keystock_system_inventory.json"), "w") as f:
            json.dump({"daily_report_sidecars": {"count": 10}}, f)

        svc = ProductApiBundleService()
        summary = svc.build_all(base, out, data_dir)
        svc.atomic_publish(
            summary["staging_docs_dir"], summary["staging_out_dir"], data_dir, out,
            summary["run_id"], svc.pool_svc.get_active_members(),
            {"warning_reasons": [], "blocking_reasons": [], "decision_blockers": []},
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
        )
        return docs_root, data_dir

    def _run_checker(self, docs_root, data_dir):
        return subprocess.run(
            [sys.executable, CHECKER, "--docs-dir", docs_root, "--data-dir", data_dir],
            cwd=ROOT, capture_output=True, text=True,
        )

    def test_business_block_exits_zero_when_engineering_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs_root, data_dir = self._docs_with_bundle(tmp)
            result = self._run_checker(docs_root, data_dir)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["engineering_status"], "PASS")
            self.assertEqual(payload["business_user_visible_status"], "BLOCK")
            self.assertEqual(result.returncode, 0)

    def test_run_id_mismatch_exits_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs_root, data_dir = self._docs_with_bundle(tmp)
            path = os.path.join(data_dir, "stocks.json")
            data = json.load(open(path))
            data["run_id"] = "bad-run-id"
            json.dump(data, open(path, "w"), ensure_ascii=False, indent=2)
            result = self._run_checker(docs_root, data_dir)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["engineering_status"], "BLOCK")
            self.assertEqual(result.returncode, 1)

    def test_missing_field_evidence_exits_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs_root, data_dir = self._docs_with_bundle(tmp)
            path = os.path.join(data_dir, "today_decisions.json")
            data = json.load(open(path))
            del data["field_evidence"]["market_today.close"]
            json.dump(data, open(path, "w"), ensure_ascii=False, indent=2)
            result = self._run_checker(docs_root, data_dir)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["engineering_status"], "BLOCK")
            self.assertEqual(result.returncode, 1)


if __name__ == "__main__":
    unittest.main()
