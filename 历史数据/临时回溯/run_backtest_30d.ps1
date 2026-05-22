<#
.SYNOPSIS
  铁律量化 — 30日回溯验证引擎
.DESCRIPTION
  用历史K线数据滑窗回测分析逻辑有效性。
  复用现有六维评分函数和三周期预判函数，不修改现有逻辑。
  输出回测报告供人工审阅，确认后再决定是否优化判定逻辑。

  核心思路：
  对过去 N 个交易日，每天用截至当天的数据跑一遍现有分析逻辑，
  记录评分/预测 → 对照后续实际走势 → 统计各维度/各信号的有效性。

  局限性：
  - 资金面/消息面/基本面使用当前快照，不会逐日变化
  - 板块数据使用当前快照
  - 回测结果不等于未来表现，但能快速暴露逻辑短板

.OUTPUT
  临时回溯/
    backtest_data.json        # 全部原始回测数据
    backtest_report.html      # 可视化报告
#>

param(
    [int]$Days = 30,
    [string[]]$TargetStocks = @()
)

$rootDir = "C:\Users\34269\Documents\Claude\股票分析"
$outDir = Join-Path $rootDir "临时回溯"
$modulePath = Join-Path $rootDir "每日荐股\scripts\stock_data_fetcher.psm1"
$edgePath = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir -Force | Out-Null }

# 全部6只股票
$allStocks = @(
    @{ Code="603019"; Name="中科曙光"; Industry="计算机" },
    @{ Code="601689"; Name="拓普集团"; Industry="汽车零部件" },
    @{ Code="600114"; Name="东睦股份"; Industry="电子/机械" },
    @{ Code="301075"; Name="多瑞医药"; Industry="医药" },
    @{ Code="000967"; Name="盈峰环境"; Industry="环保" },
    @{ Code="600036"; Name="招商银行"; Industry="银行" }
)
if ($TargetStocks.Count -gt 0) {
    $stocks = $allStocks | Where-Object { $_.Code -in $TargetStocks }
} else { $stocks = $allStocks }

Write-Host "============================================"
Write-Host "  铁律量化 — 30日回溯验证"
Write-Host "  股票数: $($stocks.Count) | 回测天数: $Days"
Write-Host "  输出: $outDir"
Write-Host "============================================"

# ============================================================
# 导入数据模块
# ============================================================
if (-not (Test-Path $modulePath)) { Write-Error "模块不存在: $modulePath"; exit 1 }
Import-Module $modulePath -Force -WarningAction SilentlyContinue 2>$null
Write-Host "[OK] 数据模块已导入"

# API节流
$script:apiCallCount = 0
function Invoke-ThrottledApi($scriptBlock) {
    Start-Sleep -Milliseconds 300
    $script:apiCallCount++
    if ($script:apiCallCount % 10 -eq 0) { Start-Sleep -Seconds 2 }
    return & $scriptBlock
}

# ============================================================
# 复用：评分函数（来自 run_keystock_analysis.ps1，完全一致）
# ============================================================

function Get-TechScore {
    param($D)
    $score = 0
    if (-not $D.KLines -or $D.KLines.Count -lt 20 -or -not $D.MACD) { return 40 }
    $ma5v = $D.MA5[-1]; $ma10v = $D.MA10[-1]; $ma20v = $D.MA20[-1]; $price = $D.Price
    if     ($ma5v -gt $ma10v -and $ma10v -gt $ma20v -and $price -gt $ma20v) { $score += 30 }
    elseif ($ma5v -gt $ma10v -and $price -gt $ma10v)                       { $score += 20 }
    elseif ($ma5v -gt $ma10v)                                                { $score += 12 }
    elseif ($ma5v -lt $ma10v -and $ma10v -lt $ma20v)                       { $score += 3 }
    else                                                                     { $score += 8 }
    $dif = $D.MACD.DIF[-1]; $dea = $D.MACD.DEA[-1]
    if     ($dif -gt $dea -and $dif -gt 0 -and $D.MACD.DIF[-1] -gt $D.MACD.DIF[-2]) { $score += 20 }
    elseif ($dif -gt $dea -and $dif -gt 0)                                           { $score += 15 }
    elseif ($dif -gt $dea)                                                            { $score += 8 }
    else                                                                              { $score += 3 }
    $rsi = [double]$D.RSI14[-1]
    if     ($rsi -ge 45 -and $rsi -le 65)   { $score += 20 }
    elseif ($rsi -ge 35 -and $rsi -lt 45)   { $score += 12 }
    elseif ($rsi -gt 65 -and $rsi -le 75)   { $score += 12 }
    elseif ($rsi -gt 75 -and $rsi -le 85)   { $score += 5 }
    elseif ($rsi -lt 25)                     { $score += 5 }
    else                                      { $score += 8 }
    $close = $D.KLines[-1].Close; $bm = $D.Bollinger.MA[-1]
    $bu = $D.Bollinger.Upper[-1]; $bd = $D.Bollinger.Lower[-1]
    $bmPrev = if ($D.Bollinger.MA.Count -ge 3) { $D.Bollinger.MA[-3] } else { $bm }
    if     ($close -ge $bm -and $close -le $bu -and $bm -gt $bmPrev) { $score += 15 }
    elseif ($close -lt $bm -and $close -gt $bd -and $bm -gt $bmPrev) { $score += 10 }
    elseif ($close -ge $bu)                                            { $score += 8 }
    elseif ($close -le $bd)                                            { $score += 3 }
    else                                                               { $score += 8 }
    $vol = $D.KLines[-1].Volume; $v5 = $D.VolMA5[-2]; $chg = $D.Quote.ChangePct
    if     ($chg -ge 2 -and $vol -gt $v5 * 1.5)   { $score += 15 }
    elseif ($chg -ge 0 -and $vol -le $v5 * 1.2)   { $score += 8 }
    elseif ($chg -lt -2 -and $vol -gt $v5 * 1.5)  { $score += 2 }
    elseif ($chg -lt 0 -and $vol -lt $v5 * 0.8)   { $score += 5 }
    else                                            { $score += 10 }
    return [Math]::Min([Math]::Max($score, 0), 100)
}

function Get-FundamentalScore {
    param($D)
    $score = 0
    $fin = $D.Financial
    if (-not $fin -or $fin.Count -eq 0) { return 40 }
    $roe = [double]$fin[0].WEIGHTAVG_ROE
    if     ($roe -ge 15)  { $score += 25 }
    elseif ($roe -ge 10)  { $score += 15 }
    elseif ($roe -ge 5)   { $score += 8 }
    else                  { $score += 2 }
    $rev = [double]$fin[0].TOTAL_OPERATE_INCOME; $cost = [double]$fin[0].OPERATE_COST
    if ($rev -gt 0) {
        $gm = ($rev - $cost) / $rev * 100
        if     ($gm -ge 50)  { $score += 20 }
        elseif ($gm -ge 30)  { $score += 15 }
        elseif ($gm -ge 15)  { $score += 8 }
        elseif ($gm -ge 5)   { $score += 3 }
        else                 { $score += 0 }
    } else { $score += 8 }
    if ($fin.Count -ge 2 -and [double]$fin[1].TOTAL_OPERATE_INCOME -ne 0) {
        $revGrowth = ([double]$fin[0].TOTAL_OPERATE_INCOME - [double]$fin[1].TOTAL_OPERATE_INCOME) / [Math]::Abs([double]$fin[1].TOTAL_OPERATE_INCOME) * 100
        if     ($revGrowth -ge 30)  { $score += 20 }
        elseif ($revGrowth -ge 15)  { $score += 14 }
        elseif ($revGrowth -ge 0)   { $score += 8 }
        elseif ($revGrowth -ge -10) { $score += 4 }
        else                        { $score += 0 }
    } else { $score += 8 }
    $pep = $D.PEPercentile
    if ($pep) {
        $pct = $pep.Percentile
        if     ($pct -lt 20)  { $score += 20 }
        elseif ($pct -lt 40)  { $score += 15 }
        elseif ($pct -lt 60)  { $score += 10 }
        elseif ($pct -lt 80)  { $score += 5 }
        else                  { $score += 2 }
    } else { $score += 10 }
    $debt = [double]$fin[0].DEBT_ASSET_RATIO
    if     ($debt -lt 30)   { $score += 15 }
    elseif ($debt -lt 50)   { $score += 10 }
    elseif ($debt -lt 65)   { $score += 5 }
    elseif ($debt -lt 80)   { $score += 2 }
    else                    { $score += 0 }
    return [Math]::Min([Math]::Max($score, 0), 100)
}

