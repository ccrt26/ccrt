# 铁律量化 - 模拟交易参数回测工具
# 回放历史出场数据，用新参数重新计算出场决策
#
# 用途：
#   比较不同 FixedPct1(FixedPct2) 参数对历史交易的绩效影响
#   支持 P1(止损)、P4(全部止盈R3)、P5(止盈减仓R2) 的重新判定
#   自动配对买入/卖出交易，逐笔核算手续费和印花税
#
# 限制：
#   仅能回测出场规则中与价格相关的部分（P1/P4/P5）
#   P2(趋势恶化) 和 P3(预判转空) 依赖每日评估数据，无法回放
#   开仓决策依赖评估数据，同样无法回放（假定历史开仓不变）
#
# 用法:
#   .\param_backtest.ps1
#   .\param_backtest.ps1 -Interactive
#   .\param_backtest.ps1 -CustomParams @{ "保守" = @{ Pct1=4; Pct2=8 }; "激进" = @{ Pct1=6; Pct2=12 } }
#   .\param_backtest.ps1 -ConfigOverride @{ Pct1=5.5; Pct2=11 }

param(
    [string]$HistoryDir = "",
    [string]$OriginalConfig = "",
    [string]$OutputDir = "",
    [switch]$Interactive,
    [hashtable]$CustomParams = $null,
    [hashtable]$ConfigOverride = $null
)

$rootDir = "C:\Users\34269\Documents\Claude\股票分析"

# ---- 默认路径 ----
if (-not $HistoryDir) { $HistoryDir = Join-Path $rootDir "模拟交易/绩效" }
if (-not $OriginalConfig) { $OriginalConfig = Join-Path $rootDir "模拟交易/sim_config.json" }
if (-not $OutputDir) { $OutputDir = Join-Path $rootDir "模拟交易/工具/回测结果" }

# 确保输出目录存在
if (-not (Test-Path $OutputDir)) { New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null }

# ============================================================
# 辅助函数
# ============================================================

function Write-Header {
    param([string]$Text)
    Write-Host "`n=== $Text ===" -ForegroundColor Cyan
}

function Write-Result {
    param([string]$Text, [string]$Color="Gray")
    Write-Host "  $Text" -ForegroundColor $Color
}

# 费用计算（与 sim_trading.ps1 一致）
function Calc-Commission {
    param([double]$Amount, [double]$Rate, [double]$MinFee)
    $fee = [Math]::Abs($Amount) * $Rate
    if ($fee -lt $MinFee) { $fee = $MinFee }
    return [Math]::Round($fee, 2)
}

function Calc-StampTax {
    param([double]$Amount, [double]$Rate)
    return [Math]::Round([Math]::Abs($Amount) * $Rate, 2)
}

# R2/R3 计算（方案B：固定百分比）
function Get-R2R3 {
    param([double]$EntryPrice, [double]$Pct1, [double]$Pct2)
    return @{
        R2 = [Math]::Round($EntryPrice * (1 + $Pct1 / 100), 2)
        R3 = [Math]::Round($EntryPrice * (1 + $Pct2 / 100), 2)
    }
}

# 判定出场类型（基于原始退出价格和仓位信息）
function Get-ExitType {
    param([double]$ExitPrice, [double]$EntryPrice, [double]$StopLoss, [double]$R2, [double]$R3, [string]$Reason)

    # 优先使用原始出场理由判断
    if ($Reason -match "止损|StopLoss") { return "P1止损" }
    if ($Reason -match "全部止盈|R3")    { return "P4全部止盈" }
    if ($Reason -match "止盈减仓|R2")   { return "P5止盈减仓" }
    if ($Reason -match "趋势恶化|危险")  { return "P2趋势恶化" }
    if ($Reason -match "预判转空|中性|看空") { return "P3预判转空" }

    # 用价格判定
    if ($ExitPrice -le $StopLoss) { return "P1止损(价格判定)" }
    if ($ExitPrice -ge $R3) { return "P4全部止盈(价格判定)" }
    if ($ExitPrice -ge $R2) { return "P5止盈减仓(价格判定)" }

    return "其他"
}

