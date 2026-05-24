# 独立模块 — 纯计算函数，无外部依赖

function Calc-MovingAverage {
    param([array]$Data, [string]$Field = "Close", [int]$Period = 5)
    $values = $Data | ForEach-Object { [double]$_.$Field }
    $result = @()
    for ($i = 0; $i -lt $values.Count; $i++) {
        if ($i -lt $Period - 1) { $result += $null; continue }
        $sum = 0
        for ($j = 0; $j -lt $Period; $j++) { $sum += $values[$i - $j] }
        $result += [math]::Round($sum / $Period, 2)
    }
    return $result
}

function Calc-RSI {
    param([array]$Data, [int]$Period = 14)
    $values = $Data | ForEach-Object { [double]$_.Close }
    $result = @()
    for ($i = 0; $i -lt $values.Count; $i++) {
        if ($i -lt $Period) { $result += $null; continue }
        $gains = 0; $losses = 0
        for ($j = $i - $Period + 1; $j -le $i; $j++) {
            $diff = $values[$j] - $values[$j-1]
            if ($diff -gt 0) { $gains += $diff } else { $losses -= $diff }
        }
        $avgGain = $gains / $Period
        $avgLoss = $losses / $Period
        if ($avgLoss -eq 0) { $result += 100 } else { $result += [math]::Round(100 - (100 / (1 + $avgGain/$avgLoss)), 2) }
    }
    return $result
}

function Calc-MACD {
    param([array]$Data, [int]$Fast = 12, [int]$Slow = 26, [int]$Signal = 9)
    $values = $Data | ForEach-Object { [double]$_.Close }
    # EMA calculation
    function Get-EMA($vals, $n) {
        $ema = @(); $k = 2.0 / ($n + 1)
        for ($i = 0; $i -lt $vals.Count; $i++) {
            if ($i -eq 0) { $ema += $vals[$i] }
            else { $ema += $vals[$i] * $k + $ema[-1] * (1 - $k) }
        }
        return $ema
    }
    $emaFast = Get-EMA $values $Fast
    $emaSlow = Get-EMA $values $Slow
    $dif = @(); for ($i = 0; $i -lt $values.Count; $i++) { $dif += $emaFast[$i] - $emaSlow[$i] }
    $dea = Get-EMA $dif $Signal
    $macd = @(); for ($i = 0; $i -lt $dif.Count; $i++) { $macd += ($dif[$i] - $dea[$i]) * 2 }
    return [PSCustomObject]@{ DIF = $dif; DEA = $dea; MACD = $macd }
}

function Calc-Bollinger {
    param([array]$Data, [int]$Period = 20, [double]$Multiplier = 2.0)
    $ma = Calc-MovingAverage -Data $Data -Field "Close" -Period $Period
    $values = $Data | ForEach-Object { [double]$_.Close }
    $upper = @(); $lower = @()
    for ($i = 0; $i -lt $values.Count; $i++) {
        if ($i -lt $Period - 1) { $upper += $null; $lower += $null; continue }
        $sumSq = 0
        for ($j = 0; $j -lt $Period; $j++) { $sumSq += [math]::Pow($values[$i - $j] - $ma[$i], 2) }
        $stdDev = [math]::Sqrt($sumSq / $Period)
        $upper += [math]::Round($ma[$i] + $Multiplier * $stdDev, 2)
        $lower += [math]::Round($ma[$i] - $Multiplier * $stdDev, 2)
    }
    return [PSCustomObject]@{ MA = $ma; Upper = $upper; Lower = $lower }
}

