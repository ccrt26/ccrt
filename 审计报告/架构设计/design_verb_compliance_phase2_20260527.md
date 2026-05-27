# 动词合规化 Phase 2 — 架构设计

> pipeline_stage: complete | finance_confirmed: true
> **日期**: 2026-05-27 | **设计**: 情墨 | **代码等级**: L1（策略/基础设施）
> **触发**: Phase 1识别出9个未批准动词函数（Calc-×7/Save-×1/Load-×1），本期完整迁移

---

## 一、现状分析

### 1.1 未批准动词清单

| 旧函数 | 出现次数(定义+调用) | 定义位置 | 标准动词 |
|:------|:------------------:|:--------|:------|
| `Save-DataCache` | 26 | core.ps1, legacy.ps1, legacy.psm1 | `Export-` |
| `Load-DataCache` | 25 | core.ps1, legacy.ps1, legacy.psm1 | `Import-` |
| `Calc-MovingAverage` | 15 | technical.ps1, legacy.ps1, legacy.psm1 | `Measure-` |
| `Calc-RSI` | 7 | technical.ps1, legacy.ps1, legacy.psm1 | `Measure-` |
| `Calc-MACD` | 7 | technical.ps1, legacy.ps1, legacy.psm1 | `Measure-` |
| `Calc-Bollinger` | 7 | technical.ps1, legacy.ps1, legacy.psm1 | `Measure-` |
| `Calc-ADX` | 3 | technical.ps1, legacy.psm1 | `Measure-` |
| `Calc-OBV` | 3 | technical.ps1, legacy.psm1 | `Measure-` |
| `Calc-ATR` | 5 | technical.ps1, legacy.psm1, run_daily_eval.ps1 | `Measure-` |

### 1.2 受影响文件

**定义层（4文件）**：
- `modules/core.ps1` — Save-DataCache + Load-DataCache 定义
- `modules/technical.ps1` — Calc-×7 定义
- `stock_data_fetcher_legacy.ps1` — Save/Load + Calc-×4 + 模块内调用
- `stock_data_fetcher_legacy.psm1` — Save/Load + Calc-×7 + 模块内调用

**调用层（11文件）**：
- `modules/biying.ps1`, `external.ps1`, `financial.ps1`, `fundflow.ps1`, `quote.ps1`, `sector.ps1` — Save/Load-DataCache
- `modules/test.ps1` — Calc-×5 + Export-ModuleMember
- `重点股票/run_keystock_analysis.ps1` — Calc-×8
- `run_daily_eval.ps1` — Calc-ATR (本地定义+调用)
- `pigeon_collector.ps1` — Import-Module (已加-DisableNameChecking)

**Export-ModuleMember 引用（2处）**：
- `modules/test.ps1:93` — 导出 Calc-×7
- `legacy.psm1:1078` — 导出 Calc-×7

### 1.3 统计

| 指标 | 数值 |
|:-----|:--:|
| 总文件数 | 15 |
| 总变更点 | ~100+ |
| 定义位置 | 4文件 9处定义 |
| 调用位置 | ~90处调用 |

---

## 二、动词映射方案

参考 [PowerShell Approved Verbs](https://docs.microsoft.com/en-us/powershell/scripting/developer/cmdlet/approved-verbs-for-windows-powershell-commands)：

| 旧动词 | 新动词 | 选择理由 |
|:------|:------|:--------|
| `Save-` | `Export-` | 数据持久化写入，Export 是标准动词 |
| `Load-` | `Import-` | 数据持久化读取，与 Export 对称 |
| `Calc-` | `Measure-` | 最接近计算的批准动词——"执行计算并返回结果" |

> **备选**：Calc→`ConvertTo-` 适用于数据格式转换而非指标计算，不适合。Calc→`Get-` 过于泛化，丢失"计算"语义。`Measure-` 语义最匹配。

---

## 三、向后兼容策略

### 3.1 核心方案：轻量级包装器（Wrapper）

旧函数保留为轻量包装，内部调用新函数，确保所有外部调用方不中断：

```powershell
# 新定义（批准动词）
function Measure-MovingAverage {
    param([array]$Data, [string]$Field = "Close", [int]$Period = 5)
    # ... 完整实现 ...
}

# 旧包装（向后兼容）
function Calc-MovingAverage {
    param([array]$Data, [string]$Field = "Close", [int]$Period = 5)
    Write-Warning "Calc-MovingAverage is deprecated, use Measure-MovingAverage"
    Measure-MovingAverage -Data $Data -Field $Field -Period $Period
}
```

### 3.2 层级执行计划

| 层级 | 操作 | 文件 | 影响 |
|:----:|:-----|:-----|:----|
| L1 | 定义新函数 | core.ps1, technical.ps1, legacy.ps1, legacy.psm1, run_daily_eval.ps1 | 新增9个Measure-*/Export-*/Import-*定义 |
| L2 | 旧函数→包装器 | 同上 | 9个旧函数主体替换为→新函数调用 |
| L3 | 模块内调用改用新名 | 所有定义文件内部 | 自调用改为新名 |
| L4 | Export-ModuleMember更新 | test.ps1, legacy.psm1 | 导出新名+旧名 |
| L5 | 外部调用方迁移 | biying/external/financial/fundflow/quote/sector/run_keystock_analysis | 全部改用新名 |

### 3.3 Deprecation Timeline

| 阶段 | 时间 | 状态 |
|:-----|:----|:-----|
| 当前 Phase 2 | 2026-05-27 | 旧包装器+deprecation warning |
| Phase 3（未来） | TBD | 移除所有旧包装器 |

---

## 四、风险与验证

### 4.1 风险

| 风险 | 等级 | 缓解 |
|:-----|:---:|:-----|
| 包装器参数传递错误 | 低 | 使用 `@PSBoundParameters` splatting |
| Export-ModuleMember 遗漏 | 中 | 逐文件 grep 验证 |
| 旧定义文件与新模块文件冲突 | 低 | legacy.ps1/legacy.psm1 已独立，无交叉依赖 |
| Calc-ATR 本地定义冲突 | 低 | run_daily_eval.ps1 的 Calc-ATR 是独立副本，单独处理 |

### 4.2 Golden Master 验证

Calc-* 系列函数迁移后，需验证技术指标输出完全一致：
- 选1只股票历史K线(≥120条)
- 分别用旧函数和新函数计算 MA/RSI/MACD/Bollinger/ADX/OBV/ATR
- 逐值diff，全部一致 = PASS

---

## 五、需求→代码核对清单

| # | 需求 | 落地点 |
|:--|:-----|:------|
| V1 | Save-DataCache → Export-DataCache | core.ps1, legacy.ps1, legacy.psm1 |
| V2 | Load-DataCache → Import-DataCache | core.ps1, legacy.ps1, legacy.psm1 |
| V3 | Calc-×7 → Measure-×7 | technical.ps1, legacy.ps1, legacy.psm1 |
| V4 | Calc-ATR → Measure-ATR | run_daily_eval.ps1 |
| V5 | 旧函数保留为包装器+deprecation warning | 全部4个定义文件 |
| V6 | 模块内自调用改为新名 | 全部定义文件 |
| V7 | Export-ModuleMember 新增新名 | test.ps1, legacy.psm1 |
| V8 | 外部调用方全部迁移至新名 | 11个调用文件 |
| V9 | Golden Master 指标一致性验证 | 技术指标 diff |

---

> **版本**: v1.0 | **日期**: 2026-05-27 | pipeline_stage: complete
