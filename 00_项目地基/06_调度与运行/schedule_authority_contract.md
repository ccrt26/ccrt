# 调度权威契约

> 版本: 1.0 | 生效日期: 2026-06-04 | 维护人: 红枫+阿黑+情墨

---

## 一、调度权威入口定义

当前项目运行在 macOS 环境下，唯一调度权威入口体系为：

| 组件 | 角色 | 说明 |
|:-----|:-----|:------|
| **generate_launchd.py** | 调度注册器 | 将定时任务注册为 macOS launchd plist |
| **launchd** | 调度执行器 | macOS 原生调度器，按 plist 规则定时触发 |
| **daily_workflow.py** | 被调度的执行体 | 由 launchd 或手动触发，负责每日工作流编排 |
| **batch_data_collector.py** | 被调度的执行体 | 由 launchd 或 workflow 触发，负责数据采集 |
| **daily_orchestrator.py** | 被调度的执行体 | 由 workflow 触发，负责日报生成 |

**Windows Task Scheduler 及关联脚本为 legacy，不得作为当前环境权威调度。**

---

## 二、调度注册规则

| 规则 | 内容 |
|:-----|:------|
| 唯一注册器 | `generate_launchd.py`（`--install`/`--uninstall`/`--list`/`--status`） |
| 禁止注册方式 | schtasks、`setup_scheduler.ps1`、`register_tasks.ps1`、`register_pigeon_scheduler.ps1` |
| 手动执行 | 允许，但执行者必须承担数据新鲜度责任。launchd 触发前手动执行可能导致重复或状态冲突 |

---

## 三、数据采集顺序

| 顺序 | 步骤 | 约束 |
|:----:|:-----|:------|
| 1 | 数据采集（batch_data_collector.py / stock_data_fetcher_tushare.py） | 须在日报生成前完成 |
| 2 | manifest 更新 | 数据采集完成后写入完成时间戳 |
| 3 | 日报生成（daily_orchestrator.py） | 读取 manifest + source_snapshot 判断数据新鲜度 |
| 4 | 闸门回归 | P0-A/B/C/D/P5 + runtime gate |

禁止绕过数据采集顺序直接生成日报。

---

## 四、source_snapshot 要求

日报生成时必须记录：
- `report_generated_at`：报告生成时间（ISO 8601, Asia/Shanghai）
- `source_snapshot.margin`：融资数据快照（latest_trade_date, report_trade_date, lag_days, degraded, declared_in, source_path）

---

## 五、运行时入口注册表

`runtime_entry_registry.json` 为运行时入口的权威注册表。所有新增运行时入口必须注册后方可运行。

---

## 六、Win Legacy 迁移注册

`win_legacy_migration_register.json` 登记已有 Python 替代的 PS1 脚本的迁移状态。已登记的 E 级脚本禁止在当前运行时调用。

---

## 七、禁止事项

| 禁止 | 说明 |
|:-----|:------|
| ⛔ 禁止通过 PS1 注册新定时任务 | 仅允许 generate_launchd.py |
| ⛔ 禁止绕过数据采集顺序直接生成日报 | 数据采集未完成则日报不得生成 |
| ⛔ 禁止使用 `daily_workflow.ps1` 或 `batch_data_collector.ps1` | 已有 Python 替代 |
| ⛔ 禁止在 `_win32_legacy/` 外执行已被替代的 PS1 | 需改用 Python 版 |
