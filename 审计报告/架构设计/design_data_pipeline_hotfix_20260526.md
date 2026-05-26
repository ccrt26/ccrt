# 数据管线紧急修复设计 — 玉夜5/25核查P0/P1四合一

> 情墨 | 阶段① 设计交付物 | 2026-05-26
> pipeline_stage: complete
> 代码等级: L0-L1 (工具/数据层)
> 关联审计: 玉夜5/25数据质量核查报告

---

## 一、背景

玉夜5/25核查发现4项缺陷，其中P0-1（FundFlow备源未接线）已有完整设计[design_fundflow_multi_backup_v1.0.md](design_fundflow_multi_backup_v1.0.md)但未实施。本设计文件覆盖全部4项，P0-1引用已有设计，P0-2/P1-3/P1-4为新增设计。

| # | 级别 | 缺陷 | 根因 | 文件 |
|:--|:----:|:-----|:-----|:-----|
| P0-1 | 阻断 | FundFlow备源未接线 | Get-StockFundFlow调用Invoke-DataSource未传BackupCall | fundflow.ps1:16-40 |
| P0-2 | 阻断 | 新浪API[2]不可达 | 外部网络/DNS/API域名问题 | 健康报告4/4复现 |
| P1-3 | 高 | 回填覆盖率<50%阻断全流水线 | 阈值过严+无预热机制，T0/T1字段实际完整却被拦 | health_check.ps1:211 |
| P1-4 | 高 | summary.csv从未填充 | run_daily_eval.ps1未实现§6.1.2聚合逻辑 | run_daily_eval.ps1 |

---

## 二、P0-1: FundFlow备源接线（引用已有设计）

### 2.1 设计引用

完整设计见 [design_fundflow_multi_backup_v1.0.md](design_fundflow_multi_backup_v1.0.md)。核心方案：

- `Get-StockFundFlow` 的 `Invoke-DataSource` 调用补上 `-BackupCall` 参数
- 备源链：THS同花顺 → 迪雅数据[B1] → 麦蕊智数[B2] → 智兔数服[B3] → StockTV[B4]
- 引擎不变，BackupCall内部链式尝试

### 2.2 本次实施范围调整

已有设计覆盖完整的4商业API备源链，但桥接脚本（diya/mairei/zhitu/stocktv）需要API密钥和测试验证。本次实施分两阶段：

**阶段A（本次）**：接线THS备源（已有stock_data_fetcher_ths.py桥接，sector_fund_flow已有THS调用模式可复用）
- fundflow.ps1: BackupCall内先尝试THS
- THS个股资金流需确认bridge是否支持，若否则标记"THS: 仅行业资金流"

**阶段B（后续）**：按已有设计接入4商业API备源
- 需用户提供API密钥/注册后实施

### 2.3 最小实现

```powershell
# fundflow.ps1 Get-StockFundFlow 修改
return Invoke-DataSource -Category "FundFlow" `
    -CacheKey $cacheKey `
    -PrimaryName "东方财富[9]" `
    -PrimaryCall { ... } `
    -BackupName "同花顺[THS]" `
    -BackupCall {
        # 尝试THS个股资金流桥接
        $thsResult = Invoke-ThsFallback -Action "stock_fund_flow" -Params "--code $Code --days $Days"
        if ($thsResult -and $thsResult.Count -gt 0) {
            $script:SourceUsed["FundFlow"] = "同花顺[THS]"
            return $thsResult
        }
        return $null
    }
```

### 2.4 变更清单

| 文件 | 操作 | 等级 | 预计行数 |
|:-----|:----:|:----:|:-------:|
| fundflow.ps1 | 修改Get-StockFundFlow，补BackupCall | L1 | +15行 |
| core.ps1 | 无需变更（SourceRegistry已有THS） | — | 0 |

---

## 三、P0-2: 新浪API不可达监控

### 3.1 问题分析

4份健康报告一致显示新浪API[2]不可达。Get-StockKLine以新浪为主源、腾讯为备源，新浪不可达时退化为单源。需区分：
- **间歇性故障**：加retry解决
- **持续性故障**：加告警+建议切换主源

### 3.2 设计方案

**不修改数据获取函数本身**（Get-StockQuote/Get-StockKLine已有内置降级）。修改点：

1. **health_check.ps1**: 新浪不可达时记录连续失败计数到状态文件
2. **boot模式**: 连续3次不可达→L2告警（建议人工排查）
3. **daily_sim模式**: 仅记录，不阻断（已有腾讯备源兜底）

### 3.3 实现

```powershell
# health_check.ps1 新浪检查增强
$sinaStateFile = Join-Path $RootDir "代码文件\数据\.sina_health.json"
$sinaConsecutiveFails = 0
if (Test-Path $sinaStateFile) {
    $sinaState = Get-Content $sinaStateFile -Raw | ConvertFrom-Json
    $sinaConsecutiveFails = [int]$sinaState.ConsecutiveFails
}
# 新浪不可达时
if (新浪不可达) {
    $sinaConsecutiveFails++
    if ($sinaConsecutiveFails -ge 3) {
        Add-Msg "新浪API[2]连续${sinaConsecutiveFails}次不可达，建议排查网络/DNS" "Red"
        if ($result.AlertLevel -lt "L2") { $result.AlertLevel = "L2" }
    }
} else {
    $sinaConsecutiveFails = 0
}
@{ ConsecutiveFails = $sinaConsecutiveFails; LastCheck = (Get-Date).ToString("o") } | 
    ConvertTo-Json | Set-Content $sinaStateFile
