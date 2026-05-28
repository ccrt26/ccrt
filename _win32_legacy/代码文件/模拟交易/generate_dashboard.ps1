# generate_dashboard.ps1 v1.0
# Pure ASCII script - all i18n strings in template file
[CmdletBinding()]
param(
    [string]$Date = (Get-Date -Format "yyyyMMdd"),
    [string]$RootDir = ""
)
. "$PSScriptRoot/../lib/init_encoding.ps1"

$ErrorActionPreference = "Continue"

# ---- Resolve paths ----
if (-not $RootDir) {
    if ($PSScriptRoot) {
        $RootDir = (Resolve-Path "$PSScriptRoot/../..").Path
    }
}
if (-not $RootDir) {
    Write-Host "ERROR: Cannot resolve RootDir"
    exit 1
}

$TemplateFile = Join-Path $PSScriptRoot "dashboard_template.html"
$OutDir = Join-Path $RootDir "模拟交易\展示"
$OutFile = Join-Path $OutDir "持仓仪表盘.html"

if (-not (Test-Path $TemplateFile)) {
    Write-Host "ERROR: Template not found: $TemplateFile"
    exit 1
}
if (-not (Test-Path $OutDir)) {
    New-Item $OutDir -ItemType Directory -Force | Out-Null
}

$KeyPosFile = Join-Path $RootDir "历史数据\00_核心交易\positions.json"
$PerfFile   = Join-Path $RootDir "历史数据\00_核心交易\perf_summary.json"
$TxFile     = Join-Path $RootDir "历史数据\00_核心交易\transactions.csv"
$DailyPosFile = Join-Path $RootDir "模拟交易\每日荐股赛道\持仓记录\positions_daily.json"
$DailyTxFile  = Join-Path $RootDir "模拟交易\每日荐股赛道\持仓记录\transactions.csv"
$SnapshotDir  = Join-Path $RootDir "历史数据\01_交易快照"
$InstFile     = Join-Path $RootDir "模拟交易\交易决策\交易指令_${Date}.json"

# ---- Read template ----
$html = [System.IO.File]::ReadAllText($TemplateFile)

# ---- Read positions ----
$positions = @{}
$cash = 0.0
$stockVal = 0.0

function Add-Positions {
    param($File, $Label)
    if (-not (Test-Path $File)) { return }
    try {
        $data = Get-Content $File -Raw -Encoding UTF8 | ConvertFrom-Json
        $script:cash += $data.Cash
        if ($data.Positions) {
            $data.Positions.PSObject.Properties | ForEach-Object {
                $p = $_.Value
                $mv = $p.CurrentPrice * $p.Shares
                $script:stockVal += $mv
                $script:positions[$p.Code] = [PSCustomObject]@{
                    Code = $p.Code; Name = $p.Name; Shares = [int]$p.Shares
                    AvgCost = [double]$p.AvgCost; CurrentPrice = [double]$p.CurrentPrice
                    EntryDate = if ($p.EntryDate) { $p.EntryDate } else { "" }
                    UnrealizedPnL = [double]$p.UnrealizedPnL
                    UnrealizedPnLPct = [double]$p.UnrealizedPnLPct
                    Track = $Label
                }
            }
        }
    } catch {
        Write-Host "WARN: Position read error: $File"
    }
}
Add-Positions -File $KeyPosFile -Label "K"
Add-Positions -File $DailyPosFile -Label "D"

# ---- Read perf ----
$perf = $null
if (Test-Path $PerfFile) {
    try { $perf = Get-Content $PerfFile -Raw -Encoding UTF8 | ConvertFrom-Json } catch {}
}

# ---- Read transactions ----
$transactions = @()
function Add-Transactions {
    param($File)
    if (-not (Test-Path $File)) { return }
    try {
        Import-Csv $File -Encoding UTF8 | ForEach-Object {
            $src = if ($_.source) { $_.source } else { "auto" }
            $script:transactions += [PSCustomObject]@{
                date = $_.date; code = $_.code; name = $_.name; action = $_.action
                price = [double]$_.price; shares = [int]$_.shares
                amount = [double]$_.amount; total_cost = [double]$_.total_cost
                reason = $_.reason; source = $src
            }
        }
    } catch {}
}
Add-Transactions $TxFile
Add-Transactions $DailyTxFile

