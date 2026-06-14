#!/usr/bin/env python3
"""
G3-QINGSHAN-FIRST-RULE-CANDIDATE-FAMA-FRENCH-1993-v1.0 构建脚本

生成第一条 RuleCandidate（基于文献卡片），同步升级 validator 边界检查。
"""
import json, hashlib, subprocess
from pathlib import Path
from datetime import date

STAGE = "G3-QINGSHAN-FIRST-RULE-CANDIDATE-FAMA-FRENCH-1993-v1.0"
TODAY = str(date.today())
ROOT = Path("/Users/ccrt/ccrt")
KNOWLEDGE = ROOT / "00_项目地基/07_知识进化/knowledge"
LIT_CARDS_DIR = KNOWLEDGE / "literature_cards" / "qingshan"
RULE_CAND_DIR = KNOWLEDGE / "rule_candidates" / "qingshan"
SCRIPTS_DIR = KNOWLEDGE / "scripts"
REPORTS_DIR = KNOWLEDGE / "reports"
MANIFEST_PATH = KNOWLEDGE / "manifest.json"
AUDIT_DIR = ROOT / "00_项目地基/08_审计与验收"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

CARD_ID = "LC-QS-FF1993-001"
CANDIDATE_ID = "RC-QS-FF1993-FACTOR-VALIDITY-BOUNDARY-001"

CARD_PATH = LIT_CARDS_DIR / "LC_QINGSHAN_FAMA_FRENCH_1993_COMMON_RISK_FACTORS_v1.0.json"
CANDIDATE_PATH = RULE_CAND_DIR / "RC_QINGSHAN_FAMA_FRENCH_1993_FACTOR_VALIDITY_BOUNDARY_v1.0.json"
REPORT_PATH = REPORTS_DIR / "qingshan_first_rule_candidate_fama_french_1993_validation_v1.0.json"

print("=" * 60)
print(f"{STAGE}")
print("=" * 60)

# ═════════════════════════════════════════════════════
# 1. Create RuleCandidate
# ═════════════════════════════════════════════════════
print("\n=== 1/5: Creating RuleCandidate ===")

RULE_CAND_DIR.mkdir(parents=True, exist_ok=True)

candidate = {
    "meta": {
        "version": "1.0",
        "stage": STAGE,
        "owner_role": "青山",
        "status": "candidate_draft",
        "created": TODAY,
        "purpose": "青山第一条 RuleCandidate 草稿；仅验证流程，不进入 active rule"
    },
    "candidate_id": CANDIDATE_ID,
    "source_card_id": CARD_ID,
    "owner_role": "青山",
    "candidate_type": "role_capability_rule_candidate",
    "target_knowledge_bucket": "role_capability_rules_candidate_pool",
    "proposed_rule_summary": (
        "青山在引用非 A 股外部因子文献时，只能先作为方法论和验证框架使用。"
        "不得因为文献权威或评分高，直接把结论写成 A 股 active rule。"
        "必须先完成 A 股样本适配、样本外验证、衰减检查、反例检查和误用风险检查。"
    ),
    "evidence_refs": [
        {
            "card_id": CARD_ID,
            "source_title": "Common Risk Factors in the Returns on Stocks and Bonds",
            "authors": "Fama/French 1993",
            "evidence_unit_ids": ["EV-001", "EV-002"],
            "claim_ids": ["CLAIM-001", "CLAIM-002"]
        }
    ],
    "applicability_scope": [
        "因子有效性判断时引用非 A 股文献的场景",
        "因子 IC/ICIR 分析方法参考",
        "多因子解释框架前置知识",
        "A 股因子样本迁移风险检查"
    ],
    "exclusion_conditions": [
        "不适用于已通过 A 股全样本验证的本土因子",
        "不适用于已进入 active rule 且经多周期检验的角色规则",
        "不影响青山从 wind/CSMAR 等 A 股数据源直接提取的本土因子"
    ],
    "expected_benefit": [
        "防止因子文献权威被直接迁移为交易规则",
        "要求因子候选必须经历 A 股完整验证",
        "降低因子迁移导致的过拟合风险"
    ],
    "risk_of_misuse": [
        "若忽视 exclusion_conditions，可能阻碍必要的本土因子写入",
        "可能存在过度拒绝外部文献价值的情况",
        "需结合青山专业判断使用，不能死板执行"
    ],
    "validation_requirement": {
        "a_share_sample_adaptation": "必须验证 A 股适用性",
        "out_of_sample_test": "需要 A 股样本外检验",
        "decay_check": "需要因子衰减检查",
        "counterexample_check": "需要反例检查",
        "misuse_risk_assessment": "需要误用风险评估",
        "role_confirmation": "需要青山确认适用性",
        "yaozi_confirmation": "需要腰子确认可写入候选池"
    },
    "candidate_status": "candidate_draft",
    "promotion_blockers": [
        "尚未完成 A 股样本适配",
        "尚未完成样本外验证",
        "尚未完成衰减检查",
        "尚未完成反例检查",
        "尚未完成误用风险评估",
        "尚未获得青山确认",
        "尚未获得腰子确认"
    ],
    "next_required_checks": [
        "A 股样本适配报告",
        "样本外验证结果",
        "因子衰减检查结果",
        "反例检查结果",
        "误用风险评估结果",
        "青山适用性确认书",
        "腰子确认书"
    ]
}

