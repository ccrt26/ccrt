# L2 KB 知识进化：外部文献到正式入库全流程方案 v1.0

## 1. 定位

本文档定义金融团队从外部文献、权威资料、项目经验中吸收知识，并最终写入角色正式知识库的完整流程。

它解决的问题不是“把一篇文献放进知识库”，而是：

```text
文献进入系统
→ 系统提炼候选
→ 候选生成验证任务
→ 分析模块按任务留痕
→ 后评估判断是否有价值
→ 角色确认
→ 正式入库
→ 持续监控
```

本流程适用于青山，也适用于玉夜、流金、信鸽、山猫、腰子等角色。不同角色的判断内容不同，但流程入口、状态机、审计和入库方式必须统一。

## 2. 总原则

### 2.1 统一入口，角色分领域判断

文献收集不由每个角色各自随便找，也不由某一个角色独自判断。

采用两层机制：

```text
系统/阿黑统一收集、去重、登记、分发；
角色按职责判断专业价值、验证档位、是否继续推进。
```

分工如下：

```text
阿黑/系统：定时任务、收集、去重、分发、状态跟踪。
青山：因子、信号、技术有效性、样本外、衰减、过拟合。
玉夜：数据口径、数据质量、字段可信度、证据可用性。
流金：风险边界、交易纪律、否决项、动作审计。
信鸽：公告、事件、催化剂、信息源等级、事件窗口。
山猫：宏观、行业、市场环境、状态切换。
腰子：整合裁决、结论强度、状态机、是否进入整体决策体系。
旧影：复查是否越界、是否破坏流程边界。
```

### 2.2 程序推动流程，角色判断质量

程序负责：

```text
定时收集
生成候选
生成卡片
生成验证任务
维护 manifest
执行 validator
监控流程卡点
自动修复低风险账务问题
```

角色负责：

```text
专业判断
验证结论
确认是否晋级
确认是否写入 active rule
```

### 2.3 候选不等于正式知识

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

## 3. 文献收集机制

### 3.1 是否需要定时任务

需要。文献收集应长期运行，不能靠人工想起来才做。

建议节奏：

```text
每 2 周：轻量收集
每 1 月：深度整理
每季度：全局缺口复盘
随时：人工指定资料入口
```

### 3.2 定时任务分层

轻量收集任务：

```text
literature_discovery_job
周期：每 2 周
职责：发现新资料、去重、登记、生成 SourceCandidate、建议 owner_role。
不做：最终价值判断、规则生成、active rule 更新。
```

深度整理任务：

```text
literature_quality_review_job
周期：每 1 月
职责：对 SourceCandidate 做质量评分、合并重复资料、清理过期资料、推进 LiteratureCard。
```

人工指定入口：

```text
manual_source_intake_job
触发：用户或角色明确指定资料
职责：立即生成 SourceCandidate，并进入同一套质量评分流程。
```

季度缺口复盘：

```text
literature_gap_review_job
周期：每季度
职责：检查各角色资料是否偏科、是否长期无更新、是否缺少关键能力文献。
```

## 4. 12 步状态机

外部资料到正式入库必须走统一状态链。

```text
SourceCandidate
→ QualityScore
→ LiteratureCard
→ RuleCandidate
→ RuleCandidateValidationTask
→ ScenarioTrace
→ WeeklyValidationSummary
→ ValidationReview
→ RoleConfirmation
→ PromotionDecision
→ ActiveRule
→ KnowledgeAdoptionRecord
```

### 4.1 Step 1：SourceCandidate

回答：

```text
这份资料是什么？
来源是否可追溯？
可能属于哪个角色？
是否明显低质或无关？
```

输入：

```text
外部文献、数据源、交易所公告、监管文件、研究论文、用户指定资料。
```

输出：

```text
SourceCandidate
```

禁止：

```text
不得直接生成 LiteratureCard。
不得直接生成 RuleCandidate。
不得直接影响报告结论。
```

### 4.2 Step 2：QualityScore

回答：

```text
这份资料质量如何？
是否具备方法、样本、证据、可追溯性？
是否适合进入文献卡片？
```

评分维度包括：

```text
权威性
方法透明度
样本质量
可复现性
适用市场
过拟合风险
与角色职责相关性
```

输出：

```text
QualityScore
```

状态：

```text
quality_pass
quality_pass_with_cross_check
quality_background_only
quality_reject
```

### 4.3 Step 3：LiteratureCard

回答：

```text
这篇资料讲了什么？
证据在哪里？
适用边界是什么？
不能怎么用？
```

输出：

```text
LiteratureCard
```

初始状态：

```text
card_draft
```

边界：

```text
可以登记为文献卡片。
不得直接生成 active rule。
不得直接进入正式投研结论。
```

### 4.4 Step 4：RuleCandidate

回答：

```text
这篇文献可能让我们新增什么规则想法？
这个想法需要哪些验证？
有哪些误用风险？
```

输出：

```text
RuleCandidate
```

