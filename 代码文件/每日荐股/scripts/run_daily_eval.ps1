# 铁律量化 - 每日荐股次日后评估执行脚本
# 基于：次日后评估白皮书 v1.5
# 数据源：[1]腾讯行情 [1B]新浪行情 [2]新浪K线 [2B]腾讯K线 [3]东方财富财务 [7]东方财富板块 [9]东方财富资金流向 [C]缓存兜底
# 评估流程：数据采集(§2.1) → 模拟交易(§2.2) → 维度回检(§3) → 规则验证(§4) → 评估报告(附录A) → 参数校准建议(§5)
# 输出：评估报告_YYYYMMDD.docx | records.csv(§6.1.1) | summary.csv(§6.1.2)
# 调用方式：.\run_daily_eval.ps1 [-ReportDate "YYYYMMDD"] [-KeepHtml]

param(
    [string]$ReportDate = "",
    [switch]$KeepHtml = $false
)
. "$PSScriptRoot/../../lib/init_encoding.ps1"

$rootDir = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$modulePath = Join-Path $rootDir "代码文件\每日荐股\scripts\stock_data_fetcher.psm1"
$dataFile = Join-Path $rootDir "代码文件\数据\data_scored.json"
$edgePath = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

# 输出目录 — 白皮书 §1.4: 评估报告存储于事后评估目录
$evalReportDir = Join-Path $rootDir "每日荐股\评估报告"
if (-not (Test-Path $evalReportDir)) { New-Item -ItemType Directory -Path $evalReportDir -Force | Out-Null }

# records.csv 路径 — 白皮书 §6.1.1
$recordsFile = Join-Path $evalReportDir "records.csv"

# 导入数据模块
if (Test-Path $modulePath) {
    Import-Module $modulePath -Force -WarningAction SilentlyContinue 2>$null
    Write-Host "数据模块已导入 [1][1B][2][2B][3][7][9][C]"
} else {
    Write-Error "Module not found: $modulePath"
    exit 1
}

$execDate = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$todayStr = Get-Date -Format "yyyyMMdd"

# ============================================================
# 辅助函数
# ============================================================

# ATR(14) 计算 — 白皮书 §2.2.3
# 输入：日K线数组（至少15条），输出：最新ATR值
function Calc-ATR { param([array]$Klines) Measure-ATR -Klines $Klines }

function Measure-ATR {
    param([array]$Klines)
    if (-not $Klines -or $Klines.Count -lt 15) { return $null }
    $trValues = @()
    for ($i = 1; $i -lt $Klines.Count; $i++) {
        $high = [double]$Klines[$i].High
        $low = [double]$Klines[$i].Low
        $prevClose = [double]$Klines[$i-1].Close
        $tr = [Math]::Max($high - $low, [Math]::Max([Math]::Abs($high - $prevClose), [Math]::Abs($low - $prevClose)))
        $trValues += $tr
    }
    if ($trValues.Count -lt 14) { return $null }
    $recentTR = $trValues[-14..-1]
    return [Math]::Round(($recentTR | Measure-Object -Average).Average, 2)
}

# 获取沪深300涨跌幅 — 腾讯行情[1]
# 白皮书 §2.1: 沪深300指数涨跌 → 超额收益计算基准
function Get-HS300Change {
    try {
        $quote = Get-StockQuote -Code "000300"
        if ($quote -and $quote.ChangePct) {
            $script:SourceUsed["HS300"] = "腾讯"
            return [double]$quote.ChangePct
        }
    } catch {}
    # 备源：直接请求腾讯API
    try {
        $url = "http://qt.gtimg.cn/q=sh000300"
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 5
        if ($r.Content -match '"([^"]*)"') {
            $fields = $matches[1] -split '~'
            if ($fields.Count -ge 32) {
                $script:SourceUsed["HS300"] = "腾讯(备)"
                return [double]$fields[32]
            }
        }
    } catch {}
    $script:SourceUsed["HS300"] = "失败"
    return $null
}

# 判断大盘环境 — 白皮书 §3.2 动态基线
# 强势市场 >+2% | 正常市场 −2%~+2% | 弱势市场 <−2%
function Get-MarketEnvironment {
    param([double]$MarketAvgReturn)
    if ($MarketAvgReturn -gt 2.0) { return "强势" }
    if ($MarketAvgReturn -lt -2.0) { return "弱势" }
    return "正常"
}

# 获取误判触发条件阈值 — 白皮书 §3.2 动态调整
function Get-MisjudgeThreshold {
    param([string]$MarketEnv, [double]$HS300Change)
    switch ($MarketEnv) {
        "强势" { return $HS300Change - 3.0 }   # 跑输大盘>3%
        "弱势" { return -2.0 }                  # 亏损>2%
        default { return -3.0 }                 # 亏损>3%
    }
}

# ============================================================
# 读取 T 日荐股数据
# ============================================================
Write-Host "`n========== 每日荐股次日后评估（白皮书 v1.5）=========="
Write-Host "执行时间: $execDate`n"

if (-not (Test-Path $dataFile)) {
    Write-Error "数据文件不存在: $dataFile"
    exit 1
}

$rawData = Get-Content $dataFile -Raw -Encoding UTF8 | ConvertFrom-Json