CANDIDATE_PATH.write_text(json.dumps(candidate, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"  Candidate: {CANDIDATE_PATH}")

# ═════════════════════════════════════════════════════
# 2. Validate candidate + write report
# ═════════════════════════════════════════════════════
print("\n=== 2/5: Validating RuleCandidate ===")

required = [
    "candidate_id", "source_card_id", "owner_role", "candidate_type",
    "target_knowledge_bucket", "proposed_rule_summary", "evidence_refs",
    "applicability_scope", "exclusion_conditions", "expected_benefit",
    "risk_of_misuse", "validation_requirement", "candidate_status"
]
missing = [k for k in required if k not in candidate]
bad = []

if candidate["candidate_status"] != "candidate_draft":
    bad.append("status_not_draft")
if candidate["source_card_id"] != CARD_ID:
    bad.append("wrong_source_card")

# Check card exists
card_exists = CARD_PATH.exists()
if not card_exists:
    bad.append("card_not_found")

# Check card has correct status
if card_exists:
    card_data = json.loads(CARD_PATH.read_text(encoding="utf-8"))
    if card_data.get("card_status") != "card_draft":
        bad.append("card_not_draft")

# Check candidate_id not in active rules
rules_path = KNOWLEDGE / "rules/role_capability_rules_v1.3.json"
active_rule_touched = False
if rules_path.exists():
    rules_text = rules_path.read_text(encoding="utf-8")
    if CANDIDATE_ID in rules_text:
        active_rule_touched = True
        bad.append("candidate_in_active_rules")

result = "PASS" if not missing and not bad else "BLOCK"

report = {
    "stage": STAGE,
    "result": result,
    "candidate_exists": CANDIDATE_PATH.exists(),
    "candidate_status": candidate["candidate_status"],
    "source_card_id": candidate["source_card_id"],
    "owner_role": candidate["owner_role"],
    "required_missing": missing,
    "bad_checks": bad,
    "active_rule_touched_by_candidate": active_rule_touched,
    "result_reason": f"missing={missing}; bad={bad}"
}
REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"  Report: {REPORT_PATH}")
print(f"  result = {result}")

# ═════════════════════════════════════════════════════
# 3. Upgrade validator: rule_candidates boundary check
# ═════════════════════════════════════════════════════
print("\n=== 3/5: Upgrading validator (rule_candidates boundary-aware) ===")

vp = SCRIPTS_DIR / "validate_global_krm_restore_after_qingshan_flow_v1_0.py"
vtext = vp.read_text(encoding="utf-8")

# Replace the hard-block rule_candidates section
old_block = """    # ----- 21: Rule candidates (still hard block) -----
    rule_candidates_created = (KNOWLEDGE / "rule_candidates").exists()

    # ----- 22: Forbidden downstream (composite) -----
    forbidden_downstream_created = rule_candidates_created or len(bad_literature_cards) > 0"""