function Get-SentimentScore {
    param($D)
    $score = 0
    $r = $D.Research
    if (-not $r -or $r.Count -eq 0) { return 25 }
    $cnt = $r.Count
    if     ($cnt -ge 5)   { $score += 30 }
    elseif ($cnt -ge 3)   { $score += 22 }
    elseif ($cnt -ge 1)   { $score += 12 }
    $buy = ($r | Where-Object { $_.EmRating -eq '买入' }).Count
    $hold = ($r | Where-Object { $_.EmRating -eq '增持' }).Count
    $positive = $buy + $hold
    $positiveRatio = if ($cnt -gt 0) { $positive / $cnt } else { 0 }
    if     ($positiveRatio -ge 0.8)  { $score += 35 }
    elseif ($positiveRatio -ge 0.5)  { $score += 20 }
    elseif ($positiveRatio -ge 0.2)  { $score += 8 }
    else                              { $score += 3 }
    $tr = $D.Quote.TurnoverRate; $chg5 = if ($D.KLines.Count -ge 5) { ($D.KLines[-1].Close / $D.KLines[-5].Close - 1) * 100 } else { 0 }
    $attention = 0
    if ($cnt -ge 3) { $attention += 15 }; if ($tr -gt 3) { $attention += 10 }; if ($chg5 -gt 0) { $attention += 10 }
    $score += $attention
    return [Math]::Min([Math]::Max($score, 0), 100)
}

function Get-SectorScore {
    param($D, $GlobalSectors, $GlobalSectorFund)
    $score = 0
    $industry = ""
    if ($D.Financial -and $D.Financial.Count -gt 0 -and $D.Financial[0].INDUSTRY) { $industry = $D.Financial[0].INDUSTRY }
    $secData = $null; $secFund = $null
    if ($industry -ne "") {
        $secData = $GlobalSectors | Where-Object { $_.SectorName -eq $industry }
        $secFund = $GlobalSectorFund | Where-Object { $_.SectorName -eq $industry }
    }
    if ($secData) {
        $chg = $secData.ChangePct
        if     ($chg -ge 3)   { $score += 40 }
        elseif ($chg -ge 1)   { $score += 30 }
        elseif ($chg -ge 0)   { $score += 20 }
        elseif ($chg -ge -1)  { $score += 15 }
        else                  { $score += 5 }
    } else {
        $avgChg = ($GlobalSectors | Measure-Object ChangePct -Average).Average
        if ($avgChg -ge 1) { $score += 25 } elseif ($avgChg -ge 0) { $score += 18 } else { $score += 10 }
    }
    if ($secFund) {
        $ni = $secFund.NetInflow
        if     ($ni -gt 5e8)   { $score += 30 }
        elseif ($ni -gt 0)     { $score += 20 }
        elseif ($ni -gt -3e8)  { $score += 10 }
        else                   { $score += 3 }
    } else { $score += 15 }
    if ($secData -and $D.Quote.ChangePct -ne 0) {
        $relStr = $D.Quote.ChangePct - $secData.ChangePct
        if     ($relStr -gt 2)   { $score += 30 }
        elseif ($relStr -gt 0)   { $score += 20 }
        elseif ($relStr -gt -2)  { $score += 10 }
        else                     { $score += 3 }
    } else { $score += 15 }
    return [Math]::Min([Math]::Max($score, 0), 100)
}

function Get-CapitalScore {
    param($D)
    $score = 0
    $ff = $D.FundFlow
    if ($ff -and $ff.Count -gt 0) {
        $netInflows = $ff | ForEach-Object { $_.MainNetInflow }
        $posDays = ($netInflows | Where-Object { $_ -gt 0 }).Count
        $total = $netInflows.Count
        if ($total -gt 0) {
            $ratio = $posDays / $total
            $cum = ($netInflows | Measure-Object -Sum).Sum
            if     ($ratio -ge 0.8 -and $cum -gt 0) { $score += 35 }
            elseif ($ratio -ge 0.6)                  { $score += 22 }
            elseif ($ratio -ge 0.4)                  { $score += 12 }
            else                                     { $score += 4 }
        }
    } else { $score += 15 }
    $nb = $D.Northbound
    if ($nb -and $nb.SharesRatio -gt 0) {
        $sr = $nb.SharesRatio
        if ($sr -ge 5) { $score += 35 } elseif ($sr -ge 3) { $score += 25 } elseif ($sr -ge 1) { $score += 15 } else { $score += 8 }
    } else { $score += 15 }
    $mg = $D.Margin
    if ($mg -and $mg.Count -ge 2) {
        $rzStart = $mg[0].RZYE; $rzEnd = $mg[-1].RZYE
        if ($rzStart -gt 0) {
            $chg = ($rzEnd - $rzStart) / $rzStart * 100
            if ($chg -gt 1) { $score += 30 } elseif ($chg -gt -0.5) { $score += 18 } elseif ($chg -gt -3) { $score += 8 } else { $score += 3 }
        }
    } else { $score += 15 }
    return [Math]::Min([Math]::Max($score, 0), 100)
}

function Get-MacroScore {
    param($GlobalSectors)
    $score = 0
    $total = $GlobalSectors.Count
    if ($total -eq 0) { return 50 }
    $positive = ($GlobalSectors | Where-Object { $_.ChangePct -ge 0 }).Count
    $posRatio = $positive / $total
    $score += [Math]::Round($posRatio * 50)
    $strong = ($GlobalSectors | Where-Object { $_.ChangePct -ge 2 -and $_.Turnover -gt 80 }).Count
    $strongRatio = $strong / $total
    $score += [Math]::Round([Math]::Min($strongRatio * 100, 50))
    return [Math]::Min($score, 100)
}

function Get-CompositeScore {
    param($TechS, $FundS, $SentS, $SectS, $CapS, $MacS)
    $composite = $TechS * 0.25 + $FundS * 0.20 + $SentS * 0.15 + $SectS * 0.20 + $CapS * 0.15 + $MacS * 0.05
    $composite = [Math]::Round([Math]::Max([Math]::Min($composite, 100), 0))
    $ratingShort = if ($composite -ge 85) { "强烈关注" } elseif ($composite -ge 70) { "关注" } elseif ($composite -ge 55) { "观察" } elseif ($composite -ge 40) { "谨慎" } else { "回避" }
    return @{ Score = $composite; RatingShort = $ratingShort }
}

function Get-TrendHealth {
    param($D)
    $h = 0
    if (-not $D.KLines -or $D.KLines.Count -lt 20) { return @{ Score = 50; Label = "数据不足" } }
    $high20 = ($D.KLines[-20..-1] | Measure-Object High -Maximum).Maximum
    $pullback = ($high20 - $D.Price) / $high20 * 100
    if     ($pullback -lt 3)   { $h += 20 } elseif ($pullback -lt 8) { $h += 15 } elseif ($pullback -lt 15) { $h += 8 } else { $h += 2 }
    $recentVol = ($D.KLines[-3..-1] | Measure-Object Volume -Average).Average
    $avgVol = $D.VolMA20[-1]
    if ($avgVol -gt 0) {
        $vr = $recentVol / $avgVol
        if ($vr -ge 1.2) { $h += 20 } elseif ($vr -ge 0.8) { $h += 12 } else { $h += 5 }
    } else { $h += 10 }
    $m5 = $D.MA5[-1]; $m20 = $D.MA20[-1]
    if ($m20 -gt 0) {
        $spread = ($m5 - $m20) / $m20 * 100
        if ($spread -gt 2) { $h += 20 } elseif ($spread -gt 0.5) { $h += 14 } elseif ($spread -gt -1) { $h += 8 } elseif ($spread -gt -3) { $h += 3 } else { $h += 0 }
    } else { $h += 10 }
    if ($D.MACD) {
        $df = $D.MACD.DIF[-1]; $da = $D.MACD.DEA[-1]; $mh = $D.MACD.MACD[-1]
        if ($df -gt $da -and $df -gt 0 -and $mh -gt 0) { $h += 20 } elseif ($df -gt $da -and $df -gt 0) { $h += 14 } elseif ($df -gt $da) { $h += 8 } else { $h += 2 }
    } else { $h += 10 }
    if ($D.RSI14.Count -ge 5) {
        $rNow = [double]$D.RSI14[-1]; $rPrev = [double]$D.RSI14[-5]
        if ($rNow -ge 50 -and $rNow -le 70 -and $rNow -gt $rPrev) { $h += 20 } elseif ($rNow -ge 40 -and $rNow -le 60) { $h += 12 } elseif ($rNow -gt 70) { $h += 5 } elseif ($rNow -lt 30) { $h += 3 } else { $h += 8 }
    } else { $h += 10 }
    $hs = [Math]::Min([Math]::Max($h, 0), 100)
    $label = if ($hs -ge 80) { "健康" } elseif ($hs -ge 60) { "预警关注" } elseif ($hs -ge 40) { "警戒" } else { "危险" }
    return @{ Score = $hs; Label = $label; Pullback = $pullback }
}

