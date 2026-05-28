<#
.SYNOPSIS
    Daily Recommendation Simulation Trading Engine v1.0
.DESCRIPTION
    Broad-spectrum simulation trading based on daily stock recommendations.
    Runs at 09:35 daily, outputs transaction log, position snapshot, performance report.
.PARAMETER Date
    Trading date (yyyyMMdd), default today
.PARAMETER DataFile
    Path to data_scored.json
.PARAMETER RootDir
    Project root directory
.PARAMETER DryRun
    Dry-run mode: log only, no file writes
#>

[CmdletBinding()]
param(
    [string]$Date = (Get-Date -Format "yyyyMMdd"),
    [string]$DataFile = "",
    [string]$RootDir = "",
    [switch]$DryRun = $false,
    [switch]$Force = $false,
    [string]$InstructionFile = ""
)

if (-not $RootDir) {
    if ($PSScriptRoot) {
        $RootDir = (Resolve-Path "$PSScriptRoot/../../..").Path
    } else {
        $RootDir = "C:\Users\34269\Documents\Claude\股票分析"
    }
}

$simDir = Join-Path $RootDir "模拟交易"
$sharedDir = Join-Path $simDir "共享模块"
$trackDir = Join-Path $simDir "每日荐股赛道"
$configFile = Join-Path $trackDir "sim_config_daily.json"
$positionsFile = Join-Path $trackDir "持仓记录/positions_daily.json"
$txnFile = Join-Path $trackDir "持仓记录/transactions_daily.csv"
$snapshotFile = Join-Path $trackDir "每日快照/snapshot_daily_${Date}.json"
$perfFile = Join-Path $trackDir "绩效报告/perf_summary_daily.json"
$logDir = Join-Path $trackDir "日志"
$cacheFile = Join-Path $simDir "quotes_cache.json"

if (-not $DryRun -and -not (Test-Path $logDir)) { New-Item $logDir -ItemType Directory -Force | Out-Null }

. (Join-Path $sharedDir "quote_engine.ps1")
. (Join-Path $sharedDir "trade_utils.ps1")
. (Join-Path $sharedDir "risk_framework.ps1")

$logLines = @()
function Write-Log {
    param([string]$Msg, [string]$Level = "INFO")
    $line = "[$Level] $Msg"
    $script:logLines += $line
    Write-Output $line
}

Write-Log "===== Daily Rec Sim Engine v1.0 | Date ${Date} ====="
if ($DryRun) { Write-Log "[DRY RUN MODE]" "WARN" }

# Step 0: Trading day check
if (-not (Test-IsTradingDay -Date $Date)) {
    Write-Log "Non-trading day, skip"
    if (-not $DryRun) { exit 0 }
}

# Time check: 09:45 cutoff
$currentTime = Get-Date
$cutoffTime = Get-Date -Hour 9 -Minute 45 -Second 0
$skipOpenNewPositions = $false
if (-not $Force -and $currentTime -gt $cutoffTime) {
    $skipOpenNewPositions = $true
    Write-Log "Past 09:45, skip new positions" "WARN"
}

# Step 1: Read config
Write-Log "Reading config..."
try { $config = Get-Content $configFile -Raw -Encoding UTF8 | ConvertFrom-Json } catch {
    Write-Error "Config parse failed: $_"; exit 1
}

# Step 2: Read positions
Write-Log "Reading positions..."
if (Test-Path $positionsFile) {
    try { $positions = Get-Content $positionsFile -Raw -Encoding UTF8 | ConvertFrom-Json } catch {
        Write-Error "Positions parse failed: $_"; exit 1
    }
} else {
    Write-Log "Positions file not found, initializing default" "WARN"
    $positions = [PSCustomObject]@{
        Cash = $config.InitialCapital
        TotalValue = $config.InitialCapital
        LastUpdated = $Date
        Positions = @{}
        Cooldowns = @{}
        RiskCooldowns = @{}
    }
}
$stockMap = @{}
$positions.Positions.PSObject.Properties | ForEach-Object { $stockMap[$_.Name] = $_.Value }

$cooldowns = @{}
if ($positions.PSObject.Properties.Name -contains 'Cooldowns') {
    $positions.Cooldowns.PSObject.Properties | ForEach-Object { $cooldowns[$_.Name] = $_.Value }
}
$riskCooldowns = @{}
if ($positions.PSObject.Properties.Name -contains 'RiskCooldowns') {
    $positions.RiskCooldowns.PSObject.Properties | ForEach-Object { $riskCooldowns[$_.Name] = $_.Value }
}

# Step 3: Read data_scored.json
if (-not $DataFile) {
    $DataFile = Join-Path $RootDir "代码文件/数据/data_scored.json"
}
if (-not (Test-Path $DataFile)) {
    Write-Log "data_scored.json not found: $DataFile" "ERROR"
    exit 1
}
Write-Log "Reading scored data..."
try { $scoredData = Get-Content $DataFile -Raw -Encoding UTF8 | ConvertFrom-Json } catch {
    Write-Error "Scored data parse failed: $_"; exit 1
}
$candidates = @{}
$scoredData.Recommendations | ForEach-Object {
    $candidates[$_.Code] = $_
}
Write-Log "Candidate pool: $($candidates.Count) stocks"

# Step 3.5: 读取腰子交易指令 (Phase 1 指令通道 v2.1)
if (-not $InstructionFile) {
    $InstructionFile = Join-Path $simDir "交易决策/交易指令_${Date}.json"
}
$yaoziSells = @{}; $yaoziBuys = @{}; $yaoziHolds = @{}
$hasYaoziInstructions = $false
if (Test-Path $InstructionFile) {
    try {
        $yaoziRaw = Get-Content $InstructionFile -Raw -Encoding UTF8 | ConvertFrom-Json
        foreach ($d in $yaoziRaw.decisions) {
            if ($d.status -ne "pending") { continue }
            if ($d.action -eq "SELL" -or $d.action -eq "SELL_HALF") { $yaoziSells[$d.code] = $d }
            elseif ($d.action -eq "BUY") { $yaoziBuys[$d.code] = $d }
            elseif ($d.action -eq "HOLD") { $yaoziHolds[$d.code] = $d }
        }
        $hasYaoziInstructions = ($yaoziSells.Count + $yaoziBuys.Count + $yaoziHolds.Count) -gt 0
        if ($hasYaoziInstructions) {
            Write-Log "腰子指令: SELL=$($yaoziSells.Count) BUY=$($yaoziBuys.Count) HOLD=$($yaoziHolds.Count)"
        }
    } catch {
        Write-Log "腰子指令解析失败: $_" "WARN"
        $yaoziSells = @{}; $yaoziBuys = @{}; $yaoziHolds = @{}
    }
}

