# 重点股票分析生产线产品化方案 v0.1

> 日期：2026-06-16
> 阶段：G2 技术子方案候选
> 上位框架：`PLAN_重点股票产品化分析闭环总框架_v0.1.md`
> 对应步骤：第 3 步，分析生产线产品化方案
> 边界：本文只定义 G2 产品化方案、契约、状态、重跑、告警和后续 G3 执行边界；不修改生产报告、不修改 baseline registry、不切换 runtime entry、不放行任何投资或回测结论。

---

## 1. 前置检查结论

已按总框架第 12 节完成本步骤用户确认。

用户确认的产品口径：

1. 第一屏不展示系统技术告警，而是展示某只股票今天走势、持仓、成本、盈利、今日走势的人话分析、支撑该分析的技术参数或图表，以及第二天决策。
2. 技术失败应由系统自动监控、自动重跑、自动通知 AI 团队/角色处理；只有失败救不回来且影响分析或决策，才弹出告知用户。
3. 需要一键重跑某只股票，但必须明确使用场景，避免把技术自愈责任转嫁给用户。

因此，分析生产线产品化的核心不是增加用户要看的技术后台，而是把后台复杂性封装起来，稳定输出一个面向用户的 `StockTodayDecisionView`。

---

## 2. 流程编号与阶段门

流程编号：F-ANALYSIS。

当前阶段：G2 技术子方案候选。

后续阶段：

```text
G0 需求识别与路由
  -> G1 用户/金融口径确认
  -> G2 技术方案
  -> G3 实施，需用户显式授权
  -> G4 执行方自检候选
  -> G5 旧影独立复查候选
  -> G6 腰子放行/归档/同步，按阶段政策确认
```

本文件不进入 G3。

---

## 3. 产品目标

分析生产线第一阶段要稳定回答一个用户问题：

```text
我今天看这只股票，应该知道什么，明天该怎么做？
```

第一屏目标对象为：

```text
StockTodayDecisionView
```

最低展示内容：

1. 股票今天走势：价格、涨跌幅、成交量、关键价位相对位置、日内/日线状态。
2. 我的持仓：持仓数量、成本、当前市值、浮盈亏、仓位占比；若没有持仓，则展示空仓状态和可观察条件。
3. 今日走势分析：用人话解释今天为什么这样走，明确是趋势延续、支撑反弹、破位、放量冲高回落、缩量观望还是风险事件驱动。
4. 证据与图表：至少关联技术参数、支撑/压力/止损、成交量、资金或板块相位；前端可画图，后端先输出结构化数据。
5. 第二天决策：持有、观察、减仓、止损、加仓等待、禁止动作，以及触发条件。

技术后台只在详情页或运维视图暴露。第一屏不得被工程告警、脚本日志、schema 名称、角色流程淹没。

---

## 4. 角色职责与待确认项

### 4.1 已确认

1. 用户第一屏优先级：股票走势、持仓、盈亏、分析、证据、次日决策。
2. 技术失败处理原则：后台自愈优先，救不回来且影响分析再告知用户。
3. 一键重跑能力：需要，但必须绑定清晰场景。

### 4.2 仍需后续确认，但不阻塞本 G2 方案

1. 持仓数据来源：手工维护、模拟交易账户、券商导出、还是现有组合文件。
2. 第一阶段样例股票：若 Phase 1 试点股票选择影响用户使用优先级，需按总框架第 12.2 节确认。
3. 是否允许在 G3 新增 `analysis_pipeline_status.json`、`stock_today_decision_view.json`、`alert_center.json` 等候选产物。

---

## 5. 允许修改范围

后续 G3 可申请的最小修改范围：

```text
00_项目地基/03_报告对象/
00_项目地基/04_一致性闸门/
00_项目地基/06_后评估闭环/
代码文件/tools/
scripts/
tests/
```

允许新增：

1. `AnalysisProductionContract` schema。
2. `StockTodayDecisionView` schema。
3. `AnalysisProductionStatus` 生成脚本。
4. `alert_center.json` 生成脚本。
5. 重跑幂等检查脚本。
6. 只读资产扫描脚本。
7. schema/golden/negative 测试。

允许读取但默认不写入：

```text
重点股票/股票报告/
重点股票/深度分析/
00_项目地基/02_权威注册表/baseline_registry.json
00_项目地基/06_调度与运行/runtime_entry_registry.json
```

---

## 6. 禁止修改范围

本步骤和后续未获授权的 G3 前禁止：

