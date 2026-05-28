# 铁律量化 - 模拟交易策略迭代触发器自动检测
# 被 sim_trading.ps1 在每轮执行末尾调用，也可独立运行
# 用法: .\check_tier_triggers.ps1 -PerfFile "路径/perf_summary.json"
#       .\check_tier_triggers.ps1 -Standalone -Date 20260523

param(
    [string]$PerfFile = "",
    [string]$LogDir = "",
    [string]$IssuesFile = "",
    [switch]$Standalone,
    [string]$Date = (Get-Date).ToString("yyyyMMdd")
)

$rootDir = "C:\Users\34269\Documents\Claude\股票分析"

# 默认路径
if (-not $PerfFile) {
    $PerfFile = Join-Path $rootDir "模拟交易/绩效报告/perf_summary.json"
}
if (-not $LogDir) {
    $LogDir = Join-Path $rootDir "模拟交易/日志"
}
if (-not $IssuesFile) {
    $IssuesFile = Join-Path $rootDir "模拟交易/issues.csv"
}

Write-Host "=== 模拟交易策略迭代触发器检测 ===" -ForegroundColor Cyan
Write-Host "日期: $Date`n"

# 检查 perf_summary.json 是否存在
if (-not (Test-Path $PerfFile)) {
    Write-Host "[SKIP] perf_summary.json 不存在（数据不足）" -ForegroundColor Yellow
    exit 0
}

# 读取绩效数据
try {
    $perf = Get-Content $PerfFile -Raw -Encoding UTF8 | ConvertFrom-Json
} catch {
    Write-Error "[ERROR] 无法解析 $PerfFile : $_ "
    exit 1
}

$triggered = @()  # 记录触发的级别

# ---- Tier 1: 日常微调 ----
$tier1Reasons = @()
if ($perf.ConsecutiveLosses -ge 3) {
    $tier1Reasons += "连续亏损$($perf.ConsecutiveLosses)笔>=3笔"
}
if ($perf.MaxDrawdown -lt -3 -and $perf.MaxDrawdown -gt -100) {
    $tier1Reasons += "最大回撤$($perf.MaxDrawdown)%>3%"
}
# 单项策略亏损>1% 需要额外数据，暂略

if ($tier1Reasons.Count -gt 0) {
    Write-Host "[TIER 1] 触发微调条件:" -ForegroundColor Cyan
    foreach ($r in $tier1Reasons) { Write-Host "   ⚠ $r" -ForegroundColor Cyan }
    $triggered += 1
} else {
    Write-Host "[TIER 1] 未触发" -ForegroundColor Green
}

# ---- Tier 2: 规则迭代 ----
$tier2Reasons = @()
if ($perf.ConsecutiveLosses -ge 5) {
    $tier2Reasons += "连续亏损$($perf.ConsecutiveLosses)笔>=5笔"
}
# MaxSingleStockLoss 从 perf_summary.json PerStock 聚合计算
$maxStockLoss = 0
if ($perf.PerStock) {
    foreach ($stockP in $perf.PerStock.PSObject.Properties) {
        if ($stockP.Value.TotalPnL -and [double]$stockP.Value.TotalPnL -lt $maxStockLoss) {
            $maxStockLoss = [double]$stockP.Value.TotalPnL
        }
    }
}
if ($maxStockLoss -le -3) {
    $tier2Reasons += "单股累计亏损${maxStockLoss}元>=3%总资产"
}
if ($null -ne $perf.WinRate -and [double]$perf.WinRate -lt 40 -and $null -ne $perf.TotalTrades -and [int]$perf.TotalTrades -ge 10) {
    $tier2Reasons += "胜率$($perf.WinRate)%<40%且交易$($perf.TotalTrades)笔>=10笔"
}

if ($tier2Reasons.Count -gt 0) {
    Write-Host "[TIER 2] 触发规则迭代条件:" -ForegroundColor Yellow
    foreach ($r in $tier2Reasons) { Write-Host "   ⚠ $r" -ForegroundColor Yellow }
    $triggered += 2
} else {
    Write-Host "[TIER 2] 未触发" -ForegroundColor Green
}

# ---- Tier 3: 方法论重构 ----
$tier3Reasons = @()
if ($null -ne $perf.TotalReturnPct -and [double]$perf.TotalReturnPct -le -10) {
    $tier3Reasons += "累计亏损$($perf.TotalReturnPct)%>=10%"
}
if ($null -ne $perf.WinRate -and [double]$perf.WinRate -lt 30) {
    $tier3Reasons += "胜率$($perf.WinRate)%<30%"
}
# 最大回撤超预警3次需要历史数据，暂略

if ($tier3Reasons.Count -gt 0) {
    Write-Host "[TIER 3] 触发方法论重构条件!!!!" -ForegroundColor Red
    foreach ($r in $tier3Reasons) { Write-Host "   🚨 $r" -ForegroundColor Red }
    $triggered += 3
} else {
    Write-Host "[TIER 3] 未触发" -ForegroundColor Green
}

# ---- 写入 issues.csv ----
$maxLevel = if ($triggered.Count -gt 0) { ($triggered | Measure-Object -Maximum).Maximum } else { 0 }
if ($maxLevel -gt 0 -and $IssuesFile) {
    $issueLine = "$Date,$maxLevel,""$($tier1Reasons + $tier2Reasons + $tier3Reasons -join '; ')"",$($perf.WinRate),$($perf.TotalReturn)"
    Add-Content -Path $IssuesFile -Value $issueLine -Encoding UTF8
    Write-Host "`n已写入: $IssuesFile" -ForegroundColor Gray
}

# ---- 输出汇总 ----
Write-Host "`n触发级别: "$(if ($maxLevel -eq 0) { "无" } else { "Tier $maxLevel" }) -ForegroundColor $(if ($maxLevel -ge 3) { "Red" } elseif ($maxLevel -ge 2) { "Yellow" } else { "Cyan" })
exit $maxLevel
