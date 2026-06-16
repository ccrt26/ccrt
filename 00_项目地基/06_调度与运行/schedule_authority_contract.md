# 调度权威契约

> 版本: 2.0 | 生效日期: 2026-06-11 | 维护人: 红枫+阿黑+情墨
>
> 更新说明: v2.0 — 统一收口至 launchd，禁止 crontab/GitHub Actions schedule/PS1 注册

---

## 一、调度权威入口定义

当前项目运行在 macOS 环境下，唯一调度权威入口体系为：

| 组件 | 角色 | 说明 |
|:-----|:-----|:------|
| **generate_launchd.py** | 调度注册器（唯一） | macOS 当前唯一调度注册器，将所有定时任务注册为 launchd plist |
| **launchd** | 调度执行器（唯一） | macOS 原生调度器，按 plist 规则定时触发 |
| **daily_workflow.py** | 被调度的执行体 | 由 launchd 或手动触发，负责每日工作流编排 |
| **batch_data_collector.py** | 被调度的执行体 | 由 launchd 或 workflow 触发，负责数据采集 |
| **run_daily_data_pipeline_today.py** | 被调度的日报数据链入口 | 由 launchd 触发，串联 tushare_history_sync → batch_data_collector → materialize → daily_orchestrator |
| **daily_orchestrator.py** | 被调度的执行体 | 由 workflow 触发，负责日报生成 |
| **feishu_bridge.py** | 被调度的执行体 | 飞书消息桥接，由 launchd 每 30s 轮询 |
| **im_consumer.py** | 被调度的执行体 | IM 消息消费，由 launchd 每 30s 轮询 |
| **sim_orchestrator.py** | 被调度的执行体 | 模拟交易引擎，由 launchd 交易日 09:45 触发 |
| **scheduler_health_check.py** | 被调度的执行体 | 调度心跳监控，由 launchd 每小时触发 |

## 二、禁止的调度入口

| 禁止 | 原因 | 替代 |
|:-----|:------|:------|
| ⛔ crontab | 铁律量化不再使用 crontab 管理定时任务 | `generate_launchd.py --install all` |
| ⛔ install_crontab.sh | 已废弃，改为仅输出提示的保护脚本 | 使用 generate_launchd.py |
| ⛔ cron_runner.sh | 模拟交易不再通过 cron 触发 | `generate_launchd.py --install sim_trading` |
| ⛔ GitHub Actions schedule: sim_trading.yml | 禁止 GitHub 定时自动模拟交易 | 仅保留 workflow_dispatch，且只运行 dry-run |
| ⛔ Windows Task Scheduler 及关联 PS1 | Windows legacy，macOS 当前环境不得使用 | 仅保留 `_win32_legacy/` 用于回滚 |
| ⛔ 通过 PS1 注册新定时任务 | PS1 注册脚本均标记为 forbidden | 仅允许 generate_launchd.py |
| ⛔ --mode data_only 作为定时任务 | data_only 模式不得注册为 launchd 任务 | 仅使用标准模式 |

## 三、注册规则

| 规则 | 内容 |
|:-----|:------|
| 唯一注册器 | `generate_launchd.py`（`--install`/`--uninstall`/`--list`/`--status`） |
| 项目根目录 | `/Users/ccrt/ccrt`（硬编码，禁止相对路径依赖） |
| 飞书桥接 | 如保留，必须登记到 runtime_entry_registry.json，并由 generate_launchd.py 统一管理 |
| check_runtime_entry_authority.py | 必须能查出 crontab、GitHub schedule、LaunchAgents、占位任务、unsupported mode |

## 四、运行时密钥规则