function Get-ThreePeriodPrediction {
    param($D, $TechS, $FundS, $SectS, $CapS)
    $shortBull = 0
    if ($D.KLines.Count -ge 5 -and $D.MA5[-1] -gt $D.MA10[-1]) { $shortBull++ }
    if ($D.RSI14.Count -gt 0 -and [double]$D.RSI14[-1] -gt 45 -and [double]$D.RSI14[-1] -lt 70) { $shortBull++ }
    if ($D.MACD -and $D.MACD.DIF[-1] -gt $D.MACD.DEA[-1]) { $shortBull++ }
    if ($D.KLines.Count -ge 3 -and $D.KLines[-1].Close -gt $D.KLines[-3].Close) { $shortBull++ }
    $shortDir = if ($shortBull -ge 3) { "看多" } elseif ($shortBull -eq 2) { "偏多" } elseif ($shortBull -eq 1) { "中性" } else { "看空" }
    $midBull = 0
    if ($D.MA20.Count -gt 0 -and $D.MA50.Count -gt 0 -and $D.MA20[-1] -gt $D.MA50[-1]) { $midBull++ }
    if ($SectS -ge 55) { $midBull++ }
    if ($FundS -ge 55) { $midBull++ }
    $midDir = if ($midBull -ge 2) { if ($midBull -eq 3) { "趋势看多" } else { "区间震荡" } } else { "趋势看空" }
    $longBull = 0
    if ($D.PEPercentile -and $D.PEPercentile.Percentile -lt 45) { $longBull++ }
    if ($FundS -ge 55) { $longBull++ }
    if ($D.MA120.Count -gt 0 -and $D.Price -gt $D.MA120[-1]) { $longBull++ }
    $longDir = if ($longBull -ge 2) { "长期看好" } elseif ($longBull -eq 1) { "长期中性" } else { "长期看空" }
    $support = if ($D.MA20.Count -gt 0) { [Math]::Round($D.MA20[-1], 2) } else { [Math]::Round($D.Price * 0.95, 2) }
    $resistance = if ($D.MA50.Count -gt 0) { [Math]::Round($D.MA50[-1], 2) } elseif ($D.MA20.Count -gt 0) { [Math]::Round($D.MA20[-1] * 1.05, 2) } else { [Math]::Round($D.Price * 1.05, 2) }
    $stopLoss = [Math]::Round($support * 0.93, 2)
    $confidence = if ($shortBull -ge 3) { "高(>70%)" } elseif ($shortBull -eq 2) { "中(50-70%)" } else { "低(<50%)" }
    return @{
        Short = $shortDir; Mid = $midDir; Long = $longDir
        Support = $support; Resistance = $resistance; StopLoss = $stopLoss
        Confidence = $confidence; ShortBull = $shortBull
        MidBull = $midBull; LongBull = $longBull
    }
}

# ============================================================
# 复用：评估函数（来自 run_keystock_evaluation.ps1）
# ============================================================

function Get-PearsonR {
    param([double[]]$X, [double[]]$Y)
    $n = $X.Length
    if ($n -lt 3) { return 0, 0 }
    $meanX = ($X | Measure-Object -Average).Average
    $meanY = ($Y | Measure-Object -Average).Average
    $cov = 0.0; $varX = 0.0; $varY = 0.0
    for ($i = 0; $i -lt $n; $i++) {
        $dx = $X[$i] - $meanX; $dy = $Y[$i] - $meanY
        $cov += $dx * $dy; $varX += $dx * $dx; $varY += $dy * $dy
    }
    $denom = [Math]::Sqrt($varX * $varY)
    if ($denom -eq 0) { return 0, $n }
    return [Math]::Round($cov / $denom, 4), $n
}

function Get-SignalWinRate {
    param($MatchedList, $SignalField, $SignalValue)
    $matching = $MatchedList | Where-Object { $_."$SignalField" -eq $SignalValue }
    $cnt = @($matching).Count
    if ($cnt -eq 0) { return @{ Count=0; Wins=0; WinRate=0 } }
    $wins = @($matching | Where-Object { $_.ReturnPct -gt 0 }).Count
    return @{ Count=$cnt; Wins=$wins; WinRate=[Math]::Round($wins/$cnt*100, 1) }
}

function Get-SignalRating {
    param($WinRate)
    if ($WinRate -ge 65) { return "强有效" }
    elseif ($WinRate -ge 50) { return "有参考价值" }
    elseif ($WinRate -ge 40) { return "随机水平" }
    else { return "反向信号" }
}

# ============================================================
# 信号提取函数
# ============================================================

function Get-SignalsFromData {
    param($D)
    # 加入 null 保护，避免某些情况下数组为空的索引错误
    try {
        $m5 = if ($D.MA5 -and $D.MA5.Count -gt 0) { $D.MA5[-1] } else { $null }
        $m10 = if ($D.MA10 -and $D.MA10.Count -gt 0) { $D.MA10[-1] } else { $null }
        $m20 = if ($D.MA20 -and $D.MA20.Count -gt 0) { $D.MA20[-1] } else { $null }
        $p = $D.Price
        $maTrend = if ($m5 -gt $m10 -and $m10 -gt $m20 -and $p -gt $m20) { "多头排列" }
                   elseif ($m5 -lt $m10 -and $m10 -lt $m20) { "空头排列" }
                   else { "纠缠/不明" }
    } catch { $maTrend = "N/A" }
    try {
        $macdObj = $D.MACD
        $macdDIF = if ($macdObj -and $macdObj.DIF -and $macdObj.DIF.Count -gt 0) { $macdObj.DIF[-1] } else { $null }
        $macdDEA = if ($macdObj -and $macdObj.DEA -and $macdObj.DEA.Count -gt 0) { $macdObj.DEA[-1] } else { $null }
        if ($macdDIF -ne $null -and $macdDEA -ne $null) {
            $macdPos = if ($macdDIF -gt $macdDEA -and $macdDIF -gt 0) { "零轴上金叉" }
                       elseif ($macdDIF -gt $macdDEA) { "零轴下金叉" }
                       else { "死叉" }
        } else { $macdPos = "N/A" }
    } catch { $macdPos = "N/A" }
    try {
        $rsiArr = $D.RSI14
        $rsiVal = if ($rsiArr -and $rsiArr.Count -gt 0) { [double]$rsiArr[-1] } else { 50 }
        $rsiZone = if ($rsiVal -ge 70) { "超买" } elseif ($rsiVal -ge 50) { "中性偏强" } elseif ($rsiVal -ge 30) { "中性偏弱" } else { "超卖" }
    } catch { $rsiVal = 50; $rsiZone = "N/A" }
    try {
        $boll = $D.Bollinger
        if ($boll -and $boll.Upper -and $boll.Upper.Count -gt 0 -and $D.KLines -and $D.KLines.Count -gt 0) {
            $c = $D.KLines[-1].Close; $u = $boll.Upper[-1]; $m = $boll.MA[-1]; $l = $boll.Lower[-1]
            $bollPos = if ($c -ge $u) { "触及上轨" } elseif ($c -ge $m) { "中轨上方" } elseif ($c -ge $l) { "中轨下方" } else { "触及下轨" }
        } else { $bollPos = "N/A" }
    } catch { $bollPos = "N/A" }
    try {
        if ($D.VolMA5 -and $D.VolMA5.Count -gt 1 -and $D.VolMA5[-2] -gt 0) {
            $vr = $D.KLines[-1].Volume / $D.VolMA5[-2]
            $cg = $D.ChangePct
            $volRel = if ($cg -ge 2 -and $vr -ge 1.5) { "放量上涨" } elseif ($cg -ge 0 -and $vr -le 1.1) { "缩量上涨" } elseif ($cg -lt -2 -and $vr -ge 1.5) { "放量下跌" } elseif ($cg -lt 0 -and $vr -le 0.8) { "缩量下跌" } else { "量能正常" }
        } else { $volRel = "N/A" }
    } catch { $volRel = "N/A" }
    return @{
        MA_Trend = $maTrend; MACD_Position = $macdPos
        RSI_Value = [Math]::Round($rsiVal,1); RSI_Zone = $rsiZone
        Bollinger_Position = $bollPos; Volume_Relation = $volRel
        ShortBull_Score = 0
    }
}

# ============================================================
# 数据采集
# ============================================================

Write-Host "`n[1/4] 采集数据..." -ForegroundColor Cyan

# 全局板块数据
Write-Host "  [全局] 板块TOP20..."
$globalSectors = Invoke-ThrottledApi { Get-SectorData -Top 20 }
$globalSectorFund = Invoke-ThrottledApi { Get-SectorFundFlow -Top 20 }
Write-Host "  [OK] 板块: $($globalSectors.Count) 行业, $($globalSectorFund.Count) 资金流向"

# 各股票数据
$stockDataMap = @{}
$allTradingDays = $null