# ---- Read snapshots ----
$snapshots = @()
if (Test-Path $SnapshotDir) {
    Get-ChildItem $SnapshotDir -Filter "snapshot_*.json" | Sort-Object Name | ForEach-Object {
        try {
            $s = Get-Content $_.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
            $snapshots += [PSCustomObject]@{ Date = $s.Date; TotalValue = [double]$s.TotalValue; TotalReturnPct = [double]$s.TotalReturnPct }
        } catch {}
    }
}

# ---- Read pending instructions ----
$pending = @()
if (Test-Path $InstFile) {
    try {
        $inst = Get-Content $InstFile -Raw -Encoding UTF8 | ConvertFrom-Json
        foreach ($d in $inst.decisions) {
            if ($d.status -eq "pending") {
                $pending += [PSCustomObject]@{ action = $d.action; code = $d.code; name = $d.name; shares = [int]$d.shares; reason = $d.reason; priority = $d.priority }
            }
        }
    } catch {}
}

# ---- Compute values ----
$totalVal  = if ($perf) { $perf.CurrentValue } else { $cash + $stockVal }
$totalRet  = if ($perf) { $perf.TotalReturnPct } else { 0 }
$maxDD     = if ($perf) { $perf.MaxDrawdown } else { 0 }
$peakVal   = if ($perf) { $perf.PeakValue } else { $totalVal }
$numTrades = if ($perf) { $perf.TotalTrades } else { 0 }
$wrVal     = if ($perf -and $perf.WinRate -ne $null) { [Math]::Round($perf.WinRate * 100, 0) } else { -1 }

# Benchmark
$bmN = if ($perf -and $perf.Benchmark -and $perf.Benchmark.Name) { $perf.Benchmark.Name } else { "--" }
$bmC = if ($perf -and $perf.Benchmark -and $perf.Benchmark.Code) { $perf.Benchmark.Code } else { "--" }
$bmI = if ($perf -and $perf.Benchmark.InitialValue) { $perf.Benchmark.InitialValue } else { 0 }
$bmR = if ($perf -and $perf.Benchmark.BenchmarkReturnPct) { [Math]::Round($perf.Benchmark.BenchmarkReturnPct, 2) } else { 0 }
$bmE = if ($perf -and $perf.Benchmark.ExcessReturnPct) { [Math]::Round($perf.Benchmark.ExcessReturnPct, 2) } else { 0 }

# Risk
$rDD   = if ($perf -and $perf.RiskMetrics.CurrentDrawdown) { $perf.RiskMetrics.CurrentDrawdown } else { 0 }
$rSL   = if ($perf -and $perf.RiskMetrics.AvgStopLossDistance) { [Math]::Round($perf.RiskMetrics.AvgStopLossDistance, 1) } else { 0 }
$rCons = if ($perf -and $perf.RiskMetrics.ConsecutiveLosses) { $perf.RiskMetrics.ConsecutiveLosses } else { 0 }
$rAlrt = if ($perf -and $perf.RiskMetrics.IsDrawdownAlert) { 1 } else { 0 }

# ---- Format labels ----
$genTime = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$retSign = if ($totalRet -ge 0) { "+" } else { "" }
$winLbl = if ($wrVal -ge 0) { "$wrVal% SR" } else { "HOLD" }
$bmExcCls = if ($bmE -ge 0) { "pnl-up" } else { "pnl-down" }
$alertTxt = if ($rAlrt -eq 1) { "WARN" } else { "OK" }

# ---- Build JSON embed strings ----
function Esc-Json { param($S) return ($S -replace '\\','\\' -replace '"','\"' -replace "`n",'\n' -replace "`r",'') }