# Step 4: Data quality check (玉夜 v2026-05-24)
Write-Log "Running data quality check..."
$dqScript = Join-Path $RootDir "代码文件/tools/check_data_quality.ps1"
$dqJson = ""
if (Test-Path $dqScript) {
    try { $dqJson = & powershell -File $dqScript -Mode daily_sim -DataFile $DataFile -RootDir $RootDir } catch {
        Write-Log "数据质检脚本执行失败: $_" "WARN"
    }
}
$dqFlag = "normal"
$dqDegradedFields = @()
if ($dqJson) {
    try { $dqResult = $dqJson | ConvertFrom-Json
        $dqFlag = $dqResult.Flag
        $dqDegradedFields = @($dqResult.DegradedFields)
        Write-Log "Quality flag: $dqFlag, degraded: $($dqDegradedFields -join ',')"
    } catch { Write-Log "Quality check parse failed, assuming normal" "WARN" }
}

$validCandidates = @{}
foreach ($code in $candidates.Keys) {
    $s = $candidates[$code]
    $skip = $false
    if (-not $s.Price -or $s.Price -le 0) { $skip = $true }
    if (-not $s.TotalScore -or $s.TotalScore -lt 0 -or $s.TotalScore -gt 100) { $skip = $true }
    if (-not $s.Code) { $skip = $true }
    if (-not $skip) { $validCandidates[$code] = $s }
}
Write-Log "Quality check passed: $($validCandidates.Count)/$($candidates.Count)"

# Step 5: Get quotes
Write-Log "Fetching real-time quotes..."
$quoteList = @{}
foreach ($code in $validCandidates.Keys) {
    $mk = if ($code -match '^0[0-7]|^6') { "sh" } else { "sz" }
    $quoteList[$code] = @{ Code = $code; Market = $mk; Name = $validCandidates[$code].Name }
}
foreach ($code in $stockMap.Keys) {
    if (-not $quoteList.ContainsKey($code)) {
        $mk = if ($code -match '^0[0-7]|^6') { "sh" } else { "sz" }
        $quoteList[$code] = @{ Code = $code; Market = $mk; Name = $stockMap[$code].Name }
    }
}
$stockList = $quoteList.Values | ForEach-Object { @{ Code = $_.Code; Market = $_.Market; Name = $_.Name } }
$quoteResult = Get-QuoteMap -StockList $stockList -CacheFile $cacheFile -SimDir $simDir
$quotes = $quoteResult.Quotes
if ($quotes.Count -eq 0) {
    Write-Log "All quote APIs unavailable" "WARN"
}
Start-Sleep -Milliseconds 300
$benchData = Get-BenchmarkValue
if ($benchData) { Write-Log "CSI300: $($benchData.Price)" }

if (-not $DryRun -and $quotes.Count -gt 0) {
    Save-QuoteCache -Quotes $quotes -CacheFile $cacheFile
}