foreach ($s in $stocks) {
    $code = $s.Code; $name = $s.Name
    Write-Host "  [$name] 获取数据..."

    # K线 120日（从新浪获取，含历史数据）
    $klines = Invoke-ThrottledApi { Get-StockKLine -Code $code -Scale 240 -Count 150 }
    if (-not $klines -or $klines.Count -lt 60) {
        Write-Warning "    K线数据不足: $($klines.Count)日"
        continue
    }
    Write-Host "    K线: $($klines.Count)日 ($($klines[0].Date) ~ $($klines[-1].Date))"

    # 统一交易日期（用第一只股票确定交易日历）
    if (-not $allTradingDays) {
        $allTradingDays = $klines | ForEach-Object { $_.Date }
    }

    # 财务数据
    $fin = Invoke-ThrottledApi { Get-StockFinancial -Code $code -Quarters 4 }

    # PE百分位
    $pePct = Invoke-ThrottledApi { Get-PEPercentile -Code $code -LookbackYears 5 }

    # 资金面（当前快照）
    $fundFlow = Invoke-ThrottledApi { Get-StockFundFlow -Code $code -Days 5 }
    $northbound = Invoke-ThrottledApi { Get-NorthboundHold -Code $code }
    $research = Invoke-ThrottledApi { Get-StockResearch -Code $code -Count 5 -DaysBack 30 }
    $margin = Invoke-ThrottledApi { Get-MarginData -Code $code -Days 5 }
    $quote = Invoke-ThrottledApi { Get-StockQuote -Code $code }

    $stockDataMap[$code] = @{
        KLines = $klines; Financial = $fin; PEPercentile = $pePct
        FundFlow = $fundFlow; Northbound = $northbound
        Research = $research; Margin = $margin
        Quote = $quote
    }
}

if (-not $allTradingDays) { Write-Error "无法获取交易日历"; exit 1 }

Write-Host "[OK] 数据采集完成, API调用: $script:apiCallCount 次"

# ============================================================
# 回测主循环
# ============================================================

Write-Host "`n[2/4] 运行滑窗回测..." -ForegroundColor Cyan

# --- Debug: 单次测试（先用第一个失败日期）---
$debugCode = $stocks[0].Code
$debugDate = $allTradingDays[110]  # 接近第一个回测日
$debugSD = $stockDataMap[$debugCode]
Write-Host "[DEBUG] 测试: $($stocks[0].Name) @ $debugDate"
$debugKlines = $debugSD.KLines
$debugSliced = $debugKlines | Where-Object { $_.Date -le $debugDate }
Write-Host "[DEBUG] K线切片: $($debugSliced.Count) 条"
if ($debugSliced.Count -ge 30) {
    try {
        $dm5 = Calc-MovingAverage -Data $debugSliced -Period 5
        $dm10 = Calc-MovingAverage -Data $debugSliced -Period 10
        $dm20 = Calc-MovingAverage -Data $debugSliced -Period 20
        $drsi = Calc-RSI -Data $debugSliced -Period 14
        $dmacd = Calc-MACD -Data $debugSliced
        $dboll = Calc-Bollinger -Data $debugSliced
        Write-Host "[DEBUG] MACD.DIF type=$($dmacd.DIF.GetType()) count=$($dmacd.DIF.Count) last=$($dmacd.DIF[-1])"
        Write-Host "[DEBUG] KLines[-1] type=$($debugSliced[-1].GetType())"
        Write-Host "[DEBUG] Close=$($debugSliced[-1].Close) Vol=$($debugSliced[-1].Volume)"
        if ($dmacd.DIF[-1] -eq $null) { Write-Host "[DEBUG] *** DIF[-1] IS NULL ***" }
        $dquote = [PSCustomObject]@{ Price=$debugSliced[-1].Close; ChangePct=0; TurnoverRate=0; PE=0; MktCap=0; Name=""; Amplitude=0 }
        $dobj = [PSCustomObject]@{
            KLines=$debugSliced; Price=$debugSliced[-1].Close
            MA5=$dm5; MA10=$dm10; MA20=$dm20; MA50=@(); MA120=@()
            RSI14=$drsi; MACD=$dmacd; Bollinger=$dboll
            VolMA5=Calc-MovingAverage -Data $debugSliced -Field Volume -Period 5
            VolMA20=Calc-MovingAverage -Data $debugSliced -Field Volume -Period 20
            Financial=$debugSD.Financial; PEPercentile=$debugSD.PEPercentile
            FundFlow=$debugSD.FundFlow; Northbound=$debugSD.Northbound
            Research=$debugSD.Research; Margin=$debugSD.Margin
            Quote=$dquote
        }
        $dts = Get-TechScore -D $dobj
        Write-Host "[DEBUG] TechScore=$dts"
        $dsig = Get-SignalsFromData -D $dobj
        Write-Host "[DEBUG] Signals OK: MA_Trend=$($dsig.MA_Trend) MACD=$($dsig.MACD_Position)"
    } catch { Write-Host "[DEBUG] FAIL at $($_.InvocationInfo.ScriptLineNumber): $_" }
}

$allResults = @()
$totalDays = $allTradingDays.Count
$endIdx = $totalDays - 3  # 留3天算forward return

# 确定回测天数
$backtestStartIdx = [Math]::Max($endIdx - $Days + 1, 60)  # 至少60天用于指标预热
$backtestDates = $allTradingDays[$backtestStartIdx..$endIdx]
Write-Host "  交易日: $($backtestDates[0]) ~ $($backtestDates[-1]) ($($backtestDates.Count)天)"

$completed = 0
$total = $backtestDates.Count * $stocks.Count
$hasError = $false

foreach ($dateStr in $backtestDates) {
    foreach ($s in $stocks) {
        $code = $s.Code; $name = $s.Name
        $sd = $stockDataMap[$code]
        if (-not $sd) { continue }

        $klines = $sd.KLines

        # 切片K线
        $sliced = $klines | Where-Object { $_.Date -le $dateStr }
        if ($sliced.Count -lt 30) { $completed++; continue }

        try {
            # --- 计算技术指标 ---
            $ma5   = Calc-MovingAverage -Data $sliced -Period 5
            $ma10  = Calc-MovingAverage -Data $sliced -Period 10
            $ma20  = Calc-MovingAverage -Data $sliced -Period 20
            $ma50  = if ($sliced.Count -ge 50) { Calc-MovingAverage -Data $sliced -Period 50 } else { @() }
            $ma120 = if ($sliced.Count -ge 120) { Calc-MovingAverage -Data $sliced -Period 120 } else { @() }
            $rsi14 = Calc-RSI -Data $sliced -Period 14
            $macd  = Calc-MACD -Data $sliced
            $boll  = Calc-Bollinger -Data $sliced
            $vol5  = Calc-MovingAverage -Data $sliced -Field Volume -Period 5
            $vol20 = Calc-MovingAverage -Data $sliced -Field Volume -Period 20

            $lastBar = $sliced[-1]
            $price = $lastBar.Close
            # 用前一根K线的收盘价计算涨跌幅（模拟盘中实时）
            $chgPct = if ($sliced.Count -ge 2) { [Math]::Round(($lastBar.Close / $sliced[-2].Close - 1) * 100, 2) } else { 0 }
            $turnoverRateRaw = 0
            if ($sd.Quote) { $turnoverRateRaw = $sd.Quote.TurnoverRate }

            # 构建 D 对象
            $D = [PSCustomObject]@{
                Code = $code; Name = $name; Price = $price
                KLines = $sliced
                MA5 = $ma5; MA10 = $ma10; MA20 = $ma20; MA50 = $ma50; MA120 = $ma120
                RSI14 = $rsi14; MACD = $macd; Bollinger = $boll
                VolMA5 = $vol5; VolMA20 = $vol20
                Financial = $sd.Financial; PEPercentile = $sd.PEPercentile
                FundFlow = $sd.FundFlow; Northbound = $sd.Northbound
                Research = $sd.Research; Margin = $sd.Margin
                Quote = [PSCustomObject]@{
                    Price = $price; ChangePct = $chgPct; TurnoverRate = $turnoverRateRaw
                    PE = 0; MktCap = 0; Name = $name; Amplitude = 0
                }
            }

            # --- 评分 ---
            $techS = Get-TechScore -D $D
            $fundS = Get-FundamentalScore -D $D
            $sentS = Get-SentimentScore -D $D
            $sectS = Get-SectorScore -D $D -GlobalSectors $globalSectors -GlobalSectorFund $globalSectorFund
            $capS  = Get-CapitalScore -D $D
            $macS  = Get-MacroScore -GlobalSectors $globalSectors
            $comp  = Get-CompositeScore -TechS $techS -FundS $fundS -SentS $sentS -SectS $sectS -CapS $capS -MacS $macS

            # --- 预测 ---
            $health = Get-TrendHealth -D $D
            $pred   = Get-ThreePeriodPrediction -D $D -TechS $techS -FundS $fundS -SectS $sectS -CapS $capS

            # --- 信号 ---
            $signals = Get-SignalsFromData -D $D
            $signals.ShortBull_Score = $pred.ShortBull

            # --- Forward收益（真实后验） ---
            $idx = [array]::IndexOf($klines.Date, $dateStr)
            $fwd1 = if ($idx -ge 0 -and $idx + 1 -lt $klines.Count) { [Math]::Round(($klines[$idx+1].Close / $lastBar.Close - 1) * 100, 2) } else { $null }
            $fwd3 = if ($idx -ge 0 -and $idx + 3 -lt $klines.Count) { [Math]::Round(($klines[$idx+3].Close / $lastBar.Close - 1) * 100, 2) } else { $null }
            $fwd5 = if ($idx -ge 0 -and $idx + 5 -lt $klines.Count) { [Math]::Round(($klines[$idx+5].Close / $lastBar.Close - 1) * 100, 2) } else { $null }

            # 支撑/阻力触及检查（T+5内）
            $supportHit = $false; $resistanceHit = $false
            if ($idx -ge 0) {
                $lookahead = $klines | Select-Object -Skip ($idx + 1) -First 5
                foreach ($k in $lookahead) {
                    if ($k.Low -le $pred.Support) { $supportHit = $true }
                    if ($k.High -ge $pred.Resistance) { $resistanceHit = $true }
                }
            }

            # --- 记录 ---
            $allResults += [PSCustomObject]@{
                Date = $dateStr; Code = $code; Name = $name; Industry = $s.Industry
                Price = $price; ChangePct = $chgPct

                TechScore = $techS; FundScore = $fundS; SentScore = $sentS
                SectScore = $sectS; CapScore = $capS; MacScore = $macS
                CompositeScore = $comp.Score; Rating = $comp.RatingShort

                TrendHealthScore = $health.Score; TrendHealthLabel = $health.Label

                ShortPred = $pred.Short; MidPred = $pred.Mid; LongPred = $pred.Long
                Confidence = $pred.Confidence
                ShortBull = $pred.ShortBull; MidBull = $pred.MidBull; LongBull = $pred.LongBull

                Support = $pred.Support; Resistance = $pred.Resistance; StopLoss = $pred.StopLoss

                FwdReturn1 = $fwd1; FwdReturn3 = $fwd3; FwdReturn5 = $fwd5
                SupportHit = $supportHit; ResistanceHit = $resistanceHit

                Signals = $signals
            }
        } catch {
            if (-not $hasError) {
                $errLine = $_.InvocationInfo.ScriptLineNumber
                Write-Warning "    [$name @ $dateStr] 行${errLine}: $_"
                $hasError = $true
            }
        }

        $completed++
        if ($completed % 30 -eq 0) { Write-Host "   进度: $completed/$total" }
    }
}