# 用新参数重新模拟出场决策
function Simulate-ExitWithNewParams {
    param(
        [double]$ExitPrice,
        [double]$EntryPrice,
        [double]$StopLoss,
        [double]$NewR2,
        [double]$NewR3,
        [string]$OriginalExitType
    )

    # 在新参数下，如果价格仍未触发 R2/R3，但实际已出场
    # 说明出场是由 P2/P3/人工 等其他原因导致的
    if ($ExitPrice -le $StopLoss) {
        # 止损不受参数影响
        return @{ NewExitType = "P1止损"; WouldHold = $false; TriggerAt = $StopLoss; Note = "止损价不变" }
    }

    if ($ExitPrice -ge $NewR3) {
        # 触发全部止盈
        $profitPct = [Math]::Round(($NewR3 / $EntryPrice - 1) * 100, 2)
        return @{ NewExitType = "P4全部止盈"; WouldHold = $false; TriggerAt = $NewR3; Note = "止盈${profitPct}%" }
    }

    if ($ExitPrice -ge $NewR2) {
        $profitPct = [Math]::Round(($NewR2 / $EntryPrice - 1) * 100, 2)
        return @{ NewExitType = "P5止盈减仓"; WouldHold = $false; TriggerAt = $NewR2; Note = "减仓${profitPct}%" }
    }

    # 在新参数下未触发任何价格出场条件
    # 检查实际出场价格是否超过了原参数 R2/R3 但新参数 R2/R3 更高

    if ($OriginalExitType -match "P4|P5|止盈") {
        # 原为价格止盈退出，但新参数门槛更高
        return @{
            NewExitType = "持有(原止盈未达标)"; WouldHold = $true; TriggerAt = $null
            Note = "原为$OriginalExitType，新参数R2=$NewR2/R3=$NewR3均未触及(出场价=$ExitPrice)"
        }
    }

    # 其他原因出场
    return @{
        NewExitType = "其他(同原出场)"; WouldHold = $false; TriggerAt = $ExitPrice
        Note = "出场原因不变: $OriginalExitType"
    }
}

# ============================================================
# 主流程
# ============================================================

Write-Host "===== 模拟交易参数回测工具 =====" -ForegroundColor Cyan
Write-Host "运行时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Gray

# ---- Step 1: 读取配置 ----
if (-not (Test-Path $OriginalConfig)) {
    Write-Error "配置文件不存在: $OriginalConfig"
    exit 1
}
try {
    $config = Get-Content $OriginalConfig -Raw -Encoding UTF8 | ConvertFrom-Json
} catch {
    Write-Error "无法解析配置文件 [${OriginalConfig}]: $_"
    exit 1
}

$origFixedPct1 = [double]$config.TakeProfit.FixedPct1
$origFixedPct2 = [double]$config.TakeProfit.FixedPct2
$commRate = [double]$config.Commission.Rate
$commMin = [double]$config.Commission.MinPerOrder
$stampRate = [double]$config.StampTax.Rate

Write-Host "`n原始配置参数:" -ForegroundColor Gray
Write-Host "  FixedPct1(R2)=${origFixedPct1}%, FixedPct2(R3)=${origFixedPct2}%" -ForegroundColor Gray
Write-Host "  手续费率=${commRate}, 最低=${commMin}, 印花税率=${stampRate}" -ForegroundColor Gray

# ---- Step 2: 如果指定了 ConfigOverride，临时修改参数 ----
$effectivePct1 = $origFixedPct1
$effectivePct2 = $origFixedPct2
if ($ConfigOverride) {
    if ($ConfigOverride.ContainsKey("Pct1")) { $effectivePct1 = [double]$ConfigOverride["Pct1"] }
    if ($ConfigOverride.ContainsKey("Pct2")) { $effectivePct2 = [double]$ConfigOverride["Pct2"] }
    Write-Host "`nConfigOverride 生效: FixedPct1=${effectivePct1}%, FixedPct2=${effectivePct2}%" -ForegroundColor Yellow
    $origFixedPct1 = $effectivePct1
    $origFixedPct2 = $effectivePct2
}

# ---- Step 3: 定义候选参数组合 ----
$paramSets = @()

