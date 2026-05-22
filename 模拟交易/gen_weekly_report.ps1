<#
.SYNOPSIS
  铁律量化 · 模拟交易周报生成器
.DESCRIPTION
  读取每日快照/交易流水/绩效报告，生成HTML格式的模拟交易周报。
  包含：本周概况、净值曲线（组合 vs 沪深300）、交易清单、持仓明细、绩效指标、最大回撤标注。
.PARAMETER WeekEndDate
  周末日期 (yyyy-MM-dd)，默认取最新快照所在周的周五。
.PARAMETER OutDir
  输出目录，默认 模拟交易/周报/
.PARAMETER RootDir
  项目根目录
.EXAMPLE
  .\gen_weekly_report.ps1
  .\gen_weekly_report.ps1 -WeekEndDate "2026-05-22"
#>

[CmdletBinding()]
param(
    [string]$WeekEndDate = "",
    [string]$OutDir = "",
    [string]$RootDir = "C:\Users\34269\Documents\Claude\股票分析"
)

$ErrorActionPreference = "Stop"

# ============================================================
# PATHS
# ============================================================
$simDir        = Join-Path $RootDir "模拟交易"
$snapshotDir   = Join-Path $simDir "每日快照"
$reportDir     = if ($OutDir) { $OutDir } else { Join-Path $simDir "周报" }
$configFile    = Join-Path $simDir "sim_config.json"
$transFile     = Join-Path $simDir "持仓记录\transactions.csv"
$perfFile      = Join-Path $simDir "绩效报告\perf_summary.json"

# ============================================================
# HELPERS
# ============================================================
function Format-Num {
    param([double]$Value, [int]$Decimals = 2)
    return "{0:N$Decimals}" -f $Value
}

function Format-Pct {
    param([double]$Value, [int]$Decimals = 2)
    $sign = if ($Value -ge 0) { "+" } else { "" }
    return "$sign{0:N$Decimals}%" -f $Value
}

function Get-ColorClass {
    param([double]$Value)
    # 中国股市：红涨绿跌
    if ($Value -gt 0) { return "up" }
    if ($Value -lt 0) { return "down" }
    return "flat"
}

function Format-DateDisplay {
    param([string]$YyyyMmDd)
    if ($YyyyMmDd.Length -ne 8) { return $YyyyMmDd }
    return "$($YyyyMmDd.Substring(0,4))-$($YyyyMmDd.Substring(4,2))-$($YyyyMmDd.Substring(6,2))"
}

# ============================================================
# LOAD CONFIG
# ============================================================
if (-not (Test-Path $configFile)) {
    Write-Error "配置文件不存在: $configFile"
    exit 1
}
$config = Get-Content $configFile -Raw | ConvertFrom-Json
$initialCapital = [double]$config.InitialCapital
$benchmarkName  = $config.Benchmark.Name

# ============================================================
# LOAD SNAPSHOTS
# ============================================================
$snapshotFiles = Get-ChildItem $snapshotDir -Filter "snapshot_*.json" | Sort-Object Name
if ($snapshotFiles.Count -eq 0) {
    Write-Error "每日快照目录中没有找到 snapshot_*.json 文件: $snapshotDir"
    exit 1
}

$allSnapshots = @()
foreach ($f in $snapshotFiles) {
    try {
        $data = Get-Content $f.FullName -Raw | ConvertFrom-Json
        # 兼容两种字段命名: snapshot用 Date, perf_summary用 StartDate
        $snapDate = if ($data.Date) { $data.Date } elseif ($data.StartDate) { $data.StartDate } else { $null }
        if (-not $snapDate) {
            Write-Warning ("跳过无效快照（无日期字段）: " + $f.Name)
            continue
        }
        # 统一添加 Date 字段以便后续处理
        if (-not $data.Date) { $data | Add-Member -NotePropertyName "Date" -NotePropertyValue $snapDate -Force }
        $allSnapshots += $data
    } catch {
        Write-Warning ("跳过无法解析的快照: " + $f.Name + " - " + $_.Exception.Message)
    }
}

if ($allSnapshots.Count -eq 0) {
    Write-Error "没有可用的快照数据"
    exit 1
}

# Sort by date ascending
$allSnapshots = $allSnapshots | Sort-Object @{Expression={[int]$_.Date}}

$latestSnap = $allSnapshots[-1]
$latestDate = [datetime]::ParseExact($latestSnap.Date, "yyyyMMdd", $null)

# ============================================================
# DETERMINE WEEK RANGE
# ============================================================
if ($WeekEndDate) {
    $weekEnd = [datetime]::ParseExact($WeekEndDate, "yyyy-MM-dd", $null)
} else {
    # 取最新快照所在周的周五
    $dow = [int]$latestDate.DayOfWeek  # 0=Sun,1=Mon,...,6=Sat
    if ($dow -ge 1 -and $dow -le 5) {
        # 周一至周五：找当周周五
        $weekEnd = $latestDate.AddDays(5 - $dow)
    } else {
        # 周末：找上周五
        $addDays = @{0 = -2; 6 = -1}
        $weekEnd = $latestDate.AddDays($addDays[$dow])
    }
}