# Extract stocks from v2 format — 使用 Recommendations（含评分字段），AllStocks 仅有原始行情无评分
if ($rawData.Recommendations -and @($rawData.Recommendations).Count -gt 0) {
    $allStocks = @($rawData.Recommendations)
} elseif ($rawData.AllStocks) {
    Write-Warning "Recommendations为空，回退至AllStocks（评分字段将缺失）"
    $allStocks = @($rawData.AllStocks)
} elseif ($rawData -is [array]) {
    $allStocks = $rawData
} else {
    Write-Error "Unknown data format in $dataFile"
    exit 1
}

# Select top stocks for evaluation
$topN = $allStocks | Sort-Object TotalScore -Descending | Select-Object -First 8

Write-Host "T日荐股数据: $($allStocks.Count) 只候选, 选取前 $($topN.Count) 只评估`n"
Write-Host ("{0,-10} {1,-10} {2,-8} {3,-8} {4,-8} {5,-12}" -f "代码", "名称", "T日价", "总分", "评级", "行业")
Write-Host ("{0,-10} {1,-10} {2,-8} {3,-8} {4,-8} {5,-12}" -f "------", "------", "------", "----", "----", "------")

foreach ($s in $topN) {
    $rating = if ($s.TotalScore -ge 70) { "推荐" } elseif ($s.TotalScore -ge 60) { "观察" } elseif ($s.TotalScore -ge 50) { "谨慎" } else { "回避" }
    Write-Host ("{0,-10} {1,-10} {2,-8} {3,-8} {4,-8} {5,-12}" -f $s.Code, $s.Name, [Math]::Round($s.Price,2), $s.TotalScore, $rating, $s.Industry)
}

# ============================================================
# 获取沪深300 & 大盘环境判断 [1] — 白皮书 §2.1、§3.2
# ============================================================
Write-Host "`n获取沪深300数据 [1]..."
$hs300Change = Get-HS300Change
if ($null -eq $hs300Change) {
    Write-Host "  !! 沪深300获取失败[1]，超额收益无法计算。使用0%作为默认值"
    $hs300Change = 0.0
} else {
    Write-Host ("  沪深300涨跌幅[1]: {0:+#0.00;-#0.00}%" -f $hs300Change)
}

# 大盘环境分类 — 白皮书 §3.2
$marketEnv = Get-MarketEnvironment -MarketAvgReturn $hs300Change
$misjudgeThreshold = Get-MisjudgeThreshold -MarketEnv $marketEnv -HS300Change $hs300Change

$misjudgeDesc = switch ($marketEnv) {
    "强势" { "跑输大盘>3%" }
    "弱势" { "亏损>2%" }
    default { "亏损>3%" }
}
Write-Host ("  大盘环境判定: $marketEnv | 误判条件: $misjudgeDesc (阈值: {0:+#0.00;-#0.00}%)" -f $misjudgeThreshold)

# ============================================================
# 模拟交易与评估 — 白皮书 §2.2
# ============================================================
$evalResults = @()
$totalWin = 0; $totalLoss = 0; $winCount = 0; $lossCount = 0
$totalReturn = 0
$untradeable = 0         # 无法成交计数（一字涨停/开盘异常）
$stopLossCount = 0       # 止损触发计数
$sysRiskCount = 0        # 系统性风险卖出计数

# 维度回检 — 六维评估（含板块面） 白皮书 §3.1
# 评分维度: 技术面/基本面/资金面/消息面/风控/板块面
$dimCorrect = @{ tech=0; fund=0; money=0; news=0; risk=0; sector=0 }
$dimTotal   = @{ tech=0; fund=0; money=0; news=0; risk=0; sector=0 }
$dimNames   = @{ tech="技术面"; fund="基本面"; money="资金面"; news="消息面"; risk="风控"; sector="板块面" }

# 维度高分阈值（满分60%）— 白皮书 §3.2
# S_Tech/S_Money/S_News/S_Fund/S_Risk 满分20分 → 60%=12分
# S_Base 满分10分 → 60%=6分
$dimHighThreshold = @{ tech=12; fund=12; money=12; news=12; risk=12; sector=6 }

