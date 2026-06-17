# 重点股票分析池治理与产品化驱动方案 v0.1

> 日期：2026-06-17
> 阶段：G2 技术子方案候选
> 上位框架：`PLAN_重点股票产品化分析闭环总框架_v0.1.md`
> 关联方案：`PLAN_重点股票分析生产线产品化方案_v0.1.md`、`PLAN_重点股票产品页面五会话产品化总方案_v0.1.md`
> 定位：定义重点股票分析池的权威来源、入池、用户特例、出池、运行驱动、产品 API 和运维治理。
> 边界：本文只生成 G2 方案文件；不修改生产代码、不切换运行入口、不修改正式日报/深度分析/基线、不放行任何投资结论。

---

## 0. CCRT 阶段声明

已调用 skill: ccrt-standard-flow

流程阶段：

```text
G0 需求识别
  -> G1 业务/金融口径确认
  -> G2 技术子方案候选
```

本文件性质：

```text
方案文件 / G2 候选
```

当前状态：

```text
未进入 G3 实施
未修改生产规则
未切换运行入口
未修改 baseline_registry
未删除历史报告或历史股票资产
```

---

## 1. 前置检查结论

当前系统已经发生产品化转向：

1. `PLAN_重点股票产品化分析闭环总框架_v0.1.md` 已经把重点股票定义为“分析生产线 -> 后评估/回测 -> 产品使用层 -> 运营闭环”的长期产品后端框架。
2. `PLAN_重点股票产品页面五会话产品化总方案_v0.1.md` 已明确当前产品股票池只包含 `600114 东睦股份`，但实现上不得写死东睦股份。
3. `代码文件/重点股票/product_eval/stock_pool.py` 已有产品股票池雏形，当前 active 成员为 `600114 东睦股份`。
4. `00_项目地基/02_权威注册表/daily_report_targets.json` 当前 active target 也只包含 `600114 东睦股份`。
5. `代码文件/信鸽信息采集/pigeon_config.json` 仍保留旧 target_stocks 多只股票配置，部分脚本仍可能从它或历史报告目录读取“股票池”。
6. 历史日报、历史深度分析、历史 baseline 中仍包含多只旧股票。这些历史资产不能删除，但也不能反向决定当前 active 分析池。

因此，本次问题不是“删掉 9 只股票”这么简单，而是要把“当前重点股票分析范围”做成产品化的一等契约：

```text
KeystockAnalysisPool
  -> 驱动深度分析
  -> 驱动每日分析
  -> 驱动产品 API bundle
  -> 驱动 dashboard
  -> 驱动后评估和规则健康展示
  -> 驱动运维告警和重跑范围
```

---

## 2. 一句话目标

让重点股票系统从“多个脚本各自猜股票池”升级为“一个权威分析池驱动全部产品化链路”：

```text
分析池契约
  -> active / user_override / candidate / paused / archived
  -> 深度分析按池生成或检查
  -> 每日分析按池生成或检查
  -> 后评估按池验证
  -> 产品 API 按池发布
  -> 页面按池展示
  -> 运维按池告警、重跑、退出和审计
```

当前 active 默认只保留：

```text
600114 东睦股份
```

同时允许用户自行添加少数“重点关注特例股”。这类股票必须被系统明确标记为用户特例，不应伪装成算法自动筛选结果。

---

## 3. 与总框架 v0.1 的关系

本方案是总框架下的一个横向支撑子方案，位于四条主线之前，负责回答：

```text
哪些股票进入重点股票产品化分析闭环？
哪些股票只做候选观察？
哪些股票已经暂停或出池？
日报、深度分析、后评估、产品页面到底分析哪些股票？
```

对应总框架关系：

| 总框架主线 | 本方案承接方式 |
|:--|:--|
| A. 分析生产线产品化 | 分析生产线不得硬编码股票，必须读取 `KeystockAnalysisPool` active 范围 |
| B. 后评估/回测产品化 | 后评估默认只评估 active/current pool；历史资产仍可用于样本，但不能反向扩池 |
| C. 用户使用层产品化 | 页面股票列表、详情页、今日驾驶舱必须由产品化池输出，不由前端写死 |
| D. 总集成与运营闭环 | 调度、告警、重跑、归档、出池审计都围绕 pool membership 运行 |

本方案不替代：

1. `baseline_registry.json`，它仍是 baseline 权威源。
2. 深度分析和日报具体分析逻辑，它们仍按现有方法论与 D01-D12 能力域运行。
3. 产品 API bundle 方案，它消费本方案定义的池契约。

本方案新增的是“分析范围权威层”。