$weekStart = $weekEnd.AddDays(-4)  # 周一
$weekStartStr = $weekStart.ToString("yyyy-MM-dd")
$weekEndStr   = $weekEnd.ToString("yyyy-MM-dd")
$weekLabel    = "$weekStartStr 至 $weekEndStr"

# ISO week number
$isoWeek = ([System.Globalization.CultureInfo]::CurrentCulture.Calendar.GetWeekOfYear($weekEnd, [System.Globalization.CalendarWeekRule]::FirstFourDayWeek, [DayOfWeek]::Monday))
$weekLabelShort = "第${isoWeek}周 ($weekLabel)"

# ============================================================
# FILTER WEEKLY SNAPSHOTS
# ============================================================
$weekStartInt = [int]$weekStart.ToString("yyyyMMdd")
$weekEndInt   = [int]$weekEnd.ToString("yyyyMMdd")

$weekSnapshots = $allSnapshots | Where-Object {
    $d = [int]$_.Date
    $d -ge $weekStartInt -and $d -le $weekEndInt
}

if ($weekSnapshots.Count -eq 0) {
    Write-Warning "指定周期内无快照数据（${weekLabel}），使用全部数据进行计算"
    $weekSnapshots = $allSnapshots
}

# ============================================================
# LOAD TRANSACTIONS
# ============================================================
$allTransactions = @()
if (Test-Path $transFile) {
    try {
        # Try UTF-8 first, fall back to system default (GBK on Chinese Windows)
        $allTransactions = @(Import-Csv $transFile -Encoding UTF8 -ErrorAction Stop)
    } catch {
        try {
            Write-Warning "UTF-8读取交易流水失败，尝试系统默认编码"
            $allTransactions = @(Import-Csv $transFile -Encoding Default -ErrorAction Stop)
        } catch {
            Write-Warning "无法读取交易流水文件: $_"
            $allTransactions = @()
        }
    }
}

# Filter weekly transactions
$weekTransactions = $allTransactions | Where-Object {
    $_.date -and [int]$_.date -ge $weekStartInt -and [int]$_.date -le $weekEndInt
} | Sort-Object date

# ============================================================
# CALCULATE POSITIONS (from latest snapshot StockDetails)
# ============================================================
$currentPositions = @()
$totalStockValue = 0
$totalPosCost = 0

# Try StockDetails from latest weekly snapshot first
$posSourceSnap = $weekSnapshots[-1]
if ($posSourceSnap.StockDetails -and $posSourceSnap.StockDetails.Count -gt 0) {
    foreach ($sd in $posSourceSnap.StockDetails) {
        $shares    = [int]$sd.Shares
        $avgCost   = [double]$sd.AvgCost
        $curPrice  = [double]$sd.CurrentPrice
        $mktVal    = [Math]::Round($shares * $curPrice, 2)
        $cost      = [Math]::Round($shares * $avgCost, 2)
        $pnl       = if ($sd.UnrealizedPnL) { [double]$sd.UnrealizedPnL } else { $mktVal - $cost }
        $pnlPct    = if ($sd.UnrealizedPnLPct) { [double]$sd.UnrealizedPnLPct } else { if ($cost -gt 0) { ($mktVal / $cost - 1) * 100 } else { 0 } }

        $currentPositions += [PSCustomObject]@{
            Code      = $sd.Code
            Name      = $sd.Name
            Shares    = $shares
            AvgCost   = $avgCost
            TotalCost = $cost
            CurPrice  = $curPrice
            MktValue  = $mktVal
            UnrealizedPnL   = $pnl
            UnrealizedPnLPct = $pnlPct
        }
        $totalStockValue += $mktVal
        $totalPosCost += $cost
    }
} else {
    # Fallback: derive from transactions
    Write-Warning "快照无 StockDetails，从交易流水推导持仓（无市价信息）"
    $posHash = @{}
    if ($allTransactions.Count -gt 0) {
        foreach ($t in $allTransactions) {
            if (-not $t.date -or -not $t.code) { continue }
            $tDateInt = [int]$t.date
            if ($tDateInt -gt $weekEndInt) { continue }
            $code = $t.code.Trim()
            if (-not $posHash.ContainsKey($code)) {
                $posHash[$code] = @{ Code=$code; Name=if($t.name){$t.name.Trim()}else{$code}; Shares=0; TotalCost=0.0; TotalBuyQty=0 }
            }
            $p = $posHash[$code]
            $qty = [int]$t.shares; $cost = [Math]::Abs([double]$t.total_cost)
            if ($t.action -eq "BUY") { $p.Shares += $qty; $p.TotalCost += $cost; $p.TotalBuyQty += $qty }
            elseif ($t.action -eq "SELL") { $p.Shares -= $qty }
        }
    }
    foreach ($kv in $posHash.GetEnumerator()) {
        $p = $kv.Value
        if ($p.Shares -gt 0) {
            $avgCost = if ($p.TotalBuyQty -gt 0) { $p.TotalCost / $p.TotalBuyQty } else { 0 }
            $cost = [Math]::Round($avgCost * $p.Shares, 2)
            $currentPositions += [PSCustomObject]@{
                Code=$p.Code; Name=$p.Name; Shares=$p.Shares
                AvgCost=$avgCost; TotalCost=$cost
                CurPrice=0; MktValue=0; UnrealizedPnL=0; UnrealizedPnLPct=0
            }
            $totalPosCost += $cost
        }
    }
}
$currentPositions = $currentPositions | Sort-Object Code