foreach ($s in $topN) {
    # 获取 T+1 日行情[1] → 含开盘价/最高价/最低价/收盘价
    $quote = Get-StockQuote -Code $s.Code
    if (-not $quote -or $quote.Price -eq 0) {
        Write-Host "  !! $($s.Name)($($s.Code)) 行情获取失败[1]，跳过"
        continue
    }

    # ---- §2.2.1 买入模拟 ----
    $tPrice = [double]$s.Price                # T日收盘价
    $t1Open = [double]$quote.Open             # T+1日开盘价
    $t1High = [double]$quote.High             # T+1日最高价
    $t1Low = [double]$quote.Low               # T+1日最低价
    $t1Close = [double]$quote.Price           # T+1日收盘价

    # 判断是否可交易
    $isUntradeable = $false
    $untradeableReason = ""

    # 涨停判断（约10%）
    $upperLimitPct = ($t1Open - $tPrice) / $tPrice * 100

    if ($upperLimitPct -ge 9.5) {
        # 一字涨停/接近涨停开盘 → 白皮书 §2.2.1 标记「无法成交」
        $isUntradeable = $true
        $untradeableReason = "一字涨停"
        $buyPrice = 0
        $sellPrice = 0
        $returnPct = 0
        $exitReason = "无法成交"
    } elseif ($upperLimitPct -lt -3.0) {
        # 开盘跌>3% → 白皮书 §2.2.1 标记「开盘异常」
        $isUntradeable = $true
        $untradeableReason = "开盘异常"
        $buyPrice = 0
        $sellPrice = 0
        # 仍记录涨跌幅作为参考
        $returnPct = ($t1Close - $tPrice) / $tPrice * 100
        $exitReason = "开盘异常"
    } else {
        # 正常开盘 → 买入价 = 开盘价×1.005（含0.5%单向滑点）— 白皮书 §2.2.1
        $buyPrice = [Math]::Round($t1Open * 1.005, 2)

        # ---- §2.2.3 止损计算 ----
        # 获取K线数据[2]计算ATR(14)
        $klines = Get-StockKLine -Code $s.Code -Scale "240" -Count 20
        $atr = Measure-ATR -Klines $klines
        if ($null -eq $atr -or $atr -le 0) {
            # ATR计算失败，用股价的2%作为默认值
            $atr = [Math]::Round($buyPrice * 0.02, 2)
            Write-Host "    [$($s.Code)] ATR计算失败[2]，使用默认值2%"
        }

        # 止损价 = 买入价 − 2×ATR，硬上限−8% — 白皮书 §2.2.3
        $stopLossByATR = $buyPrice - 2 * $atr
        $stopHardCap = $buyPrice * 0.92
        $stopPrice = [Math]::Max($stopLossByATR, $stopHardCap)

        # ---- §2.2.4 日内止损检查 + §2.2.2 卖出模拟 ----
        $exitReason = "收盘价"
        $sellPrice = $t1Close

        # 优先级1: 日内最低价 ≤ 止损价 → 按触发价卖出 — 白皮书 §2.2.4
        if ($t1Low -le $stopPrice) {
            $sellPrice = $stopPrice
            $exitReason = "日内止损"
            $stopLossCount++
        }
        # 优先级2: 盈利>10%后收盘跌破买入价 — 白皮书 §2.2.2
        elseif (($t1High - $buyPrice) / $buyPrice * 100 -gt 10.0 -and $t1Close -lt $buyPrice) {
            $sellPrice = $t1Close
            $exitReason = "止盈保护"
        }
        # 优先级3: 大盘当日跌>3% → 当日收盘价卖出 — 白皮书 §2.2.2
        elseif ($hs300Change -lt -3.0) {
            $sellPrice = $t1Close
            $exitReason = "系统性风险"
            $sysRiskCount++
        }
        # 优先级4: 默认 → T+1日收盘价 — 白皮书 §2.2.2

        # 计算收益率
        $returnPct = ($sellPrice - $buyPrice) / $buyPrice * 100
    }

    # === 交易结果 ===
    $isWin = $returnPct -gt 0

    if ($isUntradeable) {
        $untradeable++
        $isWinMark = "[XX]"
    } else {
        if ($isWin) { $winCount++; $totalWin += $returnPct } else { $lossCount++; $totalLoss += $returnPct }
        $totalReturn += $returnPct
        $isWinMark = if ($isWin) { "[OK]" } else { "[--]" }
    }

    # === 维度归因 — 白皮书 §3.1、§3.2 ===
    $dimNotes = @()
    $primaryMisjudge = ""  # 主要误判维度 — 白皮书 §3.2.2

    $dimScoreMap = @{
        tech   = [double]$s.S_Tech
        fund   = [double]$s.S_Fund
        money  = [double]$s.S_Money
        news   = [double]$s.S_News
        risk   = [double]$s.S_Risk
        sector = [double]$s.S_Base   # S_Base 映射为板块面评分
    }

    foreach ($dim in $dimScoreMap.Keys) {
        $score = $dimScoreMap[$dim]
        if ($score -ge $dimHighThreshold[$dim]) {
            $dimTotal[$dim]++
            if ($returnPct -lt $misjudgeThreshold) {
                # 误判 — 亏损超过动态阈值
                $dimNotes += "$($dimNames[$dim])误判"
                if ([string]::IsNullOrEmpty($primaryMisjudge)) {
                    $primaryMisjudge = $dim.ToUpper() + "_MISJUDGE"
                }
            } else {
                $dimCorrect[$dim]++
            }
        }
    }

    $misjudge = if ($dimNotes.Count -gt 0) { $dimNotes -join ";" } else { "-" }

    # === 输出 ===
    if ($isUntradeable) {
        Write-Host ("  {0,-10} {1,-8} T价:{2,-8} {3,-10} 标记:{4,-10} {5}" -f $s.Name, $s.Code, [Math]::Round($tPrice,2), $untradeableReason, $isWinMark, $misjudge)
    } else {
        $signal = if ($isWin) { "+" } else { "" }
        Write-Host ("  {0,-10} {1,-8} 买入:{2,-8} 卖出:{3,-8} 收益:{4,7}% [{5,-8}] {6,-10} {7}" -f $s.Name, $s.Code, [Math]::Round($buyPrice,2), [Math]::Round($sellPrice,2), "$signal$([Math]::Round($returnPct,2))", $exitReason, $isWinMark, $misjudge)
    }

    # === 收集结果 ===
    $evalResults += [PSCustomObject]@{
        Code = $s.Code; Name = $s.Name
        TPrice = [Math]::Round($tPrice,2)
        T1Open = [Math]::Round($t1Open,2)
        T1Close = [Math]::Round($t1Close,2)
        BuyPrice = if ($isUntradeable) { 0 } else { [Math]::Round($buyPrice,2) }
        SellPrice = if ($isUntradeable) { 0 } else { [Math]::Round($sellPrice,2) }
        ReturnPct = [Math]::Round($returnPct,2)
        ExitReason = $exitReason
        TotalScore = $s.TotalScore
        IsWin = $isWin
        IsUntradeable = $isUntradeable
        S_Tech = [double]$s.S_Tech; S_Fund = [double]$s.S_Fund
        S_Money = [double]$s.S_Money; S_News = [double]$s.S_News
        S_Risk = [double]$s.S_Risk; S_Base = [double]$s.S_Base
        Misjudge = $misjudge
        PrimaryMisjudge = $primaryMisjudge
        Industry = $s.Industry
        MarketEnv = $marketEnv
    }
}