1. 修改正式日报 MD/JSON/HTML/PDF。
2. 修改深度分析正文或历史报告。
3. 修改 `baseline_registry.json`。
4. 修改 `runtime_entry_registry.json` 或 launchd 调度。
5. 修改正式规则资产。
6. 切换 canonical 到真实生产链路。
7. 接入新数据源、付费 API、token、cookie 或批量下载。
8. 生成正式回测结论或投资放行结论。

---

## 7. 当前资产依据

只读检查显示，分析生产线已有以下地基：

| 类别 | 现有资产 | 方案结论 |
|:--|:--|:--|
| baseline 权威源 | `00_项目地基/02_权威注册表/baseline_registry.json` | 继续作为唯一权威源 |
| baseline 契约 | `baseline_authority_contract.md` | 无有效或多有效 baseline 均 BLOCK |
| 日报 sidecar | `重点股票/股票报告/{name}({code})/{name}({code})日报_{date}.json` | 作为机器字段主要来源 |
| MD/sidecar 闸门 | `scripts/check_md_sidecar_consistency.py` | 作为日报完整性关键闸门 |
| canonical shadow | `canonical_report_contract.md`、`scripts/run_canonical_shadow.py` | Phase 1 仍 shadow-only |
| 调度注册 | `runtime_entry_registry.json` | 不在本步骤修改 |
| 日报调度 | `代码文件/tools/daily_orchestrator.py --mode daily` | 现有信号链路，后续只包状态，不切入口 |
| 深度分析调度 | `代码文件/tools/daily_orchestrator.py --mode deep` | 周度信号入口，后续只包状态，不切入口 |
| 重点股票入口 | `代码文件/重点股票/run_keystock_analysis.py` | 当前偏薄，适合后续封装状态，不直接承担全部生产逻辑 |
| 深度分析解析 | `代码文件/深度分析/parse_deep_analysis_report.py` | 可作为 baseline/证据结构化候选来源 |

---

## 8. 用户第一屏契约

### 8.1 StockTodayDecisionView

用途：面向用户的第一屏后端契约，不暴露后台工程细节。

建议字段：

```text
view_id
stock_code
stock_name
trade_date
as_of_time
user_position
market_today
plain_language_summary
technical_evidence
chart_refs
baseline_refs
decision_for_next_day
confidence
decision_blockers
user_visible_status: COMPLETE | AUTO_REPAIRING | BLOCK
updated_at
```

### 8.2 user_position

字段：

```text
has_position
quantity
cost_price
market_price
market_value
unrealized_pnl
unrealized_pnl_pct
position_weight
position_source
position_as_of
```

规则：

1. 有持仓数据时，第一屏必须展示成本和盈亏。
2. 无持仓数据时，展示 `has_position=false`，不得伪造成本或盈亏。
3. 持仓数据缺失不应阻断股票分析，但应标注“持仓未接入/未填写”。
4. 如果持仓数据过期且会影响决策，进入 `decision_blockers`。

### 8.3 market_today

字段：

```text
open
high
low
close
change_pct
volume
turnover
intraday_pattern
relative_to_support
relative_to_pressure
relative_to_stop_loss
sector_phase
fund_flow_summary
data_freshness_status
```

### 8.4 plain_language_summary

要求：

1. 用 3-5 句话解释今天走势。
2. 必须引用结构化证据，不允许只写情绪化判断。
3. 必须区分“事实发生了什么”和“系统判断是什么”。
4. 数据不足时直说数据不足，不得编造解释。

建议模板：

```text
今天这只股票属于 {走势类型}。
价格相对关键位 {位置关系}，成交量 {量能状态}，资金 {资金状态}，板块 {板块状态}。
因此系统判断 {结论}。
明天主要看 {触发条件}，若 {条件A} 则 {动作A}，若 {条件B} 则 {动作B}。
```

### 8.5 technical_evidence

最低字段：

```text
ma5
ma10
ma20
rsi
macd
volume_ratio
support_levels
pressure_levels
stop_loss
risk_light
fund_flow_4level
sector_phase
evidence_refs
```

说明：

1. 后端先输出图表所需数据，不要求 Phase 1 做 UI。
2. 图表引用以 `chart_refs` 描述，例如 K 线、均线、支撑压力、成交量、资金流。
3. 所有技术参数必须能追溯到 sidecar、baseline 或 D04/D06 特征服务。

### 8.6 decision_for_next_day

字段：

```text
primary_action
position_suggestion
stop_loss
take_profit_or_pressure
observe_conditions
forbidden_actions
trigger_if_up
trigger_if_down
trigger_if_flat
reason_codes
confidence
```

约束：