Write-Host "[OK] 回测完成, 有效样本: $($allResults.Count) 条"

# ============================================================
# 结果分析
# ============================================================

Write-Host "`n[3/4] 分析结果..." -ForegroundColor Cyan

if ($allResults.Count -eq 0) { Write-Error "无有效回测结果"; exit 1 }

# 1. 评分区分度（按综合评分分组）
$scoreGroups = @{}
foreach ($r in $allResults) {
    $group = if ($r.CompositeScore -ge 80) { "优秀(≥80)" }
             elseif ($r.CompositeScore -ge 60) { "良好(60-79)" }
             elseif ($r.CompositeScore -ge 40) { "一般(40-59)" }
             else { "差(<40)" }
    if (-not $scoreGroups[$group]) { $scoreGroups[$group] = @() }
    $scoreGroups[$group] += $r.FwdReturn1
}

$discrimination = @{}
foreach ($g in $scoreGroups.Keys | Sort-Object) {
    $returns = $scoreGroups[$g] | Where-Object { $_ -ne $null }
    if ($returns.Count -gt 0) {
        $avgReturn = ($returns | Measure-Object -Average).Average
        $positiveRatio = (@($returns | Where-Object { $_ -gt 0 }).Count / $returns.Count * 100)
        $discrimination[$g] = @{ Count = $returns.Count; AvgReturn = [Math]::Round($avgReturn, 2); PositiveRatio = [Math]::Round($positiveRatio, 1) }
    }
}

# 2. 维度相关性
$dimResults = @()
$dimensions = @(
    @{ Name="技术面"; Field="TechScore" },
    @{ Name="基本面"; Field="FundScore" },
    @{ Name="消息面"; Field="SentScore" },
    @{ Name="板块行业"; Field="SectScore" },
    @{ Name="资金面"; Field="CapScore" },
    @{ Name="宏观大盘"; Field="MacScore" },
    @{ Name="综合评分"; Field="CompositeScore" }
)

foreach ($dim in $dimensions) {
    $pairs = $allResults | Where-Object { $_."$($dim.Field)" -ne $null -and $_.FwdReturn1 -ne $null }
    if ($pairs.Count -ge 3) {
        $r, $n = Get-PearsonR -X ($pairs | ForEach-Object { [double]$_."$($dim.Field)" }) -Y ($pairs | ForEach-Object { [double]$_.FwdReturn1 })
        $dimResults += [PSCustomObject]@{ Name=$dim.Name; R=$r; Samples=$n }
    }
}

# 3. 方向预测准确率
$directionAccuracy = @{}
$directions = @("看多", "偏多", "中性", "看空")
foreach ($dir in $directions) {
    $matches = $allResults | Where-Object { $_.ShortPred -eq $dir -and $_.FwdReturn1 -ne $null }
    if ($matches.Count -gt 0) {
        $win = @($matches | Where-Object { $_.FwdReturn1 -gt 0 }).Count
        $directionAccuracy[$dir] = @{ Count = $matches.Count; Wins = $win; WinRate = [Math]::Round($win / $matches.Count * 100, 1) }
    }
}

# 4. 置信度校准
$confCalibration = @{}
$confLevels = @("高(>70%)", "中(50-70%)", "低(<50%)")
foreach ($cl in $confLevels) {
    $matches = $allResults | Where-Object { $_.Confidence -eq $cl -and $_.FwdReturn1 -ne $null }
    if ($matches.Count -gt 0) {
        $win = @($matches | Where-Object { $_.FwdReturn1 -gt 0 }).Count
        $confCalibration[$cl] = @{ Count = $matches.Count; Wins = $win; WinRate = [Math]::Round($win / $matches.Count * 100, 1) }
    }
}

# 5. 信号胜率（展平嵌套 Signals 属性后分析）
$signalResults = @()

# 预定义要分析的信号
$signalChecks = @(
    @{ Name="MA趋势_多头排列"; Prop="MA_Trend"; Value="多头排列" }
    @{ Name="MA趋势_空头排列"; Prop="MA_Trend"; Value="空头排列" }
    @{ Name="MA趋势_纠缠不明"; Prop="MA_Trend"; Value="纠缠/不明" }
    @{ Name="MACD_零轴上金叉"; Prop="MACD_Position"; Value="零轴上金叉" }
    @{ Name="MACD_死叉"; Prop="MACD_Position"; Value="死叉" }
    @{ Name="RSI_超买"; Prop="RSI_Zone"; Value="超买" }
    @{ Name="RSI_超卖"; Prop="RSI_Zone"; Value="超卖" }
    @{ Name="RSI_中性偏强"; Prop="RSI_Zone"; Value="中性偏强" }
    @{ Name="RSI_中性偏弱"; Prop="RSI_Zone"; Value="中性偏弱" }
    @{ Name="布林_中轨上方"; Prop="Bollinger_Position"; Value="中轨上方" }
    @{ Name="布林_中轨下方"; Prop="Bollinger_Position"; Value="中轨下方" }
    @{ Name="布林_触及上轨"; Prop="Bollinger_Position"; Value="触及上轨" }
    @{ Name="布林_触及下轨"; Prop="Bollinger_Position"; Value="触及下轨" }
    @{ Name="量能_放量上涨"; Prop="Volume_Relation"; Value="放量上涨" }
    @{ Name="量能_缩量下跌"; Prop="Volume_Relation"; Value="缩量下跌" }
    @{ Name="量能_放量下跌"; Prop="Volume_Relation"; Value="放量下跌" }
)

foreach ($sc in $signalChecks) {
    $matching = $allResults | Where-Object {
        $_.Signals -and $_.Signals."$($sc.Prop)" -eq $sc.Value -and $_.FwdReturn1 -ne $null
    }
    $cnt = @($matching).Count
    if ($cnt -gt 0) {
        $wins = @($matching | Where-Object { $_.FwdReturn1 -gt 0 }).Count
        $wr = [Math]::Round($wins / $cnt * 100, 1)
        $signalResults += [PSCustomObject]@{
            Name = $sc.Name; Count = $cnt; Wins = $wins; WinRate = $wr
            Rating = Get-SignalRating -WinRate $wr
        }
    }
}
$signalResults = $signalResults | Where-Object { $_.Count -ge 3 } | Sort-Object WinRate -Descending

# 6. 趋势健康度区分度
$healthGroups = @{}
foreach ($r in $allResults) {
    $hLabel = $r.TrendHealthLabel
    if (-not $healthGroups[$hLabel]) { $healthGroups[$hLabel] = @() }
    if ($r.FwdReturn1 -ne $null) { $healthGroups[$hLabel] += $r.FwdReturn1 }
}
$healthDiscrimination = @{}
foreach ($h in $healthGroups.Keys | Sort-Object) {
    $rets = $healthGroups[$h]
    if ($rets.Count -gt 0) {
        $healthDiscrimination[$h] = @{
            Count = $rets.Count
            AvgReturn = [Math]::Round(($rets | Measure-Object -Average).Average, 2)
            PositiveRatio = [Math]::Round((@($rets | Where-Object { $_ -gt 0 }).Count / $rets.Count * 100), 1)
        }
    }
}