初始状态：

```text
candidate_draft
```

示例：

```text
青山引用非 A 股外部因子文献时，只能先作为方法论和验证框架使用；
不得因为文献权威或评分高，直接写成 A 股 active rule。
```

### 4.5 Step 5：RuleCandidateValidationTask

回答：

```text
这个候选要在哪些分析模块中验证？
验证多久？
触发条件是什么？
谁负责留痕？
什么情况下晋级、拒绝、继续观察？
```

输出：

```text
RuleCandidateValidationTask
```

这是连接候选规则与周报、日报、后评估、深度分析等模块的核心。

### 4.6 Step 6：ScenarioTrace

回答：

```text
某个分析模块本次是否触发了验证任务？
留下了什么证据？
有没有反例或误用风险？
```

输出：

```text
ScenarioTrace
```

日报、深度分析、荐股、模拟交易等模块主要负责留痕，不做最终晋级判断。

### 4.7 Step 7：WeeklyValidationSummary

回答：

```text
本周触发几次？
证据是否支持候选？
有没有反例？
是否继续观察？
```

输出：

```text
WeeklyValidationSummary
```

周报只做汇总，不直接入库。

### 4.8 Step 8：ValidationReview

回答：

```text
候选规则是否提升判断？
是否误导？
问题是适用边界、参数、数据，还是规则本身不成立？
```

输出：

```text
ValidationReview
```

可能结论：

```text
continue_observation
validation_passed
rejected
counterexample_only
parameter_candidate
```

### 4.9 Step 9：RoleConfirmation

回答：

```text
相关角色是否确认候选规则成立？
是否符合角色职责？
是否会污染其他角色边界？
```

不是所有角色都参与，只叫相关角色。

示例：

```text
青山：确认因子/信号逻辑是否成立。
玉夜：确认数据口径和证据质量。
流金：确认风险红线和动作边界。
信鸽：确认事件证据和催化窗口。
山猫：确认宏观环境适用性。
腰子：确认整体决策体系可吸收。
```

### 4.10 Step 10：PromotionDecision

回答：

```text
是否允许从候选进入正式入库？
是否只进入反例库、参数库、背景库？
```

可能结果：

```text
promote_to_active_rule
keep_observing
reject
counterexample_only
parameter_candidate
background_only
```

### 4.11 Step 11：ActiveRule

回答：

```text
正式规则是什么？
适用范围是什么？
禁止误用是什么？
版本和废止条件是什么？
```

写入后才允许被正式报告自动引用。

必须记录：

```text
active_rule_id
source_card_id
rule_candidate_id
validation_task_id
确认角色
生效日期
适用范围
废止条件
```

### 4.12 Step 12：KnowledgeAdoptionRecord

回答：

```text
这条知识为什么入库？
来自哪些文献？
经历了哪些验证？
谁确认过？
以后如何复查或废止？
```

输出：

```text
KnowledgeAdoptionRecord
```

它是给人读的入库记录，必须和 active rule 同步生成。

## 5. 前后依赖关系

每一步必须等前置产物通过 validator。

```text
没有 SourceCandidate，不能 QualityScore。
没有 QualityScore PASS，不能 LiteratureCard。
没有 LiteratureCard，不能 RuleCandidate。
没有 RuleCandidate，不能 ValidationTask。
没有 ValidationTask，不能要求周报/日报验证。
没有足够观察周期，不能进入 RoleConfirmation。
没有 RoleConfirmation，不能 PromotionDecision。
没有 PromotionDecision PASS，不能 ActiveRule。
没有 ActiveRule，不能生成最终 KnowledgeAdoptionRecord。
```

任何脚本必须检查依赖状态，不允许跳步。

## 6. 验证档位矩阵

不同知识的验证周期不同。系统不应每次从零讨论，而应先套默认档位。

建议固化为：

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

高影响候选可升级人工讨论。

## 7. 分析模块调用规则

分析模块不自己决定是否调用候选验证任务。调用关系由 `RuleCandidateValidationTask` 定义，并由 KRM router 分发。

示例：

```text
daily_report: trace_only
weekly_report: weekly_summary
post_evaluation: promotion_review
deep_analysis: trigger_when_external_factor_used
stock_recommendation: not_applicable
simulated_trading: not_applicable
```

职责划分：

```text
日报：记录触发事实、证据、反例、误用风险。
周报：汇总一周触发情况，不直接入库。
后评估：判断候选是否晋级、拒绝、继续观察。
深度分析：触发相关候选时做边界检查。
荐股：仅在 ValidationTask 明确要求时检查排序/否决。
模拟交易：仅在 ValidationTask 明确要求时检查动作边界。
```

## 8. 定时任务设计

### 8.1 任务清单

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

validation_progress_monitor_job
周期：每日或每周
输出：WorkflowMonitorReport

manifest_integrity_job
触发：每次写文件后 + 每日巡检
输出：manifest integrity report

