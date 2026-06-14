# L2 KB 知识进化：外部文献到正式入库全流程方案 v1.1

## 1. 方案定位

本文档定义金融团队从外部文献、权威资料、项目经验中吸收知识，并最终写入角色正式知识库的完整流程。

v1.1 在 v1.0 基础上新增三条硬原则：

```text
迭代优先于新增：新知入库前必须和存量知识融合校验，禁止简单堆砌。
有效性绑定实战：正式知识必须持续接受日常分析场景验证，失效自动复审。
能力可追踪量化：角色知识必须按能力维度打标签，并统计覆盖、有效、失效和成长。
```

本流程的目标不是让知识库变大，而是让知识库持续提纯、优化、迭代，并能证明角色能力确实提升。

## 2. 适用范围

适用于所有金融团队角色：

```text
玉夜：数据质量、字段口径、数据可用等级。
青山：信号有效性、因子胜率、样本约束。
流金：风险边界、否决项、动作审计。
信鸽：事件分级、公告证据、催化窗口。
山猫：宏观覆写、行业相位、市场环境。
腰子：整合裁决、状态机、结论强度。
```

适用于所有知识来源：

```text
外部文献
权威资料
交易所/监管/公告资料
项目已验证经验
后评估复盘结论
反例和失败案例
参数校准结果
```

适用于所有分析场景：

```text
日报
周报
后评估
深度分析
每日荐股
模拟交易
其他未来新增分析模块
```

## 3. 总原则

### 3.1 统一入口，角色分领域判断

定期文献收集不由每个角色各自随便找，也不由某个角色独自统一判断。

采用两层机制：

```text
系统/阿黑统一收集、去重、登记、分发；
角色按职责判断专业价值、验证档位、是否继续推进。
```

职责：

```text
阿黑/系统：调度任务、收集候选、去重、登记、分发、状态跟踪。
青山：因子、信号、技术有效性、样本外、衰减、过拟合。
玉夜：数据口径、数据质量、字段可信度、证据可用性。
流金：风险边界、交易纪律、否决项、动作审计。
信鸽：公告、事件、催化剂、信息源等级、事件窗口。
山猫：宏观、行业、市场环境、状态切换。
腰子：整合裁决、结论强度、状态机、是否进入整体决策体系。
旧影：复查是否越界、是否破坏流程边界。
```

### 3.2 程序推动流程，角色判断质量

程序负责：

```text
定时收集
生成候选
生成卡片
生成候选规则
生成验证任务
维护 manifest
执行 validator
监控流程卡点
自动修复低风险账务问题
生成审计草稿
```

角色负责：

```text
专业判断
验证结论
确认是否晋级
确认是否写入 active rule
确认是否废止或修订旧知识
```

### 3.3 候选不等于正式知识

外部资料进入系统后，最多自动推进到：

```text
RuleCandidate candidate_draft
RuleCandidateValidationTask observation_pending
```

不得自动进入：

```text
active rule
角色核心知识库
正式投研结论
交易动作边界
```

### 3.4 迭代优先于新增

新知入库前必须执行：

```text
KnowledgeMergeCheck
```

检查：

```text
是否已有同类规则
是否只是换了说法
是否补充旧规则边界
是否修正旧规则过时结论
是否与旧规则冲突
是否应进入反例库/参数库，而不是新增 active rule
```

结论只能是：

```text
merge_existing
revise_existing
add_new
reject_duplicate
counterexample_only
parameter_candidate
background_only
```

禁止每篇文献都新增一条规则。

### 3.5 知识有效性绑定实战表现

每条 active rule 入库后必须绑定：

```text
PerformanceMonitor
```

监控：

```text
被哪些报告引用
触发次数
支持正确判断次数
误导次数
场景不匹配次数
胜率/命中率变化
失效率变化
误用率变化
是否长期无触发
```

长期失效或场景不匹配时自动触发：

```text
review_required
revise_required
deprecate_candidate
```

### 3.6 能力可追踪，知识可量化

每个角色必须维护：

```text
RoleKnowledgeMetrics
```

统计：

```text
知识覆盖度
能力维度规则数量
active/draft/deprecated 比例
最近更新时间
被实战引用次数
有效知识占比
失效知识比例
外部文献转化率
候选规则通过率
反例数量
参数校准次数
```

