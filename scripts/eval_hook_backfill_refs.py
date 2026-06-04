#!/usr/bin/env python3
"""eval_hook 引用链回填 — 支持同一 interpretation_id 多 hook"""
import json, sys, os, glob
from collections import defaultdict

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE = os.path.join(PROJECT_ROOT, "统一解读", "eval_hooks", "store")
SAMPLE_DIR = os.path.join(PROJECT_ROOT, "统一解读", "样例")

REF_FIELDS = ["scene","stock_code","trade_date","role","rule_refs","knowledge_refs","signal_refs","source_levels","trigger_condition","invalidation_condition"]


def load_samples():
    """iid → interpretation dict"""
    samples = {}
    for pattern in ["接入_*.json", "场景入口_*.json", "样例[123]_*.json"]:
        for path in glob.glob(os.path.join(SAMPLE_DIR, pattern)):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                interp = data.get("interpretation", data)
                iid = interp.get("interpretation_id", "")
                if iid and iid != "UNKNOWN":
                    samples[iid] = interp
            except Exception:
                pass
    return samples


def load_hooks():
    """P0-H: iid → [hook_info, ...] 列表"""
    hooks = defaultdict(list)
    if not os.path.exists(STORE):
        return hooks
    for fn in sorted(os.listdir(STORE)):
        if not fn.endswith(".json"):
            continue
        path = os.path.join(STORE, fn)
        try:
            with open(path, "r", encoding="utf-8") as f:
                h = json.load(f)
            iid = h.get("interpretation_id", "")
            hooks[iid].append({"file": fn, "path": path, "hook": h})
        except Exception:
            pass
    return hooks


def backfill(dry_run=True):
    samples = load_samples()
    hooks = load_hooks()
    total_hooks = sum(len(v) for v in hooks.values())
    results = {"total": total_hooks, "matched": [], "unmatched": [], "legacy_marked": 0, "fields_filled": 0}

    # 回填: 匹配的 interpretation_id
    for iid, sample_interp in samples.items():
        if iid not in hooks:
            continue
        for hinfo in hooks[iid]:
            h = hinfo["hook"]
            updated_fields = []
            for fld in REF_FIELDS:
                val = sample_interp.get(fld)
                if val and not h.get(fld):
                    h[fld] = val
                    updated_fields.append(fld)
            if updated_fields:
                results["fields_filled"] += len(updated_fields)
                if not dry_run:
                    with open(hinfo["path"], "w", encoding="utf-8") as f:
                        json.dump(h, f, ensure_ascii=False, indent=2)
                results["matched"].append({"file": hinfo["file"], "iid": iid, "fields": updated_fields})

    # 标记: 无法匹配的 hook → legacy
    all_sample_iids = set(samples.keys())
    for iid, hlist in hooks.items():
        if iid in all_sample_iids:
            continue
        for hinfo in hlist:
            h = hinfo["hook"]
            if not h.get("legacy_missing_interpretation"):
                results["unmatched"].append({"file": hinfo["file"], "iid": iid})
                if not dry_run:
                    h["legacy_missing_interpretation"] = True
                    with open(hinfo["path"], "w", encoding="utf-8") as f:
                        json.dump(h, f, ensure_ascii=False, indent=2)
                    results["legacy_marked"] += 1

    return results


def verify():
    """检查: 每条 hook 必须有引用链或 legacy 标记"""
    issues = []
    if not os.path.exists(STORE):
        return issues
    for fn in sorted(os.listdir(STORE)):
        if not fn.endswith(".json"):
            continue
        path = os.path.join(STORE, fn)
        try:
            with open(path, "r", encoding="utf-8") as f:
                h = json.load(f)
        except Exception:
            issues.append(f"{fn}: 无法读取")
            continue

        has_refs = any(h.get(f) for f in ["knowledge_refs", "rule_refs", "scene"])
        has_legacy = h.get("legacy_missing_interpretation", False)

        if not has_refs and not has_legacy:
            issues.append(f"{fn}: 无引用链且无legacy标记")
    return issues


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", default=True)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--verify", action="store_true", help="仅检查，不修改")
    args = p.parse_args()

    if args.verify:
        issues = verify()
        if issues:
            print(f"FAIL: {len(issues)} 个问题")
            for i in issues:
                print(f"  - {i}")
            sys.exit(1)
        print("PASS: 所有 hook 均有引用链或 legacy 标记")
        return

    dry = not args.apply
    action = "预览" if dry else "回填"
    results = backfill(dry_run=dry)

    print(f"=== eval_hook 引用链{action} ===")
    print(f"Store 总数: {results['total']}")
    print(f"匹配回填: {len(results['matched'])} 条 hook, 填充 {results['fields_filled']} 字段")
    for m in results['matched'][:5]:
        print(f"  {m['file']}: {m['fields']}")
    if len(results['matched']) > 5:
        print(f"  ... 共 {len(results['matched'])} 条")
    print(f"未匹配(legacy): {len(results['unmatched'])} 条 hook")
    if not dry and results['legacy_marked']:
        print(f"已标记 legacy: {results['legacy_marked']} 条")

    if dry:
        print("\n使用 --apply 执行实际回填")

    # 自动验证
    if not dry:
        issues = verify()
        if issues:
            print(f"\nWARN: {len(issues)} 条仍有问题")


if __name__ == "__main__":
    main()
