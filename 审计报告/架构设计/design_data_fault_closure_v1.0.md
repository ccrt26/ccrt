# 设计文档: 数据调用故障闭环方案

> **pipeline_stage: complete**
> **阶段**: ①架构设计 | **设计者**: 情墨 | **日期**: 2026-05-29
> **任务**: 数据调用故障"设计预防→运行检测→通知响应→审计闭环"四环方案
> **代码分级**: L0/L1混合（health_check/打点为L0工具类，告警信号为L0调度类，fault_coverage为L0审计类）
> **影响范围**: `health_check.py` (1文件), `batch_data_collector.ps1` (1文件), 数据获取函数(3-5文件), orchestrator(1文件), 新增`check_fault_coverage.py`, 玉夜/情墨知识库(5文件)
> **Token影响**: 新增文件~200行Python, 修改~120行(分散6文件), 知识库~150行markdown。不增加Agent spawn, 不增加报告生成, API调用量不变。总Token增量<5%。

---

## 一、问题诊断（3项根因）

### 1.1 文件没有契约

现有 `arch-interface-contracts` 定义了 I1-I8 共8个模块间函数调用接口契约，但未覆盖**数据文件**。项目架构是文件松耦合——模块A写文件→模块B隔天来读，比函数调用更容易出错，却没有 schema 约束。

**实际案例**：
- `manual_extraction` 直接写入评估数据文件，sim_trading 读取时格式不兼容→返回空
- 无人声明文件所有者 → 竞写无人察觉

### 1.2 静默降级隐蔽了故障

1+2主备架构的降级设计过于优雅：
- 新浪[2]状态为 `down`，`LastSuccess: null`，从未成功连接
- 降级到缓存后，报告正常生成，一切看起来没问题
- 健康检查只查4项（disk/cache/events/signal），**不查API连通性**
- `.sina_health.json` 明确记录 `"Status":"down"`，但无人读取

### 1.3 故障记录脱离执行

玉夜知识库05设计了完善的 P0-P5 异常分类体系和故障记录模板，但：
- `08-数据源故障历史.md` 故障记录表完全空白（0条记录）
- 故障记录是"期望玉夜手动填写"的模式，但发现→记录环节断链
- 数据调用失败后→红结修代码→提交→结束，没有环节强制补记录

---

## 二、方案设计：四环闭环

```
设计时预防（三道防线）
    ↓
运行时检测（API连通性+降级打点）
    ↓
通知响应（degradation_events → 责任人）
    ↓
审计闭环（旧影交叉比对 → 趋势分析 → 预防规则更新）
```

---

## 三、第一环：设计时预防 — 三道防线

### 防线一：数据文件契约

**变更文件**: `.claude/agents/情墨-知识库/02-接口契约设计.md`

在现有 I1-I8 契约体系上新增 **§九「数据文件契约」**，将文件视为一等接口。

**契约模板**：

```
## 数据文件契约：{文件路径}
- 文件路径：...
- 所有者：  {唯一写入者，模块+角色}
- 消费者：  {读取者列表}
- 格式版本：v{N}
- 字段Schema：
  | 字段路径 | 类型 | 必填 | 约束 |
- 变更历史：
- 禁止写入者：{明确排除的模块}
```

**设计审查规则**：
- 任何模块写入数据文件前，必须在设计文档中声明契约
- 写入者不在"所有者"或授权名单中 → 设计打回
- 格式变更 → 必须更新版本号 + 通知所有消费者

### 防线二：静默失败升级为阻塞失败

**变更文件**: `.claude/agents/情墨-知识库/04-反模式库.md`

新增 **AP-08「校验降级」（Verification Downgrading）**：

| 属性 | 内容 |
|:-----|:-----|
| 定义 | 数据完整性校验结果只写WARN日志，不阻止引擎继续运行 |
| 识别方法 | 数据加载返回空→仅WARN；格式不兼容导致0条匹配→继续运行；必需字段缺失→使用默认值 |
| 危害等级 | 🔴 致命 |
| 修复方案 | 数据加载层增加硬闸门：matched==0→FATAL+exit(1)；matched<预期50%→FATAL+exit(1) |

同时在 CH12 审查清单后增加 **CH13: 数据加载失败是否阻塞？（对照AP-08）**

### 防线三：数据格式变更纳入架构审查清单

**变更文件**: `.claude/agents/情墨-知识库/05-设计检查清单.md`

