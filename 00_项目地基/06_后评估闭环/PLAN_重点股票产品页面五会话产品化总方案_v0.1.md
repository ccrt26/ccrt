# 重点股票产品页面五会话产品化总方案 v0.1

> 日期：2026-06-16
> 阶段：G2 总方案候选
> 上位框架：`PLAN_重点股票产品化分析闭环总框架_v0.1.md`
> 对应对象：`docs/keystock-dashboard/`、`代码文件/重点股票/product_eval/`、`运行产物/重点股票产品化后评估/product_api/`
> 边界：本文只沉淀五个后续会话的产品化方案、架构边界、文件范围和验收口径；不进入 G3 实施，不切生产调度，不修改正式规则，不生成正式投资或回测放行结论。

---

## 1. 一句话目标

本轮产品化的目标不是把当前静态页面简单美化，而是把它升级为一套可长期演进的重点股票产品页面底座：

```text
产品股票池
  -> 单股票数据生产
  -> 数据状态与结论闸门
  -> 产品 API bundle
  -> 可交互前端
  -> shadow 调度与生产放行准备
```

当前产品股票池只包含：

```text
600114 东睦股份
```

但实现上不得写死东睦股份。后续新增股票时，应通过产品股票池配置和数据契约扩展，而不是改页面代码或复制脚本。

---

## 2. 本会话准备做什么

本会话只完成 G2 总方案沉淀，形成后续 5 个会话的路线图。

后续 5 个会话分别处理：

1. 产品股票池与成员治理底座。
2. 数据状态闸门与结论分层。
3. 产品 API bundle 与证据链聚合。
4. 交互式前端产品页。
5. shadow 刷新、验收闭环与生产放行准备。

每个会话都应单独经历：

```text
G2 子方案确认
  -> 用户确认进入 G3
  -> G3 实施
  -> G4 自检候选
  -> G5 独立复查候选
  -> G6 放行/归档/同步候选
```

本文件不是执行命令包。进入任何 G3 前必须再次获得用户确认。

---

## 3. 与总框架的关系

本方案继承总框架中的四条主线：

| 总框架主线 | 本方案承接方式 |
|:--|:--|
| A. 分析生产线产品化 | 只消费稳定 baseline、sidecar、feature snapshot 和运行状态；不重写深度分析或日报生成逻辑 |
| B. 后评估/回测产品化 | 通过 rule health、evidence index、prediction ledger 暴露验证状态，不把回测 WARN 包装成正式结论 |
| C. 用户使用层产品化 | 把 `docs/keystock-dashboard/` 从静态展示页升级为可日常查看的产品页 |
| D. 总集成与运营闭环 | 先做 shadow/dry-run 刷新和验收证据，不直接切 launchd 生产调度 |

本方案同时遵守总框架的关键约束：

1. `baseline_registry.json` 继续是 baseline 权威源，不因当前产品池只有 1 只股票而清空历史台账。
2. Markdown 只作为阶段方案和证据记录，不作为主执行逻辑。
3. 产品页面不得绕过 D01-D12 能力域自建孤立数据链路。
4. 后评估和回测不得直接修改正式规则，只能产生观察、告警或规则候选。
5. 临时分析、每日荐股、重点股票日报不得混成同一产品场景。

---

## 4. 当前状态判断

### 4.1 已具备的基础

当前已有：

1. `代码文件/重点股票/product_eval/` 后端 MVP 模块。
2. `运行产物/重点股票产品化后评估/product_api/` 产品 API JSON 产物。
3. `docs/keystock-dashboard/` 静态驾驶舱。
4. `feature_snapshot`、`rule_health_summary`、`evidence_index`、`run_state` 等雏形。
5. dry-run 重置工作流。

这些基础说明系统已经从“纯报告”走到“有产品数据包雏形”。

### 4.2 不能作为正式生产页面的原因

当前页面仍不能生产使用，主要原因是：

1. 股票被硬编码为 `600114`，没有产品股票池抽象。
2. `dashboard.json` 显示 `COMPLETE`，但 `today_decisions.json` 同时存在 `DATA_STALE`、`DATA_DATE_DIVERGENCE`、`POSITION_UNAVAILABLE`。
3. `chart_data.json` 和 `feature_snapshot` 的实际日期存在分歧。
4. 持仓、成本、盈亏未接入，只能显示 `UNAVAILABLE`。
5. 页面是静态展示，缺少股票池、详情联动、证据下钻、状态解释、结论边界。
6. 未接生产调度，产品数据包不是稳定自动刷新链路的一部分。
7. checker 对日期分歧仍可能给出 PASS，存在验收假阳性。

### 4.3 当前正确产品定位

当前页面应定位为：

