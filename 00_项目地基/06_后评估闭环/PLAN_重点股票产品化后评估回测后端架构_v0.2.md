# 重点股票产品化后评估/回测后端架构方案 v0.2

> 日期：2026-06-16
> 阶段：G2 技术子方案候选
> 上位框架：`PLAN_重点股票产品化分析闭环总框架_v0.1.md`
> 定位：在重点股票产品化分析闭环下，定义后评估/回测后端能力的第一阶段落地方案。
> 边界：本文不替代总框架，不直接修改生产规则，不切换日报/深度分析生产入口，不放行任何回测结论。

---

## 1. 修订定位

v0.1 文件把深度分析、日报、后评估、回测、规则治理、驾驶舱放在同一个大方案里讨论，方向正确，但执行边界过宽。

v0.2 的定位调整为：

```text
重点股票产品化分析闭环总框架
  -> 后评估/回测后端能力子方案
```

本文件只回答：

```text
后评估/回测后端第一阶段怎么落地？
依赖哪些 D01-D12 能力？
需要哪些结构化契约？
第一阶段做什么、不做什么？
怎么验收可以进入 G3？
```

---

## 2. 与总框架的分工

| 文件 | 职责 |
|:--|:--|
| `PLAN_重点股票产品化分析闭环总框架_v0.1.md` | 定义深度分析、日报、后评估、规则治理、产品使用层的全局闭环 |
| 本文件 v0.2 | 定义后评估/回测后端在 Phase 1/2 的技术落地 |
| `后评估流程定义_v1.0.md` | 定义 EvalHook、到期验证、偏差归因、RuleUpdateCandidate 的流程边界 |

本文件不再承载完整产品前端设计。前端只保留数据契约和状态输出，正式 UI 留到后续 Phase 3。

---

## 3. 地基能力对齐

后评估/回测后端必须服从地基四层架构：

```text
治理地基
  -> D01-D12 原子能力域
  -> 重点股票分析场景编排
  -> CanonicalReport / ReportSidecar / EvalHook / RuleUpdateCandidate
```

### 3.1 主要依赖能力

| 能力域 | 使用方式 | 第一阶段要求 |
|:--|:--|:--|
| D01 数据采集与快照输入 | 获取行情、资金、基础数据 | 只读复用，不新增采集源 |
| D03 数据治理与质量检查 | freshness、缺失、异常、降级 | 复用现有质量标识，新增后评估状态映射 |
| D04 数据中台与历史分析服务 | 历史 K 线、评分历史、回测样本 | 第一阶段特征服务必须挂靠 D04，不自建数据仓库 |
| D06 信号与特征计算 | MA/RSI/MACD、收益标签、风险特征 | 先机器化核心子集 |
| D08 风控/交易解释辅助 | 止损、仓位、交易成本、滑点边界 | 第一阶段只预留最小字段，不做完整交易回测 |
| D10 报告/产物输出 | JSON 状态、人读报告、后续驾驶舱数据 | 第一阶段输出 JSON，报告保留为展示层 |
| D11 后评估钩子 | EvalHook、到期验证、结果回填 | 建议后续注册为 `C-D11-0001` |
| D12 知识反馈/运行闭环 | RuleUpdateCandidate、知识入库 | 第一阶段只生成候选队列，不放行规则 |

### 3.2 明确不做

1. 不重建数据仓库。
2. 不绕过 D04 直接从零散文件拼回测数据。
3. 不让后评估重新解释股票。
4. 不让回测结果直接修改规则资产。
5. 不把驾驶舱 UI 纳入第一阶段实现。

---

## 4. 第一阶段目标

Phase 1 的目标不是“完整产品上线”，而是跑通一条可信的后端闭环：

```text
资产盘点
  -> PredictionLedger 最小账本
  -> FeatureSnapshot 核心特征
  -> MA20 破位止损单规则回测
  -> 前向后评估雏形
  -> dashboard_status / alert_center JSON
```

第一阶段必须证明：

1. 系统能知道现有资产在哪里。
2. 深度分析/日报里的可验证判断能结构化入账。
3. 后评估/回测能读取同一套特征和数据可见性口径。
4. 单规则回测能复现、能标样本不足、能防未来函数。
5. 输出结果能被未来前端直接消费。

---

