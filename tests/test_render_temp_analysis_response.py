#!/usr/bin/env python3
"""Tests for temporary-analysis front response renderer."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from render_temp_analysis_response import render_response, load_json


BRIEF = load_json(ROOT / "临时分析/sidecar/temporary_analysis_trial_brief_600114_20260616_demo.json")


class TestRenderTemporaryAnalysisResponse(unittest.TestCase):
    def test_render_hides_backend_process_terms(self):
        text = render_response(BRIEF, "现在能不能追")
        self.assertIn("一句话判断", text)
        self.assertIn("操作计划", text)
        self.assertIn("针对你的问题", text)
        self.assertNotIn("数据质量确认", text)
        self.assertNotIn("方法审查", text)
        self.assertNotIn("非目标确认", text)
        self.assertNotIn("假设链", text)

    def test_render_has_enough_counter_points_and_plan_items(self):
        text = render_response(BRIEF, "破位怎么办")
        counter_block = text.split("4. 哪些情况说明判断可能错了", 1)[1].split("5. 操作计划", 1)[0]
        plan_block = text.split("5. 操作计划", 1)[1].split("6. 针对你的问题", 1)[0]
        self.assertGreaterEqual(counter_block.count("- "), 4)
        self.assertGreaterEqual(plan_block.count("- "), 5)

    def test_question_about_chasing_gets_direct_answer(self):
        text = render_response(BRIEF, "现在能不能追")
        self.assertIn("不建议追", text)

    def test_cli_writes_rendered_output(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "rendered.txt"
            proc = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/render_temp_analysis_response.py"),
                    "--brief",
                    str(ROOT / "临时分析/sidecar/temporary_analysis_trial_brief_600114_20260616_demo.json"),
                    "--question",
                    "现在能不能追",
                    "--output",
                    str(out)
                ],
                cwd=str(ROOT),
                text=True,
                capture_output=True
            )
            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["status"], "PASS")
            self.assertTrue(out.exists())
            self.assertIn("临时分析｜东睦股份 600114", out.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