# ============================================================
# 计算汇总指标 — 白皮书 §1.2、附录B
# ============================================================
$totalEval = $evalResults.Count
$tradeableCount = ($evalResults | Where-Object { -not $_.IsUntradeable }).Count

$winRate = if ($tradeableCount -gt 0) { [Math]::Round($winCount / $tradeableCount * 100, 1) } else { 0 }
$avgWin = if ($winCount -gt 0) { [Math]::Round($totalWin / $winCount, 2) } else { 0 }
$avgLoss = if ($lossCount -gt 0) { [Math]::Round($totalLoss / $lossCount, 2) } else { 0 }
$profitLossRatio = if ($avgLoss -ne 0) { [Math]::Round([Math]::Abs($avgWin / $avgLoss), 2) } else { 0 }
$portfolioReturn = if ($tradeableCount -gt 0) { [Math]::Round($totalReturn / $tradeableCount, 2) } else { 0 }

# 超额收益 = 组合日收益 − 沪深300涨跌 — 白皮书 §1.2
$excessReturn = if ($tradeableCount -gt 0) { [Math]::Round($portfolioReturn - $hs300Change, 2) } else { 0 }

$bestStock = $evalResults | Where-Object { -not $_.IsUntradeable } | Sort-Object ReturnPct -Descending | Select-Object -First 1
$worstStock = $evalResults | Where-Object { -not $_.IsUntradeable } | Sort-Object ReturnPct | Select-Object -First 1

# 维度回检汇总
$dimChecks = @()
foreach ($key in @("tech","fund","money","news","risk","sector")) {
    $cor = $dimCorrect[$key]; $tot = $dimTotal[$key]
    $rate = if ($tot -gt 0) { [Math]::Round($cor / $tot * 100, 1) } else { "-" }
    $dimChecks += [PSCustomObject]@{ Dim=$dimNames[$key]; Correct=$cor; Total=$tot; Rate=$rate }
}

# 评分区分度 — 白皮书 §1.2（使用70分为阈值，目标差值≥15%）
$scoreDistinction = "数据不足，无法计算评分区分度（需≥2只可交易股票）"
$hsWinRate = 0; $lsWinRate = 0; $diff = 0
if ($evalResults.Count -ge 2) {
    $highScore = $evalResults | Where-Object { $_.TotalScore -ge 70 -and -not $_.IsUntradeable }
    $lowScore = $evalResults | Where-Object { $_.TotalScore -lt 70 -and -not $_.IsUntradeable }
    $hsWin = 0; $hsTotal = 0; $lsWin = 0; $lsTotal = 0
    if ($highScore) { $hsTotal = $highScore.Count; $hsWin = ($highScore | Where-Object IsWin).Count }
    if ($lowScore) { $lsTotal = $lowScore.Count; $lsWin = ($lowScore | Where-Object IsWin).Count }
    $hsWinRate = if ($hsTotal -gt 0) { [Math]::Round($hsWin / $hsTotal * 100, 1) } else { 0 }
    $lsWinRate = if ($lsTotal -gt 0) { [Math]::Round($lsWin / $lsTotal * 100, 1) } else { 0 }
    $diff = [Math]::Round($hsWinRate - $lsWinRate, 1)
    $diffStatus = if ($diff -ge 15) { "良好" } elseif ($diff -ge 5) { "一般" } else { "不足" }
    $scoreDistinction = "{0}% ({1}% - {2}%) — {3}" -f $diff, $hsWinRate, $lsWinRate, $diffStatus
}

# ============================================================
# 写入 records.csv — 白皮书 §6.1.1
# ============================================================
Write-Host "`n写入评估明细 records.csv [§6.1.1]..."
$recordsHeader = "eval_date,report_date,stock_code,stock_name,total_score,rating,market_stage,buy_price,sell_price,return_pct,profit,misjudge_dim,misjudge_subtype,tech_expected,money_expected,sector_expected,news_expected,veto_type,exemption_flag,volume_ratio,bellwether_code,bellwether_return,notes"
$recordsExists = Test-Path $recordsFile
if (-not $recordsExists) {
    Add-Content -Path $recordsFile -Value $recordsHeader -Encoding UTF8
    Write-Host "  创建新文件: $recordsFile"
}

foreach ($r in $evalResults) {
    $rating = if ($r.TotalScore -ge 70) { "推荐" } elseif ($r.TotalScore -ge 60) { "观察" } elseif ($r.TotalScore -ge 50) { "谨慎" } else { "回避" }
    if ($r.IsUntradeable) { $profitLabel = "无法成交" } elseif ($r.IsWin) { $profitLabel = "盈利" } else { $profitLabel = "亏损" }

    $recordLine = "$todayStr,$todayStr,$($r.Code),$($r.Name),$($r.TotalScore),$rating,$marketEnv,$($r.BuyPrice),$($r.SellPrice),$($r.ReturnPct),$profitLabel,$($r.PrimaryMisjudge),,,,1,1,,1,,,$($r.Misjudge)"
    Add-Content -Path $recordsFile -Value $recordLine -Encoding UTF8
}
Write-Host "  已写入 $($evalResults.Count) 条记录到 records.csv"