1. 决策必须承接权威 baseline，不重算深度分析。
2. 如果 baseline 无效或冲突，决策必须 BLOCK。
3. 如果报告成功但账本/sidecar/闸门失败，用户可读报告可保留，但第一屏不得标 COMPLETE。

---

## 9. AnalysisProductionContract

用途：统一深度分析和日报生产线的运行对象、状态、输入输出和失败处理。

字段：

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
stock_today_view_ref
status: PENDING | RUNNING | PASS | WARN | ALERT | BLOCK
self_healing_status: NOT_REQUIRED | QUEUED | RUNNING | FIXED | ESCALATED | FAILED
retry_policy
retry_count
failure_reason
failure_impact
user_visible_status: COMPLETE | AUTO_REPAIRING | BLOCK
evidence_refs
created_at
updated_at
```

关键约束：

1. 深度分析和日报都必须有运行状态。
2. 第一屏读取 `StockTodayDecisionView`，不直接读取脚本日志。
3. 报告成功但 sidecar 失败，不得标 COMPLETE。
4. sidecar 成功但 MD/sidecar 不一致，按现有闸门规则 WARN 或 BLOCK。
5. 账本写入失败时，报告可作为人读产物保留，但闭环状态不得 COMPLETE。
6. canonical Phase 1 只允许 shadow-only，不作为真实生产输入。

---

## 10. 状态机设计

### 10.1 内部状态

```text
PENDING
  -> RUNNING
  -> PASS
  -> WARN
  -> ALERT
  -> BLOCK
```

内部状态含义：

| 状态 | 含义 | 用户第一屏 |
|:--|:--|:--|
| PASS | 生产线完整通过 | COMPLETE |
| WARN | 有非关键问题，不影响分析决策 | COMPLETE 或 AUTO_REPAIRING |
| ALERT | 需要后台处理，暂不影响用户决策或正在自愈 | AUTO_REPAIRING |
| BLOCK | 影响分析或决策，无法自动恢复 | BLOCK |

### 10.2 用户可见状态

用户只看三类：

```text
COMPLETE
AUTO_REPAIRING
BLOCK
```

展示规则：

1. `COMPLETE`：第一屏可用，走势/持仓/证据/次日决策完整。
2. `AUTO_REPAIRING`：系统正在后台修复，第一屏可展示上一次可信结果或部分结果，但必须标注数据时间。
3. `BLOCK`：当前结果会误导决策，必须明确告诉用户不能按本次分析行动。

### 10.3 失败影响分级

| 失败点 | 默认处理 | 是否第一屏告知 |
|:--|:--|:--|
| 数据临时未就绪 | 自动重试 | 否 |
| API 短时失败 | 自动重试/缓存降级 | 否 |
| sidecar 缺辅助字段 | 自动补齐或 WARN | 否 |
| canonical shadow 失败 | 记录 WARN | 否 |
| baseline 缺失 | BLOCK | 是 |
| 多有效 baseline | BLOCK | 是 |
| MD/sidecar 决策字段冲突 | BLOCK | 是 |
| 关键行情 freshness 不合格 | BLOCK 或 AUTO_REPAIRING | 只在救不回来时是 |
| 账本写入失败 | AUTO_REPAIRING，超过阈值 BLOCK | 只在影响闭环时是 |
| 持仓数据缺失 | 不阻断股票分析 | 只提示持仓未接入 |
| 持仓数据过期且影响动作 | BLOCK 或用户确认 | 是 |

---

## 11. 后台自愈与告警

### 11.1 原则

技术问题优先由系统处理：

```text
detect
  -> classify
  -> retry
  -> fallback
  -> notify_ai_team_or_role
  -> escalate_to_user_only_if_decision_impacted
