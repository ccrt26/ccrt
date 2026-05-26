<#
.SYNOPSIS
    重点股票模拟交易引擎 v1.5
.DESCRIPTION
    基于评估数据的评分/预判/信号，对6只重点股票执行日频模拟交易。
    每日09:35运行，输出交易流水、持仓快照、绩效报告。
    设计文档：临时报告/重点股票模拟交易系统设计方案.md v1.8
.PARAMETER Date
    交易日期，格式 yyyyMMdd，默认当天
.PARAMETER DataFile
    评估数据 JSON 路径。默认读取 重点股票/次日评估/评估数据_{Date}.json
.PARAMETER RootDir
    项目根目录
.PARAMETER DryRun
    试运行模式，只输出日志不写文件
.EXAMPLE
    .\sim_trading.ps1 -Date "20260522"
    .\sim_trading.ps1 -Date "20260522" -DryRun
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

# Resolve RootDir: use parameter if provided, else derive from script location
if (-not $RootDir) {
    if ($PSScriptRoot) {
        $RootDir = (Resolve-Path "$PSScriptRoot/../..").Path
    } else {
        $RootDir = "C:\Users\34269\Documents\Claude\股票分析"
    }
}

# ============================================================
# PATHS
# ============================================================
$simDir = Join-Path $RootDir "模拟交易"
$configFile = Join-Path $simDir "sim_config.json"
$exDivFile = Join-Path $simDir "ex_dividend_dates.json"
$logDir = Join-Path $simDir "日志"

# === 主路径: 历史数据/ 归档架构 (情墨 06-数据持久化) ===
$canonBase = Join-Path $RootDir "历史数据"
$positionsFile = Join-Path $canonBase "00_核心交易/positions.json"
$txnFile = Join-Path $canonBase "00_核心交易/transactions.csv"
$snapshotFile = Join-Path $canonBase "01_交易快照/snapshot_${Date}.json"
$perfFile = Join-Path $canonBase "00_核心交易/perf_summary.json"
$canonBackupDir = Join-Path $canonBase "_backup"

# 旧路径(只读兼容) — 主路径不存在时回退
$legacyPositionsFile = Join-Path $simDir "持仓记录/positions.json"
$legacyTxnFile = Join-Path $simDir "持仓记录/transactions.csv"
$legacyPerfFile = Join-Path $simDir "绩效报告/perf_summary.json"
$legacySnapshotFile = Join-Path $simDir "每日快照/snapshot_${Date}.json"

if (-not $DryRun -and -not (Test-Path $logDir)) { New-Item $logDir -ItemType Directory -Force | Out-Null }

# Source shared risk module (山猫+流金 v2026-05-24)
. (Join-Path $simDir "共享模块/risk_framework.ps1")

# === 股票代码映射 ===
$codeMap = @{
    "603019" = @{ Market="sh"; Name="中科曙光"; Board="main" }
    "601689" = @{ Market="sh"; Name="拓普集团"; Board="main" }
    "600114" = @{ Market="sh"; Name="东睦股份"; Board="main" }
    "301075" = @{ Market="sz"; Name="多瑞医药"; Board="chiNext" }
    "000967" = @{ Market="sz"; Name="盈峰环境"; Board="main" }
    "600036" = @{ Market="sh"; Name="招商银行"; Board="main" }
}

# ============================================================
# LOGGING
# ============================================================
$logLines = @()
function Assert-WriteSuccess {
    param([string]$Path)
    if (-not (Test-Path $Path)) { Write-Error "写入失败: $Path"; exit 1 }
}

function Write-Log {
    param([string]$Msg, [string]$Level="INFO")
    $line = "[$Level] $Msg"
    $script:logLines += $line
    Write-Output $line
}

# ============================================================
# FUNCTION: 获取行情
# ============================================================
function Get-QuoteMap {
    $qtCodes = @()
    $codeMap.Keys | ForEach-Object { $qtCodes += $codeMap[$_].Market + $_ }
    $result = @{}
    $dataSourceLog = ""

    # Tier 1: 腾讯行情[1] (primary)
    try {
        $wc = New-Object System.Net.WebClient
        $rawBytes = $wc.DownloadData("https://qt.gtimg.cn/q=$($qtCodes -join ',')")
        $utf16text = [System.Text.Encoding]::GetEncoding("GBK").GetString($rawBytes)
        ($utf16text -split ';') | ForEach-Object {
            $m = [regex]::Match($_, '"(.*)"')
            if (-not $m.Success) { return }
            $parts = $m.Groups[1].Value -split '~'
            if ($parts.Count -lt 45) { return }
                $code = $parts[2]
                $openP = 0; [double]::TryParse($parts[5], [ref]$openP) | Out-Null
                $nowP  = 0; [double]::TryParse($parts[3], [ref]$nowP) | Out-Null
                $chgP  = 999; [double]::TryParse($parts[32], [ref]$chgP) | Out-Null
                $highP = 0; [double]::TryParse($parts[33], [ref]$highP) | Out-Null
                $lowP  = 0; [double]::TryParse($parts[34], [ref]$lowP) | Out-Null
                $prevCloseP = 0; [double]::TryParse($parts[4], [ref]$prevCloseP) | Out-Null
                $result[$code] = @{
                    OpenPrice   = $openP
                    Price       = $nowP
                    ChangePct   = $chgP
                    High        = $highP
                    Low         = $lowP
                    PrevClose   = $prevCloseP
                    Name        = $parts[1]
                    DataSource  = "[1]"
                }
            }
            if ($result.Count -gt 0) { $dataSourceLog = "腾讯行情[1]" }
    # DEBUG: log ALL quotes to file for diagnosis
    $dbgLines = @()
    foreach ($k in $result.Keys) {
        $q = $result[$k]
        $dbgLines += "QUOTE $k Open=$($q.OpenPrice) PC=$($q.PrevClose) Price=$($q.Price) Name=$($q.Name)"
    }
    $dbgLines | Out-File "$env:TEMP\sim_debug_quotes.log" -Encoding utf8
    } catch {
        Write-Log "腾讯行情[1]异常: $_" "WARN"
    }

    # Tier 2: 新浪行情[1B] (backup)
    if ($result.Count -eq 0) {
        Write-Log "腾讯行情[1]不可用，尝试新浪行情[1B]..." "WARN"
        try {
            $sinaUrl = "https://hq.sinajs.cn/list=$($qtCodes -join ',')"
            $wc = New-Object System.Net.WebClient
            $wc.Headers.Add("Referer", "https://finance.sina.com.cn")
            $rawBytes = $wc.DownloadData($sinaUrl)
            $utf16text = [System.Text.Encoding]::GetEncoding("GBK").GetString($rawBytes)
            ($utf16text -split ';') | ForEach-Object {
                    if ($_.Trim().Length -eq 0) { return }
                    $m = [regex]::Match($_, 'var hq_str_(\w+)="(.*)"')
                    if (-not $m.Success) { return }
                    $fullCode = $m.Groups[1].Value
                    $parts = $m.Groups[2].Value -split ','
                    if ($parts.Count -lt 32) { return }
                    $code = $fullCode -replace '^(sh|sz|bj)', ''
                    $name = $parts[0]
                    $openP = 0; [double]::TryParse($parts[1], [ref]$openP) | Out-Null
                    $nowP  = 0; [double]::TryParse($parts[3], [ref]$nowP) | Out-Null
                    $highP = 0; [double]::TryParse($parts[4], [ref]$highP) | Out-Null
                    $lowP  = 0; [double]::TryParse($parts[5], [ref]$lowP) | Out-Null
                    $chgP  = 999
                    $prevClose = 0; [double]::TryParse($parts[2], [ref]$prevClose) | Out-Null
                    if ($prevClose -gt 0) { $chgP = [Math]::Round(($nowP / $prevClose - 1) * 100, 2) }
                    $result[$code] = @{
                        OpenPrice   = $openP
                        Price       = $nowP
                        ChangePct   = $chgP
                        High        = $highP
                        Low         = $lowP
                        Name        = $name
                        DataSource  = "[1B]"
                        PrevClose   = $prevClose
                    }
                }
                if ($result.Count -gt 0) { $dataSourceLog = "新浪行情[1B]" }
        } catch {
            Write-Log "新浪行情[1B]异常: $_" "WARN"
        }
    }

    # Tier 3: 缓存兜底[C]
    if ($result.Count -eq 0) {
        Write-Log "行情API均不可用，尝试缓存[C]..." "WARN"
        $cacheFile = Join-Path $simDir "quotes_cache.json"
        if (Test-Path $cacheFile) {
            try {
                $cache = Get-Content $cacheFile -Raw | ConvertFrom-Json
                foreach ($code in $codeMap.Keys) {
                    if ($null -ne $cache.$code -and $cache.$code.Price -gt 0) {
                        $result[$code] = @{
                            OpenPrice   = [double]$cache.$code.Price
                            Price       = [double]$cache.$code.Price
                            ChangePct   = 0
                            High        = [double]$cache.$code.Price
                            Low         = [double]$cache.$code.Price
                            Name        = $codeMap[$code].Name
                            DataSource  = "[C]"
                        }
                    }
                }
                if ($result.Count -gt 0) { $dataSourceLog = "缓存[C]" }
            } catch {
                Write-Log "缓存[C]读取失败: $_" "WARN"
            }
        }
    }

    if ($dataSourceLog) {
        Write-Log "行情数据来源: $dataSourceLog"
    } else {
        Write-Log "所有行情源均无数据" "WARN"
    }
    return $result
}

