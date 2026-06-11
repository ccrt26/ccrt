#!/usr/bin/env python3
"""validate_cases.py — 15 个测试用例验证 v3.7.2.1

读取 tests/cases/*.json，用 position_cost.py 计算，
与 tests/expected/*.json 的预期输出逐字段对比。

支持三种期望类型:
  - status=BLOCK → 验证 valid=False + reason 匹配
  - status=WARN  → 验证 valid=True + warnings 匹配 + result 正确
  - 默认 (PASS)  → 验证 valid=True + result 字段匹配

预期输出: CASES: 15 PASS / 0 FAIL / 15 TOTAL
"""

import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, os.pardir))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from position_cost import calculate

CASES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests", "cases")
EXPECTED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests", "expected")


def run_all_cases():
    passed = 0
    failed = 0
    details = []

    if not os.path.isdir(CASES_DIR):
        print(f"[ERROR] 测试用例目录不存在: {CASES_DIR}")
        return 0, 0, [("SYSTEM", "测试用例目录不存在")]

    case_files = sorted(f for f in os.listdir(CASES_DIR) if f.endswith(".json"))
    if not case_files:
        print("[ERROR] 未找到测试用例")
        return 0, 0, [("SYSTEM", "未找到测试用例")]

    for cf in case_files:
        case_path = os.path.join(CASES_DIR, cf)
        expected_path = os.path.join(EXPECTED_DIR, cf.replace(".json", ".expected.json"))

        try:
            with open(case_path, encoding="utf-8") as f:
                case_data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            failed += 1
            details.append((cf, f"用例读取失败: {e}"))
            continue

        try:
            with open(expected_path, encoding="utf-8") as f:
                expected = json.load(f)
        except (json.JSONDecodeError, IOError):
            failed += 1
            details.append((cf, "期望输出读取失败"))
            continue

        input_data = case_data.get("input", case_data)
        result = calculate(input_data)
        exp_v = expected.get("validation", {})
        exp_status = exp_v.get("status", "")

        # ── BLOCK 校验 ──────────────────────────────────────────────
        if exp_status == "BLOCK":
            if result["validation"]["valid"] is not False:
                failed += 1
                details.append((cf, f"应 BLOCK 但实际 valid=True: {result}"))
                continue
            exp_reason = exp_v["block_reason"]
            act_reason = result["validation"]["reason"] or ""
            if exp_reason not in act_reason:
                failed += 1
                details.append((cf, f"BLOCK 原因不匹配: 期望'{exp_reason}', 实际'{act_reason}'"))
                continue
            # 校验 do_not_generate_operation_card
            if "do_not_generate_operation_card" in exp_v:
                exp_dng = exp_v["do_not_generate_operation_card"]
                act_dng = result["validation"].get("do_not_generate_operation_card")
                if act_dng != exp_dng:
                    failed += 1
                    details.append((cf, f"do_not_generate_operation_card 不匹配: 期望{exp_dng}, 实际{act_dng}"))
                    continue
            passed += 1
            details.append((cf, f"PASS (BLOCK正确: {act_reason})"))
            continue

        # ── WARN 校验 ───────────────────────────────────────────────
        if exp_status == "WARN":
            if result["validation"]["valid"] is not True:
                failed += 1
                details.append((cf, f"WARN 但 valid=False: {result['validation']['reason']}"))
                continue
            if result["validation"]["status"] != "WARN":
                failed += 1
                details.append((cf, f"期望 WARN 但 status={result['validation']['status']}"))
                continue
            # 检查 expected warnings
            exp_warnings = exp_v.get("warnings", [])
            act_warnings = result["validation"].get("warnings", [])
            for w in exp_warnings:
                if w not in act_warnings:
                    failed += 1
                    details.append((cf, f"缺期望警告 '{w}'，实际 {act_warnings}"))
                    continue
            # WARN 仍应执行计算，验证 result
            calc = result["result"]
            exp_calc = expected.get("result", {})
            if calc is None:
                failed += 1
                details.append((cf, "WARN 状态下 result 不应为 None"))
                continue
            mismatches = []
            for key in ["cost_after", "position_after_quantity", "realized_pnl"]:
                if key in exp_calc and exp_calc[key] is not None:
                    act_val = calc.get(key)
                    exp_val = exp_calc[key]
                    tol = 0.02 if key == "cost_after" else 0.01
                    if abs((act_val or 0) - exp_val) > tol:
                        mismatches.append(f"{key}: 期望{exp_val}, 实际{act_val}")
                elif key in exp_calc and exp_calc[key] is None:
                    if calc.get(key) is not None:
                        mismatches.append(f"{key}: 期望null, 实际{calc[key]}")
            if mismatches:
                failed += 1
                details.append((cf, f"WARN 结果不匹配: {'; '.join(mismatches)}"))
                continue
            # 校验 do_not_generate_operation_card
            if "do_not_generate_operation_card" in exp_v:
                exp_dng = exp_v["do_not_generate_operation_card"]
                act_dng = result["validation"].get("do_not_generate_operation_card")
                if act_dng != exp_dng:
                    failed += 1
                    details.append((cf, f"do_not_generate_operation_card 不匹配: 期望{exp_dng}, 实际{act_dng}"))
                    continue
            passed += 1
            details.append((cf, f"PASS (WARN正确: {act_warnings})"))
            continue

        # ── PASS / 正常计算校验 ─────────────────────────────────────
        if result["validation"]["valid"] is not True:
            failed += 1
            details.append((cf, f"计算失败但预期通过: {result['validation']['reason']}"))
            continue

        calc = result["result"]
        exp_calc = expected.get("result", expected)
        if "result" in expected:
            exp_calc = expected["result"]

        mismatches = []
        for key in ["cost_after", "position_after_quantity", "realized_pnl"]:
            if key in exp_calc and exp_calc[key] is not None:
                act_val = calc.get(key)
                exp_val = exp_calc[key]
                tol = 0.02 if key == "cost_after" else 0.01
                if abs((act_val or 0) - exp_val) > tol:
                    mismatches.append(f"{key}: 期望{exp_val}, 实际{act_val}")
            elif key in exp_calc and exp_calc[key] is None:
                if calc.get(key) is not None:
                    mismatches.append(f"{key}: 期望null, 实际{calc[key]}")

        if mismatches:
            failed += 1
            details.append((cf, f"不匹配: {'; '.join(mismatches)}"))
        else:
            # 校验 do_not_generate_operation_card
            if "do_not_generate_operation_card" in exp_v:
                exp_v2 = expected.get("validation", {})
                exp_dng = exp_v2["do_not_generate_operation_card"]
                act_dng = result["validation"].get("do_not_generate_operation_card")
                if act_dng != exp_dng:
                    failed += 1
                    details.append((cf, f"do_not_generate_operation_card 不匹配: 期望{exp_dng}, 实际{act_dng}"))
                    continue
            passed += 1
            details.append((cf, "PASS"))

    return passed, failed, details


def main():
    print("=" * 60)
    print("  TEST CASES VALIDATION REPORT")
    print("=" * 60)
    passed, failed, details = run_all_cases()
    total = passed + failed
    for name, status in details:
        icon = "✅" if status.startswith("PASS") else "❌"
        print(f"  {icon} {name}: {status}")

    print(f"\n  CASES: {passed} PASS / {failed} FAIL / {total} TOTAL")
    if failed == 0:
        print("  ✅ 全部测试用例通过")
    print("=" * 60)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