# 默认 5 组
$defaultSets = @(
    @{ Name = "原始参数"; Pct1 = $origFixedPct1; Pct2 = $origFixedPct2 }
    @{ Name = "保守止盈"; Pct1 = [Math]::Round($origFixedPct1 - 1, 1); Pct2 = [Math]::Round($origFixedPct2 - 2, 1) }
    @{ Name = "积极止盈"; Pct1 = [Math]::Round($origFixedPct1 + 1, 1); Pct2 = [Math]::Round($origFixedPct2 + 2, 1) }
    @{ Name = "宽止损(抬R3)"; Pct1 = $origFixedPct1; Pct2 = [Math]::Round($origFixedPct2 + 5, 1) }
    @{ Name = "窄止损(降R3)"; Pct1 = $origFixedPct1; Pct2 = [Math]::Round($origFixedPct2 - 3, 1) }
)

# 使用自定义参数（如果有）
if ($CustomParams) {
    foreach ($key in $CustomParams.Keys) {
        $val = $CustomParams[$key]
        $defaultSets += @{ Name = $key; Pct1 = [double]$val.Pct1; Pct2 = [double]$val.Pct2 }
    }
}

# 交互模式：提示用户输入自定义参数
if ($Interactive) {
    Write-Host "`n[交互模式]" -ForegroundColor Yellow
    do {
        $resp = Read-Host "是否添加自定义参数组合？(y/n)"
    } while ($resp -notin @("y","n","Y","N"))

    while ($resp -eq "y" -or $resp -eq "Y") {
        $name = Read-Host "  参数组合名称"
        $p1 = [double](Read-Host "  FixedPct1 (%)")
        $p2 = [double](Read-Host "  FixedPct2 (%)")
        $defaultSets += @{ Name = $name; Pct1 = $p1; Pct2 = $p2 }
        Write-Host "  已添加: ${name} (${p1}%/${p2}%)" -ForegroundColor Green
        do {
            $resp = Read-Host "是否继续添加？(y/n)"
        } while ($resp -notin @("y","n","Y","N"))
    }
}

# 去重（相同 Pct1/Pct2 只保留第一个）
$seen = @{}
$paramSets = $defaultSets | Where-Object {
    $key = "$($_.Pct1)-$($_.Pct2)"
    if ($seen.ContainsKey($key)) { $false } else { $seen[$key] = $true; $true }
}

Write-Host "`n待测参数组合 ($($paramSets.Count) 组):" -ForegroundColor Gray
foreach ($ps in $paramSets) {
    Write-Host "  $($ps.Name): Pct1=$($ps.Pct1)%, Pct2=$($ps.Pct2)%" -ForegroundColor Gray
}

# ---- Step 4: 读取交易记录 ----
$txnFile = Join-Path $rootDir "模拟交易/持仓记录/transactions.csv"
if (-not (Test-Path $txnFile)) {
    Write-Host "`n[跳过] 交易记录不存在: $txnFile" -ForegroundColor Yellow
    Write-Host "请先积累至少几笔完整交易（买入+卖出）后再运行回测" -ForegroundColor Yellow
    exit 0
}

try {
    $allTxns = Import-Csv $txnFile -Encoding UTF8
} catch {
    Write-Error "无法读取交易记录: $_"
    exit 1
}

if ($allTxns.Count -eq 0) {
    Write-Host "`n[跳过] 交易记录为空" -ForegroundColor Yellow
    exit 0
}

Write-Host "`n读取交易记录: $($allTxns.Count) 条" -ForegroundColor Gray

# ---- Step 5: 读取当前持仓（用于获取止损价等数据） ----
$positionsFile = Join-Path $rootDir "模拟交易/持仓记录/positions.json"
$posMap = @{}
if (Test-Path $positionsFile) {
    try {
        $positions = Get-Content $positionsFile -Raw -Encoding UTF8 | ConvertFrom-Json
        $positions.Positions.PSObject.Properties | ForEach-Object { $posMap[$_.Name] = $_.Value }
        Write-Host "读取当前持仓: $($posMap.Count) 只" -ForegroundColor Gray
    } catch {
        Write-Host "警告: 无法解析持仓文件，止损价将缺失" -ForegroundColor Yellow
    }
}

# ---- Step 6: 按股票代码配对交易 ----
# 分组，组内按日期排序，BUY 与后续 SELL/SELL_HALF 逐笔配对（FIFO）
$grouped = $allTxns | Group-Object Code

