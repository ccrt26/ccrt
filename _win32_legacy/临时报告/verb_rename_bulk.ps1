# 动词合规化Phase2 批量重命名脚本
# 红结执行 | 2026-05-27
$ErrorActionPreference = "Stop"
$BASE = "c:/Users/34269/Documents/Claude/股票分析/代码文件/每日荐股/scripts"

# ============================================================
# Step 1: 处理定义文件 — 只改调用点，不碰旧函数定义（先加新函数再转包装器）
# ============================================================

# --- legacy.ps1 ---
Write-Host "=== Processing legacy.ps1 ===" -ForegroundColor Cyan
$legacy1 = "$BASE/stock_data_fetcher_legacy.ps1"
$c = [System.IO.File]::ReadAllText($legacy1, [System.Text.Encoding]::UTF8)

# 1a. 在 Save-DataCache 之前插入 Export-DataCache 完整实现
$exportFunc = @'
function Export-DataCache {
    param([string]$Key, $Data)
    if (-not $Data) { return }
    $path = Join-Path $script:CacheDir "$Key.json"
    try {
        $toSave = @{ Timestamp = (Get-Date).ToString("o"); Data = $Data }
        $toSave | ConvertTo-Json -Depth 5 -Compress | Set-Content $path -Encoding UTF8
    } catch { Write-Debug "Cache save failed for $Key : $_" }
}

'@
$c = $c -replace 'function Save-DataCache \{', ($exportFunc + 'function Save-DataCache {')

# 1b. 在 Load-DataCache 之前插入 Import-DataCache 完整实现
$importFunc = @'
function Import-DataCache {
    param([string]$Key, [int]$TTLHours = 24)
    $path = Join-Path $script:CacheDir "$Key.json"
    if (-not (Test-Path $path)) { return $null }
    try {
        $cached = Get-Content $path -Encoding UTF8 -Raw | ConvertFrom-Json
        $age = [datetime]::Now - [datetime]::Parse($cached.Timestamp)
        if ($age.TotalHours -gt $TTLHours) {
            Write-Debug "Cache expired for $Key (age: $($age.TotalHours.ToString('0.0'))h)"
            return $null
        }
        return $cached.Data
    } catch { return $null }
}

'@
$c = $c -replace 'function Load-DataCache \{', ($importFunc + 'function Load-DataCache {')

# 1c. Save-DataCache body -> wrapper
$saveWrapper = @'
function Save-DataCache {
    param([string]$Key, $Data)
    Export-DataCache -Key $Key -Data $Data
}
'@
$c = $c -replace '(?s)function Save-DataCache \{\s*param\(\[string\]\$Key, \$Data\).*?^}', ($saveWrapper + "`n")

# Actually need a different approach. Let me do targeted replacements.
# Save-DataCache: replace the body between { and the next ^function
$c = $c -replace '(?s)(function Save-DataCache \{\s*param\(\[string\]\$Key, \$Data\)\s*if \(-not \$Data\) \{ return \}.*?catch \{ Write-Debug "Cache save failed for \$Key : \$_" \}\s*\})', $saveWrapper

# 1d. Load-DataCache body -> wrapper
$loadWrapper = @'
function Load-DataCache {
    param([string]$Key, [int]$TTLHours = 24)
    Import-DataCache -Key $Key -TTLHours $TTLHours
}
'@
$c = $c -replace '(?s)(function Load-DataCache \{\s*param\(\[string\]\$Key, \[int\]\$TTLHours = 24\).*?return \$cached\.Data\s*\} catch \{ return \$null \}\s*\})', $loadWrapper

# 1e. 为 Calc-* 添加 Measure-* 定义 (在function Calc-MovingAverage之前)
$measureFuncs = @'
function Measure-MovingAverage {
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

function Measure-RSI {
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

function Measure-MACD {
    param([array]$Data, [int]$Fast = 12, [int]$Slow = 26, [int]$Signal = 9)
    $values = $Data | ForEach-Object { [double]$_.Close }
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

function Measure-Bollinger {
    param([array]$Data, [int]$Period = 20, [double]$Multiplier = 2.0)
    $ma = Measure-MovingAverage -Data $Data -Field "Close" -Period $Period
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

'@
$c = $c -replace 'function Calc-MovingAverage \{', ($measureFuncs + 'function Calc-MovingAverage {')

# 1f. 将 Calc-* 函数体替换为包装器
$calcWrappers = @{
    'Calc-MovingAverage' = 'function Calc-MovingAverage { param([array]$Data, [string]$Field = "Close", [int]$Period = 5) Measure-MovingAverage -Data $Data -Field $Field -Period $Period }'
    'Calc-RSI' = 'function Calc-RSI { param([array]$Data, [int]$Period = 14) Measure-RSI -Data $Data -Period $Period }'
    'Calc-MACD' = 'function Calc-MACD { param([array]$Data, [int]$Fast = 12, [int]$Slow = 26, [int]$Signal = 9) Measure-MACD -Data $Data -Fast $Fast -Slow $Slow -Signal $Signal }'
    'Calc-Bollinger' = 'function Calc-Bollinger { param([array]$Data, [int]$Period = 20, [double]$Multiplier = 2.0) Measure-Bollinger -Data $Data -Period $Period -Multiplier $Multiplier }'
}

foreach ($oldName in $calcWrappers.Keys) {
    $wrapper = $calcWrappers[$oldName]
    # Match from "function Calc-X {" to the closing "}" before next function or end
    $pattern = "(?s)function $oldName \{.*?^}"
    if ($c -match $pattern) {
        Write-Host "  Wrapping $oldName" -ForegroundColor Gray
        $c = $c -replace $pattern, $wrapper
    }
}

# 1g. 替换内部调用 (但不碰函数定义行——它们现在已经是包装器了)
$c = $c -replace '([^-])Save-DataCache -Key', '$1Export-DataCache -Key'
$c = $c -replace '([^-])Load-DataCache -Key', '$1Import-DataCache -Key'

[System.IO.File]::WriteAllText($legacy1, $c, (New-Object System.Text.UTF8Encoding $false))
Write-Host "  legacy.ps1 DONE" -ForegroundColor Green

Write-Host "`n=== All bulk operations complete ===" -ForegroundColor Green
Write-Host "legacy.ps1 processed. Remaining files to handle manually: legacy.psm1, run_daily_eval.ps1, caller modules"