# 7. 支撑/阻力准确率
$supportStats = @{
    TotalHit = (@($allResults | Where-Object { $_.SupportHit -eq $true }).Count)
    TotalMiss = (@($allResults | Where-Object { $_.SupportHit -eq $false }).Count)
    ResistanceHit = (@($allResults | Where-Object { $_.ResistanceHit -eq $true }).Count)
    ResistanceMiss = (@($allResults | Where-Object { $_.ResistanceHit -eq $false }).Count)
}
$supportStats.Total = $supportStats.TotalHit + $supportStats.TotalMiss
$supportStats.ResistanceTotal = $supportStats.ResistanceHit + $supportStats.ResistanceMiss

# 8. 各股票平均收益
$stockAvg = @{}
foreach ($r in $allResults) {
    if (-not $stockAvg[$r.Name]) { $stockAvg[$r.Name] = @{ Fwd1=@(); Fwd3=@(); Fwd5=@() } }
    if ($r.FwdReturn1 -ne $null) { $stockAvg[$r.Name].Fwd1 += $r.FwdReturn1 }
    if ($r.FwdReturn3 -ne $null) { $stockAvg[$r.Name].Fwd3 += $r.FwdReturn3 }
    if ($r.FwdReturn5 -ne $null) { $stockAvg[$r.Name].Fwd5 += $r.FwdReturn5 }
}
$stockSummary = @{}
foreach ($sn in $stockAvg.Keys | Sort-Object) {
    $d = $stockAvg[$sn]
    $f1 = if ($d.Fwd1.Count -gt 0) { [Math]::Round(($d.Fwd1 | Measure-Object -Average).Average, 2) } else { 0 }
    $f3 = if ($d.Fwd3.Count -gt 0) { [Math]::Round(($d.Fwd3 | Measure-Object -Average).Average, 2) } else { 0 }
    $f5 = if ($d.Fwd5.Count -gt 0) { [Math]::Round(($d.Fwd5 | Measure-Object -Average).Average, 2) } else { 0 }
    $win1 = [Math]::Round((@($d.Fwd1 | Where-Object { $_ -gt 0 }).Count / [Math]::Max($d.Fwd1.Count, 1) * 100), 1)
    $stockSummary[$sn] = @{ Fwd1Avg=$f1; Fwd3Avg=$f3; Fwd5Avg=$f5; WinRate1=$win1; Count=$d.Fwd1.Count }
}

# 9. 评分趋势稳定性（各期平均收益的波动）
$periodAverages = @{}
foreach ($r in $allResults) {
    if (-not $periodAverages[$r.Date]) { $periodAverages[$r.Date] = @() }
    if ($r.FwdReturn1 -ne $null) { $periodAverages[$r.Date] += $r.FwdReturn1 }
}
$periodMeans = @()
foreach ($d in $periodAverages.Keys | Sort-Object) {
    $pm = ($periodAverages[$d] | Measure-Object -Average).Average
    $periodMeans += [Math]::Round($pm, 2)
}
$stabilityMAD = if ($periodMeans.Count -ge 3) {
    $overallMean = ($periodMeans | Measure-Object -Average).Average
    ($periodMeans | ForEach-Object { [Math]::Abs($_ - $overallMean) } | Measure-Object -Average).Average
} else { 0 }

Write-Host "[OK] 分析完成"

# ============================================================
# 保存原始数据
# ============================================================

Write-Host "`n[4/4] 生成报告..." -ForegroundColor Cyan

# 缩减版结果（不含PSMetadata便于序列化）
$resultsSimple = $allResults | ForEach-Object {
    [PSCustomObject]@{
        Date = $_.Date; Code = $_.Code; Name = $_.Name; Industry = $_.Industry
        Price = $_.Price; ChangePct = $_.ChangePct
        TechScore = $_.TechScore; FundScore = $_.FundScore; SentScore = $_.SentScore
        SectScore = $_.SectScore; CapScore = $_.CapScore; MacScore = $_.MacScore
        CompositeScore = $_.CompositeScore; Rating = $_.Rating
        TrendHealthScore = $_.TrendHealthScore; TrendHealthLabel = $_.TrendHealthLabel
        ShortPred = $_.ShortPred; MidPred = $_.MidPred; LongPred = $_.LongPred
        Confidence = $_.Confidence; ShortBull = $_.ShortBull
        FwdReturn1 = $_.FwdReturn1; FwdReturn3 = $_.FwdReturn3; FwdReturn5 = $_.FwdReturn5
        Support = $_.Support; Resistance = $_.Resistance; StopLoss = $_.StopLoss
        SupportHit = $_.SupportHit; ResistanceHit = $_.ResistanceHit
        Signals = $_.Signals
    }
}

$summaryData = @{
    GeneratedAt = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
    BacktestDays = $backtestDates.Count
    TotalSamples = $allResults.Count
    StockCount = $stocks.Count
    DateRange = "$($backtestDates[0]) ~ $($backtestDates[-1])"
    Discrimination = $discrimination
    DimensionCorrelation = $dimResults | ForEach-Object { @{ Name=$_.Name; R=$_.R; Samples=$_.Samples } }
    DirectionAccuracy = $directionAccuracy
    ConfidenceCalibration = $confCalibration
    SignalEffectiveness = $signalResults | ForEach-Object { @{ Name=$_.Name; Count=$_.Count; WinRate=$_.WinRate; Rating=$_.Rating } }
    HealthDiscrimination = $healthDiscrimination
    SupportAccuracy = $supportStats
    StockSummary = $stockSummary
    StabilityMAD = [Math]::Round($stabilityMAD, 4)
}

$summaryJson = $summaryData | ConvertTo-Json -Depth 5 -Compress
Set-Content -Path (Join-Path $outDir "backtest_summary.json") -Value $summaryJson -Encoding UTF8

$resultsSimple | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $outDir "backtest_data.json") -Encoding UTF8
Write-Host "[OK] 原始数据: backtest_data.json + backtest_summary.json"

# ============================================================
# HTML报告生成
# ============================================================

