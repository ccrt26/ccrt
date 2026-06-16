# 重点股票产品化分析闭环总框架 v0.1

> 日期：2026-06-16
> 阶段：G2 总框架设计候选
> 定位：统一深度分析、每日分析、后评估/回测、规则治理和未来产品使用层的总架构。
> 边界：本文只定义总体框架、能力调用、契约边界和阶段路线；不直接修改生产规则、不切换运行入口、不放行任何回测或投资结论。

---

## 1. 一句话定位

重点股票产品化分析闭环不是单独的“后评估系统”，而是一套围绕重点股票长期使用的产品后端框架：

```text
深度分析形成 baseline
  -> 每日分析承接 baseline 并记录 delta/trigger
  -> 预测账本结构化保存可验证判断
  -> 特征与证据服务提供当时可见数据
  -> 后评估验证已发生判断
  -> 回测检验规则历史有效性
  -> 偏差归因生成规则候选
  -> 规则治理完成专项回测、shadow、灰度、放行、回滚
  -> 产品使用层向用户展示今日状态、股票详情、规则健康和证据下钻
```

核心目标：让系统从“生成分析报告”升级为“可持续验证、可追溯、可迭代、可产品化使用的分析闭环”。

完整产品化范围分为四条主线：

```text
A. 分析生产线产品化：深度分析、日报、baseline、sidecar、canonical、质量闸门、重跑和状态
B. 后评估/回测产品化：账本、特征、快照、前向验证、历史回测、偏差归因
C. 用户使用层产品化：今日驾驶舱、股票详情、规则健康、证据下钻、规则候选
D. 总集成与运营闭环：调度、状态机、自修复、审计、规则治理、知识反馈
```

因此，本框架不能只围绕后评估展开。后评估/回测是验证层，分析生产线是源头层；源头层不产品化，验证层会失去稳定输入。

---

## 2. 与地基四层架构的关系

本框架必须服从 `00_项目地基` 已定义的四层架构：

```text
治理地基
  -> 生产地基：D01-D12 原子能力域
  -> 场景编排：重点股票分析（深度分析/日报）
  -> 产物与闭环：CanonicalReport / ReportSidecar / EvalHook / AuditRecord
```

关键约束：

1. 重点股票分析是业务主场景，深度分析和日报是该场景的核心子模式。
2. 后评估/回测是验证与反馈层，不是独立业务场景。
3. 场景编排只能组合 D01-D12 能力，不得绕过标准能力接口直接自建数据链路。
4. 产物必须标准化，优先使用 `CanonicalReport`、`ReportSidecar`、`EvalHook`、`RuleUpdateCandidate` 等结构化对象。
5. Markdown 只作为人读方案、报告展示和阶段证据，不作为主执行逻辑。
6. 临时分析不纳入重点股票分析产品化主线；若未来需要引用临时分析结果，只能作为外部来源通过标准契约进入账本或证据链，不得混同为重点股票深度分析/日报子模式。

---

## 3. D01-D12 能力域映射

| 能力域 | 在本框架中的作用 | 当前处理原则 |
|:--|:--|:--|
| D01 数据采集与快照输入 | 获取行情、资金、事件、基础数据 | 复用已注册 `C-D01-0001` |
| D02 数据源/外部信息接入 | API、授权、外部事件源、成本限频 | 待后续补齐最小注册 |
| D03 数据治理与质量检查 | freshness、缺失、异常、降级 | 复用已注册 `C-D03-0001` |
| D04 数据中台与历史分析服务 | 历史 K 线、评分历史、特征面板、回测样本 | 复用已注册 `C-D04-0001`，作为特征服务和回测数据底座 |
| D05 证据抽取 | 从数据与报告中抽取证据包 | 复用已注册 `C-D05-0001` |
| D06 信号与特征计算 | 技术指标、评分、信号、收益标签 | 复用已注册 `C-D06-0001`，第一阶段需机器化核心子集 |
| D07 统一解读 | 汇总角色意见、反证、结论强度 | 复用已注册 `C-D07-0001` |
| D08 风控/交易解释辅助 | 风险灯、止损、仓位折扣、交易成本边界 | 需补最小契约，第一阶段至少预留字段 |
| D09 场景编排 | 深度分析、日报、后评估、回测、规则治理的流程组合 | 当前继续按场景治理，不急于注册为独立能力 |
| D10 报告/产物输出 | 报告、sidecar、canonical、状态 JSON、驾驶舱数据 | 以结构化产物为主，报告为展示层 |
| D11 后评估钩子 | EvalHook、到期验证、回填、复盘 | 建议后续注册 `C-D11-0001` |
| D12 知识反馈/运行闭环 | RuleUpdateCandidate、知识入库、规则生命周期 | 建议定义最小接口，不在第一阶段直接放行规则 |