# ============================================================
# FUNCTION: 获取沪深300基准
# ============================================================
function Get-BenchmarkValue {
    try {
        $wc = New-Object System.Net.WebClient
        $rawBytes = $wc.DownloadData("https://qt.gtimg.cn/q=sh000300")
        $utf16text = [System.Text.Encoding]::GetEncoding("GBK").GetString($rawBytes)
        $m = [regex]::Match($utf16text, '"(.*)"')
        if (-not $m.Success) { return $null }
        $parts = $m.Groups[1].Value -split '~'
        if ($parts.Count -lt 6) { return $null }
        $price = [double]$parts[3]
        $prevClose = [double]$parts[4]
        $changePct = 0
        if ($prevClose -gt 0) { $changePct = [Math]::Round(($price / $prevClose - 1) * 100, 2) }
        $turnover = 0; [double]::TryParse($parts[37], [ref]$turnover) | Out-Null
        return @{ Price = $price; Open = [double]$parts[5]; ChangePct = $changePct; Turnover = $turnover }
    } catch { return $null }
}

# ============================================================
# FUNCTION: 仓位管理
# ============================================================
function Get-PositionSize {
    param([double]$Score)
    foreach ($tier in $config.PositionSizing.Tiers) {
        if ($Score -ge $tier.MinScore) { return [double]$tier.Ratio }
    }
    return 0
}

function Get-PositionSizeText {
    param([double]$Pct)
    if ($Pct -ge 25) { return "可重点配置" }
    if ($Pct -ge 20) { return "正常配置" }
    if ($Pct -ge 10) { return "轻仓试探" }
    if ($Pct -ge 5)  { return "极轻仓或观望" }
    return "不参与"
}

# ============================================================
# FUNCTION: R2/R3 计算（方案B）
# ============================================================
function Get-R2R3 {
    param([double]$EntryPrice)
    $mode = $config.TakeProfit.Mode
    if ($mode -eq "atr") {
        throw "ATR mode not implemented"
    }
    return @{
        R2 = $EntryPrice * (1 + $config.TakeProfit.FixedPct1 / 100)
        R3 = $EntryPrice * (1 + $config.TakeProfit.FixedPct2 / 100)
    }
}

# ============================================================
# FUNCTION: 费用计算
# ============================================================
function Calc-Commission {
    param([double]$Amount)
    $fee = [Math]::Abs($Amount) * $config.Commission.Rate
    if ($fee -lt $config.Commission.MinPerOrder) { $fee = $config.Commission.MinPerOrder }
    return [Math]::Round($fee, 2)
}

function Calc-StampTax {
    param([double]$Amount, [bool]$IsSell = $true)
    if ($config.StampTax.OnSellOnly -and -not $IsSell) { return 0 }
    return [Math]::Round($Amount * $config.StampTax.Rate, 2)
}

# ============================================================
# FUNCTION: 交易日计数（周一到周五）
# ============================================================
function Get-TradingDaysBetween {
    param([datetime]$StartDate, [datetime]$EndDate)
    $count = 0
    $current = $StartDate.AddDays(1)
    while ($current -le $EndDate) {
        if ($current.DayOfWeek -ge [DayOfWeek]::Monday -and $current.DayOfWeek -le [DayOfWeek]::Friday) {
            $count++
        }
        $current = $current.AddDays(1)
    }
    return $count
}

# ============================================================
# FUNCTION: 冷却期检查（交易日计算）
# ============================================================
function Get-CoolingDays {
    param([string]$DateStr)
    if (-not $DateStr) { return 999 }
    $d1 = [datetime]::ParseExact($Date, "yyyyMMdd", $null)
    $d2 = [datetime]::ParseExact($DateStr, "yyyyMMdd", $null)
    return Get-TradingDaysBetween -StartDate $d2 -EndDate $d1
}

# ============================================================
# FUNCTION: 涨跌停检测
# ============================================================
function Test-IsLimitUp {
    param([double]$ChangePct, [string]$Board="main")
    $limit = if ($Board -eq "chiNext" -or $Board -eq "star") { 19.4 } else { 9.4 }
    return $ChangePct -ge $limit
}
function Test-IsLimitDown {
    param([double]$ChangePct, [string]$Board="main")
    $limit = if ($Board -eq "chiNext" -or $Board -eq "star") { 19.4 } else { 9.4 }
    return $ChangePct -le -$limit
}

# ============================================================
# FUNCTION: 除权除息调整
# ============================================================
function Get-DividendRatio {
    param([string]$CodeVal)
    if (-not $config.ExDividendAdjustment.Enabled) { return 1.0 }
    $exDivFile = $config.ExDividendAdjustment.ConfigFile
    $fullPath = Join-Path $simDir $exDivFile
    if (-not (Test-Path $fullPath)) { return 1.0 }
    try { $exDivData = Get-Content $fullPath -Raw | ConvertFrom-Json } catch { Write-Error "除权除息文件解析失败: $_"; return 1.0 }
    if (-not $exDivData) { return 1.0 }
    $match = $exDivData.$Date | Where-Object { $_.Code -eq $CodeVal }
    if (-not $match) { return 1.0 }
    return [double]$match.Ratio
}

# ============================================================
# FUNCTION: 卖单计算（提取自P1-P5重复代码）
# ============================================================
function Get-SellProceeds {
    param([double]$Price, [int]$Shares, [bool]$IsSell = $true)
    $amount = [Math]::Round($Price * $Shares, 2)
    $commission = Calc-Commission -Amount $amount
    $stampTax = Calc-StampTax -Amount $amount -IsSell $IsSell
    return @{ Amount = $amount; Commission = $commission; StampTax = $stampTax; NetProceeds = $amount - $commission - $stampTax }
}

# ============================================================
# MAIN
# ============================================================
Write-Log "===== 模拟交易引擎 v1.3 | 日期 ${Date} ====="
if ($DryRun) { Write-Log "[DRY RUN MODE - 不会写入文件]" "WARN" }

$scriptDateObj = [datetime]::ParseExact($Date, "yyyyMMdd", $null)

# ---- Step 0: 节假日/停市检测 ----
$dayOfWeek = $scriptDateObj.DayOfWeek
if ($dayOfWeek -eq "Saturday" -or $dayOfWeek -eq "Sunday") {
    Write-Log "非交易日，跳过"
    if (-not $DryRun) { exit 0 }
}

# ---- 中国法定节假日检测（2026年） ----
$holidays2026 = @(
    "20260101",                                    # 元旦
    "20260217","20260218","20260219",              # 春节
    "20260404","20260405","20260406",              # 清明节
    "20260501","20260502","20260503",              # 劳动节
    "20260619","20260620","20260621",              # 端午节
    "20261001","20261002","20261003","20261004","20261005","20261006","20261007"  # 中秋+国庆
)
if ($holidays2026 -contains $Date) {
    Write-Log "法定节假日，跳过"
    if (-not $DryRun) { exit 0 }
}

# ---- 时间检查: 09:45 超时 ----
$currentTime = Get-Date
$cutoffTime = Get-Date -Hour 9 -Minute 45 -Second 0
if (-not $Force -and $currentTime -gt $cutoffTime) {
    $script:skipOpenNewPositions = $true
    Write-Log "当前时间 $($currentTime.ToString('HH:mm')) 超过 09:45，禁止开新仓" "WARN"
} else {
    $script:skipOpenNewPositions = $false
}

# ---- Step 1: 读取配置 ----
Write-Log "读取配置..."
try { $config = Get-Content $configFile -Raw | ConvertFrom-Json } catch { Write-Error "配置文件解析失败: $_"; exit 1 }

# ---- Step 2: 读取持仓 ----
Write-Log "读取持仓..."
$positionsLoaded = $false
if (Test-Path $positionsFile) {
    try { $positions = Get-Content $positionsFile -Raw | ConvertFrom-Json; $positionsLoaded = $true } catch { Write-Error "持仓文件解析失败: $_"; exit 1 }
} elseif (Test-Path $legacyPositionsFile) {
    Write-Log "主持仓文件不存在，从旧路径只读回退" "WARN"
    try { $positions = Get-Content $legacyPositionsFile -Raw | ConvertFrom-Json; $positionsLoaded = $true } catch { Write-Log "旧持仓文件解析失败: $_" "WARN" }
}
if (-not $positionsLoaded) {
    Write-Log "持仓文件不存在，初始化默认持仓" "WARN"
    $positions = [PSCustomObject]@{
        Cash = $config.InitialCapital
        TotalValue = $config.InitialCapital
        LastUpdated = $Date
        Positions = @{}
        Cooldowns = @{}
    }
}
$stockMap = @{}
$positions.Positions.PSObject.Properties | ForEach-Object { $stockMap[$_.Name] = $_.Value }
# 加载冷却期数据（独立于持仓持久化，防止清仓后冷却标记丢失）
$cooldowns = @{}
if ($positions.PSObject.Properties.Name -contains 'Cooldowns') {
    $positions.Cooldowns.PSObject.Properties | ForEach-Object { $cooldowns[$_.Name] = $_.Value }
}
# 加载警戒关注名单（独立于持仓持久化）
$watchlist = @{}
if ($positions.PSObject.Properties.Name -contains 'Watchlist') {
    $positions.Watchlist.PSObject.Properties | ForEach-Object { $watchlist[$_.Name] = $_.Value }
}

