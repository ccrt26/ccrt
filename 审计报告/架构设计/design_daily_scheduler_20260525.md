# 每日数据管线自动化调度 — 架构设计

> 情墨 | 2026-05-25 | L1级
> pipeline_stage: complete
> finance_confirmed: true (腰子确认：本变更为纯工程基础设施，不涉及金融分析/策略/交易逻辑变更)
> ⚠️ **平台标注 (2026-05-29)**：本文档描述 Windows Task Scheduler 架构。macOS 实际采用 `daily_orchestrator.py` + crontab 方案（支持 daily/deep/pigeon/health 四种模式，文件锁幂等，数据就绪检查+故障分级告警）。详见代码注释。

---

## 一、问题诊断

5月25日（周一）每日数据管线未执行。根因：**Windows Task Scheduler 中零个定时任务被注册**，管线自项目启动以来一直依赖人工在 Claude Code 中手动触发。

需修复的缺陷：
- B1(P0): `setup_scheduler.ps1` 设计完整(含StartWhenAvailable)但从未被执行
- B2(P1): `register_tasks.ps1:14` 路径求值bug
- B3(P1): `daily_workflow.ps1` 缺少幂等守卫

## 二、设计方案

### 三层调度架构

```
Layer 1: Windows Task Scheduler (OS级触发)
  Trigger A: Daily 19:00  |  Trigger B: AtLogon +120s

Layer 2: invoke_daily.ps1 (幂等守卫，~25行)
  检查 workflow_records.csv → 今日已跑? 跳过 : 启动管线

Layer 3: daily_workflow.ps1 (现有管线，不改动)
  7阶段：选股池→数据采集→QC→评分→报告→重点股票→归档→模拟交易
```

### 四种场景覆盖

| 场景 | 行为 |
|:-----|:-----|
| 19:00开机 | 准时触发 |
| 19:00未开机，晚上开机 | 开机120s触发，检测未跑→补跑 |
| 跑完重启 | 开机触发，检测已跑→跳过 |
| 周末/节假日 | is_market_open返回false→写SKIP退出 |

### 新增文件（2个）

| 文件 | 行数 | 等级 | 用途 |
|:-----|:---:|:---:|:-----|
| `代码文件/每日荐股/scripts/invoke_daily.ps1` | ~25 | L1 | 幂等守卫 |
| `代码文件/每日荐股/scripts/install_scheduler.ps1` | ~100 | L0 | 一键安装定时任务 |

### 修改文件

**无。** `daily_workflow.ps1` 不修改，现有管线代码质量合格。

### Task Scheduler 设置

- 两个任务: TieLv-DailyPipeline(19:00) + TieLv-Evaluation(19:30)
- 每个双触发器: Daily定时 + AtLogon延迟120s
- StartWhenAvailable + ExecutionTimeLimit 2h
- LogonType S4U (无需密码)

## 三、接口契约

### invoke_daily.ps1 输入/输出

```
输入: 无参数 (自动取当天日期)
输出: exit 0 (成功/跳过) | exit 1 (失败)
依赖: workflow_records.csv (只读) + daily_workflow.ps1 (调用)
```

### install_scheduler.ps1 输入/输出

```
输入: 无参数（可选 -Uninstall）
输出: 控制台状态报告
副作用: 修改 Windows Task Scheduler (Register-ScheduledTask)
```

## 四、风险与缓解

| 风险 | 缓解 |
|:-----|:-----|
| 管线>2h被终止 | 实测~30min，2h足够 |
| 开机重跑冲突 | 幂等守卫 |
| S4U不兼容 | 自动降级Password模式提示 |
| 2027节假日过期 | 安装脚本输出提醒 |

## 五、需求→代码核对

- [ ] invoke_daily.ps1: 幂等检查 + 调用 daily_workflow.ps1
- [ ] install_scheduler.ps1: 双任务注册 + 双触发器 + S4U
- [ ] schtasks /query 确认任务存在
- [ ] 重复触发不重复执行
- [ ] 非交易日自动跳过

---

## macOS 实际架构（2026-05-29 补充，代码已实现但原设计未记录）

### daily_orchestrator.py 四模式调度

`daily_orchestrator.py:L473` 支持四种运行模式，通过 crontab 触发：
- `daily` — 每日荐股全流程（采集→评分→报告→PDF）
- `deep` — 深度分析触发
- `pigeon` — 信鸽信息采集
- `health` — 健康巡检

### 数据就绪检查 (`daily_orchestrator.py:L47-48,216-241`)

- 检查数据缓存目录中 ≥3 个文件在当日15:00后更新
- 未就绪时最多重试4次，每次间隔15分钟(MAX_RETRIES=4, RETRY_DELAY=900)
- 超时仍未就绪→WARN退出

### 故障分级告警 (`daily_orchestrator.py:L410-459`)

三级故障分类，自动通知对应角色：
- P0: 核心数据源全故障 → 通知玉夜+腰子
- P1: 单数据源降级 → 通知玉夜
- P2: 缓存过期/配置异常 → 通知玉夜+红枫
- P3: 仅记录，连续3次升级为P2

### 幂等锁机制 (`daily_orchestrator.py:L71-97`)

使用文件锁(`.locks/`目录)替代设计中的workflow_records.csv，1小时自动过期。