## 5. 第一阶段范围

### 5.1 允许范围

第一阶段允许新增或修改的对象类型：

1. 结构化 schema。
2. 资产盘点脚本。
3. 预测账本最小写入/读取程序。
4. 核心特征服务入口。
5. 单规则回测引擎雏形。
6. 前向到期扫描和结果回填雏形。
7. 状态/告警 JSON 输出。
8. schema/golden/negative 测试。

### 5.2 禁止范围

第一阶段禁止：

1. 修改正式金融规则资产。
2. 修改日报或深度分析生产入口。
3. 修改 launchd 生产调度。
4. 直接接入新付费 API 或敏感 token。
5. 批量改历史报告。
6. 生成 G5/G6 放行结论。
7. 把回测结论写成投资建议。
8. 正式启用前端 UI。

---

## 6. 后端模块设计

### 6.1 AssetInventory

作用：盘点现有数据、报告、baseline、sidecar、后评估脚本、规则入口。

输出：

```text
keystock_system_inventory.json
```

最低字段：

```text
generated_at
scan_root
baseline_registry
baseline_files
daily_report_sidecars
deep_analysis_reports
eval_scripts
data_assets
rule_assets
runtime_entries
detected_gaps
candidate_pilot_rules
no_production_write_evidence
```

验收：

1. 能识别 `baseline_registry.json`。
2. 能识别重点股票日报 sidecar。
3. 能识别现有后评估脚本。
4. 能输出第一阶段候选规则。

### 6.2 PredictionLedger

作用：统一记录深度分析和日报中的可验证判断。

第一阶段不要求完美解析所有正文，优先读取：

1. baseline registry。
2. 日报 sidecar。
3. 已有 `eval_hooks` 或机器字段。
4. 可稳定抽取的支撑/压力/方向/止损字段。

主存储建议：

```text
JSONL first, SQLite later
```

最低字段：

```text
ledger_id
source_type
source_report_path
source_sidecar_path
stock_code
stock_name
trade_date
baseline_id
rule_version
data_snapshot_id
prediction_type
assertion
horizon
confidence
verification_windows
status
evidence_refs
created_at
updated_at
superseded_by
```

幂等键建议：

```text
stock_code + trade_date + source_type + baseline_id + prediction_type + horizon + assertion_hash
```

旧 `predictions.csv` 处理：

1. 保留为历史兼容。
2. 不作为未来主账本。
3. 第一阶段可做只读导入或对照，不做回写。

### 6.3 FeatureSnapshot

作用：给后评估和回测提供统一输入，避免各模块各自取数。

第一阶段核心特征：

| 类别 | 字段 |
|:--|:--|
| 技术 | close、volume、ma5、ma20、ma60、rsi14、macd、turnover_rate |
| baseline | baseline_id、support、pressure、stop_loss、valid_until |
| risk_flags | overall_risk_level、pledge、unlock、margin、northbound |
| labels | ret_t1、ret_t5、ret_t20、ret_t60、max_drawdown、relative_return |

入口建议：

```text
get_features(stock_code, trade_date, as_of_date, market_lag_days=0)
```

输出最低字段：

```text
snapshot_id
stock_code
trade_date
as_of_date
generated_at
feature_values
label_values
baseline_id
data_lineage_refs
quality_flags
freshness_status
reconstructed_snapshot
future_function_check
```

质量规则：

1. `as_of_date` 之后的数据不得进入特征。
2. 财务和事件数据必须按披露日可见性处理。
3. 历史快照缺失时可重建，但必须标记 `reconstructed_snapshot=true`。

### 6.4 BacktestEngine

作用：用统一特征服务验证规则历史有效性。

第一阶段只实现单规则模式：

```text
rule_id: TECH_MA20_BREAK_STOP_LOSS
```

规则定义草案：

```text
触发：收盘价跌破 MA20
验证：T+5/T+20 是否继续跑输基准、最大回撤是否扩大、是否存在假破位反向收益
输出：样本数、胜率、平均收益、超额收益、最大回撤、反向收益、弱规则原因
```

回测窗口：

1. 近 3 年。
2. 近 1 年。
3. 近 6 个月。

质量闸门：