# ============================================================
# CALCULATE WEEKLY METRICS
# ============================================================
$firstSnap = $weekSnapshots[0]
$lastSnap  = $weekSnapshots[-1]

$startNAV = [double]$firstSnap.TotalValue
$endNAV   = [double]$lastSnap.TotalValue
$weeklyReturn       = if ($startNAV -ne 0) { ($endNAV / $startNAV - 1) * 100 } else { 0 }
$cumulativeReturn   = [double]$lastSnap.TotalReturnPct

# Benchmark
$benchStart = [double]$firstSnap.Benchmark.CurrentValue
$benchEnd   = [double]$lastSnap.Benchmark.CurrentValue
$benchWeeklyReturn = if ($benchStart -ne 0) { ($benchEnd / $benchStart - 1) * 100 } else { 0 }
$benchCumulativeReturn = [double]$lastSnap.Benchmark.BenchmarkReturnPct

$excessReturn     = $weeklyReturn - $benchWeeklyReturn
$excessCumulative = $cumulativeReturn - $benchCumulativeReturn

# Max drawdown: calculate from full TotalValue series
$maxDD = 0
$maxDDDateRaw = $null
$runningMaxVal = -1e15
foreach ($snap in $allSnapshots) {
    $val = [double]$snap.TotalValue
    if ($val -gt $runningMaxVal) { $runningMaxVal = $val }
    $dd = if ($runningMaxVal -gt 0) { ($val - $runningMaxVal) / $runningMaxVal * 100 } else { 0 }
    if ($dd -lt $maxDD) { $maxDD = $dd; $maxDDDateRaw = $snap.Date }
}
if ($maxDD -eq 0) {
    $maxDDDate = "无"
    $maxDDStr  = "0.00%"
} else {
    $maxDDStr = "{0:N2}%" -f $maxDD
    $maxDDDate = if ($maxDDDateRaw) { Format-DateDisplay $maxDDDateRaw } else { "无" }
}

# Perf summary data
$perfTrades = 0
$perfWinRate = $null
$perfSharpe = $null
$perfInfoRatio = $null

if (Test-Path $perfFile) {
    try {
        $perfData = Get-Content $perfFile -Raw | ConvertFrom-Json
        $perfTrades     = if ($null -ne $perfData.TotalTrades) { [int]$perfData.TotalTrades } else { 0 }
        $perfWinRate    = if ($null -ne $perfData.WinRate) { [double]$perfData.WinRate } else { $null }
        # 兼容新旧结构：SharpeRatio 可能在顶层或 RiskMetrics 子对象中
        $perfSharpe     = if ($null -ne $perfData.SharpeRatio) { [double]$perfData.SharpeRatio } `
                     elseif ($perfData.RiskMetrics -and $null -ne $perfData.RiskMetrics.SharpeRatio) { [double]$perfData.RiskMetrics.SharpeRatio } `
                     else { $null }
        # 兼容新旧结构：InformationRatio 可能在顶层或 RiskMetrics 子对象中
        $perfInfoRatio  = if ($null -ne $perfData.InformationRatio) { [double]$perfData.InformationRatio } `
                     elseif ($perfData.RiskMetrics -and $null -ne $perfData.RiskMetrics.InformationRatio) { [double]$perfData.RiskMetrics.InformationRatio } `
                     else { $null }
    } catch {
        Write-Warning "无法读取绩效报告: $_"
    }
}

# ============================================================
# BUILD CHART DATA
# ============================================================
$chartLabels   = @()  # Display date strings for JS
$chartPortRet  = @()  # Portfolio cumulative return %
$chartBenchRet = @()  # Benchmark cumulative return %
$chartDrawdown = @()  # Drawdown series