```

用户不应承担：

1. 判断脚本是否失败。
2. 判断该不该重跑。
3. 判断 schema 或 sidecar 是否一致。
4. 判断哪个后台角色应处理。

用户只需要知道：

```text
这个股票今天能不能看？
这份分析能不能用于明天决策？
如果不能，为什么不能？
```

### 11.2 AlertCenterContract

字段：

```text
alert_id
stock_code
stock_name
trade_date
source_run_id
severity: INFO | WARN | ALERT | BLOCK
category
technical_reason
decision_impact
self_healing_action
self_healing_status
assigned_route
user_visible
user_message
created_at
updated_at
resolved_at
```

`user_visible=false` 的告警只进入后台。

`user_visible=true` 只允许在以下情况出现：

1. 已超过自动重试上限。
2. 失败影响今日走势判断或次日决策。
3. baseline、持仓、关键行情、MD/sidecar 决策字段存在不可自动裁定冲突。
4. 需要用户业务偏好或持仓事实才能继续。

### 11.3 自动通知 AI 团队/角色

本方案不让执行模型冒充任何项目角色。自动通知只生成路由任务或候选告警：

```text
route_target
problem_summary
evidence_refs
required_action
blocking_condition
```

执行模型只能生成 G3 实施结果和 G4 自检候选，不得签署 G5/G6。

---

## 12. 重跑幂等设计

### 12.1 为什么需要一键重跑

一键重跑不是让用户修技术问题，而是用于以下用户真实场景：

1. 用户刚补充或修正持仓成本/数量，需要重新计算盈亏和次日动作。
2. 收盘后或盘中关键数据更新，用户想刷新某只股票的今日视图。
3. 出现重大事件、公告、板块异动，用户希望重新生成当日判断。
4. 第一屏显示 `AUTO_REPAIRING` 太久，用户希望主动触发同一只股票的恢复流程。
5. 用户认为人话解释与证据不匹配，需要重建 view 并重新过闸门。
6. baseline 到期、反证条件触发、支撑破位等会改变决策的问题，需要判断是否只重跑日报或升级深度分析。

不应由用户一键重跑处理的场景：

1. 普通 API 抖动。
2. 单次脚本超时。
3. 可自动补齐的 sidecar 辅助字段。
4. canonical shadow 失败。
5. 后台日志清理或非决策字段告警。

这些由系统自动重试和自愈。

### 12.2 重跑类型

| 类型 | 触发场景 | 影响范围 |
|:--|:--|:--|
| `rerun_view_only` | 持仓或展示层字段变化 | 只重建第一屏 view |
| `rerun_daily_report` | 数据更新、日报解释需刷新 | 日报、sidecar、闸门、view、账本候选 |
| `rerun_sidecar_gate` | 报告存在但机器字段或闸门异常 | sidecar、consistency gate、view |
| `rerun_deep_analysis_review` | baseline 到期、反证触发、深度逻辑失效 | 生成深度分析重做任务，不直接改 baseline |
| `rerun_full_chain_candidate` | 仅 G3 明确授权后用于试点 | 深度分析候选、baseline 候选、日报、sidecar、view |

Phase 1 默认只实现 `rerun_view_only`、`rerun_daily_report`、`rerun_sidecar_gate` 的候选能力。

### 12.3 幂等键

```text
run_type
stock_code
trade_date
baseline_id
input_snapshot_hash
position_snapshot_hash
rule_version
rerun_reason_code
```

幂等规则：

1. 同一幂等键重复重跑，不新增冲突账本。
2. 输出路径必须可预测。
3. 新结果替代旧结果时，旧对象标记 `superseded_by`。
4. 报告正文不应被静默覆盖；正式覆盖策略需 G3 执行包单独授权。
5. 失败重跑必须记录 retry_count 和 failure_reason。

---

## 13. 文件级清单

### 13.1 本步骤新增

| 文件 | 理由 |
|:--|:--|
| `00_项目地基/06_后评估闭环/PLAN_重点股票分析生产线产品化方案_v0.1.md` | 第 3 步 G2 子方案产物，用于承接用户确认和后续 G3 执行包 |

### 13.2 后续 G3 候选文件

| 文件 | 类型 | 作用 |
|:--|:--|:--|
| `00_项目地基/03_报告对象/analysis_production_contract.schema.json` | schema | 定义生产线运行状态对象 |
| `00_项目地基/03_报告对象/stock_today_decision_view.schema.json` | schema | 定义用户第一屏契约 |
| `00_项目地基/03_报告对象/alert_center.schema.json` | schema | 定义后台告警和用户可见告警 |
| `scripts/build_analysis_production_status.py` | script | 只读聚合日报、sidecar、baseline、闸门状态 |
| `scripts/build_stock_today_decision_view.py` | script | 生成第一屏 JSON |
| `scripts/check_analysis_rerun_idempotency.py` | script | 检查重跑幂等和冲突 |
| `tests/test_analysis_production_contract.py` | test | schema/golden/negative 测试 |

### 13.3 不应在 Phase 1 修改的文件

```text
00_项目地基/02_权威注册表/baseline_registry.json
00_项目地基/06_调度与运行/runtime_entry_registry.json
重点股票/股票报告/**
重点股票/深度分析/**
正式规则资产
launchd plist
```

---

## 14. 脚本/函数/字段设计

### 14.1 build_analysis_production_status.py

输入：

```text
--code
--name
--date
--report-root
--out
```

读取：

1. baseline registry。
2. 日报 MD/sidecar。
3. MD/sidecar consistency gate 输出。
4. canonical shadow 输出，如存在。
5. 账本写入状态，如存在。
6. 持仓 snapshot，如存在。

输出：

```text
analysis_pipeline_status.json
```

### 14.2 build_stock_today_decision_view.py

输入：

```text
--code
--name
--date
--position-snapshot optional
--analysis-status
--out
```

输出：

```text
stock_today_decision_view.json
```

核心函数：

```text
load_sidecar()
load_current_baseline()
load_position_snapshot()
derive_market_today()
derive_plain_language_summary()
derive_technical_evidence()
derive_next_day_decision()
derive_user_visible_status()
```

### 14.3 check_analysis_rerun_idempotency.py

输入：

```text
--code
--date
--run-type
--input-snapshot-hash
--position-snapshot-hash
--rule-version
```

输出：

```text
rerun_idempotency_check.json
```

判定：

```text
PASS
WARN
BLOCK
```

---

## 15. 验收命令

本 G2 方案只需验证文件存在和未触碰生产范围：

```bash
test -f "00_项目地基/06_后评估闭环/PLAN_重点股票分析生产线产品化方案_v0.1.md"
git diff --name-only
```

后续 G3 执行包建议验收命令：

```bash
python3 scripts/check_baseline_authority.py --all --date <YYYYMMDD>
python3 scripts/check_md_sidecar_consistency.py --all --date <YYYYMMDD>
python3 scripts/check_runtime_entry_authority.py
python3 scripts/build_analysis_production_status.py --code <code> --name <name> --date <YYYYMMDD> --out /private/tmp/analysis_pipeline_status.json
python3 scripts/build_stock_today_decision_view.py --code <code> --name <name> --date <YYYYMMDD> --analysis-status /private/tmp/analysis_pipeline_status.json --out /private/tmp/stock_today_decision_view.json
python3 scripts/check_analysis_rerun_idempotency.py --code <code> --date <YYYYMMDD> --run-type daily_report
python3 -m pytest tests/test_analysis_production_contract.py
```

说明：G3 前不得把上述候选脚本当作已存在事实。

---

## 16. 回滚/不切生产证明

本方案阶段的回滚方式：

```text
删除本 G2 子方案文件即可回滚本步骤产物。
```

不切生产证明：

1. 未修改 `baseline_registry.json`。
2. 未修改 `runtime_entry_registry.json`。
3. 未修改 launchd。
4. 未修改重点股票正式报告目录。
5. 未修改深度分析正式报告目录。
6. 未修改正式规则资产。
7. 未切换 canonical 真实链路。

---

## 17. 执行顺序

后续推荐顺序：

```text
1. 用本方案冻结用户第一屏契约
2. 与后评估/回测 v0.2 对齐 PredictionLedger 和 FeatureSnapshot 输入
3. 生成 Phase 1 后端 MVP 执行包
4. 用户确认是否进入 G3
5. G3 新增 schema、脚本、测试和 /private/tmp 候选输出
6. G4 自检候选
7. G5 独立复查候选
8. G6 放行/归档/同步
```

---

## 18. G0-G6 连续执行说明与 BLOCK 停止条件

可自动推进：

1. 继续读取地基文件。
2. 生成 G2 方案草案。
3. 生成后续 G3 执行包草案。
4. 运行只读校验。

必须停止并询问用户：

1. 进入 G3 实施前。
2. 需要修改生产报告、baseline registry、runtime entry、launchd、正式规则资产前。
3. 需要接入新数据源、付费 API、token、cookie 或批量下载前。
4. 发现多个权威入口且无法从地基自动裁定时。
5. 样例股票选择影响用户优先级时。
6. 是否接受关键 WARN 或延期 Phase 1 验收项时。
7. 进入 G6 放行/归档前，如阶段政策要求确认。

---

## 19. 用户可见状态

当前状态：

```text
COMPLETE
```

含义：

1. 第 3 步用户确认已完成。
2. 分析生产线产品化 G2 子方案已形成。
3. 未进入 G3。
4. 未修改生产规则、生产报告、baseline registry、runtime entry 或 launchd。

---

## 20. 本方案结论

分析生产线产品化应以用户第一屏为牵引：

```text
股票今天走势
  -> 我的持仓和盈亏
  -> 人话解释
  -> 技术参数/图表证据
  -> 第二天决策
```

后台工程能力必须服务于这个第一屏：

```text
baseline 权威
sidecar/canonical 机器契约
质量闸门
状态 JSON
自动重试
重跑幂等
告警升级
证据链索引
```

用户不应看到普通技术失败；用户只应在结果无法用于决策时收到明确、短促、可行动的 BLOCK 提示。