# 配对结果：每笔完整交易 = 一次或多次 BUY -> 一次 SELL（或最终清仓）
$pairedTrades = @()

foreach ($group in $grouped) {
    $code = $group.Name
    $txns = $group.Group | Sort-Object Date

    $buyQueue = @()        # 等待配对的买入记录
    $currentShares = 0     # 当前持仓股数
    $currentCost = 0       # 当前持仓总成本（正数=已投入资金）
    $currentEntryDate = $null
    $currentEntryPrediction = $null

    foreach ($t in $txns) {
        $action = $t.action
        $price = [double]$t.price
        $shares = [int]$t.shares
        $amount = [double]$t.amount
        $reason = $t.reason

        if ($action -eq "BUY") {
            $buyQueue += @{
                Shares = $shares
                Price = $price
                Amount = -$amount  # amount 在 CSV 中为负，转正
                Date = $t.date
                Prediction = $t.entry_prediction
            }
            $currentShares += $shares
            $currentCost += (-$amount)  # 负的 amount = 实际支出
            $currentEntryDate = $t.date
            $currentEntryPrediction = $t.entry_prediction
        }
        elseif ($action -eq "SELL_HALF") {
            # 减仓：从最早买入中扣除
            $remainingToSell = $shares
            $soldCost = 0

            while ($remainingToSell -gt 0 -and $buyQueue.Count -gt 0) {
                $earliestBuy = $buyQueue[0]
                $sellFromThis = [Math]::Min($remainingToSell, $earliestBuy.Shares)
                $soldCost += $sellFromThis * $earliestBuy.Price
                $earliestBuy.Shares -= $sellFromThis
                $remainingToSell -= $sellFromThis
                if ($earliestBuy.Shares -le 0) { $buyQueue = $buyQueue | Select-Object -Skip 1 }
            }

            $currentShares -= $shares
            $currentCost -= $soldCost

            # 记录减仓事件（不结算完整交易）
        }
        elseif ($action -eq "SELL") {
            # 清仓：结算一笔完整交易
            $remainingToSell = $shares
            $totalBuyCost = 0
            $buyDetails = @()

            while ($remainingToSell -gt 0 -and $buyQueue.Count -gt 0) {
                $earliestBuy = $buyQueue[0]
                $sellFromThis = [Math]::Min($remainingToSell, $earliestBuy.Shares)
                $costBasis = $sellFromThis * $earliestBuy.Price
                $totalBuyCost += $costBasis
                $buyDetails += @{ Shares = $sellFromThis; BuyPrice = $earliestBuy.Price; CostBasis = $costBasis }
                $earliestBuy.Shares -= $sellFromThis
                $remainingToSell -= $sellFromThis
                if ($earliestBuy.Shares -le 0) { $buyQueue = $buyQueue | Select-Object -Skip 1 }
            }

            $avgBuyPrice = if ($shares -gt 0) { $totalBuyCost / $shares } else { $price }

            # 获取止损价
            $stopLoss = $null
            $support = $null
            $resistance = $null
            if ($posMap.ContainsKey($code)) {
                $pos = $posMap[$code]
                $stopLoss = [double]$pos.StopLoss
                $support = [double]$pos.Support
                $resistance = [double]$pos.Resistance
            }

            # 净卖出收入（不含手续费）
            $grossProceed = $price * $shares
            # 原始手续费（从CSV获取）
            $origCommission = [double]$t.commission
            $origStampTax = [double]$t.stamp_tax

            # 实际盈亏
            $realizedPnL = $grossProceed - $totalBuyCost - $origCommission - $origStampTax
            $realizedPnLPct = if ($totalBuyCost -gt 0) { [Math]::Round($realizedPnL / $totalBuyCost * 100, 2) } else { 0 }

            # 入场到出场天数
            $entryDate = if ($currentEntryDate) { $currentEntryDate } else { $t.date }
            $exitDate = $t.date
            $daysHeld = 0
            try {
                $d1 = [datetime]::ParseExact($entryDate, "yyyyMMdd", $null)
                $d2 = [datetime]::ParseExact($exitDate, "yyyyMMdd", $null)
                $daysHeld = ($d2 - $d1).Days
            } catch {}

            $pairedTrades += [PSCustomObject]@{
                Code = $code
                Name = $t.name
                EntryDate = $entryDate
                ExitDate = $exitDate
                DaysHeld = $daysHeld
                BuyPrice = [Math]::Round($totalBuyCost / $shares, 2)
                AvgBuyPrice = [Math]::Round($avgBuyPrice, 2)
                ExitPrice = $price
                Shares = $shares
                TotalBuyCost = [Math]::Round($totalBuyCost, 2)
                GrossProceed = [Math]::Round($grossProceed, 2)
                Commission = $origCommission
                StampTax = $origStampTax
                NetPnL = [Math]::Round($realizedPnL, 2)
                NetPnLPct = $realizedPnLPct
                StopLoss = $stopLoss
                Support = $support
                Resistance = $resistance
                EntryPrediction = $currentEntryPrediction
                ExitReason = $reason
            }

            $currentShares = 0
            $currentCost = 0
            $currentEntryDate = $null
            $currentEntryPrediction = $null
        }
    }
}