$posJson = "{"
$first = $true
foreach ($kv in $positions.GetEnumerator()) {
    $p = $kv.Value
    if (-not $first) { $posJson += "," }; $first = $false
    $nameEsc = Esc-Json $p.Name
    $edEsc = Esc-Json $p.EntryDate
    $trackEsc = Esc-Json $p.Track
    $posJson += """$($p.Code)"":{""Code"":""$($p.Code)"",""Name"":""$nameEsc"",""Shares"":$($p.Shares),""AvgCost"":$($p.AvgCost),""CurrentPrice"":$($p.CurrentPrice),""EntryDate"":""$edEsc"",""UnrealizedPnL"":$($p.UnrealizedPnL),""UnrealizedPnLPct"":$($p.UnrealizedPnLPct),""Track"":""$trackEsc""}"
}
$posJson += "}"

$perfJson = if ($perf) { ($perf | ConvertTo-Json -Depth 6 -Compress) } else { "null" }

$txParts = @()
foreach ($t in $transactions) {
    $nm = Esc-Json $t.name
    $rsn = Esc-Json $t.reason
    $txParts += "{date:""$($t.date)"",code:""$($t.code)"",name:""$nm"",action:""$($t.action)"",price:$($t.price),shares:$($t.shares),amount:$($t.amount),total_cost:$($t.total_cost),reason:""$rsn"",source:""$($t.source)""}"
}
$txJson = "[" + ($txParts -join ",") + "]"

$pendParts = @()
foreach ($p in $pending) {
    $nm = Esc-Json $p.name; $rsn = Esc-Json $p.reason
    $pendParts += "{action:""$($p.action)"",code:""$($p.code)"",name:""$nm"",shares:$($p.shares),reason:""$rsn"",priority:""$($p.priority)""}"
}
$pendJson = "[" + ($pendParts -join ",") + "]"

$snapParts = @()
foreach ($s in $snapshots) {
    $snapParts += "{date:""$($s.Date)"",value:$($s.TotalValue),ret:$($s.TotalReturnPct)}"
}
$snapJson = "[" + ($snapParts -join ",") + "]"

# ---- Format numbers ----
function Fmt-Num($n) { return [Math]::Round($n, 2).ToString("N2") }
function Fmt-Pct($n, $m) { return [Math]::Round($n / [Math]::Max($m, 1) * 100, 1).ToString() + "%" }

$navStr = Fmt-Num $totalVal
$cashStr = Fmt-Num $cash
$stockStr = Fmt-Num $stockVal
$peakStr = Fmt-Num $peakVal
$cashPct = Fmt-Pct $cash $totalVal
$stockPct = Fmt-Pct $stockVal $totalVal

# ---- Replace placeholders ----
$html = $html.Replace("__GEN_TIME__", $genTime)
$html = $html.Replace("__NAV__", "Y" + $navStr)
$html = $html.Replace("__CASH__", "Y" + $cashStr)
$html = $html.Replace("__CASH_PCT__", $cashPct)
$html = $html.Replace("__STOCK_VAL_VAL__", [Math]::Round($stockVal, 2).ToString("F2"))
$html = $html.Replace("__STOCK_VAL__", "Y" + $stockStr)
$html = $html.Replace("__POS_COUNT__", $positions.Count.ToString())
$html = $html.Replace("__STOCK_PCT__", $stockPct)
$html = $html.Replace("__MAXDD__", "$maxDD%")
$html = $html.Replace("__PEAK__", "Y" + $peakStr)
$html = $html.Replace("__TOTAL_TRADES__", $numTrades.ToString())
$html = $html.Replace("__WINRATE__", $winLbl)

$html = $html.Replace("__RETURN__", "$retSign$totalRet%")
$html = $html.Replace("__BM_NAME__", $bmN)
$html = $html.Replace("__BM_CODE__", $bmC)
$html = $html.Replace("__BM_RET__", "+$bmR%")
$html = $html.Replace("__BM_EXCESS_CLS__", $bmExcCls)
$html = $html.Replace("__BM_EXCESS__", "$bmE%")
$html = $html.Replace("__BM_INIT__", $bmI.ToString())

$html = $html.Replace("__RISK_CURDD__", "$rDD%")
$html = $html.Replace("__RISK_AVGSL__", "$rSL%")
$html = $html.Replace("__RISK_CONSEC__", $rCons.ToString())
$html = $html.Replace("__ALERT__", $alertTxt)

$html = $html.Replace("__CASH_VAL__", [Math]::Round($cash, 2).ToString("F2"))

$html = $html.Replace("__POS_JSON__", $posJson)
$html = $html.Replace("__PERF_JSON__", $perfJson)
$html = $html.Replace("__TX_JSON__", $txJson)
$html = $html.Replace("__PENDING_JSON__", $pendJson)
$html = $html.Replace("__SNAP_JSON__", $snapJson)

# ---- Write output ----
[System.IO.File]::WriteAllText($OutFile, $html, [System.Text.UTF8Encoding]::new($false))
Write-Host "[DONE] Dashboard: $OutFile"
Write-Host "  NAV=$totalVal | Pos=$($positions.Count) | Tx=$($transactions.Count)"
