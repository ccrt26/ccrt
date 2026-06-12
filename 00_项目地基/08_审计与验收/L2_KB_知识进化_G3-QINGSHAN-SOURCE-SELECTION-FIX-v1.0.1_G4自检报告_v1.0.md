# G4 自检报告 (修正 v1.0.1)

| 项目 | 内容 |
|:-----|:-----|
| 任务名称 | G3-QINGSHAN-SOURCE-SELECTION-FIX-v1.0.1 |
| 审计阶段 | G4 自检 |
| 报告版本 | v1.0.1 |
| 审计人 | 青山 |
| 审计日期 | 2026-06-11 |
| 流程类型 | F-ARCH |
| 修正范围 | validation 字段语义 + G6 放行人口径 |

---

## 修正内容说明

本次修正不涉及 policy JSON 变更，仅修复以下两项：

1. **validation 字段语义修复**：`bad_direct_application_policy` 不再承载 PASS 证据对象；通过时输出 `[]` 并新增 `direct_application_policy_ok: true` 布尔字段。
2. **G6 放行人口径修正**：原 G6 误写为"新安放行"，修正为腰子 G6 放行口径。

---

## 检查清单

### 1. 文件完整性

| # | 检查项 | 结果 | 说明 |
|:--|:-------|:----|:-----|
| 1.1 | policy JSON 未修改 | ✅ PASS | `qingshan_source_selection_policy_v1.0.json` 内容与原版一致 |
| 1.2 | 校验报告重新生成 | ✅ PASS | `reports/qingshan_source_selection_validation_v1.0.json` result=PASS |
| 1.3 | 校验脚本已修改 | ✅ PASS | 字段语义修复完成 |

### 2. 字段语义修复验证

| # | 检查项 | 结果 | 说明 |
|:--|:-------|:----|:-----|
| 2.1 | validation result = PASS | ✅ PASS | 脚本重新运行输出 PASS |
| 2.2 | bad_direct_application_policy = [] | ✅ PASS | 通过时不再是证据对象 |
| 2.3 | direct_application_policy_ok = true | ✅ PASS | 新增布尔字段 |
| 2.4 | 输出规范可程序解析 | ✅ PASS | `[]` + `true` 为确定性类型 |

### 3. 不是白名单

| # | 检查项 | 结果 | 说明 |
|:--|:-------|:----|:-----|
| 3.1 | selection_principle 声明"候选池不是白名单" | ✅ PASS | 不涉及 policy 变更 |
| 3.2 | 无 only_allowed / whitelist_only | ✅ PASS | 不涉及 policy 变更 |
| 3.3 | 每个 preferred source 的 not_exclusive=true | ✅ PASS | 不涉及 policy 变更 |

### 4. 来源分类完整性

| # | 检查项 | 结果 | 说明 |
|:--|:-------|:----|:-----|
| 4.1 | source_classes 包含 S/A/B/C/D (5 个) | ✅ PASS | 不涉及 policy 变更 |

### 5. 门禁完整性

| # | 检查项 | 结果 | 说明 |
|:--|:-------|:----|:-----|
| 5.1 | must_have_gates 5 条完整 | ✅ PASS | 不涉及 policy 变更 |
| 5.2 | QS-SRC-GATE-005 禁止直接 applied | ✅ PASS | 不涉及 policy 变更 |

### 6. 未创建下游文件

| # | 检查项 | 结果 | 说明 |
|:--|:-------|:----|:-----|
| 6.1 | 未创建 literature_cards 文件 | ✅ PASS | literature 目录无相关文件 |
| 6.2 | 未创建 rule_candidates 文件 | ✅ PASS | literature 目录无相关文件 |

### 7. 外部文件一致性

| # | 检查项 | 结果 | 说明 |
|:--|:-------|:----|:-----|
| 7.1 | manifest 已更新 sha/line | ✅ PASS | validation report 和 script 的 sha256/line_count 已重算 |
| 7.2 | router 未修改 | ✅ PASS | 本次修正不涉及 router |

### 8. 未修改禁止范围

| # | 检查项 | 结果 | 说明 |
|:--|:-------|:----|:-----|
| 8.1 | 未改 .claude/agents/*.md | ✅ PASS | 未涉及 |
| 8.2 | 未改 .claude/agents/*-知识库/ | ✅ PASS | 未涉及 |
| 8.3 | 未改 role_capability_rules | ✅ PASS | 未涉及 |
| 8.4 | 未改 production 入口 | ✅ PASS | 未涉及 |

---

## 总结

| 维度 | 结果 |
|:-----|:-----|
| 字段语义修复 | ✅ PASS |
| 文件完整性 | ✅ PASS |
| 白名单防御 | ✅ PASS |
| 下游文件保护 | ✅ PASS |
| 禁止修改范围 | ✅ PASS |

**G4 结论：✅ PASS — 字段语义修复完成，可以进入 G5 旧影复查。**