这不是为了做漂亮指标，而是为了发现能力缺口。

## 4. 15 步状态机

v1.1 将 v1.0 的 12 步升级为 15 步。

```text
1. SourceCandidate
2. QualityScore
3. LiteratureCard
4. RuleCandidate
5. RuleCandidateValidationTask
6. ScenarioTrace
7. WeeklyValidationSummary
8. ValidationReview
9. RoleConfirmation
10. KnowledgeMergeCheck
11. PromotionDecision
12. ActiveRule
13. KnowledgeAdoptionRecord
14. PerformanceMonitor
15. RoleKnowledgeMetrics
```

### 4.1 Step 1：SourceCandidate

目的：

```text
把外部资料登记为候选来源。
```

输入：

```text
外部文献、论文、数据源、交易所公告、监管文件、项目经验、用户指定资料。
```

输出：

```text
knowledge/source_candidates/<source_id>.json
```

必须字段：

```text
source_id
title
source_type
url_or_location
author_or_institution
publication_date
discovered_at
discovery_channel
suggested_owner_roles
dedup_key
traceability
initial_status
```

状态：

```text
source_candidate
duplicate_rejected
out_of_scope
pending_role_route
```

禁止：

```text
不得直接生成 active rule。
不得直接进入投研报告。
不得跳过质量评分。
```

### 4.2 Step 2：QualityScore

目的：

```text
判断资料是否值得制卡。
```

输出：

```text
knowledge/quality_scores/<source_id>_quality_score.json
```

评分维度：

```text
权威性
方法透明度
样本质量
可复现性
适用市场
过拟合风险
角色相关性
证据可追溯性
```

状态：

```text
quality_pass
quality_pass_with_cross_check
quality_background_only
quality_reject
```

依赖：

```text
SourceCandidate 必须存在。
SourceCandidate 不能是 duplicate_rejected 或 out_of_scope。
```

### 4.3 Step 3：LiteratureCard

目的：

```text
把资料浓缩成可读、可追溯、带边界的文献卡片。
```

输出：

```text
knowledge/literature_cards/<role>/<card_id>.json
```

必须字段：

```text
card_id
source_id
source_title
source_type
author_or_institution
publication_date
source_selection_status
quality_status
total_score
hard_block_triggered
extracted_claims
evidence_units
applicable_market
sample_scope
method_summary
limitations
conflict_notes
role_use_case
traceability
card_status
```

状态：

```text
card_draft
card_rejected
card_background_only
```

边界：

```text
card_draft 可以存在。
card_draft 不等于规则。
card_draft 不允许被正式报告当成结论依据。
```

### 4.4 Step 4：RuleCandidate

目的：

```text
从文献卡片中提炼可能值得吸收的规则想法。
```

输出：

```text
knowledge/rule_candidates/<role>/<candidate_id>.json
```

必须字段：

```text
candidate_id
source_card_id
owner_role
candidate_type
target_knowledge_bucket
proposed_rule_summary
evidence_refs
applicability_scope
exclusion_conditions
expected_benefit
risk_of_misuse
validation_requirement
candidate_status
promotion_blockers
next_required_checks
```

状态：

```text
candidate_draft
candidate_rejected
candidate_background_only
```

禁止：

```text
不得直接写 active rule。
不得修改 role_capability_rules。
不得影响日报/周报主结论。
```

### 4.5 Step 5：RuleCandidateValidationTask

目的：

```text
定义候选规则如何被分析模块验证。
```

输出：

```text
knowledge/validation_tasks/<candidate_id>_validation_task.json
```

必须字段：

```text
task_id
candidate_id
source_card_id
owner_role
validation_type
status
created_at
validation_scope
applicable_scenarios
trigger_conditions
required_evidence
minimum_observation_window
minimum_trigger_count
required_checks
scenario_responsibilities
promotion_conditions
rejection_conditions
review_gates
deadline_policy
```

状态：

```text
observation_pending
observing
ready_for_review
blocked
closed
```

关键原则：

```text
周报、日报、后评估、深度分析等模块不自己决定验证方式；
它们读取 ValidationTask 后执行并留痕。
```

