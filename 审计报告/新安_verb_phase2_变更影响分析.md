# 动词合规化 Phase 2 — 变更影响分析

**日期**: 2026-05-27  
**执行者**: 新安  
**流水线**: pipeline_20260527_verb_compliance_phase2  

---

## 变更概述

将 `stock_data_fetcher_legacy` 模块中 9 个非标准动词函数重命名为 PowerShell 标准动词，涉及 15 个文件。

### 函数重命名映射

| 旧函数名 | 新函数名 | 变更类型 |
|:---------|:---------|:--------|
| `Calc-MovingAverage` | `Measure-MovingAverage` | 重命名 |
| `Calc-RSI` | `Measure-RSI` | 重命名 |
| `Calc-MACD` | `Measure-MACD` | 重命名 |
| `Calc-Bollinger` | `Measure-Bollinger` | 重命名 |
| `Calc-ADX` | `Measure-ADX` | 重命名 |
| `Calc-OBV` | `Measure-OBV` | 重命名 |
| `Calc-ATR` | `Measure-ATR` | 重命名 |
| `Save-DataCache` | `Export-DataCache` | 重命名 |
| `Load-DataCache` | `Import-DataCache` | 重命名 |

---

## 逐文件影响分析

### 定义文件（含全新实现+包装器）

| 文件 | Calc-*→Measure-* | Save→Export | Load→Import | Export-ModuleMember | 包装器 |
|:-----|:---:|:---:|:---:|:---:|:---:|
| `core.ps1` | — | 替换 | 替换 | N/A (dot-source) | Save/Load 包装器 |
| `technical.ps1` | 7个全量替换 | — | — | N/A (dot-source) | 7个Calc-*包装器 |
| `legacy.psm1` | 7个全量替换 | 替换 | 替换 | 更新为Measure-* | 全部9个包装器 |

### 调用方文件（仅替换调用，无包装器）

| 文件 | 变更点 |
|:-----|:------|
| `biying.ps1` | Save→Export (3处) |
| `external.ps1` | Save→Export + Load→Import (replace_all) |
| `financial.ps1` | Save→Export + Load→Import (replace_all) |
| `fundflow.ps1` | Save→Export + Load→Import (replace_all) |
| `quote.ps1` | Save→Export + Load→Import (replace_all) |
| `sector.ps1` | Save→Export + Load→Import (replace_all) |
| `test.ps1` | Calc-*→Measure-* (4处) + Export-ModuleMember更新 |
| `run_daily_eval.ps1` | Calc-ATR→Measure-ATR (replace_all) + 包装器 |
| `run_keystock_analysis.ps1` | Calc-*→Measure-* (8处 replace_all) |
| `pigeon_collector.ps1` | 移除 `-DisableNameChecking` 参数 |

### 未修改文件

| 文件 | 原因 |
|:-----|:-----|
| `legacy.ps1` | 死文件——未被任何 .ps1 脚本导入或点源加载 |

---

## 影响范围矩阵

| 影响维度 | 风险等级 | 说明 |
|:---------|:------:|:-----|
| 函数签名 | 零风险 | 参数名和类型完全不变 |
| 返回值格式 | 零风险 | 完全不变 |
| API调用 | 零风险 | 不变 |
| 数据结构 | 零风险 | 不变 |
| 调用链路 | 低风险 | 包装器保证向后兼容 |
| 评分/排序/风控逻辑 | 零风险 | 不变 |

---

## 回滚方案

所有旧函数名保留为包装器，恢复旧行为只需在调用方将 `Measure-*` 改回 `Calc-*`（或直接使用包装器）。包装器为纯委托，无副作用。

**回滚复杂度**: 极低（包装器已就位，无需改定义文件）

---

pipeline_stage: complete
verified_by: 新安
verified_at: 2026-05-27
