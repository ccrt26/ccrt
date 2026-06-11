#!/usr/bin/env python3
"""validate_rules.py — 规则 JSON 可解析性 + 必填字段验证 v3.7.2

预期输出: RULES: PASS (或 FAIL)
"""

import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, os.pardir))
LOGIC_DIR = os.path.join(ROOT, "重点股票", "分析逻辑", "日报执行逻辑")


def check_rules():
    errors = []
    warnings = []

    # ── 规则 JSON 可解析 ─────────────────────────────────────────
    rules_dir = os.path.join(LOGIC_DIR, "rules")
    rule_files = {
        "daily_report_rules.json": ["rule_id", "rule_name", "positioning", "user_summary", "m_layer", "data_missing", "risk_light_override", "forbidden_expressions", "a4_a5_a7_reference"],
        "state_machine.json": ["rule_id", "rule_name", "states", "transitions", "action_change_map"],
        "fee_template_a_share_v0.1.json": ["rule_id", "rule_name", "buy", "sell", "marking_rules"],
        "user_operation_rules.json": ["rule_id", "rule_name", "generation_triggers", "core_principles", "templates"],
        "validation_rules.json": ["rule_id", "rule_name", "scenario_blocks", "field_blocks", "value_blocks", "quantity_validation", "date_validation"],
        "stock_whitelist.json": ["rule_id", "rule_name", "version", "mode", "active_stocks", "blocked_stocks_policy"],
        "daily_entry_switch.json": ["rule_id", "rule_name", "version", "formal_entry_enabled", "shadow_enabled", "dual_run_enabled", "allowed_stock_count", "allowed_codes"]
    }

    for fname, required_keys in rule_files.items():
        fpath = os.path.join(rules_dir, fname)
        if not os.path.exists(fpath):
            errors.append(f"[MISSING] {fname} — 文件不存在")
            continue
        try:
            with open(fpath, encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            errors.append(f"[PARSE FAIL] {fname}: {e}")
            continue
        for key in required_keys:
            if key not in data:
                warnings.append(f"[MISSING KEY] {fname} 缺少顶级键: {key}")

    # ── Schema JSON 可解析 ──────────────────────────────────────
    schemas_dir = os.path.join(LOGIC_DIR, "schemas")
    for fname in ["position_input.schema.json", "shadow_state.schema.json", "operation_card.schema.json"]:
        fpath = os.path.join(schemas_dir, fname)
        if not os.path.exists(fpath):
            errors.append(f"[MISSING] schemas/{fname} — 文件不存在")
            continue
        try:
            with open(fpath, encoding="utf-8") as f:
                json.load(f)
        except json.JSONDecodeError as e:
            errors.append(f"[PARSE FAIL] schemas/{fname}: {e}")

    # ── 费用模板特殊检查 ────────────────────────────────────────
    fee_path = os.path.join(rules_dir, "fee_template_a_share_v0.1.json")
    if os.path.exists(fee_path):
        with open(fee_path, encoding="utf-8") as f:
            fee = json.load(f)
        if "buy" in fee:
            for k in ["commission_rate", "min_commission", "stamp_tax_rate", "transfer_fee_rate"]:
                if k not in fee["buy"]:
                    warnings.append(f"[MISSING] fee_template buy.{k}")
        if "sell" in fee:
            for k in ["commission_rate", "min_commission", "stamp_tax_rate", "transfer_fee_rate"]:
                if k not in fee["sell"]:
                    warnings.append(f"[MISSING] fee_template sell.{k}")
        if "marking_rules" not in fee or len(fee.get("marking_rules", {})) < 3:
            errors.append("[CONTENT] fee_template.marking_rules 未包含三个层级标记")

    # ── 状态机检查 ──────────────────────────────────────────────
    sm_path = os.path.join(rules_dir, "state_machine.json")
    if os.path.exists(sm_path):
        with open(sm_path, encoding="utf-8") as f:
            sm = json.load(f)
        for state in ["A", "B", "C", "D", "E", "M"]:
            if state not in sm.get("states", {}):
                warnings.append(f"[CONTENT] state_machine 缺少状态 {state}")
        required_transitions = ["B→A", "A→B", "B→E", "B/A→C", "C→D", "D→B", "M→any"]
        found = [f"{t['from']}→{t['to']}" for t in sm.get("transitions", [])]
        for rt in required_transitions:
            if rt not in found:
                # B/A→C is a special case with "/"
                found_adj = [f for f in found if rt.split("→")[1] in f]
                if not found_adj:
                    warnings.append(f"[CONTENT] state_machine 缺少转移 {rt}")

    # ── 输出 ───────────────────────────────────────────────────
    print("=" * 60)
    print("  RULES VALIDATION REPORT")
    print("=" * 60)
    if errors:
        for e in errors:
            print(f"  ❌ {e}")
    if warnings:
        for w in warnings:
            print(f"  ⚠️  {w}")
    if not errors and not warnings:
        print("  ✅ 全部规则文件完整可解析")

    status = "FAIL" if errors else "PASS"
    print(f"\n  RULES: {status}")
    print(f"  ERRORS: {len(errors)}")
    print(f"  WARNINGS: {len(warnings)}")
    print("=" * 60)
    return status, errors, warnings


if __name__ == "__main__":
    status, errors, warnings = check_rules()
    sys.exit(1 if errors else 0)