### 4.6 Step 6：ScenarioTrace

目的：

```text
分析模块触发候选任务时留下事实痕迹。
```

输出：

```text
knowledge/scenario_traces/<task_id>/<scenario>/<date>.json
```

场景：

```text
daily_report
weekly_report
post_evaluation
deep_analysis
stock_recommendation
simulated_trading
```

必须字段：

```text
trace_id
task_id
scenario
run_id
date
triggered
trigger_reason
evidence_added
counterexample_found
misuse_risk_level
operator_note
```

边界：

```text
日报只留痕。
周报只汇总。
后评估才判断晋级方向。
```

### 4.7 Step 7：WeeklyValidationSummary

目的：

```text
按周汇总验证任务的触发和证据。
```

输出：

```text
knowledge/validation_summaries/<task_id>/weekly_<week_id>.json
```

必须字段：

```text
summary_id
task_id
week_id
trigger_count
effective_trigger_count
supporting_evidence
counterexamples
misuse_risk_summary
scenario_coverage
missing_required_checks
weekly_conclusion
```

结论：

```text
continue_observation
insufficient_evidence
counterexample_found
ready_for_review
```

### 4.8 Step 8：ValidationReview

目的：

```text
判断候选规则经过实战观察后是否有价值。
```

输出：

```text
knowledge/validation_reviews/<task_id>_review.json
```

必须字段：

```text
review_id
task_id
candidate_id
observation_window
effective_trigger_count
required_checks_result
counterexample_result
misuse_risk_result
performance_summary
review_conclusion
review_reason
```

结论：

```text
continue_observation
validation_passed
rejected
counterexample_only
parameter_candidate
background_only
```

### 4.9 Step 9：RoleConfirmation

目的：

```text
相关角色确认候选是否符合职责和专业判断。
```

输出：

```text
knowledge/role_confirmations/<candidate_id>/<role>_confirmation.json
```

确认角色按任务需要选择，不是所有角色都参与。

必须字段：

```text
confirmation_id
candidate_id
role
confirmation_result
confirmation_reason
scope_limit
remaining_risk
confirmed_at
```

结论：

```text
PASS
WARN
BLOCK
```

红线：

```text
系统不得代签角色确认。
缺角色确认时不得进入 PromotionDecision PASS。
```

### 4.10 Step 10：KnowledgeMergeCheck

目的：

```text
入库前与存量知识融合校验，防止堆砌。
```

输出：

```text
knowledge/merge_checks/<candidate_id>_merge_check.json
```

必须检查：

```text
existing_rule_similarity
duplicate_risk
conflict_with_active_rules
can_merge_existing
should_revise_existing
should_add_new
should_enter_counterexample
should_enter_parameter_library
deprecated_rules_affected
```

结论：

```text
merge_existing
revise_existing
add_new
reject_duplicate
counterexample_only
parameter_candidate
background_only
```

硬约束：

```text
未完成 KnowledgeMergeCheck，不得新增 active rule。
若判定为 merge_existing 或 revise_existing，优先迭代旧规则。
```

### 4.11 Step 11：PromotionDecision

目的：

```text
决定候选如何处理。
```

输出：

```text
knowledge/promotion_decisions/<candidate_id>_promotion_decision.json
```

可能结果：

```text
promote_to_active_rule
merge_into_existing_rule
revise_existing_rule
keep_observing
reject
counterexample_only
parameter_candidate
background_only
```

依赖：

```text
ValidationReview 已完成。
RoleConfirmation 必要角色 PASS 或有明确 WARN 处理。
KnowledgeMergeCheck 已完成。
```

### 4.12 Step 12：ActiveRule

目的：

```text
写入正式规则库，成为可被报告引用的知识。
```

输出：

```text
knowledge/rules/role_capability_rules_vX.json
knowledge/rules/role_capability_rules_vX.jsonl
knowledge/rules/role_capability_index_vX.json
```

必须字段：

```text
active_rule_id
owner_role
rule_text
source_card_id
candidate_id
validation_task_id
merge_check_id
promotion_decision_id
applicability_scope
exclusion_conditions
misuse_risk
effective_date
review_after
deprecation_condition
status
```

状态：