# ---- Step 7: 统计并输出 ----
$closedTrades = $pairedTrades | Where-Object { $_.NetPnL -ne $null }

if ($closedTrades.Count -lt 1) {
    Write-Host "`n[跳过] 未找到已平仓的完整交易" -ForegroundColor Yellow
    Write-Host "交易记录中可能只有买入/减仓记录，需要至少一笔完整的 买入→卖出" -ForegroundColor Yellow
    exit 0
}

Write-Host "`n已配对完整交易: $($closedTrades.Count) 笔" -ForegroundColor Gray
Write-Host "`n交易明细:" -ForegroundColor Gray
foreach ($t in $closedTrades) {
    $sign = if ($t.NetPnL -ge 0) { "+" } else { "" }
    Write-Host "  $($t.Name)($($t.Code)) 买入$($t.EntryDate)@¥$($t.AvgBuyPrice) → 卖出$($t.ExitDate)@¥$($t.ExitPrice) 持有${daysHeld}d  ${sign}$($t.NetPnL)元(${sign}$($t.NetPnLPct)%)  $($t.ExitReason)" -ForegroundColor Gray
}

$totalDays = ($closedTrades | Measure-Object -Property DaysHeld -Sum).Sum

# ============================================================
# Step 8: 对每组参数计算绩效
# ============================================================
Write-Header "参数组合绩效回测"

$results = @()
$detailRows = @()