# Step 6.5: Market circuit breaker (山猫 v2026-05-24)
$blackSwanTriggered = $false
$csi300Change = 0
$marketTurnover = 10000
if ($benchData) {
    if ($benchData.ChangePct) { $csi300Change = $benchData.ChangePct }
    if ($benchData.Turnover) { $marketTurnover = $benchData.Turnover }
}
$marketCB = Get-MarketCircuitBreaker -CSI300ChangePct $csi300Change `
    -MarketTurnover $marketTurnover -LowTurnoverDays 0
if ($marketCB.Level -ne "none") {
    Write-Log "MARKET CB: level=$($marketCB.Level) | $($marketCB.Action)" "WARN"
    if ($marketCB.SkipOpen) {
        $skipOpenNewPositions = $true
        Write-Log "  -> New positions blocked by market circuit breaker" "WARN"
    }
    if ($marketCB.ForceReduce) {
        $blackSwanTriggered = $true
        Write-Log "  -> Force reduce triggered by market meltdown" "WARN"
    }
}

# Sector phase check on holdings (山猫 v2026-05-24)
$sectorPhases = @{}
foreach ($code in $validCandidates.Keys) {
    $sc = $validCandidates[$code]
    $ind = if ($sc.Industry) { $sc.Industry } else { $sc.SectorName }
    if ($ind -and $sc.SectorPhase) {
        $sectorPhases[$ind] = $sc.SectorPhase
    }
}
# Build confidence map from SectorTrendMap (v2026-05-24: trend_score 0-10 → confidence 0-100)
$sectorConf = @{}
if ($scoredData.SectorTrendMap) {
    $scoredData.SectorTrendMap.PSObject.Properties | ForEach-Object {
        $stm = $_.Value
        $indName = $stm.sector_name
        $trendScore = [double]$stm.trend_score
        if ($indName -and $trendScore -ge 0) {
            $sectorConf[$indName] = [Math]::Round($trendScore * 10, 0)
        }
    }
}
# Fallback: any industries in positions not in SectorTrendMap default to 50
foreach ($code in $validCandidates.Keys) {
    $sc = $validCandidates[$code]
    $ind = if ($sc.Industry) { $sc.Industry } else { $sc.SectorName }
    if ($ind -and -not $sectorConf.ContainsKey($ind)) {
        $sectorConf[$ind] = 50
    }
}
$phaseAlerts = Get-SectorPhaseAlerts -Positions $stockMap -CurrentPhases $sectorPhases -ConfidenceMap $sectorConf
foreach ($w in $phaseAlerts.Warnings) {
    Write-Log "SECTOR WARN: $($w.Code) - $($w.Reason)" "WARN"
}
foreach ($r in $phaseAlerts.ForceReduce) {
    Write-Log "SECTOR REDUCE: $($r.Code) - $($r.Reason)" "WARN"
}

# Step 6: Portfolio risk check
Write-Log "Portfolio risk check..."
$prevSnapshot = $null
$scriptDateObj = [datetime]::ParseExact($Date, "yyyyMMdd", $null)
$prevDate = $scriptDateObj.AddDays(-1).ToString("yyyyMMdd")
$prevSnapshotFile = Join-Path $trackDir "每日快照/snapshot_daily_${prevDate}.json"
$prevValue = $config.InitialCapital
if (Test-Path $prevSnapshotFile) {
    try { $prevSnapshot = Get-Content $prevSnapshotFile -Raw -Encoding UTF8 | ConvertFrom-Json } catch {}
    if ($prevSnapshot -and $prevSnapshot.TotalValue -gt 0) {
        $prevValue = $prevSnapshot.TotalValue
    }
}

$currentStockValue = 0
foreach ($code in $stockMap.Keys) {
    $pos = $stockMap[$code]
    if ($pos.Shares -le 0) { continue }
    $price = $pos.CurrentPrice
    if ($quotes.ContainsKey($code) -and $quotes[$code].Price -gt 0) {
        $price = $quotes[$code].Price
    }
    $currentStockValue += $price * $pos.Shares
}
$currentValue = $positions.Cash + $currentStockValue

$peakValue = $currentValue
if (Test-Path $perfFile) {
    try {
        $existingPerf = Get-Content $perfFile -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($existingPerf.PeakValue -and $existingPerf.PeakValue -gt $peakValue) {
            $peakValue = $existingPerf.PeakValue
        }
    } catch {}
}

$consecLosses = 0
if (Test-Path $perfFile) {
    try { $existingPerf = Get-Content $perfFile -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($existingPerf.ConsecutiveLosses) { $consecLosses = $existingPerf.ConsecutiveLosses }
    } catch {}
}

$riskConfigHash = @{
    YellowFlagDD = [double]$config.RiskControl.YellowFlagDD
    RedFlagDD = [double]$config.RiskControl.RedFlagDD
    BlackFlagDD = [double]$config.RiskControl.BlackFlagDD
    MaxConsecutiveLosses = [int]$config.RiskControl.MaxConsecutiveLosses
}
$riskDecision = Get-PortfolioRiskDecision -CurrentValue $currentValue -PrevValue $prevValue `
    -InitialCapital $config.InitialCapital -PeakValue $peakValue `
    -ConsecutiveLosses $consecLosses -Config $riskConfigHash

if ($riskDecision.MaxLevel -ne "none") {
    Write-Log "RISK: level=$($riskDecision.MaxLevel) DD=$($riskDecision.DailyDD)%" "WARN"
    foreach ($d in $riskDecision.Decisions) {
        Write-Log "  $($d.Source): $($d.Detail) -> $($d.Action)" "WARN"
    }
    if ($riskDecision.ForceSuspend) {
        Write-Log "BLACK FLAG: system suspended" "ERROR"
        if (-not $DryRun) { exit 0 }
    }
}

$redCooldown = Get-RiskCooldownState -RiskCooldowns $riskCooldowns -Date $Date
if ($redCooldown.InCooldown) {
    $skipOpenNewPositions = $true
    Write-Log "Red flag cooldown active ($($redCooldown.DaysRemaining) days left)" "WARN"
}

# Step 7: Exit check
Write-Log "Running exit checks..."
$txns = @()

foreach ($code in $stockMap.Keys) {
    $pos = $stockMap[$code]
    if ($pos.Shares -le 0) { continue }

    $quote = $quotes[$code]
    $scored = $validCandidates[$code]

    $currentPrice = 0
    if ($quote -and $quote.Price -gt 0) {
        $currentPrice = $quote.Price
    } elseif ($pos.CurrentPrice -gt 0) {
        $currentPrice = $pos.CurrentPrice
    } else {
        Write-Log "  $code no price data, skip exit" "WARN"
        continue
    }

    $quoteSrc = if ($quote -and $quote.DataSource) { $quote.DataSource } else { "[C]" }

    # ATR dynamic stop loss (流金 v2026-05-24)
    $atrN = 2.0
    if ($pos.EntryScore -ge 78) { $atrN = 2.5 }
    elseif ($pos.EntryScore -ge 65) { $atrN = 2.0 }
    else { $atrN = 1.5 }

    $atr14 = 0
    if ($scored -and $scored.ATR14 -and $scored.ATR14 -gt 0) {
        $atr14 = $scored.ATR14
    } elseif ($pos.EntryATR -and $pos.EntryATR -gt 0) {
        $atr14 = $pos.EntryATR
    }

    if ($atr14 -gt 0) {
        $stopLoss = [Math]::Round($pos.AvgCost - $atrN * $atr14, 2)
        $hardMax = [Math]::Round($pos.AvgCost * 0.92, 2)
        $hardMin = [Math]::Round($pos.AvgCost * 0.97, 2)
        if ($stopLoss -lt $hardMax) { $stopLoss = $hardMax }
        if ($stopLoss -gt $hardMin) { $stopLoss = $hardMin }
    } else {
        $stopLoss = [Math]::Round($pos.AvgCost * (1 - $config.StopLossPct / 100), 2)
    }
    $takeProfit = [Math]::Round($pos.AvgCost * (1 + $config.TakeProfitPct / 100), 2)

    # P1: Stop loss
    if ($currentPrice -le $stopLoss) {
        if ($quote -and (Test-IsLimitDown -ChangePct $quote.ChangePct -Code $code)) {
            Write-Log "  $code P1 stop-loss hit but limit-down, pending" "WARN"
            $pos | Add-Member -MemberType NoteProperty -Name "LimitDownPending" -Value $true -Force
            continue
        }
        $sp = Get-SellProceeds -Price $currentPrice -Shares $pos.Shares `
            -CommissionRate $config.Commission.Rate -MinCommission $config.Commission.MinPerOrder `
            -StampTaxRate $config.StampTax.Rate -OnSellOnly $config.StampTax.OnSellOnly
        $txns += [PSCustomObject]@{
            Date = $Date; Code = $code; Name = $pos.Name
            Action = "SELL"; Price = $currentPrice; Shares = $pos.Shares
            Amount = $sp.Amount; Commission = $sp.Commission; StampTax = $sp.StampTax
            TotalCost = $sp.NetProceeds; Reason = "SL_ATR${atrN}x_-8%cap"
            EntryScore = $pos.EntryScore; EntrySector = $pos.EntrySectorPhase
            EntryTheme = $pos.EntryThemePath; DataSource = $quoteSrc
        }
        Write-Log "  $code P1 stop-loss: $currentPrice <= $stopLoss, sell $($pos.Shares)"
        continue
    }

    # P2: Trend break (MA5 cross below MA20)
    if ($scored -and $scored.MA5 -gt 0 -and $scored.MA20 -gt 0 -and
        $pos.EntryMA5 -gt 0 -and $pos.EntryMA20 -gt 0) {
        $crossDown = Test-MACrossover -MA5 $scored.MA5 -MA20 $scored.MA20 -PrevMA5 $pos.EntryMA5 -PrevMA20 $pos.EntryMA20
        if ($crossDown) {
            $sp = Get-SellProceeds -Price $currentPrice -Shares $pos.Shares `
                -CommissionRate $config.Commission.Rate -MinCommission $config.Commission.MinPerOrder `
                -StampTaxRate $config.StampTax.Rate -OnSellOnly $config.StampTax.OnSellOnly
            $txns += [PSCustomObject]@{
                Date = $Date; Code = $code; Name = $pos.Name
                Action = "SELL"; Price = $currentPrice; Shares = $pos.Shares
                Amount = $sp.Amount; Commission = $sp.Commission; StampTax = $sp.StampTax
                TotalCost = $sp.NetProceeds; Reason = "TrendBreak_MA5xMA20"
                EntryScore = $pos.EntryScore; EntrySector = $pos.EntrySectorPhase
                EntryTheme = $pos.EntryThemePath; DataSource = $quoteSrc
            }
            Write-Log "  $code P2 trend break: MA5 < MA20, sell $($pos.Shares)"
            continue
        }
    }

    # P3: Score deterioration
    if ($scored) {
        if ($scored.TotalScore -lt 45) {
            $sp = Get-SellProceeds -Price $currentPrice -Shares $pos.Shares `
                -CommissionRate $config.Commission.Rate -MinCommission $config.Commission.MinPerOrder `
                -StampTaxRate $config.StampTax.Rate -OnSellOnly $config.StampTax.OnSellOnly
            $txns += [PSCustomObject]@{
                Date = $Date; Code = $code; Name = $pos.Name
                Action = "SELL"; Price = $currentPrice; Shares = $pos.Shares
                Amount = $sp.Amount; Commission = $sp.Commission; StampTax = $sp.StampTax
                TotalCost = $sp.NetProceeds; Reason = "ScoreDrop_$($scored.TotalScore)"
                EntryScore = $pos.EntryScore; EntrySector = $pos.EntrySectorPhase
                EntryTheme = $pos.EntryThemePath; DataSource = $quoteSrc
            }
            Write-Log "  $code P3 score drop: $($scored.TotalScore) < 45, sell $($pos.Shares)"
            continue
        }
    } else {
        $sp = Get-SellProceeds -Price $currentPrice -Shares $pos.Shares `
            -CommissionRate $config.Commission.Rate -MinCommission $config.Commission.MinPerOrder `
            -StampTaxRate $config.StampTax.Rate -OnSellOnly $config.StampTax.OnSellOnly
        $txns += [PSCustomObject]@{
            Date = $Date; Code = $code; Name = $pos.Name
            Action = "SELL"; Price = $currentPrice; Shares = $pos.Shares
            Amount = $sp.Amount; Commission = $sp.Commission; StampTax = $sp.StampTax
            TotalCost = $sp.NetProceeds; Reason = "ScoreDrop_Removed"
            EntryScore = $pos.EntryScore; EntrySector = $pos.EntrySectorPhase
            EntryTheme = $pos.EntryThemePath; DataSource = $quoteSrc
        }
        Write-Log "  $code P3 score drop: removed from pool, sell $($pos.Shares)"
        continue
    }

    # P4: Take profit
    if ($currentPrice -ge $takeProfit) {
        $sp = Get-SellProceeds -Price $currentPrice -Shares $pos.Shares `
            -CommissionRate $config.Commission.Rate -MinCommission $config.Commission.MinPerOrder `
            -StampTaxRate $config.StampTax.Rate -OnSellOnly $config.StampTax.OnSellOnly
        $txns += [PSCustomObject]@{
            Date = $Date; Code = $code; Name = $pos.Name
            Action = "SELL"; Price = $currentPrice; Shares = $pos.Shares
            Amount = $sp.Amount; Commission = $sp.Commission; StampTax = $sp.StampTax
            TotalCost = $sp.NetProceeds; Reason = "TP_+12%"
            EntryScore = $pos.EntryScore; EntrySector = $pos.EntrySectorPhase
            EntryTheme = $pos.EntryThemePath; DataSource = $quoteSrc
        }
        Write-Log "  $code P4 take-profit: $currentPrice >= $takeProfit, sell $($pos.Shares)"
        continue
    }

    # P5: Overbought reduce
    if ($scored -and $scored.RSI -gt $config.RSIExtreme -and $pos.RSIPrevOver) {
        $sellShares = [int]($pos.Shares / 2)
        $sellShares = $sellShares - ($sellShares % 100)
        if ($sellShares -lt 100) { $sellShares = [int]$pos.Shares }
        $sp = Get-SellProceeds -Price $currentPrice -Shares $sellShares `
            -CommissionRate $config.Commission.Rate -MinCommission $config.Commission.MinPerOrder `
            -StampTaxRate $config.StampTax.Rate -OnSellOnly $config.StampTax.OnSellOnly
        $txns += [PSCustomObject]@{
            Date = $Date; Code = $code; Name = $pos.Name
            Action = "SELL_HALF"; Price = $currentPrice; Shares = $sellShares
            Amount = $sp.Amount; Commission = $sp.Commission; StampTax = $sp.StampTax
            TotalCost = $sp.NetProceeds; Reason = "Overbought_RSI$($scored.RSI)"
            EntryScore = $pos.EntryScore; EntrySector = $pos.EntrySectorPhase
            EntryTheme = $pos.EntryThemePath; DataSource = $quoteSrc
        }
        Write-Log "  $code P5 overbought: RSI=$($scored.RSI) > 80 x2, sell ${sellShares}"
    } elseif ($scored) {
        if ($scored.RSI -gt $config.RSIExtreme) {
            $pos | Add-Member -MemberType NoteProperty -Name "RSIPrevOver" -Value $true -Force
        } else {
            $pos | Add-Member -MemberType NoteProperty -Name "RSIPrevOver" -Value $false -Force
        }
    }
}

# Black-swan reduce (includes market circuit breaker meltdown)
if ($riskDecision.ForceReduce -or $blackSwanTriggered) {
    $triggerSource = if ($blackSwanTriggered) { "MarketMeltdown" } else { "RiskDD" }
    Write-Log "RED FLAG: black-swan reduce triggered (source=$triggerSource)" "WARN"
    foreach ($code in $stockMap.Keys) {
        $pos = $stockMap[$code]
        if ($pos.Shares -le 0) { continue }
        $alreadyExited = $txns | Where-Object { $_.Code -eq $code -and $_.Action -eq "SELL" }
        if ($alreadyExited) { continue }

        $currentPrice = $pos.CurrentPrice
        if ($quotes.ContainsKey($code) -and $quotes[$code].Price -gt 0) {
            $currentPrice = $quotes[$code].Price
        }
        $sellShares = [int]($pos.Shares / 2)
        $sellShares = $sellShares - ($sellShares % 100)
        if ($sellShares -lt 100) { $sellShares = [int]$pos.Shares }

        $sp = Get-SellProceeds -Price $currentPrice -Shares $sellShares `
            -CommissionRate $config.Commission.Rate -MinCommission $config.Commission.MinPerOrder `
            -StampTaxRate $config.StampTax.Rate -OnSellOnly $config.StampTax.OnSellOnly
        $ddPct = [Math]::Round($riskDecision.DailyDD, 1)
        $txns += [PSCustomObject]@{
            Date = $Date; Code = $code; Name = $pos.Name
            Action = "SELL_HALF"; Price = $currentPrice; Shares = $sellShares
            Amount = $sp.Amount; Commission = $sp.Commission; StampTax = $sp.StampTax
            TotalCost = $sp.NetProceeds; Reason = "BlackSwan_DD$ddPct%"
            EntryScore = $pos.EntryScore; EntrySector = $pos.EntrySectorPhase
            EntryTheme = $pos.EntryThemePath; DataSource = $quoteSrc
        }
        Write-Log "  $code black-swan reduce: DD=$ddPct%, sell ${sellShares}"
    }
    $riskCooldowns["RedFlagDate"] = $Date
}

# Step 8: Apply exit transactions
foreach ($txn in $txns) {
    $code = $txn.Code
    $pos = $stockMap[$code]
    if (-not $pos) { continue }

    $positions.Cash = [Math]::Round($positions.Cash + $txn.TotalCost, 2)

    if ($txn.Action -eq "SELL_HALF") {
        $pos.Shares = [int]$pos.Shares - $txn.Shares
        $pos.CurrentPrice = $txn.Price
        $pos.UnrealizedPnL = [Math]::Round(($pos.CurrentPrice - $pos.AvgCost) * $pos.Shares, 2)
        $pos.UnrealizedPnLPct = [Math]::Round(($pos.CurrentPrice / $pos.AvgCost - 1) * 100, 2)
    } else {
        $pos.Shares = 0
        $pos.CurrentPrice = $txn.Price
        $pos.UnrealizedPnL = 0
        $pos.UnrealizedPnLPct = 0
        if ($txn.Reason -match "SL_|TrendBreak|ScoreDrop") {
            $pos.LastStopLossDate = $Date
            if (-not $cooldowns[$code]) {
                $cooldowns[$code] = @{ Code = $code; Name = $pos.Name; LastStopLossDate = $null; LastFullTakeProfitDate = $null }
            }
            $cooldowns[$code].LastStopLossDate = $Date
        } elseif ($txn.Reason -match "TP_") {
            $pos.LastFullTakeProfitDate = $Date
            if (-not $cooldowns[$code]) {
                $cooldowns[$code] = @{ Code = $code; Name = $pos.Name; LastStopLossDate = $null; LastFullTakeProfitDate = $null }
            }
            $cooldowns[$code].LastFullTakeProfitDate = $Date
        }
    }
}

# Step 9: Entry check
Write-Log "Running entry checks..."
if ($skipOpenNewPositions) {
    Write-Log "Entry blocked (timeout/risk/cooldown), skip" "WARN"
} elseif ($riskDecision.SkipOpen) {
    $riskLvl = $riskDecision.MaxLevel
    Write-Log "Entry blocked by risk (${riskLvl} flag), skip" "WARN"
} elseif ($dqFlag -eq "cached") {
    Write-Log "Entry blocked by data quality (cached), skip" "WARN"
} else {
    # Data quality: degraded -> position size 80%
    $posMultiplier = 1.0
    if ($dqFlag -eq "degraded") {
        $posMultiplier = 0.8
        Write-Log "Data quality degraded, position size x0.8" "WARN"
    }

    $entryCandidates = @()

    # Industry concentration check (流金 v2026-05-24)
    $indResult = Get-IndustryConcentration -Positions $stockMap -MaxPerIndustry 2
    if ($indResult.Violations.Count -gt 0) {
        foreach ($ind in $indResult.Violations.Keys) {
            Write-Log "Industry conc: ${ind} has $($indResult.Violations[$ind].Count) > 2, blocking" "WARN"
        }
    }

    foreach ($code in $validCandidates.Keys) {
        $sc = $validCandidates[$code]

        if ($stockMap[$code] -and $stockMap[$code].Shares -gt 0) { continue }
        if ($sc.TotalScore -lt $config.MinScore) { continue }
        if (-not ($sc.MA5 -gt $sc.MA10 -and $sc.MA10 -gt $sc.MA20)) { continue }
        if ($sc.RSI -ge $config.RSIOverbought) { continue }

        $isLimitUp = $false
        if ($quotes.ContainsKey($code) -and $quotes[$code].ChangePct -ne 999) {
            $isLimitUp = Test-IsLimitUp -ChangePct $quotes[$code].ChangePct -Code $code
        } elseif ($sc.ChangePct -ne 999) {
            $isLimitUp = Test-IsLimitUp -ChangePct $sc.ChangePct -Code $code
        }
        if ($isLimitUp) { continue }

        if ($sc.TurnoverRate -lt $config.MinTurnoverRate) { continue }
        if ($sc.SectorPhase -eq "衰退期") { continue }
        if ($sc.VolRatio -lt $config.MinVolRatio) { continue }

        $coolSource = if ($cooldowns[$code]) { $cooldowns[$code] } else { $null }
        if ($coolSource -and $coolSource.LastStopLossDate) {
            $coolDays = Get-CoolingDays -DateStr $coolSource.LastStopLossDate -TodayStr $Date
            if ($coolDays -lt $config.CooloffPeriodDays) { continue }
        }
        if ($coolSource -and $coolSource.LastFullTakeProfitDate) {
            $coolDays = Get-CoolingDays -DateStr $coolSource.LastFullTakeProfitDate -TodayStr $Date
            if ($coolDays -lt $config.FullTakeProfitCooldownDays) { continue }
        }

        $entryCandidates += [PSCustomObject]@{
            Code = $code
            Name = $sc.Name
            TotalScore = $sc.TotalScore
            S_Tech = $sc.S_Tech
            SectorPhase = $sc.SectorPhase
            Data = $sc
        }
    }

    if ($entryCandidates.Count -gt 0) {
        $phaseOrder = @{ "高潮期" = 3; "主升调整" = 2; "潜伏期" = 1 }
        $entryCandidates = $entryCandidates | Sort-Object -Property @{
            Expression = { -$_.TotalScore }
        }, @{
            Expression = {
                if ($phaseOrder.ContainsKey($_.SectorPhase)) { -$phaseOrder[$_.SectorPhase] } else { 0 }
            }
        }, @{
            Expression = { -$_.S_Tech }
        }

        $currentPosCount = ($stockMap.Values | Where-Object { $_.Shares -gt 0 }).Count
        $slotsAvailable = $config.MaxPositions - $currentPosCount
        if ($slotsAvailable -le 0) {
            $maxPos = $config.MaxPositions
            Write-Log "Positions full ($currentPosCount/$maxPos)"
        } else {
            $entryCandidates = $entryCandidates | Select-Object -First $slotsAvailable
            $names = ($entryCandidates | ForEach-Object { "$($_.Name)($($_.TotalScore))" }) -join ", "
            Write-Log "Slots: $slotsAvailable, selected: $names"

            foreach ($cand in $entryCandidates) {
                $code = $cand.Code
                $sc = $cand.Data

                $entryPrice = 0
                $buySrc = ""
                if ($quotes.ContainsKey($code) -and $quotes[$code].OpenPrice -gt 0) {
                    $entryPrice = $quotes[$code].OpenPrice
                    $buySrc = if ($quotes[$code].DataSource) { $quotes[$code].DataSource } else { "[1]" }
                } elseif ($quotes.ContainsKey($code) -and $quotes[$code].PrevClose -gt 0) {
                    $entryPrice = $quotes[$code].PrevClose
                    $buySrc = "[PrevClose]"
                } elseif ($sc.Price -gt 0) {
                    $entryPrice = $sc.Price
                    $buySrc = "[ScoredData]"
                } else {
                    continue
                }

                $posPct = Get-PositionSize -Score $sc.TotalScore -Tiers $config.PositionSizing.Tiers
                if ($posPct -le 0) { continue }
                $posPct = [Math]::Round($posPct * $posMultiplier, 1)
                if ($posPct -le 0) { continue }

                # Industry concentration skip (流金 v2026-05-24)
                $entryIndustry = if ($sc.Industry) { $sc.Industry } else { "未知" }
                $indCount = @($stockMap.Values | Where-Object { $_.Shares -gt 0 -and $_.EntryIndustry -eq $entryIndustry }).Count
                if ($indCount -ge 2) {
                    Write-Log "  $code skipped: industry ${entryIndustry} already has ${indCount} positions"
                    continue
                }

                $posAmount = [Math]::Round($positions.Cash * $posPct / 100, 2)
                $maxAmount = [Math]::Round($currentValue * $config.SingleStockLimitPct / 100, 2)
                if ($posAmount -gt $maxAmount) { $posAmount = $maxAmount }

                $buyCost = Get-BuyCost -Price $entryPrice -Shares 100 -CommissionRate $config.Commission.Rate `
                    -MinCommission $config.Commission.MinPerOrder -SlippagePct $config.SlippagePct
                $slippedPrice = $buyCost.Price

                $shares = [Math]::Floor($posAmount / $slippedPrice / 100) * 100
                if ($shares -lt 100) { continue }

                $buyCost = Get-BuyCost -Price $entryPrice -Shares $shares -CommissionRate $config.Commission.Rate `
                    -MinCommission $config.Commission.MinPerOrder -SlippagePct $config.SlippagePct

                if ($buyCost.TotalCost -gt $positions.Cash) { continue }

                $txns += [PSCustomObject]@{
                    Date = $Date; Code = $code; Name = $cand.Name
                    Action = "BUY"; Price = $buyCost.Price; Shares = $shares
                    Amount = -$buyCost.Amount; Commission = $buyCost.Commission; StampTax = 0
                    TotalCost = -$buyCost.TotalCost; Reason = "Entry_Score$($sc.TotalScore)"
                    EntryScore = $sc.TotalScore; EntrySector = $sc.SectorPhase
                    EntryTheme = $(if ($sc.ThemePath) { $sc.ThemePath } else { "" })
                    DataSource = $buySrc
                }

                $positions.Cash = [Math]::Round($positions.Cash - $buyCost.TotalCost, 2)

                $avgCost = [Math]::Round($buyCost.TotalCost / $shares, 2)
                $newPos = [PSCustomObject]@{
                    Code = $code
                    Name = $cand.Name
                    Shares = $shares
                    AvgCost = $avgCost
                    CurrentPrice = $buyCost.Price
                    EntryDate = $Date
                    EntryScore = $sc.TotalScore
                    EntryScoreDetail = @{
                        S_Base = $sc.S_Base; S_Fund = $sc.S_Fund; S_Tech = $sc.S_Tech
                        S_Money = $sc.S_Money; S_News = $sc.S_News; S_Risk = $sc.S_Risk
                        S_SectorTrend = $sc.S_SectorTrend
                    }
                    EntrySectorPhase = $sc.SectorPhase
                    EntryThemePath = $(if ($sc.ThemePath) { $sc.ThemePath } else { "" })
                    EntryIndustry = $(if ($sc.Industry) { $sc.Industry } else { "未知" })
                    EntryATR = $(if ($sc.ATR14 -gt 0) { $sc.ATR14 } else { 0 })
                    EntryMA5 = $sc.MA5
                    EntryMA20 = $sc.MA20
                    LastStopLossDate = $null
                    LastFullTakeProfitDate = $null
                    RSIPrevOver = ($sc.RSI -gt $config.RSIExtreme)
                    UnrealizedPnL = 0
                    UnrealizedPnLPct = 0
                }
                $stockMap[$code] = $newPos
                Write-Log "  $code ENTRY: $shares x $($buyCost.Price) = $($buyCost.Amount), pos=${posPct}%"
            }
        }
    } else {
        Write-Log "No stocks meet entry conditions"
    }
}

# Step 10: Write transactions
if ($txns.Count -gt 0 -and -not $DryRun) {
    $existingLines = @()
    $existingFp = @{}
    if (Test-Path $txnFile) {
        $existingContent = Get-Content $txnFile -Raw
        if ($existingContent.Trim().Length -gt 0) {
            $allExisting = $existingContent.Trim() -split "`n"
            $existingLines = $allExisting | Select-Object -Skip 1
            foreach ($line in $existingLines) {
                $parts = $line -split ','
                if ($parts.Count -ge 4) {
                    $existingFp["$($parts[0])|$($parts[1])|$($parts[3])"] = $true
                }
            }
        }
    }
    $header = "date,code,name,action,price,shares,amount,commission,stamp_tax,total_cost,reason,entry_score,entry_sector,entry_theme,data_source"
    $newLines = @()
    $dupCount = 0
    foreach ($txn in $txns) {
        $line = "{0},{1},{2},{3},{4},{5},{6},{7},{8},{9},{10},{11},{12},{13},{14}" -f
            $txn.Date, $txn.Code, $txn.Name, $txn.Action,
            $txn.Price, $txn.Shares, $txn.Amount, $txn.Commission,
            $txn.StampTax, $txn.TotalCost, $txn.Reason, $txn.EntryScore,
            $txn.EntrySector, $txn.EntryTheme,
            $(if ($txn.DataSource) { $txn.DataSource } else { "[1]" })
        $fp = "$($txn.Date)|$($txn.Code)|$($txn.Action)"
        if ($existingFp.ContainsKey($fp) -and $txn.Action -eq "BUY") {
            $dupCount++
        } else {
            $newLines += $line
        }
    }
    if ($newLines.Count -gt 0) {
        $allLines = @($header) + $existingLines + $newLines
        $txnBefore = if (Test-Path $txnFile) { (Get-Item $txnFile).LastWriteTime } else { [datetime]::MinValue }
        try { $allLines | Set-Content -Encoding UTF8 $txnFile -ErrorAction Stop } catch { Write-Error "Daily txn write error: $_"; exit 1 }
        Assert-WriteSuccess -Path $txnFile -BeforeWrite $txnBefore
        Write-Log "Transactions written: $($newLines.Count) ($dupCount dupes)"
    }
}

