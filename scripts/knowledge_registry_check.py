#!/usr/bin/env python3
"""知识注册表校验脚本"""
import json, sys, os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(PROJECT_ROOT, "统一解读", "knowledge_registry.json")
VALID_LEVELS = {"L1","L2","L3","L4","L5","L5-seed"}
VALID_SCENES = {"日报","深度分析","每日荐股","模拟交易","保护机制","临时分析"}


def load_registry():
    if not os.path.exists(REGISTRY):
        print(f"FAIL: registry不存在: {REGISTRY}")
        sys.exit(1)
    with open(REGISTRY,"r",encoding="utf-8") as f:
        return json.load(f)


def validate():
    data = load_registry()
    entries = data.get("entries",[])
    ids = set()
    errors = []
    for i, e in enumerate(entries):
        kid = e.get("knowledge_id","?")
        # ID唯一
        if kid in ids: errors.append(f"重复ID: {kid}")
        ids.add(kid)
        # 必填字段
        for fld in ["knowledge_id","role","file","source_level","can_support_strong_action","owner"]:
            if fld not in e:
                errors.append(f"{kid}: 缺少 {fld}")
        # source_level合法性
        sl = e.get("source_level","")
        if sl and sl not in VALID_LEVELS:
            errors.append(f"{kid}: 非法source_level: {sl}")
        # L5不能标记为可支撑强动作
        if sl in ("L5","L5-seed") and e.get("can_support_strong_action"):
            errors.append(f"{kid}: L5/L5-seed 不得标记 can_support_strong_action=true")
        # 场景合法性
        for s in e.get("applicable_scenes",[]):
            if s not in VALID_SCENES:
                errors.append(f"{kid}: 非法场景: {s}")

    if errors:
        print(f"FAIL: {len(errors)} 个问题")
        for e in errors: print(f"  - {e}")
        sys.exit(1)
    print(f"PASS: {len(entries)} 条注册，0 问题")
    print(f"  唯一ID: {len(ids)}")
    roles = set(e["role"] for e in entries)
    print(f"  覆盖角色: {roles}")


def scan():
    """统计registry概览"""
    data = load_registry()
    entries = data.get("entries",[])
    print(f"知识注册表: {len(entries)} 条")
    for role in ["腰子","山猫","信鸽","玉夜","流金","青山"]:
        role_entries = [e for e in entries if e["role"]==role]
        l5 = [e for e in role_entries if e["source_level"] in ("L5","L5-seed")]
        strong = [e for e in role_entries if e["can_support_strong_action"]]
        print(f"  {role}: {len(role_entries)}条, L5/L5-seed={len(l5)}, 可支撑强动作={len(strong)}")


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--scan", action="store_true")
    p.add_argument("--validate", action="store_true")
    args = p.parse_args()
    if args.scan: scan()
    elif args.validate: validate()
    else:
        scan()
        print()
        validate()


if __name__=="__main__":
    main()