---

## 4. 总体业务闭环

### 4.1 深度分析层

深度分析回答：

```text
这家公司中期怎么看？
核心假设是什么？
哪些证据支持？
哪些反证会改变判断？
风险边界在哪里？
未来日报应该跟踪什么？
```

深度分析必须产出或关联：

1. `baseline_id`
2. `source_report_path`
3. 核心逻辑和核心假设
4. 支撑/压力/止损/目标区间
5. 反证条件
6. 风险灯和风控边界
7. 可验证判断候选
8. 规则来源和规则版本
9. 数据快照引用

深度分析正文不是 baseline_id 权威源。baseline 权威源必须服从：

```text
00_项目地基/02_权威注册表/baseline_registry.json
```

### 4.2 每日分析层

每日分析回答：

```text
今天相对 baseline 发生了什么变化？
哪些 trigger 被触发？
是否改变原判断？
明日需要观察什么？
是否需要重做深度分析？
```

每日分析必须围绕 `baseline -> delta -> trigger` 三层模型执行：

1. `baseline`：只引用权威 baseline，不重算中期逻辑。
2. `delta`：记录当天价格、资金、事件、风险、板块状态变化。
3. `trigger`：判断支撑破位、风险灯变化、事件落空、数据不足等触发项。

日报必须产出 `ReportSidecar`，并通过 MD/sidecar 一致性闸门。

### 4.3 分析生产线产品化层

分析生产线回答：

```text
深度分析和日报如何稳定生成？
baseline 如何固化为产品对象？
sidecar/canonical 如何成为机器契约？
失败、缺数据、重跑、状态如何被系统处理？
```

这一层是完整产品化的源头层。它不等于写更复杂的分析逻辑，而是把已有分析能力变成可运行、可检查、可追溯、可重放的生产链路。

深度分析产品化最低要求：

1. 有稳定生成入口，入口登记到运行注册表或执行包中。
2. 输出报告必须关联 `baseline_id`、`source_report_path`、数据快照和规则版本。
3. baseline 写入或注册必须服从 `baseline_registry.json` 权威规则。
4. 反证条件、风险边界、支撑/压力、验证窗口必须进入机器可读 sidecar 或派生对象。
5. 生成失败必须输出结构化失败状态，不以缺报告静默结束。

日报产品化最低要求：

1. 日报只承接权威 baseline，不重算深度分析。
2. 必须稳定输出 `ReportSidecar`，且 MD/sidecar 一致性闸门可检查。
3. 必须输出 `eval_hooks` 或可转入 PredictionLedger 的机器字段。
4. 数据缺失、freshness、风险灯、动作变化必须有结构化状态。
5. 重跑必须幂等，不重复生成冲突账本或冲突 sidecar。

生产线共同能力：

```text
入口注册
输入校验
baseline 解析
数据 freshness 检查
报告/sidecar 生成
canonical shadow 构建
质量闸门
状态 JSON
失败恢复
重跑幂等
证据链索引
```

第一阶段不要求重构整个报告生成系统，但必须完成生产线资产盘点和最小契约确认，确保后评估/回测拿到的输入不是临时拼出来的。

