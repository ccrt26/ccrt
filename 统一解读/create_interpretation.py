#!/usr/bin/env python3
"""
统一解释对象生成器 — 双对象格式：interpretation + unified_interpretation
用法:
  python3 create_interpretation.py --from-adapter <JSON>  # 验证+包装
  python3 create_interpretation.py --from-adapter <JSON> --json
"""

import json, sys, os, subprocess, uuid
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VALIDATOR = os.path.join(SCRIPT_DIR, "validate_interpretation.py")
WRITE_HOOK = os.path.join(SCRIPT_DIR, "write_eval_hook.py")
STORE_DIR = os.path.join(SCRIPT_DIR, "eval_hooks", "store")

SCENES = ["日报", "深度分析", "每日荐股", "模拟交易", "保护机制", "临时分析"]
ROLES = ["腰子", "山猫", "信鸽", "玉夜", "流金", "青山"]

os.makedirs(STORE_DIR, exist_ok=True)


def generate_id(prefix, date_str=None):
    if not date_str:
        date_str = datetime.now().strftime("%Y%m%d")
    else:
        date_str = date_str.replace("-", "")
    ts = datetime.now().strftime("%H%M%S")
    uid = uuid.uuid4().hex[:6]
    return f"{prefix}-{date_str}-{ts}-{uid}"


def create_interpretation(scene, stock_code, trade_date, role, data_fact, hypothesis,
                          supporting, counter, implication, action_bias, confidence,
                          trigger_cond="", price_range="", position_limit="", time_window="",
                          invalidation="", rule_refs=None, knowledge_refs=None, signal_refs=None,
                          eval_window=None):
    if scene not in SCENES:
        raise ValueError(f"scene 必须为: {SCENES}")
    if role not in ROLES:
        raise ValueError(f"role 必须为: {ROLES}")
    return {
        "interpretation_id": generate_id("INT", trade_date),
        "scene": scene, "stock_code": stock_code, "trade_date": trade_date, "role": role,
        "data_fact": data_fact, "interpretation_hypothesis": hypothesis,
        "supporting_evidence": supporting, "counter_evidence": counter,
        "investment_implication": implication, "action_bias": action_bias,
        "trigger_condition": trigger_cond, "price_range": price_range,
        "position_limit": position_limit, "time_window": time_window,
        "confidence": confidence, "invalidation_condition": invalidation,
        "eval_window": eval_window or {"t1": "", "t3": "", "t5": ""},
        "rule_refs": rule_refs or [], "knowledge_refs": knowledge_refs or [],
        "signal_refs": signal_refs or []
    }


def validate(obj):
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(obj, f, ensure_ascii=False)
        tmp = f.name
    try:
        r = subprocess.run([sys.executable, VALIDATOR, tmp, "--json"],
                          capture_output=True, text=True)
        result = json.loads(r.stdout) if r.stdout else {"overall": "ERROR"}
        result["exit_code"] = r.returncode
        return result
    finally:
        os.unlink(tmp)


def build_unified_output(obj, u9_result, u10_result, eval_hook_ids=None):
    """P0-D-1: 双对象格式 — interpretation + unified_interpretation"""
    return {
        "interpretation": obj,
        "unified_interpretation": {
            "enabled": True,
            "interpretation_id": obj["interpretation_id"],
            "scene": obj["scene"],
            "role_interpretations": [{"role": obj["role"], "hypothesis": obj["interpretation_hypothesis"]}],
            "yaozi_integration": {
                "action_bias": obj["action_bias"],
                "confidence": obj["confidence"],
                "invalidation": obj["invalidation_condition"]
            },
            "audit_u9": u9_result,
            "audit_u10": u10_result,
            "eval_hooks": eval_hook_ids or [],
            "rule_refs": obj.get("rule_refs", []),
            "knowledge_refs": obj.get("knowledge_refs", []),
            "signal_refs": obj.get("signal_refs", [])
        }
    }


def extract_interpretation(data):
    """P0-D-2: 从输入中提取原始解释对象。支持3种格式"""
    # 格式1: 纯原始解释对象 (有 interpretation_id + data_fact)
    if "data_fact" in data and "interpretation_id" in data:
        return data

    # 格式2: 双对象 (有 interpretation + unified_interpretation)
    if "interpretation" in data:
        inner = data["interpretation"]
        if isinstance(inner, dict) and "data_fact" in inner:
            return inner

    # 格式3: 只有 unified_interpretation，无 interpretation → BLOCK
    if "unified_interpretation" in data and "interpretation" not in data:
        ui = data["unified_interpretation"]
        if isinstance(ui, dict) and "interpretation_id" in ui:
            return {"__error__": True, "msg": "BLOCK: 缺少 raw interpretation (仅有 unified_interpretation)，不得验收为正式解释对象",
                    "unified_id": ui.get("interpretation_id", "UNKNOWN")}

    return None


def write_eval_hook_for(obj):
    """调用 write_eval_hook.py 写入 eval_hook，返回 hook_id"""
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(obj, f, ensure_ascii=False)
        tmp = f.name
    try:
        r = subprocess.run([sys.executable, WRITE_HOOK, "--interpretation", tmp],
                          capture_output=True, text=True)
        if r.returncode != 0:
            return None
        for line in r.stdout.split("\n"):
            if "eval_hook_id:" in line:
                return line.split("eval_hook_id:")[-1].strip()
    except Exception:
        return None
    finally:
        os.unlink(tmp)
    return None


def main():
    import argparse
    parser = argparse.ArgumentParser(description="统一解释对象生成器")
    parser.add_argument("--from-adapter", help="从JSON创建")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="不写入eval_hook到store")
    args = parser.parse_args()

    if not args.from_adapter:
        print("用法: create_interpretation.py --from-adapter <JSON>")
        sys.exit(1)

    with open(args.from_adapter, "r", encoding="utf-8") as f:
        data = json.load(f)

    obj = extract_interpretation(data)

    if obj is None:
        print("BLOCK: 输入无法识别为有效解释对象")
        sys.exit(2)

    if isinstance(obj, dict) and obj.get("__error__"):
        print(obj["msg"])
        sys.exit(2)

    # 验证
    result = validate(obj)
    u9 = result.get("u9", {"status": "ERROR"})
    u10 = result.get("u10", {"status": "ERROR"})
    overall = result.get("overall", "ERROR")

    # 生成 eval_hook (PASS/WARN 时，--dry-run 跳过写入)
    hook_ids = []
    if overall in ("PASS", "WARN") and not args.dry_run:
        hid = write_eval_hook_for(obj)
        if hid:
            hook_ids.append(hid)

    # 双对象输出
    output = build_unified_output(obj, u9, u10, hook_ids)

    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        iid = obj["interpretation_id"]
        print(f"解释对象: {iid} | 整体: {overall} | U-9: {u9.get('status')} | U-10: {u10.get('status')}")
        if hook_ids:
            print(f"eval_hooks: {hook_ids}")
        if overall == "BLOCK":
            print("BLOCK: 不得输出强动作")
        elif overall == "WARN":
            print("WARN: 动作降级")
        else:
            print("PASS: 可正常输出")


if __name__ == "__main__":
    main()
