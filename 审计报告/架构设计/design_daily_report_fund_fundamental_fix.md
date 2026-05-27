# 日报数据空洞修复（第二期）— 资金面基线+基本面补齐

> 情墨 | 阶段① 设计交付物 | 2026-05-27
> pipeline_stage: complete
> 代码等级: L0 (工具/数据层)
> finance_confirmed: true
> 关联: 第一期 design_daily_report_1_2_data_fix.md（1.2节行情已修）

---

## 一、根因

玉夜诊断4项数据空洞：

| # | 空洞 | 根因 | 数据是否存在 |
|:--|:-----|:-----|:----:|
| F1 | PS="数据不可获取" | RevenueTTM+MktCap都有，未计算 | ⚠️ 可算 |
| F2 | 经营现金流="数据不可获取" | THS的`stock_financial_abstract_ths`返回`CFPS`字段，但batch_collector未提取 | ✅ THS有 |
| F3 | 主力净流入5/26基线="—" | FundFlow_History数组有5日数据，未提取昨日值 | ✅ 有 |
| F4 | 融资余额5/26基线="—" | Get-MarginData返回5日数组，未提取$mg[1] | ✅ 有 |

---

## 二、修复方案

### 2.1 变更范围

| 文件 | 等级 | 变更 |
|:-----|:----:|:-----|
| `代码文件/每日荐股/scripts/batch_data_collector.ps1` | L0 | 新增5个预计算字段 + 从$fin提取CFPS |
| `.claude/commands/日报.md` | M类 | §二资金面/§三基本面数据源说明更新 |

### 2.2 batch_data_collector.ps1 变更

#### F1: PS计算

```powershell
# 在 RevenueTTM 赋值后：
$ps = $null
if ($revenueTTM -and $revenueTTM -gt 0 -and $q.MktCap -and $q.MktCap -gt 0) {
    $revenueTTM_Yi = $revenueTTM / 1e8
    if ($revenueTTM_Yi -gt 0) {
        $ps = [math]::Round([double]$q.MktCap / $revenueTTM_Yi, 2)
    }
}
```

输出增加字段：`PS = $ps`

#### F2: 经营现金流提取

从`$fin`（Get-StockFinancial返回）提取CFPS。东方财富主源`RPT_LICO_FN_CPD`表可能不包含，但THS备源返回的字段中包含`CFPS`：

```powershell
$cfps = $null
if ($fin -and $fin.Count -gt 0) {
    $cfpsVal = $fin[0].CFPS
    if (-not $cfpsVal) { $cfpsVal = $fin[0].OPERATE_CASHFLOW_PS }
    if ($cfpsVal) { $cfps = [double]$cfpsVal }
}
```

#### F3: 主力净流入昨日基线

FundFlow_History 是数组，取倒数第二个值（昨日）：

```powershell
# 在 FundFlow_History 赋值后：
$fundMainNetPrev = $null
if ($fund -and $fund.Count -ge 2) {
    $fundMainNetPrev = [double]$fund[1].MainNetInflow
}
```

#### F4: 融资余额/净买入昨日基线

`$mg`是Get-MarginData返回的5日数组，`$mg[0]`=今日，`$mg[1]`=昨日：

```powershell
$marginRZYE_Prev = $null; $marginRZJME_Prev = $null
if ($mg -and $mg.Count -ge 2) {
    $marginRZYE_Prev = [double]$mg[1].RZYE
    $marginRZJME_Prev = [double]$mg[1].RZJME
}
```

### 2.3 日报.md 变更

§二资金面表格增加数据源说明：

```markdown
> **数据源**：主力净流入从 `FundMainNet`/`FundMainNet_Prev` 读取，融资余额从 `MarginRZYE`/`MarginRZYE_Prev` 读取。
```

§三基本面表格增加PS/CFPS说明。

---

## 三、影响评估

| 维度 | 评估 |
|:-----|:-----|
| **下游消费者** | scoring_engine_v2.py 不受影响（忽略未知字段） |
| **向后兼容** | 新增字段，旧消费者忽略 |
| **CFPS可用性** | 仅当THS备源被触发时有值。主源(东方财富RPT_LICO_FN_CPD)不含此字段。在输出中`$null`表示不可获取 |
| **PS可用性** | RevenueTTM和MktCap都有值时自动计算，否则为null |
| **风险** | 低。仅增加字段输出，不改变现有逻辑 |

---

## 四、需求→代码核对清单

| # | 需求 | 验证方式 |
|:--|:-----|:-----|
| 1 | data_full.json有PS字段 | `jq '.[].PS' data_full.json` — 重点股非null |
| 2 | data_full.json有CFPS字段 | `jq '.[].CFPS' data_full.json` — 字段存在 |
| 3 | data_full.json有FundMainNet_Prev | `jq '.[].FundMainNet_Prev' data_full.json` |
| 4 | data_full.json有MarginRZYE_Prev | `jq '.[].MarginRZYE_Prev' data_full.json` |
| 5 | data_full.json有MarginRZJME_Prev | `jq '.[].MarginRZJME_Prev' data_full.json` |
| 6 | scoring_engine_v2.py兼容 | 正常运行不报错 |

---

> 情墨+腰子勾签放行后 → 流入阶段③ 新安+旧影审查