# Step 11: Update positions
$posObj = @{}
foreach ($kv in $stockMap.GetEnumerator()) {
    if ($kv.Value.Shares -gt 0) { $posObj[$kv.Key] = $kv.Value }
}
$stockValue = 0
foreach ($kv in $posObj.GetEnumerator()) {
    $p = $kv.Value
    if ($quotes.ContainsKey($kv.Key) -and $quotes[$kv.Key].Price -gt 0) {
        $p.CurrentPrice = $quotes[$kv.Key].Price
    }
    $p.UnrealizedPnL = [Math]::Round(($p.CurrentPrice - $p.AvgCost) * $p.Shares, 2)
    $p.UnrealizedPnLPct = [Math]::Round(($p.CurrentPrice / $p.AvgCost - 1) * 100, 2)
    $stockValue += $p.CurrentPrice * $p.Shares
}
$positions.TotalValue = [Math]::Round($positions.Cash + $stockValue, 2)
$positions.LastUpdated = $Date

if (-not $DryRun) {
    $posOutput = @{
        Cash = $positions.Cash
        TotalValue = $positions.TotalValue
        LastUpdated = $Date
        Positions = $posObj
        Cooldowns = $cooldowns
        RiskCooldowns = $riskCooldowns
    }
    $posBefore = if (Test-Path $positionsFile) { (Get-Item $positionsFile).LastWriteTime } else { [datetime]::MinValue }
    $posOutput | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 $positionsFile -ErrorAction Stop
    Assert-WriteSuccess -Path $positionsFile -BeforeWrite $posBefore
    Write-Log "Positions updated"

    # Shared cooldowns sync (流金 v2026-05-24)
    $sharedDir = Join-Path $simDir "共享模块/shared"
    $sharedCooldownsFile = Join-Path $sharedDir "cooldowns.json"
    if (-not (Test-Path $sharedDir)) { New-Item $sharedDir -ItemType Directory -Force | Out-Null }
    $syncCooldowns = @{}
    $cooldowns.GetEnumerator() | ForEach-Object { $syncCooldowns[$_.Key] = $_.Value }
    if ($syncCooldowns.Count -gt 0) {
        try { $syncCooldowns | ConvertTo-Json -Depth 3 | Set-Content -Encoding UTF8 $sharedCooldownsFile -ErrorAction Stop } catch { Write-Log "Shared cooldowns write error: $_" "WARN" }
    }
}