在 §三「新增功能架构评估清单」A10 后增加3条：

| 编号 | 评估项 | 检查内容 |
|:----:|:-------|:---------|
| D1 | 数据文件契约 | 新增/修改的数据文件是否声明了格式契约？（对照02-接口契约设计§九） |
| D2 | 下游兼容性 | 格式变更是否兼容所有消费者？（扫描所有读取该文件的模块） |
| D3 | 竞写风险 | 是否有多个进程写入同一文件？（检查文件所有者声明） |

---

## 四、第二环：运行时检测

### 改造A：health_check.py 增加 API 连通性探测

**变更文件**: `代码文件/tools/health_check.py`
**代码分级**: L0
**改动量**: 约30行

现有检查项（disk_space / data_cache_freshness / events_db_freshness / signal_stale）之外新增：

```
api_connectivity:
  读取 .tencent_health.json / .sina_health.json / .eastmoney_health.json
  任一 Status=="down" → 返回 WARN
  全部 Status=="down" → 返回 FAIL
```

探测逻辑复用现有的 health.json 写入机制（数据采集时已写入），health_check 只读不写，不额外产生API调用。

### 改造B：1+2降级路径嵌入故障打点

**变更文件**: `代码文件/每日荐股/scripts/batch_data_collector.ps1` + 其他数据获取函数(3-5文件)
**代码分级**: L0
**改动量**: 约40行（分散）

在1+2降级分叉点增加副作用——写入结构化故障事件：

```python
# 降级发生时（在现有降级逻辑之后，主流程不受影响）
def _write_fault_event(event_id, source, description):
    try:
        event = {
            "EventID": event_id,
            "Timestamp": datetime.now().isoformat(),
            "Level": event_id.split("-")[0],  # P3-01 → P3
            "Source": source,
            "Description": description,
            "ConsecutiveCount": _get_consecutive_count(event_id, source) + 1,
            "Resolved": False
        }
        # 去重：同一EventID+同一Source+同一小时内 → 更新ConsecutiveCount
        _upsert_fault_event(event)
    except Exception:
        print(f"[FAULT_RECORD_FAIL] {event_id} {source}", file=sys.stderr)
        # 打点失败不影响数据获取主流程
```

**fault_events.json schema**（复用玉夜知识库05 §11.1）：

```json
{
  "events": [
    {
      "EventID": "P3-01",
      "Timestamp": "2026-05-29T09:35:12+08:00",
      "Level": "P3",
      "Source": "新浪",
      "Description": "新浪行情API连接失败，降级到缓存",
      "ConsecutiveCount": 1,
      "Resolved": false
    }
  ]
}
```

**数据文件契约声明**：
- 文件路径: `代码文件/数据/fault_events.json`
- 所有者: 数据获取函数（红结维护）
- 消费者: 玉夜巡检、旧影审计、orchestrator告警检查
- 禁止写入者: 报告生成流程、手动脚本

---

## 五、第三环：通知响应

### 改造C：降级事件 → 责任人通知

**变更文件**: orchestrator / cron_runner 相关
**代码分级**: L0
**改动量**: 约30行

引擎结束后检查 `fault_events.json`，按等级分发：

| 等级 | 触发条件 | 通知对象 | 通知方式 |
|:----:|:-----|:-----|:-----|
| P0 | 评估数据缺失/格式不兼容 | 玉夜 + 腰子 | signal_alert.json + 下次日报强制展示 |
| P1 | 双源全down，仅缓存可用 | 玉夜 | signal_alert.json |
| P2 | 主源down，切备源 | 玉夜 + 红枫 | signal_alert.json |
| P3 | 单次超时/单字段异常 | 仅记录 | 连续3次升级为P2后通知 |

**责任矩阵**：

| 降级场景 | 责任人 | 响应动作 |
|:-----|:-----|:-----|
| 评估数据缺失/格式不兼容 | 玉夜 + 腰子 | 暂停相关分析，排查数据源 |
| 行情API主源失败 | 玉夜 | 确认备源可用，记录故障 |
| 行情API主+备全失败 | 玉夜 + 红枫 | 立即排查API状态，评估缓存时效 |
| 引擎09:45后超时跳过 | 红枫 | 检查调度配置 |
| 连续3次同源同类型P3 | 玉夜 | 升级为P2，主动告警 |

---

## 六、第四环：审计闭环

### 改造D：故障覆盖交叉比对

