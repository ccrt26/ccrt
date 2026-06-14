# G5 旧影复查报告

| 项目 | 内容 |
|:-----|:-----|
| 任务名称 | G3-QINGSHAN-LITERATURE-CARD-TO-RULE-CANDIDATE-v1.0 |
| 审计阶段 | G5 旧影复查 |
| 报告版本 | v1.0 |
| 审计人 | 旧影 |
| 审计日期 | 2026-06-11 |
| 流程类型 | F-GATE / F-FIX |
| 前驱 | G4 自检 ✅ PASS |

---

## 复查主题

### 1. 是否建立了完整的 LiteratureCard → RuleCandidate 流程？

**结论：✅ 已建立。**

- 定义了 **LiteratureCard 20 个必填字段**，覆盖来源追溯、质量评分引用、证据抽取、市场/样本/方法摘要、限制条件、冲突说明、可用性和追踪链
- 定义了 **RuleCandidate 13 个必填字段**，覆盖来源卡片追溯、角色归属、候选类型、目标知识桶、规则摘要、证据引用、适用/排除范围、预期收益、滥用风险和验证要求
- 定义了 **10 条允许生成条件**，确保任何规则候选必须达到最低证据和适用性门槛
- 定义了 **10 条禁止生成条件**，涵盖质量拒绝、背景仅参、无方法、强泛化、交易红线、核心知识库等多种阻断场景
- 定义了 **5 类分流规则**，根据资料性质导向不同候选类型

### 2. 是否防止高分/权威资料绕过流程？

**结论：✅ 已防止。**

- RL-004 "不得因为权威来源自动通过"
- RL-005 "不得因为高评分自动通过"
- RL-006 "不得绕过项目内验证"
- BLOCK-001 ~ BLOCK-010 阻断机制独立于评分
- anti_overreach 中有 `no_auto_pass_for_authority` 和 `no_auto_pass_for_high_score`

### 3. 是否保持"中间层"（source_candidate → literature_card → rule_candidate）？

**结论：✅ 已保持。**

- input_objects 明确接受 source_candidate + quality_score_result
- LiteratureCard 的 `required_fields` 包含 `source_selection_status` 和 `quality_status`，追溯前两阶段结果
- RuleCandidate 的 `required_fields` 包含 `source_card_id`，追溯文献卡片
- 初始状态均为 `_draft`，不直接进入 active 状态

**完整通路：**
> source → source_selection_policy → source_candidate → quality_schema → quality_pass → literature_card (draft) → rule_candidate (draft) → project_validation → active_rule

### 4. 联动修复是否完成？

**结论：✅ 已修复。**

- quality validation 的 result_reason 中 `applied_rule_present=True` 已改为 `forbidden_output_guard_ok=True`
- manifest 中 quality validation 报告和脚本的 sha/line 已重算
- meta description 已追加第三步信息

### 5. 是否建议通过？

**结论：✅ 建议通过。**

全部检查通过：
- 流程 JSON 可解析，字段完整
- LiteratureCard 20 字段 / RuleCandidate 13 字段均完整
- 允许条件 10 条 / 禁止条件 10 条 / 红线 7 条 / 分流 5 类完整
- anti_overreach 8 项全部 true
- 联动修复完成
- 未创建真实实例

---

## 综合评估

| 复查维度 | 结果 |
|:---------|:-----|
| 流程完整性 | ✅ PASS |
| 防越界 | ✅ PASS |
| 中间层保持 | ✅ PASS |
| 联动修复 | ✅ PASS |

**G5 结论：✅ PASS — 流程设计完整，联动修复合规。建议进入 G6 放行。**