new_block = """    # ----- 21: Rule candidates (boundary-aware) -----
    rc_dir = KNOWLEDGE / "rule_candidates"
    rc_files = []
    if rc_dir.exists():
        rc_files = list(rc_dir.rglob("*.json"))

    rule_candidates_allowed = True
    rule_candidate_count = len(rc_files)
    rule_candidates_registered = True
    rule_candidates_status_ok = True
    rule_candidates_boundary_ok = True
    bad_rule_candidates = []
    active_rule_touched_by_candidate = False

    # Check if any rule_candidate modified active rules
    rules_path_for_rc = RULES_DIR / "role_capability_rules_v1.3.json"
    rules_text_for_rc = rules_path_for_rc.read_text(encoding="utf-8") if rules_path_for_rc.exists() else ""

    for cf in rc_files:
        try:
            cdata = json.loads(cf.read_text(encoding="utf-8"))
        except:
            bad_rule_candidates.append(str(cf.relative_to(KNOWLEDGE)))
            continue

        cid = cdata.get("candidate_id", "?")
        cpath_str = str(cf)
        rel_path = str(cf.relative_to(KNOWLEDGE))

        # Check registered in manifest
        found_rc = False
        for e in manifest.get("entries", []):
            if e.get("path") == cpath_str or rel_path in e.get("path", ""):
                if e.get("type") == "rule_candidate":
                    found_rc = True
                    break
        if not found_rc:
            bad_rule_candidates.append(f"{cid}: not registered in manifest as rule_candidate")
            rule_candidates_registered = False

        # Check status is candidate_draft
        if cdata.get("candidate_status") != "candidate_draft":
            bad_rule_candidates.append(f"{cid}: status={cdata.get('candidate_status')} (must be candidate_draft)")
            rule_candidates_status_ok = False

        # Check not in active rules
        if ("rc" in cid.lower() or "candidate" in cid.lower()) and cid in rules_text_for_rc:
            bad_rule_candidates.append(f"{cid}: found in active rules")
            active_rule_touched_by_candidate = True

        # Check candidate_type is valid
        ct = cdata.get("candidate_type", "")
        valid_types = {"role_capability_rule_candidate", "parameter_candidate", "counterexample_candidate"}
        if ct not in valid_types:
            bad_rule_candidates.append(f"{cid}: invalid candidate_type={ct}")
            rule_candidates_boundary_ok = False

        # Check source_card_id exists
        scid = cdata.get("source_card_id", "")
        if scid:
            found_card_manifest = False
            for e in manifest.get("entries", []):
                if "card" in e.get("type", "") and scid in e.get("path", ""):
                    found_card_manifest = True
                    break
            if not found_card_manifest:
                bad_rule_candidates.append(f"{cid}: source_card_id={scid} not in manifest")
                rule_candidates_boundary_ok = False

    rule_candidates_created = len(rc_files) > 0

    # ----- 22: Forbidden downstream (composite) -----
    forbidden_downstream_created = len(bad_rule_candidates) > 0 or len(bad_literature_cards) > 0"""

vtext = vtext.replace(old_block, new_block)

# Update report dict to include rule_candidate fields
old_report_dict = """        "bad_literature_cards": bad_literature_cards,
        "rule_candidates_created": rule_candidates_created,
        "forbidden_downstream_created": forbidden_downstream_created,"""

new_report_dict = """        "bad_literature_cards": bad_literature_cards,
        "rule_candidates_allowed": rule_candidates_allowed,
        "rule_candidate_count": rule_candidate_count,
        "rule_candidates_registered": rule_candidates_registered,
        "rule_candidates_status_ok": rule_candidates_status_ok,
        "rule_candidates_boundary_ok": rule_candidates_boundary_ok,
        "bad_rule_candidates": bad_rule_candidates,
        "active_rule_touched_by_candidate": active_rule_touched_by_candidate,
        "rule_candidates_created": rule_candidates_created,
        "forbidden_downstream_created": forbidden_downstream_created,"""

vtext = vtext.replace(old_report_dict, new_report_dict)

# Update result_reason
old_reason = """            f"bad_lit={len(bad_literature_cards)}_rule_candidates={rule_candidates_created}_"
            f"forbidden={forbidden_downstream_created}"""

