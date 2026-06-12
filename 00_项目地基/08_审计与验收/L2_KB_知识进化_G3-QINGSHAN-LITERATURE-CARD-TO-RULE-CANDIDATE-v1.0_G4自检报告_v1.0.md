# G4 自检报告

| 项目 | 内容 |
|:-----|:-----|
| 任务名称 | G3-QINGSHAN-LITERATURE-CARD-TO-RULE-CANDIDATE-v1.0 |
| 审计阶段 | G4 自检 |
| 报告版本 | v1.0 |
| 审计人 | 青山 |
| 审计日期 | 2026-06-11 |
| 流程类型 | F-GATE / F-FIX |
| 前驱 | G3-QINGSHAN-LITERATURE-QUALITY-SCORING-v1.0 ✅ PASS |

---

## 检查清单

### 1. 主流程文件完整性

| # | 检查项 | 结果 | 说明 |
|:--|:-------|:----|:-----|
| 1.1 | 主流程 JSON 存在且可解析 | ✅ PASS | `qingshan_literature_card_to_rule_candidate_flow_v1.0.json` |
| 1.2 | depends_on 指向 source selection policy | ✅ PASS | 文件存在 |
| 1.3 | depends_on 指向 quality schema | ✅ PASS | 文件存在 |
| 1.4 | 校验脚本存在 | ✅ PASS | `validate_qingshan_literature_card_to_rule_candidate_flow_v1_0.py` |
| 1.5 | 校验报告已生成且 result=PASS | ✅ PASS | 已运行 |

### 2. LiteratureCard 字段完整性

| # | 检查项 | 结果 | 说明 |
|:--|:-------|:----|:-----|
| 2.1 | 必填字段完整（20个） | ✅ PASS | card_id/source_id/source_title/source_type/author_or_institution/publication_date/source_selection_status/quality_status/total_score/hard_block_triggered/extracted_claims/evidence_units/applicable_market/sample_scope/method_summary/limitations/conflict_notes/qingshan_use_case/traceability/card_status |
| 2.2 | 初始状态为 card_draft | ✅ PASS | |

### 3. RuleCandidate 字段完整性

| # | 检查项 | 结果 | 说明 |
|:--|:-------|:----|:-----|
| 3.1 | 必填字段完整（13个） | ✅ PASS | candidate_id/source_card_id/owner_role/candidate_type/target_knowledge_bucket/proposed_rule_summary/evidence_refs/applicability_scope/exclusion_conditions/expected_benefit/risk_of_misuse/validation_requirement/candidate_status |
| 3.2 | 初始状态为 candidate_draft | ✅ PASS | |

### 4. 允许生成规则候选条件

| # | 检查项 | 结果 | 说明 |
|:--|:-------|:----|:-----|
| 4.1 | ALLOW-001 ~ 010 完整 | ✅ PASS | 10 条条件完整 |

### 5. 禁止生成规则候选条件

| # | 检查项 | 结果 | 说明 |
|:--|:-------|:----|:-----|
| 5.1 | BLOCK-001 ~ 010 完整 | ✅ PASS | 10 条条件完整 |

### 6. 分流规则完整

| # | 检查项 | 结果 | 说明 |
|:--|:-------|:----|:-----|
| 6.1 | 5 种分流目标完整 | ✅ PASS | role_capability_rules / parameter_candidate / counterexample_candidate / literature_background / reject_or_hold |

### 7. 红线完整

| # | 检查项 | 结果 | 说明 |
|:--|:-------|:----|:-----|
| 7.1 | RL-001 ~ 007 完整 | ✅ PASS | 7 条红线 |

### 8. Anti Overreach

| # | 检查项 | 结果 | 说明 |
|:--|:-------|:----|:-----|
| 8.1 | 8 项全部 true | ✅ PASS | |

### 9. 未创建下游真实实例

| # | 检查项 | 结果 | 说明 |
|:--|:-------|:----|:-----|
| 9.1 | 无真实 literature_cards | ✅ PASS | |
| 9.2 | 无真实 rule_candidates | ✅ PASS | |

### 10. 联动修复验证

| # | 检查项 | 结果 | 说明 |
|:--|:-------|:----|:-----|
| 10.1 | quality validation result_reason 已修复 | ✅ PASS | 不再出现 applied_rule_present=True |
| 10.2 | manifest sha/line 准确 | ✅ PASS | 已重算 |

### 11. 未改禁止范围

| # | 检查项 | 结果 | 说明 |
|:--|:-------|:----|:-----|
| 11.1 | 未改 .claude/agents/*.md | ✅ PASS | |
| 11.2 | 未改 production 入口 | ✅ PASS | |
| 11.3 | 未改角色核心规则 | ✅ PASS | |

---

## 总结

| 维度 | 结果 |
|:-----|:-----|
| 主流程文件完整性 | ✅ PASS |
| LiteratureCard 字段 | ✅ PASS |
| RuleCandidate 字段 | ✅ PASS |
| 允许/禁止条件 | ✅ PASS |
| 分流规则 | ✅ PASS |
| 红线 | ✅ PASS |
| Anti Overreach | ✅ PASS |
| 联动修复 | ✅ PASS |
| 禁止修改范围 | ✅ PASS |

**G4 结论：✅ PASS — 主流程 JSON 格式与字段完整，联动修复完成，可以进入 G5 旧影复查。**