```text
重点股票产品页面 shadow / 试运行底座
```

而不是：

```text
正式生产决策页面
```

---

## 5. 总体技术架构

### 5.1 分层架构

建议目标架构：

```text
权威与配置层
  - baseline_registry.json
  - product_stock_pool.json
  - rule/version refs

数据与特征层
  - kline_cache
  - daily_basic / moneyflow / event refs
  - feature_snapshot
  - position_snapshot

分析与验证层
  - daily sidecar
  - baseline refs
  - prediction ledger
  - rule health
  - evidence index

产品 API 层
  - bundle_index.json
  - dashboard.json
  - stocks.json
  - stock_detail/{code}.json
  - today_decisions.json
  - chart_data/{code}.json
  - run_state.json

前端使用层
  - stock pool list
  - stock detail
  - decision panel
  - evidence drawer
  - rule health view
  - data status banner

运营闭环层
  - checker
  - test suite
  - run_manifest
  - atomic publish
  - dry-run refresh
  - shadow schedule
  - G4/G5/G6 evidence
```

### 5.2 关键设计原则

1. 池化优先：当前只有东睦股份，也必须通过产品股票池进入页面。
2. 契约优先：前端不直接猜后端字段，后端输出稳定 JSON 契约。
3. 状态真实优先：数据 stale、日期分歧、持仓缺失、规则 WARN 不能被包装成生产 COMPLETE。
4. 观察和正式分离：正式结论必须有明确条件，试运行结论不得冒充正式结论。
5. 可追溯优先：页面每个重要数字都要有 `source_path`、`source_field_refs` 或 evidence ref。
6. 不切生产优先：调度、规则、baseline、日报正式目录在未授权前只读。
7. 自动验收优先：每个方案都必须配测试和 checker，不能靠人工肉眼判断。
8. 后续扩展优先：新增股票、持仓源、规则页、调度入口时不重构主架构。
9. 原子发布优先：前端读取的数据包必须一次性完成发布，不能让页面读到半新半旧 JSON。
10. 版本兼容优先：schema 和 bundle 必须带版本号，新增字段向后兼容，删除字段必须有迁移窗口。
11. 隐私最小化优先：持仓、成本、盈亏属于敏感数据，默认不写入公开 docs，除非明确采用本地私有部署口径。
12. 可回滚优先：每次产品 API 生成必须能回退到上一个完整 bundle，而不是只覆盖当前文件。

### 5.3 深度复盘后新增架构要求

进一步复盘后，原方案还需要补充以下架构要求，避免后续五个会话实现时留下长期维护隐患。

#### 5.3.1 运行清单必须成为一等产物

每次生成产品 API 时，必须同时生成 `run_manifest.json`。它回答：

```text
这次页面数据是谁生成的？
用了哪些输入？
生成了哪些输出？
哪些状态被降级？
前端应该读取哪一个 bundle？
如果失败，失败到哪一步？
```

没有 run manifest 的 bundle，不得作为生产候选。

#### 5.3.2 前端数据发布必须原子化

当前静态页面会直接读取 `docs/keystock-dashboard/data/*.json`。如果构建过程中只写完一半文件，用户可能读到：

```text
新 dashboard + 旧 chart
新 stock_pool + 旧 today_decisions
新 rule_health + 旧 evidence_index
```

因此后续必须采用临时目录构建、校验通过后再发布的策略。最低要求：

```text
build to product_api/_staging/{run_id}/
  -> checker PASS
  -> write bundle_index.json
  -> copy/sync to docs data
  -> write run_manifest.json
```

若发布失败，保留上一个完整 bundle，不让前端进入半更新状态。

#### 5.3.3 schema 版本和迁移策略必须提前定义

产品页面后续会多次扩展字段。如果没有 schema 版本，前端和后端很快会出现契约漂移。

最低要求：

```text
schema_version
bundle_version
producer_version
min_frontend_version
deprecated_fields
compatibility_notes
```

新增字段必须默认可选；删除字段必须先标记 deprecated，再经过至少一个版本窗口。

#### 5.3.4 持仓数据必须分公开视图和私有视图

`docs/` 目录可能被当作静态站点发布，因此不能默认把真实持仓、成本、盈亏写入公开路径。

持仓产品化应分两层：

```text
public_position_view
  - has_position
  - position_status
  - display_note
  - blocker flags

private_position_snapshot
  - quantity
  - cost_price
  - market_value
  - unrealized_pnl
  - source file
```

在真实部署口径确认前，`docs/keystock-dashboard/data/` 只允许写公开视图。私有持仓快照只能放在明确的本地私有产物目录，并且必须有脱敏检查。

#### 5.3.5 降级 UI 要有固定展示协议

状态异常不是简单显示红色告警。页面需要固定降级展示协议：