foreach ($paramSet in $paramSets) {
    $totalNetPnL = 0
    $wins = 0
    $losses = 0
    $totalFees = 0
    $maxDrawdown = 0
    $peakEquity = 0
    $equity = 0
    $tradePnLs = @()

    # 按时间顺序处理交易（模拟资金曲线）
    $sortedTrades = $closedTrades | Sort-Object ExitDate

    foreach ($trade in $sortedTrades) {
        $entryPrice = $trade.AvgBuyPrice
        $exitPrice = $trade.ExitPrice
        $shares = $trade.Shares
        $stopLoss = $trade.StopLoss

        # 用新参数计算 R2/R3
        $r2r3 = Get-R2R3 -EntryPrice $entryPrice -Pct1 $paramSet.Pct1 -Pct2 $paramSet.Pct2
        $newR2 = $r2r3.R2
        $newR3 = $r2r3.R3

        # 判定原始出场类型
        $origR2R3 = Get-R2R3 -EntryPrice $entryPrice -Pct1 $origFixedPct1 -Pct2 $origFixedPct2
        $origExitType = Get-ExitType -ExitPrice $exitPrice -EntryPrice $entryPrice -StopLoss $stopLoss -R2 $origR2R3.R2 -R3 $origR2R3.R3 -Reason $trade.ExitReason

        # 用新参数模拟
        $simResult = Simulate-ExitWithNewParams -ExitPrice $exitPrice -EntryPrice $entryPrice -StopLoss $stopLoss -NewR2 $newR2 -NewR3 $newR3 -OriginalExitType $origExitType

        # 计算在新参数下的理论盈亏
        if ($simResult.WouldHold) {
            # 理论持有未卖出：用当前价（实际出场价）计算账面盈亏
            $simPnL = ($exitPrice - $entryPrice) * $shares
            $simPnLPct = ($exitPrice / $entryPrice - 1) * 100
            $theoryExitPrice = $exitPrice  # 实际出场价作为"当前价"
            $theoryExitType = $simResult.NewExitType
        } elseif ($simResult.NewExitType -eq "P1止损") {
            # 止损价出场
            $theoryExitPrice = $stopLoss
            $simPnL = ($stopLoss - $entryPrice) * $shares
            $simPnLPct = ($stopLoss / $entryPrice - 1) * 100
            $theoryExitType = "P1止损"
        } elseif ($simResult.NewExitType -match "P4|P5") {
            # 止盈价出场
            $triggerPrice = $simResult.TriggerAt
            $theoryExitPrice = $triggerPrice
            $simPnL = ($triggerPrice - $entryPrice) * $shares
            $simPnLPct = ($triggerPrice / $entryPrice - 1) * 100
            $theoryExitType = $simResult.NewExitType
        } else {
            # 其他原因，保持实际出场
            $theoryExitPrice = $exitPrice
            $simPnL = ($exitPrice - $entryPrice) * $shares
            $simPnLPct = ($exitPrice / $entryPrice - 1) * 100
            $theoryExitType = $simResult.NewExitType
        }

        # 扣除手续费（用新参数计算理论费用）
        $grossProceed = $theoryExitPrice * $shares
        $buyComm = Calc-Commission -Amount ($entryPrice * $shares) -Rate $commRate -MinFee $commMin
        $sellComm = Calc-Commission -Amount $grossProceed -Rate $commRate -MinFee $commMin
        $sellStamp = Calc-StampTax -Amount $grossProceed -Rate $stampRate
        $totalFee = $buyComm + $sellComm + $sellStamp

        $buyCost = $entryPrice * $shares
        $netSimPnL = $grossProceed - $buyCost - $totalFee
        $netSimPnLPct = if ($buyCost -gt 0) { [Math]::Round($netSimPnL / $buyCost * 100, 2) } else { 0 }

        # 盈亏计数
        if ($netSimPnL -gt 0) { $wins++ } else { $losses++ }
        $totalNetPnL += $netSimPnL
        $totalFees += $totalFee
        $tradePnLs += $netSimPnL

        # 资金曲线回撤
        $equity += $netSimPnL
        if ($equity -gt $peakEquity) { $peakEquity = $equity }
        $dd = $equity - $peakEquity
        if ($dd -lt $maxDrawdown) { $maxDrawdown = $dd }

        # 详细行
        $detailRows += [PSCustomObject]@{
            ParamSet = $paramSet.Name
            Code = $trade.Code
            Name = $trade.Name
            EntryDate = $trade.EntryDate
            ExitDate = $trade.ExitDate
            EntryPrice = $entryPrice
            ExitPrice_Actual = $exitPrice
            ExitPrice_Theory = [Math]::Round($theoryExitPrice, 2)
            NewR2 = $newR2
            NewR3 = $newR3
            OrigExitType = $origExitType
            NewExitType = $theoryExitType
            TotalFee = [Math]::Round($totalFee, 2)
            NetPnL = [Math]::Round($netSimPnL, 2)
            NetPnLPct = $netSimPnLPct
            WouldHold = $simResult.WouldHold
            Note = $simResult.Note
        }
    }

    $totalTrades = $wins + $losses
    $winRate = if ($totalTrades -gt 0) { [Math]::Round($wins / $totalTrades * 100, 1) } else { 0 }
    $avgPnL = if ($totalTrades -gt 0) { [Math]::Round($totalNetPnL / $totalTrades, 2) } else { 0 }
    $maxDDpct = if ($peakEquity -gt 0) { [Math]::Round($maxDrawdown / $peakEquity * 100, 2) } else { 0 }

    # 盈亏比/获利因子
    $totalWins = ($tradePnLs | Where-Object { $_ -gt 0 } | Measure-Object -Sum).Sum
    $totalLosses = [Math]::Abs(($tradePnLs | Where-Object { $_ -le 0 } | Measure-Object -Sum).Sum)
    $profitFactor = if ($totalLosses -gt 0) { [Math]::Round($totalWins / $totalLosses, 2) } else { "N/A" }

    $results += [PSCustomObject]@{
        ParamSet = $paramSet.Name
        FixedPct1 = $paramSet.Pct1
        FixedPct2 = $paramSet.Pct2
        WinRate = $winRate
        Wins = $wins
        Losses = $losses
        TotalNetPnL = [Math]::Round($totalNetPnL, 2)
        AvgPnL = $avgPnL
        TotalFees = [Math]::Round($totalFees, 2)
        MaxDrawdown = $maxDDpct
        ProfitFactor = $profitFactor
        TradeCount = $totalTrades
    }
}

