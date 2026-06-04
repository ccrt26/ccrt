#!/usr/bin/env python3
"""知识进化执行器 — 扫描eval_hooks，生成五库更新草案"""
import json, sys, os
from datetime import datetime, date

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE = os.path.join(PROJECT_ROOT, "统一解读", "eval_hooks", "store")
PROPOSALS = os.path.join(PROJECT_ROOT, "统一解读", "evolution", "proposals")
REGISTRY = os.path.join(PROJECT_ROOT, "统一解读", "knowledge_registry.json")

os.makedirs(PROPOSALS, exist_ok=True)


def load_hooks():
    hooks = []
    if not os.path.exists(STORE): return hooks
    for fn in sorted(os.listdir(STORE)):
        if not fn.endswith(".json"): continue
        try:
            with open(os.path.join(STORE, fn)) as f:
                hooks.append(json.load(f))
        except: pass
    return hooks


def load_registry():
    if not os.path.exists(REGISTRY): return {}
    with open(REGISTRY) as f: return json.load(f)


def scan():
    hooks = load_hooks()
    total = len(hooks)
    by_verdict = {}
    for h in hooks:
        v = h.get("comprehensive_result","待评估")
        by_verdict[v] = by_verdict.get(v,0)+1

    print(f"eval_hooks: {total} 条")
    for v, c in sorted(by_verdict.items()):
        print(f"  {v}: {c}")

    failures = [h for h in hooks if h.get("comprehensive_result")=="失败"]
    if failures:
        print(f"\n失败归因分布 ({len(failures)}条):")
        attrs = {}
        for h in failures:
            a = h.get("failure_attribution","未知")
            attrs[a] = attrs.get(a,0)+1
        for a, c in sorted(attrs.items(), key=lambda x:-x[1]):
            print(f"  {a}: {c}")


def propose():
    hooks = load_hooks()
    registry = load_registry()
    entries = registry.get("entries",[])
    today = date.today().isoformat()
    proposals = []

    failures = [h for h in hooks if h.get("comprehensive_result")=="失败"]

    # 规则更新候选
    rule_fails = {}
    for h in failures:
        for r in h.get("rule_refs",[]):
            rule_fails[r] = rule_fails.get(r,0)+1
    for rule, cnt in rule_fails.items():
        if cnt >= 2:
            proposals.append({
                "type": "rule_update",
                "target": rule,
                "failures": cnt,
                "proposal": f"规则 {rule} 连续失败{cnt}次，建议review修正条件或阈值",
                "date": today
            })

    # 错误反例候选
    for h in failures[:5]:
        attr = h.get("failure_attribution","")
        if attr in ("规则问题","动作过强","腰子整合问题","角色问题"):
            proposals.append({
                "type": "error_case_candidate",
                "interpretation_id": h.get("interpretation_id"),
                "claim": h.get("claim",""),
                "attribution": attr,
                "template": f"## 反例候选\n错误类型: {attr}\n原始主张: {h.get('claim','')}\n为什么错: 后评估判定失败\n关联rule_refs: {h.get('rule_refs',[])}\n关联knowledge_refs: {h.get('knowledge_refs',[])}",
                "date": today
            })

    # 模板污染候选
    pollution_keywords = ["大概率","确定性","毋庸置疑","必然","肯定","后市看涨"]
    for h in hooks:
        claim = h.get("claim","")
        hits = [k for k in pollution_keywords if k in claim]
        if hits:
            proposals.append({
                "type": "pollution_candidate",
                "interpretation_id": h.get("interpretation_id"),
                "expressions": hits,
                "proposal": f"含污染表达: {hits}",
                "date": today
            })

    # 写入草案
    if proposals:
        fn = f"evolution_proposal_{today}.json"
        path = os.path.join(PROPOSALS, fn)
        with open(path,"w",encoding="utf-8") as f:
            json.dump({"date":today,"proposals":proposals}, f, ensure_ascii=False, indent=2)
        print(f"已生成 {len(proposals)} 条进化草案 → {path}")
        for p in proposals:
            print(f"  [{p['type']}] {p.get('target',p.get('interpretation_id','?'))}")
    else:
        print("无需更新草案（无失败案例或候选）")


def weekly():
    """周报: eval_hooks统计+五库状态"""
    hooks = load_hooks()
    total = len(hooks)
    EVALUATED = {"命中","部分命中","失败","不可评估"}
    completed = [h for h in hooks if h.get("comprehensive_result") in EVALUATED]
    pending = [h for h in hooks if h.get("comprehensive_result","") not in EVALUATED]
    failures = [h for h in completed if h.get("comprehensive_result")=="失败"]
    hits = [h for h in completed if h.get("comprehensive_result")=="命中"]

    print(f"=== 知识进化周报 {date.today().isoformat()} ===")
    print(f"eval_hooks: {total}条")
    print(f"  已评估: {len(completed)}条 | 待评估: {len(pending)}条")
    if completed:
        print(f"  命中率: {len(hits)}/{len(completed)} = {len(hits)/len(completed)*100:.1f}%")
    else:
        print(f"  命中率: 暂无可计算样本")
    if failures:
        print(f"  失败: {len(failures)}条")
    # 注册表状态
    reg = load_registry()
    entries = reg.get("entries",[])
    print(f"知识注册: {len(entries)}条")
    l5 = [e for e in entries if e["source_level"] in ("L5","L5-seed")]
    print(f"L5-seed待升级: {len(l5)}条")
    # 进化草案
    prop_files = os.listdir(PROPOSALS) if os.path.exists(PROPOSALS) else []
    print(f"进化草案: {len(prop_files)}份")


def main():
    import argparse
    p = argparse.ArgumentParser(description="知识进化执行器")
    p.add_argument("--scan", action="store_true", help="扫描eval_hooks统计")
    p.add_argument("--propose", action="store_true", help="生成五库更新草案")
    p.add_argument("--weekly", action="store_true", help="周报")
    args = p.parse_args()

    if args.scan: scan()
    elif args.propose: propose()
    elif args.weekly: weekly()
    else:
        scan()
        print()
        propose()


if __name__=="__main__":
    main()