### 4.4 预测账本层

预测账本回答：

```text
系统当时到底说过什么？
来自深度分析还是日报？
依据哪个 baseline、规则版本和数据快照？
什么时候该验证？
```

未来主账本建议从旧式 `predictions.csv` 升级为 JSONL 或 SQLite。旧 CSV 保留历史兼容，不作为产品化主账本。

账本最低字段：

```text
ledger_id
source_type: deep_analysis | daily_report
source_report_path
source_sidecar_path
stock_code
stock_name
trade_date
baseline_id
rule_version
data_snapshot_id
prediction_type
horizon
assertion
confidence
verification_windows
status
created_at
superseded_by
evidence_refs
```

### 4.5 特征与证据层

特征与证据层回答：

```text
在某个判断日，系统当时能看到什么数据？
后评估和回测能否复现当时输入？
有没有未来函数？
```

第一阶段特征服务只做核心子集：

1. 技术特征：MA、RSI、MACD、成交量、换手率。
2. baseline 特征：支撑、压力、止损、valid_until。
3. risk_flags 基础特征：质押、解禁、融资、北向等已有字段。
4. 收益标签：T+1/T+5/T+20/T+60、最大回撤、相对基准收益。

特征入口建议统一为：

```text
get_features(stock_code, trade_date, as_of_date, market_lag_days=0)
```

所有回测和后评估默认读取数据可见性快照。历史快照缺失时只能进入重建流程，并标记 `reconstructed_snapshot=true`。

### 4.6 后评估/回测层

后评估回答：

```text
系统已经说过的话，后来验证结果如何？
命中、偏离，还是数据不足无法判断？
偏差原因是什么？
```

回测回答：

```text
某类规则在历史上是否稳定有效？
是否存在弱规则、过拟合、样本不足、近期衰减或极端行情失效？
```

两者必须共用同一特征服务、规则版本和质量闸门，避免一套后评估口径、一套回测口径。

第一阶段回测只做 1-2 个完全可程序化规则试点，优先：

1. `MA20 破位止损`
2. 基础 `risk_flags` 风险预警

### 4.7 规则治理层

规则治理回答：

```text
后评估或回测发现的问题，是否值得变成规则修改？
新规则是否经过专项回测、shadow、灰度和回滚设计？
```

后评估/回测不得直接修改规则资产。它只能生成 `RuleUpdateCandidate`。

规则生命周期建议：

```text
draft
  -> candidate
  -> backtest_required
  -> shadow
  -> gray
  -> active
  -> degraded
  -> retired
  -> rollback
```

第一阶段只生成候选队列，不进入正式规则放行。

### 4.8 产品使用层

未来产品层回答：

```text
我今天该看什么？
某只股票为什么是这个状态？
哪些规则正在失效？
系统为什么这么判断？
哪些问题需要我确认？
```

前端可以后做，但后端第一阶段必须输出前端可消费数据。

未来页面建议：

1. 今日驾驶舱
2. 股票详情页
3. 规则健康页
4. 后评估/回测证据页
5. 规则候选队列页

---

## 5. 核心契约

### 5.0 AnalysisProductionContract

用途：统一深度分析和日报生产线的运行对象、状态、输入输出和失败处理。

关键字段：

```text
run_id
run_type: deep_analysis | daily_report
stock_code
stock_name
trade_date
baseline_id
input_refs
output_report_path
output_sidecar_path
canonical_report_ref
quality_gate_status
eval_hook_refs
ledger_write_status
data_freshness_status
status: PENDING | RUNNING | PASS | WARN | ALERT | BLOCK
failure_reason
retry_count
evidence_refs
created_at
updated_at
```

关键约束：

1. 深度分析和日报都必须有运行状态。
2. 报告成功但 sidecar 失败，不得标记为完整成功。
3. sidecar 成功但 MD/sidecar 不一致，必须 BLOCK 或 WARN，按现有闸门规则处理。
4. 账本写入失败时，报告可保留为人读产物，但闭环状态不得标 COMPLETE。

