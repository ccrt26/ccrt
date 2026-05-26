# 数学工具函数 — 全项目共享
# 抽取自 run_keystock_evaluation.ps1，供日报后评估和深度分析后评估共用

function Get-SpearmanR {
    param([double[]]$X, [double[]]$Y)
    $n = $X.Length
    if ($n -lt 3) { return 0, 0 }
    function Get-Ranks([double[]]$arr) {
        $n = $arr.Count
        $indexed = @(for ($i=0; $i -lt $n; $i++) { [PSCustomObject]@{Idx=$i; Val=$arr[$i]} })
        $sorted = $indexed | Sort-Object Val
        $ranks = New-Object double[] $n
        $j = 0
        while ($j -lt $n) {
            $k = $j
            while ($k+1 -lt $n -and [Math]::Abs($sorted[$k+1].Val - $sorted[$j].Val) -lt 1e-10) { $k++ }
            $avgRank = ($j + $k) / 2.0 + 1
            for ($t = $j; $t -le $k; $t++) { $ranks[$sorted[$t].Idx] = $avgRank }
            $j = $k + 1
        }
        return $ranks
    }
    $rankX = Get-Ranks $X
    $rankY = Get-Ranks $Y
    $meanRx = ($rankX | Measure-Object -Average).Average
    $meanRy = ($rankY | Measure-Object -Average).Average
    $cov = 0.0; $varX = 0.0; $varY = 0.0
    for ($i = 0; $i -lt $n; $i++) {
        $dx = $rankX[$i] - $meanRx
        $dy = $rankY[$i] - $meanRy
        $cov += $dx * $dy
        $varX += $dx * $dx
        $varY += $dy * $dy
    }
    $denom = [Math]::Sqrt($varX * $varY)
    if ($denom -eq 0) { return 0, $n }
    $rho = $cov / $denom
    return [Math]::Round($rho, 4), $n
}

function Get-ICIR {
    param([double[]]$ICValues)
    if ($ICValues.Count -lt 2) { return 0 }
    $meanIC = ($ICValues | Measure-Object -Average).Average
    $stdIC = [Math]::Sqrt((($ICValues | ForEach-Object { [Math]::Pow($_ - $meanIC, 2) }) | Measure-Object -Average).Average)
    if ($stdIC -eq 0) { return 0 }
    return [Math]::Round($meanIC / $stdIC, 3)
}

function Get-BrierScore {
    param([double[]]$PredictedProbs, [double[]]$ActualOutcomes)
    $n = $PredictedProbs.Count
    if ($n -eq 0) { return 1.0 }
    $sum = 0.0
    for ($i = 0; $i -lt $n; $i++) {
        $sum += [Math]::Pow($PredictedProbs[$i] - $ActualOutcomes[$i], 2)
    }
    return [Math]::Round($sum / $n, 4)
}

function Get-MAPE {
    param([double]$Predicted, [double]$Actual)
    if ($Actual -eq 0) { return 999.9 }
    return [Math]::Round([Math]::Abs($Predicted - $Actual) / [Math]::Abs($Actual) * 100, 1)
}