| 后端状态 | 页面展示 | 用户动作 |
|:--|:--|:--|
| FORMAL | 正式结论 | 可作为今日页面主结论 |
| OBSERVATION | 观察结论 | 只看条件，不看强动作 |
| SHADOW | 试运行 | 只用于验证页面，不作为决策 |
| BLOCKED | 阻断 | 展示原因和证据，不输出结论 |

这套协议必须由数据字段驱动，不得由前端文案硬猜。

#### 5.3.6 扩展多股票前要先解决性能和加载策略

当前只有东睦股份，可以一次性加载所有 JSON。未来股票数增加后，必须支持：

```text
首页只加载 stock_pool + stocks summary
详情页按需加载 stocks/{code}/detail.json
图表按需加载 stocks/{code}/chart_data.json
证据按需加载 stocks/{code}/evidence.json
```

因此即使当前只有一只股票，也应优先形成按股票分片的数据结构，避免后续重写前端加载模型。

---

## 6. 核心契约设计

### 6.1 ProductStockPoolContract

用途：定义产品页面服务哪些股票。

建议字段：

```text
pool_id
pool_name
pool_version
generated_at
members[]
  stock_code
  stock_name
  status: active | paused | candidate | retired
  join_reason
  joined_at
  primary_baseline_id
  baseline_status
  evidence_status
  data_status
  display_order
  source_refs
```

当前成员只允许：

```text
600114 东睦股份
```

但代码不得使用 `primary_code = "600114"` 作为业务常量。东睦股份只能来自 pool member。

### 6.2 DataTruthStatusContract

用途：统一数据可用性和页面状态。

建议字段：

```text
stock_code
trade_date
as_of_date
market_data_status: FRESH | STALE | MISSING | DIVERGED
feature_snapshot_status: FRESH | STALE | MISSING | DIVERGED
position_status: AVAILABLE | UNAVAILABLE | STALE | INVALID
rule_health_status: PASS | OBSERVE | WARN | BLOCK
evidence_status: COMPLETE | PARTIAL | MISSING
date_divergence
blocking_reasons[]
warning_reasons[]
source_refs[]
```

最低闸门：

```text
DATA_STALE -> 不允许正式 COMPLETE
DATA_DATE_DIVERGENCE -> 不允许正式 COMPLETE
RULE_HEALTH_WARN/BLOCK -> 不允许正式动作
POSITION_UNAVAILABLE -> 不允许持仓盈亏和仓位建议
EVIDENCE_MISSING -> 不允许正式结论
```

### 6.3 ConclusionStatusContract

用途：区分正式结论、观察、试运行和阻断。

建议状态：

```text
FORMAL
OBSERVATION
SHADOW
BLOCKED
```

解释：

| 状态 | 含义 | 页面行为 |
|:--|:--|:--|
| FORMAL | 满足正式结论闸门 | 可显示为正式今日结论 |
| OBSERVATION | 数据基本可看，但有降级项 | 只显示观察，不给强动作 |
| SHADOW | 试运行产物 | 显示试运行标签，不进入正式决策 |
| BLOCKED | 关键数据或证据缺失 | 显示阻断原因，不输出结论 |

### 6.4 StockTodayDecisionViewContract

用途：用户第一屏和股票详情页的主对象。

建议字段：

```text
view_id
stock_code
stock_name
trade_date
as_of_time
pool_ref
baseline_ref
user_position
market_today
plain_language_summary
technical_evidence
rule_health_summary
evidence_refs
decision_for_next_day
decision_blockers
conclusion_status
user_visible_status: COMPLETE | AUTO_REPAIRING | BLOCK
updated_at
```

当前持仓处理：

```text
position_source = UNAVAILABLE
has_position = false
cost_price = null
unrealized_pnl = null
```

在真实持仓来源确认前，不计算盈亏、不输出仓位建议。

### 6.5 ProductApiBundleContract

用途：前端唯一读取入口。

建议文件结构：

```text
docs/keystock-dashboard/data/
  bundle_index.json
  stock_pool.json
  dashboard.json
  stocks.json
  run_state.json
  today_decisions.json
  rule_health.json
  evidence_index.json
  chart_data.json              # 兼容旧入口
  stocks/600114/detail.json    # 新结构
  stocks/600114/chart_data.json
  stocks/600114/evidence.json
```

第一阶段可保留旧文件名兼容页面，但新增 `bundle_index.json` 和 `stock_pool.json`，为后续多股票做准备。

### 6.6 RunManifestContract

用途：记录一次产品 API 构建的输入、输出、状态、证据和发布结果。

建议字段：

