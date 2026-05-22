# 每日荐股临时回溯 - 数据采集
# 基于30日历史K线，回测技术信号有效性

$rootDir = "C:\Users\34269\Documents\Claude\股票分析"
Import-Module (Join-Path $rootDir "每日荐股\scripts\stock_data_fetcher.psm1") -Force -WarningAction SilentlyContinue 2>$null

# 从data_final.json读取42只股票
$jsonPath = Join-Path $rootDir "代码文件\数据\data_final.json"
$stocks = Get-Content $jsonPath -Encoding UTF8 | ConvertFrom-Json

Write-Host "===== 每日荐股技术信号回溯 - 数据采集 ====="
Write-Host "股票数量: $($stocks.Count)"
$startStr = Get-Date -Format "HH:mm:ss"
Write-Host "开始时间: $startStr"
Write-Host ""

$allResults = @()

foreach ($s in $stocks) {
    $code = $s.Code
    $name = $s.Name
    Write-Host "[$code $name] 采集K线数据..."

    $klines = Get-StockKLine -Code $code -Scale 240 -Count 35
    if (($klines -eq $null) -or ($klines.Count -lt 10)) {
        Write-Host "  -> K线不足,跳过"
        continue
    }

    $closes = $klines | ForEach-Object { [double]$_.Close }
    $volumes = $klines | ForEach-Object { [double]$_.Volume }

    $ma5  = Calc-MovingAverage -Data $closes -Period 5
    $ma10 = Calc-MovingAverage -Data $closes -Period 10
    $ma20 = Calc-MovingAverage -Data $closes -Period 20
    $rsi14 = Calc-RSI -Data $closes -Period 14
    $macd = Calc-MACD -Data $closes
    $boll = Calc-Bollinger -Data $closes -Period 20

    $startIdx = 20  # 从第20根开始，确保所有指标有值
    $maxIdx = $klines.Count - 1

    for ($i = $startIdx; $i -le $maxIdx; $i++) {
        $day = $klines[$i]
        $close = [double]$day.Close
        $open = [double]$day.Open
        $high = [double]$day.High
        $low = [double]$day.Low
        $vol = [double]$day.Volume
        $prevClose = [double]$klines[$i-1].Close
        $todayChg = [Math]::Round(($close - $prevClose) / $prevClose * 100, 2)

        # T+1/T+3/T+5 收益
        $nextDayChg = $null
        if ($i + 1 -le $maxIdx) {
            $nextClose = [double]$klines[$i+1].Close
            $nextDayChg = [Math]::Round(($nextClose - $close) / $close * 100, 2)
        }
        $day3Chg = $null
        if ($i + 3 -le $maxIdx) {
            $c3 = [double]$klines[$i+3].Close
            $day3Chg = [Math]::Round(($c3 - $close) / $close * 100, 2)
        }
        $day5Chg = $null
        if ($i + 5 -le $maxIdx) {
            $c5 = [double]$klines[$i+5].Close
            $day5Chg = [Math]::Round(($c5 - $close) / $close * 100, 2)
        }

        # === 指标值提取 ===
        $ma5v = 0; $ma10v = 0; $ma20v = 0
        if ($null -ne $ma5[$i])  { $ma5v = [double]$ma5[$i] }
        if ($null -ne $ma10[$i]) { $ma10v = [double]$ma10[$i] }
        if ($null -ne $ma20[$i]) { $ma20v = [double]$ma20[$i] }
        $rsi = 50
        if ($null -ne $rsi14[$i]) { $rsi = [double]$rsi14[$i] }
        $dif = 0; $dea = 0
        if ($null -ne $macd.DIF[$i]) { $dif = [double]$macd.DIF[$i] }
        if ($null -ne $macd.DEA[$i]) { $dea = [double]$macd.DEA[$i] }
        $bu = 0; $bm = 0; $bd = 0
        if ($null -ne $boll.Upper[$i]) { $bu = [double]$boll.Upper[$i] }
        if ($null -ne $boll.MA[$i])    { $bm = [double]$boll.MA[$i] }
        if ($null -ne $boll.Lower[$i]) { $bd = [double]$boll.Lower[$i] }

        # === 信号判定 ===
        # 1. 均线多头
        $sMA_Bull = 0
        if (($ma5v -gt $ma10v) -and ($ma10v -gt $ma20v)) { $sMA_Bull = 1 }

        # 2. 均线空头
        $sMA_Bear = 0
        if (($ma5v -lt $ma10v) -and ($ma10v -lt $ma20v)) { $sMA_Bear = 1 }

        # 3. 均线收敛
        $sMA_Converge = 0
        if (($ma5v -gt 0) -and ($ma10v -gt 0) -and ($ma20v -gt 0)) {
            $maxMa = $ma5v
            if ($ma10v -gt $maxMa) { $maxMa = $ma10v }
            if ($ma20v -gt $maxMa) { $maxMa = $ma20v }
            $minMa = $ma5v
            if ($ma10v -lt $minMa) { $minMa = $ma10v }
            if ($ma20v -lt $minMa) { $minMa = $ma20v }
            $spread = ($maxMa - $minMa) / $minMa * 100
            if ($spread -lt 1.0) { $sMA_Converge = 1 }
        }

        # 4. MACD
        $sMACD_Golden = 0
        if ($dif -gt $dea) { $sMACD_Golden = 1 }
        $sMACD_Dead = 0
        if ($dif -lt $dea) { $sMACD_Dead = 1 }

        # 5. RSI
        $sRSI_40_55 = 0
        if (($rsi -ge 40) -and ($rsi -le 55)) { $sRSI_40_55 = 1 }
        $sRSI_LT30 = 0
        if ($rsi -lt 30) { $sRSI_LT30 = 1 }
        $sRSI_GT70 = 0
        if ($rsi -gt 70) { $sRSI_GT70 = 1 }

        # 6. 布林带
        $sBoll_Upper = 0
        if (($bu -gt 0) -and ($close -ge $bu)) { $sBoll_Upper = 1 }
        $sBoll_Lower = 0
        if (($bd -gt 0) -and ($close -le $bd)) { $sBoll_Lower = 1 }
        $sBoll_MidAbove = 0
        if (($bm -gt 0) -and ($close -ge $bm)) { $sBoll_MidAbove = 1 }

        # 7. 量价
        $sVol_Shrink = 0
        $sVol_Expand = 0
        $sVol_Gentle = 0
        if ($i -ge 5) {
            $avgVol5 = 0
            for ($v = 1; $v -le 5; $v++) { $avgVol5 = $avgVol5 + $volumes[$i-$v] }
            $avgVol5 = $avgVol5 / 5
            if ($avgVol5 -gt 0) {
                $volRatio = $vol / $avgVol5
                if (($volRatio -lt 0.7) -and ($todayChg -lt 0)) { $sVol_Shrink = 1 }
                if (($volRatio -gt 1.5) -and ($todayChg -gt 0)) { $sVol_Expand = 1 }
                if (($volRatio -ge 0.8) -and ($volRatio -le 1.2) -and ($todayChg -gt 0) -and ($todayChg -lt 2)) { $sVol_Gentle = 1 }
            }
        }

        # 8. 底部抬高
        $sBottom_Rising = 0
        if ($i -ge 5) {
            $rising = 1
            for ($j = ($i-4); $j -le $i; $j++) {
                if ($j -gt ($i-4)) {
                    $prevLow = [double]$klines[$j-1].Low
                    $currLow = [double]$klines[$j].Low
                    if ($currLow -le $prevLow) { $rising = 0; break }
                }
            }
            if ($rising -eq 1) { $sBottom_Rising = 1 }
        }

        $result = New-Object PSObject -Property @{
            Code=$code; Name=$name; DateIndex=$i
            Price=$close; ChgPct=$todayChg
            NextDayChg=$nextDayChg; Day3Chg=$day3Chg; Day5Chg=$day5Chg
            MA5=$ma5v; MA10=$ma10v; MA20=$ma20v
            RSI14=$rsi; MACD_DIF=$dif; MACD_DEA=$dea
            S_MA_Bull=$sMA_Bull; S_MA_Bear=$sMA_Bear; S_MA_Converge=$sMA_Converge
            S_MACD_Golden=$sMACD_Golden; S_MACD_Dead=$sMACD_Dead
            S_RSI_40_55=$sRSI_40_55; S_RSI_LT30=$sRSI_LT30; S_RSI_GT70=$sRSI_GT70
            S_Boll_Upper=$sBoll_Upper; S_Boll_Lower=$sBoll_Lower; S_Boll_MidAbove=$sBoll_MidAbove
            S_Vol_Shrink=$sVol_Shrink; S_Vol_Expand=$sVol_Expand; S_Vol_Gentle=$sVol_Gentle
            S_Bottom_Rising=$sBottom_Rising
        }
        $allResults += $result
    }
    Write-Host "  -> $($klines.Count)根K线, $($klines.Count - 19)个样本"
}

$outPath = Join-Path $rootDir "临时回溯\backtest_signals.json"
$allResults | ConvertTo-Json -Depth 3 | Out-File $outPath -Encoding UTF8

Write-Host ""
Write-Host "===== 采集完成 ====="
Write-Host "总样本: $($allResults.Count)"
Write-Host "输出: $outPath"
$nowStr = Get-Date -Format "HH:mm:ss"
Write-Host "时间: $nowStr"