# ============================================================
# 写入 summary.csv — 白皮书 §6.1.2
# ============================================================
Write-Host "写入评估汇总 summary.csv [§6.1.2]..."
$summaryFile = Join-Path $evalReportDir "summary.csv"
$summaryExists = Test-Path $summaryFile
if (-not $summaryExists) {
    $summaryHeader = "period,start_date,end_date,total_recommendations,wins,losses,win_rate,total_profit,total_loss,profit_loss_ratio,portfolio_return,hs300_return,excess_return,tech_misjudge_rate,money_misjudge_rate,sector_misjudge_rate,news_misjudge_rate,veto_kill_rate,exemption_win_rate,recommended_win_rate,vetoed_win_rate,market_win_rate,veto_effectiveness,score_distinction"
    Add-Content -Path $summaryFile -Value $summaryHeader -Encoding UTF8
    Write-Host "  创建新文件: $summaryFile"
}
$techMisRate = ($dimChecks | Where-Object { $_.Dim -eq "技术面" }).Rate
if (-not $techMisRate) { $techMisRate = "-" }
$moneyMisRate = ($dimChecks | Where-Object { $_.Dim -eq "资金面" }).Rate
if (-not $moneyMisRate) { $moneyMisRate = "-" }
$sectorMisRate = ($dimChecks | Where-Object { $_.Dim -eq "板块面" }).Rate
if (-not $sectorMisRate) { $sectorMisRate = "-" }
$newsMisRate = ($dimChecks | Where-Object { $_.Dim -eq "消息面" }).Rate
if (-not $newsMisRate) { $newsMisRate = "-" }
$summaryLine = "single,$todayStr,$todayStr,$totalEval,$winCount,$lossCount,$winRate,$avgWin,$avgLoss,$profitLossRatio,$portfolioReturn,$hs300Change,$excessReturn,$techMisRate,$moneyMisRate,$sectorMisRate,$newsMisRate,-,-,-,-,-,-,$scoreDistinction"
Add-Content -Path $summaryFile -Value $summaryLine -Encoding UTF8
Write-Host "  已追加评估汇总到 summary.csv"

# ============================================================
# 输出汇总 — 白皮书 §1.2、附录B
# ============================================================
Write-Host "`n========== 评估汇总（白皮书 v1.5）=========="
Write-Host ("大盘环境[1]: $marketEnv | 沪深300[1]: {0:+#0.00;-#0.00}%" -f $hs300Change)
Write-Host ("误判动态阈值[§3.2]: $misjudgeDesc")
Write-Host "--------------------------------------------------"
Write-Host "评估股票: $totalEval 只（可交易 $tradeableCount 只）"
Write-Host ("次日胜率[§1.2]: $winRate% ($winCount胜/$lossCount负) | 目标≥60%")
Write-Host "平均盈利: $avgWin% | 平均亏损: $avgLoss%"
Write-Host ("盈亏比[§1.2]: $profitLossRatio : 1 | 目标≥1.5:1")
Write-Host ("组合日收益[§1.2]: {0:+#0.00;-#0.00}%" -f $portfolioReturn)
Write-Host ("沪深300[1]: {0:+#0.00;-#0.00}% | 超额收益[§1.2]: {1:+#0.00;-#0.00}% | 目标>0%" -f $hs300Change, $excessReturn)
Write-Host ("评分区分度[§1.2]: $scoreDistinction | 目标差值≥15%")
Write-Host "无法成交: $untradeable 只（一字涨停/开盘异常）"
Write-Host "止损触发[§2.2.3]: $stopLossCount 次 | 系统性风险卖出: $sysRiskCount 次"
if ($bestStock) { Write-Host ("最佳: $($bestStock.Name)($($bestStock.Code)) {0:+#0.00}% 评分$($bestStock.TotalScore)" -f $bestStock.ReturnPct) }
if ($worstStock) { Write-Host ("最差: $($worstStock.Name)($($worstStock.Code)) {0:+#0.00}% 评分$($worstStock.TotalScore)" -f $worstStock.ReturnPct) }
Write-Host "--------------------------------------------------"

# 参数校准建议 — 白皮书 §5、附录B
Write-Host "`n【参数校准建议】"
if ($winRate -lt 60) { Write-Host "  ⚠ 胜率 $winRate% < 目标60%，建议审查评分逻辑" }
if ($profitLossRatio -lt 1.5) { Write-Host "  ⚠ 盈亏比 $profitLossRatio < 目标1.5，盈利覆盖亏损能力不足" }
if ($excessReturn -lt 0) { Write-Host "  ⚠ 超额收益为负，组合未跑赢大盘" }
if ($diff -lt 15) { Write-Host "  ⚠ 评分区分度 $diff% < 目标15%，高分与低分股表现差异不足" }
foreach ($d in $dimChecks) {
    if ($d.Total -ge 5 -and $d.Rate -ne "-" -and [double]$d.Rate -lt 60) {
        Write-Host ("  ⚠ $($d.Dim)预期正确率 {0}%（{1}/{2}），建议关注" -f $d.Rate, $d.Correct, $d.Total)
    }
}
if ($untradeable -gt 0) { Write-Host ("  ℹ 无法成交 $untradeable 只，已从胜率统计中排除") }

# ============================================================
# 生成 HTML 报告（附录A标准模板）
# ============================================================
Write-Host "`n生成评估报告..."