### 5.1 BaselineContract

用途：统一深度分析、日报、后评估对 baseline 的引用。

权威源：

```text
00_项目地基/02_权威注册表/baseline_registry.json
```

关键字段：

```text
baseline_id
stock_code
stock_name
baseline_date
valid_until
source_report_path
core_thesis
key_support_price
key_pressure_price
stop_loss_price
risk_flags
counter_evidence
trigger_signals
data_snapshot
```

### 5.2 DailyDeltaContract

用途：统一日报相对 baseline 的每日变化记录。

关键字段：

```text
stock_code
trade_date
baseline_id
p0_decision_card
delta.price_change
delta.fund_flow_4level
delta.margin_trading
delta.northbound
delta.sector_phase
delta.news_events
trigger
risk_light
data_completeness
eval_hooks
```

### 5.3 PredictionLedgerContract

用途：统一深度分析和日报中的可验证判断。

判断类型：

1. 方向性判断
2. 区间判断
3. 触发条件判断
4. 风险预警判断
5. 事件判断

关键约束：

1. 必须幂等，重跑不重复入账。
2. 必须记录来源报告、sidecar、baseline、规则版本、数据快照。
3. 低置信度解析只能 WARN，不进入正式回测。

### 5.4 FeatureSnapshotContract

用途：为后评估和回测提供同口径输入。

最低字段：

```text
snapshot_id
stock_code
trade_date
as_of_date
generated_at
available_sources
freshness_status
feature_values
label_values
baseline_id
rule_version
data_lineage_refs
reconstructed_snapshot
quality_flags
```

### 5.5 EvaluationResultContract

用途：统一后评估和回测输出。

结果状态：

```text
HIT
MISS
PARTIAL
INSUFFICIENT_DATA
PENDING
OBSERVE
BLOCK
```

偏差归因：

```text
data_gap
rule_weakness
hypothesis_error
market_noise
execution_carryover_error
event_delay
sample_insufficient
future_function_risk
```

### 5.6 RuleCandidateContract

用途：把验证结果转成规则候选，而不是直接改规则。

关键字段：

```text
candidate_id
source_eval_ids
source_backtest_ids
affected_rule_ids
problem_statement
proposed_change
evidence_summary
risk_assessment
required_backtest
shadow_plan
rollback_plan
status
created_by
review_required_by
```

### 5.7 DashboardStatusContract

用途：让未来前端直接消费后端状态。

第一阶段建议输出：

```text
dashboard_status.json
analysis_pipeline_status.json
stock_health.json
prediction_ledger.jsonl
rule_backtest_result.json
alert_center.json
evidence_trace.json
rule_candidate_queue.json
```

总状态只暴露三类：

```text
COMPLETE
AUTO_REPAIRING
BLOCK
```

详情保留：

```text
WARN
ALERT
BLOCK
```

---

## 6. 阶段路线

### Phase 0：总框架定版

目标：统一重点股票分析闭环的全局边界，明确分析生产线、后评估/回测、规则治理、产品使用层的分工。

产物：

1. 总框架 v0.1
2. 技术团队确认清单
3. 分析生产线产品化子方案方向
4. 后评估/回测后端子方案修订方向
5. 第一阶段 MVP 边界

不做：

1. 不改生产规则
2. 不改调度入口
3. 不注册新能力
4. 不生成正式回测结论

### Phase 1：重点股票产品化后端 MVP

目标：先让一条重点股票链路从分析生产线到验证层形成最小产品闭环。

范围：

```text
分析生产线资产盘点
深度分析/baseline/日报 sidecar 契约确认
AnalysisProductionStatus 最小状态
PredictionLedger 最小账本
FeatureSnapshot 核心特征
数据可见性快照
MA20 单规则回测
前向后评估雏形
dashboard_status / alert_center JSON
```

验收：