| 检查 | 失败状态 |
|:--|:--|
| 数据可见性无法证明 | BLOCK |
| 样本数不足 | OBSERVE |
| 无规则版本 | BLOCK |
| 无对照组 | WARN，进入正式候选前补齐 |
| 无时间分层 | WARN |
| 未来函数风险 | BLOCK |
| 输出不可复现 | BLOCK |

### 6.5 ForwardEval

作用：自动发现到期判断并回填结果。

第一阶段只做雏形：

```text
scan_due_predictions(date)
  -> load_features()
  -> evaluate_outcome()
  -> update_ledger_status()
  -> emit_eval_result_json()
```

结果状态：

```text
HIT
MISS
PARTIAL
PENDING
INSUFFICIENT_DATA
OBSERVE
BLOCK
```

不得做：

1. 不用数据不足伪造 HIT/MISS。
2. 不因单次 MISS 直接生成规则修改。
3. 不删除历史账本，只能 supersede。

### 6.6 Attribution

作用：把偏差拆成可处理原因。

第一阶段只做字段预留和基础分类，不做复杂归因模型。

分类：

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

### 6.7 RuleCandidateQueue

作用：承接后评估/回测发现的问题。

第一阶段只输出队列，不进入正式规则治理。

最低字段：

```text
candidate_id
source_eval_ids
source_backtest_ids
affected_rule_ids
problem_statement
evidence_summary
proposed_change
required_backtest
shadow_plan
rollback_plan
status
created_at
```

状态：

```text
draft
backtest_required
observe_only
blocked_by_data
rejected
```

---

## 7. 第一阶段建议文件清单

> 具体路径可在 G3 执行包中再锁定。以下是建议，不代表已允许实施。

### 7.1 建议新增 schema

```text
00_项目地基/01_数据契约/prediction_ledger.schema.json
00_项目地基/01_数据契约/feature_snapshot.schema.json
00_项目地基/01_数据契约/backtest_result.schema.json
00_项目地基/01_数据契约/evaluation_result.schema.json
00_项目地基/01_数据契约/rule_update_candidate.schema.json
00_项目地基/01_数据契约/dashboard_status.schema.json
```

### 7.2 建议新增后端代码

```text
代码文件/重点股票/product_eval/inventory.py
代码文件/重点股票/product_eval/prediction_ledger.py
代码文件/重点股票/product_eval/feature_service.py
代码文件/重点股票/product_eval/backtest_engine.py
代码文件/重点股票/product_eval/forward_eval.py
代码文件/重点股票/product_eval/status_exporter.py
```

### 7.3 建议新增测试

```text
tests/keystock_product_eval/test_prediction_ledger_schema.py
tests/keystock_product_eval/test_feature_snapshot_golden.py
tests/keystock_product_eval/test_backtest_negative_future_function.py
tests/keystock_product_eval/test_forward_eval_due_scan.py
```

### 7.4 建议输出目录

第一阶段输出应先写入非生产产物目录：

```text
运行产物/重点股票产品化后评估/
  inventory/
  ledger/
  feature_snapshots/
  backtests/
  forward_eval/
  status/
```

若技术团队认为该目录不符合现有治理，可在 G3 前另行确认。

---

## 8. 状态机与告警

### 8.1 任务状态机

```text
PENDING
  -> RUNNING
  -> PASS | WARN | ALERT | BLOCK | OBSERVE
  -> RETRYING
  -> RESOLVED | SUPERSEDED
```

### 8.2 用户可见总状态

```text
COMPLETE
AUTO_REPAIRING
BLOCK
```

### 8.3 告警明细状态

```text
WARN
ALERT
BLOCK
```

第一阶段输出：

```text
dashboard_status.json
alert_center.json
```

最低字段：

```text
generated_at
overall_status
task_statuses
alerts
auto_repairing_items
blocked_items
evidence_refs
next_required_action
```

---

## 9. 第一阶段验收标准

Phase 1 完成时，必须满足：

1. 有机器可读资产盘点。
2. 有 PredictionLedger 最小 schema 和幂等写入。
3. 有 FeatureSnapshot 核心特征输出。
4. 有单规则 `MA20 破位止损` 回测结果。
5. 有未来函数 BLOCK 负向测试。
6. 有样本不足 `OBSERVE` 表达。
7. 有前向后评估到期扫描雏形。
8. 有 `dashboard_status.json` 和 `alert_center.json`。
9. 所有结果能追溯到 baseline、sidecar、数据快照、规则版本。
10. 不修改生产规则、不切换生产调度、不生成 G6 放行。

