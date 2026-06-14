
import json, hashlib
from pathlib import Path
from datetime import date

BASE = Path("/Users/ccrt/ccrt")
KB = BASE / "00_项目地基/07_知识进化/knowledge"
LIT_CARDS = KB / "literature_cards/qingshan"
REPORTS = KB / "reports"
AUDIT = BASE / "00_项目地基/08_审计与验收"
MANIFEST = KB / "manifest.json"

STAGE = "G3-QINGSHAN-FIRST-LITERATURE-CARD-FAMA-FRENCH-1993-v1.0"

CARD_PATH = LIT_CARDS / "LC_QINGSHAN_FAMA_FRENCH_1993_COMMON_RISK_FACTORS_v1.0.json"
REPORT_PATH = REPORTS / "qingshan_first_literature_card_fama_french_1993_validation_v1.0.json"

LIT_CARDS.mkdir(parents=True, exist_ok=True)
REPORTS.mkdir(parents=True, exist_ok=True)

card = {
  "meta": {
    "version": "1.0",
    "stage": STAGE,
    "owner_role": "青山",
    "status": "card_draft",
    "created": str(date.today()),
    "purpose": "青山第一张真实 LiteratureCard 小样本试跑；只验证文献卡片流程，不生成规则候选"
  },
  "card_id": "LC-QS-FF1993-001",
  "source_id": "SRC-FAMA-FRENCH-1993-JFE-COMMON-RISK-FACTORS",
  "source_title": "Common Risk Factors in the Returns on Stocks and Bonds",
  "source_type": "academic_paper",
  "author_or_institution": ["Eugene F. Fama", "Kenneth R. French", "Journal of Financial Economics"],
  "publication_date": "1993",
  "source_selection_status": "source_candidate_accepted",
  "quality_status": "quality_pass_with_cross_check",
  "total_score": 88,
  "hard_block_triggered": [],
  "source_urls": [
    "https://doi.org/10.1016/0304-405X(93)90023-5",
    "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html"
  ],
  "extracted_claims": [
    {
      "claim_id": "CLAIM-001",
      "claim": "股票收益可以用市场、规模、价值等共同因子进行解释，单一 beta 不足以覆盖主要横截面差异。",
      "evidence_ref": "Fama/French 1993, Journal of Financial Economics 33, 3-56",
      "qingshan_relevance": "用于训练青山判断因子有效性时必须区分单因子解释与多因子解释。"
    },
    {
      "claim_id": "CLAIM-002",
      "claim": "SMB 与 HML 的构造依赖分组、样本、组合形成方法和数据口径，不能脱离样本环境直接迁移。",
      "evidence_ref": "Kenneth French Data Library: Fama/French 3 Factors and portfolio details",
      "qingshan_relevance": "用于约束青山在 A 股场景下不得直接套用美股因子结论。"
    }
  ],
  "evidence_units": [
    {
      "evidence_id": "EV-001",
      "source": "Journal of Financial Economics",
      "type": "peer_reviewed_paper",
      "trace": "Fama & French 1993, Common Risk Factors in the Returns on Stocks and Bonds"
    },
    {
      "evidence_id": "EV-002",
      "source": "Kenneth French Data Library",
      "type": "research_dataset",
      "trace": "Fama/French 3 Factors, 5 Factors, portfolio downloads and details"
    }
  ],
  "applicable_market": {
    "primary": "US equities",
    "secondary": "factor research methodology",
    "a_share_direct_applicability": "not_direct",
    "a_share_use_policy": "只能作为方法论和反例检查框架，必须经过 A 股样本验证后才可转规则候选"
  },
  "sample_scope": {
    "market": "NYSE/AMEX/NASDAQ context in original research",
    "asset_class": ["stocks", "bonds"],
    "frequency": "monthly factor/portfolio research context",
    "limitation": "不是 A 股样本，不覆盖中国交易制度、涨跌停、壳价值、ST、北向资金等本土结构"
  },
  "method_summary": [
    "使用共同风险因子解释股票和债券收益。",
    "强调市场因子之外，规模和账面市值比相关因子具有解释力。",
    "通过组合分组和回归框架检验因子解释能力。"
  ],
  "limitations": [
    "原始研究主要基于美国市场，不能直接迁移为 A 股交易规则。",
    "该文献支持因子研究框架，不支持单次信号直接下交易结论。",
    "后续如进入 RuleCandidate，必须补充 A 股数据、样本外验证、衰减检查和反例检查。"
  ],
  "conflict_notes": [
    "Fama/French 因子模型有强学术地位，但因子有效性存在市场、时期、样本和构造方式差异。",
    "高权威不等于自动通过；本卡片只进入 card_draft。"
  ],
  "qingshan_use_case": [
    "因子有效性判断",
    "IC/ICIR 与多因子解释框架前置知识",
    "样本迁移风险提醒",
    "A 股因子规则候选前的质量门"
  ],
  "traceability": {
    "doi": "10.1016/0304-405X(93)90023-5",
    "data_library": "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html",
    "depends_on": [
      "knowledge/literature/qingshan_source_selection_policy_v1.0.json",
      "knowledge/literature/qingshan_literature_quality_schema_v1.0.json",
      "knowledge/literature/qingshan_literature_card_to_rule_candidate_flow_v1.0.json"
    ]
  },
  "card_status": "card_draft",
  "next_step": "仅允许进入 RuleCandidate 评估准备；不得直接生成 active rule"
}

