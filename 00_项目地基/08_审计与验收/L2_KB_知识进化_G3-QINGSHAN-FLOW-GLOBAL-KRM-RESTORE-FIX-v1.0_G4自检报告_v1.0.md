# G4 自检报告

| 项目 | 内容 |
|:-----|:-----|
| 任务名称 | G3-QINGSHAN-FLOW-GLOBAL-KRM-RESTORE-FIX-v1.0 |
| 审计阶段 | G4 自检 |
| 报告版本 | v1.0 |
| 审计人 | 青山 |
| 审计日期 | 2026-06-11 |
| 流程类型 | F-FIX |

---

## 根因

第三步脚本只按青山文献三步重建了 knowledge/manifest.json 和 krm_task_router_v1.0.json，导致 KRM 全局结构缩窄：
1. manifest 只剩青山三步 9 条 entry
2. router 只剩 4 个青山相关 route
3. knowledge/sources/legacy_role_kb 为空
4. roles/shared/rules 等全局 KRM 结构缺失
5. 前面"旧库能力不下降"的承诺无法成立

---

## 恢复检查清单

### 1. 青山三步文件保护

| # | 检查项 | 结果 | 说明 |
|:--|:-------|:----|:-----|
| 1.1 | source_selection_policy 存在且未改 | ✅ PASS | sha256 与 before 一致 |
| 1.2 | quality_schema 存在且未改 | ✅ PASS | sha256 与 before 一致 |
| 1.3 | card_to_rule_candidate_flow 存在且未改 | ✅ PASS | sha256 与 before 一致 |

### 2. legacy_role_kb 恢复

| # | 检查项 | 结果 | 说明 |
|:--|:-------|:----|:-----|
| 2.1 | 6 角色目录完整 | ✅ PASS | 玉夜/青山/流金/信鸽/山猫/腰子 |
| 2.2 | 总文件数 = 64 | ✅ PASS | 与旧库一致 |
| 2.3 | sha256 与原文件一致 | ✅ PASS | 确认未改动 |
| 2.4 | 未改写旧库正文 | ✅ PASS | 仅复制，不修改 |

### 3. Roles 启动包恢复

| # | 检查项 | 结果 | 说明 |
|:--|:-------|:----|:-----|
| 3.1 | 6 角色启动包目录完整 | ✅ PASS | |
| 3.2 | 每个角色 6 个文件 | ✅ PASS | README + 01~05 |
| 3.3 | 只做导航不承载全文 | ✅ PASS | 深度读取指向 legacy_role_kb |

### 4. Shared 共享规则恢复

| # | 检查项 | 结果 | 说明 |
|:--|:-------|:----|:-----|
| 4.1 | 6 类共享目录完整 | ✅ PASS | risk/evidence/output/routing/post_eval/parameter |
| 4.2 | 每个目录有 README | ✅ PASS | 适用说明+角色关联+读取时机 |

### 5. Rules 恢复

| # | 检查项 | 结果 | 说明 |
|:--|:-------|:----|:-----|
| 5.1 | role_capability_rules JSON 存在 | ✅ PASS | |
| 5.2 | role_capability_rules JSONL 存在 | ✅ PASS | |
| 5.3 | role_capability_index 存在 | ✅ PASS | |
| 5.4 | active rules >= 118 | ✅ PASS | 从 legacy_role_kb 提取 |
| 5.5 | source coverage = 64/64 | ✅ PASS | 全覆盖 |
| 5.6 | 每条规则有 source_evidence | ✅ PASS | 指向 legacy_role_kb 文件 |

### 6. Router 恢复

| # | 检查项 | 结果 | 说明 |
|:--|:-------|:----|:-----|
| 6.1 | 10 类 route 完整 | ✅ PASS | flow/knowledge/financial/evidence/signal/event/macro/integration/post_eval/output |
| 6.2 | signal_validity_issue 包含青山三步 | ✅ PASS | 3 个 optional_read |

### 7. Manifest 恢复

| # | 检查项 | 结果 | 说明 |
|:--|:-------|:----|:-----|
| 7.1 | entries > 9 | ✅ PASS | |
| 7.2 | 覆盖 roles/shared/legacy/rules/routing/literature/scripts/reports | ✅ PASS | |
| 7.3 | sha256 全部真实匹配 | ✅ PASS | |
| 7.4 | line_count 全部真实匹配 | ✅ PASS | |

### 8. 禁止修改范围检查

| # | 检查项 | 结果 | 说明 |
|:--|:-------|:----|:-----|
| 8.1 | 未改 .claude/agents | ✅ PASS | |
| 8.2 | 未改生产入口 | ✅ PASS | |
| 8.3 | 未创建 literature_cards | ✅ PASS | |
| 8.4 | 未创建 rule_candidates | ✅ PASS | |

---

## 总结

| 维度 | 结果 |
|:-----|:-----|
| 青山三步保护 | ✅ PASS |
| legacy_role_kb 恢复 | ✅ PASS |
| roles 启动包 | ✅ PASS |
| shared 共享规则 | ✅ PASS |
| rules 恢复 | ✅ PASS |
| router 恢复 | ✅ PASS |
| manifest 恢复 | ✅ PASS |
| 禁止修改范围 | ✅ PASS |

**G4 结论：✅ PASS — 全局 KRM 结构已恢复，青山三步保留，能力不下降，可以进入 G5 旧影复查。**