# ============================================================
# Step 9: 输出结果
# ============================================================

# 表格头
Write-Host ""
Write-Host ("{0,-14} {1,8} {2,8} {3,8} {4,6} {5,6} {6,12} {7,10} {8,10} {9,10}" -f
    "参数组合", "Pct1", "Pct2", "胜率", "赢", "输", "总盈亏(元)", "平均(元)", "最大回撤", "获利因子") -ForegroundColor Yellow
Write-Host ("{0,-14} {1,8} {2,8} {3,8} {4,6} {5,6} {6,12} {7,10} {8,10} {9,10}" -f
    ("-"*14), ("-"*8), ("-"*8), ("-"*8), ("-"*6), ("-"*6), ("-"*12), ("-"*10), ("-"*10), ("-"*10))

foreach ($r in $results) {
    $color = if ($r.TotalNetPnL -gt 0) { "Green" } elseif ($r.TotalNetPnL -lt 0) { "Red" } else { "Gray" }
    Write-Host ("{0,-14} {1,8} {2,8} {3,7}% {4,6} {5,6} {6,12} {7,10} {8,9}% {9,10}" -f
        $r.ParamSet, $r.FixedPct1, $r.FixedPct2, $r.WinRate, $r.Wins, $r.Losses,
        $r.TotalNetPnL, $r.AvgPnL, $r.MaxDrawdown, $r.ProfitFactor) -ForegroundColor $color
}

# 最优参数
$bestByReturn = $results | Sort-Object TotalNetPnL -Descending | Select-Object -First 1
$bestByWinRate = $results | Sort-Object WinRate -Descending | Select-Object -First 1
$bestByProfitFactor = $results | Where-Object { $_.ProfitFactor -ne "N/A" } | Sort-Object ProfitFactor -Descending | Select-Object -First 1

Write-Host ""
Write-Host "===== 最优参数分析 =====" -ForegroundColor Cyan
Write-Host "按总收益最优: $($bestByReturn.ParamSet) (Pct1=$($bestByReturn.FixedPct1)%, Pct2=$($bestByReturn.FixedPct2)%) 总盈亏=$($bestByReturn.TotalNetPnL)元 胜率=$($bestByReturn.WinRate)%" -ForegroundColor Green
Write-Host "按胜率最优:   $($bestByWinRate.ParamSet) (Pct1=$($bestByWinRate.FixedPct1)%, Pct2=$($bestByWinRate.FixedPct2)%) 胜率=$($bestByWinRate.WinRate)% 总盈亏=$($bestByWinRate.TotalNetPnL)元" -ForegroundColor Green
if ($bestByProfitFactor) {
    Write-Host "按获利因子最优: $($bestByProfitFactor.ParamSet) (Pct1=$($bestByProfitFactor.FixedPct1)%, Pct2=$($bestByProfitFactor.FixedPct2)%) 获利因子=$($bestByProfitFactor.ProfitFactor)" -ForegroundColor Green
}

# 建议
Write-Host ""
$firstResult = $results | Where-Object { $_.ParamSet -eq "原始参数" } | Select-Object -First 1
if ($firstResult -and $bestByReturn.ParamSet -ne "原始参数") {
    $delta = $bestByReturn.TotalNetPnL - $firstResult.TotalNetPnL
    $deltaSign = if ($delta -ge 0) { "+" } else { "" }
    Write-Host "建议: 当前参数总盈亏 $($firstResult.TotalNetPnL)元，最优组合改善 ${deltaSign}$($delta)元" -ForegroundColor Yellow
    Write-Host "  可考虑将 FixedPct1 调整为 $($bestByReturn.FixedPct1)%, FixedPct2 调整为 $($bestByReturn.FixedPct2)%" -ForegroundColor Yellow
} else {
    Write-Host "当前参数已为最优或数据不足以判断" -ForegroundColor Gray
}

