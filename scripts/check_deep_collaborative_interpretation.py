#!/usr/bin/env python3
"""P5-B: 深度分析协作解读闸门 — 全字段禁句扫描+同质化重写"""
import argparse, json, sys, re
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]

OBJS = ["baseline_conclusion","fundamental_interpretation","valuation_interpretation",
        "industry_policy_interpretation","event_catalyst_interpretation",
        "technical_structure_interpretation","capital_liquidity_interpretation",
        "risk_boundary_interpretation","position_strategy_interpretation","scenario_plan"]
FIELDS = ["data_fact","interpretation","supporting_evidence","counter_evidence",
          "investment_meaning","action_impact","trigger_condition","invalidation_condition","confidence"]

PSEUDO = [
    "为投资决策提供基线","指引仓位和触发条件","关键价位突破","反向突破","正文数据",
    "需关注后续数据变化和市场预期修正","事件跟踪中","北向/主力资金","三情景展望",
    "长期看好","估值合理","后续关注","建议跟踪",
    "趋势改善","有望修复","政策支持","行业空间广阔","基本面稳健","资金关注度提升",
    "风险可控","等待验证","维持判断","结论不变","具备配置价值","逢低关注","择机参与",
]

MD_SECTIONS = [
    ("总结论","baseline_conclusion"),("核心投资逻辑","fundamental_interpretation"),
    ("估值判断","valuation_interpretation"),("关键价位","risk_boundary_interpretation"),
    ("仓位建议","position_strategy_interpretation"),("风险边界","risk_boundary_interpretation"),
    ("三情景推演","scenario_plan"),("后续验证点","event_catalyst_interpretation")
]

def is_empty(v):
    return v is None or v == "" or v == [] or v == {}

def contains_pseudo(text):
    text = str(text)
    for p in PSEUDO:
        if p in text and len(p) >= 4:
            return p
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    args = ap.parse_args()
    dc = args.date.replace("-", "")
    issues = []
    app_files = sorted((ROOT / "重点股票" / "深度分析" / "深度分析报告").glob(f"*/*深度分析报告_{dc}_系统附录.json"))
    md_files = sorted((ROOT / "重点股票" / "深度分析" / "深度分析报告").glob(f"*/*深度分析报告_{dc}.md"))

    if not app_files:
        issues.append(f"未找到 {dc} 系统附录")
    if len(app_files) != 10:
        issues.append(f"系统附录数量={len(app_files)}")

    # Phase 1: per-file checks
    for jp in app_files:
        try:
            data = json.loads(jp.read_text(encoding="utf-8"))
        except:
            issues.append(f"{jp.parent.name}: JSON解析失败")
            continue
        ds = (data.get("yaozi_integration") or {}).get("deep_synthesis")
        if not isinstance(ds, dict):
            issues.append(f"{jp.parent.name}: missing deep_synthesis")
            continue

        for obj in OBJS:
            item = ds.get(obj)
            if not isinstance(item, dict):
                issues.append(f"{jp.parent.name}: {obj} missing")
                continue
            for f in FIELDS:
                v = item.get(f)
                if is_empty(v):
                    issues.append(f"{jp.parent.name}: {obj}.{f} empty")
                if f != "confidence":
                    hit = contains_pseudo(str(v))
                    if hit:
                        issues.append(f"{jp.parent.name}: {obj}.{f}包含禁句: {hit}")
            conf = item.get("confidence")
            if conf not in ("高","中","低"):
                issues.append(f"{jp.parent.name}: {obj}.confidence={conf}")

        # Full text scan of deep_discussion + yaozi_integration + eval_hooks
        full_text = json.dumps(data.get("role_interpretations",{}),ensure_ascii=False)
        full_text += json.dumps(data.get("yaozi_integration",{}),ensure_ascii=False)
        full_text += json.dumps(data.get("eval_hooks",{}),ensure_ascii=False)
        for p in PSEUDO:
            if p in full_text and len(p) >= 4:
                issues.append(f"{jp.parent.name}: 全文包含禁句: {p}")
                break

        # eval_hooks check
        eh = data.get("eval_hooks",{})
        for h in ["baseline_id","report_date","stock_code","stock_name","t5_verify","t20_verify","invalidation_condition"]:
            if is_empty(eh.get(h)):
                issues.append(f"{jp.parent.name}: eval_hooks.{h}缺失")

    # Phase 2: homogeneity across 10 files
    seen = {}
    for obj in OBJS:
        for f in FIELDS:
            seen[(obj,f)] = Counter()
    for jp in app_files:
        try:
            data = json.loads(jp.read_text(encoding="utf-8"))
            ds = (data.get("yaozi_integration") or {}).get("deep_synthesis") or {}
        except:
            continue
        for obj in OBJS:
            item = ds.get(obj) or {}
            for f in FIELDS:
                txt = str(item.get(f,""))[:40].strip()
                if txt:
                    seen[(obj,f)][txt] += 1
    for (obj,f), counter in seen.items():
        for txt, cnt in counter.items():
            if cnt >= 4 and len(txt) >= 10:
                issues.append("同质化:" + obj + "." + f + " x" + str(cnt) + ": " + txt[:40])

    # Phase 3: MD traceability
    if md_files:
        for mp in md_files:
            md_text = mp.read_text(encoding="utf-8")
            jp = mp.with_name(mp.stem + "_系统附录.json")
            if not jp.exists():
                continue
            try:
                data = json.loads(jp.read_text(encoding="utf-8"))
                ds = (data.get("yaozi_integration") or {}).get("deep_synthesis") or {}
            except:
                continue
            for section, obj_name in MD_SECTIONS:
                if section in md_text:
                    item = ds.get(obj_name,{})
                    for f in ["data_fact","supporting_evidence","counter_evidence","trigger_condition","invalidation_condition"]:
                        val = str(item.get(f,""))
                        if "深度" in val[:10]:
                            issues.append(f"{mp.parent.name}: MD有{section}但{obj_name}.{f}仍为占位")
                        if "正文数据" in val:
                            issues.append(f"{mp.parent.name}: MD有{section}但{obj_name}.{f}='正文数据'")
                        if "需关注后续" in val:
                            issues.append(f"{mp.parent.name}: MD有{section}但{obj_name}.{f}为模板句")

    if issues:
        print("DEEP_COLLABORATIVE_INTERPRETATION: BLOCK")
        for i in issues[:35]:
            print(f"  - {i}")
        return 2
    print("DEEP_COLLABORATIVE_INTERPRETATION: PASS")
    return 0

if __name__ == "__main__":
    sys.exit(main())