| 规则 | 内容 |
|:-----|:------|
| 生产密钥来源 | launchd 生产任务必须能从 `/Users/ccrt/.ccrt/tielv.env` 读取所需密钥 |
| shell 配置限制 | `.zshrc` / `.zprofile` 只属于交互 shell，不得视为 launchd 生产运行时凭证来源 |
| 日报数据链密钥 | `daily_signal` → `run_daily_data_pipeline_today.py` → `run_daily_production_pipeline.py` 必须具备 launchd 可见 `TUSHARE_TOKEN` |
| 验收闸门 | `check_runtime_secret_readiness.py --runtime daily_production` 与 `check_runtime_entry_authority.py --all` 必须 PASS |
| 日志约束 | 闸门和健康检查只允许输出密钥是否存在及来源，不得输出密钥值 |

## 五、generate_launchd.py 调度任务清单

| 任务名 | 调度 | 命令 |
|:-------|:-----|:------|
| `git_autosweep` | 每小时 :07 | `代码文件/tools/git_autosweep.py` |
| `pigeon` | 交易日 19:07 | `daily_orchestrator.py --mode pigeon` |
| `daily_signal` | 交易日 16:30 | `scripts/run_daily_data_pipeline_today.py` |
| `deep_signal` | 周五 20:30 | `daily_orchestrator.py --mode deep` |
| `post_eval` | 交易日 17:20 | `daily_workflow.py --mode eval` |
| `scheduler_health` | 每小时 :03、:33 | `scheduler_health_check.py` |
| `sim_trading` | 交易日 09:45 | `sim_orchestrator.py` |
| `feishu_bridge` | 每 30 秒 | `feishu_bridge.py --once` |
| `im_consumer` | 每 30 秒 | `im_consumer.py --once` |

## 六、数据采集顺序

| 顺序 | 步骤 | 约束 |
|:----:|:-----|:------|
| 1 | 数据采集（batch_data_collector.py / stock_data_fetcher_tushare.py） | 须在日报生成前完成 |
| 2 | manifest 更新 | 数据采集完成后写入完成时间戳 |
| 3 | 日报生成（daily_orchestrator.py） | 读取 manifest + source_snapshot 判断数据新鲜度 |
| 4 | 闸门回归 | P0-A/B/C/D/P5 + runtime gate |

禁止绕过数据采集顺序直接生成日报。

## 七、source_snapshot 要求

日报生成时必须记录：
- `report_generated_at`：报告生成时间（ISO 8601, Asia/Shanghai）
- `source_snapshot.margin`：融资数据快照（latest_trade_date, report_trade_date, lag_days, degraded, declared_in, source_path）

## 八、运行时入口注册表

`runtime_entry_registry.json` 为运行时入口的权威注册表。所有新增运行时入口必须注册后方可运行。
crontab、install_crontab.sh、cron_runner.sh、GitHub Actions schedule 均标记为 forbidden_current_runtime。

## 九、Win Legacy 迁移注册

`win_legacy_migration_register.json` 登记已有 Python 替代的 PS1 脚本的迁移状态。已登记的 E 级脚本禁止在当前运行时调用。

## 十、禁止事项（完整版）

| 禁止 | 说明 |
|:-----|:------|
| ⛔ 禁止 crontab 继续运行铁律量化任务 | crontab -l 不得包含 /Users/ccrt/ccrt |
| ⛔ 禁止 GitHub Actions 定时自动模拟交易 | sim_trading.yml 不得包含 schedule: |
| ⛔ 禁止通过 PS1 注册新定时任务 | 仅允许 generate_launchd.py |
| ⛔ 禁止绕过数据采集顺序直接生成日报 | 数据采集未完成则日报不得生成 |
| ⛔ 禁止使用 daily_workflow.ps1 或 batch_data_collector.ps1 | 已有 Python 替代 |
| ⛔ 禁止在 _win32_legacy/ 外执行已被替代的 PS1 | 需改用 Python 版 |
| ⛔ 禁止 PS1 注册脚本作为当前运行入口 | register_tasks.ps1 / setup_scheduler.ps1 / register_pigeon_scheduler.ps1 |
| ⛔ 禁止 data_only 作为定时任务模式 | 不得注册为 launchd 任务 |
| ⛔ 禁止 print('... trigger') 占位任务 | generate_launchd.py 中不得包含占位任务 |