# ============================================================
# [5b] ADX (14) — 趋势强度指标
# ============================================================
function Calc-ADX {
    param([array]$Data, [int]$Period = 14)
    $highs = $Data | ForEach-Object { [double]$_.High }
    $lows  = $Data | ForEach-Object { [double]$_.Low }
    $closes = $Data | ForEach-Object { [double]$_.Close }
    $n = $highs.Count

    $tr = @(); $plusDM = @(); $minusDM = @()
    for ($i = 0; $i -lt $n; $i++) {
        if ($i -eq 0) { $tr += $null; $plusDM += $null; $minusDM += $null; continue }
        $h = $highs[$i]; $l = $lows[$i]; $pc = $closes[$i-1]
        $tr += [Math]::Max([Math]::Max($h - $l, [Math]::Abs($h - $pc)), [Math]::Abs($l - $pc))
        $upMove = $h - $highs[$i-1]; $downMove = $lows[$i-1] - $l
        $plusDM  += if ($upMove -gt $downMove -and $upMove -gt 0) { $upMove } else { 0 }
        $minusDM += if ($downMove -gt $upMove -and $downMove -gt 0) { $downMove } else { 0 }
    }

    # Wilder's smoothing
    $atr = @(); $smoothedPlusDM = @(); $smoothedMinusDM = @()
    for ($i = 0; $i -lt $n; $i++) {
        if ($i -lt $Period) { $atr += $null; $smoothedPlusDM += $null; $smoothedMinusDM += $null; continue }
        if ($i -eq $Period) {
            $atr += ($tr[1..$Period] | Measure-Object -Average).Average
            $smoothedPlusDM  += ($plusDM[1..$Period] | Measure-Object -Average).Average
            $smoothedMinusDM += ($minusDM[1..$Period] | Measure-Object -Average).Average
        } else {
            $atr += ($atr[-1] * ($Period - 1) + $tr[$i]) / $Period
            $smoothedPlusDM  += ($smoothedPlusDM[-1] * ($Period - 1) + $plusDM[$i]) / $Period
            $smoothedMinusDM += ($smoothedMinusDM[-1] * ($Period - 1) + $minusDM[$i]) / $Period
        }
    }

    $plusDI = @(); $minusDI = @(); $adx = @()
    for ($i = 0; $i -lt $n; $i++) {
        if ($i -lt $Period * 2 - 1) { $plusDI += $null; $minusDI += $null; $adx += $null; continue }
        $a = $atr[$i]
        $pdi = if ($a -gt 0) { [math]::Round($smoothedPlusDM[$i] / $a * 100, 2) } else { 0 }
        $mdi = if ($a -gt 0) { [math]::Round($smoothedMinusDM[$i] / $a * 100, 2) } else { 0 }
        $plusDI += $pdi; $minusDI += $mdi

        if ($i -eq $Period * 2 - 1) {
            # First ADX value: average of first Period DX values
            $dxSum = 0; $dxCount = 0
            for ($j = $Period; $j -le $i; $j++) {
                $denom = $plusDI[$j] + $minusDI[$j]
                if ($denom -gt 0) { $dxSum += [Math]::Abs($plusDI[$j] - $minusDI[$j]) / $denom * 100; $dxCount++ }
            }
            $adx += if ($dxCount -gt 0) { [math]::Round($dxSum / $dxCount, 2) } else { $null }
        } else {
            $denom = $pdi + $mdi
            $dx = if ($denom -gt 0) { [Math]::Abs($pdi - $mdi) / $denom * 100 } else { 0 }
            $adx += if ($adx[-1] -ne $null) { [math]::Round(($adx[-1] * ($Period - 1) + $dx) / $Period, 2) } else { $null }
        }
    }
    return [PSCustomObject]@{ ADX = $adx; PlusDI = $plusDI; MinusDI = $minusDI }
}

# ============================================================
# [5c] OBV — 能量潮（累积量价指标）
# ============================================================
function Calc-OBV {
    param([array]$Data)
    $obv = @(); $cum = 0
    for ($i = 0; $i -lt $Data.Count; $i++) {
        if ($i -eq 0) { $obv += $cum; continue }
        $c = [double]$Data[$i].Close; $pc = [double]$Data[$i-1].Close; $v = [long]$Data[$i].Volume
        if ($c -gt $pc) { $cum += $v }
        elseif ($c -lt $pc) { $cum -= $v }
        $obv += $cum
    }
    return $obv
}

# ============================================================
# [5d] ATR (14) — 平均真实波幅
# ============================================================
function Calc-ATR {
    param([array]$Data, [int]$Period = 14)
    $trs = @()
    for ($i = 1; $i -lt $Data.Count; $i++) {
        $h = [double]$Data[$i].High; $l = [double]$Data[$i].Low; $pc = [double]$Data[$i-1].Close
        $trs += [Math]::Max([Math]::Max($h - $l, [Math]::Abs($h - $pc)), [Math]::Abs($l - $pc))
    }
    $atr = @()
    for ($i = 0; $i -lt $trs.Count; $i++) {
        if ($i -lt $Period - 1) { $atr += $null; continue }
        if ($i -eq $Period - 1) { $atr += ($trs[0..$i] | Measure-Object -Average).Average }
        else { $atr += ($atr[-1] * ($Period - 1) + $trs[$i]) / $Period }
    }
    return $atr
}

# ============================================================
# [7] 东方财富板块行业数据（TOP N）
# ============================================================