```

### 3.4 变更清单

| 文件 | 操作 | 等级 | 预计行数 |
|:-----|:----:|:----:|:-------:|
| health_check.ps1 | 增强新浪不可达检测+连续失败计数 | L0 | +20行 |

---

## 四、P1-3: 回填覆盖率阈值调整

### 4.1 问题分析

当前逻辑（health_check.ps1:205-214）：
```
if coverage < 50% AND mode != "boot" → T0阻断 → L3 → exit 1
```

5/25实际状态：T0字段完整率100%，T1字段缺失率0%，数据文件含134只股票。仅因回填覆盖率24.3%<50%，流水线全停。这违反了"数据可用即应放行"的原则——回填覆盖率是**积累性指标**，不应成为单日阻断条件。

### 4.2 设计方案

**分层处理**：

| 条件 | 当前行为 | 新行为 |
|:-----|:--------|:------|
| coverage < 30% | T0阻断(L3) | T0阻断(L3) — 严重不足 |
| 30% ≤ coverage < 50% | T0阻断(L3) | T1降级(L1) — 告警但不阻断 |
| 50% ≤ coverage < 80% | T1降级(L1) | T1降级(L1) — 不变 |
| coverage ≥ 80% | 正常(L0) | 正常(L0) — 不变 |

增加的L1降级标记不阻断流水线，但在报告中标注 `backfill_degraded`。

**额外**：在boot模式增加回填预热步骤（health_check.ps1 boot模式下调backfill_returns.py），每日开机时先跑一次回填。

### 4.3 变更清单

| 文件 | 操作 | 等级 | 预计行数 |
|:-----|:----:|:----:|:-------:|
| health_check.ps1:205-214 | 修改回填覆盖率判定阈值 | L0 | 改8行 |
| daily_workflow.ps1:177 | Phase 0健康检查新增boot预热 | L1 | +3行 |

---

## 五、P1-4: summary.csv生成

### 5.1 问题分析

run_daily_eval.ps1 写入records.csv（§6.1.1实现完整），但白皮书§6.1.2要求的summary.csv从未生成。summary.csv应聚合当次评估的汇总指标。

### 5.2 设计方案

在run_daily_eval.ps1末尾（records.csv写入完成后，§6.1.1之后）追加summary.csv写入逻辑。

**summary.csv格式**（与现有header一致）：
```
period,start_date,end_date,total_recommendations,wins,losses,win_rate,
total_profit,total_loss,profit_loss_ratio,portfolio_return,hs300_return,
excess_return,tech_misjudge_rate,money_misjudge_rate,sector_misjudge_rate,
news_misjudge_rate,veto_kill_rate,exemption_win_rate,recommended_win_rate,
vetoed_win_rate,market_win_rate,veto_effectiveness,score_distinction
```

**数据来源**：当次评估已计算的变量（$winRate, $avgWin, $avgLoss, $profitLossRatio, $portfolioReturn, $hs300Change, $excessReturn, $dimChecks, $scoreDistinction）。

**聚合方式**：每次eval追加一行，period=本次评估日期范围（单日）。

### 5.3 实现位置

run_daily_eval.ps1 第406行（records.csv写入完成后）之后插入：

```powershell
# ============================================================
# 写入 summary.csv — 白皮书 §6.1.2
# ============================================================
Write-Host "`n写入评估汇总 summary.csv [§6.1.2]..."
$summaryFile = Join-Path $evalReportDir "summary.csv"
$summaryExists = Test-Path $summaryFile
if (-not $summaryExists) {
    $summaryHeader = "period,start_date,end_date,total_recommendations,wins,losses,win_rate,total_profit,total_loss,profit_loss_ratio,portfolio_return,hs300_return,excess_return,tech_misjudge_rate,money_misjudge_rate,sector_misjudge_rate,news_misjudge_rate,veto_kill_rate,exemption_win_rate,recommended_win_rate,vetoed_win_rate,market_win_rate,veto_effectiveness,score_distinction"
    Add-Content -Path $summaryFile -Value $summaryHeader -Encoding UTF8
}