$stockRows = ""
foreach ($r in $evalResults) {
    $cls = if ($r.IsUntradeable) { "untradeable" } elseif ($r.IsWin) { "win" } else { "loss" }
    $mark = if ($r.IsUntradeable) { "[XX]" } elseif ($r.IsWin) { "[OK]" } else { "[--]" }
    $retDisplay = if ($r.IsUntradeable) { $r.ExitReason } else { "$(if($r.IsWin){'+'})$($r.ReturnPct)%" }
    $stockRows += @"
<tr class="$cls">
    <td>$($r.Code)</td><td>$($r.Name)</td>
    <td>$($r.TPrice)</td><td>$($r.BuyPrice)</td><td>$($r.SellPrice)</td>
    <td class="$cls">$retDisplay</td>
    <td>$($r.ExitReason)</td>
    <td>$($r.TotalScore)</td>
    <td style="font-size:12px;">$mark</td>
    <td style="font-size:12px;color:#999;">$($r.Misjudge)</td>
</tr>
"@
}

$dimRows = ""
foreach ($d in $dimChecks) {
    $cls = if ($d.Rate -ne "-" -and [double]$d.Rate -ge 60) { "color:#27ae60" } elseif ($d.Rate -ne "-" -and [double]$d.Rate -ge 40) { "color:#e67e22" } else { "color:#e74c3c" }
    $dimRows += "<tr><td>$($d.Dim)</td><td>$($d.Correct)/$($d.Total)</td><td style='$cls'>$($d.Rate)%</td></tr>"
}

# 评估结论
$verdictHtml = ""
if ($winRate -ge 60) {
    $verdictHtml = "<div class='verdict-box verdict-good'><div class='v-title' style='color:#27ae60;'>整体表现达标</div><div class='v-detail'>胜率 $winRate% >= 目标60%，推荐体系有效</div></div>"
} elseif ($winRate -ge 45) {
    $verdictHtml = "<div class='verdict-box verdict-warn'><div class='v-title' style='color:#f39c12;'>表现需关注</div><div class='v-detail'>胜率 $winRate% 低于目标60%，需审查评分逻辑</div></div>"
} else {
    $verdictHtml = "<div class='verdict-box verdict-bad'><div class='v-title' style='color:#e74c3c;'>表现不佳</div><div class='v-detail'>胜率 $winRate% 显著低于目标，建议全面排查评分体系</div></div>"
}

$plHtml = ""
if ($profitLossRatio -ge 1.5) {
    $plHtml = "<p style='margin-top:8px;'>盈亏比 $profitLossRatio:1 >= 目标1.5:1，赔率结构健康</p>"
} else {
    $plHtml = "<p style='margin-top:8px;'>盈亏比 $profitLossRatio:1 低于目标1.5:1，盈利覆盖亏损能力不足</p>"
}

# 最佳/最差
$bestHtml = ""
$worstHtml = ""
if ($bestStock) {
    $bestHtml = "<div class='bw-item bw-best'><div class='bw-label'>最佳表现</div><div class='bw-name' style='color:#e74c3c;'>$($bestStock.Name)</div><div class='bw-ret'>$($bestStock.Code) | 评分 $($bestStock.TotalScore) | 涨幅 <strong>$(if($bestStock.ReturnPct -gt 0){'+'})$($bestStock.ReturnPct)%</strong></div></div>"
}
if ($worstStock) {
    $worstHtml = "<div class='bw-item bw-worst'><div class='bw-label'>最差表现</div><div class='bw-name' style='color:#27ae60;'>$($worstStock.Name)</div><div class='bw-ret'>$($worstStock.Code) | 评分 $($worstStock.TotalScore) | 涨幅 <strong>$($worstStock.ReturnPct)%</strong></div></div>"
}

$wrColor = if ($winRate -ge 60) { "#27ae60" } elseif ($winRate -ge 40) { "#f39c12" } else { "#e74c3c" }
$prColor = if ($portfolioReturn -gt 0) { "#e74c3c" } else { "#27ae60" }

# 参数校准建议HTML — 白皮书 §5.1
$paramSuggestions = ""
if ($winRate -lt 60) { $paramSuggestions += "<li>推荐阈值：连续5日胜率<55%→阈值+3（白皮书§5.1）</li>" }
if ($profitLossRatio -lt 1.5) { $paramSuggestions += "<li>审查止损参数：ATR止损倍数可扩大（白皮书§5.1）</li>" }
if ($diff -lt 15) { $paramSuggestions += "<li>评分区分度不足：审查六维评分相关系数，考虑维度重构（白皮书§5.1）</li>" }
foreach ($d in $dimChecks) {
    if ($d.Total -ge 5 -and $d.Rate -ne "-" -and [double]$d.Rate -lt 50) {
        $paramSuggestions += "<li>$($d.Dim)预期正确率仅$($d.Rate)%：建议下调该维度权重或暂停该维度信号（白皮书§3.2）</li>"
    }
}
if ([string]::IsNullOrEmpty($paramSuggestions)) {
    $paramSuggestions = "<li>本日无异常：各指标正常</li>"
}

# 数据源标注
$dataSrcNotes = "数据来源：腾讯行情[1]（实时报价/沪深300）；新浪K线[2]（ATR计算）；东方财富板块[7]（行业分类）"
if ($untradeable -gt 0) {
    $dataSrcNotes += "；无法成交标注已从胜率计算中排除"
}