1. 能扫描现有深度分析、baseline、日报 sidecar、后评估脚本和数据资产。
2. 能确认深度分析和日报的最小机器契约缺口。
3. 能输出分析生产线最小运行状态。
4. 能从深度分析/日报生成可验证账本记录。
5. 能按当时可见数据返回核心特征。
6. 能跑通一个完全可程序化规则。
7. 能输出机器可读状态与告警。

### Phase 2：后端产品化

目标：把 Phase 1 MVP 从脚本能力升级为稳定后端能力。

范围：

```text
分析生产线状态机
报告生成重跑幂等
统一状态机
幂等与 replay
DAG 调度
自动修复
专项回测队列
RuleUpdateCandidate
证据链索引
运行健康指标
```

### Phase 3：前端/驾驶舱

目标：让用户日常真正好用。

页面：

1. 今日驾驶舱
2. 股票详情页
3. 规则健康页
4. 后评估/回测证据页
5. 规则候选页

### Phase 4：规则治理与扩展

目标：从验证系统升级为规则迭代系统。

范围：

```text
shadow 规则
灰度验证
正式放行
回滚
财务特征
事件研究
拥挤度指标
跨市场状态分层
```

### Phase 5：运营闭环与长期治理

目标：让系统可长期运行、审计、复盘和演进。

范围：

```text
运行 SLO
数据授权与成本治理
密钥脱敏
历史归档与 replay
知识反馈入库
规则退役和回滚
跨阶段审计报表
```

---

## 7. 技术团队待确认清单

### 7.0 分析生产线

1. 深度分析当前权威生成入口是什么，是否已登记到 runtime/执行包。
2. 深度分析是否已有稳定 sidecar，若没有，Phase 1 是否只做字段盘点和契约缺口。
3. 日报 v3.6 sidecar 是否能稳定承接 `baseline -> delta -> trigger -> eval_hooks`。
4. `canonical_report` 是否继续 shadow-only，Phase 1 是否只读检查，不切真实链路。
5. 报告生成失败、sidecar 失败、账本写入失败分别如何映射到 `AnalysisProductionStatus`。
6. 深度分析和日报的重跑幂等键如何定义。
7. Phase 1 是否需要选择一只样例股票跑通分析生产线到后评估的最小链路。

### 7.1 权威契约

1. `baseline_registry.json` 是否继续作为 baseline 唯一权威源。
2. `baseline.schema.json` 是否升级为 `BaselineContract` 的实现 schema。
3. 日报 v3.6 sidecar 是否能稳定输出机器字段，是否需要新增 sidecar 生成器。
4. `predictions.csv` 是否退为历史兼容，未来主账本改为 JSONL 或 SQLite。
5. `canonical_report` 是否继续作为影子对象承接日报产物，暂不切真实链路。

### 7.2 D01-D12 能力域

1. D04 数据中台是否作为特征服务和回测样本的唯一后端底座。
2. D08 是否先补最小风控解释契约。
3. D11 是否注册为 `C-D11-0001` 后评估钩子能力。
4. D12 是否定义 RuleUpdateCandidate 与知识反馈最小接口。
5. D09 是否继续作为场景治理，不急于注册为单独能力。

### 7.3 第一阶段实现

1. 第一阶段是否同时覆盖“分析生产线最小状态 + 后评估/回测最小闭环”。
2. 第一阶段特征服务是否只覆盖技术特征、baseline、risk_flags、收益标签。
3. 数据可见性快照放在哪里，是否长期保留。
4. 回测引擎第一条试点规则选 `MA20 破位止损` 还是基础 `risk_flags`。
5. 告警中心第一阶段是否只输出 JSON，暂不做 UI。
6. 规则候选第一阶段是否只生成队列，不进入正式规则修改。
7. 是否保留现有后评估报告生成逻辑作为人读输出，但不再作为主执行入口。
8. 未来前端需要的 API/JSON 字段是否在 Phase 1 固化。

### 7.4 调度与运行