# ============================================================
# Step 10: 导出 CSV
# ============================================================
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"

# 汇总结果
$resultCsv = Join-Path $OutputDir "backtest_summary_${timestamp}.csv"
$results | Export-Csv -Path $resultCsv -NoTypeInformation -Encoding UTF8
Write-Host "`n汇总结果已写入: $resultCsv" -ForegroundColor Gray

# 逐笔明细
if ($detailRows.Count -gt 0) {
    $detailCsv = Join-Path $OutputDir "backtest_details_${timestamp}.csv"
    $detailRows | Export-Csv -Path $detailCsv -NoTypeInformation -Encoding UTF8
    Write-Host "逐笔明细已写入: $detailCsv" -ForegroundColor Gray
}

# ============================================================
# Step 11: 额外输出 - 当前持仓在新参数下的表现
# ============================================================
Write-Header "当前持仓在新参数下的状态"

$currentPositions = $allTxns | Where-Object { $_.action -eq "BUY" } | Group-Object Code
$openPositions = @()

foreach ($gp in $currentPositions) {
    $code = $gp.Name
    if (-not $posMap.ContainsKey($code)) { continue }
    $pos = $posMap[$code]
    $shares = [int]$pos.Shares
    if ($shares -le 0) { continue }

    $entryPrice = [double]$pos.AvgCost
    $currentPrice = [double]$pos.CurrentPrice
    $stopLoss = [double]$pos.StopLoss
    $entryDate = $pos.EntryDate

    $openPositions += [PSCustomObject]@{
        Code = $code
        Name = $pos.Name
        Shares = $shares
        EntryPrice = $entryPrice
        CurrentPrice = $currentPrice
        StopLoss = $stopLoss
        UnrealizedPnL = [double]$pos.UnrealizedPnL
        UnrealizedPnLPct = [double]$pos.UnrealizedPnLPct
        EntryDate = $entryDate
    }
}

if ($openPositions.Count -eq 0) {
    Write-Host "  当前无持仓" -ForegroundColor Gray
} else {
    foreach ($pos in $openPositions) {
        Write-Host "`n$($pos.Name)($($pos.Code)):" -ForegroundColor White
        Write-Host "  入场: $($pos.EntryDate) @ ¥$($pos.EntryPrice) 现价: ¥$($pos.CurrentPrice)" -ForegroundColor Gray
        Write-Host "  浮动盈亏: $($pos.UnrealizedPnLPct)% 止损价: ¥$($pos.StopLoss)" -ForegroundColor Gray

        foreach ($ps in $paramSets) {
            $r2r3 = Get-R2R3 -EntryPrice $pos.EntryPrice -Pct1 $ps.Pct1 -Pct2 $ps.Pct2
            $r2 = $r2r3.R2
            $r3 = $r2r3.R3

            $r2gap = [Math]::Round(($r2 / $pos.CurrentPrice - 1) * 100, 1)
            $r3gap = [Math]::Round(($r3 / $pos.CurrentPrice - 1) * 100, 1)
            $stopGap = [Math]::Round(($pos.CurrentPrice / $pos.StopLoss - 1) * 100, 1)

            $statusText = ""
            if ($pos.CurrentPrice -le $pos.StopLoss) {
                $statusText = " [已触发止损 P1]"
                $statusColor = "Red"
            } elseif ($pos.CurrentPrice -ge $r3) {
                $statusText = " [已触发全部止盈 P4]"
                $statusColor = "Green"
            } elseif ($pos.CurrentPrice -ge $r2) {
                $statusText = " [已触发止盈减仓 P5]"
                $statusColor = "Yellow"
            } else {
                $statusText = " [持有中]"
                $statusColor = "Gray"
            }

            Write-Host "  $($ps.Name): R2=¥$r2(还需+${r2gap}%) R3=¥$r3(还需+${r3gap}%) 止损距离=${stopGap}%$statusText" -ForegroundColor $statusColor
        }
    }
}

# ============================================================
# Done
# ============================================================
Write-Host ""
Write-Host "===== 回测完成 =====" -ForegroundColor Cyan
Write-Host "输出目录: $OutputDir" -ForegroundColor Gray
