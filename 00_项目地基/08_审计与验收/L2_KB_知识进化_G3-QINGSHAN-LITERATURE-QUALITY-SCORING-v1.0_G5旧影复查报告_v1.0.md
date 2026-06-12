# G5 旧影复查报告

| 项目 | 内容 |
|:-----|:-----|
| 任务名称 | G3-QINGSHAN-LITERATURE-QUALITY-SCORING-v1.0 |
| 审计阶段 | G5 旧影复查 |
| 报告版本 | v1.0 |
| 审计人 | 旧影 |
| 审计日期 | 2026-06-11 |
| 流程类型 | F-ARCH |
| 前驱 | G4 自检 ✅ PASS |

---

## 复查主题

### 1. schema 是否真正解决"候选资料质量如何判断"的问题？

**结论：✅ 已解决。**

检查评估：
- 定义了 **6 维评分模型**（authority 20% + replicability 20% + market_fit 15% + recency 10% + conflict_risk 15% + rule_convertibility 20%），覆盖了资料可信度、适用性、时效性和可转化性的全部关键维度
- 每维有 **5 档 scoring_rules**，从高分到低分有明确的 condition 描述，可操作性强
- **总分 100 分**，分 4 个决策区间（pass / cross_check / background / reject），边界清晰
- **4 条 hard_blocks** 在评分前拦截不符合基本条件的资料（职责外、来源不清、直接要求 applied、无方法无样本）
- **output_schema** 定义了评分输出必填字段，确保评分结果结构一致

**机制分析：**
> 以前：source_candidate 只靠来源分类（S/A/B/C/D）隐式判断质量。
> 现在：每个 candidate 通过 6 维评分 + hard_blocks 两阶段评估，得出明确的 quality_status 和流向（create_literature_card_candidate / background / reject）。
> 高分（≥75）进入文献卡片候选，中分（60-74）需交叉验证，低分（40-59）仅背景参考，低于 40 拒绝。

### 2. 是否防止高分资料直接变成 applied 规则？

**结论：✅ 已防止。**

三层防御：
1. **status_decision 层**：`quality_pass` 明确 `can_generate_rule_candidate: false`，note 注明"只能进入文献卡片候选，不得直接生成规则"
2. **anti_overreach 层**：`no_direct_applied_rule: true` + `no_direct_rule_candidate: true`
3. **scope.not_allowed_output 层**：明确禁止 `applied_rule`、`rule_candidate`、`parameter_update`、`core_knowledge_update`

即使资料评分 100 分，也必须经过文献卡片 → 规则候选 → 项目验证的完整流程。

### 3. 是否保留 source_candidate → 文献卡片的中间层？

**结论：✅ 已保留。**

- `quality_pass` 的 `next_step` 为 `create_literature_card_candidate`——不是直接创建文献卡片，而是创建"文献卡片候选"
- `quality_pass_with_cross_check` 的 `next_step` 为 `create_literature_card_candidate_after_cross_check`——交叉验证后才能进入
- 评分输出不产生文献卡片，只决定是否进入文献卡片候选流程

**通道路径：**
> source_candidate → (准入规则检查) → source_candidate_with_status → (质量评分) → quality_pass → create_literature_card_candidate → (未来阶段) → literature_card → rule_candidate → project_validation

### 4. 是否与第一步 source selection policy 衔接？

**结论：✅ 已衔接。**

衔接方式：
- `depends_on` 明确指向 `qingshan_source_selection_policy_v1.0.json`，声明依赖关系
- `scope.input_status` 接受 4 种输入状态：`source_candidate`、`source_candidate_with_cross_check`、`source_candidate_low_confidence`、`background_only`——这些状态正是第一步 policy 的 `decision_output.accepted_status`
- 第一步的 8 个 preferred_candidate 通过准入规则后获得 `source_candidate` 状态，然后进入本 schema 评分
- 第一步的 6 个 `score_dimensions_for_next_stage`（authority/replicability/market_fit/recency/conflict_risk/rule_convertibility）与本次 6 个评分维度完全一致

### 5. 是否建议进入第三步：青山文献卡片 → 规则候选流程？

**结论：✅ 强烈建议进入第三步。**

理由：
1. 本阶段已产出评分结果，下一步需要将 `quality_pass` 的结果转化为正式的 literature_card
2. 目前的 `next_step`（`create_literature_card_candidate`）是占位指引，需要实际流程实现
3. 文献卡片模板、卡片内容结构、规则候选推导规则尚未定义
4. 第三阶段需要定义：文献卡片 schema → 规则候选推导规则 → 项目验证触发条件

---

## 综合评估

| 复查维度 | 结果 |
|:---------|:-----|
| 质量判断能力 | ✅ PASS — 6 维评分可操作 |
| 防直接应用 | ✅ PASS — 三层防御 |
| 中间层保留 | ✅ PASS — 文献卡片候选层 |
| 与第一步衔接 | ✅ PASS — input_status 和维度完全对齐 |
| 下一阶段建议 | ✅ 建议进入文献卡片 → 规则候选流程 |

**G5 结论：✅ PASS — 质量评分 schema 设计完整，与第一步衔接良好。建议进入第三步：青山文献卡片 → 规则候选流程。**