1. 是否复用 `runtime_entry_registry.json` 中的 launchd/runtime 规则。
2. 是否新增后评估调度入口，或先由现有 `post_eval`/daily workflow 承接。
3. 自动修复失败 3 次进入 BLOCK 的状态是否接入统一告警。
4. 调度是否从第一阶段开始只做手动触发，Phase 2 再接 DAG。

### 7.5 测试与审计

1. 第一阶段最低测试是否包括 schema test、golden sample、negative test。
2. 未来函数检查是否作为 BLOCK gate。
3. 样本不足是否统一标 `OBSERVE`，不得给确定性结论。
4. G5 独立复查是否必须覆盖角色边界、证据链、文件范围和阶段门。

---

## 8. 禁止事项

1. 不把后评估设计成独立于深度分析和日报的孤立系统。
2. 不重建数据仓库；必须复用 D04 数据中台与历史分析服务。
3. 不让 Markdown 承担执行逻辑。
4. 不让回测结果绕过规则治理直接改正式规则。
5. 不让日报重新计算深度 baseline。
6. 不用当前股票池替代历史股票池，避免幸存者偏差。
7. 不把事件样本不足误判为规则无效。
8. 不把用户界面延期理解为可以不做前端契约。
9. 不把 dry-run 会审候选当作 G5/G6 正式签字。
10. 不在未通过 G2 技术拆包前进入 G3 实施。
11. 不把“后评估产品化完成”误写成“重点股票分析产品化完成”。
12. 不把临时分析、每日荐股、重点股票日报混成同一场景。

---

## 9. 与当前后评估方案的关系

当前文件：

```text
00_项目地基/06_后评估闭环/PLAN_重点股票产品化后评估回测架构_v0.1.md
```

建议后续升级为子方案：

```text
PLAN_重点股票产品化后评估回测后端架构_v0.2.md
```

两者关系：

| 文件 | 定位 |
|:--|:--|
| 总框架 v0.1 | 定义重点股票产品化分析闭环的全局架构 |
| 后评估/回测后端 v0.2 | 在总框架下定义 D11/D04/D06/D12 相关后端落地 |

总框架不替代后评估/回测子方案；后评估/回测子方案也不应继续承载全部产品总架构。

---

## 10. 建议下一步

下一步不直接进入 G3。

建议顺序：

```text
1. 技术团队围绕本文件第 7 节确认关键问题
2. 新增或补充“重点股票分析生产线产品化方案”
3. 对齐后评估/回测后端子方案 v0.2
4. 抽出覆盖分析生产线 + 后评估/回测的 Phase 1 后端 MVP 执行包
5. 用户确认后再进入 G3 实施
```

Phase 1 推荐第一目标：

```text
分析生产线资产盘点
  -> 深度分析/baseline/日报 sidecar 契约缺口
  -> AnalysisProductionStatus 最小状态
  -> PredictionLedger 最小账本
  -> FeatureSnapshot 核心特征
  -> MA20 单规则回测
  -> 前向后评估雏形
  -> dashboard_status / alert_center JSON
```

---

## 11. 用户可见结论

本框架确认：重点股票项目应按“产品化分析闭环”设计，而不是按单独的后评估工具设计。

后端可以先做，前端可以后做；但后端必须从第一阶段就输出稳定的结构化契约、状态、证据链和可追溯对象，确保未来产品层可以自然接上。

当前状态：

```text
G2 总框架候选完成
未进入 G3 实施
未修改生产规则
未切换运行入口
未放行任何回测结论
```

---

## 12. 分步会话与用户确认点

用户计划每个步骤开启一个新会话。为避免用户记忆所有决策点，后续每个新会话启动时，执行方必须先读取本节，判断是否存在必须询问用户的问题；若存在，先问用户，再继续自动化执行。

原则：