---

## 3.1 二次复盘优化结论

按业务适配、产品架构、编码可行性、运维难易重新评审后，本方案需要做三处优化：

1. 权威源应从“代码内硬编码池”优化为“可审计 JSON 注册表 + Python 服务适配”。`ProductStockPoolService` 继续存在，但不再作为用户可变池的唯一事实源；它应读取、校验、导出和兼容旧产品 API。
2. 分析池应拆出三个运行视角：`analysis_pool`、`data_warmup_pool`、`message_watch_pool`。用户特例可以先进入关注和数据预热，但只有满足 baseline、数据 freshness、D07/质量闸门后，才进入正式每日分析。
3. G3 落地顺序应从“改所有入口”优化为“注册表/schema/checker/适配器先行，再逐步替换消费者”。这样编码风险更低，也更容易回滚。

这三处优化的原因：

| 复盘角度 | 原方案风险 | 优化方向 |
|:--|:--|:--|
| 业务适配 | 用户自行添加股票若要改 Python 代码，服务体验差，也不可审计 | 用户通过结构化注册表或命令添加，系统记录来源、复核、退出条件 |
| 能力调用 | candidate/user_override 缺 baseline 时容易误入日报链路 | 分层调用 D01/D02/D03 做预热，满足条件后再调用深度分析/日报 |
| 数据获取 | 候选股票不一定已有完整 D04/D06 特征，直接 daily 会 BLOCK | 先做 data_warmup，输出“关注中但暂不能正式决策” |
| 产品架构 | product pool、daily targets、pigeon_config 多源并存 | `keystock_analysis_pool.json` 为当前分析范围权威，其他文件只做镜像或外部输入 |
| 编码可行性 | 一次性改多个脚本容易打断日报生产线 | 先建 adapter，旧入口逐个切换，测试锁定 `--all` 语义 |
| 运维难易 | 出池/暂停/过期无操作日志，后续难追责 | membership change ledger + pool health checker + 原子导出 |

---

## 4. 设计原则

### 4.1 产品化优先

当前只有 1 只股票，也必须通过池契约进入分析、产品 API 和页面。不能因为只有东睦股份就把 `600114` 写死在脚本、API 或前端里。

### 4.2 用户特例一等化

用户可以自行添加少数重点关注股票。系统必须支持这种业务现实：

1. 用户特例可以绕过部分自动筛选排序。
2. 用户特例不能绕过数据质量、baseline、风险和状态标记。
3. 用户特例必须显示 `source_type=user_override` 或等价字段。
4. 用户特例必须有过期复核机制，避免临时兴趣永久污染 active 池。

### 4.3 入池与出池同等重要

入池规则决定“看什么”，出池规则决定“不再看什么”。如果只有入池没有出池，产品池会重新膨胀为旧式大名单。

### 4.4 历史资产不等于当前池

历史报告、历史深度分析、历史 baseline、历史回测样本可以长期保留，但不得通过“扫描目录”自动进入当前 active 池。

### 4.5 自动化优先，人工裁决只处理业务偏好

系统应自动检查：

1. 数据是否齐。
2. baseline 是否有效。
3. 分析是否过期。
4. 是否触发暂停或出池。
5. 产品 API 是否能发布。

用户只需要裁决少数业务问题：

1. 是否把某只股票设为重点关注特例。
2. 是否接受系统建议出池。
3. 是否让 candidate 升为 active。
4. 是否对 paused 股票恢复跟踪。

### 4.6 不把复杂性推给用户

产品页面第一屏不展示“池状态机术语”。用户看到的是：

```text
正在重点跟踪
用户特别关注
候选观察
暂停跟踪
已出池
```

后台保留精确字段，前端展示人话状态。

### 4.7 可变配置不写死在代码

股票池成员、用户特例、复核日期、出池原因属于业务状态，不应长期写死在 Python 类里。代码负责：

1. 读取注册表。
2. 校验契约。
3. 生成产品 API。
4. 给旧脚本提供兼容接口。
5. 输出审计证据。

业务状态负责放在可审计、可 diff、可回滚的注册表里。

### 4.8 能力调用按状态分层

不同成员状态调用不同能力，不得一进入关注就触发完整日报链路：

| 成员状态 | 允许调用能力 | 禁止行为 |
|:--|:--|:--|
| candidate | D01/D02/D03 数据检查、D05 证据预扫、D04 数据可用性探测 | 禁止正式日报结论 |
| user_override_pending_baseline | D01-D07 深度分析准备、baseline 缺口检查 | 禁止每日正式操作建议 |
| user_override | D01-D10 日报/产品 API，D11 后评估 | 禁止绕过数据 BLOCK |
| active | D01-D12 完整闭环 | 禁止从旧目录扩池 |
| paused | 只允许状态检查和恢复预检 | 禁止自动生成新日报 |
| archived | 只允许历史读取/回测样本 | 禁止进入当前 dashboard active |