# ---- Step 3: 读取评估数据 ----
if (-not $DataFile) {
    $DataFile = Join-Path $RootDir "重点股票/次日评估/评估数据_${Date}.json"
}
if (-not (Test-Path $DataFile)) {
    # 降级: GitHub Actions环境无本地分析流程，回退至最近一次可用评估数据
    $evalDir = Join-Path $RootDir "重点股票/次日评估"
    $latestEval = Get-ChildItem $evalDir -Filter "评估数据_*.json" -ErrorAction SilentlyContinue `
        | Sort-Object Name -Descending | Select-Object -First 1
    if ($latestEval) {
        Write-Log "当日评估数据不存在，回退至: $($latestEval.Name)" "WARN"
        $DataFile = $latestEval.FullName
    } else {
        Write-Log "评估数据不存在: $DataFile，且无历史回退文件" "ERROR"
        exit 1
    }
}
Write-Log "读取评估数据..."
try { $evalDataRaw = Get-Content $DataFile -Raw -Encoding UTF8 | ConvertFrom-Json } catch { Write-Error "评估数据文件解析失败: $_"; exit 1 }
$stocks = @{}
$evalDataRaw.Stocks | ForEach-Object { $stocks[$_.Code] = $_ }

# ---- Step 4: 数据质量检查 ----
Write-Log "执行数据质量检查..."
foreach ($code in $codeMap.Keys) {
    $s = $stocks[$code]
    if (-not $s) { Write-Log "  $code 无评估数据，跳过" "WARN"; continue }
    if (-not $s.Price -or $s.Price -le 0) { Write-Log "  $code Price异常: $($s.Price)" "WARN"; continue }
    if (-not $s.Scores -or $s.Scores.Composite -lt 0 -or $s.Scores.Composite -gt 100) {
        Write-Log "  $code CompositeScore异常: $($s.Scores.Composite)" "WARN"; continue
    }
    if (-not $s.Prediction -or -not $s.Prediction.Short) {
        Write-Log "  $code Prediction.Short缺失" "WARN"; continue
    }
    if (-not $s.TrendHealth -or -not $s.TrendHealth.Label) {
        Write-Log "  $code TrendHealth.Label缺失" "WARN"; continue
    }
    if ($s.KeyLevels.Support -and $s.KeyLevels.Resistance -and $s.KeyLevels.Support -ge $s.KeyLevels.Resistance) {
        Write-Log "  $code Support($($s.KeyLevels.Support)) >= Resistance($($s.KeyLevels.Resistance)) 倒挂，跳过该股质量校验" "WARN"
    }
    # 补齐检查: KeyLevels完整性（Support/Resistance/StopLoss存在且>0）
    if (-not $s.KeyLevels -or -not $s.KeyLevels.Support -or $s.KeyLevels.Support -le 0) {
        Write-Log "  $code KeyLevels.Support缺失或<=0" "WARN"; continue
    }
    if (-not $s.KeyLevels.Resistance -or $s.KeyLevels.Resistance -le 0) {
        Write-Log "  $code KeyLevels.Resistance缺失或<=0" "WARN"; continue
    }
    if (-not $s.KeyLevels.StopLoss -or $s.KeyLevels.StopLoss -le 0) {
        Write-Log "  $code KeyLevels.StopLoss缺失或<=0" "WARN"; continue
    }
    # 补齐检查: Support < Price×1.5 合理性
    if ($s.KeyLevels.Support -ge ($s.Price * 1.5)) {
        Write-Log "  $code Support($($s.KeyLevels.Support)) >= Price×1.5($([Math]::Round($s.Price*1.5,2)))，不合理" "WARN"
    }
    # 补齐检查: Resistance > Price×0.5 合理性
    if ($s.KeyLevels.Resistance -le ($s.Price * 0.5)) {
        Write-Log "  $code Resistance($($s.KeyLevels.Resistance)) <= Price×0.5($([Math]::Round($s.Price*0.5,2)))，不合理" "WARN"
    }
}
Write-Log "数据质量检查完成"

# ---- Step 4.5: 读取腰子交易指令 (Phase 1 指令通道 v2.1) ----
if (-not $InstructionFile) {
    $InstructionFile = Join-Path $simDir "交易决策/交易指令_${Date}.json"
}
$yaoziSells = @{}   # code → decision
$yaoziBuys = @{}     # code → decision
$yaoziHolds = @{}    # code → decision
$yaoziExecuted = @{}  # code → $true (mark after execution)
$hasYaoziInstructions = $false
if (Test-Path $InstructionFile) {
    try {
        $yaoziRaw = Get-Content $InstructionFile -Raw -Encoding UTF8 | ConvertFrom-Json
        foreach ($d in $yaoziRaw.decisions) {
            if ($d.status -ne "pending") { continue }
            $code = $d.code
            if ($d.action -eq "SELL" -or $d.action -eq "SELL_HALF") {
                $yaoziSells[$code] = $d
            } elseif ($d.action -eq "BUY") {
                $yaoziBuys[$code] = $d
            } elseif ($d.action -eq "HOLD") {
                $yaoziHolds[$code] = $d
            }
        }
        $hasYaoziInstructions = ($yaoziSells.Count + $yaoziBuys.Count + $yaoziHolds.Count) -gt 0
        if ($hasYaoziInstructions) {
            Write-Log "腰子指令已加载: SELL=$($yaoziSells.Count) BUY=$($yaoziBuys.Count) HOLD=$($yaoziHolds.Count)"
        }
    } catch {
        Write-Log "腰子指令文件解析失败: $_，回退至纯自动模式" "WARN"
        $yaoziSells = @{}; $yaoziBuys = @{}; $yaoziHolds = @{}
    }
} else {
    Write-Log "无腰子指令文件，使用纯自动模式"
}

# ---- Step 5: 获取行情 ----
Write-Log "获取实时行情..."
$quotes = Get-QuoteMap
if ($quotes.Count -eq 0) {
    Write-Log "行情API全部不可用，跳过开新仓，止损用保守估计" "WARN"
}
Start-Sleep -Milliseconds 300  # API间隔≥0.3s (红线§3.2)
$benchData = Get-BenchmarkValue
if ($benchData) { Write-Log "沪深300: $($benchData.Price)" }

# ---- Step 5.5: Market Circuit Breaker & Shared Cooldowns (山猫+流金 v2026-05-24) ----
$sharedCooldownsFile = Join-Path $simDir "共享模块/shared/cooldowns.json"
$sharedCooldowns = @{}
if (Test-Path $sharedCooldownsFile) {
    try { $sc = Get-Content $sharedCooldownsFile -Raw -Encoding UTF8 | ConvertFrom-Json
        $sc.PSObject.Properties | ForEach-Object { $sharedCooldowns[$_.Name] = $_.Value }
    } catch {}
}

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
}

# ---- Step 6: 除权除息调整 ----
Write-Log "检查除权除息..."
foreach ($code in $stockMap.Keys) {
    $ratio = Get-DividendRatio -CodeVal $code
    if ($ratio -ne 1.0) {
        $pos = $stockMap[$code]
        Write-Log "  $code 除权除息，调整因子: $ratio"
        $pos | Add-Member -MemberType NoteProperty -Name "DividendRatio" -Value $ratio -Force
    }
}

# ---- Step 7: 出场检查（P1~P5优先级） ----
Write-Log "执行出场检查..."
$txns = @()
$exitReasons = @{}

foreach ($code in $stockMap.Keys) {
    $pos = $stockMap[$code]
    $quote = $quotes[$code]
    $evalStock = $stocks[$code]

    $currentPrice = 0
    if ($quote -and $quote.Price -gt 0) {
        $currentPrice = $quote.Price        # L1: 实时行情
    } elseif ($evalStock -and $evalStock.Price -gt 0) {
        $currentPrice = $evalStock.Price    # L2: 评估数据昨收
    } else {
        # L3: 保守估计 — min(昨收, 缓存价), 兜底=止损价
        $conservativePrice = 0
        if ($quote -and $quote.PrevClose -gt 0) {
            $conservativePrice = $quote.PrevClose
        }
        $cacheFile = Join-Path $simDir "quotes_cache.json"
        if (Test-Path $cacheFile) {
            try {
                $cache = Get-Content $cacheFile -Raw | ConvertFrom-Json
                if ($cache.$code -and $cache.$code.Price -gt 0) {
                    $cachedPrice = [double]$cache.$code.Price
                    if ($conservativePrice -gt 0) {
                        $conservativePrice = [Math]::Min($conservativePrice, $cachedPrice)
                    } else {
                        $conservativePrice = $cachedPrice
                    }
                }
            } catch {}
        }
        if ($conservativePrice -gt 0) {
            $currentPrice = $conservativePrice
            Write-Log "  $code 使用保守估计价(L3): $currentPrice" "WARN"
        } else {
            $currentPrice = $pos.StopLoss
            Write-Log "  $code 无价格数据，使用止损价兜底(L3c): $currentPrice" "WARN"
        }
    }

    $adjStopLoss = $pos.StopLoss
    $adjSupport = $pos.Support
    $adjResistance = $pos.Resistance
    if ($pos.DividendRatio) {
        $adjStopLoss = [Math]::Round($adjStopLoss * $pos.DividendRatio, 2)
        $adjSupport  = [Math]::Round($adjSupport * $pos.DividendRatio, 2)
        $adjResistance = [Math]::Round($adjResistance * $pos.DividendRatio, 2)
    }

    $r2r3 = Get-R2R3 -EntryPrice $pos.AvgCost
    $r2 = $r2r3.R2; $r3 = $r2r3.R3

    $quoteDataSource = if ($quote -and $quote.DataSource) { $quote.DataSource } else { "[评估数据]" }

    # --- P1: 止损 ---
    if ($currentPrice -le $adjStopLoss) {
        if ($quote -and (Test-IsLimitDown -ChangePct $quote.ChangePct -Board $codeMap[$code].Board)) {
            Write-Log "  $code 触发止损($currentPrice <= $adjStopLoss)但跌停，标记未成交" "WARN"
            continue
        }
        $shares = [int]$pos.Shares
        $sp = Get-SellProceeds -Price $currentPrice -Shares $shares
        $txns += [PSCustomObject]@{
            Date = $Date; Code = $code; Name = $pos.Name
            Action = "SELL"; Price = $currentPrice; Shares = $shares
            Amount = $sp.Amount; Commission = $sp.Commission; StampTax = $sp.StampTax
            TotalCost = $sp.NetProceeds; Reason = "止损_StopLoss"; EntryPrediction = $pos.EntryShortPrediction
            DataSource = $quoteDataSource
        }
        $exitReasons[$code] = "P1止损"
        Write-Log "  $code P1止损: $currentPrice <= $adjStopLoss, 卖出${shares}股, 收入¥$($sp.NetProceeds)"
        continue
    }

    # --- P2前置: 警戒状态关注名单 ---
    if ($evalStock -and $evalStock.TrendHealth.Label -eq "警戒") {
        if ($watchlist.ContainsKey($code)) {
            $watchlist[$code].LastWarnDate = $Date
            $watchlist[$code].ConsecutiveDays += 1
            Write-Log "  $code 黄旗: TrendHealth警戒第$($watchlist[$code].ConsecutiveDays)天" "WARN"
        } else {
            $watchlist[$code] = @{
                Code = $code
                Name = $pos.Name
                WarnLevel = "警戒"
                FirstWarnDate = $Date
                LastWarnDate = $Date
                ConsecutiveDays = 1
            }
            Write-Log "  $code 黄旗: 新增关注, TrendHealth警戒" "WARN"
        }
        continue
    }
    if ($evalStock -and $evalStock.TrendHealth.Label -eq "健康" -and $watchlist.ContainsKey($code)) {
        Write-Log "  $code 趋势恢复健康，移出关注名单" "INFO"
        $watchlist.Remove($code)
    }

    # --- P2: 趋势恶化 ---
    if ($evalStock -and $evalStock.TrendHealth.Label -eq "危险") {
        if ($watchlist.ContainsKey($code)) {
            $watchlist.Remove($code)
            Write-Log "  $code 警戒→危险升级，移出关注名单" "WARN"
        }
        $shares = [int]$pos.Shares
        $sp = Get-SellProceeds -Price $currentPrice -Shares $shares
        $txns += [PSCustomObject]@{
            Date = $Date; Code = $code; Name = $pos.Name
            Action = "SELL"; Price = $currentPrice; Shares = $shares
            Amount = $sp.Amount; Commission = $sp.Commission; StampTax = $sp.StampTax
            TotalCost = $sp.NetProceeds; Reason = "趋势恶化_危险"; EntryPrediction = $pos.EntryShortPrediction
            DataSource = $quoteDataSource
        }
        $exitReasons[$code] = "P2趋势恶化"
        Write-Log "  $code P2趋势恶化: TrendHealth=危险, 卖出${shares}股"
        continue
    }

    # --- 腰子SELL: 人工卖出指令(P1/P2安全网之下, P3自动规则之上) ---
    if ($yaoziSells.ContainsKey($code)) {
        $yd = $yaoziSells[$code]
        $targetShares = if ($yd.action -eq "SELL_HALF") {
            [int]($pos.Shares / 2 / 100) * 100
        } else {
            [int]$pos.Shares
        }
        if ($targetShares -ge 100) {
            $shares = $targetShares
            $sp = Get-SellProceeds -Price $currentPrice -Shares $shares
            $yaoziReason = $yd.reason
            $overrideMark = ""
            if ($yd.risk_override -eq $true -and $yd.risk_override_reason) {
                $yaoziReason = "$yaoziReason | [风险覆盖]$($yd.risk_override_reason)"
                $overrideMark = "_override"
                Write-Log "  $code [风险覆盖] 腰子SELL覆盖流金警告: $($yd.risk_override_reason)" "WARN"
            }
            if ($yd.analysis_ref) {
                $yaoziSummary = "山猫:$($yd.analysis_ref.shanyao)|流金:$($yd.analysis_ref.liujin)|青山:$($yd.analysis_ref.qingshan)"
            } else {
                $yaoziSummary = ""
            }
            $txns += [PSCustomObject]@{
                Date = $Date; Code = $code; Name = $pos.Name
                Action = $yd.action; Price = $currentPrice; Shares = $shares
                Amount = $sp.Amount; Commission = $sp.Commission; StampTax = $sp.StampTax
                TotalCost = $sp.NetProceeds; Reason = $yaoziReason
                Source = "manual$overrideMark"; AnalysisSummary = $yaoziSummary
                EntryPrediction = $pos.EntryShortPrediction; DataSource = $quoteDataSource
            }
            $exitReasons[$code] = "腰子指令"
            $yaoziExecuted[$code] = $true
            Write-Log "  $code 腰子指令: $($yd.action) ${shares}股, 理由: $yaoziReason"
        } else {
            Write-Log "  $code 腰子SELL指令但持仓不足100股, 跳过" "WARN"
        }
        continue
    }

    # --- 腰子HOLD保护: 腰子明确HOLD则跳过P3/P4/P5自动卖出 ---
    $skipAutoSell = $yaoziHolds.ContainsKey($code)
    if ($skipAutoSell) {
        Write-Log "  $code 腰子HOLD指令: 跳过P3/P4/P5自动卖出检查"
    }

    # --- P3: 预判转空 ---
    if (-not $skipAutoSell -and $evalStock -and $pos.EntryShortPrediction) {
        $currentShort = $evalStock.Prediction.Short
        if ($currentShort -eq "中性" -or $currentShort -eq "看空") {
            $shares = [int]$pos.Shares
            $sp = Get-SellProceeds -Price $currentPrice -Shares $shares
            $txns += [PSCustomObject]@{
                Date = $Date; Code = $code; Name = $pos.Name
                Action = "SELL"; Price = $currentPrice; Shares = $shares
                Amount = $sp.Amount; Commission = $sp.Commission; StampTax = $sp.StampTax
                TotalCost = $sp.NetProceeds; Reason = "预判转空_${currentShort}"; EntryPrediction = $pos.EntryShortPrediction
                DataSource = $quoteDataSource
            }
            $exitReasons[$code] = "P3预判转空"
            Write-Log "  $code P3预判转空: $($pos.EntryShortPrediction)->$currentShort, 卖出${shares}股"
            continue
        }
    }

    # --- P4: 全部止盈 ---
    if (-not $skipAutoSell -and $currentPrice -ge $r3) {
        $shares = [int]$pos.Shares
        $sp = Get-SellProceeds -Price $currentPrice -Shares $shares
        $txns += [PSCustomObject]@{
            Date = $Date; Code = $code; Name = $pos.Name
            Action = "SELL"; Price = $currentPrice; Shares = $shares
            Amount = $sp.Amount; Commission = $sp.Commission; StampTax = $sp.StampTax
            TotalCost = $sp.NetProceeds; Reason = "全部止盈_R3"; EntryPrediction = $pos.EntryShortPrediction
            DataSource = $quoteDataSource
        }
        $exitReasons[$code] = "P4全部止盈"
        Write-Log "  $code P4全部止盈: $currentPrice >= R3($r3), 卖出${shares}股"
        continue
    }

    # --- P5: 止盈减仓 ---
    if (-not $skipAutoSell -and $currentPrice -ge $r2) {
        $sellShares = [int]($pos.Shares / 2)
        $sellShares = $sellShares - ($sellShares % 100)
        if ($sellShares -lt 100) { $sellShares = [int]$pos.Shares }
        $sp = Get-SellProceeds -Price $currentPrice -Shares $sellShares
        $txns += [PSCustomObject]@{
            Date = $Date; Code = $code; Name = $pos.Name
            Action = "SELL_HALF"; Price = $currentPrice; Shares = $sellShares
            Amount = $sp.Amount; Commission = $sp.Commission; StampTax = $sp.StampTax
            TotalCost = $sp.NetProceeds; Reason = "止盈减仓_R2"; EntryPrediction = $pos.EntryShortPrediction
            DataSource = $quoteDataSource
        }
        Write-Log "  $code P5止盈减仓: $currentPrice >= R2($r2), 卖出${sellShares}股(50%)"
    }
}

# ---- Step 8: 应用出场交易 ----
foreach ($txn in $txns) {
    $code = $txn.Code
    $pos = $stockMap[$code]
    if (-not $pos) { continue }

    # 卖出后现金增加
    $positions.Cash = [Math]::Round($positions.Cash + $txn.TotalCost, 2)

    if ($txn.Action -eq "SELL_HALF") {
        $pos.Shares = [int]$pos.Shares - $txn.Shares
        $pos.CurrentPrice = $txn.Price
        $pos.UnrealizedPnL = [Math]::Round(($pos.CurrentPrice - $pos.AvgCost) * $pos.Shares, 2)
        $pos.UnrealizedPnLPct = [Math]::Round(($pos.CurrentPrice / $pos.AvgCost - 1) * 100, 2)
        Write-Log "  $code 减仓后剩余 $($pos.Shares) 股, 浮动盈亏 ¥$($pos.UnrealizedPnL)"
    } else {
        $pos.Shares = 0
        $pos.CurrentPrice = $txn.Price
        $pos.UnrealizedPnL = 0
        $pos.UnrealizedPnLPct = 0
        if ($txn.Reason -match "止损|趋势恶化|预判转空") {
            $pos.LastStopLossDate = $Date
            if (-not $cooldowns[$code]) { $cooldowns[$code] = @{ Code = $code; Name = $pos.Name; LastStopLossDate = $null; LastFullTakeProfitDate = $null } }
            $cooldowns[$code].LastStopLossDate = $Date
            $sharedCooldowns[$code] = $cooldowns[$code]  # 流金: sync to shared
        } elseif ($txn.Reason -match "全部止盈") {
            $pos.LastFullTakeProfitDate = $Date
            if (-not $cooldowns[$code]) { $cooldowns[$code] = @{ Code = $code; Name = $pos.Name; LastStopLossDate = $null; LastFullTakeProfitDate = $null } }
            $cooldowns[$code].LastFullTakeProfitDate = $Date
            $sharedCooldowns[$code] = $cooldowns[$code]  # 流金: sync to shared
        }
        Write-Log "  $code 清仓完成，卖出价 $($txn.Price)"
    }
}

# ---- Step 9: 开仓检查 ----
Write-Log "执行开仓检查..."
if ($skipOpenNewPositions) { Write-Log "09:45 超时标志触发，跳过开新仓" "WARN" }
else {
$candidates = @()

# --- 腰子BUY: 人工买入指令优先于自动开仓 ---
foreach ($code in $yaoziBuys.Keys) {
    $yd = $yaoziBuys[$code]
    $evalStock = $stocks[$code]
    if (-not $evalStock) {
        Write-Log "  $code 腰子BUY指令但无评估数据，跳过" "WARN"
        continue
    }
    if ($stockMap[$code] -and $stockMap[$code].Shares -gt 0) {
        Write-Log "  $code 腰子BUY指令但已有持仓，跳过" "WARN"
        continue
    }
    $coolSource = if ($cooldowns[$code]) { $cooldowns[$code] } elseif ($sharedCooldowns[$code]) { $sharedCooldowns[$code] } else { $null }
    if ($coolSource -and $coolSource.LastStopLossDate) {
        $coolDays = Get-CoolingDays -DateStr $coolSource.LastStopLossDate
        if ($coolDays -lt $config.CooloffPeriodDays) {
            Write-Log "  $code 腰子BUY指令但止损冷却期($coolDays/${$config.CooloffPeriodDays}日)，跳过" "WARN"
            continue
        }
    }
    $quote = $quotes[$code]
    if ($quote -and $quote.ChangePct -ne 999 -and (Test-IsLimitUp -ChangePct $quote.ChangePct -Board $codeMap[$code].Board)) {
        Write-Log "  $code 腰子BUY指令但涨停，跳过" "WARN"
        continue
    }
    if (-not $evalStock.KeyLevels -or $evalStock.KeyLevels.StopLoss -ge $evalStock.Price) {
        Write-Log "  $code 腰子BUY指令但KeyLevels数据异常，跳过" "WARN"
        continue
    }

    $posPct = Get-PositionSize -Score $evalStock.Scores.Composite
    if ($posPct -le 0) { $posPct = 10 }
    $posAmount = [Math]::Round($positions.Cash * $posPct / 100, 2)
    $maxAmount = [Math]::Round($positions.TotalValue * $config.SingleStockLimitPct / 100, 2)
    if ($posAmount -gt $maxAmount) { $posAmount = $maxAmount }

    $entryPrice = if ($quote -and $quote.Price -gt 0) { $quote.Price } else { $evalStock.Price }
    $slippagePct = if ($config.SlippagePct) { $config.SlippagePct } else { 0.001 }
    $slippedPrice = [Math]::Round($entryPrice * (1 + $slippagePct), 2)
    $shares = [Math]::Floor($posAmount / $slippedPrice / 100) * 100
    if ($shares -lt 100) { Write-Log "  $code 腰子BUY指令但资金不足100股，跳过" "WARN"; continue }

    $actualAmount = $slippedPrice * $shares
    $commission = [Math]::Max($actualAmount * $config.Commission.Rate / 100, $config.Commission.MinPerOrder)
    $totalCost = $actualAmount + $commission

    if ($totalCost -gt $positions.Cash) {
        $shares = [Math]::Floor(($positions.Cash * 0.98) / $slippedPrice / 100) * 100
        if ($shares -lt 100) { Write-Log "  $code 腰子BUY指令但现金不足，跳过" "WARN"; continue }
        $actualAmount = $slippedPrice * $shares
        $commission = [Math]::Max($actualAmount * $config.Commission.Rate / 100, $config.Commission.MinPerOrder)
        $totalCost = $actualAmount + $commission
    }

    $yaoziReason = $yd.reason
    $overrideMarkBuy = ""
    if ($yd.risk_override -eq $true -and $yd.risk_override_reason) {
        $yaoziReason = "$yaoziReason | [风险覆盖]$($yd.risk_override_reason)"
        $overrideMarkBuy = "_override"
        Write-Log "  $code [风险覆盖] 腰子BUY覆盖流金警告: $($yd.risk_override_reason)" "WARN"
    }
    if ($yd.analysis_ref) {
        $yaoziSummary = "山猫:$($yd.analysis_ref.shanyao)|流金:$($yd.analysis_ref.liujin)|青山:$($yd.analysis_ref.qingshan)"
    } else { $yaoziSummary = "" }

    $txns += [PSCustomObject]@{
        Date = $Date; Code = $code; Name = $codeMap[$code].Name
        Action = "BUY"; Price = $slippedPrice; Shares = $shares
        Amount = -$actualAmount; Commission = $commission; StampTax = 0
        TotalCost = -$totalCost; Reason = $yaoziReason
        Source = "manual$overrideMarkBuy"; AnalysisSummary = $yaoziSummary
        EntryPrediction = $evalStock.Prediction.Short; DataSource = $(if ($quote -and $quote.DataSource) { $quote.DataSource } else { "[评估数据]" })
    }
    $positions.Cash = [Math]::Round($positions.Cash - $totalCost, 2)
    $avgCost = [Math]::Round($totalCost / $shares, 2)
    $stockMap[$code] = [PSCustomObject]@{
        Code = $code; Name = $codeMap[$code].Name
        Shares = $shares; AvgCost = $avgCost; CurrentPrice = $entryPrice
        EntryDate = $Date; EntryScore = $evalStock.Scores.Composite
        EntryShortPrediction = $evalStock.Prediction.Short
        StopLoss = $evalStock.KeyLevels.StopLoss
        Support = $evalStock.KeyLevels.Support
        Resistance = $evalStock.KeyLevels.Resistance
        UnrealizedPnL = 0; UnrealizedPnLPct = 0
    }
    $yaoziExecuted[$code] = $true
    Write-Log "  $code 腰子BUY: $shares x $slippedPrice = $actualAmount, 理由: $yaoziReason"
}

foreach ($code in $codeMap.Keys) {
    $evalStock = $stocks[$code]
    if (-not $evalStock) { continue }

    if ($stockMap[$code] -and $stockMap[$code].Shares -gt 0) {
        Write-Log "  $code 已有持仓，跳过"
        continue
    }

    if ($evalStock.Prediction.Short -ne "看多" -and $evalStock.Prediction.Short -ne "偏多") {
        Write-Log "  $code Short=$($evalStock.Prediction.Short)，非看多/偏多，跳过"
        continue
    }

    $th = $evalStock.TrendHealth.Label
    if ($th -eq "危险" -or $th -eq "数据不足") {
        Write-Log "  $code TrendHealth=$th，跳过"
        continue
    }

    $existingPos = $stockMap[$code]
    # 冷却检查：当前持仓 → 持久化 Cooldowns → 跨系统共享 Cooldowns (流金 v2026-05-24)
    $coolSource = if ($existingPos) { $existingPos } elseif ($cooldowns[$code]) { $cooldowns[$code] } elseif ($sharedCooldowns[$code]) { $sharedCooldowns[$code] } else { $null }
    if ($coolSource -and $coolSource.LastStopLossDate) {
        $coolDays = Get-CoolingDays -DateStr $coolSource.LastStopLossDate
        if ($coolDays -lt $config.CooloffPeriodDays) {
            Write-Log "  $code 止损冷却期($coolDays/$($config.CooloffPeriodDays)日)，跳过"
            continue
        }
    }

    if ($coolSource -and $coolSource.LastFullTakeProfitDate) {
        $coolDays = Get-CoolingDays -DateStr $coolSource.LastFullTakeProfitDate
        if ($coolDays -lt $config.FullTakeProfitCooldownDays) {
            Write-Log "  $code 止盈冷却期($coolDays/$($config.FullTakeProfitCooldownDays)日)，跳过"
            continue
        }
    }

    $quote = $quotes[$code]
    if ($quote -and $quote.ChangePct -ne 999 -and (Test-IsLimitUp -ChangePct $quote.ChangePct -Board $codeMap[$code].Board)) {
        Write-Log "  $code 涨停(涨跌幅$($quote.ChangePct)%)，跳过开仓" "WARN"
        continue
    }

    if (-not $evalStock.KeyLevels) {
        Write-Log "  $code KeyLevels 数据缺失，跳过开仓" "WARN"
        continue
    }
    if ($evalStock.KeyLevels.StopLoss -ge $evalStock.Price) {
        Write-Log "  $code StopLoss($($evalStock.KeyLevels.StopLoss)) >= Price($($evalStock.Price))，跳过开仓" "WARN"
        continue
    }

    $candidates += [PSCustomObject]@{
        Code = $code
        Name = $codeMap[$code].Name
        CompositeScore = $evalStock.Scores.Composite
        Confidence = $evalStock.Prediction.Confidence
        ShortBull = $evalStock.Prediction.ShortBull
    }
    Write-Log "  $code 候选开仓: 评分=$($evalStock.Scores.Composite) 置信度=$($evalStock.Prediction.Confidence)"
}

# 多股选股优先级排序
if ($candidates.Count -gt 0) {
    $confMap = @{ "高(>70%)" = 3; "中(50-70%)" = 2; "低(<50%)" = 1 }
    $candidates = $candidates | Sort-Object -Property @{
        Expression = { -$_.CompositeScore }
    }, @{
        Expression = { if ($confMap.ContainsKey($_.Confidence)) { -$confMap[$_.Confidence] } else { 0 } }
    }, @{
        Expression = { -$_.ShortBull }
    }

    $currentPosCount = ($stockMap.Values | Where-Object { $_.Shares -gt 0 }).Count
    $slotsAvailable = $config.MaxPositions - $currentPosCount
    if ($slotsAvailable -le 0) {
        Write-Log "持仓已满($currentPosCount/$($config.MaxPositions))，不开新仓"
    } else {
        $candidates = $candidates | Select-Object -First $slotsAvailable
        Write-Log "可用仓位: $slotsAvailable, 前${slotsAvailable}只: $($candidates.Name -join ', ')"

        foreach ($cand in $candidates) {
            $code = $cand.Code
            $evalStock = $stocks[$code]
            $quote = $quotes[$code]

            $entryPrice = 0
            $buyDataSource = ""
            if ($quote -and $quote.OpenPrice -gt 0) {
                $entryPrice = $quote.OpenPrice
                $buyDataSource = if ($quote.DataSource) { $quote.DataSource } else { "[1]" }
            } elseif ($quote -and $quote.PrevClose -gt 0) {
                $entryPrice = $quote.PrevClose
                $buyDataSource = "[昨收价]"
                Write-Log "  $code 开盘价不可用，使用API昨收价 $entryPrice" "WARN"
            } elseif ($evalStock.Price -gt 0) {
                $entryPrice = $evalStock.Price
                $buyDataSource = "[评估数据]"
                Write-Log "  $code 开盘价+昨收均不可用，使用评估数据价 $entryPrice" "WARN"
            } else {
                Write-Log "  $code 无法获取入场价" "WARN"
                continue
            }
            $entryPrice = [Math]::Round($entryPrice * (1 + $config.SlippagePct / 100), 2)

            $posPct = Get-PositionSize -Score $evalStock.Scores.Composite
            $posAmount = [Math]::Round($positions.Cash * $posPct / 100, 2)

            $maxAmount = [Math]::Round($positions.TotalValue * $config.SingleStockLimitPct / 100, 2)
            if ($posAmount -gt $maxAmount) { $posAmount = $maxAmount }

            $shares = [Math]::Floor($posAmount / $entryPrice / 100) * 100
            if ($shares -lt 100) {
                Write-Log "  $code 计算股数不足一手(100股)，跳过" "WARN"
                continue
            }

            $actualAmount = [Math]::Round($shares * $entryPrice, 2)
            $commission = Calc-Commission -Amount $actualAmount
            $totalCost = $actualAmount + $commission

            if ($totalCost -gt $positions.Cash) {
                Write-Log "  $code 资金不足: 需¥$totalCost 可用¥$($positions.Cash)" "WARN"
                continue
            }

            $txns += [PSCustomObject]@{
                Date = $Date; Code = $code; Name = $cand.Name
                Action = "BUY"; Price = $entryPrice; Shares = $shares
                Amount = -$actualAmount; Commission = $commission; StampTax = 0
                TotalCost = -$totalCost; Reason = "开仓_$($evalStock.Prediction.Short)_$($evalStock.TrendHealth.Label)"
                EntryPrediction = $evalStock.Prediction.Short
                DataSource = $buyDataSource
            }

            # 买入后扣减现金
            $positions.Cash = [Math]::Round($positions.Cash - $totalCost, 2)

            $newPos = [PSCustomObject]@{
                Code = $code
                Name = $cand.Name
                Shares = $shares
                AvgCost = [Math]::Round($totalCost / $shares, 2)
                CurrentPrice = $entryPrice
                EntryDate = $Date
                EntryShortPrediction = $evalStock.Prediction.Short
                LastStopLossDate = $null
                LastFullTakeProfitDate = $null
                Support = $evalStock.KeyLevels.Support
                Resistance = $evalStock.KeyLevels.Resistance
                StopLoss = $evalStock.KeyLevels.StopLoss
                UnrealizedPnL = 0
                UnrealizedPnLPct = 0
            }
            $stockMap[$code] = $newPos

            Write-Log "  $code 开仓: $shares 股 x ¥$entryPrice = ¥${actualAmount}, 仓位${posPct}%"
        }
    }
} else {
    Write-Log "无符合开仓条件的股票"
}
}  # 关闭 if (-not $skipOpenNewPositions) else 块

# ---- Step 10: 写入交易流水（幂等：防重复写入）----
if ($txns.Count -gt 0 -and -not $DryRun) {
    $existingTxns = @()
    $existingFingerprints = @{}
    $txnReadPath = if (Test-Path $txnFile) { $txnFile } elseif (Test-Path $legacyTxnFile) { $legacyTxnFile } else { $null }
    if ($txnReadPath) {
        $existingContent = Get-Content $txnReadPath -Raw
        if ($existingContent.Trim().Length -gt 0) {
            $allExisting = $existingContent.Trim() -split "`n"
            $existingTxns = $allExisting | Select-Object -Skip 1
            # 构建指纹集合(date|code|action|shares)用于防重
            foreach ($line in $existingTxns) {
                $parts = $line -split ','
                if ($parts.Count -ge 5) {
                    $fp = "$($parts[0])|$($parts[1])|$($parts[3])|$($parts[4])"  # date|code|action|shares
                    if (-not $existingFingerprints.ContainsKey($fp)) {
                        $existingFingerprints[$fp] = @()
                    }
                    $existingFingerprints[$fp] += $line
                }
            }
        }
    }
    $header = "date,code,name,action,price,shares,amount,commission,stamp_tax,total_cost,reason,entry_prediction,data_source,source,analysis_summary"
    $newLines = @()
    $dupCount = 0
    foreach ($txn in $txns) {
        $txnSource = if ($txn.Source) { $txn.Source } else { "auto" }
        $txnAnalysis = if ($txn.AnalysisSummary) { $txn.AnalysisSummary } else { "" }
        $line = "{0},{1},{2},{3},{4},{5},{6},{7},{8},{9},{10},{11},{12},{13},{14}" -f
            $txn.Date, $txn.Code, $txn.Name, $txn.Action,
            $txn.Price, $txn.Shares, $txn.Amount, $txn.Commission,
            $txn.StampTax, $txn.TotalCost, $txn.Reason, $txn.EntryPrediction,
            $(if ($txn.DataSource) { $txn.DataSource } else { "[评估数据]" }),
            $txnSource, $txnAnalysis
        $fp = "$($txn.Date)|$($txn.Code)|$($txn.Action)|$($txn.Shares)"
        # 同日同股同操作同股数 → 跳过（已经写入过）
        if ($existingFingerprints.ContainsKey($fp)) {
            Write-Log "  ⚠ $($txn.Code) $($txn.Action) 今日已有记录，跳过重复写入" "WARN"
            $dupCount++
        } else {
            $newLines += $line
        }
    }
    if ($newLines.Count -gt 0) {
        $allLines = @($header) + $existingTxns + $newLines
        $allLines | Set-Content -Encoding UTF8 $txnFile
        Assert-WriteSuccess -Path $txnFile
        Write-Log "交易流水已写入: $($newLines.Count) 条 (跳过${dupCount}条重复)"
    } else {
        Write-Log "交易流水无新增 (${dupCount}条全部重复，已跳过)" "INFO"
    }
}

