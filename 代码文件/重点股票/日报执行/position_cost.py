#!/usr/bin/env python3
"""position_cost.py — 持仓成本计算引擎 v3.7.2.1

用户主动填写持仓交易记录后，按五种动作（建仓/加仓/减仓/平仓/无变化）
计算操作后持仓成本（cost_after）和已实现盈亏（realized_pnl）。

校验返回结构化结果：
  {
    "validation": {"valid": bool, "status": "PASS|WARN|BLOCK", "reason": str or None,
                   "warnings": [], "do_not_generate_operation_card": bool},
    "result": {...} or None
  }

依赖: rules/validation_rules.json (校验规则)
      rules/fee_template_a_share_v0.1.json (费用估算)
"""

import json
import os
import sys
from decimal import Decimal, ROUND_HALF_UP

# ── 路径 ──────────────────────────────────────────────────────────────
DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(DIR, os.pardir, os.pardir, os.pardir))
RULES_DIR = os.path.join(ROOT, "重点股票", "分析逻辑", "日报执行逻辑", "rules")


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── 校验返回结构 ─────────────────────────────────────────────────────
def _block(reason):
    return {"valid": False, "status": "BLOCK", "reason": reason,
            "warnings": [], "do_not_generate_operation_card": True}


def _pass_with_warnings(warnings, reason_extra=None, do_not_generate=False):
    return {"valid": True,
            "status": "WARN" if warnings else "PASS",
            "reason": reason_extra,
            "warnings": warnings,
            "do_not_generate_operation_card": do_not_generate}


# ── 费用估算 ─────────────────────────────────────────────────────────
def estimate_fee(action_type, transaction_price, transaction_quantity,
                 template_path=None):
    """估算 A 股交易费用。

    返回: (fee_amount, marking_flag)
    """
    if template_path is None:
        template_path = os.path.join(RULES_DIR, "fee_template_a_share_v0.1.json")
    template = load_json(template_path)
    amount = transaction_price * transaction_quantity

    if action_type in ("建仓", "加仓"):
        fee_rules = template["buy"]
    else:
        fee_rules = template["sell"]

    commission = max(amount * fee_rules["commission_rate"], fee_rules["min_commission"])
    stamp_tax = amount * fee_rules["stamp_tax_rate"]
    transfer_fee = amount * fee_rules["transfer_fee_rate"]
    fee = round(commission + stamp_tax + transfer_fee, 2)
    return fee, "estimated"


# ── 输入校验 ═════════════════════════════════════════════════════════
def validate_position_input(input_data, validation_rules_path=None):
    """校验用户持仓输入是否合法。

    返回结构化 dict:
      {"valid": bool, "status": "PASS|WARN|BLOCK", "reason": str or None, "warnings": [str]}
    """
    if validation_rules_path is None:
        validation_rules_path = os.path.join(RULES_DIR, "validation_rules.json")

    rules = load_json(validation_rules_path)
    status = input_data.get("position_status")
    action = input_data.get("action_type")
    warnings = []

    # ── 1. 场景 BLOCK ────────────────────────────────────────────
    for sb in rules["scenario_blocks"]:
        scenario = sb["scenario"]
        want_status, want_action = scenario.split("+")
        if status == want_status and action == want_action:
            return _block(sb["block_reason"])

    # ── 2. 字段缺失 BLOCK ────────────────────────────────────────
    for fb in rules["field_blocks"]:
        field = fb["field"]
        if action in fb["block_scenarios"] and input_data.get(field) is None:
            return _block(fb["block_reason"])

    # ── 3. 字段值 BLOCK（<=0 检查）───────────────────────────────
    for vb in rules.get("value_blocks", []):
        field = vb["field"]
        val = input_data.get(field)
        if action in vb.get("block_scenarios", []) and val is not None and val <= 0:
            return _block(vb["block_reason"])

    # ── 4. 数量校验 BLOCK（减仓超持仓 / 平仓不等）───────────────
    price = input_data.get("transaction_price") or 0
    qty = input_data.get("transaction_quantity") or 0
    pos_before = input_data.get("position_before_quantity") or 0

    if action == "减仓" and qty > pos_before:
        return _block("减仓数量不能超过当前持仓")
    if action == "减仓" and (pos_before - qty) < 0:
        return _block("减仓后持仓不能为负数")
    if action == "平仓" and qty != pos_before:
        return _block("平仓数量必须等于当前持仓数量")

    # ── 5. 日期校验（未来日期 → WARN）───────────────────────────
    txn_date = input_data.get("transaction_date")
    report_date = input_data.get("report_trade_date")
    has_future_date = False
    if txn_date and report_date and txn_date > report_date:
        warnings.append("future_transaction_date")
        has_future_date = True

    # ── 6. 费用缺失 WARN ─────────────────────────────────────────
    if input_data.get("fee_amount") is None:
        warnings.append("fee_assumed_zero")

    return _pass_with_warnings(warnings, do_not_generate=has_future_date)


