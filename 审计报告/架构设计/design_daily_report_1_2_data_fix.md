# 日报1.2节数据空洞修复设计

> 情墨 | 阶段① 设计交付物 | 2026-05-27
> pipeline_stage: complete
> 代码等级: L0 (工具/数据层)
> finance_confirmed: true
> 关联诊断: 玉夜5/27 — data_full.json缺少High/Low/Open顶层字段 + K线历史数据未被日报提取

---

## 一、根因摘要

玉夜诊断结论（详见对话上下文）：

| # | 空洞表现 | 根因 | 数据是否存在 |
|:--|:-----|:-----|:----:|
| R1 | 5/22-5/23全部"—" | 日报未从K线数组提取历史日数据 | ✅ KHigh/KLow/KClose/KVolume 中有 |
| R2 | 5/26仅收盘价有值 | 同上，收盘价来自PrevClose或末位KClose | ✅ K线数组中有完整OHLCV |
| R3 | 5/27日内高/低也是"—" | data_full.json 缺少High/Low/Open顶层字段 | ✅ stock_data_raw.json中有 |

**一句话**：数据都采到了，但 data_full.json 输出结构不完整（缺 High/Low/Open），且日报生成时没有回填 K 线历史数据。

---

## 二、修复方案

### 2.1 变更范围

| 文件 | 等级 | 变更 | 行数 |
|:-----|:----:|:-----|:----:|
| `代码文件/每日荐股/scripts/batch_data_collector.py` | L0 | ① 组装输出增加 High/Low/Open/PrevClose 顶层字段；② 新增 Recent4Days 预计算数组 | +35行 |
| `.claude/commands/日报.md` | M类 | 1.2节数据源说明更新：标注读取 Recent4Days 字段 | +3行 |

### 2.2 batch_data_collector.ps1 变更

#### 2.2.1 增加行情快照字段（修复R3）

在股票输出对象的组装段（当前 ~line 446-456）增加：

```powershell
Open         = $q.Open
High         = $q.High
Low          = $q.Low
PrevClose    = $q.PrevClose
```

行情API（腾讯[1]）返回中已包含这些字段，当前 `stock_data_raw.json` 有但 `data_full.json` 漏掉了。

#### 2.2.2 预计算 Recent4Days 数组（修复R1/R2）

在组装输出对象之后、添加到 `$output` 之前，增加预计算逻辑：

```powershell
# 预计算近4日数据（供日报1.2节直接读取，避免AI解析K线数组）
$recent4 = @()
if ($k -and $k.KDate -and $k.KDate.Count -gt 0) {
    $n = $k.KDate.Count
    $start = [Math]::Max(0, $n - 4)
    for ($i = $start; $i -lt $n; $i++) {
        $prevClose = if ($i -gt 0) { $k.KClose[$i-1] } else { $k.KClose[0] }
        $chg = if ($prevClose -ne 0) { [math]::Round(($k.KClose[$i] - $prevClose) / $prevClose * 100, 2) } else { 0 }
        $recent4 += [PSCustomObject]@{
            Date         = $k.KDate[$i]
            Close        = $k.KClose[$i]
            ChangePct    = $chg
            High         = $k.KHigh[$i]
            Low          = $k.KLow[$i]
            Volume       = $k.KVolume[$i]
            TurnoverRate = $null   # K线不含换手率，仅当日有
        }
    }
}
# 追加今日快照（如果K线尚未包含今日）
if ($recent4.Count -eq 0 -or $recent4[-1].Date -ne (Get-Date).ToString("yyyy-MM-dd")) {
    $recent4 += [PSCustomObject]@{
        Date         = (Get-Date).ToString("yyyy-MM-dd")
        Close        = $q.Price
        ChangePct    = $q.ChangePct
        High         = $q.High
        Low          = $q.Low
        Volume       = $q.Volume
        TurnoverRate = $q.TurnoverRate
    }
}
# 只保留最近4条
$recent4 = @($recent4 | Select-Object -Last 4)
```

输出对象增加字段：
```powershell
Recent4Days  = $recent4
```

#### 2.2.3 采集后核查（防止再次出现）

在脚本末尾 `$output | ConvertTo-Json` 之前增加核查段：

```powershell
# 核查：重点股票数据完整性（日报1.2节依赖）
$keystockCodes = @("600114","601727","603019","301075","601689","000967","002230","603092")
$missingHigh = @(); $missingRecent4 = @()
foreach ($stock in $output) {
    if ($stock.Code -in $keystockCodes) {
        if (-not $stock.High -or $stock.High -eq 0) { $missingHigh += $stock.Code }
        if (-not $stock.Recent4Days -or $stock.Recent4Days.Count -eq 0) { $missingRecent4 += $stock.Code }
    }
}
if ($missingHigh.Count -gt 0) { Write-Warning "核查: 以下重点股票缺少当日High: $($missingHigh -join ', ')" }
if ($missingRecent4.Count -gt 0) { Write-Warning "核查: 以下重点股票缺少Recent4Days: $($missingRecent4 -join ', ')" }
```

### 2.3 日报.md 变更

1.2节模板下方增加一行数据源提示：

```markdown
> **数据源**：近4日数据从 `data_full.json` → `Recent4Days` 字段直接读取，无需解析K线数组。换手率仅当日有值。
```

---

## 三、影响评估

| 维度 | 评估 |
|:-----|:-----|
| **下游消费者** | scoring_engine_v2.py 读取 data_full.json，新增字段不影响其逻辑（它读 KDate/KClose 等已有数组） |
| **data_final.json** | `data_final.json` 是从 `data_full.json` 派生的，字段透传，不受影响 |
| **向后兼容** | 新增字段完全向后兼容，旧消费者忽略未知字段 |
| **文件大小** | Recent4Days 每只股票 ~500 bytes，54只股票 ≈ 27KB 增量，可忽略 |
| **单文件行数** | batch_data_collector.ps1 当前531行（已超500红线，Phase 2评估）。本次+35行=566行，增幅6.6%，不新增拆分需求 |
| **风险** | 低。仅增加字段输出，不改变现有字段结构或计算逻辑 |

---

## 四、需求→代码核对清单

| # | 需求 | 对应代码位置 | 验证方式 |
|:--|:-----|:-----|:-----|
| 1 | data_full.json 每只股票有 High/Low/Open/PrevClose | batch_data_collector.ps1 组装段 | `jq '.[0].High' data_full.json` 非空 |
| 2 | data_full.json 每只股票有 Recent4Days 数组 | batch_data_collector.ps1 预计算段 | `jq '.[0].Recent4Days | length'` >=1 |
| 3 | Recent4Days 包含 Date/Close/ChangePct/High/Low/Volume | 同上 | `jq '.[0].Recent4Days[0] | keys'` |
| 4 | 采集后核查8只重点股票 | 脚本末尾核查段 | 运行日志无 WARNING |
| 5 | 日报1.2节数据说明更新 | 日报.md | 查看1.2节模板下方 |
| 6 | 旧消费者不受影响 | — | scoring_engine_v2.py 正常运行 |

---

> 情墨+腰子勾签放行后 → 流入阶段③ 新安+旧影审查