$runningMaxVal = -1e15
foreach ($snap in $allSnapshots) {
    $dStr = $snap.Date
    $label = "$($dStr.Substring(0,4))-$($dStr.Substring(4,2))-$($dStr.Substring(6,2))"
    $chartLabels += "'$label'"

    $portRet = [Math]::Round([double]$snap.TotalReturnPct, 2)
    $benchRet = [Math]::Round([double]$snap.Benchmark.BenchmarkReturnPct, 2)
    $chartPortRet += $portRet
    $chartBenchRet += $benchRet

    # Compute drawdown from TotalValue
    $navVal = [double]$snap.TotalValue
    if ($navVal -gt $runningMaxVal) { $runningMaxVal = $navVal }
    $dd = if ($runningMaxVal -gt 0) { [Math]::Round(($navVal - $runningMaxVal) / $runningMaxVal * 100, 2) } else { 0 }
    $chartDrawdown += $dd
}

$datesJson    = "[" + ($chartLabels -join ",") + "]"
$portRetJson  = "[" + ($chartPortRet -join ",") + "]"
$benchRetJson = "[" + ($chartBenchRet -join ",") + "]"
$ddJson       = "[" + ($chartDrawdown -join ",") + "]"

# Find max drawdown index for annotation
$minDDVal  = 0
$minDDIdx  = -1
for ($i = 0; $i -lt $chartDrawdown.Count; $i++) {
    if ($chartDrawdown[$i] -lt $minDDVal) {
        $minDDVal = $chartDrawdown[$i]
        $minDDIdx = $i
    }
}

# ============================================================
# BUILD TABLES (HTML fragments)
# ============================================================

# --- Weekly Transactions Table ---
$transHtml = ""
if ($weekTransactions.Count -gt 0) {
    $transHtml += '<table class="tbl"><thead><tr>'
    $transHtml += '<th>日期</th><th>代码</th><th>名称</th><th>操作</th><th>价格</th><th>数量</th><th>金额</th><th>原因</th>'
    $transHtml += '</tr></thead><tbody>'
    foreach ($t in $weekTransactions) {
        $dateStr = Format-DateDisplay $t.date
        $priceStr = Format-Num ([double]$t.price) 2
        $sharesStr = [int]$t.shares
        $amountVal = [double]$t.amount
        $amountStr = Format-Num $amountVal 2
        $actionClass = if ($t.action -eq "BUY") { "buy" } else { "sell" }
        $actionLabel = if ($t.action -eq "BUY") { "买入" } else { "卖出" }
        $reason = if ($t.reason) { $t.reason } else { "-" }

        $transHtml += "<tr>"
        $transHtml += "<td>$dateStr</td>"
        $transHtml += "<td>$($t.code)</td>"
        $transHtml += "<td>$($t.name)</td>"
        $transHtml += "<td class='$actionClass'>$actionLabel</td>"
        $transHtml += "<td class='num'>$priceStr</td>"
        $transHtml += "<td class='num'>$sharesStr</td>"
        $transHtml += "<td class='num'>$amountStr</td>"
        $transHtml += "<td>$reason</td>"
        $transHtml += "</tr>"
    }
    $transHtml += '</tbody></table>'
} else {
    $transHtml = '<div class="empty-note">本周无交易记录</div>'
}