---

## 5. 目标架构

### 5.1 分层

```text
池治理层
  - keystock_analysis_pool.json / ProductStockPoolService
  - membership lifecycle
  - user override
  - entry / exit rules

权威映射层
  - baseline_registry.json
  - daily_report_targets mirror
  - product API stock_pool.json
  - runtime/report scopes

分析生产线层
  - deep_analysis scope
  - daily_report scope
  - sidecar / canonical / quality gates

产品 API 层
  - stock_pool.json
  - stocks.json
  - dashboard.json
  - today_decisions.json
  - evidence_index.json
  - run_manifest.json

前端使用层
  - pool list
  - active/current detail
  - user override badge
  - candidate and paused state
  - exit reason history

运营闭环层
  - pool health checker
  - stale membership alert
  - baseline missing alert
  - one-stock rerun
  - exit recommendation
  - audit evidence
```

### 5.2 权威源建议

二次复盘后，建议第一阶段新增可审计注册表作为当前分析池权威源：

```text
00_项目地基/02_权威注册表/keystock_analysis_pool.json
```

并配套 schema：

```text
00_项目地基/04_一致性闸门/keystock_analysis_pool.schema.json
```

`ProductStockPoolService` 的职责调整为服务层：

```text
读取 keystock_analysis_pool.json
  -> validate_pool_contract()
  -> get_daily_analysis_targets()
  -> get_deep_analysis_targets()
  -> build_pool()
  -> export product stock_pool.json
```

生成机器产物：

```text
运行产物/重点股票产品化后评估/product_api/stock_pool.json
docs/keystock-dashboard/data/stock_pool.json
```

不再建议把用户可变池只写在：

```text
代码文件/重点股票/product_eval/stock_pool.py
```

因为这会让“用户自行添加特例股”变成代码修改，不利于审计、回滚和产品化使用。

### 5.3 三池分离

为避免 `pigeon_config.json`、候选股、用户特例和正式日报互相污染，建议逻辑上分三池：

```text
analysis_pool
  - active / user_override
  - 驱动正式深度分析、日报、产品页面、后评估

data_warmup_pool
  - candidate / user_override_pending_baseline
  - 驱动数据可用性、freshness、baseline 缺口、特征预热

message_watch_pool
  - watch_only / candidate
  - 驱动消息和事件观察，不驱动正式日报
```

三池可以存在于同一个 `keystock_analysis_pool.json` 内，用字段区分：

```text
membership_status
analysis_modes
data_warmup_enabled
message_watch_enabled
```

这样产品层看到的是一个池，运行层按模式调用能力。

---

## 6. 池成员状态模型

建议定义 `membership_status`：

```text
active
user_override
candidate
watch_only
paused
exit_pending
archived
rejected
```

含义：

| 状态 | 用户含义 | 系统行为 |
|:--|:--|:--|
| active | 正在重点跟踪 | 默认进入深度分析、每日分析、产品页面、后评估 |
| user_override | 用户特别关注 | 与 active 类似，但展示特例标签，并有复核期 |
| candidate | 候选观察 | 可收集数据和事件，不生成正式日报，除非用户点名 |
| watch_only | 只看消息/事件 | 不进入每日分析主链路，不占 active 容量 |
| paused | 暂停跟踪 | 保留历史，不生成新日报，不出现在第一屏 |
| exit_pending | 建议出池待确认 | 不自动删除，等待用户确认或规则到期 |
| archived | 已出池 | 只保留历史资产，不再驱动分析 |
| rejected | 不纳入 | 用于记录被否决候选，防止重复推荐 |

第一阶段可简化为：

```text
active
user_override
candidate
paused
archived
```

---

## 7. 当前初始池

第一阶段当前池：

```text
active:
  - 600114 东睦股份
```

旧 `pigeon_config.json` 中其他股票不直接进入重点股票分析池。

它们可以按后续需要分流为：

```text
candidate / watch_only / archived
```

但不能默认 active。

---

## 8. 入池规则

### 8.1 自动入池候选条件

系统可以建议 candidate，但不得直接升 active。candidate 建议条件：