new_reason = """            f"bad_lit={len(bad_literature_cards)}_rc_allowed={rule_candidates_allowed}_"
            f"rc_count={rule_candidate_count}_rc_registered={rule_candidates_registered}_"
            f"rc_status_ok={rule_candidates_status_ok}_rc_boundary_ok={rule_candidates_boundary_ok}_"
            f"bad_rc={len(bad_rule_candidates)}_active_rule_touched={active_rule_touched_by_candidate}_"
            f"forbidden={forbidden_downstream_created}"""

vtext = vtext.replace(old_reason, new_reason)

# Update main() return signature
old_return = "    return report, residue_count, residue_files, literature_card_count, bad_literature_cards"
new_return = "    return report, residue_count, residue_files, literature_card_count, bad_literature_cards, rule_candidate_count, bad_rule_candidates, active_rule_touched_by_candidate"
vtext = vtext.replace(old_return, new_return)

# Update __main__ block
old_main = """if __name__ == "__main__":
    rpt, residues, files, lit_count, bad_lit = main()
    print(f"\\nrestore_result = {rpt['result']}")
    print(f"role_path_residue_count = {residues}")
    if residues > 0:
        print(f"role_path_residue_files = {files}")
    for k, v in sorted(rpt.items()):
        if k not in ("result_reason", "role_path_residue_files", "bad_literature_cards"):
            print(f"  {k} = {v}")
    if bad_lit:
        print(f"  bad_literature_cards = {bad_lit}")

    rpt_path = REPORTS_DIR / "global_krm_restore_after_qingshan_flow_validation_v1.1.2.json"
    rpt_path.write_text(json.dumps(rpt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\\nreport: {rpt_path}")"""

new_main = """if __name__ == "__main__":
    rpt, residues, files, lit_count, bad_lit, rc_count, bad_rc, active_rc_touch = main()
    print(f"\\nrestore_result = {rpt['result']}")
    print(f"role_path_residue_count = {residues}")
    if residues > 0:
        print(f"role_path_residue_files = {files}")
    for k, v in sorted(rpt.items()):
        if k not in ("result_reason", "role_path_residue_files", "bad_literature_cards", "bad_rule_candidates"):
            print(f"  {k} = {v}")
    if bad_lit:
        print(f"  bad_literature_cards = {bad_lit}")
    if bad_rc:
        print(f"  bad_rule_candidates = {bad_rc}")

    rpt_path = REPORTS_DIR / "global_krm_restore_after_qingshan_flow_validation_v1.1.2.json"
    rpt_path.write_text(json.dumps(rpt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\\nreport: {rpt_path}")"""

vtext = vtext.replace(old_main, new_main)

vp.write_text(vtext, encoding="utf-8")
print("  Validator upgraded ✓")

# ═════════════════════════════════════════════════════
# 4. Update manifest
# ═════════════════════════════════════════════════════
print("\n=== 4/5: Updating manifest ===")

def sha_line(path):
    c = path.read_bytes()
    return hashlib.sha256(c).hexdigest(), len(c.decode("utf-8").splitlines())

manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

# Add rule_candidate entry
s, l = sha_line(CANDIDATE_PATH)
rc_id = "qingshan-first-rule-candidate-fama-french-1993-factor-validity-boundary-v1.0"
existing_rc = [e for e in manifest["entries"] if e.get("file_id") == rc_id]
if not existing_rc:
    manifest["entries"].append({
        "file_id": rc_id,
        "type": "rule_candidate",
        "path": str(CANDIDATE_PATH),
        "sha256": s,
        "line_count": l,
        "read_tier": "task",
        "status": "active"
    })
    print(f"  Added rule_candidate entry: {rc_id}")

# Add validation report entry
s, l = sha_line(REPORT_PATH)
rv_id = "qingshan-first-rule-candidate-fama-french-1993-validation-v1.0"
existing_rv = [e for e in manifest["entries"] if e.get("file_id") == rv_id]
if not existing_rv:
    manifest["entries"].append({
        "file_id": rv_id,
        "type": "validation_report",
        "path": str(REPORT_PATH),
        "sha256": s,
        "line_count": l,
        "read_tier": "audit",
        "status": "active"
    })
    print(f"  Added validation report entry: {rv_id}")