# 维度误判率
$techMisRate = ($dimChecks | Where-Object Dim -eq "技术面").Rate
if (-not $techMisRate) { $techMisRate = "-" }
$moneyMisRate = ($dimChecks | Where-Object Dim -eq "资金面").Rate
if (-not $moneyMisRate) { $moneyMisRate = "-" }
$sectorMisRate = ($dimChecks | Where-Object Dim -eq "板块面").Rate
if (-not $sectorMisRate) { $sectorMisRate = "-" }
$newsMisRate = ($dimChecks | Where-Object Dim -eq "消息面").Rate
if (-not $newsMisRate) { $newsMisRate = "-" }

$summaryLine = "single,$todayStr,$todayStr,$totalEval,$winCount,$lossCount,$winRate,$avgWin,$avgLoss,$profitLossRatio,$portfolioReturn,$hs300Change,$excessReturn,$techMisRate,$moneyMisRate,$sectorMisRate,$newsMisRate,-,-,-,-,-,-,$scoreDistinction"
Add-Content -Path $summaryFile -Value $summaryLine -Encoding UTF8
Write-Host "  已追加评估汇总到 summary.csv"
```

### 5.4 变更清单

| 文件 | 操作 | 等级 | 预计行数 |
|:-----|:----:|:----:|:-------:|
| run_daily_eval.ps1:406后 | 新增summary.csv写入 | L1 | +25行 |

---

## 六、影响范围总表

### 6.1 变更文件汇总

| # | 文件 | 操作 | 等级 | 行数 |
|:--|:-----|:----:|:----:|:---:|
| P0-1 | fundflow.ps1 | 修改Get-StockFundFlow | L1 | +15 |
| P0-2 | health_check.ps1 | 新浪连续失败计数 | L0 | +20 |
| P1-3 | health_check.ps1 | 回填阈值调整 | L0 | 改8 |
| P1-3 | daily_workflow.ps1 | Phase 0预热 | L1 | +3 |
| P1-4 | run_daily_eval.ps1 | summary.csv生成 | L1 | +25 |
| **合计** | **5处修改，0新增文件** | | | **~71行** |

### 6.2 下游影响

| 下游模块 | 影响 |
|:---------|:----:|
| scoring_engine_v2.py | 无影响 |
| batch_data_collector.ps1 | 无影响（Get-StockFundFlow签名不变） |
| gen_daily_html.ps1 | 无影响 |
| sim_trading.ps1 | 无影响 |
| 健康报告 | 新浪连续失败变L2告警；回填30-50%变L1不阻断 |

### 6.3 回滚方案

`git revert` 单次提交即可。无新增文件，无接口变更。

---

## 七、设计决策记录

| 决策 | 选择 | 备选 | 理由 |
|:-----|:----:|:-----|:-----|
| FundFlow备源阶段 | 先接THS，4商业API后推 | 一步到位4API | THS桥接已存在，零新依赖；4API需密钥验证 |
| 新浪不可达处理 | 连续失败计数+告警 | 自动切换主源 | 改主源顺序风险大，先监控收集数据 |
| 回填阈值 | 30%阻断/50%告警 | 保持50%阻断 | 避免因积累性指标阻断数据质量合格的流水线 |
| summary.csv | 追加模式 | 全量重写 | 追加保持历史记录，与records.csv一致 |

---

## 八、需求→代码核对清单

> 情墨+腰子共同勾签后放行至红结编码

| # | 需求 | 实现位置 | 情墨 | 腰子 |
|:--|:-----|:---------|:----:|:----:|
| H1 | Get-StockFundFlow补BackupCall，接THS | fundflow.ps1:16-40 | ☐ | ☐ |
| H2 | THS失败→过期缓存兜底不变 | Invoke-DataSource引擎 | ☐ | ☐ |
| H3 | 新浪连续3次不可达→L2告警 | health_check.ps1 | ☐ | ☐ |
| H4 | 新浪状态持久化到.sina_health.json | health_check.ps1 | ☐ | ☐ |
| H5 | 回填<30%→L3阻断；30-50%→L1告警不阻断 | health_check.ps1:211 | ☐ | ☐ |
| H6 | Phase 0 boot模式预热回填 | daily_workflow.ps1:177 | ☐ | ☐ |
| H7 | summary.csv按§6.1.2格式追加 | run_daily_eval.ps1 | ☐ | ☐ |
| H8 | 不改变任何现有函数签名 | 全部 | ☐ | ☐ |
| H9 | 不改变数据文件格式 | 全部 | ☐ | ☐ |

---

> 情墨阶段①完成 | pipeline_stage: complete | 待腰子闸门1a确认