1. 数据可用：近 60 个交易日日线、成交量、换手、资金流至少通过最低 freshness 检查。
2. 业务理由：存在产业主线、事件催化、持仓相关性或与当前主题高度相关。
3. 风险过滤：非 ST、非退市风险、无明显数据不可得、无近期重大合规黑洞。
4. 可解释性：系统能说明“为什么值得看”，不能只给分数。
5. 成本可控：加入后不会让每日分析规模超过当前运维能力。

### 8.1.1 数据获取与能力预热

candidate 和用户特例入池前，应先走数据预热，不直接进入日报：

```text
stock identity check
  -> market/code/name normalization
  -> D01/D02 数据源可达性检查
  -> D03 freshness 预检
  -> D04 历史数据覆盖检查
  -> D05 事件/公告证据预扫
  -> D06 核心特征可计算性检查
  -> baseline gap scan
```

预热结果写入成员字段：

```text
data_readiness:
  kline_status
  moneyflow_status
  daily_basic_status
  event_status
  feature_status
  baseline_status
  blocker_reasons
  checked_at
```

数据预热结论：

| 结论 | 含义 | 后续动作 |
|:--|:--|:--|
| READY_FOR_BASELINE | 数据足够，可以进入深度分析/baseline 准备 | 生成深度分析任务候选 |
| READY_FOR_DAILY | baseline 和数据均可用 | 可升 active/user_override |
| WATCH_ONLY | 只能做消息观察 | 不生成日报 |
| DATA_BLOCK | 数据不足 | 页面展示关注中但不可正式分析 |
| IDENTITY_BLOCK | 代码/名称/市场无法确认 | 阻止入池 |

### 8.2 active 入池硬条件

candidate 升 active 必须满足：

1. 用户确认或明确授权。
2. 存在唯一有效 baseline，或先生成并通过深度分析 baseline 注册流程。
3. 数据 freshness gate 不为 BLOCK。
4. D07/深度分析质量闸门不为 BLOCK。
5. 产品 API 能为该股票生成最小 `stock_detail` / `today_decision` / `evidence`。
6. 有入池理由、复核日期、退出条件。

### 8.3 用户特例入池

用户可以直接指定：

```text
把 X 加入重点关注
```

系统处理方式：

1. 生成 `user_override` 成员，而不是直接伪装为普通 active。
2. 如果 baseline 缺失，则状态为 `user_override_pending_baseline` 或 `candidate`，页面显示“已关注，待深度分析/基线补齐”。
3. 如果数据缺失，则允许进入关注列表，但不得生成正式每日决策，只能显示 `BLOCK: 数据不足`。
4. 用户特例默认复核周期为 20 个交易日或 30 自然日。
5. 用户特例数量第一阶段建议上限为 3 只；超过上限需要用户再次确认，因为会增加日报和运维负担。

### 8.4 手工入池最小字段

用户特例最小字段：

```text
stock_code
stock_name
market
membership_status: user_override
source_type: user_override
join_reason
joined_at
review_due_at
desired_analysis_mode: daily | deep_only | watch_only
baseline_required: true
exit_rule_refs
```

### 8.5 用户添加特例的产品流程

用户不应手改配置文件。推荐提供命令或界面动作：

```text
add user override
  -> dry-run 展示影响
  -> 写 membership change proposal
  -> 用户确认
  -> 原子更新 keystock_analysis_pool.json
  -> 运行 pool validate
  -> 触发 data warmup
  -> 刷新 product API shadow bundle
```

第一阶段可以先实现 CLI，不做前端：

```bash
python3 scripts/keystock_analysis_pool.py --add-user-override 600114 --name 东睦股份 --reason "用户重点关注" --dry-run
python3 scripts/keystock_analysis_pool.py --add-user-override 600114 --name 东睦股份 --reason "用户重点关注" --write
```

所有 `--write` 必须生成变更日志。

---

## 9. 出池逻辑

### 9.1 自动建议出池条件

系统应生成 `exit_pending`，而不是直接删除 active：

1. baseline 过期超过复核窗口，且未生成新深度分析。
2. 连续 N 个交易日数据 freshness BLOCK。
3. 关键投资假设被反证事件击穿。
4. 风险灯连续处于红灯或监管/财务风险升级。
5. 用户特例到期且用户未继续确认。
6. 股票不再有持仓、不再有用户关注理由、也无明确中期跟踪价值。
7. 产品 API 连续生成失败且自动修复失败 3 次。
8. 分析产物长期只输出“观察/无动作”，没有新增信息价值。

### 9.2 直接暂停条件

以下情况可自动 `paused`：

1. 停牌、重大资产重组停牌。
2. 数据源临时不可用且影响决策。
3. baseline 冲突，多有效 baseline 未解决。
4. 生产链路显示该股票会导致全池发布 BLOCK。