```text
run_id
run_type: manual | shadow | scheduled_candidate | production
started_at
finished_at
producer_version
pool_ref
input_refs[]
generated_files[]
checker_result
status_gate_result
publish_status
rollback_ref
no_production_touch
warnings[]
blocks[]
```

要求：

1. 每次 bundle 生成必须有 run manifest。
2. manifest 必须记录输入文件和输出文件。
3. checker 未通过时，manifest 仍要写入 evidence 目录，但不得发布为前端当前 bundle。
4. shadow 运行的 manifest 不得宣称生产 PASS。

### 6.7 AtomicPublishContract

用途：保证前端读取到的 JSON 来自同一次完整构建。

建议流程：

```text
prepare staging dir
  -> generate all files
  -> validate schema
  -> run checker
  -> write bundle_index
  -> publish to docs data
  -> write run_manifest
```

发布状态：

```text
NOT_STARTED
STAGED
VALIDATED
PUBLISHED
ROLLED_BACK
FAILED
```

生产候选要求：

1. `bundle_index.json` 中所有文件必须存在。
2. 所有文件的 `run_id` 或 `bundle_id` 必须一致。
3. 发布失败必须保留上一次完整 bundle。

### 6.8 PositionDataContract

用途：为未来真实持仓接入预留安全边界。

公开视图字段：

```text
has_position
position_status: AVAILABLE | UNAVAILABLE | STALE | INVALID | PRIVATE_REDACTED
position_source_type
position_as_of
display_note
decision_blockers[]
```

私有快照字段：

```text
quantity
cost_price
market_price
market_value
unrealized_pnl
unrealized_pnl_pct
source_path
quality_flags[]
```

要求：

1. 未确认部署隐私边界前，`docs/` 只写公开视图。
2. 私有快照不得进入可公开发布目录。
3. 持仓缺失不得阻断行情观察，但必须阻断持仓盈亏和仓位建议。

### 6.9 SchemaVersionContract

用途：控制前后端契约升级。

建议字段：

```text
schema_version
bundle_version
producer_version
min_frontend_version
deprecated_fields[]
required_fields[]
optional_fields[]
compatibility_notes
```

要求：

1. 所有顶层产品 JSON 都必须包含 `schema_version`。
2. 兼容旧页面的 legacy 文件必须标记 `legacy_compat=true`。
3. 删除字段前必须先进入 deprecated 列表。
4. checker 必须校验关键 schema version 是否一致。

---

## 7. 五个会话拆分

### 7.1 会话一：产品股票池与成员治理底座

#### 目标

建立产品股票池概念，当前只放东睦股份，但架构支持后续增加股票。

#### 解决的问题

1. 消除后端和前端对 `600114` 的硬编码。
2. 把“当前只做一只”和“未来可扩展”同时保住。
3. 避免清空或污染 `baseline_registry.json`。

#### 建议 G3 修改范围

```text
代码文件/重点股票/product_eval/stock_pool.py
代码文件/重点股票/product_eval/product_api_bundle.py
scripts/build_keystock_product_api_bundle.py
tests/keystock_product_eval/test_stock_pool_contract.py
tests/keystock_product_eval/test_schema_version_contract.py
docs/keystock-dashboard/data/stock_pool.json
运行产物/重点股票产品化后评估/product_api/stock_pool.json
```

#### 关键实现

1. 新增 `ProductStockPoolService`。
2. 默认池成员来自内置配置或只读候选配置，当前仅 `600114`。
3. `ProductApiBundleService` 从 pool members 循环生成，而不是读 `self.primary_code`。
4. 输出 `stock_pool.json`。
5. 保留对旧 `stocks.json` 的兼容。
6. 为 `stock_pool.json` 增加 `schema_version`、`pool_version` 和 `source_refs`。

#### 验收命令

```bash
python3 -m py_compile 代码文件/重点股票/product_eval/stock_pool.py
python3 -m pytest tests/keystock_product_eval/test_stock_pool_contract.py tests/keystock_product_eval/test_schema_version_contract.py
python3 scripts/build_keystock_product_api_bundle.py --base-dir "运行产物/重点股票产品化后评估" --out-dir "运行产物/重点股票产品化后评估/product_api" --docs-data-dir "docs/keystock-dashboard/data"
jq '.members | length' docs/keystock-dashboard/data/stock_pool.json
jq '.members[0].stock_code' docs/keystock-dashboard/data/stock_pool.json
jq '.schema_version,.pool_version' docs/keystock-dashboard/data/stock_pool.json
```

#### 不做

1. 不扩展到 10 只股票。
2. 不定义未来入池业务规则。
3. 不修改 `baseline_registry.json`。

#### 进入 G3 前确认

确认当前产品池只包含东睦股份，且不清空历史 baseline 注册表。

---