# Step 12: Daily snapshot
$dailyReturn = 0
$totalReturn = [Math]::Round(($positions.TotalValue / $config.InitialCapital - 1) * 100, 2)
if ($prevSnapshot -and $prevSnapshot.TotalValue -gt 0) {
    $dailyReturn = [Math]::Round(($positions.TotalValue / $prevSnapshot.TotalValue - 1) * 100, 2)
}

$benchmarkVal = $null
if ($config.Benchmark.Enabled -and $benchData) {
    $benchVal = $benchData.Price
    $benchPerf = $null
    if (Test-Path $perfFile) {
        try { $benchPerf = Get-Content $perfFile -Raw -Encoding UTF8 | ConvertFrom-Json } catch {}
    }
    if (-not $benchPerf) {
        $benchPerf = [PSCustomObject]@{ StartDate = $Date; InitialCapital = $config.InitialCapital; CurrentValue = $positions.TotalValue }
    }
    if (-not $benchPerf.Benchmark) {
        $benchPerf | Add-Member -MemberType NoteProperty -Name "Benchmark" -Value @{
            Code = $config.Benchmark.Code; Name = $config.Benchmark.Name; InitialValue = $null
        } -Force
    }
    if (-not $benchPerf.Benchmark.InitialValue) {
        $benchPerf.Benchmark.InitialValue = $benchVal
    }
    $initB = $benchPerf.Benchmark.InitialValue
    if ($initB -and $initB -gt 0) {
        $benchReturn = [Math]::Round(($benchVal / $initB - 1) * 100, 2)
        $excessReturn = [Math]::Round($totalReturn - $benchReturn, 2)
        $benchmarkVal = @{
            Code = $config.Benchmark.Code
            Name = $config.Benchmark.Name
            InitialValue = $initB
            CurrentValue = $benchVal
            BenchmarkReturnPct = $benchReturn
            ExcessReturnPct = $excessReturn
        }
    }
}