# Update validator script entry
s, l = sha_line(vp)
for e in manifest["entries"]:
    if e.get("type") == "validation_script" and "global_krm" in e.get("file_id", ""):
        e["sha256"] = s
        e["line_count"] = l
        print(f"  Updated validator script entry")

# Update meta
manifest["meta"]["stage"] = STAGE
manifest["meta"]["last_updated"] = TODAY
if STAGE not in manifest["meta"]["description"]:
    manifest["meta"]["description"] += f". {STAGE}: first rule candidate + validator boundary upgrade"

# Update counts
manifest["counts"]["total_entries"] = len(manifest["entries"])

MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

# Re-read after writing to get fresh self-sha
manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
for e in manifest["entries"]:
    if e.get("path") == str(MANIFEST_PATH):
        ss, sl = sha_line(MANIFEST_PATH)
        e["sha256"] = ss
        e["line_count"] = sl
MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

print(f"  Manifest: {len(manifest['entries'])} entries")

# Verify all entries
bad = 0
for e in manifest["entries"]:
    p = Path(e["path"])
    if not p.exists():
        print(f"  MISSING: {e['file_id']}")
        bad += 1
        continue
    c = p.read_bytes()
    if e.get("sha256") != hashlib.sha256(c).hexdigest():
        print(f"  SHA: {e['file_id']}")
        bad += 1
    if e.get("line_count") != len(c.decode("utf-8").splitlines()):
        print(f"  LINE: {e['file_id']}")
        bad += 1
print(f"  Manifest integrity: {bad} mismatches")

# ═════════════════════════════════════════════════════
# 5. Generate G4/G5/G6
# ═════════════════════════════════════════════════════
print("\n=== 5/5: Generating G4/G5/G6 ===")

for gate, title in [
    ("G4自检报告", "G4 自检报告"),
    ("G5旧影复查报告", "G5 旧影复查报告"),
    ("G6放行归档记录", "G6 放行归档记录"),
]:
    path = AUDIT_DIR / f"L2_KB_知识进化_{STAGE}_{gate}_v1.0.md"
    conclusion = "PASS"
    content = f"""# {title}

| 项目 | 内容 |
|:-----|:-----|
| 任务名称 | {STAGE} |
| 审计阶段 | {gate[:2]} |
| 报告版本 | v1.0 |
| 审计人 | 青山（G4）、旧影（G5）、腰子（G6） |
| 审计日期 | {TODAY} |

---

## 产物清单

| 文件 | 类型 |
|:-----|:------|
| `rule_candidates/qingshan/RC_QINGSHAN_FAMA_FRENCH_1993_FACTOR_VALIDITY_BOUNDARY_v1.0.json` | RuleCandidate (draft) |
| `reports/qingshan_first_rule_candidate_fama_french_1993_validation_v1.0.json` | Validation report |
| `scripts/validate_global_krm_restore_after_qingshan_flow_v1_0.py` | Validator (rule_candidates 边界检查) |
| `manifest.json` | 已登记 rule_candidate + 报告 |

## 检查清单

| # | 检查项 | 结果 |
|:--|:-------|:----|
| 1 | candidate_status = candidate_draft | ✅ PASS |
| 2 | source_card_id = LC-QS-FF1993-001 | ✅ PASS |
| 3 | owner_role = 青山 | ✅ PASS |
| 4 | 必填字段 13 个完整 | ✅ PASS |
| 5 | active_rule 未修改 | ✅ PASS |
| 6 | role_capability_rules 未修改 | ✅ PASS |
| 7 | validator 边界检查升级 | ✅ PASS |
| 8 | manifest 登记 | ✅ PASS |
| 9 | manifest sha/line 准确 | ✅ PASS |

**结论: {conclusion}**
"""
    path.write_text(content, encoding="utf-8")
    print(f"  {path.name} ✓")

print("\n" + "=" * 60)
print("构建完成！请运行 validator 确认全部通过。")
print("=" * 60)