```text
active
deprecated
superseded
under_review
```

### 4.13 Step 13：KnowledgeAdoptionRecord

目的：

```text
生成人能读懂的正式入库记录。
```

输出：

```text
knowledge/adoption_records/<active_rule_id>_adoption_record.md
```

必须包含：

```text
active_rule_id
来源文献
LiteratureCard ID
RuleCandidate ID
ValidationTask ID
验证周期
触发次数
关键证据
反例检查
误用风险
KnowledgeMergeCheck 结论
确认角色
为什么入库
适用范围
禁止误用
未来复查日期
废止条件
```

### 4.14 Step 14：PerformanceMonitor

目的：

```text
正式知识入库后持续绑定实战表现。
```

输出：

```text
knowledge/performance_monitors/<active_rule_id>_performance.json
```

监控指标：

```text
report_reference_count
trigger_count
correct_support_count
misleading_count
counterexample_count
scene_mismatch_count
win_rate_or_hit_rate
misuse_rate
last_triggered_at
review_required
```

自动触发：

```text
长期无触发：review_required
误导次数达到阈值：revise_required
胜率/命中率下滑：performance_review
场景不匹配反复出现：scope_revision_required
```

### 4.15 Step 15：RoleKnowledgeMetrics

目的：

```text
量化角色能力成长，而不是凭感觉说变强。
```

输出：

```text
knowledge/metrics/<role>_knowledge_metrics.json
```

按角色能力维度统计。

青山示例：

```text
因子有效性
IC/ICIR
样本外验证
因子衰减
过拟合防范
A 股适配
技术信号胜率
```

通用指标：

```text
coverage_score
active_rule_count
candidate_count
deprecated_rule_count
effective_knowledge_ratio
stale_knowledge_ratio
external_literature_conversion_rate
candidate_pass_rate
counterexample_count
last_updated
```

## 5. 前后依赖关系

任何脚本不得跳步。

```text
没有 SourceCandidate，不能 QualityScore。
没有 QualityScore PASS，不能 LiteratureCard。
没有 LiteratureCard，不能 RuleCandidate。
没有 RuleCandidate，不能 ValidationTask。
没有 ValidationTask，不能要求周报/日报验证。
没有 ScenarioTrace，不能形成有效 WeeklyValidationSummary。
没有足够 WeeklyValidationSummary，不能 ValidationReview PASS。
没有 ValidationReview，不能 RoleConfirmation。
没有 RoleConfirmation，不能 KnowledgeMergeCheck 通过。
没有 KnowledgeMergeCheck，不能 PromotionDecision。
没有 PromotionDecision PASS，不能 ActiveRule。
没有 ActiveRule，不能 KnowledgeAdoptionRecord。
没有 ActiveRule，不能 PerformanceMonitor。
没有 PerformanceMonitor，不能更新 RoleKnowledgeMetrics。
```

## 6. 分析模块调用规范

调用关系不由周报或日报临时决定，而由 ValidationTask 定义。

示例字段：

```text
applicable_scenarios:
  daily_report: trace_only
  weekly_report: weekly_summary
  post_evaluation: promotion_review
  deep_analysis: trigger_when_external_factor_used
  stock_recommendation: not_applicable
  simulated_trading: not_applicable
```

模块职责：

```text
日报：记录触发事实、证据、反例、误用风险。
周报：汇总一周触发情况，不直接入库。
后评估：判断候选是否晋级、拒绝、继续观察。
深度分析：触发相关候选时做边界检查。
荐股：仅在 ValidationTask 明确要求时检查排序/否决。
模拟交易：仅在 ValidationTask 明确要求时检查动作边界。
```

## 7. 验证档位矩阵

应程序化为：

```text
knowledge/policies/validation_policy_matrix_v1.0.json
```

默认档位：

```text
方法论规则：
至少 4 个周报周期，至少 3 次有效触发。

因子/信号规则：
至少 8-12 周，或 20-30 次有效信号样本。

参数规则：
至少 2 个回测窗口，或 1 次样本外验证。

风险红线：
可快速处理，但必须流金 + 腰子确认。

数据口径规则：
玉夜确认 + 至少 2 个数据样例 + 1 个异常案例。

事件催化规则：
按公告后 1/3/5/10 个交易日窗口验证。

宏观环境规则：
至少 2 个周报周期，或完整覆盖一次宏观事件窗口。

流程/输出规则：
1-2 个执行周期，旧影复查通过即可。
```

