# G5 旧影复查报告

| 项目 | 内容 |
|:-----|:-----|
| 任务名称 | G3-QINGSHAN-SOURCE-SELECTION-v1.0 |
| 审计阶段 | G5 旧影复查 |
| 报告版本 | v1.0 |
| 审计人 | 旧影 |
| 审计日期 | 2026-06-11 |
| 流程类型 | F-ARCH |
| 前驱 | G4 自检 ✅ PASS |

---

## 复查主题

### 1. 是否解决"来源不能写死"的问题？

**结论：✅ 已解决。**

检查评估：
- `selection_principle.primary_rule` 明确声明"来源准入规则优先于候选池；候选池不是白名单，不构成唯一允许来源"
- `selection_principle.candidate_pool_usage` 声明"候选池只作为优先检查入口，任何候选仍需通过准入规则"
- 所有 preferred source 均标注 `not_exclusive: true`
- 校验脚本和 G4 检查均已验证无 `only_allowed` / `whitelist_only` / `exclusive: true` 关键词
- 准入规则（must_have_gates）是独立于候选池的，新的来源即使不在候选池中，只要能通过 gate 检查即可成为 source_candidate

**机制分析：**
> 候选池（preferred_candidate_pool）提供"优先检查入口"，但所有来源最终必须通过 must_have_gates（QS-SRC-GATE-001~005）的校验。
> 新的权威来源只要能通过 gate 校验即可自动成为 source_candidate，不需要修改候选池。
> 这种设计确保了候选池是推荐的而非排他的。

### 2. 是否保留新增权威来源的开放入口？

**结论：✅ 已保留。**

- `must_have_gates` 是通用准入规则，不是封闭列表，不限制来源类型
- `source_classes` 定义了 S/A/B/C/D 五级分类，新来源可映射到对应分类
- `decision_output.accepted_status` 定义了四种接受状态，给不同可信度来源开放了入口
- 候选池不要求修改 policy JSON 即可接纳新来源（通过准入规则即可）

**潜在增强建议（非本阶段要求）：**
- 未来可在 `source_classes` 中增加新的 class，如混合类型或规则推导源
- 候选池可定期复审和扩充

### 3. 是否防止个人/机构资料直接入规则？

**结论：✅ 已防止。**

四级防御：
1. **源头防御**：`selection_principle.direct_rule_application` 明确声明"禁止外部资料直接成为 applied 规则"
2. **分类防御**：C 类（个人研究/博客/开源项目）仅允许 `source_candidate_low_confidence`，且明确 `cannot_directly_generate_rule`
3. **门禁防御**：QS-SRC-GATE-005 "任何外部资料不得直接写入 applied 规则"（`block_if_missing: true`）
4. **流程防御**：D 类（观点型）仅允许 `background_only`，且明确 `cannot_generate_rule_candidate`
5. **阶段防御**：`decision_output.next_required_stage` 指向"文献质量评分"阶段，意味着 source_candidate 还必须经过评分才能进入文献卡片

### 4. 是否符合青山职责？

**结论：✅ 符合。**

- `scope.applies_to` 覆盖青山核心职责：因子有效性、IC/ICIR、样本外检验、过拟合防范、因子衰减、市场状态、A股因子实证、技术信号胜率验证
- `scope.not_applies_to` 排除非青山职责：直接投资建议、仓位动作、最终裁决
- 职责范围与方法论定位（因子研究、策略研究）完全匹配
- 预定义的 `score_dimensions_for_next_stage`（authority/replicability/market_fit/recency/conflict_risk/rule_convertibility）符合量化研究员视角

### 5. 是否建议进入第二步：青山文献质量评分 schema？

**结论：✅ 强烈建议进入 G3-LITERATURE-QUALITY-SCORING 阶段。**

理由：
1. 本阶段仅做了来源准入规则和候选池，未定义任何质量评分机制
2. `decision_output.next_required_stage` 已指向 `qingshan_literature_quality_scoring_v1.0`
3. `score_dimensions_for_next_stage` 已预定义 6 个评分维度（authority/replicability/market_fit/recency/conflict_risk/rule_convertibility），为下一阶段做好了接口准备
4. 目前 source_candidate → applied 规则之间缺少正式的质量评分模型

---

## 综合评估

| 复查维度 | 结果 |
|:---------|:-----|
| 来源不写死 | ✅ PASS |
| 新增来源开放入口 | ✅ PASS |
| 直接应用防御 | ✅ PASS |
| 青山职责匹配 | ✅ PASS |
| 下一阶段建议 | ✅ 建议进入文献质量评分阶段 |

**G5 结论：✅ PASS — 资源选择机制设计合理，符合青山职责。建议进入下一阶段：qingshan_literature_quality_scoring_v1.0。**