# --- Current Positions Table ---
$posHtml = ""
if ($currentPositions.Count -gt 0) {
    $hasMktData = ($currentPositions[0].CurPrice -and $currentPositions[0].CurPrice -gt 0)
    $posHtml += '<table class="tbl"><thead><tr>'
    $posHtml += '<th>代码</th><th>名称</th><th>持仓数量</th><th>均价</th><th>持仓成本</th>'
    if ($hasMktData) {
        $posHtml += '<th>现价</th><th>市值</th><th>浮动盈亏</th><th>收益率</th>'
    }
    $posHtml += '</tr></thead><tbody>'

    $totalMktVal = 0
    $totalPnl = 0
    foreach ($p in $currentPositions) {
        $avgCostStr = Format-Num $p.AvgCost 2
        $totalCostStr = Format-Num $p.TotalCost 2
        $posHtml += '<tr>'
        $posHtml += "<td>$($p.Code)</td>"
        $posHtml += "<td>$($p.Name)</td>"
        $posHtml += "<td class='num'>$($p.Shares)</td>"
        $posHtml += "<td class='num'>$avgCostStr</td>"
        $posHtml += "<td class='num'>$totalCostStr</td>"
        if ($hasMktData) {
            $curPxStr = Format-Num $p.CurPrice 2
            $mktValStr = Format-Num $p.MktValue 2
            $pnlStr = Format-Num $p.UnrealizedPnL 2
            $pnlPctStr = Format-Pct $p.UnrealizedPnLPct
            $pnlClass = Get-ColorClass $p.UnrealizedPnL
            $posHtml += "<td class='num'>$curPxStr</td>"
            $posHtml += "<td class='num'>$mktValStr</td>"
            $posHtml += "<td class='num $pnlClass'>$pnlStr</td>"
            $posHtml += "<td class='num $pnlClass'>$pnlPctStr</td>"
            $totalMktVal += $p.MktValue
            $totalPnl += $p.UnrealizedPnL
        }
        $posHtml += '</tr>'
    }

    if ($hasMktData) {
        # Summary row
        $cashVal = if ($posSourceSnap.Cash) { [double]$posSourceSnap.Cash } else { 0 }
        $totalMktStr = Format-Num $totalMktVal 2
        $totalPnlStr = Format-Num $totalPnl 2
        $totalPnlClass = Get-ColorClass $totalPnl
        $cashStr = Format-Num $cashVal 2
        $posHtml += '<tr class="summary-row">'
        $posHtml += "<td colspan='2'>合计</td>"
        $posHtml += "<td class='num'>-</td><td class='num'>-</td>"
        $posHtml += "<td class='num'>$(Format-Num $totalPosCost 2)</td>"
        $posHtml += "<td class='num'>-</td>"
        $posHtml += "<td class='num'>$totalMktStr</td>"
        $posHtml += "<td class='num $totalPnlClass'>$totalPnlStr</td>"
        $posHtml += "<td class='num $totalPnlClass'>$(Format-Pct $(if($totalPosCost -gt 0){$totalPnl/$totalPosCost*100}else{0}))</td>"
        $posHtml += '</tr>'
        $posHtml += '<tr class="summary-row cash-row"><td colspan="9">可用现金：' + $cashStr + ' ｜ 组合总值：' + (Format-Num $endNAV 2) + ' ｜ 总仓位：' + (Format-Num ($totalMktVal / $endNAV * 100) 1) + '%</td></tr>'
    }
    $posHtml += '</tbody></table>'
} else {
    $posHtml = '<div class="empty-note">当前无持仓</div>'
}

# --- Performance Metrics Table ---
$perfHtml = '<table class="tbl perf-tbl"><tbody>'
$perfHtml += "<tr><td>起始净值</td><td class='num'>" + (Format-Num $startNAV 2) + "</td></tr>"
$perfHtml += "<tr><td>期末净值</td><td class='num'>" + (Format-Num $endNAV 2) + "</td></tr>"
$perfHtml += "<tr><td>期初沪深300</td><td class='num'>" + (Format-Num $benchStart 2) + "</td></tr>"
$perfHtml += "<tr><td>期末沪深300</td><td class='num'>" + (Format-Num $benchEnd 2) + "</td></tr>"

$wrClass = Get-ColorClass $weeklyReturn
$perfHtml += "<tr><td>周收益率</td><td class='num $wrClass'>" + (Format-Pct $weeklyReturn) + "</td></tr>"

$bwClass = Get-ColorClass $benchWeeklyReturn
$perfHtml += "<tr><td>沪深300周收益</td><td class='num $bwClass'>" + (Format-Pct $benchWeeklyReturn) + "</td></tr>"

$exClass = Get-ColorClass $excessReturn
$perfHtml += "<tr><td>超额周收益</td><td class='num $exClass'>" + (Format-Pct $excessReturn) + "</td></tr>"

$crClass = Get-ColorClass $cumulativeReturn
$perfHtml += "<tr><td>累计收益率</td><td class='num $crClass'>" + (Format-Pct $cumulativeReturn) + "</td></tr>"

$bcClass = Get-ColorClass $benchCumulativeReturn
$perfHtml += "<tr><td>沪深300累计收益</td><td class='num $bcClass'>" + (Format-Pct $benchCumulativeReturn) + "</td></tr>"

$ecClass = Get-ColorClass $excessCumulative
$perfHtml += "<tr><td>超额累计收益</td><td class='num $ecClass'>" + (Format-Pct $excessCumulative) + "</td></tr>"

$perfHtml += "<tr><td>最大回撤</td><td class='num down'>$maxDDStr</td></tr>"
$perfHtml += "<tr><td>最大回撤日期</td><td>$maxDDDate</td></tr>"
$perfHtml += "<tr><td>初始资金</td><td class='num'>" + (Format-Num $initialCapital 0) + "</td></tr>"

$wtStr = if ($null -ne $perfWinRate) { (Format-Pct $perfWinRate) } else { "N/A（暂无平仓交易）" }
$perfHtml += "<tr><td>胜率（平仓）</td><td>$wtStr</td></tr>"
$perfHtml += "<tr><td>总交易次数（含持仓）</td><td class='num'>" + ($allTransactions.Count) + "</td></tr>"

$sharpeStr = if ($null -ne $perfSharpe) { (Format-Num $perfSharpe 2) } else { "N/A（数据不足）" }
$perfHtml += "<tr><td>夏普比率</td><td class='num'>$sharpeStr</td></tr>"

