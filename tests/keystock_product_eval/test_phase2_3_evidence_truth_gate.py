"""验证 Phase 2/3 evidence 文件不包含无条件 true/COMPLETE"""
import json, os, unittest, re

class TestPhase23EvidenceTruthGate(unittest.TestCase):
    """G5/G6 证据文件真实性门禁测试"""

    def setUp(self):
        self.ev_dir = "运行产物/重点股票产品化后评估/evidence"
        self.fake_true_patterns = [
            r'"ui_design_adhered"\s*:\s*true',
            r'"production_entry_not_modified"\s*:\s*true\b',
            r'"all_frontend_data_from_api_bundle"\s*:\s*true\b',
            r'"dry_run_reset_supported"\s*:\s*true\b',
            r'"step8_goals_met"\s*:\s*true\b',
        ]

    def test_g5_evidence_not_unconditional_true(self):
        """G5 证据文件不应包含无条件 true 字段（须基于检查结果）。"""
        for fname in os.listdir(self.ev_dir):
            if "g5_review" in fname and fname.startswith("phase2_3"):
                for bad_pat in self.fake_true_patterns:
                    text = open(os.path.join(self.ev_dir, fname), encoding="utf-8").read()
                    matches = re.findall(bad_pat, text)
                    if matches:
                        self.fail(f"{fname} 包含无条件 true: {matches}")

    def test_g6_archive_not_pre_written_complete(self):
        """G6 archive 不能直接写死 COMPLETE。"""
        ev_files = [f for f in os.listdir(self.ev_dir) if f.endswith("g6_archive.json") and f.startswith("phase2_3")]
        for fname in ev_files:
            data = json.load(open(os.path.join(self.ev_dir, fname), encoding="utf-8"))
            archive = data.get("archive_status", "")
            if archive == "COMPLETE" and not data.get("checker_overall") and not data.get("checker_result"):
                self.fail(f"{fname}: COMPLETE 但无 checker_overall/checker_result 证据")

    def test_repair_g6_has_supersedes(self):
        """修复版 G6 archive 应包含 supersedes 旧文件。"""
        repair = os.path.join(self.ev_dir, "phase2_3_productization_repair_g6_archive.json")
        if os.path.exists(repair):
            data = json.load(open(repair, encoding="utf-8"))
            self.assertIn("supersedes", data,
                          "修复版 G6 必须声明 supersedes 旧文件")

    def test_g6_block_if_block_status(self):
        """G6 archive 若 block_status=true 则 archive_status 应为 BLOCK。"""
        for fname in os.listdir(self.ev_dir):
            if "g6_archive" in fname and fname.startswith("phase2_3"):
                data = json.load(open(os.path.join(self.ev_dir, fname), encoding="utf-8"))
                if data.get("block_status") and data.get("archive_status") == "COMPLETE":
                    self.fail(f"{fname}: block_status=true 但 archive_status=COMPLETE")

    def test_g6_checker_not_pass_cannot_complete(self):
        """checker overall != PASS 时 archive 不能 COMPLETE。"""
        for fname in os.listdir(self.ev_dir):
            if "g6_archive" in fname and fname.startswith("phase2_3"):
                data = json.load(open(os.path.join(self.ev_dir, fname), encoding="utf-8"))
                checker = data.get("checker_overall", data.get("checker_result", {}).get("overall", ""))
                if data.get("archive_status") == "COMPLETE":
                    if checker not in ("PASS", ""):
                        self.fail(f"{fname}: checker_overall={checker} 但 archive_status=COMPLETE")

    def test_g4_evidence_has_fake_data_hits(self):
        """G4 证据应包含 fake_data_hits 检查结果。"""
        candidates = [f for f in os.listdir(self.ev_dir) if f.endswith("_candidate.json") or f.endswith("_candidate.json")]
        candidates = [f for f in candidates if f.startswith("phase2_3")]
        for fname in candidates:
            data = json.load(open(os.path.join(self.ev_dir, fname), encoding="utf-8"))
            has_fake = "fake_data_hits" in data
            has_checker = "checker_result" in data
            has_findings = "findings" in data
            self.assertTrue(has_fake or has_checker or has_findings,
                            f"{fname} 应包含 fake_data_hits 或 checker_result 或 findings")

if __name__ == "__main__":
    unittest.main()