paused 不是出池，只是不生成新的正式分析。

### 9.3 archived 出池确认

进入 `archived` 应保留：

```text
exit_reason
exit_at
last_active_at
last_baseline_id
last_report_refs
user_confirmed: true | false
auto_exit_policy_ref
```

历史报告、历史深度分析、baseline registry 不删除。

### 9.4 用户重新拉回

archived 股票可重新进入 candidate 或 user_override，但必须重新检查：

1. 最新数据 freshness。
2. baseline 是否仍有效。
3. 是否需要新深度分析。
4. 是否仍符合容量和用户服务优先级。

---

## 10. 分析范围驱动规则

### 10.1 深度分析

默认分析范围：

```text
active + user_override 且 baseline_due=true
```

candidate 不自动生成正式深度分析，除非：

1. 用户确认升 active 前需要深度分析。
2. 系统生成 candidate review 包。
3. 当前 active 池为空，用户授权从 candidate 中补充。

深度分析生成后必须回写或关联：

```text
baseline_id
source_report_path
membership_id
pool_version
analysis_run_id
```

### 10.2 每日分析

默认分析范围：

```text
active + user_override
```

前置条件：

1. baseline 有效。
2. 当日数据 ready。
3. 单票 sidecar/canonical 生成可通过质量闸门。

如果 user_override 缺 baseline：

```text
不生成正式日报
输出待补 baseline 状态
必要时生成“关注中但暂不能给正式决策”的产品状态
```

### 10.2.1 每日分析的数据降级策略

active/user_override 成员进入日报前必须完成以下 gate：

```text
identity PASS
baseline PASS
daily_data_ready PASS
freshness PASS or controlled WARN
sidecar_contract PASS
```

数据缺失时不得用空话补齐：

| 缺失类型 | 处理 |
|:--|:--|
| 行情缺失 | BLOCK，不生成正式日报 |
| 资金流缺失 | 可 WARN 降级，但必须写 evidence_gap |
| 公告/事件缺失 | 可 WARN 降级，声明事件源不可用 |
| baseline 缺失 | BLOCK，转深度分析/baseline 任务 |
| 持仓缺失 | 不阻断分析，但产品页面不得展示虚假成本/盈亏 |

### 10.2.2 深度分析的数据策略

深度分析比日报更重，不能因用户特例立刻全量运行。建议策略：

1. 用户特例先完成数据预热。
2. 数据足够后生成“深度分析待办”。
3. 深度分析通过后写入或关联 baseline。
4. baseline 生效后才进入正式日报。

这样用户可以先把股票加入关注，但系统不会在证据不足时给出正式操作建议。

### 10.3 后评估

默认评估范围：

```text
current active/user_override 的新产物
```

历史样本范围：

```text
可读取 archived 历史产物作为回测样本
但必须标记 historical_sample，不得加入当前 dashboard active 列表
```

### 10.4 产品页面

产品页面股票列表按状态分区：

1. 正在重点跟踪。
2. 用户特别关注。
3. 候选观察。
4. 暂停/待处理。
5. 历史已出池，默认折叠。

第一屏默认展示：

```text
active + user_override 中优先级最高的一只
```

当前应为：

```text
东睦股份 600114
```

---

## 11. 编码落地方案

### 11.1 核心服务

建议升级：

```text
代码文件/重点股票/product_eval/stock_pool.py
```

新增能力：

```text
get_members(statuses=None)
get_active_analysis_members()
get_user_override_members()
get_daily_analysis_targets()
get_deep_analysis_targets()
get_product_visible_members()
validate_membership_contract()
validate_entry_requirements(member)
evaluate_exit_recommendations(member, context)
build_pool()
```

核心服务的实现应尽量薄：

```text
registry IO
schema validation
status filter
target projection
entry/exit rule evaluation
product export
```

不建议在 `stock_pool.py` 内实现复杂数据采集、深度分析生成或日报生成。那些能力应继续由 D01-D12 和现有脚本承担，池服务只负责“范围和状态”。

### 11.2 脚本适配器

新增统一脚本适配器：

```text
scripts/keystock_analysis_pool.py
```

职责：

1. 给旧脚本提供稳定读取函数。
2. 输出 CLI 方便验收。
3. 避免每个脚本直接 import 产品 API 细节。

建议 CLI：

```text
python3 scripts/keystock_analysis_pool.py --active --json
python3 scripts/keystock_analysis_pool.py --daily-targets --json
python3 scripts/keystock_analysis_pool.py --deep-targets --json
python3 scripts/keystock_analysis_pool.py --validate
python3 scripts/keystock_analysis_pool.py --exit-scan --json
```

