# 砺石 — 角色知识库

> 角色：砺石（方法校准官 / 反证审查官）
> 代码名：LISHI
> 知识库版本：v1.0
> 知识库初始时间：2026-06-12

## 目录结构

```
roles/lishi/
├── README.md              # 本文件：目录索引
├── 01_角色职责.md          # 角色职责定义
├── 02_启动必读.md          # 启动引导
├── 03_能力边界.md          # 能力边界与约束
├── seed_rules_v0.1.json   # 初始候选规则池（L5-seed）

source_candidates/lishi/
├── SC_LISHI_METHOD_REVIEW_FOUNDATION_v1.0.json  # 方法审查基础源

role_knowledge_metrics/lishi/
├── RKM_LISHI_v1.0.json  # 知识指标壳
```

## 15 步状态机当前状态

| 步骤 | 状态 |
|:-----|:-----|
| 1. SourceCandidate | ✅ 已建立 |
| 2. QualityScore | ⏳ 未开始 |
| 3. LiteratureCard | ⏳ 未开始 |
| 4. RuleCandidate | ❌ 未创建 |
| 5. RuleCandidateValidationTask | ❌ 未创建 |
| 6. ScenarioTrace | ⏳ 未开始 |
| 7. WeeklyValidationSummary | ⏳ 未开始 |
| 8. ValidationReview | ⏳ 未开始 |
| 9. RoleConfirmation | ⏳ 未开始 |
| 10. KnowledgeMergeCheck | ⏳ 未开始 |
| 11. PromotionDecision | ⏳ 未开始 |
| 12. ActiveRule | ❌ 未进入 |
| 13. KnowledgeAdoptionRecord | ❌ 未进入 |
| 14. PerformanceMonitor | ⏳ 未开始 |
| 15. RoleKnowledgeMetrics | ✅ 已建立初始壳 |

## 关联流程

- F-ROLE — 角色契约落地
- F-KNOW — 知识库进化纳入
- F-ANALYSIS — 日常分析触发

## 维护人

砺石（方法校准官）
