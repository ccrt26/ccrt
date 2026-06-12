# G4 自检报告

| 项目 | 内容 |
|:-----|:-----|
| 任务名称 | G3-QINGSHAN-SOURCE-SELECTION-v1.0 |
| 审计阶段 | G4 自检 |
| 报告版本 | v1.0 |
| 审计人 | 青山 |
| 审计日期 | 2026-06-11 |
| 流程类型 | F-ARCH |
| 前驱 | G3 → 文件创建完成 |

---

## 检查清单

### 1. 文件完整性

| # | 检查项 | 结果 | 说明 |
|:--|:-------|:----|:-----|
| 1.1 | policy JSON 存在且可解析 | ✅ PASS | `literature/qingshan_source_selection_policy_v1.0.json` 存在，JSON 语法正确 |
| 1.2 | 校验报告存在且解析正确 | ✅ PASS | `reports/qingshan_source_selection_validation_v1.0.json` 存在，result=PASS |
| 1.3 | 校验脚本存在 | ✅ PASS | `scripts/validate_qingshan_source_selection_v1_0.py` 存在且可执行 |

### 2. 不是白名单

| # | 检查项 | 结果 | 说明 |
|:--|:-------|:----|:-----|
| 2.1 | selection_principle 声明"候选池不是白名单" | ✅ PASS | `candidate_pool_usage` 明确声明 |
| 2.2 | 无 only_allowed 关键词 | ✅ PASS | 校验脚本确认无此关键词 |
| 2.3 | 无 whitelist_only 关键词 | ✅ PASS | 校验脚本确认无此关键词 |
| 2.4 | 每个 preferred source 的 not_exclusive=true | ✅ PASS | 全部 8 条均为 true |

### 3. 来源分类完整性

| # | 检查项 | 结果 | 说明 |
|:--|:-------|:----|:-----|
| 3.1 | source_classes 包含 S | ✅ PASS | 官方/一手/可复现权威源 |
| 3.2 | source_classes 包含 A | ✅ PASS | 高质量学术/专业研究源 |
| 3.3 | source_classes 包含 B | ✅ PASS | 机构研究/数据库说明/券商深度 |
| 3.4 | source_classes 包含 C | ✅ PASS | 个人研究/博客/开源项目 |
| 3.5 | source_classes 包含 D | ✅ PASS | 观点型/不可复现/营销材料 |

### 4. 门禁完整性

| # | 检查项 | 结果 | 说明 |
|:--|:-------|:----|:-----|
| 4.1 | 至少 5 条 must_have_gates | ✅ PASS | 5 条（QS-SRC-GATE-001 ~ 005） |
| 4.2 | 每条有 gate_id | ✅ PASS | 全部存在 |
| 4.3 | 每条有 name | ✅ PASS | 全部存在 |
| 4.4 | 每条有 rule | ✅ PASS | 全部存在 |
| 4.5 | 每条有 block_if_missing | ✅ PASS | 全部存在且为 true |

### 5. 候选池完整性

| # | 检查项 | 结果 | 说明 |
|:--|:-------|:----|:-----|
| 5.1 | 至少 8 条 preferred source | ✅ PASS | 8 条（QS-SRC-PREF-001 ~ 008） |
| 5.2 | 每条有 source_id | ✅ PASS | 全部存在 |
| 5.3 | 每条有 name | ✅ PASS | 全部存在 |
| 5.4 | 每条有 class_hint | ✅ PASS | 全部存在 |
| 5.5 | 每条有 source_type | ✅ PASS | 全部存在 |
| 5.6 | 每条有 why_preferred | ✅ PASS | 全部存在 |
| 5.7 | 每条有 allowed_use | ✅ PASS | 全部存在 |
| 5.8 | 每条有 not_allowed_use | ✅ PASS | 全部存在 |

### 6. 禁止直接应用

| # | 检查项 | 结果 | 说明 |
|:--|:-------|:----|:-----|
| 6.1 | selection_principle 包含"applied" | ✅ PASS | `direct_rule_application` 明确声明 |
| 6.2 | QS-SRC-GATE-005 明确禁止 | ✅ PASS | gate 名称"不得直接应用" |

### 7. 未创建下游文件

| # | 检查项 | 结果 | 说明 |
|:--|:-------|:----|:-----|
| 7.1 | 未创建 literature_cards 文件 | ✅ PASS | literature 目录无相关文件 |
| 7.2 | 未创建 rule_candidates 文件 | ✅ PASS | literature 目录无相关文件 |

### 8. 外部文件完整性

| # | 检查项 | 结果 | 说明 |
|:--|:-------|:----|:-----|
| 8.1 | manifest.json 已更新 | ✅ PASS | 含 policy + report + script 三条 entries |
| 8.2 | manifest sha256 准确 | ✅ PASS | 已校验 |
| 8.3 | manifest line_count 准确 | ✅ PASS | 已校验 |
| 8.4 | router optional_read 已更新 | ✅ PASS | signal_validity_issue 路由已配置 |
| 8.5 | policy 不在 must_read 中 | ✅ PASS | 仅 optional_read |

### 9. 未修改禁止范围

| # | 检查项 | 结果 | 说明 |
|:--|:-------|:----|:-----|
| 9.1 | 未改 .claude/agents/*.md | ✅ PASS | 未涉及 |
| 9.2 | 未改 .claude/agents/*-知识库/ | ✅ PASS | 未涉及 |
| 9.3 | 未改 production 入口 | ✅ PASS | 未涉及 |

### 10. 特殊约束

| # | 检查项 | 结果 | 说明 |
|:--|:-------|:----|:-----|
| 10.1 | meta.version = 1.0 | ✅ PASS | 确认 |
| 10.2 | owner_role = 青山 | ✅ PASS | 确认 |
| 10.3 | decision_output 完整 | ✅ PASS | accepted/blocked/next_stage 均定义 |
| 10.4 | 外部资料不得进入启动上下文 | ✅ PASS | selection_principle 明确声明 |

---

## 总结

| 维度 | 结果 |
|:-----|:-----|
| 文件完整性 | ✅ PASS |
| 白名单防御 | ✅ PASS |
| 来源分类完整性 | ✅ PASS |
| 门禁完整性 | ✅ PASS |
| 候选池完整性 | ✅ PASS |
| 禁止直接应用 | ✅ PASS |
| 下游文件保护 | ✅ PASS |
| 外部文件一致性 | ✅ PASS |
| 禁止修改范围 | ✅ PASS |

**G4 结论：✅ PASS — 所有检查项通过，可以进入 G5 旧影复查。**
