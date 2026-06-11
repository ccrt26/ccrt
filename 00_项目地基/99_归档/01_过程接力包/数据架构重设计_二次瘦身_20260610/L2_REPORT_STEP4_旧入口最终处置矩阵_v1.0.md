# STEP4 旧入口最终处置矩阵

> **流程编号**：F-ARCH + F-DATA + F-GATE + F-MIGRATE + F-SCHEDULE
> **阶段门**：G3（实施阶段）
> **日期**：2026-06-09
> **目的**：固化所有旧入口/旧脚本的最终状态，状态更新仅限注册表，不删除/不移动任何物理文件
> **formal pipeline**：继续明示例外

---

## 一、处置状态语义

| 状态 | 含义 | 可操作 |
|:-----|:------|:-------|
| **保留** | 继续作为生产入口，保持现状 | ❌ 不修改（除重大 bug 修复） |
| **废弃（已冻结）** | 不再使用，保留物理文件作为回滚证据 | ❌ 不删除，仅更新注册表状态 |
| **待确认（under_review）** | 需进一步核查 Python 替代覆盖 | ⬜ 核查后更新状态 |
| **遗留隔离** | `_win32_legacy/` 已物理隔离，不纳入调度 | ❌ 不删除 |

---

## 二、旧入口最终处置矩阵

### 2.1 保留（BAU 生产入口）

| # | 入口 | 文件路径 | 权威层级 | 说明 |
|:-:|:-----|:---------|:---------|:------|
| R1 | CachedDataSource | `代码文件/lib/cached_data_source.py` | L1 日报读取入口 | 不删除，不改返回值格式。Phase 3 评估是否 shadow 接入 |
| R2 | daily_workflow.py | `代码文件/每日荐股/scripts/daily_workflow.py` | 日报编排入口 | 不修改 |
| R3 | batch_data_collector.py | `代码文件/每日荐股/scripts/batch_data_collector.py` | 数据采集核心 | 不修改 |
| R4 | daily_orchestrator.py | `代码文件/tools/daily_orchestrator.py` | 统一调度入口 | 保持 L1 链路 |
| R5 | archive_data.py | `代码文件/每日荐股/scripts/archive_data.py` | L3 归档入口 | 保持 L3 链路 |
| R6 | stock_data_fetcher_*.py | `代码文件/每日荐股/scripts/stock_data_fetcher_*.py` | 数据采集实现 | 不修改 |
| R7 | UnifiedDataSource | `代码文件/数据/unified_data_source.py` | D04 shadow 模式 | 保持 shadow。Phase 3 前不切生产 |

### 2.2 废弃（已冻结）

| # | 原入口 | 文件路径 | Python 替代 | 注册表状态 |
|:-:|:-------|:---------|:------------|:-----------|
| D1 | archive_data.ps1 | `代码文件/每日荐股/scripts/archive_data.ps1` | archive_data.py | `forbidden` |
| D2 | stock_data_fetcher_*.ps1 | `代码文件/每日荐股/scripts/stock_data_fetcher_*.ps1` | stock_data_fetcher_*.py | `forbidden` |
| D3 | daily_workflow.ps1 | `代码文件/每日荐股/scripts/daily_workflow.ps1` | daily_workflow.py | `forbidden`（从 forbidden_when_python_available 升级） |
| D4 | batch_data_collector.ps1 | `代码文件/每日荐股/scripts/batch_data_collector.ps1` | batch_data_collector.py | `forbidden`（从 forbidden_when_python_available 升级） |
| D5 | build_docx.ps1 | `代码文件/tools/build_docx.ps1` | build_tools.py | `forbidden` |
| D6 | git_autocommit.ps1 | `代码文件/tools/git_autocommit.ps1` | git_autocommit.py | `forbidden_when_python_available`（从 under_review 更新） |
| D7 | gen_pdf.ps1 | `代码文件/tools/gen_pdf.ps1` | build_tools.py + convert_md_to_pdf.py | `forbidden_when_python_available`（从 under_review 更新） |
| D8 | gen_eval_pdf.ps1 | `代码文件/tools/gen_eval_pdf.ps1` | build_tools.py + convert_md_to_pdf.py | `forbidden_when_python_available`（从 under_review 更新） |
| D9 | gen_keystock_pdf.ps1 | `代码文件/tools/gen_keystock_pdf.ps1` | build_tools.py + convert_md_to_pdf.py + gen_keystock_pdf.py | `forbidden_when_python_available`（从 under_review 更新） |

### 2.3 待确认（under_review）

| # | 文件 | 路径 | 说明 |
|:-:|:-----|:------|:------|
| U1 | register_tasks.ps1 | `代码文件/每日荐股/scripts/register_tasks.ps1` | Windows Task Scheduler 注册脚本。已有 macOS launchd 替代 |
| U2 | setup_scheduler.ps1 | `代码文件/每日荐股/scripts/setup_scheduler.ps1` | 同上 |
| U3 | gen_monthly_report.ps1 | `代码文件/每日荐股/scripts/gen_monthly_report.ps1` | 需确认是否有 Python 替代（monthly_learn.ps1 关联） |
| U4 | monthly_learn.ps1 | `代码文件/每日荐股/scripts/monthly_learn.ps1` | 是否已在 Python 版实现 |
| U5 | catchup_launcher.ps1 | `代码文件/每日荐股/scripts/catchup_launcher.ps1` | 需确认是否有 Python 替代 |
| U6 | gen_monthly_report.ps1 | `代码文件/每日荐股/scripts/gen_monthly_report.ps1` | 需确认是否有 Python 替代（monthly_learn.ps1 关联） |
| U7 | monthly_learn.ps1 | `代码文件/每日荐股/scripts/monthly_learn.ps1` | 是否已在 Python 版实现 |
| U8 | catchup_launcher.ps1 | `代码文件/每日荐股/scripts/catchup_launcher.ps1` | 需确认是否有 Python 替代 |
| U9 | 其他 Win-only .ps1 脚本 | `代码文件/每日荐股/scripts/*.ps1` | 保留现有 runtime_entry_registry 中 `forbidden` 状态不变 |

### 2.4 遗留隔离

| # | 隔离资产 | 路径 | 说明 |
|:-:|:---------|:------|:------|
| L1 | _win32_legacy/ | `_win32_legacy/` | 整个目录标记为 legacy_isolated，不加修改，不入运行时 |
| L2 | PreToolUse_hook.ps1 | `_win32_legacy/PreToolUse_hook.ps1` | 旧 Windows hook 实现，已由 Python 版替代 |
| L3 | write_protection_hook.ps1 | `_win32_legacy/write_protection_hook.ps1` | 同上 |

---

## 三、变更记录

| 操作 | 文件 | 仅注册表 | 物理删除 |
|:-----|:-----|:---------|:---------|
| 新增 R1-R7 保留确认 | — | 否（仅确认状态） | ❌ 否 |
| 新增 D1-D9 废弃冻结 | — | ✅ 更新 win_legacy_migration_register.json | ❌ 否 |
| 新增 U1-U9 under_review（不含已迁移的 gen_pdf 系列） | — | ✅ 更新 win_legacy_migration_register.json | ❌ 否 |
| 新增 L1-L3 遗留隔离 | — | ✅ 更新 win_legacy_migration_register.json | ❌ 否 |

> **本文件仅做状态登记，不删除、不移动任何物理文件。**

---

*流程编号：F-ARCH + F-DATA + F-GATE + F-MIGRATE + F-SCHEDULE | 阶段门：G3*
*formal pipeline actor/HMAC 明示例外*