### 7.2 会话二：数据状态闸门与结论分层

#### 目标

修正当前 `COMPLETE` 假阳性，建立数据状态和结论状态的统一闸门。

#### 解决的问题

1. `dashboard.json` 显示 COMPLETE，但实际存在 stale/date divergence。
2. checker 对日期分歧只给 WARN，仍可能推荐 COMPLETE。
3. 页面无法清楚区分正式结论、观察和试运行。

#### 建议 G3 修改范围

```text
代码文件/重点股票/product_eval/status_exporter.py
代码文件/重点股票/product_eval/analysis_run_state.py
代码文件/重点股票/product_eval/conclusion_status.py
代码文件/重点股票/product_eval/position_adapter.py
代码文件/重点股票/product_eval/product_api_bundle.py
scripts/check_keystock_dashboard_productization.py
tests/keystock_product_eval/test_dashboard_status_truth_gate.py
tests/keystock_product_eval/test_conclusion_status_contract.py
tests/keystock_product_eval/test_position_data_redaction.py
```

#### 关键实现

1. 新增 `ConclusionStatusService`。
2. 汇总 `DATA_STALE`、`DATA_DATE_DIVERGENCE`、`RULE_HEALTH_WARN`、`POSITION_UNAVAILABLE`。
3. `dashboard.overall_status` 不再单独相信上游 dashboard_status，而是由 bundle 统一推导。
4. checker 把关键日期分歧从非阻断 WARN 升级为生产 COMPLETE 阻断。
5. 页面数据输出 `conclusion_status` 和 `decision_blockers`。
6. 建立公开持仓视图和私有持仓快照边界，当前只输出公开 `UNAVAILABLE`。

#### 状态映射

```text
无阻断 + 数据新鲜 + 证据完整 + 规则非 WARN/BLOCK -> FORMAL / COMPLETE
有非关键降级 -> OBSERVATION / COMPLETE 或 AUTO_REPAIRING
试运行产物 -> SHADOW / COMPLETE
关键数据缺失或日期分歧 -> BLOCKED / BLOCK
```

具体映射应由测试固定，避免不同模块各说各话。

#### 验收命令

```bash
python3 -m py_compile 代码文件/重点股票/product_eval/status_exporter.py 代码文件/重点股票/product_eval/analysis_run_state.py
python3 -m pytest tests/keystock_product_eval/test_dashboard_status_truth_gate.py tests/keystock_product_eval/test_conclusion_status_contract.py tests/keystock_product_eval/test_position_data_redaction.py
python3 scripts/check_keystock_dashboard_productization.py --docs-dir docs/keystock-dashboard --data-dir docs/keystock-dashboard/data
jq '.overall_status,.blocks,.warnings' docs/keystock-dashboard/data/dashboard.json
jq '.decision_blockers,.conclusion_status' docs/keystock-dashboard/data/today_decisions.json
jq '.user_position.position_status,.user_position.position_source_type' docs/keystock-dashboard/data/today_decisions.json
```

#### 不做

1. 不修真实行情数据源。
2. 不接真实持仓。
3. 不把 OBSERVATION 改成正式买卖建议。

#### 进入 G3 前确认

确认存在 stale/date divergence 时，页面不得显示正式生产 COMPLETE。

---

### 7.3 会话三：产品 API bundle 与证据链聚合

#### 目标

把前端依赖的数据包从分散 JSON 升级为稳定、可追溯、可扩展的产品 API bundle。

#### 解决的问题

1. 前端目前读取多个扁平 JSON，缺少 bundle 索引。
2. 证据链只覆盖很少字段，页面无法系统下钻。
3. chart、decision、run_state、rule_health 的日期和状态可能不一致。

#### 建议 G3 修改范围

```text
代码文件/重点股票/product_eval/product_api_bundle.py
代码文件/重点股票/product_eval/evidence_trace_index.py
代码文件/重点股票/product_eval/rule_health_summary.py
代码文件/重点股票/product_eval/feature_service.py
scripts/build_keystock_product_api_bundle.py
tests/keystock_product_eval/test_product_api_bundle.py
tests/keystock_product_eval/test_product_api_bundle_index.py
tests/keystock_product_eval/test_run_manifest_contract.py
tests/keystock_product_eval/test_atomic_publish_contract.py
docs/keystock-dashboard/data/
运行产物/重点股票产品化后评估/product_api/
```

#### 关键实现