---

## 10. 建议验收命令

> 以下为 G3 执行包候选命令，当前 G2 不执行实现。

JSON/schema 检查：

```bash
python3 -m json.tool 00_项目地基/01_数据契约/prediction_ledger.schema.json
python3 -m json.tool 00_项目地基/01_数据契约/feature_snapshot.schema.json
python3 -m json.tool 00_项目地基/01_数据契约/backtest_result.schema.json
python3 -m json.tool 00_项目地基/01_数据契约/evaluation_result.schema.json
python3 -m json.tool 00_项目地基/01_数据契约/rule_update_candidate.schema.json
python3 -m json.tool 00_项目地基/01_数据契约/dashboard_status.schema.json
```

Python 编译：

```bash
python3 -m py_compile 代码文件/重点股票/product_eval/inventory.py
python3 -m py_compile 代码文件/重点股票/product_eval/prediction_ledger.py
python3 -m py_compile 代码文件/重点股票/product_eval/feature_service.py
python3 -m py_compile 代码文件/重点股票/product_eval/backtest_engine.py
python3 -m py_compile 代码文件/重点股票/product_eval/forward_eval.py
python3 -m py_compile 代码文件/重点股票/product_eval/status_exporter.py
```

最小功能验证：

```bash
python3 -m pytest tests/keystock_product_eval
```

生产不触碰证明：

```bash
git diff -- 重点股票/股票报告 重点股票/深度分析 00_项目地基/02_权威注册表/baseline_registry.json
```

---

## 11. 回滚与不切生产证明

第一阶段必须满足：

1. 所有新输出写入新增产物目录或临时目录。
2. 不修改 `baseline_registry.json`。
3. 不修改日报正式报告目录。
4. 不修改深度分析正式报告目录。
5. 不修改 `runtime_entry_registry.json`。
6. 不注册 launchd 新任务。
7. 不修改规则资产注册表。
8. 所有新增结果可删除后不影响生产链路。

若 G3 实施中需要触碰上述禁止范围，必须停止并回到 G2 重新确认。

---

## 12. 后续阶段

### Phase 2：后端产品化

在 Phase 1 跑通后，再做：

1. 统一状态机持久化。
2. DAG 调度。
3. 自动修复和重试。
4. 专项回测队列。
5. RuleUpdateCandidate 流转。
6. evidence_trace 索引。
7. 运行健康指标。

### Phase 3：前端产品化

后端契约稳定后，再做：

1. 今日驾驶舱。
2. 股票详情页。
3. 规则健康页。
4. 后评估/回测证据页。
5. 规则候选页。

### Phase 4：扩展能力

后续再纳入：

1. 财务特征按披露日回测。
2. 事件研究半定量体系。
3. 拥挤度指标。
4. 极端行情切片。
5. shadow/gray/active/rollback 规则生命周期。

---

## 13. 技术团队确认点

进入 G3 前，需要确认：

1. 第一阶段主试点规则是否确定为 `MA20 破位止损`。
2. FeatureSnapshot 是否挂靠 D04 `UnifiedDataSource`。
3. 第一阶段主账本采用 JSONL 还是 SQLite。
4. 产物目录是否使用 `运行产物/重点股票产品化后评估/`。
5. 是否新增 D11 schema 但暂不注册 `C-D11-0001`。
6. 是否把 `predictions.csv` 仅作为历史兼容输入。
7. 是否允许第一阶段只输出 JSON，不做人读报告。
8. 测试目录和 pytest 是否符合当前项目习惯。
9. 是否需要接入现有 `canonical_report` 影子对象，或 Phase 2 再接。
10. 是否保留现有后评估报告生成逻辑作为展示层兼容。

---

## 14. 用户可见结论

v0.2 将原 v0.1 的完整大架构收窄为后端子方案：

```text
先证明账本、特征、单规则回测、前向后评估、状态 JSON 能跑通；
再做调度、自修复、规则候选和前端。
```

当前状态：

```text
G2 子方案候选完成
未进入 G3 实施
未修改生产规则
未切换生产入口
未放行回测结论
```