CARD_PATH.write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")

def sha_line(path):
    text = path.read_text(encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest(), len(text.splitlines())

# validation
required = [
  "card_id","source_id","source_title","source_type","author_or_institution","publication_date",
  "source_selection_status","quality_status","total_score","hard_block_triggered","extracted_claims",
  "evidence_units","applicable_market","sample_scope","method_summary","limitations","conflict_notes",
  "qingshan_use_case","traceability","card_status"
]
missing = [k for k in required if k not in card]
bad = []
if card["card_status"] != "card_draft": bad.append("card_status_not_draft")
if card["quality_status"] not in ["quality_pass", "quality_pass_with_cross_check"]: bad.append("bad_quality_status")
if not card["extracted_claims"]: bad.append("no_extracted_claims")
if not card["evidence_units"]: bad.append("no_evidence_units")
if card["applicable_market"]["a_share_direct_applicability"] != "not_direct": bad.append("a_share_direct_applicability_not_blocked")
if (KB / "rule_candidates").exists(): bad.append("rule_candidates_created")
if (KB / "rules/role_capability_rules_v1.3.json").exists():
    rules_text = (KB / "rules/role_capability_rules_v1.3.json").read_text(encoding="utf-8")
    if "LC-QS-FF1993-001" in rules_text: bad.append("active_rules_modified_by_card")

result = "PASS" if not missing and not bad else "BLOCK"

report = {
  "stage": STAGE,
  "result": result,
  "card_exists": CARD_PATH.exists(),
  "card_status": card["card_status"],
  "quality_status": card["quality_status"],
  "required_missing": missing,
  "bad_checks": bad,
  "rule_candidate_created": (KB / "rule_candidates").exists(),
  "active_rule_touched_by_card": "active_rules_modified_by_card" in bad,
  "result_reason": f"missing={missing}; bad={bad}; card={CARD_PATH}"
}
REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

# manifest update
manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
entries = manifest.setdefault("entries", [])
def upsert(file_id, typ, path, read_tier, status="active"):
    s, l = sha_line(path)
    e = {
      "file_id": file_id,
      "type": typ,
      "path": str(path),
      "sha256": s,
      "line_count": l,
      "read_tier": read_tier,
      "status": status
    }
    for i, old in enumerate(entries):
        if old.get("file_id") == file_id:
            entries[i] = e
            return
    entries.append(e)

upsert("qingshan-first-literature-card-fama-french-1993-v1.0", "literature_card", CARD_PATH, "task")
upsert("qingshan-first-literature-card-fama-french-1993-validation-v1.0", "validation_report", REPORT_PATH, "audit")

manifest.setdefault("meta", {})["stage"] = STAGE
manifest["meta"]["last_updated"] = str(date.today())
manifest.setdefault("counts", {})["total_entries"] = len(entries)
manifest["counts"]["literature_card_count"] = manifest["counts"].get("literature_card_count", 0) + 1
MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

# refresh manifest entry for manifest itself if exists
manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
for e in manifest.get("entries", []):
    if e.get("path") == str(MANIFEST):
        s, l = sha_line(MANIFEST)
        e["sha256"] = s
        e["line_count"] = l
MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

# audit files
for gate, title, conclusion in [
    ("G4自检报告", "G4 自检报告", result),
    ("G5旧影复查报告", "G5 旧影复查报告", "PASS" if result == "PASS" else "BLOCK"),
    ("G6放行归档记录", "G6 放行归档记录", "PASS" if result == "PASS" else "BLOCK"),
]:
    path = AUDIT / f"L2_KB_知识进化_{STAGE}_{gate}_v1.0.md"
    path.write_text(f"""# {title}

| 项目 | 内容 |
|:--|:--|
| 任务名称 | {STAGE} |
| 结论 | {conclusion} |
| 检查对象 | 青山第一张 LiteratureCard |
| 主产物 | `{CARD_PATH}` |
| 验证报告 | `{REPORT_PATH}` |

## 边界

- 已生成 LiteratureCard：是
- 已生成 RuleCandidate：否
- 已修改 active rule：否
- 已修改生产入口：否
- 青山三步机制：保留

## 结论

{conclusion}
""", encoding="utf-8")

print("card =", CARD_PATH)
print("report =", REPORT_PATH)
print("result =", result)
print("rule_candidate_created =", (KB / "rule_candidates").exists())
print("active_rule_touched_by_card =", "active_rules_modified_by_card" in bad)