1. 输出 `bundle_index.json`，列明每个文件、股票、生成时间、状态和 source refs。
2. 按股票生成详情数据，当前只生成 `stocks/600114/*`。
3. 保留旧 `chart_data.json`、`today_decisions.json` 作为兼容入口。
4. 所有关键业务字段包含 `source_path` 或 `source_field_refs`。
5. 对 date divergence 做统一记录，不让 chart 和 decision 各自解释。
6. evidence index 至少覆盖 feature snapshot、kline cache、rule health、backtest。
7. 输出 `run_manifest.json`，记录输入、输出、checker、发布状态和回滚引用。
8. 采用 staging 目录生成 bundle，通过检查后再发布到 docs data。

#### 验收命令

```bash
python3 -m py_compile 代码文件/重点股票/product_eval/product_api_bundle.py
python3 -m pytest tests/keystock_product_eval/test_product_api_bundle.py tests/keystock_product_eval/test_product_api_bundle_index.py tests/keystock_product_eval/test_run_manifest_contract.py tests/keystock_product_eval/test_atomic_publish_contract.py
python3 scripts/build_keystock_product_api_bundle.py --base-dir "运行产物/重点股票产品化后评估" --out-dir "运行产物/重点股票产品化后评估/product_api" --docs-data-dir "docs/keystock-dashboard/data"
jq '.files' docs/keystock-dashboard/data/bundle_index.json
jq '.source_refs // .data_sources' docs/keystock-dashboard/data/stocks/600114/detail.json
jq '.run_id,.publish_status,.generated_files' docs/keystock-dashboard/data/run_manifest.json
```

#### 不做

1. 不接外部联网数据源。
2. 不修复正式日报 sidecar。
3. 不改正式报告目录。

#### 进入 G3 前确认

确认前端仍以静态 JSON bundle 方式运行，暂不引入后端 Web 服务。

---

### 7.4 会话四：交互式前端产品页

#### 目标

把静态驾驶舱升级为可日常使用的重点股票产品页面。

#### 解决的问题

1. 当前页面可看但不够像工具，缺少状态解释和详情联动。
2. 用户无法快速知道“为什么不是正式结论”。
3. 证据、规则健康、日期状态、持仓状态分散。

#### 建议 G3 修改范围

```text
docs/keystock-dashboard/index.html
docs/keystock-dashboard/app.css
docs/keystock-dashboard/app.js
docs/keystock-dashboard/data/
tests/keystock_product_eval/test_static_dashboard_smoke.py
tests/keystock_product_eval/test_dashboard_visual_contract.py
tests/keystock_product_eval/test_dashboard_no_fake_data.py
```

#### 关键实现

1. 前端从 `stock_pool.json` 和 `bundle_index.json` 初始化。
2. 首页只加载 `stock_pool.json`、`stocks.json` 和 `bundle_index.json`，详情、图表、证据按股票懒加载。
3. 详情页展示：
   - 今日价格和技术状态
   - 持仓状态
   - 结论状态
   - 阻断原因
   - 证据链
   - 规则健康
   - 图表
4. 首页展示产品池总览和东睦关键卡片。
5. 页面明确区分 `FORMAL`、`OBSERVATION`、`SHADOW`、`BLOCKED`。
6. 不用 in-app 文字解释系统功能说明，状态文字只服务于用户判断。
7. 页面显示 bundle 生成时间、数据日期和状态来源，避免用户误读旧数据。
8. BLOCKED 状态下仍能展示历史行情和证据，但不得显示正式动作。

#### 前端体验要求

1. 第一屏必须让用户知道今天能不能信这个页面。
2. 状态异常时，不把用户淹没在工程日志中，只展示关键原因和可下钻证据。
3. 图表和表格不得依赖硬编码股票。
4. 移动端和桌面端不能出现文本重叠。
5. UI 应保持工作型、清晰、可扫描，不做营销页。
6. 网络或 JSON 加载失败时，页面显示数据包不可用，而不是空白或沿用旧状态。

#### 验收命令

```bash
python3 -m pytest tests/keystock_product_eval/test_static_dashboard_smoke.py tests/keystock_product_eval/test_dashboard_no_fake_data.py tests/keystock_product_eval/test_dashboard_visual_contract.py
python3 scripts/check_keystock_dashboard_productization.py --docs-dir docs/keystock-dashboard --data-dir docs/keystock-dashboard/data
```

如该会话需要视觉验收，应启动本地静态服务后用浏览器截图检查：

```bash
python3 -m http.server 8765 --directory docs/keystock-dashboard
```

#### 不做

1. 不引入大型前端框架，除非后续单独确认。
2. 不接登录、权限、云部署。
3. 不展示未接入的持仓盈亏。

#### 进入 G3 前确认

确认本阶段前端仍是静态站点，不做后台服务和用户登录。

---

### 7.5 会话五：shadow 刷新、验收闭环与生产放行准备

#### 目标

在不切生产的前提下，建立自动刷新候选链路、验收证据和未来生产切换条件。

#### 解决的问题

