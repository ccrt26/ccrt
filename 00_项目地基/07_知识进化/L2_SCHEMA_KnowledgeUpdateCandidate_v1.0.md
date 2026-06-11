# L2 SCHEMA KnowledgeUpdateCandidate v1.0

> 日期：2026-06-10
> 流程编号：F-KNOW + F-EVAL + F-ANALYSIS + F-ROLE
> 阶段门：G3-1
> 历史上游方案（已归档，日常执行不读）：`00_项目地基/99_归档/01_过程接力包/运行化与知识库进化_20260610/L2_KB_金融团队知识库进化重构方案_G1G2_v1.0.md`
> 关联：
> - `00_项目地基/07_知识进化/L2_INDEX_知识进化总账_v1.0.md`
> - `00_项目地基/07_知识进化/counterexamples/L2_COUNTEREXAMPLE_INDEX_v1.0.md`
> - `00_项目地基/07_知识进化/parameters/L2_PARAMETER_INDEX_v1.0.md`
> - `00_项目地基/07_知识进化/evolution_candidates/`

---

## 1. 目的与使用边界

### 1.1 这个 schema 做什么

KnowledgeUpdateCandidate 是后评估产出知识更新候选的标准化契约。每份后评估报告在完成归因分析后，必须生成 0-N 条候选，而不是只写"判断对/错"。

### 1.2 这个 schema 不做什么

1. 不授权自动写入核心知识库。
2. 不授权自动修改参数、权重、否决项。
3. 不授权执行模型代替角色签字。
4. 不代表候选被采纳——候选只进入评审流程。

### 1.3 谁产出

后评估（B 层）的执行者，即执行模型起草，对应角色建议，腰子确认后进入评审流程。

---

## 2. 字段定义

### 2.1 标识与来源

| 字段 | 类型 | 必填 | 说明 | 示例 |
|:-----|:----:|:----:|:-----|:-----|
| candidate_id | string | 是 | 全局唯一 ID | `KUC-20260610-QINGSHAN-001` |
| source_type | enum | 是 | 候选来源报告类型 | `weekly_report` |
| source_ref | string | 是 | 来源文件路径或引用标识 | `00_项目地基/06_后评估闭环/东睦周报后评估_v1.0.md` |
| stock_code | string | 否 | 涉及单一标的时填写 | `600114` |
| scenario | string | 是 | 适用场景 | `深度周报` |

### 2.2 角色归属

| 字段 | 类型 | 必填 | 说明 | 示例 |
|:-----|:----:|:----:|:-----|:-----|
| owner_role | string | 是 | 首要确认角色 | `青山` |
| related_roles | string[] | 否 | 需要联审的角色 | `["玉夜", "腰子"]` |

### 2.3 归因与建议

| 字段 | 类型 | 必填 | 说明 | 枚举值 / 示例 |
|:-----|:----:|:----:|:-----|:--------------|
| attribution_type | enum | 是 | 失败或偏差的归因类型 | `data` / `parameter` / `weight` / `evidence_level` / `analysis_logic` / `presentation` / `execution` / `strategy_environment` |
| observed_failure | string | 是 | 后评估观察到的问题描述 | `"技术修复后走势未延续，突破信号有效天数低于预期"` |
| proposed_update | string | 是 | 建议更新的具体内容 | `"将技术修复确认窗口从 3 个交易日延长至 5 个交易日，同时增加量能倍数验证条件"` |
| target_layer | enum | 是 | 建议更新的目标层级 | `core` / `adapter` / `evolution` / `counterexample` / `parameter` |

### 2.4 置信度与证据

| 字段 | 类型 | 必填 | 说明 | 约束 |
|:-----|:----:|:----:|:-----|:-----|
| confidence | enum | 是 | 提案者对候选的置信度 | `low` / `medium` / `high` |
| evidence_refs | string[] | 是 | 证据引用列表，至少 1 条 | 必须包含可追溯的来源路径或记录 |
| risk_if_applied | string | 是 | 若采纳可能造成的副作用 | 不能为空，可写 `"无明显风险"` |
| risk_if_ignored | string | 是 | 若忽略可能重复发生的问题 | 不能为空，可写 `"无明显风险"` |

### 2.5 决策状态