# ---- Step 11: 更新持仓文件 ----
$posObj = @{}
foreach ($kv in $stockMap.GetEnumerator()) {
    if ($kv.Value.Shares -gt 0) {
        $posObj[$kv.Key] = $kv.Value
    }
}
$positions.Cash = $positions.Cash
$positions.TotalValue = $positions.Cash
$positions.LastUpdated = $Date

$stockValue = 0
foreach ($kv in $posObj.GetEnumerator()) {
    $p = $kv.Value
    $currentP = $p.CurrentPrice
    $q = $quotes[$kv.Key]
    if ($q -and $q.Price -gt 0) {
        $currentP = $q.Price
        $p.CurrentPrice = $currentP
    }
    $p.UnrealizedPnL = [Math]::Round(($currentP - $p.AvgCost) * $p.Shares, 2)
    $p.UnrealizedPnLPct = [Math]::Round(($currentP / $p.AvgCost - 1) * 100, 2)
    $stockValue += $currentP * $p.Shares
}
$positions.TotalValue = [Math]::Round($positions.Cash + $stockValue, 2)

if (-not $DryRun) {
    $posOutput = @{ Cash = $positions.Cash; TotalValue = $positions.TotalValue; LastUpdated = $Date; Positions = $posObj; Cooldowns = $cooldowns; Watchlist = $watchlist }
    $posOutput | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 $positionsFile
    Assert-WriteSuccess -Path $positionsFile
    Write-Log "持仓已更新"

    # Shared cooldowns sync (流金 v2026-05-24)
    $sharedDir = Join-Path $simDir "共享模块/shared"
    if (-not (Test-Path $sharedDir)) { New-Item $sharedDir -ItemType Directory -Force | Out-Null }
    if ($sharedCooldowns.Count -gt 0) {
        $sharedCooldowns | ConvertTo-Json -Depth 3 | Set-Content -Encoding UTF8 $sharedCooldownsFile
    }

    # 更新腰子指令状态 (Phase 1 指令通道)
    if ($hasYaoziInstructions -and (Test-Path $InstructionFile)) {
        try {
            $yaoziUpdate = Get-Content $InstructionFile -Raw -Encoding UTF8 | ConvertFrom-Json
            $updatedDecisions = @()
            foreach ($d in $yaoziUpdate.decisions) {
                $code = $d.code
                if ($yaoziExecuted.ContainsKey($code)) {
                    $d | Add-Member -MemberType NoteProperty -Name "status" -Value "queued" -Force
                    $d | Add-Member -MemberType NoteProperty -Name "executed_at" -Value (Get-Date -Format "yyyy-MM-ddTHH:mm:ss") -Force
                }
                $updatedDecisions += $d
            }
            $yaoziUpdate | Add-Member -MemberType NoteProperty -Name "decisions" -Value $updatedDecisions -Force
            $yaoziUpdate | Add-Member -MemberType NoteProperty -Name "engine_processed_at" -Value (Get-Date -Format "yyyy-MM-ddTHH:mm:ss") -Force
            $yaoziUpdate | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 $InstructionFile
            Write-Log "腰子指令状态已更新: executed=$($yaoziExecuted.Count)"
        } catch {
            Write-Log "腰子指令状态更新失败: $_" "WARN"
        }
    }
}