$html = @"
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>每日荐股后评估报告_$(Get-Date -Format "yyyyMMdd")</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: "Microsoft YaHei", "微软雅黑", sans-serif; color: #333; background: #f0f2f5; padding: 20px; }
.report-page { max-width: 210mm; margin: 0 auto; background: #fff; padding: 15mm 18mm; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
.header { background: #1a1a2e; color: #fff; padding: 28px 30px; border-radius: 10px; margin-bottom: 20px; }
.header h1 { font-size: 24px; margin-bottom: 8px; }
.header .subtitle { font-size: 15px; opacity: 0.8; }
.section { margin: 18px 0; }
.section h2 { font-size: 18px; color: #16213e; border-bottom: 2px solid #1a1a2e; padding-bottom: 6px; margin-bottom: 12px; }
.section h3 { font-size: 15px; color: #333; margin: 10px 0 6px; }
table { width: 100%; border-collapse: collapse; margin: 8px 0 14px; font-size: 13px; }
th { background: #1a1a2e; color: #fff; padding: 8px 10px; text-align: center; font-weight: normal; }
td { padding: 6px 10px; border: 1px solid #e0e0e0; text-align: center; }
tr:nth-child(even) { background: #f8f9fa; }
.win { color: #e74c3c; } .loss { color: #27ae60; } .untradeable { color: #999; }
.summary-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 12px 0; }
.summary-item { text-align: center; padding: 16px; background: #f8f9fa; border-radius: 8px; border-left: 4px solid #3498db; }
.summary-item .val { font-size: 28px; font-weight: bold; margin: 4px 0; }
.summary-item .lbl { font-size: 13px; color: #888; }
.best-worst { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin: 12px 0; }
.bw-item { padding: 14px; border-radius: 8px; }
.bw-best { background: #fde8e8; border: 1px solid #f5c6c6; }
.bw-worst { background: #e8f5e9; border: 1px solid #c6e6c8; }
.bw-item .bw-label { font-size: 11px; color: #888; }
.bw-item .bw-name { font-size: 18px; font-weight: bold; }
.bw-item .bw-ret { font-size: 14px; }
.verdict-box { padding: 16px; border-radius: 8px; margin: 12px 0; text-align: center; }
.verdict-good { background: #e8f5e9; border: 2px solid #27ae60; }
.verdict-warn { background: #fff8e1; border: 2px solid #f39c12; }
.verdict-bad { background: #fde8e8; border: 2px solid #e74c3c; }
.verdict-box .v-title { font-size: 16px; font-weight: bold; }
.verdict-box .v-detail { font-size: 13px; margin-top: 4px; }
.param-list { background: #f0f4ff; border-left: 4px solid #3498db; padding: 12px 16px; margin: 8px 0; font-size: 13px; }
.param-list li { margin: 4px 0; }
.env-tag { display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 12px; font-weight: bold; margin-left: 8px; }
.env-strong { background: #fde8e8; color: #e74c3c; }
.env-normal { background: #e8f5e9; color: #27ae60; }
.env-weak { background: #fff3e0; color: #e67e22; }
.disclaimer { margin-top: 24px; padding-top: 12px; border-top: 1px solid #ddd; font-size: 11px; color: #999; line-height: 1.8; }
</style>
</head>
<body>
<div class="report-page">
    <div class="header">
        <h1>每日荐股后评估报告_$(Get-Date -Format "yyyyMMdd")</h1>
        <div class="subtitle">
            评估 T日荐股表现 | 生成时间: $execDate | 评估股票: $totalEval 只
            <span class="env-tag env-$(if($marketEnv -eq '强势'){'strong'}elseif($marketEnv -eq '弱势'){'weak'}else{'normal'})">$marketEnv 市场</span>
        </div>
        <div class="subtitle" style="font-size:12px;margin-top:4px;">
            白皮书 v1.5 | 数据源[1][1B][2][2B][7]
        </div>
    </div>

    <div class="section">
        <h2>整体表现</h2>
        <div class="summary-grid">
            <div class="summary-item" style="border-left-color:#27ae60;"><div class="lbl">次日胜率</div><div class="val" style="color:$wrColor">$winRate%</div><div class="lbl">$winCount胜 / $lossCount负（目标≥60%）</div></div>
            <div class="summary-item" style="border-left-color:#2980b9;"><div class="lbl">盈亏比</div><div class="val" style="color:#2980b9;">$profitLossRatio : 1</div><div class="lbl">平均盈利 $avgWin% / 亏损 $avgLoss%（目标≥1.5:1）</div></div>
            <div class="summary-item" style="border-left-color:#f39c12;"><div class="lbl">组合日收益</div><div class="val" style="color:$prColor">$(if($portfolioReturn -gt 0){'+'})$portfolioReturn%</div><div class="lbl">推荐组合等权平均</div></div>
        </div>
        <div class="summary-grid" style="grid-template-columns: repeat(3, 1fr); margin-top: 0;">
            <div class="summary-item" style="border-left-color:#8e44ad;"><div class="lbl">沪深300 [1]</div><div class="val" style="color:#8e44ad;">$(if($hs300Change -gt 0){'+'})$hs300Change%</div><div class="lbl">大盘基准</div></div>
            <div class="summary-item" style="border-left-color:#e67e22;"><div class="lbl">超额收益</div><div class="val" style="color:$(if($excessReturn -gt 0){'#e74c3c'}else{'#27ae60'});">$(if($excessReturn -gt 0){'+'})$excessReturn%</div><div class="lbl">组合−沪深300（目标>0%）</div></div>
            <div class="summary-item" style="border-left-color:#c0392b;"><div class="lbl">评分区分度</div><div class="val" style="color:#c0392b;">$diff%</div><div class="lbl">≥70分胜率−<70分胜率（目标≥15%）</div></div>
        </div>

        <div class="best-worst">
            $bestHtml
            $worstHtml
        </div>
        <p style="font-size:12px;color:#888;">无法成交：$untradeable 只（一字涨停/开盘异常，不计入胜率）| 止损触发：$stopLossCount 次</p>
    </div>

    <div class="section">
        <h2>逐股评估明细</h2>
        <table>
            <tr><th>代码</th><th>名称</th><th>T收盘</th><th>买入价</th><th>卖出价</th><th>收益率</th><th>退出原因</th><th>总分</th><th>结果</th><th>归因</th></tr>
            $stockRows
        </table>
        <p style="font-size:12px;color:#888;">买入价=T+1开盘价×1.005（含0.5%滑点）[1] | 卖出价按白皮书§2.2四优先级规则</p>
    </div>

    <div class="section">
        <h2>维度回检摘要（白皮书§3）</h2>
        <table>
            <tr><th>维度</th><th>正确/总次数</th><th>正确率</th></tr>
            $dimRows
        </table>
        <p style="font-size:12px;color:#888;margin-top:6px;">
            误判触发条件（大盘环境动态基线）: $misjudgeDesc |
            <span class="env-tag env-$(if($marketEnv -eq '强势'){'strong'}elseif($marketEnv -eq '弱势'){'weak'}else{'normal'})" style="margin-left:0;">$marketEnv</span>
        </p>
    </div>

    <div class="section">
        <h2>评分有效性（白皮书§1.2）</h2>
        <p>$scoreDistinction</p>
    </div>

    <div class="section">
        <h2>规则验证（白皮书§4）</h2>
        <p>否决误杀：本日未获取否决池数据，无法计算否决误杀率（白皮书§4.1）</p>
        <p>趋势豁免：本日未获取豁免标记，无法计算豁免成功率（白皮书§4.1.3）</p>
        <p>止损触发率：$stopLossCount 次 | 系统性风险卖出：$sysRiskCount 次</p>
    </div>

    <div class="section">
        <h2>参数校准建议（白皮书§5.1）</h2>
        <ul class="param-list">
            $paramSuggestions
        </ul>
    </div>

    <div class="section">
        <h2>评估结论</h2>
        $verdictHtml
        $plHtml
    </div>

    <div class="disclaimer">
        <p><strong>免责声明</strong></p>
        <p>本报告由铁律量化系统自动生成，基于白皮书v1.5。</p>
        <p>$dataSrcNotes</p>
        <p>模拟交易含0.5%单向滑点，ATR动态止损。评估结果仅反映历史表现，不构成投资建议。</p>
        <p>股票投资有风险，过往表现不代表未来收益。生成时间：$execDate</p>
    </div>
</div>
</body>
</html>
"@

# 使用白皮书§1.4命名规范：评估报告_YYYYMMDD
$reportDateStr = if ($ReportDate) { $ReportDate } else { (Get-Date).AddDays(-1).ToString("yyyyMMdd") }
$htmlFile = Join-Path $evalReportDir "每日荐股后评估报告_$reportDateStr.html"
[System.IO.File]::WriteAllText($htmlFile, $html, [System.Text.UTF8Encoding]::new($false))
Write-Host "  HTML: $htmlFile"

# ============================================================
# 转 PDF
# ============================================================
$pdfFile = Join-Path $evalReportDir "每日荐股后评估报告_$reportDateStr.pdf"

if (-not (Test-Path $edgePath)) {
    $altEdge = Get-ChildItem "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" -ErrorAction SilentlyContinue
    if (-not $altEdge) { $altEdge = Get-ChildItem "C:\Program Files\Microsoft\Edge\Application\msedge.exe" -ErrorAction SilentlyContinue }
    if ($altEdge) { $edgePath = $altEdge.FullName }
}

if (Test-Path $edgePath) {
    try {
        # 使用共享函数（从 stock_data_fetcher.psm1 加载，带文件锁检测）
        $ok = ConvertTo-Pdf -HtmlFile $htmlFile -PdfFile $pdfFile -EdgePath $edgePath
        if ($ok) {
            Write-Host "  PDF: $pdfFile ($([Math]::Round((Get-Item $pdfFile).Length/1KB,0)) KB)"
        } else {
            Write-Host "  !! PDF 转换可能失败，保留HTML文件"
        }
    } catch {
        Write-Warning "PDF转换失败: $_"
    }
} else {
    Write-Warning "Edge not found, 保留HTML文件"
}

if (-not $KeepHtml -and (Test-Path $htmlFile)) {
    Remove-Item $htmlFile -Force
}

Write-Host "`n========== 评估完成 =========="
Write-Host "报告已保存: $pdfFile"
Write-Host "数据已追加: $recordsFile"
Write-Host "评估基于白皮书 v1.5（§§2.2模拟交易/§3.2动态基线/§6.1.1记录存储已实现）"
Write-Host "=============================="

# Auto-commit: post_eval outputs
$gitAuto = Join-Path $rootDir "代码文件\tools\git_autocommit.ps1"
if (Test-Path $gitAuto) {
    $null = & $gitAuto -Module "post_eval" -Paths @("历史数据\02_评估数据\", "临时报告\") -Message "每日荐股后评估产出"
}
