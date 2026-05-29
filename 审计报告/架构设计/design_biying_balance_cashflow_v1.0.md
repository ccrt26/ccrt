# 设计文档：必盈资产负债表 + 现金流量表接入

> pipeline_stage: complete | 代码等级: L0 | 版本: v1.0 | 2026-05-29

## 一、变更概要

| 项 | 内容 |
|:--|:-----|
| 代码等级 | **L0**（工具/数据模块，红结自查+新安常规） |
| 涉及文件 | 2个 |
| 预估行数 | ~80行新增 |
| 新增函数 | `Get-BiyingBalanceSheet`, `Get-BiyingCashFlow` |

## 二、背景

必盈免费 licence（`8025D388-5DEB-42C0-9084-E4EEB378654F`，有效期至 2099-12-31，200次/天）已实测确认资产负债表和现金流量表端点可用。当前 biying.ps1 仅实现利润表（`Get-BiyingFinancial`），financial.ps1 中必盈 fallback 将 11 个资产负债表/偿债能力字段设为 `$null`。

## 三、数据流设计

```
Get-StockFinancial (financial.ps1)
  └─ 东方财富[3] → 失败 → 同花顺[THS] → 失败
     └─ 必盈[13] (当前仅利润表)
        ├─ Get-BiyingFinancial      → 利润表 (营收/EPS/净利润)
        ├─ Get-BiyingBalanceSheet   → 资产负债表 (NEW)
        └─ Get-BiyingCashFlow       → 现金流量表 (NEW)
           → 三表合并映射 → 输出统一字段
```

降级链不变：必盈仍在第三顺位。

## 四、接口契约

### 4.1 biying.ps1 新增

```powershell
function Get-BiyingBalanceSheet {
    param([string]$Code)
    # 端点: hsstock/financial/balance/{code}.{SH|SZ}/{licence}
    # 返回: 原始资产负债表JSON数组，最新季度在前
    # 关键字段: jzrq(截止日), zzc(总资产), zfz(总负债),
    #          ldzc(流动资产), ldfz(流动负债), dqjk(短期借款),
    #          zcfzl(资产负债率), ldbl(流动比率), sdbl(速动比率)
}

function Get-BiyingCashFlow {
    param([string]$Code)
    # 端点: hsstock/financial/cashflow/{code}.{SH|SZ}/{licence}
    # 返回: 原始现金流量表JSON数组
    # 关键字段: jzrq(截止日), xjl(现金流净额),
    #          jyxjlr(经营活动现金流净额), tzxjlr(投资活动现金流净额)
}
```

格式与现有 `Get-BiyingFinancial` 一致。

### 4.2 financial.ps1 修改

在必盈 fallback 块中，获取利润表后并行调用资产负债表和现金流量表，将当前 `$null` 的字段填充：

| 字段 | 当前值 | 新来源 | 必盈字段 |
|:-----|:------|:------|:--------|
| TOTAL_ASSETS | `$null` | 资产负债表 | `zzc` |
| TOTAL_LIABILITIES | `$null` | 资产负债表 | `zfz` |
| TOTAL_CURRENT_ASSETS | `$null` | 资产负债表 | `ldzc` |
| TOTAL_CURRENT_LIABILITIES | `$null` | 资产负债表 | `ldfz` |
| DEBT_ASSET_RATIO | `$null` | 资产负债表 | `zcfzl` |
| CURRENT_RATIO | `$null` | 资产负债表 | `ldbl` |
| QUICK_RATIO | `$null` | 资产负债表 | `sdbl` |
| SHORT_BORROWINGS | `$null` | 资产负债表 | `dqjk` |
| LONG_TERM_BORROWINGS | `$null` | 资产负债表 | `cqjk` (长期借款) |
| INVENTORY | `$null` | 资产负债表 | `ch` (存货) |
| ACCOUNTS_RECEIVABLE | `$null` | 资产负债表 | `yszk` (应收账款) |
| 经营现金流 | — | 现金流量表 | `jyxjlr` |
| 投资现金流 | — | 现金流量表 | `tzxjlr` |
| 筹资现金流 | — | 现金流量表 | `czxjlr` |

## 五、风险评估

- **API限额**: 新增 2 次/日×10只 = 20次/天，仍在 200 次限额内（当前 26 次含测试）
- **必盈字段可能为"-"**: 需在映射时做 `-ne "-"` 判断，fallback 回 `$null`
- **资产负债表/现金流量表与利润表季度对齐**: 三表按 `jzrq`(截止日期) 对齐合并

## 六、Token 影响评估

- 新增 ~80 行代码，2 次额外 API 调用/只股票（仅在降级至必盈时）
- 不增加模型 token 消耗（纯数据拉取）
- biying.ps1: 173行 → ~245行（<500行限制）
- financial.ps1: 375行 → ~425行（<500行限制）

## 七、需求 → 代码核对清单

- [ ] biying.ps1: `Get-BiyingBalanceSheet` 函数
- [ ] biying.ps1: `Get-BiyingCashFlow` 函数
- [ ] biying.ps1: 函数注释更新（三大报表均实现）
- [ ] financial.ps1: 必盈 fallback 块调用新函数
- [ ] financial.ps1: 资产负债表字段映射（≥11个字段）
- [ ] financial.ps1: 现金流量表字段映射（≥3个字段）
- [ ] 字段值为"-"时 fallback 回 `$null`
- [ ] 降级链未改变（必盈仍在第三顺位）
- [ ] 单文件均不超 500 行