## 8. 定时任务设计

### 8.1 定时任务清单

```text
source_discovery_job
周期：每 2 周
输出：SourceCandidate

source_quality_scoring_job
周期：每月或候选积累到阈值
输出：QualityScore

literature_card_builder_job
触发：QualityScore PASS
输出：LiteratureCard

rule_candidate_builder_job
触发：LiteratureCard 存在可复用规则想法
输出：RuleCandidate

validation_task_builder_job
触发：RuleCandidate candidate_draft
输出：RuleCandidateValidationTask

scenario_trace_collector_job
触发：日报/周报/深度分析/荐股/模拟交易运行
输出：ScenarioTrace

weekly_validation_summary_job
周期：每周
输出：WeeklyValidationSummary

validation_review_job
触发：满足观察窗口和触发次数
输出：ValidationReview

role_confirmation_request_job
触发：ValidationReview ready_for_role_confirmation
输出：RoleConfirmation request

knowledge_merge_check_job
触发：必要 RoleConfirmation 完成
输出：KnowledgeMergeCheck

promotion_decision_job
触发：ValidationReview + RoleConfirmation + KnowledgeMergeCheck 完成
输出：PromotionDecision

active_rule_writer_job
触发：PromotionDecision = promote_to_active_rule 或 merge/revise
输出：ActiveRule

adoption_record_builder_job
触发：ActiveRule 写入
输出：KnowledgeAdoptionRecord

performance_monitor_job
周期：每周/月，且每次报告引用 active rule 后触发
输出：PerformanceMonitor

role_knowledge_metrics_job
周期：每月
输出：RoleKnowledgeMetrics

manifest_integrity_job
触发：每次写文件后 + 每日巡检
输出：manifest integrity report

workflow_progress_monitor_job
周期：每日或每周
输出：WorkflowMonitorReport

stale_candidate_cleanup_job
周期：每月
输出：长期无触发候选清理建议

literature_gap_review_job
周期：每季度
输出：角色文献缺口复盘
```

### 8.2 任务依赖

主链：

```text
source_discovery_job
→ source_quality_scoring_job
→ literature_card_builder_job
→ rule_candidate_builder_job
→ validation_task_builder_job
→ scenario_trace_collector_job
→ weekly_validation_summary_job
→ validation_review_job
→ role_confirmation_request_job
→ knowledge_merge_check_job
→ promotion_decision_job
→ active_rule_writer_job
→ adoption_record_builder_job
→ performance_monitor_job
→ role_knowledge_metrics_job
```

巡检链：

```text
manifest_integrity_job
workflow_progress_monitor_job
stale_candidate_cleanup_job
literature_gap_review_job
```

## 9. 程序化产物规划

下一阶段应逐步落地以下程序化文件。

策略与 schema：

```text
knowledge/policies/validation_policy_matrix_v1.0.json
knowledge/workflow_schemas/knowledge_ingest_workflow_schema_v1.0.json
knowledge/validation_tasks/rule_candidate_validation_task_schema_v1.0.json
knowledge/merge_checks/knowledge_merge_check_schema_v1.0.json
knowledge/adoption_records/knowledge_adoption_record_schema_v1.0.json
knowledge/performance_monitors/performance_monitor_schema_v1.0.json
knowledge/metrics/role_knowledge_metrics_schema_v1.0.json
```

运行目录：

```text
knowledge/source_candidates/
knowledge/quality_scores/
knowledge/validation_tasks/
knowledge/scenario_traces/
knowledge/validation_summaries/
knowledge/validation_reviews/
knowledge/role_confirmations/
knowledge/merge_checks/
knowledge/promotion_decisions/
knowledge/adoption_records/
knowledge/performance_monitors/
knowledge/metrics/
knowledge/workflow_runs/
```

脚本：