**新增文件**: `代码文件/监督机制/check_fault_coverage.py`
**代码分级**: L0
**改动量**: 约50行

功能：
1. 扫描 git log 中的 fix commit（匹配关键词：fix/数据/API/字段/降级）
2. 提取涉及的数据源/数据类型
3. 在 fault_events.json 中查找对应事件记录
4. 有 fix commit 但无 fault event → FAIL（"未记录的故障修复"）
5. 输出交叉比对报告

### 旧影审计补充

**变更文件**: 旧影审计脚本 / 二级审计 Section D

新增三项检查：
1. 故障历史表填充率检查（fault_events.json 有记录但 08-数据源故障历史.md 未更新 → FAIL）
2. fix commit ↔ fault event 交叉比对（调用 check_fault_coverage.py）
3. 连续3次同源同EventID → WARN升级为FAIL

---

## 七、实施计划

| 序号 | 改造内容 | 执行者 | 阶段 | 文件 | 估算 |
|:----:|:-----|:----:|:----:|:-----|:----:|
| 1 | 接口契约 §九：数据文件契约 | 情墨 | ① | 02-接口契约设计.md | +40行 |
| 2 | 反模式 AP-08「校验降级」+ CH13 | 情墨 | ① | 04-反模式库.md | +30行 |
| 3 | 审查清单 +D1/D2/D3 | 情墨 | ① | 05-设计检查清单.md | +20行 |
| 4 | health_check +API连通性 | 红结 | ④ | health_check.py | +30行 |
| 5 | 降级路径 +fault_events写入 | 红结 | ④ | batch_data_collector.ps1 等 | +40行 |
| 6 | orchestrator +告警信号 | 红结 | ④ | orchestrator相关 | +30行 |
| 7 | fault_coverage交叉比对 | 红结 | ④ | check_fault_coverage.py(新增) | +50行 |
| 8 | 玉夜知识库故障记录机制激活 | 玉夜 | ②确认 | 05-异常检测与告警.md, 08-数据源故障历史.md | 确认即生效 |

---

## 八、Token影响评估

| 维度 | 评估 | 说明 |
|:-----|:----:|:-----|
| 新增代码行数 | ~200行 | 1个新文件 + 6个文件修改 |
| 新增Agent spawn | 0 | 不增加Agent调用 |
| 新增API调用 | 0 | health_check只读health.json不调API；打点在现有API调用路径中 |
| 新增报告输出 | 0 | fault_events.json为结构化JSON，不生成报告 |
| 知识库增量 | ~150行 | 分散在5个文件 |
| 运行时开销 | <50ms/次 | fault_events读写为本地JSON操作 |
| 日常Token影响 | <5% | 仅旧影周度审计增加一次fault_coverage扫描 |

**Token预算结论**：通过。不增加Agent spawn、不增加API调用、不增加报告生成。唯一新增运行时开销为本地JSON读写。

---

## 九、需求→代码核对清单

| 编号 | 需求 | 对应改造 | 验证方式 |
|:----:|:-----|:----:|:-----|
| R1 | 数据文件在设计阶段必须有契约声明 | 改造1: 接口契约§九 | 新设计文档含数据文件契约段 |
| R2 | 数据加载失败必须阻塞，不能静默 | 改造2: AP-08 + CH13 | 引擎空数据→FATAL exit |
| R3 | 数据格式变更必须评估下游兼容性 | 改造3: D1/D2/D3 | 设计审查清单含D1-D3 |
| R4 | 健康检查覆盖API连通性 | 改造4: health_check +api_connectivity | health_check WARN on 新浪down |
| R5 | 降级发生时自动记录故障事件 | 改造5: fault_events写入 | 模拟主API超时→fault_events.json有新条目 |
| R6 | 降级事件通知到责任人 | 改造6: signal_alert | P2事件→signal_alert.json |
| R7 | 修复commit与故障记录交叉比对 | 改造7: fault_coverage | fix commit无对应event→FAIL |
| R8 | 打点失败不阻塞数据主流程 | 改造5设计约束 | 磁盘满时数据获取仍正常完成 |

---

## 十、审批

| 角色 | 意见 | 日期 |
|:-----|:-----|:----|
| 情墨（设计） | 批准 | 2026-05-29 |
| 腰子（金融确认） | 待确认 | — |
| 新安（技术审查） | 待审查 | — |
| 旧影（Token+审计审查） | 待审查 | — |
| 用户（最终审批） | 待审批 | — |