$snapshot = @{
    Date = $Date
    TotalValue = $positions.TotalValue
    Cash = $positions.Cash
    StockValue = [Math]::Round($stockValue, 2)
    DailyReturn = $dailyReturn
    TotalReturnPct = $totalReturn
    Positions = ($posObj.Values | Measure-Object).Count
    StockDetails = ($posObj.Values | ForEach-Object {
        @{
            Code = $_.Code; Name = $_.Name; Shares = $_.Shares
            AvgCost = $_.AvgCost; CurrentPrice = $_.CurrentPrice
            UnrealizedPnL = $_.UnrealizedPnL; UnrealizedPnLPct = $_.UnrealizedPnLPct
            EntryScore = $_.EntryScore; EntrySector = $_.EntrySectorPhase
        }
    })
    Benchmark = $benchmarkVal
}
if (-not $DryRun) {
    $snapBefore = if (Test-Path $snapshotFile) { (Get-Item $snapshotFile).LastWriteTime } else { [datetime]::MinValue }
    try { $snapshot | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 $snapshotFile -ErrorAction Stop } catch { Write-Error "Daily snapshot write error: $_"; exit 1 }
    Assert-WriteSuccess -Path $snapshotFile -BeforeWrite $snapBefore
    Write-Log "Snapshot written: $snapshotFile"
}