# ---- Step 12: 每日快照 ----
$dailyReturn = 0
$totalReturn = 0
$prevSnapshot = $null
$prevDate = $scriptDateObj.AddDays(-1).ToString("yyyyMMdd")
$prevSnapshotCanon = Join-Path $canonBase "01_交易快照/snapshot_${prevDate}.json"
$prevSnapshotLegacy = Join-Path $simDir "每日快照/snapshot_${prevDate}.json"
$prevSnapshotFile = if (Test-Path $prevSnapshotCanon) { $prevSnapshotCanon } elseif (Test-Path $prevSnapshotLegacy) { $prevSnapshotLegacy } else { $prevSnapshotCanon }
if (Test-Path $prevSnapshotFile) {
    try { $prevSnapshot = Get-Content $prevSnapshotFile -Raw | ConvertFrom-Json } catch { Write-Error "前日快照文件解析失败: $_"; exit 1 }
    if ($prevSnapshot.TotalValue -gt 0) {
        $dailyReturn = [Math]::Round(($positions.TotalValue / $prevSnapshot.TotalValue - 1) * 100, 2)
    }
}
$totalReturn = [Math]::Round(($positions.TotalValue / $config.InitialCapital - 1) * 100, 2)

$benchmarkVal = $null
if ($config.Benchmark.Enabled -and $benchData) {
    $benchVal = $benchData.Price
    $perfReadPath1 = if (Test-Path $perfFile) { $perfFile } elseif (Test-Path $legacyPerfFile) { $legacyPerfFile } else { $null }
    if ($perfReadPath1) { try { $perfSummary = Get-Content $perfReadPath1 -Raw -Encoding UTF8 | ConvertFrom-Json } catch { Write-Error "绩效文件解析失败: $_"; exit 1 } }
    if (-not $perfSummary) {
        $perfSummary = [PSCustomObject]@{ StartDate = $Date; InitialCapital = $config.InitialCapital; CurrentValue = $positions.TotalValue; TotalReturnPct = 0; MaxDrawdown = 0; IsDrawdownAlert = $false }
    }
    if (-not $perfSummary.Benchmark) {
        $perfSummary | Add-Member -MemberType NoteProperty -Name "Benchmark" -Value @{ Code = $config.Benchmark.Code; Name = $config.Benchmark.Name; InitialValue = $null } -Force
    }
    if (-not $perfSummary.Benchmark.InitialValue) {
        $perfSummary.Benchmark.InitialValue = $benchVal
    }
    $initB = $perfSummary.Benchmark.InitialValue
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
        @{ Code = $_.Code; Name = $_.Name; Shares = $_.Shares; AvgCost = $_.AvgCost; CurrentPrice = $_.CurrentPrice; UnrealizedPnL = $_.UnrealizedPnL; UnrealizedPnLPct = $_.UnrealizedPnLPct }
    })
    Benchmark = $benchmarkVal
}
if (-not $DryRun) {
    $snapshot | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 $snapshotFile
    Assert-WriteSuccess -Path $snapshotFile
    Write-Log "快照已写入: $snapshotFile"
}