# ── 成本计算 ─────────────────────────────────────────────────────────
def _round(val, ndigits=2):
    return float(Decimal(str(val)).quantize(Decimal("0." + "0" * ndigits), rounding=ROUND_HALF_UP))


def calculate_build(price, qty, fee=0.0):
    total = price * qty + fee
    cost_after = _round(total / qty) if qty > 0 else 0.0
    return {"position_after_quantity": qty, "cost_after": cost_after, "realized_pnl": 0.0}


def calculate_add(cost_before, pos_before, price, qty, fee=0.0):
    total_cost = cost_before * pos_before + price * qty + fee
    total_qty = pos_before + qty
    cost_after = _round(total_cost / total_qty) if total_qty > 0 else cost_before
    return {"position_after_quantity": total_qty, "cost_after": cost_after, "realized_pnl": 0.0}


def calculate_reduce(cost_before, pos_before, price, qty, fee=0.0):
    realized_pnl = _round((price - cost_before) * qty - fee)
    return {"position_after_quantity": pos_before - qty, "cost_after": cost_before,
            "realized_pnl": realized_pnl}


def calculate_close(cost_before, pos_before, price, qty, fee=0.0):
    realized_pnl = _round((price - cost_before) * pos_before - fee)
    return {"position_after_quantity": 0, "cost_after": None, "realized_pnl": realized_pnl}


def calculate_no_change():
    return {"position_after_quantity": None, "cost_after": None, "realized_pnl": 0.0}


# ── 主调度 ═══════════════════════════════════════════════════════════
COST_CALCULATORS = {
    "建仓": calculate_build,
    "加仓": calculate_add,
    "减仓": calculate_reduce,
    "平仓": calculate_close,
    "无变化": calculate_no_change,
}


def calculate(input_data, template_path=None):
    """统一入口：接收用户输入 dict，返回计算结果 dict。

    返回: {
        "validation": {"valid": bool, "status": "PASS|WARN|BLOCK", "reason": str or None,
                        "warnings": [str], "do_not_generate_operation_card": bool},
        "result": {position_after_quantity, cost_after, realized_pnl} or None
    }
    WARN 状态下仍执行计算，但携带 warnings。
    """
    v = validate_position_input(input_data)
    if v["status"] == "BLOCK":
        return {"validation": v, "result": None}

    action = input_data["action_type"]
    if action not in COST_CALCULATORS:
        return {"validation": _block(f"未知动作: {action}"), "result": None}

    price = input_data.get("transaction_price") or 0
    qty = input_data.get("transaction_quantity") or 0

    # 费用处理：用户手填优先 → 模板估算 → 默认0
    fee = input_data.get("fee_amount")
    if fee is None and price > 0 and qty > 0:
        fee, _ = estimate_fee(action, price, qty, template_path)
    elif fee is None:
        fee = 0.0

    if action == "建仓":
        result = calculate_build(price, qty, fee)
    elif action == "加仓":
        result = calculate_add(input_data["cost_before"], input_data["position_before_quantity"],
                               price, qty, fee)
    elif action == "减仓":
        result = calculate_reduce(input_data["cost_before"], input_data["position_before_quantity"],
                                  price, qty, fee)
    elif action == "平仓":
        result = calculate_close(input_data["cost_before"], input_data["position_before_quantity"],
                                 price, qty, fee)
    else:
        result = calculate_no_change()

    return {"validation": v, "result": result}


# ── CLI ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) > 1:
        path = sys.argv[1]
        data = load_json(path)
        out = calculate(data)
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        test = {
            "position_status": "空仓", "action_type": "建仓",
            "transaction_price": 38.50, "transaction_quantity": 2000,
            "fee_amount": 15.00
        }
        print(json.dumps(calculate(test), ensure_ascii=False, indent=2))
