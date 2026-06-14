# G4 自检报告

| 项目 | 内容 |
|:-----|:-----|
| 任务名称 | G3-QINGSHAN-FLOW-GLOBAL-KRM-RESTORE-FIX-v1.1 |
| 审计阶段 | G4 自检 |
| 报告版本 | v1.0 |
| 审计人 | 青山 |
| 审计日期 | 2026-06-11 |
| 流程类型 | F-FIX |

---

## 修复清单

| # | 修复项 | 说明 |
|:--|:-------|:------|
| 1 | roles/*/05_旧库索引.md | 路径从英文改为中文真实目录 |
| 2 | router 路径 | 占位符展开为6条中文路径 |
| 3 | role_capability_rules | 全部指向真实中文文件 |
| 4 | validator 升级 | 检查证据文件存在+行号范围 |
| 5 | manifest 重算 | sha/line 全部重算 |

## 修复前后对比

| 问题 | 修复前 | 修复后 |
|:-----|:-------|:-------|
| roles 指向英文目录 | legacy_role_kb/yuye/ | legacy_role_kb/玉夜/ |
| router 占位符 | {yuye,...} 6处 | 展开为6条中文路径 |
| rules source_file 不存在 | sources/legacy_role_kb/yuye/* | sources/legacy_role_kb/玉夜/* |
| validator 只检查字段存在 | 不检查真实路径 | 检查文件存在+行号范围 |

## 检查清单

### 1. legacy_role_kb 完整

| # | 检查项 | 结果 | 说明 |
|:--|:-------|:----|:-----|
| 1.1 | 6角色中文目录 | ✅ PASS | 玉夜/青山/流金/信鸽/山猫/腰子 |
| 1.2 | 文件数=64 | ✅ PASS | |
| 1.3 | sha256 与原始一致 | ✅ PASS | |

### 2. roles 索引修复

| # | 检查项 | 结果 | 说明 |
|:--|:-------|:----|:-----|
| 2.1 | 无英文 legacy_role_kb 路径 | ✅ PASS | |
| 2.2 | 指向真实中文目录 | ✅ PASS | |

### 3. router 修复

| # | 检查项 | 结果 | 说明 |
|:--|:-------|:----|:-----|
| 3.1 | 10类 route 完整 | ✅ PASS | |
| 3.2 | 无占位符路径 | ✅ PASS | |
| 3.3 | 全部路径真实存在 | ✅ PASS | |

### 4. rules 重建

| # | 检查项 | 结果 | 说明 |
|:--|:-------|:----|:-----|
| 4.1 | active_rules >= 118 | ✅ PASS | |
| 4.2 | draft_rules = 0 | ✅ PASS | |
| 4.3 | source_coverage = 64/64 | ✅ PASS | |
| 4.4 | rules_without_source_evidence = 0 | ✅ PASS | |
| 4.5 | bad_evidence_paths = 0 | ✅ PASS | |
| 4.6 | bad_evidence_lines = 0 | ✅ PASS | |

### 5. 青山三步未改

| # | 检查项 | 结果 | 说明 |
|:--|:-------|:----|:-----|
| 5.1 | source_selection_policy 存在 | ✅ PASS | 未修改 |
| 5.2 | quality_schema 存在 | ✅ PASS | 未修改 |
| 5.3 | card_to_rule_candidate_flow 存在 | ✅ PASS | 未修改 |

### 6. 禁止范围未改

| # | 检查项 | 结果 | 说明 |
|:--|:-------|:----|:-----|
| 6.1 | 未改 .claude/agents | ✅ PASS | |
| 6.2 | 未改 literature_cards | ✅ PASS | |
| 6.3 | 未改 rule_candidates | ✅ PASS | |
| 6.4 | 未改生产入口 | ✅ PASS | |

---

## 总结

**G4 结论：✅ PASS — 路径口径与证据可追溯性修复完成，可以进入 G5 旧影复查。**