1. 当前产品 API 需要手动构建。
2. 调度注册表没有产品页面刷新入口。
3. 没有连续多日 shadow 运行证据，无法谈生产。

#### 建议 G3 修改范围

```text
scripts/build_keystock_product_api_bundle.py
scripts/check_keystock_dashboard_productization.py
scripts/run_keystock_dashboard_shadow_refresh.py
tests/keystock_product_eval/
运行产物/重点股票产品化后评估/evidence/
运行产物/重点股票产品化后评估/product_api/
运行产物/重点股票产品化后评估/product_api/_staging/
```

只读检查：

```text
00_项目地基/06_调度与运行/runtime_entry_registry.json
```

#### 关键实现

1. 新增 shadow refresh 脚本，只生成产品 API 和 docs data，不注册 launchd。
2. 生成 shadow run evidence：
   - run id
   - started_at / finished_at
   - files generated
   - checker result
   - status gate result
   - no production touch evidence
3. checker 成为生产前置门。
4. 形成生产切换条件清单，但不执行切换。
5. 保留最近一次成功 bundle 的 rollback ref。
6. 验证 docs data 与 product_api 当前 bundle 的 run_id 一致。

#### 生产切换最低条件

至少满足：

1. 连续多个交易日 shadow refresh PASS。
2. 无 `DATA_DATE_DIVERGENCE`。
3. 无关键数据 stale。
4. checker 无 BLOCK。
5. 页面无假 COMPLETE。
6. 产品池成员治理明确。
7. 持仓来源明确，或页面正式定义为“无持仓分析页”。
8. G4/G5/G6 证据齐全。
9. 用户明确授权修改 runtime/launchd。
10. 最近一次 shadow manifest 有可回滚对象。
11. 公开目录无未脱敏持仓成本、数量、盈亏字段。

#### 验收命令

```bash
python3 -m py_compile scripts/run_keystock_dashboard_shadow_refresh.py
python3 scripts/run_keystock_dashboard_shadow_refresh.py --dry-run
python3 scripts/check_keystock_dashboard_productization.py --docs-dir docs/keystock-dashboard --data-dir docs/keystock-dashboard/data
python3 -m pytest tests/keystock_product_eval
jq '.no_production_touch,.checker_overall,.generated_files' 运行产物/重点股票产品化后评估/evidence/keystock_dashboard_shadow_refresh_*.json
jq '.run_id,.publish_status,.rollback_ref' docs/keystock-dashboard/data/run_manifest.json
```

#### 不做

1. 不修改 `runtime_entry_registry.json`。
2. 不调用 `generate_launchd.py` 注册任务。
3. 不加载 launchd。
4. 不宣布生产 PASS。

#### 进入 G3 前确认

确认本会话只做 shadow/dry-run，不切生产。

---

## 8. 允许修改范围总表

后续 5 个会话可按需申请以下范围：

```text
代码文件/重点股票/product_eval/
scripts/build_keystock_product_api_bundle.py
scripts/check_keystock_dashboard_productization.py
scripts/run_keystock_dashboard_shadow_refresh.py
docs/keystock-dashboard/
tests/keystock_product_eval/
运行产物/重点股票产品化后评估/product_api/
运行产物/重点股票产品化后评估/evidence/
```

允许新增的 `.md` 文件仅限阶段方案、审计记录或用户要求的文档沉淀。实际产品能力必须通过代码、测试、脚本、schema 或 JSON 产物实现。

---

## 9. 禁止修改范围总表

后续 5 个会话默认禁止：

```text
重点股票/股票报告/
重点股票/深度分析/
重点股票/基线/
00_项目地基/02_权威注册表/baseline_registry.json
00_项目地基/06_调度与运行/runtime_entry_registry.json
正式规则资产
launchd 注册或加载状态
外部 API token/cookie/付费数据源
```

除非用户在对应会话单独授权，否则不得触碰这些范围。

---

## 10. 主要风险与设计防护

### 10.1 股票池污染

风险：把历史 baseline 股票误认为当前产品池成员。

防护：产品池独立为 `ProductStockPoolContract`，当前只含东睦股份；`baseline_registry.json` 只作为 baseline 权威源。

### 10.2 状态假阳性

风险：页面显示 COMPLETE，但实际数据 stale 或日期分歧。

防护：统一状态闸门；checker 对生产 COMPLETE 执行阻断检查。

### 10.3 证据不可追溯

风险：页面数字能显示，但不知道来源。

防护：关键字段强制 `source_path`、`source_field_refs`、`evidence_refs`。

### 10.4 观察结论误当正式结论

风险：用户把 shadow/observe 当成正式建议。

防护：引入 `conclusion_status`，页面明确标识 `FORMAL/OBSERVATION/SHADOW/BLOCKED`。