新增建议 CLI：

```text
python3 scripts/keystock_analysis_pool.py --data-warmup-targets --json
python3 scripts/keystock_analysis_pool.py --message-watch-targets --json
python3 scripts/keystock_analysis_pool.py --add-user-override CODE --name NAME --reason REASON --dry-run
python3 scripts/keystock_analysis_pool.py --pause CODE --reason REASON --dry-run
python3 scripts/keystock_analysis_pool.py --archive CODE --reason REASON --dry-run
python3 scripts/keystock_analysis_pool.py --export-daily-targets --out 00_项目地基/02_权威注册表/daily_report_targets.json --dry-run
```

### 11.3 需要改为读池的入口

第一批必须改：

```text
scripts/run_daily_report_one_by_one.py
scripts/run_daily_production_pipeline.py
scripts/resolve_current_baseline.py
scripts/check_baseline_authority.py
scripts/check_daily_d07_v12_contract.py
scripts/check_freshness_degradation.py
```

原则：

1. `--all` 只代表当前分析池，不代表历史目录全部股票。
2. `pigeon_config.json` 不再作为重点股票分析池来源。
3. 历史报告目录 fallback 默认禁用。
4. 如确需历史扫描，必须显式参数：`--legacy-report-scan`。

### 11.3.1 编码实施顺序优化

为降低改造风险，不建议一次性改完所有消费者。建议顺序：

```text
Step A: 新增 schema + keystock_analysis_pool.json + checker
Step B: 改 ProductStockPoolService 读取注册表，保持现有 build_pool 输出兼容
Step C: 新增 scripts/keystock_analysis_pool.py adapter 和 CLI
Step D: 产品 API bundle 改为消费新服务，dashboard 先 shadow 验证
Step E: resolve_current_baseline.py / check_daily_d07_v12_contract.py 的 --all 改读 adapter
Step F: run_daily_report_one_by_one.py dry-run 先改读 adapter
Step G: run_daily_production_pipeline.py 最后切换，避免影响生产链路
```

每一步都应有单独测试。任何一步失败，回滚本步即可，不影响前一步。

### 11.4 产品 API bundle

第一阶段继续由：

```text
代码文件/重点股票/product_eval/product_api_bundle.py
```

消费 `ProductStockPoolService`。

新增要求：

1. `stock_pool.json` 必须输出 membership 状态、source_type、join_reason、review_due_at、exit_policy_refs。
2. `dashboard.json` 不得只写 `primary_stock_code`，必须引用 pool 成员。
3. `today_decisions.json` 必须按 pool members 构建。
4. `run_manifest.json` 必须记录 pool_version 和 pool_member_count。
5. checker 必须校验页面数据与 pool 一致。

### 11.5 注册表字段建议

`keystock_analysis_pool.json` 最小结构：

```text
schema_version
pool_id
pool_version
updated_at
updated_by
members[]
change_log[]
policies
```

成员字段：

```text
membership_id
stock_code
stock_name
market
membership_status
source_type: system_candidate | user_override | migrated_legacy | manual_admin
analysis_modes: daily | deep | product_view | message_watch | data_warmup
priority
joined_at
join_reason
review_due_at
baseline_required
primary_baseline_id
data_readiness
exit_policy_refs
last_status_change
status_reason
source_refs
```

变更日志字段：

```text
change_id
changed_at
actor_type: user | system | executor
action: add | pause | archive | restore | update_status | extend_review
stock_code
before_status
after_status
reason
evidence_refs
```

---

## 12. 运维与调度方案

### 12.1 调度范围

生产调度不再自行维护股票列表。调度只问：

```text
今天有哪些 daily_analysis_targets？
有哪些 deep_analysis_targets due？
哪些成员 paused 或 BLOCK？
```

### 12.1.1 daily_report_targets 的定位

`daily_report_targets.json` 不再作为手工维护的源头权威。它应降级为镜像/兼容文件：

```text
keystock_analysis_pool.json
  -> export daily_report_targets.json
  -> old pipeline compatibility
```

checker 必须校验：

1. `daily_report_targets.json` 中 `enabled=true` 的股票必须来自 pool 的 daily targets。
2. `daily_report_targets.json` 不得多出 pool 外股票。
3. pool 更新后未同步 mirror 时，状态为 WARN 或 BLOCK，按影响范围决定。

### 12.2 重跑

一键重跑支持三类：

```text
rerun one stock daily
rerun one stock product bundle
rerun pool validation
```

禁止：

