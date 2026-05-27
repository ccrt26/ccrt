# 信鸽自动采集报错修复 — 架构设计

> pipeline_stage: complete | finance_confirmed: false
> **日期**: 2026-05-27 | **设计**: 情墨 | **代码等级**: L0（工具/数据采集）
> **触发**: 信鸽开机自检报错 + 模块导入动词警告

---

## 一、问题诊断

### 1.1 阻断性：双BOM编码错误

| 文件 | 当前状态 | 根因 |
|:-----|:--------|:-----|
| `代码文件/信鸽信息采集/pigeon_boot_check.ps1` | 文件头双BOM (EF BB BF ×2) | 某次编辑工具重复写入UTF-8 BOM |
| `代码文件/每日荐股/scripts/test_catchup_logic.ps1` | 同上 | 同上 |

PowerShell将第二个BOM (`﻿`)解析为命令名，报`CommandNotFoundException`。**采集流程完全阻断。**

### 1.2 警告性：模块未批准动词

`stock_data_fetcher_legacy.psm1` 导出以下未批准动词的函数：

| 函数 | 未批准动词 | 调用方数量 | 标准替代 |
|:-----|:---------|:--------|:-------|
| `Save-DataCache` | Save | 2 (internal) | Export- |
| `Load-DataCache` | Load | 2 (internal) | Import- |
| `Calc-MovingAverage` | Calc | 3 | Measure- 或 ConvertTo- |
| `Calc-RSI` | Calc | 3 | 同上 |
| `Calc-MACD` | Calc | 3 | 同上 |
| `Calc-Bollinger` | Calc | 3 | 同上 |
| `Calc-ADX` | Calc | 2 | 同上 |
| `Calc-OBV` | Calc | 2 | 同上 |
| `Calc-ATR` | Calc | 3 | 同上 |

**调用方涉及5个文件**（modules/test.ps1, modules/technical.ps1, run_keystock_analysis.ps1, legacy.ps1, legacy.psm1），共约25处调用点。

---

## 二、修复方案

### 2.1 BOM修复（阻断性，立即修复）

**方案**：使用PowerShell `[System.Text.UTF8Encoding]` 无BOM模式重写文件。

```
$content = Get-Content $path -Raw
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($path, $content, $utf8NoBom)
```

- 影响：仅文件编码，不改变任何逻辑
- 风险：零
- 代码等级：L0

### 2.2 动词警告（警告性，两阶段处理）

**决策**：完整重命名9个函数+更新25处调用点属于高风险变更，当前无测试覆盖保护。采用渐进策略。

**Phase 1（本次修复）**：在模块导入处抑制警告

```powershell
Import-Module $path -WarningAction SilentlyContinue -ErrorAction Stop
```

- 仅修改导入语句（约2-3处）
- 警告不阻塞执行，抑制后采集可正常运行

**Phase 2（独立E类项目，后续推进）**：完整动词合规化

- 新建 `technical_indicators.psm1`（L1模块），使用标准动词
- 旧函数保留为别名（向后兼容），标记deprecated
- 所有调用方迁移完成后移除旧函数
- 需配合Golden Master测试验证指标计算一致性

---

## 三、变更范围

| 文件 | 变更类型 | 代码等级 | 风险 |
|:-----|:--------|:------:|:--:|
| `信鸽信息采集/pigeon_boot_check.ps1` | 编码修复 | L0 | 无 |
| `每日荐股/scripts/test_catchup_logic.ps1` | 编码修复 | L0 | 无 |
| 模块导入处（2-3处）| 添加-WarningAction | L0 | 极低 |

> 本次不涉及函数重命名。Phase 2（动词合规化）作为独立E类项目另行启动。

---

## 四、需求→代码核对清单

| # | 需求 | 落地点 |
|:--|:-----|:------|
| F1 | pigeon_boot_check.ps1 去除双BOM | 编码修复 |
| F2 | test_catchup_logic.ps1 去除双BOM | 编码修复 |
| F3 | stock_data_fetcher_legacy 导入时抑制动词警告 | Import-Module调用处 |

---

> **版本**: v1.0 | **日期**: 2026-05-27 | pipeline_stage: complete