```text
knowledge/scripts/intake_literature_source_v1_0.py
knowledge/scripts/score_source_quality_v1_0.py
knowledge/scripts/build_literature_card_v1_0.py
knowledge/scripts/build_rule_candidate_v1_0.py
knowledge/scripts/build_rule_candidate_validation_task_v1_0.py
knowledge/scripts/collect_scenario_trace_v1_0.py
knowledge/scripts/build_weekly_validation_summary_v1_0.py
knowledge/scripts/run_validation_review_v1_0.py
knowledge/scripts/request_role_confirmation_v1_0.py
knowledge/scripts/run_knowledge_merge_check_v1_0.py
knowledge/scripts/run_promotion_decision_v1_0.py
knowledge/scripts/write_active_rule_v1_0.py
knowledge/scripts/build_knowledge_adoption_record_v1_0.py
knowledge/scripts/run_performance_monitor_v1_0.py
knowledge/scripts/update_role_knowledge_metrics_v1_0.py
knowledge/scripts/run_knowledge_workflow_monitor_v1_0.py
knowledge/scripts/validate_knowledge_workflow_state_v1_0.py
```

## 10. 长周期监控与自动反馈

每条文献进入系统后生成 workflow run：

```text
workflow_id
source_id
current_state
next_required_action
owner_role
last_updated
deadline
blocked_reason
auto_fix_attempts
human_required
```

卡点规则：

```text
7 天未推进：WARN
14 天未推进：BLOCK
validator 失败：立即 WARN/BLOCK
依赖文件缺失：BLOCK
manifest 哈希漂移：自动修复
角色确认缺失：提醒角色，不自动代签
```

系统可自动修复：

```text
manifest sha/line 不一致
report 未登记 manifest
已登记文件路径存在但 hash 漂移
validator 报告缺低风险字段
G4/G5/G6 审计草稿缺失
合法卡片或候选未登记
状态机 next_required_action 未刷新
```

系统不能自动修复：

```text
文献质量争议
A 股适配是否成立
样本外验证是否通过
反例是否足以否决
青山确认
腰子确认
是否升为 active rule
是否废止旧知识
```

不能自动修复时必须生成：

```text
HumanInterventionRequest
```

字段：

```text
request_id
workflow_id
blocked_state
blocked_reason
required_role
files_to_review
suggested_options
deadline
```

## 11. KnowledgeMergeCheck 详细规则

入库前必须和角色存量知识库比对。

比对对象：

```text
knowledge/rules/role_capability_rules_v*.json
knowledge/roles/<role>/
knowledge/sources/legacy_role_kb/<role>/
knowledge/adoption_records/
knowledge/performance_monitors/
```

比对维度：

```text
语义相似度
适用场景
证据来源
角色职责
冲突关系
是否过时
是否只是补充边界
是否应进入反例库
是否应修订参数
```

输出必须明确：

```text
新增规则
合并旧规则
修订旧规则
废止旧规则
只入反例
只入参数
拒绝重复
```

## 12. PerformanceMonitor 详细规则

每条 active rule 入库后必须持续监控。

监控来源：

```text
日报引用记录
周报验证摘要
深度分析引用记录
荐股排序/否决记录
模拟交易动作边界记录
后评估归因记录
```

触发复审：

```text
连续多个周期无触发
触发后误导率超过阈值
胜率/命中率下滑
场景不匹配反复出现
后评估判定为误导
角色认为规则已过时
```

复审结果：

```text
keep_active
revise_scope
revise_rule_text
move_to_counterexample
deprecate
supersede
```

## 13. RoleKnowledgeMetrics 详细规则

每月生成角色能力指标。

通用指标：

```text
active_rule_count
candidate_count
validation_task_count
deprecated_rule_count
effective_knowledge_ratio
stale_knowledge_ratio
external_literature_conversion_rate
candidate_pass_rate
counterexample_count
last_updated
coverage_score
```

青山维度：

```text
因子有效性
IC/ICIR
样本外验证
因子衰减
过拟合防范
A 股适配
技术信号胜率
```

玉夜维度：

```text
字段口径
数据源可信度
数据可用等级
异常处理
时效性
硬/软/估算区分
```

流金维度：

```text
风险红线
止损/回撤
动作否决
仓位边界
交易审计
误用风险
```

信鸽维度：

```text
信息源等级
事件分类
公告证据
催化窗口
时效性
交叉验证
```

