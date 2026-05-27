# 设计文档：数据归档全覆盖

**设计日期**: 2026-05-27
**设计者**: 情墨
pipeline_stage: complete
finance_confirmed: true
**代码等级**: L0（工具/数据层，红结自查+新安常规）

---

## 1. 现状

玉夜全景审计发现：管线产出物有8类未归档到 `历史数据/`，另有1类需要周期备份。

## 2. 归档方案

### 2.1 日归档（追加到 archive_data.ps1）

| # | 源路径 | → 历史数据路径 | 方式 |
|:--|:------|:------|:-----|
| 1 | `代码文件/数据/score_history.jsonl` | `04_原始数据/{date}_score_history.jsonl` | 日快照 |
| 2 | `每日荐股/评估报告/records.csv` | `02_评估数据/{date}_records.csv` | 日快照 |
| 3 | `每日荐股/评估报告/summary.csv` | `02_评估数据/{date}_summary.csv` | 日快照 |
| 4 | `重点股票/次日评估/评估结果/*.json` | `02_评估数据/` (文件名含日期直接拷) | 日快照 |
| 5 | `重点股票/预判记录/predictions.csv` | `02_评估数据/{date}_predictions.csv` | 日快照 |
| 6 | `模拟交易/交易决策/交易指令_*.json` | `01_交易决策/` (文件名含日期直接拷) | 日快照 |
| 7 | `重点股票/股票报告/*/` | `03_分析报告/重点股票/` (保持子目录) | 日镜像 |
| 8 | `重点股票/深度分析/深度分析报告/*/` | `03_分析报告/深度分析/` (保持子目录) | 日镜像 |

### 2.2 周期备份（新增逻辑）

| # | 源路径 | → 备份路径 | 频率 |
|:--|:------|:------|:----:|
| 9 | `重点股票/消息面数据/events_db.json` | `_backup/events_db_{date}.json` | 每周一 |

### 2.3 巡检扩展（inspect_data_health.py）

| 新增检查项 | 目录 | 方式 |
|:----------|:-----|:-----|
| `score_history.jsonl` | `04_原始数据/` | 文件存在+非空 |
| `records.csv` | `02_评估数据/` | 文件存在+CSV有效 |
| `summary.csv` | `02_评估数据/` | 文件存在+CSV有效 |
| `predictions.csv` | `02_评估数据/` | 可选 |

### 2.4 新增目录

```
历史数据/
+  01_交易决策/     ← 模拟交易决策指令
   03_分析报告/
+   深度分析/       ← 深度分析报告（保持子目录结构）
    重点股票/       ← 重点股票日报（从空目录→有内容）
```

## 3. 设计决策

- **日快照 vs 追加**：score_history 和 accumulating CSV 采用日快照（每日拷贝完整文件），而非追加。理由：简单、可独立恢复、文件小（<100KB）
- **报告镜像**：重点股票日报和深度分析报告保持 `股票(代码)/` 子目录结构，用 robocopy /MIR 镜像（只拷贝新增/变更文件）
- **events_db 周期备份**：这是活数据库（append-only），每日归档浪费空间。每周一备份到 `_backup/`
- **03_分析报告/重点股票/** 目录已存在但为空，直接使用同一目录

## 4. 需求→代码核对

| 需求 | 实现位置 | 状态 |
|:-----|:---------|:----:|
| score_history 日归档 | archive_data.ps1 +Archive-File | 待实现 |
| records/summary 日归档 | archive_data.ps1 +Archive-File | 待实现 |
| 评估结果归档 | archive_data.ps1 +循环拷贝 | 待实现 |
| predictions 日归档 | archive_data.ps1 +Archive-File | 待实现 |
| 交易决策归档 | archive_data.ps1 +循环拷贝 | 待实现 |
| 重点股票日报镜像 | archive_data.ps1 +robocopy | 待实现 |
| 深度分析报告镜像 | archive_data.ps1 +robocopy | 待实现 |
| events_db 周期备份 | archive_data.ps1 +周一判断 | 待实现 |
| 巡检覆盖新增项 | inspect_data_health.py | 待实现 |