### 10.5 持仓缺失导致错误决策

风险：没有成本和持仓，却输出仓位建议。

防护：`POSITION_UNAVAILABLE` 禁止计算盈亏和仓位动作。

### 10.6 前端与后端契约漂移

风险：前端读取旧字段，后端输出新字段，页面静默错误。

防护：`bundle_index.json`、契约测试、dashboard smoke test。

### 10.7 过早切生产

风险：未经过 shadow 和 G5/G6，就进入正式调度。

防护：会话五只做生产准备，不切 runtime/launchd；生产切换另走授权。

### 10.8 半更新数据包

风险：构建中途失败，前端读到新旧 JSON 混合，形成错误页面状态。

防护：引入 `AtomicPublishContract`，先写 staging，通过 checker 后再发布；`run_id` 不一致时 checker BLOCK。

### 10.9 schema 无版本导致维护困难

风险：后端新增或删除字段后，前端静默读错，测试也难以定位。

防护：所有顶层 JSON 增加 `schema_version`，legacy 文件标记 `legacy_compat=true`，删除字段必须先 deprecated。

### 10.10 持仓隐私泄露

风险：真实成本、数量、盈亏被写入 `docs/` 静态目录，后续部署时意外公开。

防护：持仓分公开视图和私有快照；公开目录只允许 `position_status` 和展示说明，私有数值必须通过脱敏测试。

### 10.11 多股票扩展时前端性能退化

风险：未来股票池增加后，一次性加载全部详情、图表和证据，页面变慢且难维护。

防护：从第一版就采用 summary + detail lazy load 结构，即使当前只有东睦股份也按分片模型实现。

---

## 11. 总体验收命令

五个会话逐步完成后，最低总体验收命令：

```bash
python3 -m py_compile 代码文件/重点股票/product_eval/*.py
python3 -m pytest tests/keystock_product_eval
python3 scripts/build_keystock_product_api_bundle.py --base-dir "运行产物/重点股票产品化后评估" --out-dir "运行产物/重点股票产品化后评估/product_api" --docs-data-dir "docs/keystock-dashboard/data"
python3 scripts/check_keystock_dashboard_productization.py --docs-dir docs/keystock-dashboard --data-dir docs/keystock-dashboard/data
jq '.members' docs/keystock-dashboard/data/stock_pool.json
jq '.overall_status,.blocks,.warnings' docs/keystock-dashboard/data/dashboard.json
jq '.conclusion_status,.decision_blockers' docs/keystock-dashboard/data/today_decisions.json
jq '.run_id,.publish_status,.generated_files' docs/keystock-dashboard/data/run_manifest.json
jq '.schema_version,.bundle_version' docs/keystock-dashboard/data/bundle_index.json
```

预期：

1. 产品池只有东睦股份。
2. 没有代码层业务硬编码股票。
3. 日期分歧时不得推荐生产 COMPLETE。
4. 持仓未接入时不得生成盈亏和仓位建议。
5. checker 不允许假阳性。
6. 所有关键字段有来源引用。
7. 不修改禁止范围。
8. `bundle_index.json`、`run_manifest.json`、各顶层 JSON 的版本和 run id 一致。
9. `docs/` 目录不包含未脱敏的真实持仓成本、数量、盈亏。
10. staging 发布失败时，不覆盖上一次完整 bundle。

---

## 12. 不切生产证明

本五会话方案在完成前均不构成生产切换。

不切生产证据要求：

1. `runtime_entry_registry.json` 未修改。
2. 未调用 launchd 注册或加载命令。
3. 未修改正式日报、深度分析、baseline 文件。
4. 未修改正式规则资产。
5. 产品 API 只写入后评估产物和 docs 静态数据目录。
6. shadow refresh 只生成 dry-run evidence。
7. G6 前不得声明生产 PASS。
8. 未经单独授权，不把私有持仓快照写入 `docs/`。
9. 未经单独授权，不把 shadow refresh 注册到 runtime/launchd。

---

## 13. 下一步建议

建议后续按以下 5 个会话推进：

```text
会话一：产品股票池与成员治理底座
会话二：数据状态闸门与结论分层
会话三：产品 API bundle 与证据链聚合
会话四：交互式前端产品页
会话五：shadow 刷新、验收闭环与生产放行准备
```

每个会话开始时，应先复述本文件对应章节，给出该会话的 G2 子方案和 G3 文件范围。用户确认后才能进入 G3。

---

## 14. 用户可见状态

本文件产出状态：

```text
COMPLETE
```

产品页面生产状态：

```text
BLOCK
```

原因：当前仍未完成股票池抽象、状态闸门、产品 API 契约、交互前端和 shadow 刷新闭环。
