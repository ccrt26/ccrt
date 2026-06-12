# ROLE：砺石知识库进化入口建账 — G0-G6 记录 v0.1

> **流程编号：** F-KNOW
> **关联：** F-ROLE / F-ANALYSIS
> **名称：** 砺石知识库进化入口建账
> **性质：** 全流程入口纳入 + 候选规则池 + 初始指标壳
> **不创建正式 RuleCandidate，不创建正式 ValidationTask，不写 active registry，不宣称 L2 / active rule**
> **版本：** v0.1
> **时间：** 2026-06-12

---

## G0 — 路由记录

| 字段 | 值 |
|:-----|:-----|
| **流程编号** | F-KNOW |
| **关联流程** | F-ROLE / F-ANALYSIS |
| **目标** | 砺石知识库进化入口建账 |
| **性质** | 全流程入口纳入 + 候选规则池 + 初始指标壳 |
| **formal pipeline** | 不声明 PASS |
| **路由时间** | 2026-06-12 |

---

## G1 — 入口口径确认

### 本步完成

| 事项 | 状态 |
|:-----|:------|
| 建立砺石角色知识库目录 | ✅ roles/lishi/ 含 4MD + 1JSON |
| 建立砺石初始 seed_rules 候选规则池 | ✅ seed_rules_v0.1.json（3条L5-seed） |
| 建立 SourceCandidate 入口 | ✅ SC JSON |
| 建立 RoleKnowledgeMetrics 初始壳 | ✅ RKM JSON（全 0 指标） |

### 本步不表示

| 事项 | 状态 |
|:-----|:------|
| 不创建正式 RuleCandidate | ❌ 未创建 |
| 不创建正式 ValidationTask | ❌ 未创建 |
| 不写 active registry | ❌ 不修改 knowledge_registry.json |
| 不宣称 L2 | ❌ 全部 L5-seed |
| 不宣称 active rule | ❌ 全部 seed_candidate/not_started |

---

## G2 — 技术方案

### 新增文件清单

| # | 文件路径 | 内容 |
|:--|:---------|:------|
| 1 | `00_项目地基/07_知识进化/knowledge/roles/lishi/README.md` | 目录索引 + 15步状态机 |
| 2 | `00_项目地基/07_知识进化/knowledge/roles/lishi/01_角色职责.md` | 角色职责定义 |
| 3 | `00_项目地基/07_知识进化/knowledge/roles/lishi/02_启动必读.md` | 启动引导 |
| 4 | `00_项目地基/07_知识进化/knowledge/roles/lishi/03_能力边界.md` | 能力边界约束 |
| 5 | `00_项目地基/07_知识进化/knowledge/roles/lishi/seed_rules_v0.1.json` | 3条L5-seed候选规则 |
| 6 | `00_项目地基/07_知识进化/knowledge/source_candidates/lishi/SC_LISHI_METHOD_REVIEW_FOUNDATION_v1.0.json` | SourceCandidate入口 |
| 7 | `00_项目地基/07_知识进化/knowledge/role_knowledge_metrics/lishi/RKM_LISHI_v1.0.json` | 指标壳（全0） |
| 8 | `00_项目地基/08_审计与验收/ROLE_砺石知识库进化入口建账_G0-G6记录_v0.1.md` | 本文档 |

### 禁止范围

| 禁止项 | 状态 |
|:-------|:------|
| 不修改 统一解读/knowledge_registry.json | ✅ |
| 不修改 统一解读/knowledge_entries.jsonl | ✅ |
| 不创建 rule_candidates/lishi | ✅ |
| 不创建 validation_tasks/lishi | ✅ |
| 不创建 active rules | ✅ |
| 不修改日报/深度/荐股/模拟交易 | ✅ |
| 不修改 validate_interpretation.py | ✅ |
| 不修改 U-9/U-10 | ✅ |
| 不新增 U-11 | ✅ |
| 不修改生产调度 | ✅ |

---

## G3 — 执行记录

| 步骤 | 状态 |
|:-----|:------|
| roles/lishi/README.md | ✅ 新建 |
| roles/lishi/01_角色职责.md | ✅ 新建 |
| roles/lishi/02_启动必读.md | ✅ 新建 |
| roles/lishi/03_能力边界.md | ✅ 新建 |
| roles/lishi/seed_rules_v0.1.json | ✅ 新建 |
| source_candidates/lishi/SC_LISHI_METHOD_REVIEW_FOUNDATION_v1.0.json | ✅ 新建 |
| role_knowledge_metrics/lishi/RKM_LISHI_v1.0.json | ✅ 新建 |
| 回滚越界变更（registry/jsonl/RC/VT） | ✅ 完成 |

---

## G4 — 自检结果

### JSON 合法性

```bash
python3 -m json.tool seed_rules_v0.1.json       -> ✅
python3 -m json.tool SC_LISHI_METHOD_REVIEW...   -> ✅
python3 -m json.tool RKM_LISHI_v1.0.json         -> ✅
```

### RC/VT 目录不存在

```bash
test ! -e rule_candidates/lishi  -> ✅ 不存在
test ! -e validation_tasks/lishi -> ✅ 不存在
```

### 状态字段校验

`rg -n "砺石|LISHI|LISHI-SEED-001|LISHI-SEED-002|LISHI-SEED-003|L5-seed|seed_candidate|not_started|downstream_created|active_rule_count|l2_rule_count"`