| 字段 | 类型 | 必填 | 说明 | 允许值 |
|:-----|:----:|:----:|:-----|:-------|
| decision_status | enum | 是 | 候选当前状态 | `proposed` / `role_review` / `approved` / `final_review` / `applied` / `rejected` / `parked` / `superseded` / `closed` |
| final_decision_ref | string | 否 | 角色确认或审计记录 | 候选被 `applied` 后必须填写 |

### 2.6 可选扩展字段

| 字段 | 类型 | 说明 | 何时使用 |
|:-----|:----:|:-----|:---------|
| context | string | 市场环境、行业相位、标的状态快照 | 需要评估适用边界时 |
| failure_path | string | 从判断到失败的路径描述 | 归因为 `analysis_logic` 时 |
| linked_cases | string[] | 关联的反例 case_id | 已有对应反例记录时 |
| epoch_markers | string | 判断作出时的关键参数值快照 | 后评估需要对比参数基线时 |

---

## 3. 状态机

```
                    ┌───────────┐
                    │ proposed  │
                    └─────┬─────┘
                          │
              ┌───────────┼───────────┐
              │           │           │
     ┌────────▼────┐    ╔══╧══╗    ┌─┴─────────┐
     │ role_review │    ║ REJ ║    │  parked   │
     │ owner_role  │    ╚═════╝    │ 暂存待样本 │
     └────────┬────┘               └─────┬─────┘
              │                           │
     ┌────────┼──────────┐               │
     │        │          │               │
   ┌─▼──┐  ┌──▼───┐  ╔══╧══╗         │
   │APP │  │REJ   │  │park │         │
   └─┬──┘  └──────┘  └─────┘         │
     │                                │
   ┌─▼──────────┐                    │
   │final_review│                    │
   └─┬──────────┘                     │
     │                                │
   ┌─┼──────────┬─────────┐          │
   │ │          │         │          │
 ┌─▼──┐  ╔══╧══╗  ┌──▼───┐       │
 │app │  ║SUP  ║  │park  │       │
 └─┬──┘  ╚═════╝  └──────┘       │
   │                               │
 ┌─▼──┐                          │
 │clo │                          │
 └────┘                          │
                                  │
 ┌─────────────────────────────────┘
 │ superseded → closed
```

### 3.1 状态说明

| 状态 | 含义 | 谁可以操作 | 下一个状态 | 超时处理 |
|:-----|:-----|:----------|:-----------|:---------|
| proposed | 后评估或人工提出候选 | 执行模型/任何角色 | role_review / rejected / parked | 7 天内无动作自动标记为 parked |
| role_review | 对应角色评审中 | owner_role | approved / rejected / parked | 48 小时内无响应用 markdown 提醒 |
| approved | 角色确认可更新 | owner_role | final_review | 5 天内无动作自动标记为 parked |
| final_review | 腰子终审 | 腰子（金融）或阿黑（非金融） | applied / rejected / parked | 7 天内无动作升级为 L3 请示用户 |
| applied | 已写入目标库并记录版本 | 情墨（执行入库） | closed | — |
| rejected | 明确不采纳 | 所有者 / 腰子 | closed | — |
| parked | 暂存，等待更多样本 | owner_role（可唤醒） | role_review / superseded | 90 天 parked → 旧影审计是否关闭 |
| superseded | 被新候选替代 | 新候选创建者 | closed | — |
| closed | 流程关闭 | 旧影 | 不再流转 | — |

### 3.2 状态迁移规则

1. proposed → role_review：owner_role 被自动分配到候选。
2. proposed → rejected：仅在候选明显违反红线时才从 proposed 直接 reject，需注明原因。
3. proposed → parked：owner_role 不在线或超时处理。
4. role_review → approved：owner_role（或联审角色全部）确认通过。
5. role_review → rejected：owner_role 确认不采纳。
6. approved → final_review：自动进入，无需额外操作。
7. final_review → applied：腰子（或阿黑）签字确认入库。
8. final_review → rejected：腰子（或阿黑）否决。
9. any → superseded：当新候选声明替代旧候选时，旧候选自动 superseded。

---

## 4. 归因类型详细定义

### 4.1 attribution_type 枚举值