$infoStr = if ($null -ne $perfInfoRatio) { (Format-Num $perfInfoRatio 2) } else { "N/A（数据不足）" }
$perfHtml += "<tr><td>信息比率</td><td class='num'>$infoStr</td></tr>"

$perfHtml += '</tbody></table>'

# ============================================================
# BUILD SUMMARY CARDS
# ============================================================
$wrFormatted = Format-Pct $weeklyReturn
$wrCardClass = Get-ColorClass $weeklyReturn
$navFormatted = Format-Num $endNAV 2
$crFormatted = Format-Pct $cumulativeReturn
$crCardClass = Get-ColorClass $cumulativeReturn
$erFormatted = Format-Pct $excessReturn
$erCardClass = Get-ColorClass $excessReturn

# ============================================================
# HTML TEMPLATE
# ============================================================
$generatedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

$html = @'
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>铁律量化 | 模拟交易周报 - __WEEK_LABEL__</title>
    <script src="https://cdn.plot.ly/plotly-2.29.1.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans SC", sans-serif;
            background: #f4f5f7;
            color: #333;
            padding: 24px;
            max-width: 1200px;
            margin: 0 auto;
        }
        .header {
            background: linear-gradient(135deg, #1a1a2e, #16213e);
            color: #fff;
            padding: 36px 44px;
            border-radius: 12px;
            margin-bottom: 22px;
        }
        .header h1 { font-size: 28px; font-weight: 900; margin-bottom: 8px; }
        .header .sub { font-size: 16px; opacity: 0.85; display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; }
        .header .sub span { font-size: 14px; }

        .cards { display: flex; gap: 16px; margin-bottom: 22px; flex-wrap: wrap; }
        .card {
            flex: 1; min-width: 180px; background: #fff; border-radius: 10px;
            padding: 20px 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);
            border-left: 4px solid #1a1a2e;
        }
        .card .card-label { font-size: 13px; color: #888; margin-bottom: 6px; }
        .card .card-value { font-size: 26px; font-weight: 700; }
        .card .card-value.up    { color: #e74c3c; }
        .card .card-value.down  { color: #27ae60; }
        .card .card-value.flat  { color: #666; }
        .card:first-child { border-left-color: #e74c3c; }

        .section {
            background: #fff; border-radius: 10px; padding: 24px 28px;
            margin-bottom: 22px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        }
        .section h2 {
            font-size: 18px; font-weight: 700; color: #1a1a2e;
            margin-bottom: 16px; padding-bottom: 8px;
            border-bottom: 2px solid #f0f0f0;
        }

        #navChart { width: 100%; height: 420px; }

        .tbl { width: 100%; border-collapse: collapse; font-size: 14px; }
        .tbl thead th {
            background: #1a1a2e; color: #fff; padding: 10px 12px;
            text-align: left; font-weight: 600; white-space: nowrap;
        }
        .tbl tbody td { padding: 9px 12px; border-bottom: 1px solid #eee; }
        .tbl tbody tr:nth-child(even) { background: #f8f9fb; }
        .tbl tbody tr:hover { background: #eef1f7; }
        .tbl .num { text-align: right; font-variant-numeric: tabular-nums; }
        .tbl .buy  { color: #e74c3c; font-weight: 600; }
        .tbl .sell { color: #27ae60; font-weight: 600; }
        .tbl .up   { color: #e74c3c; font-weight: 600; }
        .tbl .down { color: #27ae60; font-weight: 600; }
        .tbl .flat { color: #666; }

        .perf-tbl td:first-child { font-weight: 600; color: #555; width: 180px; }

        .empty-note { text-align: center; color: #999; padding: 32px 0; font-size: 15px; }

        .summary-row td { font-weight: 700; background: #f0f2f6 !important; border-top: 2px solid #ddd; }
        .cash-row td { font-weight: 400; font-size: 13px; color: #666; background: #f5f6f8 !important; }

        .footer {
            text-align: center; font-size: 12px; color: #999;
            padding: 20px; line-height: 1.8;
        }

        @media (max-width: 640px) {
            body { padding: 12px; }
            .header { padding: 24px 20px; }
            .header h1 { font-size: 22px; }
            .card { min-width: 140px; }
            .card .card-value { font-size: 22px; }
            .section { padding: 16px; }
            .tbl { font-size: 12px; }
            .tbl thead th, .tbl tbody td { padding: 6px 8px; }
        }
    </style>
</head>
<body>

<div class="header">
    <h1>铁律量化 | 模拟交易周报</h1>
    <div class="sub">
        <span>报告周期：__WEEK_LABEL__</span>
        <span>生成时间：__GENERATED_AT__</span>
    </div>
</div>

<div class="cards">
    <div class="card">
        <div class="card-label">周收益率</div>
        <div class="card-value __WR_CLASS__">__WEEKLY_RETURN__</div>
    </div>
    <div class="card">
        <div class="card-label">组合净值</div>
        <div class="card-value">__END_NAV__</div>
    </div>
    <div class="card">
        <div class="card-label">累计收益率</div>
        <div class="card-value __CR_CLASS__">__CUMULATIVE_RETURN__</div>
    </div>
    <div class="card">
        <div class="card-label">超额收益（周）</div>
        <div class="card-value __ER_CLASS__">__EXCESS_RETURN__</div>
    </div>
</div>

<div class="section">
    <h2>净值走势</h2>
    <div id="navChart"></div>
</div>

<div class="section">
    <h2>本周交易清单</h2>
    __TRANSACTIONS_TABLE__
</div>

<div class="section">
    <h2>当前持仓明细</h2>
    __POSITIONS_TABLE__
</div>

<div class="section">
    <h2>绩效指标汇总</h2>
    __PERF_TABLE__
</div>

<div class="footer">
    <p>免责声明：本报告由铁律量化模拟交易系统自动生成，仅供参考，不构成任何投资建议。</p>
    <p>数据来源：模拟交易引擎 [S] &mdash; 历史模拟数据，实盘表现可能不同。</p>
    <p>铁律量化 &copy; 2026</p>
</div>

<script>
(function() {
    var dates = __CHART_DATES__;
    var portfolioReturns = __CHART_PORT_RETURNS__;
    var benchmarkReturns = __CHART_BENCH_RETURNS__;
    var drawdowns = __CHART_DD__;
    var maxDDIdx = __MAX_DD_IDX__;
    var maxDDVal = __MAX_DD_VAL__;
    var maxDDDate = '__MAX_DD_DATE__';

    // Determine marker mode based on data count
    var mode = dates.length > 1 ? 'lines+markers' : 'markers';

    // Portfolio trace
    var trace1 = {
        x: dates,
        y: portfolioReturns,
        type: 'scatter',
        mode: mode,
        name: '组合收益',
        line: { color: '#e74c3c', width: 2.5 },
        marker: { color: '#e74c3c', size: 6 },
        hovertemplate: '%{x}<br>组合收益: %{y:.2f}%<extra></extra>'
    };

    // Benchmark trace
    var trace2 = {
        x: dates,
        y: benchmarkReturns,
        type: 'scatter',
        mode: mode,
        name: '沪深300',
        line: { color: '#27ae60', width: 2.5, dash: 'dot' },
        marker: { color: '#27ae60', size: 6 },
        hovertemplate: '%{x}<br>沪深300: %{y:.2f}%<extra></extra>'
    };

    // Drawdown trace (as filled area)
    var trace3 = {
        x: dates,
        y: drawdowns,
        type: 'scatter',
        mode: 'lines',
        name: '回撤',
        line: { color: 'rgba(231,76,60,0.3)', width: 0 },
        fill: 'tozeroy',
        fillcolor: 'rgba(231,76,60,0.08)',
        hovertemplate: '%{x}<br>回撤: %{y:.2f}%<extra></extra>',
        yaxis: 'y2',
        showlegend: false
    };

    var data = [trace1, trace2, trace3];

    // Annotations
    var annotations = [];
    if (maxDDIdx >= 0 && maxDDVal < -0.5 && dates.length > 1) {
        annotations.push({
            x: dates[maxDDIdx],
            y: portfolioReturns[maxDDIdx],
            text: '最大回撤 ' + Math.abs(maxDDVal).toFixed(2) + '%',
            showarrow: true,
            arrowhead: 2,
            arrowsize: 1,
            arrowwidth: 1.5,
            arrowcolor: '#e74c3c',
            ax: 40,
            ay: -50,
            font: { color: '#e74c3c', size: 12 },
            bgcolor: 'rgba(255,255,255,0.85)',
            bordercolor: '#e74c3c',
            borderwidth: 1,
            borderpad: 4
        });
    }

    var layout = {
        title: {
            text: '组合净值走势（累计收益率 %）',
            font: { size: 16, color: '#1a1a2e' }
        },
        xaxis: {
            title: '日期',
            type: 'date',
            tickformat: '%m-%d',
            gridcolor: '#eee',
            zeroline: false
        },
        yaxis: {
            title: '收益率 (%)',
            tickformat: '.2f',
            gridcolor: '#eee',
            zeroline: true,
            zerolinecolor: '#ddd',
            zerolinewidth: 1
        },
        yaxis2: {
            title: '回撤 (%)',
            overlaying: 'y',
            side: 'right',
            tickformat: '.1f',
            showgrid: false,
            zeroline: false
        },
        hovermode: 'x unified',
        hoverlabel: {
            bgcolor: '#fff',
            bordercolor: '#ccc',
            font: { size: 12 }
        },
        legend: {
            orientation: 'h',
            y: 1.12,
            x: 0,
            font: { size: 13 }
        },
        margin: { l: 60, r: 60, t: 50, b: 50 },
        paper_bgcolor: '#fff',
        plot_bgcolor: '#fff',
        shapes: [],
        annotations: annotations
    };

    // Add range slider
    if (dates.length > 5) {
        layout.xaxis.rangeslider = { visible: true, thickness: 0.06 };
    }

    // Drawdown shape annotation (shaded region from peak to trough)
    if (maxDDIdx >= 0 && maxDDVal < -0.5 && dates.length > 2) {
        // Find peak before max drawdown
        var peakIdx = 0;
        var peakVal = portfolioReturns[0];
        for (var i = 1; i <= maxDDIdx; i++) {
            if (portfolioReturns[i] > peakVal) {
                peakVal = portfolioReturns[i];
                peakIdx = i;
            }
        }
        if (peakIdx < maxDDIdx) {
            layout.shapes.push({
                type: 'rect',
                x0: dates[peakIdx],
                y0: Math.min(portfolioReturns[peakIdx], portfolioReturns[maxDDIdx]) - 1,
                x1: dates[maxDDIdx],
                y1: Math.max(portfolioReturns[peakIdx], portfolioReturns[maxDDIdx]) + 1,
                fillcolor: 'rgba(231,76,60,0.06)',
                line: { width: 0 },
                layer: 'below'
            });
        }
    }

    Plotly.newPlot('navChart', data, layout, {
        responsive: true,
        displaylogo: false,
        modeBarButtonsToRemove: ['lasso2d', 'select2d', 'sendDataToCloud']
    });
})();
</script>

</body>
</html>
'@

# ============================================================
# REPLACE PLACEHOLDERS
# ============================================================
$html = $html.Replace('__WEEK_LABEL__',       $weekLabelShort)
$html = $html.Replace('__GENERATED_AT__',      $generatedAt)
$html = $html.Replace('__WEEKLY_RETURN__',     $wrFormatted)
$html = $html.Replace('__WR_CLASS__',           $wrCardClass)
$html = $html.Replace('__END_NAV__',           $navFormatted)
$html = $html.Replace('__CUMULATIVE_RETURN__', $crFormatted)
$html = $html.Replace('__CR_CLASS__',           $crCardClass)
$html = $html.Replace('__EXCESS_RETURN__',     $erFormatted)
$html = $html.Replace('__ER_CLASS__',           $erCardClass)
$html = $html.Replace('__TRANSACTIONS_TABLE__', $transHtml)
$html = $html.Replace('__POSITIONS_TABLE__',    $posHtml)
$html = $html.Replace('__PERF_TABLE__',         $perfHtml)
$html = $html.Replace('__CHART_DATES__',        $datesJson)
$html = $html.Replace('__CHART_PORT_RETURNS__', $portRetJson)
$html = $html.Replace('__CHART_BENCH_RETURNS__',$benchRetJson)
$html = $html.Replace('__CHART_DD__',           $ddJson)
$html = $html.Replace('__MAX_DD_IDX__',         $minDDIdx.ToString())
$html = $html.Replace('__MAX_DD_VAL__',         $minDDVal.ToString('0.00', [cultureinfo]::CurrentCulture))
$maxDDDateStr = if ($minDDIdx -ge 0) { $chartLabels[$minDDIdx] -replace "'","" } else { "" }
$html = $html.Replace('__MAX_DD_DATE__',        $maxDDDateStr)

# ============================================================
# WRITE HTML FILE
# ============================================================
if (-not (Test-Path $reportDir)) {
    New-Item -ItemType Directory -Path $reportDir -Force | Out-Null
}

$weekEndFileStr = $weekEnd.ToString("yyyyMMdd")
$reportFile = Join-Path $reportDir "模拟交易周报_${weekEndFileStr}.html"

try {
    Set-Content -Path $reportFile -Value $html -Encoding UTF8
} catch {
    Write-Error "写入文件失败: $_"
    exit 1
}

# ============================================================
# OUTPUT SUMMARY
# ============================================================
Write-Output ""
Write-Output "==========================================="
Write-Output "  模拟交易周报生成完毕"
Write-Output "==========================================="
Write-Output "  报告周期   : $weekLabelShort"
Write-Output "  起始净值   : $(Format-Num $startNAV 2)"
Write-Output "  期末净值   : $(Format-Num $endNAV 2)"
Write-Output "  周收益率   : $(Format-Pct $weeklyReturn)"
Write-Output "  累计收益率 : $(Format-Pct $cumulativeReturn)"
Write-Output "  沪深300周   : $(Format-Pct $benchWeeklyReturn)"
Write-Output "  最大回撤   : $maxDDStr ($maxDDDate)"
Write-Output "  本周交易   : $($weekTransactions.Count) 笔"
Write-Output "  当前持仓   : $($currentPositions.Count) 只"
Write-Output "  输出文件   : $reportFile"
Write-Output "==========================================="
Write-Output ""