- seed_rules: 3条均为 L5-seed / seed_candidate / not_started ✅
- SC: downstream_created: false ✅
- RKM: active_rule_count: 0, l2_rule_count: 0 ✅

### registry/jsonl 未含 LISHI

```bash
rg -c "LISHI" knowledge_registry.json -> 0 ✅
rg -c "LISHI" knowledge_entries.jsonl -> 0 ✅
wc -l knowledge_entries.jsonl -> 31 ✅ (原行数)
```

### 白空间

```bash
git diff --check -> ✅ 无错误
```

### 文件范围

仅 8 个新增文件（7知识库 + 1审计记录），统一解读无修改。

---

## G5 — 复查结论（Codex 执行）

> **Codex 执行复查，不等同旧影正式签字。**

| # | 复查项 | 结果 | 依据 |
|:--|:-------|:-----|:------|
| 1 | 是否只新增允许的 8 个文件 | ✅ PASS | roles/lishi(5) + SC(1) + RKM(1) + G0-G6(1) |
| 2 | 是否未修改 knowledge_registry.json | ✅ PASS | rg -c "LISHI" registry.json = 0 |
| 3 | 是否未修改 knowledge_entries.jsonl | ✅ PASS | rg -c "LISHI" jsonl = 0, 行数 31 |
| 4 | 是否未创建 rule_candidates/lishi | ✅ PASS | test ! -e 通过 |
| 5 | 是否未创建 validation_tasks/lishi | ✅ PASS | test ! -e 通过 |
| 6 | seed_rules 是否全部为 L5-seed/seed_candidate/not_started | ✅ PASS | 3条均一致 |
| 7 | RoleKnowledgeMetrics 是否为 0 样本初始壳 | ✅ PASS | sample_count=0, active_rule_count=0, l2_rule_count=0 |
| 8 | 是否未宣称 L2 / active rule | ✅ PASS | 均未宣称 |
| 9 | 是否未接生产 | ✅ PASS | 无程序文件被修改 |
| 10 | 是否未新增 U-11 | ✅ PASS | U-11 不存在 |

### 总体结论

| 项目 | 判定 |
|:-----|:-----|
| **总体结论** | ✅ **PASS** |
| **复查人** | Codex 执行复查（不等同于旧影正式签字） |
| **遗留问题** | 无 |

---

## G6 — 归档

### 固定声明

> Formal pipeline 未通过；RUN 仍停在当前阶段。
> 本阶段基于用户一次性授权与知识库入口建账流程例外继续，不等同于 formal pipeline PASS。
> 本轮仅完成砺石知识库进化入口、候选规则池和初始指标壳纳入。
> 不得宣称砺石规则已完成 15 步全流程，不得宣称 L2，不得宣称 active rule。

### 15 步状态机当前状态

| 步 | 步骤 | 状态 |
|:--:|:-----|:-----|
| 1 | SourceCandidate | ✅ 已建立 |
| 2 | QualityScore | ⏳ 未开始 |
| 3 | LiteratureCard | ⏳ 未开始 |
| 4 | RuleCandidate | ❌ 未创建 |
| 5 | RuleCandidateValidationTask | ❌ 未创建 |
| 6 | ScenarioTrace | ⏳ 未开始 |
| 7 | WeeklyValidationSummary | ⏳ 未开始 |
| 8 | ValidationReview | ⏳ 未开始 |
| 9 | RoleConfirmation | ⏳ 未开始 |
| 10 | KnowledgeMergeCheck | ⏳ 未开始 |
| 11 | PromotionDecision | ⏳ 未开始 |
| 12 | ActiveRule | ❌ 未进入 |
| 13 | KnowledgeAdoptionRecord | ❌ 未进入 |
| 14 | PerformanceMonitor | ⏳ 未开始 |
| 15 | RoleKnowledgeMetrics | ✅ 已建立初始壳 |

### 本轮完成

| 维度 | 状态 |
|:-----|:------|
| 砺石角色知识库目录（独立 roles/lishi/） | ✅ |
| 3 条 L5-seed 初始候选规则（seed_rules_v0.1.json） | ✅ |
| SourceCandidate 入口（SC JSON） | ✅ |
| RoleKnowledgeMetrics 初始壳（RKM JSON） | ✅ |

### 本轮未完成

| 项目 | 说明 |
|:-----|:------|
| 正式 RuleCandidate | 未创建（入口建账只需 seed_rules） |
| 正式 ValidationTask | 未创建 |
| Active Registry 注册 | 未写入 |
| 步 2-14 | 均未开始或未进入 |

### 下一步建议

1. 在真实日报/深度分析场景中积累砺石审查样本
2. 收集 20+ 样本后走 QualityScore → LiteratureCard → RuleCandidate → ValidationTask 升级路径
3. 验证通过后再考虑 registry 注册和 active rule 升级

### 最终交付物

| # | 产出物 | 状态 |
|:--|:-------|:-----|
| 1 | 砺石角色知识库目录（4MD + seed_rules） | ✅ |
| 2 | 3 条 L5-seed 初始候选规则（LISHI-SEED-001~003） | ✅ |
| 3 | SourceCandidate 入口 | ✅ |
| 4 | RoleKnowledgeMetrics 初始壳（全 0） | ✅ |
| 5 | G0-G6 记录 | ✅ |
| 6 | 自检命令结果全部通过 | ✅ |
| 7 | Codex 复查结论：PASS | ✅ |