stale_candidate_cleanup_job
周期：每月
输出：长期无触发候选清理建议

literature_gap_review_job
周期：每季度
输出：角色文献缺口复盘
```

### 8.2 任务依赖

```text
source_discovery_job
→ source_quality_scoring_job
→ literature_card_builder_job
→ rule_candidate_builder_job
→ validation_task_builder_job
→ scenario_trace_collector_job
→ weekly_validation_summary_job
→ validation_progress_monitor_job
```

`manifest_integrity_job` 独立运行，但每次写文件后必须触发。

## 9. 长周期监控与自动反馈

12 步流程跨度长，必须有状态机和监控。

建议目录：

```text
knowledge/workflow_runs/
```

每条文献进入系统后生成：

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

### 9.1 卡点规则

```text
7 天未推进：WARN
14 天未推进：BLOCK
validator 失败：立即 WARN/BLOCK
依赖文件缺失：BLOCK
manifest 哈希漂移：自动修复
角色确认缺失：提醒角色，不自动代签
```

### 9.2 系统可以自动修复的问题

```text
manifest sha/line 不一致
report 未登记 manifest
已登记文件路径存在但 hash 漂移
validator 报告缺低风险字段
G4/G5/G6 审计草稿缺失
合法卡片或候选未登记
状态机 next_required_action 未刷新
```

### 9.3 系统不能自动修复的问题

```text
文献质量争议
A 股适配是否成立
样本外验证是否通过
反例是否足以否决
青山确认
腰子确认
是否升为 active rule
```

不能自动修复时必须生成：

```text
HumanInterventionRequest
```

包含：

```text
卡在哪一步
为什么不能自动修
需要谁判断
需要看哪些文件
建议选项
截止时间
```

## 10. 正式入库记录

正式入库必须生成给人读的记录。

建议目录：

```text
knowledge/adoption_records/
```

记录文件：

```text
KnowledgeAdoptionRecord
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
确认角色
为什么入库
适用范围
禁止误用
未来复查日期
废止条件
```

正式入库至少同步产生：

```text
active rule JSON
KnowledgeAdoptionRecord 人类可读文档
manifest 登记
validator PASS
G4/G5/G6 审计文件
```

## 11. 自动化成熟目标

成熟后外部文献入口应收敛成一个主命令：

```text
python3 knowledge/scripts/intake_literature_source_v1_0.py --source <文献信息>
```

系统自动推进到：

```text
SourceCandidate
QualityScore
LiteratureCard
RuleCandidate
RuleCandidateValidationTask
```

然后停在观察期。

观察期中，系统自动：

```text
日报留痕
周报汇总
后评估归因
监控是否卡住
提醒角色确认
```

唯一不能自动完成的是：

```text
是否升为 active rule
```

该步骤必须由相关角色和腰子确认。

## 12. Fama/French 1993 首件样品状态

当前首件样品已经完成：

```text
SourceCandidate：通过人工指定入口进入
QualityScore：quality_pass_with_cross_check
LiteratureCard：LC-QS-FF1993-001，card_draft
RuleCandidate：RC-QS-FF1993-FACTOR-VALIDITY-BOUNDARY-001，candidate_draft
```

仍未完成：

```text
RuleCandidateValidationTask
ScenarioTrace
WeeklyValidationSummary
ValidationReview
RoleConfirmation
PromotionDecision
ActiveRule
KnowledgeAdoptionRecord
```

该样品的建议验证任务：

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
  青山确认
  腰子确认
```

## 13. 建议下一阶段产物

为把本文档程序化，下一阶段建议新增：

```text
knowledge/policies/validation_policy_matrix_v1.0.json
knowledge/workflow_schemas/knowledge_ingest_workflow_schema_v1.0.json
knowledge/validation_tasks/rule_candidate_validation_task_schema_v1.0.json
knowledge/validation_tasks/RC_QINGSHAN_FAMA_FRENCH_1993_FACTOR_VALIDITY_BOUNDARY_validation_task_v1.0.json
knowledge/workflow_runs/
knowledge/adoption_records/
knowledge/scripts/build_rule_candidate_validation_task_v1_0.py
knowledge/scripts/validate_rule_candidate_validation_tasks_v1_0.py
knowledge/scripts/run_knowledge_workflow_monitor_v1_0.py
knowledge/scripts/validate_knowledge_workflow_state_v1_0.py
```

## 14. 红线

```text
不得从文献直接生成 active rule。
不得从 RuleCandidate 直接修改角色核心知识库。
不得绕过 ValidationTask 要求分析模块验证。
不得绕过青山/腰子确认。
不得让周报、日报自行决定验证周期。
不得把长期状态依赖人工记忆。
不得让 manifest、validator、adoption record 三者不一致。
```

## 15. 一句话总结

```text
文献不是直接入库；
文献先成为卡片，卡片提炼候选，候选生成验证任务；
分析模块按任务留痕，后评估判断价值；
角色确认后才写入 active rule，并生成可读入库记录。
```