```text
默认一键重跑历史目录所有股票
```

### 12.3 告警

告警对象：

1. active 成员 baseline 缺失。
2. active 成员日报生成失败。
3. user_override 到期未复核。
4. pool 与 dashboard 输出不一致。
5. pool 与 `daily_report_targets.json` 镜像不一致。
6. `pigeon_config.json` 旧 target 被误用于分析入口。

### 12.4 自修复

可自动修复：

1. 重新生成 product API bundle。
2. 重新跑 pool validate。
3. 重建只读 dashboard 数据。
4. 对 paused 之外的 active 成员重跑单票日报。

不可自动修复，必须用户确认：

1. 新股票升 active。
2. user_override 超过上限。
3. active 股票 archived 出池。
4. baseline 冲突需要选择权威版本。

### 12.5 运维难点与缓解

| 难点 | 风险 | 缓解 |
|:--|:--|:--|
| 多源配置并存 | 旧池从 `pigeon_config.json` 或报告目录回流 | adapter 统一读取，checker 扫描旧入口 |
| 用户特例频繁变化 | 每次变化都可能影响日报范围 | dry-run + change_log + review_due_at |
| 数据预热失败 | 用户以为已加入就能给决策 | 产品状态明确“关注中，数据未就绪” |
| baseline 缺失 | 正式日报无法生成 | 自动转深度分析待办，不伪造日报 |
| 产品 API 半发布 | 前端读到不一致数据 | staging + checker + atomic publish |
| 调度切换风险 | 影响每日生产链路 | 最后切 production pipeline，先 shadow/dry-run |
| 出池误伤 | 用户仍持仓但系统 archived | archived 前必须检查持仓/用户确认 |
| 历史样本污染当前池 | 回测读取历史时误显示为当前 | historical_sample 标记，前端默认折叠 |

### 12.6 运维状态输出

建议新增：

```text
pool_health.json
pool_change_log.jsonl
pool_exit_recommendations.json
pool_data_warmup_status.json
```

这些产物给运维和产品 API 使用，不直接污染用户第一屏。

---

## 13. 业务配合方案

### 13.1 用户日常动作

用户应能表达：

```text
把 X 加入重点关注
把 X 暂停跟踪
把 X 移出重点池
今天只看东睦股份
这个特例继续保留 30 天
这个股票只看消息，不做日报
```

系统应转换为结构化 membership 变更，而不是让用户手改 JSON。

### 13.2 入池时系统给用户看的内容

加入前应展示：

1. 股票名称和代码确认。
2. 当前状态：可直接 active / 需补 baseline / 数据不足。
3. 加入后会产生什么：日报、深度分析、页面展示、告警、后评估。
4. 对用户的负担：每天会多一个分析对象。
5. 默认复核日期和退出条件。

### 13.3 出池时系统给用户看的内容

出池前应展示：

1. 为什么建议出池。
2. 最近一次结论。
3. 是否还有持仓或关注理由。
4. 出池后还保留哪些历史资产。
5. 以后如何重新加入。

---

## 14. 服务用户视角

本方案服务用户的核心不是“管理配置”，而是让用户每天少做选择：

1. 默认只看当前真正重要的股票。
2. 用户临时特别关注的股票能快速加入，但不会污染长期池。
3. 系统会主动提醒哪些股票不值得继续占据注意力。
4. 页面不会因为历史目录里有几十只旧股票而干扰当前决策。
5. 深度分析和日报都自然顺着用户当前关心的池运行。
6. 旧报告仍在，但不会变成今天的噪音。

用户第一屏应永远回答：

```text
我现在重点关注哪些股票？
今天最该看哪只？
为什么？
明天怎么做？
有哪些系统还没准备好，影响不影响决策？
```

---

## 15. 允许修改范围

后续 G3 可申请修改：

```text
代码文件/重点股票/product_eval/stock_pool.py
代码文件/重点股票/product_eval/product_api_bundle.py
00_项目地基/02_权威注册表/keystock_analysis_pool.json
00_项目地基/04_一致性闸门/keystock_analysis_pool.schema.json
scripts/keystock_analysis_pool.py
scripts/run_daily_report_one_by_one.py
scripts/run_daily_production_pipeline.py
scripts/resolve_current_baseline.py
scripts/check_baseline_authority.py
scripts/check_daily_d07_v12_contract.py
scripts/check_freshness_degradation.py
tests/keystock_product_eval/
tests/test_daily_production_dry_run.py
tests/test_daily_orchestrator_readiness.py
```

可新增：

