# G6 放行归档记录

| 项目 | 内容 |
|:-----|:-----|
| 任务名称 | G3-QINGSHAN-SOURCE-SELECTION-v1.0 |
| 审计阶段 | G6 放行归档 |
| 报告版本 | v1.0 |
| 审计人 | 新安 |
| 审计日期 | 2026-06-11 |
| 流程类型 | F-ARCH |
| 前驱 | G4 自检 ✅ PASS → G5 旧影复查 ✅ PASS |

---

## 放行检查

### 1. 是否允许 policy 进入 task 读取层？

**结论：✅ 允许。**

- policy JSON 的 `read_tier: "task"` — 青山在因子有效性分析、信号验证、样本外检验等日常任务中，需要知道来源准入规则
- manifest.json 中该条目的 `read_tier` 也为 `task`
- `read_tier: "task"` 是合理的——政策本身不长（202 行），且是青山工作流的必要参考

### 2. 是否允许作为青山资料来源选择的准入规则？

**结论：✅ 允许。**

- policy JSON 的 `status: "active"`，可以直接指导实际工作
- must_have_gates 明确可用，且 block_if_missing=true 确保严格执行
- preferred_candidate_pool 可直接作为优先参考入口
- 8 条候选来源覆盖了研究数据库、学术文献、官方披露三类核心来源类型

### 3. 是否建议进入下一阶段？

**结论：✅ 建议进入 G3-LITERATURE-QUALITY-SCORING（青山文献质量评分 schema v1.0）。**

具体建议：
1. **青山文献质量评分 schema**：定义 source_candidate 的质量评分模型
2. **评分维度**：已有 6 个预定义维度（authority/replicability/market_fit/recency/conflict_risk/rule_convertibility）
3. **候选来源扩充**：当前 8 条候选池可按需扩充（如 Wind 数据库、中证指数官方方法文件等）
4. **文献卡片模板**：为后续文献卡片流程定义 template
5. **规则候选生成流程**：定义 source_candidate → literature_card → rule_candidate 的完整 pipeline

---

## 归档记录

### 产出文件清单

| 文件 | 路径 | 类型 |
|:-----|:-----|:-----|
| 来源准入规则 | `literature/qingshan_source_selection_policy_v1.0.json` | literature_source_policy |
| 校验脚本 | `scripts/validate_qingshan_source_selection_v1_0.py` | validation_script |
| 校验报告 | `reports/qingshan_source_selection_validation_v1.0.json` | validation_report |
| 知识注册表 | `manifest.json` | manifest |
| 路由规则 | `routing/krm_task_router_v1.0.json` | routing |
| G4 自检报告 | `08_审计与验收/L2_KB_知识进化_G3-..._G4自检报告_v1.0.md` | audit_report |
| G5 复查报告 | `08_审计与验收/L2_KB_知识进化_G3-..._G5旧影复查报告_v1.0.md` | audit_report |
| G6 放行记录 | `08_审计与验收/L2_KB_知识进化_G3-..._G6放行归档记录_v1.0.md` | audit_report |

### 未修改文件清单

| 路径 | 状态 |
|:-----|:-----|
| `.claude/agents/*.md` | 未修改 |
| `.claude/agents/*-知识库/` | 未修改 |
| `knowledge/roles/qingshan/*.md` | 未涉及 |
| role_capability_rules | 未涉及 |
| 生产入口 | 未修改 |

---

## 放行签名

| 签名 | 状态 | 说明 |
|:-----|:-----|:------|
| G4 自检 | ✅ PASS | 青山自检通过 |
| G5 旧影复查 | ✅ PASS | 旧影复查通过，建议下一阶段 |
| G6 新安放行 | ✅ ✅ | 本记录即为 G6 放行记录 |

**G6 结论：✅ PASS — 青山资料来源准入规则 v1.0 放行归档。请参考下一阶段：qingshan_literature_quality_scoring_v1.0。**
