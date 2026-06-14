#!/usr/bin/env python3
"""知识注册表校验脚本 — 验证知识ID、来源等级、文件存在性、jsonl引用、sha256指纹"""
import json, sys, os, hashlib

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(PROJECT_ROOT, "统一解读", "knowledge_registry.json")
JSONL_PATH = os.path.join(PROJECT_ROOT, "统一解读", "knowledge_entries.jsonl")
VALID_LEVELS = {"L1","L2","L3","L4","L5","L5-seed"}
VALID_SCENES = {"日报","深度分析","每日荐股","模拟交易","保护机制","临时分析"}


def load_registry():
    if not os.path.exists(REGISTRY):
        print(f"FAIL: registry不存在: {REGISTRY}")
        sys.exit(1)
    with open(REGISTRY,"r",encoding="utf-8") as f:
        return json.load(f)


def load_jsonl_entries(path):
    """读取JSONL文件，返回 {knowledge_id: obj} 映射"""
    entries = {}
    if not os.path.exists(path):
        return entries
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                kid = obj.get("knowledge_id", "")
                if kid:
                    if kid in entries:
                        print(f"  WARN: JSONL重复knowledge_id: {kid}")
                    entries[kid] = obj
            except json.JSONDecodeError as e:
                print(f"  WARN: JSONL解析错误: {e}")
    return entries


def parse_jsonl_ref(ref):
    """解析 jsonl_ref 字段，返回 (filepath, fragment_kid)。如 knowledge_entries.jsonl#knowledge_id=XXX """
    if not ref:
        return None, None
    parts = ref.split("#", 1)
    filepath = parts[0]
    fragment = parts[1] if len(parts) > 1 else ""
    kid = ""
    if fragment.startswith("knowledge_id="):
        kid = fragment[len("knowledge_id="):]
    return filepath, kid


def sha256_file(path):
    """计算文件的SHA256"""
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def validate():
    data = load_registry()
    entries = data.get("entries",[])
    jsonl_entries = load_jsonl_entries(JSONL_PATH)
    ids = set()
    errors = []
    all_jsonl_kids = set(jsonl_entries.keys())

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
        # file_exists: 检查 file 字段指向的文件是否存在
        fpath = e.get("file","")
        if fpath:
            full_path = os.path.join(PROJECT_ROOT, fpath)
            if not os.path.exists(full_path):
                errors.append(f"{kid}: file不存在: {full_path}")
        # jsonl_ref 深度校验
        jref = e.get("jsonl_ref","")
        if jref:
            jpath, ref_kid = parse_jsonl_ref(jref)
            # 1) 文件存在
            if jpath:
                full_jpath = os.path.join(PROJECT_ROOT, jpath)
                if not os.path.exists(full_jpath):
                    errors.append(f"{kid}: jsonl_ref指向的文件不存在: {full_jpath}")
            # 2) fragment中的knowledge_id在JSONL中存在
            if ref_kid:
                if ref_kid not in all_jsonl_kids:
                    errors.append(f"{kid}: jsonl_ref中的knowledge_id={ref_kid} 在JSONL中不存在")
                else:
                    jl_obj = jsonl_entries[ref_kid]
                    # 3) JSONL条目中的source_file存在
                    src = jl_obj.get("source_file", "")
                    if src:
                        full_src = os.path.join(PROJECT_ROOT, src)
                        if not os.path.exists(full_src):
                            errors.append(f"{kid}: JSONL条目source_file不存在: {src}")
                    # 4) migrated_from_md_sha256 校验
                    actual_sha = ""
                    if src and os.path.exists(os.path.join(PROJECT_ROOT, src)):
                        actual_sha = sha256_file(os.path.join(PROJECT_ROOT, src))
                    declared_sha = jl_obj.get("migrated_from_md_sha256", "")
                    if actual_sha and declared_sha and actual_sha != declared_sha:
                        errors.append(f"{kid}: sha256不匹配 — JSONL声明={declared_sha}, 实际={actual_sha} (source_file={src})")

    # 全局检查：JSONL内knowledge_id不应重复（已在load中WARN，不额外FAIL）
    # 全局检查：JSONL条目数 >= registry条目数
    if len(jsonl_entries) < len(entries):
        errors.append(f"JSONL条目数({len(jsonl_entries)}) < registry条目数({len(entries)})，缺少知识ID")

    if errors:
        print(f"FAIL: {len(errors)} 个问题")
        for e in errors: print(f"  - {e}")
        sys.exit(1)
    print(f"PASS: {len(entries)} 条注册，{len(jsonl_entries)} 条JSONL，0 问题")
    print(f"  唯一ID: {len(ids)}")
    roles = set(e["role"] for e in entries)
    print(f"  覆盖角色: {roles}")


def scan():
    """统计registry概览"""
    data = load_registry()
    jsonl_entries = load_jsonl_entries(JSONL_PATH)
    entries = data.get("entries",[])
    print(f"知识注册表: {len(entries)} 条")
    print(f"  JSONL条目: {len(jsonl_entries)} 条")
    has_jsonl = sum(1 for e in entries if e.get("jsonl_ref"))
    print(f"  jsonl_ref已迁移: {has_jsonl}/{len(entries)}")
    for role in ["腰子","山猫","信鸽","玉夜","流金","青山"]:
        role_entries = [e for e in entries if e["role"]==role]
        l5 = [e for e in role_entries if e["source_level"] in ("L5","L5-seed")]
        strong = [e for e in role_entries if e["can_support_strong_action"]]
        print(f"  {role}: {len(role_entries)}条, L5/L5-seed={len(l5)}, 可支撑强动作={len(strong)}")


def main():
    import argparse
    p = argparse.ArgumentParser(description="知识注册表校验 — 含file_exists/jsonl_ref/sha256深度校验")
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