# ---- Step 13: 更新绩效汇总 ----
if (-not $perfSummary) {
    $perfReadPath2 = if (Test-Path $perfFile) { $perfFile } elseif (Test-Path $legacyPerfFile) { $legacyPerfFile } else { $null }
    if ($perfReadPath2) { try { $perfSummary = Get-Content $perfReadPath2 -Raw -Encoding UTF8 | ConvertFrom-Json } catch { Write-Error "绩效文件解析失败: $_"; exit 1 } }
    if (-not $perfSummary) {
        Write-Log "绩效文件不存在，初始化默认" "WARN"
        $perfSummary = [PSCustomObject]@{
            StartDate = $null; InitialCapital = $config.InitialCapital
            CurrentValue = $positions.TotalValue; TotalReturnPct = 0
            MaxDrawdown = 0; MaxDrawdownDate = $null; PeakValue = $positions.TotalValue
            TotalTrades = 0; WinningTrades = 0; LosingTrades = 0; WinRate = 0
            ConsecutiveLosses = 0; IsDrawdownAlert = $false
        }
    } elseif (-not $perfSummary.PeakValue) {
        $perfSummary | Add-Member -MemberType NoteProperty -Name "PeakValue" -Value $positions.TotalValue -Force
    }
}
$perfSummary.CurrentValue = $positions.TotalValue
$perfSummary.TotalReturnPct = $totalReturn
if (-not $perfSummary.StartDate) { $perfSummary.StartDate = $Date }