function New-BacktestReportHtml {
    param($Summary, $Results, $DateRange, $TotalSamples)

    $css = @'
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: "Microsoft YaHei","微软雅黑",sans-serif; color: #333; background: #f0f2f5; padding: 20px; }
.report { max-width: 1100px; margin: 0 auto; background: #fff; padding: 30px 40px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
h1 { font-size: 24px; color: #1a1a2e; border-bottom: 3px solid #1a1a2e; padding-bottom: 8px; margin-bottom: 16px; }
h2 { font-size: 18px; color: #16213e; border-bottom: 2px solid #3498db; padding-bottom: 6px; margin: 24px 0 12px; }
h3 { font-size: 15px; color: #333; margin: 16px 0 8px; }
.subtitle { color: #666; font-size: 13px; margin-bottom: 20px; }
.badge { display: inline-block; padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: bold; color: #fff; }
.badge-green { background: #27ae60; } .badge-blue { background: #2980b9; }
.badge-yellow { background: #f39c12; } .badge-red { background: #e74c3c; }
.badge-gray { background: #95a5a6; }
table { width: 100%; border-collapse: collapse; margin: 8px 0 16px; font-size: 13px; }
th { background: #1a1a2e; color: #fff; padding: 8px 10px; text-align: center; font-weight: normal; }
td { padding: 6px 10px; border: 1px solid #e0e0e0; text-align: center; }
tr:nth-child(even) { background: #f8f9fa; }
.summary-grid { display: grid; grid-template-columns: repeat(3,1fr); gap: 12px; margin: 12px 0 20px; }
.summary-card { background: #f8f9fa; border-radius: 8px; padding: 16px; text-align: center; border-left: 4px solid #2980b9; }
.summary-card .num { font-size: 28px; font-weight: bold; color: #1a1a2e; }
.summary-card .lbl { font-size: 12px; color: #888; margin-top: 4px; }
.insight { background: #eef2f7; border-radius: 8px; padding: 14px 16px; margin: 12px 0; border-left: 4px solid #2980b9; }
.insight.good { border-left-color: #27ae60; } .insight.warn { border-left-color: #f39c12; } .insight.bad { border-left-color: #e74c3c; }
.insight .title { font-weight: bold; font-size: 14px; }
.insight .detail { font-size: 13px; color: #555; margin-top: 4px; line-height: 1.6; }
.winrate-bar { display: inline-block; height: 12px; border-radius: 3px; vertical-align: middle; margin-right: 4px; }
.footnote { margin-top: 24px; padding-top: 12px; border-top: 1px solid #ddd; font-size: 11px; color: #999; line-height: 1.8; }
'@

    $html = "<!DOCTYPE html><html lang='zh-CN'><head><meta charset='UTF-8'>"
    $html += "<title>铁律量化 — 分析逻辑30日回溯验证报告</title><style>$css</style></head><body>"
    $html += "<div class='report'>"

    $html += "<h1>分析逻辑30日回溯验证报告</h1>"
    $html += "<div class='subtitle'>铁律量化 · 生成日期: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') | 回测区间: $DateRange | 有效样本: $TotalSamples 条</div>"

    # === 摘要卡片 ===
    $html += "<div class='summary-grid'>"
    $html += "<div class='summary-card'><div class='num'>$TotalSamples</div><div class='lbl'>有效样本（股票×天数）</div></div>"
    $html += "<div class='summary-card'><div class='num'>$(if($dimResults.Count -gt 0){$dimResults[0].R}else{'N/A'})</div><div class='lbl'>技术面 vs 收益 r 值</div></div>"
    $html += "<div class='summary-card'><div class='num'>$([Math]::Round($stabilityMAD,2))</div><div class='lbl'>收益稳定性 MAD</div></div>"
    $html += "</div>"

    # === 1. 评分区分度 ===
    $html += "<h2>一、评分区分度</h2>"
    $html += "<p style='font-size:13px;color:#666;margin-bottom:8px;'>按综合评分分组，检查高分是否确实对应更高收益</p>"
    $html += "<table><thead><tr><th>评分区间</th><th>样本数</th><th>T+1平均收益%</th><th>T+1胜率%</th></tr></thead><tbody>"
    $prevReturn = $null
    foreach ($g in @("差(<40)","一般(40-59)","良好(60-79)","优秀(≥80)")) {
        if ($discrimination[$g]) {
            $d = $discrimination[$g]
            $color = if ($d.AvgReturn -gt 0) { "#e74c3c" } else { "#27ae60" }
            $arrow = if ($prevReturn -ne $null) { if ($d.AvgReturn -ge $prevReturn) { " ↑" } else { " ↓" } } else { "" }
            $html += "<tr><td>$g</td><td>$($d.Count)</td><td style='color:$color;font-weight:bold;'>$($d.AvgReturn)%</td><td>$($d.PositiveRatio)%</td></tr>"
            $prevReturn = $d.AvgReturn
        }
    }
    $html += "</tbody></table>"

    # 添加区分度判断
    $avgHigh = if ($discrimination["良好(60-79)"]) { $discrimination["良好(60-79)"].AvgReturn } else { 0 }
    $avgLow = if ($discrimination["差(<40)"]) { $discrimination["差(<40)"].AvgReturn } else { 0 }
    $spread = $avgHigh - $avgLow
    $insightClass = if ($spread -gt 1.5) { "good" } elseif ($spread -gt 0.5) { "" } else { "bad" }
    $insightText = if ($spread -gt 1.5) { "良好区分度：高分与低分组的平均收益差距 $([Math]::Round($spread,2))%，评分体系有效" } `
                   elseif ($spread -gt 0) { "有区分度但不够强：差距仅 $([Math]::Round($spread,2))%，建议关注权重分配" } `
                   else { "区分度不足：高分组收益并不优于低分组，需要审视评分逻辑" }
    $html += "<div class='insight $insightClass'><div class='title'>评分区分度：$([Math]::Round($spread,2))%</div><div class='detail'>$insightText</div></div>"

    # === 2. 维度相关性 ===
    $html += "<h2>二、维度与收益相关性</h2>"
    $html += "<p style='font-size:13px;color:#666;margin-bottom:8px;'>皮尔逊 r 值：各维度评分 vs T+1 实际收益（正值越大说明预测力越强）</p>"
    $html += "<table><thead><tr><th>维度</th><th>r 值</th><th>样本数</th><th>有效性</th></tr></thead><tbody>"
    foreach ($dr in ($dimResults | Sort-Object R -Descending)) {
        $eff = if ($dr.R -ge 0.15) { "<span class='badge badge-green'>有效</span>" }
               elseif ($dr.R -ge 0.05) { "<span class='badge badge-yellow'>弱有效</span>" }
               elseif ($dr.R -ge -0.05) { "<span class='badge badge-gray'>无相关性</span>" }
               else { "<span class='badge badge-red'>负相关</span>" }
        $rColor = if ($dr.R -gt 0) { "#27ae60" } elseif ($dr.R -lt 0) { "#e74c3c" } else { "#666" }
        $html += "<tr><td>$($dr.Name)</td><td style='color:$rColor;font-weight:bold;'>$($dr.R)</td><td>$($dr.Samples)</td><td>$eff</td></tr>"
    }
    $html += "</tbody></table>"

    # === 3. 方向预测准确率 ===
    $html += "<h2>三、方向预测准确率（T+1）</h2>"
    $html += "<table><thead><tr><th>预测方向</th><th>样本数</th><th>上涨次数</th><th>胜率%</th><th>评级</th></tr></thead><tbody>"
    foreach ($dir in $directions) {
        if ($directionAccuracy[$dir]) {
            $d = $directionAccuracy[$dir]
            $rating = Get-SignalRating -WinRate $d.WinRate
            $badgeClass = if ($d.WinRate -ge 65) { "badge-green" } elseif ($d.WinRate -ge 50) { "badge-blue" } elseif ($d.WinRate -ge 40) { "badge-yellow" } else { "badge-red" }
            $html += "<tr><td><strong>$dir</strong></td><td>$($d.Count)</td><td>$($d.Wins)</td><td>$($d.WinRate)%</td><td><span class='badge $badgeClass'>$rating</span></td></tr>"
        }
    }
    $html += "</tbody></table>"

    # === 4. 置信度校准 ===
    $html += "<h2>四、置信度校准</h2>"
    $html += "<p style='font-size:13px;color:#666;margin-bottom:8px;'>置信度越高，胜率应当越高</p>"
    $html += "<table><thead><tr><th>置信度</th><th>样本数</th><th>上涨次数</th><th>胜率%</th></tr></thead><tbody>"
    $prevConfWinRate = $null
    foreach ($cl in $confLevels) {
        if ($confCalibration[$cl]) {
            $d = $confCalibration[$cl]
            $calOk = if ($prevConfWinRate -ne $null -and $d.WinRate -ge $prevConfWinRate) { "↑" } elseif ($prevConfWinRate -ne $null) { "↓" } else { "" }
            $html += "<tr><td>$cl</td><td>$($d.Count)</td><td>$($d.Wins)</td><td>$($d.WinRate)% $calOk</td></tr>"
            $prevConfWinRate = $d.WinRate
        }
    }
    $html += "</tbody></table>"

    # 置信度校准判断
    $confHigh = if ($confCalibration["高(>70%)"]) { $confCalibration["高(>70%)"].WinRate } else { 0 }
    $confLow = if ($confCalibration["低(<50%)"]) { $confCalibration["低(<50%)"].WinRate } else { 0 }
    $calSpread = $confHigh - $confLow
    if ($calSpread -gt 10) { $calInsight = "置信度校准良好，高置信度显著优于低置信度（差距${calSpread}%）" }
    elseif ($calSpread -gt 0) { $calInsight = "置信度有一定参考价值（差距${calSpread}%），但可以进一步优化" }
    else { $calInsight = "置信度校准异常：高置信度并不比低置信度更准确，需要审视置信度判定规则" }
    $html += "<div class='insight'><div class='title'>校准效果：差距 $calSpread%</div><div class='detail'>$calInsight</div></div>"

    # === 5. 信号有效性 ===
    $html += "<h2>五、信号有效性排名</h2>"
    $html += "<p style='font-size:13px;color:#666;margin-bottom:8px;'>按胜率降序排列，样本数 >= 3</p>"
    $html += "<table><thead><tr><th>信号</th><th>样本数</th><th>胜率%</th><th>评级</th></tr></thead><tbody>"
    foreach ($sr in $signalResults) {
        $bc = if ($sr.Rating -eq "强有效") { "badge-green" } elseif ($sr.Rating -eq "有参考价值") { "badge-blue" } elseif ($sr.Rating -eq "随机水平") { "badge-yellow" } else { "badge-red" }
        $html += "<tr><td style='text-align:left;'>$($sr.Name)</td><td>$($sr.Count)</td><td>$($sr.WinRate)%</td><td><span class='badge $bc'>$($sr.Rating)</span></td></tr>"
    }
    $html += "</tbody></table>"

    # === 6. 趋势健康度 ===
    $html += "<h2>六、趋势健康度区分度</h2>"
    $html += "<table><thead><tr><th>健康度标签</th><th>样本数</th><th>T+1平均收益%</th><th>胜率%</th></tr></thead><tbody>"
    foreach ($hl in @("健康","预警关注","警戒","危险")) {
        if ($healthDiscrimination[$hl]) {
            $h = $healthDiscrimination[$hl]
            $c = if ($h.AvgReturn -gt 0) { "#e74c3c" } else { "#27ae60" }
            $html += "<tr><td>$hl</td><td>$($h.Count)</td><td style='color:$c;'>$($h.AvgReturn)%</td><td>$($h.PositiveRatio)%</td></tr>"
        }
    }
    $html += "</tbody></table>"

    # === 7. 支撑阻力 ===
    $html += "<h2>七、支撑/阻力有效性</h2>"
    $html += "<table><thead><tr><th>类型</th><th>被触及次数</th><th>未被触及次数</th><th>触及率%</th></tr></thead><tbody>"
    $supTouchRate = if ($supportStats.Total -gt 0) { [Math]::Round($supportStats.TotalHit / $supportStats.Total * 100, 1) } else { 0 }
    $resTouchRate = if ($supportStats.ResistanceTotal -gt 0) { [Math]::Round($supportStats.ResistanceHit / $supportStats.ResistanceTotal * 100, 1) } else { 0 }
    $html += "<tr><td>支撑 S1</td><td>$($supportStats.TotalHit)</td><td>$($supportStats.TotalMiss)</td><td>$supTouchRate%</td></tr>"
    $html += "<tr><td>阻力 R1</td><td>$($supportStats.ResistanceHit)</td><td>$($supportStats.ResistanceMiss)</td><td>$resTouchRate%</td></tr>"
    $html += "</tbody></table>"

    # === 8. 各股票 ===
    $html += "<h2>八、各股票回测概览</h2>"
    $html += "<table><thead><tr><th>股票</th><th>样本数</th><th>T+1平均%</th><th>T+3平均%</th><th>T+5平均%</th><th>T+1胜率%</th></tr></thead><tbody>"
    foreach ($sn in ($stockSummary.Keys | Sort-Object)) {
        $s = $stockSummary[$sn]
        $c1 = if ($s.Fwd1Avg -gt 0) { "#e74c3c" } else { "#27ae60" }
        $html += "<tr><td>$sn</td><td>$($s.Count)</td><td style='color:$c1;'>$($s.Fwd1Avg)%</td><td>$($s.Fwd3Avg)%</td><td>$($s.Fwd5Avg)%</td><td>$($s.WinRate1)%</td></tr>"
    }
    $html += "</tbody></table>"

    # === 9. 关键发现 ===
    $html += "<h2>九、关键发现</h2>"

    $findings = @()

    # 评分区分度
    if ($spread -gt 1.5) {
        $findings += "<div class='insight good'><div class='title'>✅ 评分体系有效</div><div class='detail'>高分与低分组收益差距 $([Math]::Round($spread,2))%，综合评分有区分度。权重分配基本合理。</div></div>"
    } elseif ($spread -gt 0.5) {
        $findings += "<div class='insight'><div class='title'>⚡ 评分有一定区分度</div><div class='detail'>差距 $([Math]::Round($spread,2))%，有改进空间。建议检查各维度权重是否最优。</div></div>"
    } else {
        $findings += "<div class='insight bad'><div class='title'>❌ 评分区分度不足</div><div class='detail'>差距仅 $([Math]::Round($spread,2))%，综合评分未能有效区分优劣。建议全面审视六维评分逻辑和权重分配。</div></div>"
    }

    # 关键维度
    $bestDim = $dimResults | Sort-Object R -Descending | Select-Object -First 1
    $worstDim = $dimResults | Sort-Object R | Select-Object -First 1
    if ($bestDim -and $bestDim.R -gt 0.1) {
        $findings += "<div class='insight good'><div class='title'>✅ 最强维度：$($bestDim.Name)（r=$($bestDim.R)）</div><div class='detail'>该维度评分与收益正相关，具有预测价值。当前权重分配可以考虑适度倾斜。</div></div>"
    }
    if ($worstDim -and $worstDim.R -lt -0.05) {
        $findings += "<div class='insight bad'><div class='title'>⚠️ 最弱维度：$($worstDim.Name)（r=$($worstDim.R)）</div><div class='detail'>该维度评分与实际收益负相关或弱相关。建议审视该维度的评分逻辑是否合理。</div></div>"
    }

    # 最佳/最差信号
    $bestSignal = $signalResults | Select-Object -First 1
    $worstSignal = $signalResults | Select-Object -Last 1
    if ($bestSignal -and $bestSignal.WinRate -ge 60) {
        $findings += "<div class='insight good'><div class='title'>✅ 最强信号：$($bestSignal.Name)（胜率$($bestSignal.WinRate)%）</div><div class='detail'>基于 $($bestSignal.Count) 个样本，该信号具有较强预测力，决策时可优先参考。</div></div>"
    }
    if ($worstSignal -and $worstSignal.WinRate -lt 40 -and $worstSignal.Count -ge 5) {
        $findings += "<div class='insight bad'><div class='title'>⚠️ 最弱信号：$($worstSignal.Name)（胜率$($worstSignal.WinRate)%）</div><div class='detail'>该信号表现为反向指标，建议降低其权重或考虑规则反转。</div></div>"
    }

    # 置信度校准
    if ($calSpread -gt 10) {
        $findings += "<div class='insight good'><div class='title'>✅ 置信度校准有效</div><div class='detail'>高置信度组胜率($confHigh%)显著高于低置信度组($confLow%)，置信度判断可信。</div></div>"
    } elseif ($calSpread -le 0) {
        $findings += "<div class='insight bad'><div class='title'>❌ 置信度需校准</div><div class='detail'>高置信度组(${confHigh}%)并不优于低置信度组(${confLow}%)，置信度判定规则需要重新审视</div></div>"
    }

    # 趋势健康度
    $healthGood = if ($healthDiscrimination["健康"]) { $healthDiscrimination["健康"].AvgReturn } else { 0 }
    $healthBad = if ($healthDiscrimination["危险"]) { $healthDiscrimination["危险"].AvgReturn } else { 0 }
    $healthSpread = $healthGood - $healthBad
    if ($healthSpread -gt 0) {
        $findings += "<div class='insight'><div class='title'>⚡ 趋势健康度区分度：$([Math]::Round($healthSpread,2))%</div><div class='detail'>健康股 vs 危险股的收益差距，可作为持仓决策参考。</div></div>"
    }

    $html += ($findings -join "`n")

    # === 10. 局限性 ===
    $html += "<h2>十、回测局限性</h2>"
    $html += "<div class='insight warn'><div class='title'>⚠️ 说明</div><div class='detail'>"
    $html += "<ul style='margin-left:20px;line-height:1.8;'>"
    $html += "<li>基本面（财务数据）、消息面（研报）、资金面（流向/北向/融资）使用的是当前快照，而非历史时刻的真实数据。这些维度的评分在回测期内不变。</li>"
    $html += "<li>板块数据使用当前快照，板块评分在回测期内不变。</li>"
    $html += "<li>K线数据为后复权数据（已包含分红送股调整），与实际交易价格可能有差异。</li>"
    $html += "<li>回测无法模拟交易成本（佣金、印花税、滑点）。</li>"
    $html += "<li>过去30天的表现不代表未来，但能帮助我们识别逻辑短板。</li>"
    $html += "</ul></div></div>"

    $html += "<div class='footnote'>"
    $html += "<p><strong>免责声明</strong>：本报告由铁律量化系统自动生成，仅用于分析逻辑有效性验证，不构成投资建议。</p>"
    $html += "<p>数据来源：腾讯行情、新浪K线、东方财富。生成时间：$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')</p>"
    $html += "</div>"

    $html += "</div></body></html>"
    return $html
}

$reportHtml = New-BacktestReportHtml -Summary $summaryData -Results $resultsSimple -DateRange $summaryData.DateRange -TotalSamples $summaryData.TotalSamples
$htmlPath = Join-Path $outDir "backtest_report.html"
[System.IO.File]::WriteAllText($htmlPath, $reportHtml, [System.Text.Encoding]::UTF8)
Write-Host "[OK] HTML报告: backtest_report.html"

# 尝试转PDF
$pdfPath = Join-Path $outDir "backtest_report.pdf"
if (Test-Path $edgePath) {
    $uri = "file:///$($htmlPath.Replace('\','/'))"
    try {
        Start-Process -FilePath $edgePath -ArgumentList @(
            "--headless","--disable-gpu","--no-sandbox",
            "--print-to-pdf=`"$pdfPath`"",
            "--print-to-pdf-no-header","--no-pdf-header-footer",
            "--print-to-pdf-paper-size=A4", $uri
        ) -Wait -PassThru -NoNewWindow:$false
        Start-Sleep -Seconds 2
        if (Test-Path $pdfPath) { Write-Host "[OK] PDF报告: backtest_report.pdf" }
    } catch { Write-Warning "PDF转换失败" }
}

# ============================================================
# 汇总输出
# ============================================================
Write-Host "`n============================================" -ForegroundColor Cyan
Write-Host "  回测完成"
Write-Host "  回测区间: $($summaryData.DateRange)"
Write-Host "  有效样本: $($summaryData.TotalSamples) 条"
Write-Host "  输出目录: $outDir"
Write-Host "  HTML报告: backtest_report.html"
Write-Host "  原始数据: backtest_data.json"
Write-Host "  分析摘要: backtest_summary.json"
if (Test-Path $pdfPath) { Write-Host "  PDF报告: backtest_report.pdf" }
Write-Host "  API调用: $script:apiCallCount 次"
Write-Host "============================================"