1. 用户不需要记住全部阶段细节。
2. 每个步骤开始时，由执行方主动提示本步骤需要用户确认的最少问题。
3. 用户确认后，除非遇到 BLOCK、范围扩大、生产入口变更、新数据源/API、角色边界冲突，否则后续自动推进。
4. 不得因为缺少非关键偏好而阻塞可自动完成的盘点、校验、整理和方案草案。

### 12.1 八步会话规划

| 步骤 | 会话目标 | 是否需要用户先给意见 | 新会话启动时必须先问的问题 | 用户确认后自动执行内容 |
|:--|:--|:--:|:--|:--|
| 1 | 总框架与边界定版 | 是 | 是否确认重点股票主线只包含深度分析和日报，不包含临时分析；是否确认先后端、前端契约先行 | 修订总框架、整理边界、输出待确认清单 |
| 2 | 分析生产线资产盘点 | 通常否 | 只有发现多个权威入口冲突时，才问用户裁定哪个入口为准 | 扫描深度分析、日报、baseline、sidecar、canonical、闸门、运行入口并输出 inventory |
| 3 | 分析生产线产品化方案 | 是 | 用户每天打开系统最想先看什么；哪些失败必须提醒；是否需要一键重跑某只股票 | 设计 AnalysisProductionContract、状态、重跑幂等、告警和生产线子方案 |
| 4 | 后评估/回测方案对齐定版 | 轻量确认 | 是否确认第一条试点规则为 MA20 破位止损；是否暂缓财务/事件/拥挤度 | 修订后评估/回测 v0.2，和分析生产线方案对齐 |
| 5 | Phase 1 后端 MVP 执行包 | 是 | 是否允许进入 G3；允许新增哪些目录/文件；哪些生产目录禁止触碰 | 生成精准执行包、文件清单、验收命令、回滚证明 |
| 6 | Phase 1 实施 | 仅异常时 | 启动时只确认是否按第 5 步执行包实施；实施中遇到入口冲突、新 API、生产目录修改再问 | 新增 schema、脚本、测试、状态 JSON，跑最小链路 |
| 7 | G4/G5 验收与补修 | 通常否 | 只有 WARN 是否接受、非关键能力是否延期、是否进入下一阶段需要用户确认 | 执行自检、复查候选、补修、证据汇总 |
| 8 | Phase 2/3 产品化扩展 | 是 | 今日驾驶舱第一屏看什么；股票详情页怎么组织；规则健康页看哪些指标；哪些操作一键化 | 设计后端增强、前端/驾驶舱、长期治理路线 |

### 12.2 强制用户确认点

以下情况必须暂停并询问用户：

1. 进入 G3 实施前。
2. 需要修改生产报告目录、正式规则资产、baseline registry、runtime entry、launchd 调度时。
3. 需要接入新数据源、付费 API、token、cookie 或批量下载时。
4. 发现深度分析或日报存在多个权威入口，且无法从地基文件自动裁定时。
5. 第一阶段样例股票选择会影响用户使用优先级时。
6. 是否接受关键 WARN、是否延期某个 Phase 1 验收项时。
7. 进入前端/驾驶舱设计时。
8. 进入 G6 放行/归档前，如阶段政策要求用户确认。

### 12.3 可自动执行点

以下事项默认自动执行，不需要用户逐项批准：

1. 只读资产盘点。
2. 读取地基、schema、注册表、现有脚本和报告结构。
3. 生成 G2 方案草案。
4. 生成待确认问题清单。
5. 在非生产目录输出草案、inventory、候选 JSON。
6. 运行只读校验、schema 校验、Python 编译和测试命令。
7. 对同阶段已暴露的问题做不扩大范围的补修方案。

### 12.4 新会话启动提示模板

后续用户开启新会话并说明步骤时，执行方应先输出：

```text
已读取总框架 §12。
当前步骤：【第 X 步：步骤名称】
本步骤是否需要用户先确认：【是/否/仅异常时】
本步骤需要先问你的问题：
1. ...
你确认后，我将自动执行：
1. ...
```

用户回答后，再进入该步骤的自动化执行或方案产出。