# 跟踪历史峰值并计算最大回撤（从历史峰值算起，而非仅前一交易日）
if (-not $perfSummary.PeakValue) {
    $perfSummary | Add-Member -MemberType NoteProperty -Name "PeakValue" -Value $positions.TotalValue -Force
}
if ($positions.TotalValue -gt $perfSummary.PeakValue) {
    $perfSummary.PeakValue = $positions.TotalValue
}
$currentDD = [Math]::Round(($positions.TotalValue / $perfSummary.PeakValue - 1) * 100, 2)
if ($currentDD -lt $perfSummary.MaxDrawdown) {
    $perfSummary.MaxDrawdown = $currentDD
    $perfSummary.MaxDrawdownDate = $Date
}

$allTxns = @()
$txnReadPath2 = if (Test-Path $txnFile) { $txnFile } elseif (Test-Path $legacyTxnFile) { $legacyTxnFile } else { $null }
if ($txnReadPath2) {
    $txnContent = Get-Content $txnReadPath2 -Raw
    if ($txnContent.Trim().Length -gt 0) {
        $allTxns = Import-Csv $txnReadPath2 | ForEach-Object {
            [PSCustomObject]@{
                Date = $_.date
                Code = $_.code
                Action = $_.action
                Amount = [double]$_.amount
            }
        }
    }
}