山猫维度：

```text
宏观覆写
行业相位
市场情绪
政策窗口
流动性
状态切换
```

腰子维度：

```text
整合裁决
状态机
结论强度
角色冲突处理
入库放行
废止判断
```

## 14. 正式入库记录

正式入库必须生成：

```text
knowledge/adoption_records/<active_rule_id>_adoption_record.md
```

必须包含：

```text
active_rule_id
来源文献
LiteratureCard ID
RuleCandidate ID
ValidationTask ID
ValidationReview ID
KnowledgeMergeCheck ID
PromotionDecision ID
验证周期
触发次数
关键证据
反例检查
误用风险
确认角色
为什么入库
适用范围
禁止误用
未来复查日期
废止条件
```

入库同步产物：

```text
active rule JSON
KnowledgeAdoptionRecord
PerformanceMonitor 初始文件
RoleKnowledgeMetrics 更新
manifest 登记
validator PASS
G4/G5/G6 审计文件
```

## 15. Fama/French 1993 首件样品状态

已完成：

```text
LiteratureCard：LC-QS-FF1993-001，card_draft
RuleCandidate：RC-QS-FF1993-FACTOR-VALIDITY-BOUNDARY-001，candidate_draft
```

未完成：

```text
RuleCandidateValidationTask
ScenarioTrace
WeeklyValidationSummary
ValidationReview
RoleConfirmation
KnowledgeMergeCheck
PromotionDecision
ActiveRule
KnowledgeAdoptionRecord
PerformanceMonitor
RoleKnowledgeMetrics
```

建议验证任务：

```text
验证类型：方法论规则
调用模块：
  日报：trace_only
  周报：weekly_summary
  后评估：promotion_review
  深度分析：trigger_when_external_factor_used
  荐股：not_applicable
  模拟交易：not_applicable

观察周期：至少 4 个周报周期
有效触发：至少 3 次
晋级条件：
  至少 1 次 A 股适配检查
  至少 1 次反例检查
  无重大误用风险
  KnowledgeMergeCheck 不是 reject_duplicate
  青山确认
  腰子确认
```

## 16. 红线

```text
不得从文献直接生成 active rule。
不得从 RuleCandidate 直接修改角色核心知识库。
不得绕过 ValidationTask 要求分析模块验证。
不得绕过 KnowledgeMergeCheck 新增规则。
不得绕过 PerformanceMonitor 让旧知识永远不复审。
不得绕过 RoleKnowledgeMetrics 假称能力提升。
不得绕过青山/腰子确认。
不得让周报、日报自行决定验证周期。
不得把长期状态依赖人工记忆。
不得让 manifest、validator、adoption record 三者不一致。
```

## 17. 落地顺序建议

第一阶段：验证任务层

```text
validation_policy_matrix_v1.0.json
rule_candidate_validation_task_schema_v1.0.json
RC_QINGSHAN_FAMA_FRENCH_1993_FACTOR_VALIDITY_BOUNDARY_validation_task_v1.0.json
validate_rule_candidate_validation_tasks_v1_0.py
```

第二阶段：工作流状态层

```text
knowledge_ingest_workflow_schema_v1.0.json
workflow_runs/
validate_knowledge_workflow_state_v1_0.py
run_knowledge_workflow_monitor_v1_0.py
```

第三阶段：融合与入库层

```text
knowledge_merge_check_schema_v1.0.json
run_knowledge_merge_check_v1_0.py
promotion_decision_schema_v1.0.json
write_active_rule_v1_0.py
```

第四阶段：入库记录与实战监控层

```text
knowledge_adoption_record_schema_v1.0.json
performance_monitor_schema_v1.0.json
role_knowledge_metrics_schema_v1.0.json
build_knowledge_adoption_record_v1_0.py
run_performance_monitor_v1_0.py
update_role_knowledge_metrics_v1_0.py
```

## 18. 一句话总结

```text
文献不是直接入库；
文献先成为卡片，卡片提炼候选，候选生成验证任务；
验证任务驱动分析模块留痕，后评估判断价值；
角色确认后先做新旧知识融合校验；
通过后才写 active rule；
入库后持续绑定实战表现，并量化角色能力成长。
```
