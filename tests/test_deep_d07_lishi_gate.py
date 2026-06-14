#!/usr/bin/env python3
"""深度分析 D07+砺石 硬闸门单元测试"""
import json, os, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from check_deep_d07_lishi_gate import check_report, scan_date

class TestDeepD07LishiGate(unittest.TestCase):

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def _write(self, name, text):
        p = self.tmpdir / name
        p.write_text(text, encoding="utf-8")
        return p

    # ==============================
    # 1. 缺 D07 → BLOCK
    # ==============================
    def test_missing_d07_blocks(self):
        text = """# 深度分析报告
> 报告日期: 2026-06-12
无D07内容。无砺石。纯文本。
"""
        p = self._write("report.md", text)
        overall, findings = check_report(p)
        self.assertEqual(overall, "BLOCK")
        d07_blocks = [f for f in findings if "D07" in f["check"] and f["result"] == "BLOCK"]
        self.assertTrue(len(d07_blocks) > 0, f"应因缺D07而BLOCK, 实际={findings}")

    # ==============================
    # 2. 有 D07 但缺砺石 → BLOCK
    # ==============================
    def test_missing_lishi_blocks(self):
        text = """# 深度分析报告
> 方法论版本: v1.5 + D07_v1.2 full_release

## hypotheses
假设1: 测试

## 反证条件
反证1

## 证据缺口
GAP-001

## 结论强度
风险假设

## 长期机构资金
not_applicable

## 失效条件
若跌破则

## U-9
OK
"""
        p = self._write("report2.md", text)
        overall, findings = check_report(p)
        self.assertEqual(overall, "BLOCK")
        lishi_blocks = [f for f in findings if "砺石" in f["check"] and f["result"] == "BLOCK"]
        self.assertTrue(len(lishi_blocks) > 0, f"应因缺砺石而BLOCK, 实际={findings}")

    # ==============================
    # 3. 砺石段落含 BUY/买入 → BLOCK
    # ==============================
    def test_lishi_buy_sell_blocks(self):
        text = """# 深度分析报告
> D07_v1.2 full_release

## hypotheses
假设

## method_review
砺石审查总结：
推理链完整（D1通过）
数据可靠（D2通过）
逻辑一致（D3通过）
反证充分（D4通过）
集体推理无分歧（D5通过）
建议买入该股票。
"""
        p = self._write("report3.md", text)
        overall, findings = check_report(p)
        self.assertEqual(overall, "BLOCK")
        buy_blocks = [f for f in findings if "越界" in f["check"] and f["result"] == "BLOCK"]
        self.assertTrue(len(buy_blocks) > 0, f"砺石含买入应BLOCK, 实际={findings}")

    # ==============================
    # 4. 空扫描 → BLOCK
    # ==============================
    def test_empty_scan_blocks(self):
        results = scan_date("20990101")
        self.assertEqual(len(results), 0, f"空扫描应有0结果, 实际={results}")

    # ==============================
    # 5. 缺 U-9 → BLOCK
    # ==============================
    def test_missing_u9_blocks(self):
        text = """# 深度分析
> framework_version: D07_v1.2
## hypotheses H1
## 反证条件 C1
## 证据缺口 G1
## 结论强度 风险假设
## 长期机构资金 not_applicable
## 失效条件 F1
## U-10 PASS
## method_review
砺石。推理链（D1）数据（D2）逻辑（D3）反证（D4）集体（D5）
"""
        p = self._write("miss_u9.md", text)
        overall, findings = check_report(p)
        self.assertEqual(overall, "BLOCK", f"缺U-9应BLOCK, {findings}")

    # ==============================
    # 6. 缺 U-10 → BLOCK
    # ==============================
    def test_missing_u10_blocks(self):
        text = """# 深度分析
> framework_version: D07_v1.2
## hypotheses H1
## 反证条件 C1
## 证据缺口 G1
## 结论强度 风险假设
## 长期机构资金 not_applicable
## 失效条件 F1
## U-9 PASS
## method_review
砺石。推理链（D1）数据（D2）逻辑（D3）反证（D4）集体（D5）
"""
        p = self._write("miss_u10.md", text)
        overall, findings = check_report(p)
        self.assertEqual(overall, "BLOCK", f"缺U-10应BLOCK, {findings}")

    # ==============================
    # 7. 最小完整样例（含U-9+U-10）→ PASS
    # ==============================
    def test_complete_minimal_passes(self):
        text = """# 600114 深度分析
> framework_version: D07_v1.2 | D07_v1.2 full_release

## hypotheses
H1: 测试假设（active）
H2: 反向假设

## 反证条件
CE-001: 测试反证

## 证据缺口
GAP-001: 待补数据

## 结论强度
风险假设

## 长期机构资金
not_applicable

## 失效条件
若跌破则

## U-9
PASS

## U-10
PASS

## method_review
砺石方法审查：
推理链完整性（D1）：推理链完整，假设→结论无跳跃
数据引用可靠性（D2）：数据源均已标注，时效性合理
逻辑一致性（D3）：报告内部一致，无矛盾
反证充分性（D4）：反证充分，无确认偏误
集体推理质量（D5）：各角色推理链关联一致
"""
        p = self._write("report_pass.md", text)
        overall, findings = check_report(p)
        if overall != "PASS":
            details = [f"{f['check']}={f['result']}:{f['detail'][:60]}" for f in findings]
            self.fail(f"完整样例应PASS, 实际={overall}, {details}")


if __name__ == "__main__":
    unittest.main()