# Step 13: Update performance summary
if (-not $perfSummary) {
    if (Test-Path $perfFile) {
        try { $perfSummary = Get-Content $perfFile -Raw -Encoding UTF8 | ConvertFrom-Json } catch {}
    }
    if (-not $perfSummary) {
        $perfSummary = [PSCustomObject]@{
            StartDate = $null; InitialCapital = $config.InitialCapital
            CurrentValue = $positions.TotalValue; TotalReturnPct = 0
            MaxDrawdown = 0; MaxDrawdownDate = $null; PeakValue = $positions.TotalValue
            TotalTrades = 0; WinningTrades = 0; LosingTrades = 0; WinRate = $null
            ConsecutiveLosses = 0; IsDrawdownAlert = $false
        }
    } elseif (-not $perfSummary.PeakValue) {
        $perfSummary | Add-Member -MemberType NoteProperty -Name "PeakValue" -Value $positions.TotalValue -Force
    }
}
$perfSummary.CurrentValue = $positions.TotalValue
$perfSummary.TotalReturnPct = $totalReturn
if (-not $perfSummary.StartDate) { $perfSummary.StartDate = $Date }

if (-not $perfSummary.PeakValue -or $positions.TotalValue -gt $perfSummary.PeakValue) {
    $perfSummary.PeakValue = $positions.TotalValue
}
$currentDD = [Math]::Round(($positions.TotalValue / $perfSummary.PeakValue - 1) * 100, 2)
if ($currentDD -lt $perfSummary.MaxDrawdown) {
    $perfSummary.MaxDrawdown = $currentDD
    $perfSummary.MaxDrawdownDate = $Date
}

