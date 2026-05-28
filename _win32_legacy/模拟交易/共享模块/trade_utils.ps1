# ============================================================
# trade_utils.ps1 — 交易工具函数共享模块
# 费用计算 / 交易日计数 / 涨跌停检测 / 卖单计算 / 数据验证
# 两个模拟交易赛道共用
# ============================================================

# ---- 费用计算 ----
function Calc-Commission {
    param([double]$Amount, [double]$Rate = 0.00025, [double]$MinFee = 5.0)
    $fee = [Math]::Abs($Amount) * $Rate
    if ($fee -lt $MinFee) { $fee = $MinFee }
    return [Math]::Round($fee, 2)
}

function Calc-StampTax {
    param([double]$Amount, [double]$Rate = 0.001, [bool]$IsSell = $true, [bool]$OnSellOnly = $true)
    if ($OnSellOnly -and -not $IsSell) { return 0 }
    return [Math]::Round($Amount * $Rate, 2)
}

# ---- 交易日计算 ----
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

function Get-CoolingDays {
    param([string]$DateStr, [string]$TodayStr)
    if (-not $DateStr) { return 999 }
    $d1 = [datetime]::ParseExact($TodayStr, "yyyyMMdd", $null)
    $d2 = [datetime]::ParseExact($DateStr, "yyyyMMdd", $null)
    return Get-TradingDaysBetween -StartDate $d2 -EndDate $d1
}

# ---- 涨跌停检测 ----
function Get-BoardLimit {
    param([string]$Code)
    if ($Code -match '^30[0-9]|^68[0-9]') { return 19.4 }  # 创业板/科创板
    return 9.4  # 主板
}

function Test-IsLimitUp {
    param([double]$ChangePct, [string]$Code = "")
    $limit = Get-BoardLimit -Code $Code
    return $ChangePct -ge $limit
}

function Test-IsLimitDown {
    param([double]$ChangePct, [string]$Code = "")
    $limit = Get-BoardLimit -Code $Code
    return $ChangePct -le -$limit
}

# ---- 卖单计算 ----
function Get-SellProceeds {
    param(
        [double]$Price, [int]$Shares,
        [double]$CommissionRate = 0.00025, [double]$MinCommission = 5.0,
        [double]$StampTaxRate = 0.001, [bool]$OnSellOnly = $true
    )
    $amount = [Math]::Round($Price * $Shares, 2)
    $commission = Calc-Commission -Amount $amount -Rate $CommissionRate -MinFee $MinCommission
    $stampTax = Calc-StampTax -Amount $amount -Rate $StampTaxRate -IsSell $true -OnSellOnly $OnSellOnly
    return @{
        Amount = $amount
        Commission = $commission
        StampTax = $stampTax
        NetProceeds = $amount - $commission - $stampTax
    }
}

# ---- 买入成本计算 ----
function Get-BuyCost {
    param(
        [double]$Price, [int]$Shares,
        [double]$CommissionRate = 0.00025, [double]$MinCommission = 5.0,
        [double]$SlippagePct = 0.1
    )
    $slippedPrice = [Math]::Round($Price * (1 + $SlippagePct / 100), 2)
    $amount = [Math]::Round($slippedPrice * $Shares, 2)
    $commission = Calc-Commission -Amount $amount -Rate $CommissionRate -MinFee $MinCommission
    return @{
        Price = $slippedPrice
        Amount = $amount
        Commission = $commission
        TotalCost = $amount + $commission
    }
}

# ---- 仓位分档 ----
function Get-PositionSize {
    param([double]$Score, [array]$Tiers)
    foreach ($tier in $Tiers) {
        if ($Score -ge $tier.MinScore) { return [double]$tier.Ratio }
    }
    return 0
}

# ---- 文件写入验证 ----
function Assert-WriteSuccess {
    param([string]$Path, [datetime]$BeforeWrite)
    if (-not (Test-Path $Path)) {
        Write-Error "写入失败(文件不存在): $Path"
        exit 1
    }
    if ($BeforeWrite) {
        $actualWriteTime = (Get-Item $Path).LastWriteTime
        if ($actualWriteTime -le $BeforeWrite) {
            Write-Error "写入失败(时间戳未更新): $Path (before=$BeforeWrite, actual=$actualWriteTime)"; exit 1
        }
    }
}

# ---- 节假日检测 ----
function Test-IsTradingDay {
    param([string]$Date)
    $dt = [datetime]::ParseExact($Date, "yyyyMMdd", $null)
    $dow = $dt.DayOfWeek
    if ($dow -eq "Saturday" -or $dow -eq "Sunday") { return $false }

    $holidays2026 = @(
        "20260101",
        "20260217","20260218","20260219",
        "20260404","20260405","20260406",
        "20260501","20260502","20260503",
        "20260619","20260620","20260621",
        "20261001","20261002","20261003","20261004","20261005","20261006","20261007"
    )
    if ($holidays2026 -contains $Date) { return $false }
    return $true
}

# ---- MA交叉检测 ----
function Test-MACrossover {
    param([double]$MA5, [double]$MA20, [double]$PrevMA5, [double]$PrevMA20)
    # 返回 $true 表示 MA5 下穿 MA20（趋势破坏）
    if ($MA5 -le 0 -or $MA20 -le 0 -or $PrevMA5 -le 0 -or $PrevMA20 -le 0) { return $false }
    return ($MA5 -lt $MA20) -and ($PrevMA5 -ge $PrevMA20)
}

# ---- RSI 持续检测 ----
function Test-RSIPersistent {
    param([double]$CurrentRSI, [double]$PrevRSI, [double]$Threshold = 80)
    if ($CurrentRSI -le 0 -or $PrevRSI -le 0) { return $false }
    return ($CurrentRSI -gt $Threshold) -and ($PrevRSI -gt $Threshold)
}
