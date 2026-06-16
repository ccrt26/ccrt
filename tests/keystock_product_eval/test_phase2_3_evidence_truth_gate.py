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
        """修复 G5 证据文件不应包含无条件 true 字段（须基于检查结果）。
        原始旧证据保留为历史审计痕迹，由 repair evidence 的 supersedes 覆盖。"""
        for fname in os.listdir(self.ev_dir):
            if "g5_review" in fname and fname.startswith("phase2_3") and "repair" in fname:
                for bad_pat in self.fake_true_patterns:
                    text = open(os.path.join(self.ev_dir, fname), encoding="utf-8").read()
                    matches = re.findall(bad_pat, text)
                    if matches:
                        self.fail(f"{fname} 包含无条件 true: {matches}")

    def test_g6_archive_not_pre_written_complete(self):
        """修复 G6 archive 不能直接写死 COMPLETE（旧证据保留为历史审计痕迹）。"""
        ev_files = [f for f in os.listdir(self.ev_dir) if f.endswith("g6_archive.json") and f.startswith("phase2_3") and "repair" in f]
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
        """修复 G4 证据应包含 fake_data_hits 检查结果（旧证据保留为历史审计痕迹）。"""
        candidates = [f for f in os.listdir(self.ev_dir) if f.endswith("_candidate.json")]
        candidates = [f for f in candidates if f.startswith("phase2_3") and "repair" in f]
        for fname in candidates:
            data = json.load(open(os.path.join(self.ev_dir, fname), encoding="utf-8"))
            has_fake = "fake_data_hits" in data
            has_checker = "checker_result" in data
            has_findings = "findings" in data
            self.assertTrue(has_fake or has_checker or has_findings,
                            f"{fname} 应包含 fake_data_hits 或 checker_result 或 findings")

    def test_g5_status_block_classified_as_block(self):
        """G5 candidate 必须按 status 字段分类 BLOCK，而不是 severity。"""
        src = open("scripts/build_keystock_product_api_bundle.py", encoding="utf-8").read()
        self.assertIn('f.get("status") == "BLOCK"', src,
                      "G5 分类必须使用 status 字段")
        self.assertNotIn('f.get("severity") == "BLOCK"', src,
                         "G5 分类不应使用 severity 字段")

    def test_original_phase23_evidence_files_preserved(self):
        """旧 Phase2/3 G4/G5/G6 证据必须保留，由 repair evidence supersedes。"""
        required = [
            "phase2_3_productization_g4_self_check_candidate.json",
            "phase2_3_productization_g5_review_candidate.json",
            "phase2_3_productization_g6_archive.json",
        ]
        for fname in required:
            path = os.path.join(self.ev_dir, fname)
            self.assertTrue(os.path.exists(path), f"旧证据缺失: {fname}")


if __name__ == "__main__":
    unittest.main()