| 类型 | 含义 | 典型场景 | 首选落点 | 负责人 |
|:-----|:-----|:---------|:---------|:-------|
| data | 数据问题 | 字段值错误、缺失、延迟、口径不匹配 | 反例库 + 玉夜候选 | 玉夜 |
| parameter | 参数问题 | 阈值过紧/过松、窗口过长/过短 | 参数库 | 青山 + 流金 |
| weight | 权重问题 | 因子权重长期偏误 | 参数库 + 青山候选 | 青山 |
| evidence_level | 证据等级问题 | L1/L2a/L2b/L3 判定错误 | 反例库 + 信鸽/玉夜候选 | 信鸽 |
| analysis_logic | 分析逻辑问题 | 因果链条不成立、推理方向错误 | 反例库 + 腰子/青山候选 | 腰子 |
| presentation | 展示问题 | 用户摘要或报告结构误导动作 | 场景适配器 | 腰子 |
| execution | 执行问题 | 日报/荐股未按周报指令执行 | 场景适配器 + 审计 | 阿黑 |
| strategy_environment | 策略环境变化 | 市场风格切换、行业相位变化 | 山猫/青山候选 + 参数库 | 山猫 |

### 4.2 target_layer 与 attribution_type 匹配表

| attribution_type | 允许的 target_layer |
|:-----------------|:-------------------|
| data | core, evolution, counterexample, parameter |
| parameter | parameter |
| weight | parameter |
| evidence_level | core, evolution, counterexample |
| analysis_logic | core, evolution, counterexample |
| presentation | adapter, evolution |
| execution | adapter |
| strategy_environment | adapter, parameter, evolution |

> ⛔ 例外规则：attribution_type 为 data、evidence_level、analysis_logic 时，target_layer 可以为 core，但必须通过 final_review 且腰子终审。

---

## 5. id 生成规则

```
KUC-{YYYYMMDD}-{ROLE_EN}-{NNN}
```

| 部分 | 说明 | 示例 |
|:-----|:-----|:-----|
| YYYYMMDD | 候选创建日期 | 20260610 |
| ROLE_EN | 角色英文缩写 | QINGSHAN（青山）/ YUNYE（玉夜）/ LIUJIN（流金）/ XINGE（信鸽）/ SHANMAO（山猫）/ YAOZI（腰子） |
| NNN | 当天该角色 3 位序号 | 001 |

例如：`KUC-20260610-QINGSHAN-001`

---

## 6. 生成规范

### 6.1 后评估必须产出候选的条件

每份后评估报告无论判断命中还是偏误，都必须检查是否满足以下条件：

1. 任何归因结果 ≠ `no deviation`。
2. 同一归因类型在本标的已出现 ≥2 次。
3. 归因结果为数据、参数、证据等级、分析逻辑、展示、执行、策略环境变化之一。
4. 角色认为有可复用教训。

满足任一条件即应产出候选。

### 6.2 不应产出候选的情况

1. 纯随机波动，无可归因原因。
2. 后评估无法获取足够信息判定偏差原因。
3. 偏差已在现有候选队列中且状态为 `approved` / `applied`。
4. 偏差归因为"黑天鹅事件"，不具备可复用性。

### 6.3 候选的完整性检查

一个完整的候选必须满足：

- [ ] candidate_id 符合命名规则
- [ ] source_ref 可追溯
- [ ] attribution_type 在枚举范围内
- [ ] target_layer 与 attribution_type 匹配
- [ ] evidence_refs 至少 1 条
- [ ] decision_status 初始值为 proposed
- [ ] risk_if_applied 和 risk_if_ignored 均已填写

---

## 7. 审计规则

| 审计检查点 | 规则 | 触发条件 |
|:-----------|:-----|:---------|
| 来源检查 | 每个候选必须有 source_ref 和 evidence_refs | 候选创建时 |
| 分层检查 | target_layer 必须是五层之一且与 attribution_type 匹配 | 候选创建时 |
| 角色检查 | owner_role 必须与归因类型匹配 | 候选创建时 |
| 单次入库检查 | 单次报告结论不得直接进入核心知识库 | applied 时 |
| 签字检查 | 不得用执行模型代签角色确认 | role_review / final_review 时 |
| 版本检查 | applied 后必须记录 final_decision_ref | applied 时 |
| 回溯检查 | 下次报告引用时必须能追到候选来源 | 每次引用时 |

---

## 8. 版本历史

| 版本 | 日期 | 变更 |
|:----:|:----:|:-----|
| v1.0 | 2026-06-10 | 初始创建：字段定义、状态机、归因类型、生成规范、审计规则 |