```text
scripts/check_keystock_analysis_pool.py
tests/keystock_product_eval/test_analysis_pool_contract.py
tests/keystock_product_eval/test_analysis_pool_product_api_contract.py
```

---

## 16. 禁止修改范围

未获 G3 授权前禁止：

1. 修改正式日报正文或 sidecar。
2. 修改正式深度分析报告。
3. 修改 `baseline_registry.json`。
4. 删除历史旧股票报告、旧 baseline、旧深度分析。
5. 修改 launchd 或 runtime production entry。
6. 修改正式交易、仓位、止损、规则资产。
7. 把旧 `pigeon_config.json` 中股票批量删除作为“治理方案”。
8. 把历史报告目录扫描结果当作当前 active 池。

---

## 17. 验收命令候选

G3 实施后建议验收：

```bash
python3 scripts/keystock_analysis_pool.py --validate
python3 scripts/keystock_analysis_pool.py --active --json
python3 scripts/keystock_analysis_pool.py --data-warmup-targets --json
python3 scripts/keystock_analysis_pool.py --export-daily-targets --out 00_项目地基/02_权威注册表/daily_report_targets.json --dry-run
python3 scripts/check_keystock_analysis_pool.py --json
python3 scripts/resolve_current_baseline.py --all --date 20260617 --json
python3 scripts/run_daily_report_one_by_one.py --date 20260617 --dry-run
python3 scripts/check_daily_d07_v12_contract.py --date 20260617 --all
python3 -m pytest tests/keystock_product_eval/test_stock_pool_contract.py
python3 -m pytest tests/keystock_product_eval/test_analysis_pool_contract.py
python3 -m pytest tests/test_daily_production_dry_run.py tests/test_daily_orchestrator_readiness.py
```

预期：

1. `--active` 只返回 `600114 东睦股份`，除非用户已添加特例。
2. `--all` 对重点股票分析脚本只表示当前分析池。
3. `pigeon_config.json` 中旧股票不触发日报/深度分析。
4. 产品 API 输出 stock_pool 与 dashboard/today_decisions 一致。
5. 若添加 user_override 且缺 baseline，系统输出 pending/block 状态，不生成伪正式决策。
6. `daily_report_targets.json` dry-run 镜像与 pool daily targets 一致。
7. pool 变更日志可追溯，且 archived/paused 不进入当前 active dashboard。

---

## 18. 回滚与不切生产证明

第一阶段实施必须满足：

1. 不删除历史股票资产。
2. 不改 baseline registry。
3. 不切 launchd。
4. 不改正式规则。
5. 不接新外部 API。
6. 不修改真实持仓。
7. 所有产品 API 变更先 shadow 或 docs data 原子发布。
8. 失败时可回滚到旧读取逻辑，但回滚后必须标记旧逻辑存在“旧池污染风险”。

---

## 19. G0-G6 执行顺序

建议后续执行：

```text
G0: 确认需求为重点股票分析池治理与产品化驱动
G1: 确认业务口径：东睦股份 active，允许少数用户特例，必须有出池
G2: 本方案评审
G3: 用户授权后实施池服务、适配器、入口改造、测试
G4: 执行方输出自检候选，含 diff、命令、结果、风险
G5: 旧影独立复查候选，重点看是否仍有旧池入口污染
G6: 腰子放行/归档/同步，确认产品化池治理闭环完成
```

---

## 20. BLOCK 停止条件

后续实施遇到以下情况必须停止：

1. 需要修改 `baseline_registry.json` 才能继续。
2. 需要删除历史报告或历史基线。
3. 需要改 launchd 或生产调度。
4. 需要新增外部 API、token、cookie 或联网采集。
5. `pigeon_config.json` 同时被其他生产链路强依赖，无法区分消息采集池和重点分析池。
6. 无法保证 `--all` 不扫描历史报告目录。
7. 产品 API checker 无法识别 pool 与 dashboard 不一致。
8. 用户特例缺 baseline 却被生成正式日报结论。

---

## 21. 用户可见状态

当前状态：

```text
BLOCK
```

原因：

```text
本文件为 G2 方案候选，等待用户评审；未获授权前不得进入 G3 实施。
```

评审通过后的目标状态：

```text
AUTO_REPAIRING
```

含义：

```text
系统进入池治理实施和自检阶段，允许自动补测试、补 checker、补适配器，但不得越界修改生产资产。
```

G6 完成后的目标状态：

```text
COMPLETE
```

含义：

```text
重点股票分析池已成为产品化分析链路的权威驱动源；当前 active 默认只含东睦股份，用户特例和出池逻辑均有机器契约、入口适配、验收和审计证据。
```