# FIFO win/loss
$allTxns = @()
if (Test-Path $txnFile) {
    $txnContent = Get-Content $txnFile -Raw
    if ($txnContent.Trim().Length -gt 0) {
        $allTxns = Import-Csv $txnFile | ForEach-Object {
            [PSCustomObject]@{ Date = $_.date; Code = $_.code; Action = $_.action; TotalCost = [double]$_.total_cost }
        }
    }
}
$winCount = 0; $loseCount = 0; $consecLosses = 0
$groupedTxns = $allTxns | Group-Object Code
foreach ($group in $groupedTxns) {
    $sortedTxns = $group.Group | Sort-Object Date
    $costBase = 0
    foreach ($t in $sortedTxns) {
        if ($t.Action -eq "BUY") {
            $costBase += $t.TotalCost
        } elseif ($t.Action -eq "SELL_HALF") {
            $costBase += $t.TotalCost
            if ($costBase -gt 0) { $costBase = 0 }
        } elseif ($t.Action -eq "SELL") {
            $netPnL = $t.TotalCost + $costBase
            if ($netPnL -gt 0) { $winCount++; $consecLosses = 0 } else { $loseCount++; $consecLosses++ }
            $costBase = 0
        }
    }
}
$totalTrades = $winCount + $loseCount
$perfSummary.TotalTrades = $totalTrades
$perfSummary.WinningTrades = $winCount
$perfSummary.LosingTrades = $loseCount
$perfSummary.ConsecutiveLosses = $consecLosses
if ($totalTrades -gt 0) {
    $perfSummary.WinRate = [Math]::Round($winCount / $totalTrades * 100, 1)
}
$perfSummary.IsDrawdownAlert = ($perfSummary.MaxDrawdown -lt -10)

$riskMetrics = [PSCustomObject]@{
    MaxDrawdown = $perfSummary.MaxDrawdown
    MaxDrawdownDate = $perfSummary.MaxDrawdownDate
    AvgStopLossDistance = $config.StopLossPct
    ConsecutiveLosses = $perfSummary.ConsecutiveLosses
    SharpeRatio = $null
    InformationRatio = $null
    IsDrawdownAlert = $perfSummary.IsDrawdownAlert
    CurrentDrawdown = $currentDD
    AvgWinPct = $null
    AvgLossPct = $null
    ProfitFactor = $null
}
$perfSummary | Add-Member -MemberType NoteProperty -Name "RiskMetrics" -Value $riskMetrics -Force

$perStock = @{}
if ($perfSummary.PerStock) {
    try { $perfSummary.PerStock.PSObject.Properties | ForEach-Object { $perStock[$_.Name] = $_.Value } } catch {}
}
$currentPositions = $stockMap.Values | Where-Object { $_.Shares -gt 0 }
foreach ($p in $currentPositions) {
    $code = $p.Code
    if (-not $perStock.ContainsKey($code)) {
        $perStock[$code] = @{
            Name = $p.Name
            Trades = 0; WinRate = $null
            TotalPnL = $p.UnrealizedPnL
            UnrealizedPnL = $p.UnrealizedPnL
            UnrealizedPnLPct = $p.UnrealizedPnLPct
            CurrentShares = $p.Shares
            AvgEntryScore = $p.EntryScore
            EntrySectorPhase = $p.EntrySectorPhase
        }
    } else {
        $perStock[$code].UnrealizedPnL = $p.UnrealizedPnL
        $perStock[$code].UnrealizedPnLPct = $p.UnrealizedPnLPct
        $perStock[$code].CurrentShares = $p.Shares
    }
}
$perfSummary | Add-Member -MemberType NoteProperty -Name "PerStock" -Value ([PSCustomObject]$perStock) -Force

if ($benchmarkVal) { $perfSummary | Add-Member -MemberType NoteProperty -Name "Benchmark" -Value $benchmarkVal -Force }

if (-not $DryRun) {
    $jsonStr = $perfSummary | ConvertTo-Json -Depth 6
    [System.IO.File]::WriteAllText($perfFile, $jsonStr, [System.Text.UTF8Encoding]::new($false))
    Assert-WriteSuccess -Path $perfFile
}

# Step 14: Console report
Write-Log ""
Write-Log "===== Daily Rec Sim Report ${Date} ====="
Write-Log "NAV: $($positions.TotalValue) (daily $($dailyReturn)% | total $($totalReturn)%)"
if ($benchmarkVal) {
    Write-Log "Bench: $($benchmarkVal.BenchmarkReturnPct)% | Excess: $($benchmarkVal.ExcessReturnPct)%"
}
$posCount = ($posObj.Values | Measure-Object).Count
$posPct = [Math]::Round($stockValue / $positions.TotalValue * 100, 1)
Write-Log "Positions: ${posCount}/$($config.MaxPositions) | Exposure ${posPct}% | MaxDD: $($perfSummary.MaxDrawdown)%"
Write-Log "WinRate: $($perfSummary.WinRate)% ($winCount W / $loseCount L) | Streak: $consecLosses"
if ($riskDecision.MaxLevel -ne "none") {
    Write-Log "RISK: $($riskDecision.MaxLevel) flag" "WARN"
}

if ($posObj.Count -gt 0) {
    Write-Log ""
    foreach ($p in ($posObj.Values | Sort-Object { -$_.UnrealizedPnLPct })) {
        $sign = if ($p.UnrealizedPnLPct -ge 0) { "+" } else { "" }
        $scoreStr = $(if ($p.EntryScore) { " Score=$($p.EntryScore)" } else { "" })
        Write-Log "  $($p.Name) $($p.Shares)sh Cost=$($p.AvgCost) Now=$($p.CurrentPrice) PnL=${sign}$($p.UnrealizedPnLPct)%$scoreStr"
    }
}

if ($txns.Count -gt 0) {
    Write-Log ""
    foreach ($t in $txns) {
        $act = if ($t.Action -eq "BUY") { "BUY " } elseif ($t.Action -eq "SELL") { "SELL" } else { "HALF" }
        $sign = if ($t.TotalCost -ge 0) { "+" } else { "" }
        Write-Log "  ${act} $($t.Name): $($t.Shares) x $($t.Price) = ${sign}$([Math]::Abs($t.TotalCost)) | $($t.Reason)"
    }
}

Write-Log "===== END ====="
Write-Log "[DONE]"

if (-not $DryRun) {
    $logContent = $logLines -join "`n"
    $logContent | Out-File -Encoding utf8 (Join-Path $logDir "sim_daily_${Date}.log")
    Assert-WriteSuccess -Path (Join-Path $logDir "sim_daily_${Date}.log")
}