# BUG-03: 按时间顺序配对而非按股票代码聚合，支持多轮买卖分别结算
$winCount = 0; $loseCount = 0; $consecLosses = 0

# 按股票代码分组，组内按日期排序后逐笔配对（FIFO）
$groupedTxns = $allTxns | Group-Object Code

foreach ($group in $groupedTxns) {
    $txns = $group.Group | Sort-Object Date
    $positionCost = 0  # 当前持仓成本（负值=已投入资金）

    foreach ($t in $txns) {
        if ($t.Action -eq "BUY") {
            $positionCost += $t.TotalCost  # TotalCost为负（含佣金，资金流出）
        } elseif ($t.Action -eq "SELL_HALF") {
            # BUG-02: SELL_HALF 仅减少持仓成本，不计入完整交易结算
            $positionCost += $t.TotalCost  # TotalCost为正（含佣金+印花税，资金流入）
            if ($positionCost -gt 0) { $positionCost = 0 }  # 防溢出封顶
        } elseif ($t.Action -eq "SELL") {
            # 完整卖出 = 平仓结算一笔完整交易
            $netPnL = $t.TotalCost + $positionCost  # 净所得 + 剩余持仓成本（负值）
            if ($netPnL -gt 0) { $winCount++; $consecLosses = 0 } else { $loseCount++; $consecLosses++ }
            $positionCost = 0  # 仓位已清
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
$perfSummary.IsDrawdownAlert = ($perfSummary.MaxDrawdown -lt -8)
if ($benchmarkVal) { $perfSummary.Benchmark = $benchmarkVal }

# ---- 更新 RiskMetrics 子对象（白皮书 §3.2.4 规范） ----
$stopLossDistances = @()
$currentPositions = $stockMap.Values | Where-Object { $_.Shares -gt 0 }
foreach ($p in $currentPositions) {
    if ($p.AvgCost -and $p.AvgCost -gt 0 -and $p.StopLoss -and $p.StopLoss -gt 0) {
        $dist = [Math]::Round(($p.AvgCost - $p.StopLoss) / $p.AvgCost * 100, 2)
        $stopLossDistances += $dist
    }
}
$avgStopDist = if ($stopLossDistances.Count -gt 0) { [Math]::Round(($stopLossDistances | Measure-Object -Average).Average, 2) } else { $null }

$riskMetrics = [PSCustomObject]@{
    MaxDrawdown          = $perfSummary.MaxDrawdown
    MaxDrawdownDate      = $perfSummary.MaxDrawdownDate
    AvgStopLossDistance  = $avgStopDist
    ConsecutiveLosses    = $perfSummary.ConsecutiveLosses
    SharpeRatio          = $null   # 前20日无数据
    InformationRatio     = $null
    IsDrawdownAlert      = $perfSummary.IsDrawdownAlert
    CurrentDrawdown      = $currentDD
    AvgWinPct            = $null   # 需要逐笔统计
    AvgLossPct           = $null
    ProfitFactor         = $null
}
$perfSummary | Add-Member -MemberType NoteProperty -Name "RiskMetrics" -Value $riskMetrics -Force

# ---- 更新 PerStock 子对象 ----
$perStock = @{}
if ($perfSummary.PerStock) {
    $perfSummary.PerStock.PSObject.Properties | ForEach-Object { $perStock[$_.Name] = $_.Value }
}
foreach ($p in $currentPositions) {
    $code = $p.Code
    if (-not $perStock.ContainsKey($code)) {
        $perStock[$code] = @{
            Name              = $p.Name
            Trades            = 0
            WinRate           = $null
            TotalPnL          = $p.UnrealizedPnL
            UnrealizedPnL     = $p.UnrealizedPnL
            UnrealizedPnLPct  = $p.UnrealizedPnLPct
            CurrentShares     = $p.Shares
        }
    } else {
        $perStock[$code].UnrealizedPnL    = $p.UnrealizedPnL
        $perStock[$code].UnrealizedPnLPct = $p.UnrealizedPnLPct
        $perStock[$code].CurrentShares    = $p.Shares
    }
}
# 清除不再持仓且无历史交易的 PerStock 条目
$codesToRemove = @()
foreach ($code in $perStock.Keys) {
    $pos = $stockMap[$code]
    if ((-not $pos -or $pos.Shares -le 0) -and $perStock[$code].Trades -eq 0) {
        $codesToRemove += $code
    }
}
foreach ($code in $codesToRemove) { $perStock.Remove($code) }

$perfSummary | Add-Member -MemberType NoteProperty -Name "PerStock" -Value ([PSCustomObject]$perStock) -Force

if (-not $DryRun) {
    $jsonStr = $perfSummary | ConvertTo-Json -Depth 5
    [System.IO.File]::WriteAllText($perfFile, $jsonStr, [System.Text.UTF8Encoding]::new($false))
    Assert-WriteSuccess -Path $perfFile
    # S级资产镜像备份
    if (Test-Path $canonBackupDir) {
        $backupPerf = Join-Path $canonBackupDir "perf_summary.json"
        [System.IO.File]::WriteAllText($backupPerf, $jsonStr, [System.Text.UTF8Encoding]::new($false))
    }
}

# ---- Step 14: 控制台简报 ----
Write-Log ""
Write-Log "===== 模拟交易日报 ${Date} ====="
Write-Log "组合净值: ¥$($positions.TotalValue) (日盈亏 $($dailyReturn)% | 累计 $($totalReturn)%)"
if ($benchmarkVal) {
    Write-Log "基准: $($benchmarkVal.BenchmarkReturnPct)% | 超额: $($benchmarkVal.ExcessReturnPct)%"
}
$posCount = ($posObj.Values | Measure-Object).Count
$totalPct = [Math]::Round($stockValue / $positions.TotalValue * 100, 1)
Write-Log "持仓: ${posCount}/$($config.MaxPositions) 只 | 仓位 ${totalPct}% | 最大回撤: $($perfSummary.MaxDrawdown)%"
Write-Log "交易胜率: $($perfSummary.WinRate)% ($winCount胜/$loseCount负)"

if ($posObj.Count -gt 0) {
    Write-Log ""
    Write-Log ($posObj.Values | ForEach-Object {
        $p = $_; $sign = if ($p.UnrealizedPnLPct -ge 0) { "+" } else { "" }
        "  $($p.Name) $($p.Shares)股 成本¥$($p.AvgCost) 现价¥$($p.CurrentPrice) 浮动${sign}$($p.UnrealizedPnLPct)%"
    } | Out-String).Trim()
}

if ($txns.Count -gt 0) {
    Write-Log ""
    foreach ($t in $txns) {
        $actionText = if ($t.Action -eq "BUY") { "买入" } elseif ($t.Action -eq "SELL") { "卖出" } else { "减仓" }
        $sign = if ($t.Amount -ge 0) { "+" } else { "" }
        Write-Log "  ${actionText} $($t.Name): $($t.Shares)股 x ¥$($t.Price) = ${sign}¥$($t.Amount) | $($t.Reason)"
    }
}

Write-Log "===== END ====="

Write-Log "[DONE]"

if (-not $DryRun) {
    $logContent = $logLines -join "`n"
    $logContent | Out-File -Encoding utf8 (Join-Path $logDir "sim_${Date}.log")
    Assert-WriteSuccess -Path (Join-Path $logDir "sim_${Date}.log")

    # S级资产镜像备份 (情墨 06-数据持久化架构)
    if (Test-Path $canonBackupDir) {
        foreach ($asset in @("positions.json", "transactions.csv")) {
            $srcAsset = Join-Path $canonBase "00_核心交易/$asset"
            $dstAsset = Join-Path $canonBackupDir $asset
            if (Test-Path $srcAsset) {
                Copy-Item $srcAsset $dstAsset -Force
                $srcHash = (Get-FileHash $srcAsset -Algorithm SHA256).Hash
                $dstHash = (Get-FileHash $dstAsset -Algorithm SHA256).Hash
                if ($srcHash -ne $dstHash) {
                    Write-Warning "S级资产备份校验失败: $asset"
                }
            }
        }
    }
}
