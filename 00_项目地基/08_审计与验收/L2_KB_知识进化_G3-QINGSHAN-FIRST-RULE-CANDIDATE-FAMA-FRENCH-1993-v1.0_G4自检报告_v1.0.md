# G4 自检报告

| 项目 | 内容 |
|:-----|:-----|
| 任务名称 | G3-QINGSHAN-FIRST-RULE-CANDIDATE-FAMA-FRENCH-1993-v1.0 |
| 审计阶段 | G4 |
| 报告版本 | v1.0 |
| 审计人 | 青山（G4）、旧影（G5）、腰子（G6） |
| 审计日期 | 2026-06-11 |

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

**结论: PASS**
