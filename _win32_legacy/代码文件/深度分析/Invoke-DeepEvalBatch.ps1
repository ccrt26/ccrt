<#
.SYNOPSIS
  Invoke-DeepEvalBatch — 深度分析后评估批量编排器 (L1)
.DESCRIPTION
  扫描全部重点股票的深度分析报告，逐只解析+计算，跨股票聚合后生成1份方法论级别综合PDF。
  白皮书 §1.1: 评估对象=深度分析v1.2方法论框架，评估数据=全部重点股票的深度分析报告。
.PARAMETER TargetDate
  目标日期 (yyyyMMdd)，默认今天。用于定位对应日期的深度分析报告。
.PARAMETER Mode
  报告模式: Quick(快报)/Monthly(月度)/Quarterly(季度)
.PARAMETER KeepHtml
  保留中间HTML文件
#>
param(
    [string]$TargetDate = "",
    [ValidateSet("Quick","Monthly","Quarterly")]
    [string]$Mode = "Quick",
    [switch]$KeepHtml = $false
)

$ErrorActionPreference = "Continue"
. "$PSScriptRoot/../lib/init_encoding.ps1"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = Split-Path -Parent (Split-Path -Parent $scriptDir)

if (-not $TargetDate) {
    $TargetDate = (Get-Date).ToString("yyyyMMdd")
}
$dateLabel = $TargetDate

Write-Host "=============================================="
Write-Host "  Deep Eval Batch Pipeline v2.0"
Write-Host "  Mode: $Mode"
Write-Host "  Date: $dateLabel"
Write-Host "=============================================="
Write-Host ""

# ============================================================
# Stage 0: Scan deep analysis reports
# ============================================================
Write-Host "[0/4] Scanning deep analysis reports..."
$reportRoot = Join-Path $rootDir "重点股票\深度分析\深度分析报告"
$reports = @()

if (Test-Path $reportRoot) {
    $dirs = Get-ChildItem $reportRoot -Directory
    foreach ($dir in $dirs) {
        # Match {name}({code}) directory
        if ($dir.Name -match '^(.+)\((\d{6})\)$') {
            $stockName = $matches[1]
            $stockCode = $matches[2]
            $mdPattern = Join-Path $dir.FullName "${stockName}(${stockCode})深度分析报告_${dateLabel}.md"
            if (Test-Path $mdPattern) {
                $reports += @{ Code = $stockCode; Name = $stockName; Path = $mdPattern; Dir = $dir.FullName }
                Write-Host "  [FOUND] $stockName($stockCode)"
            } else {
                # Try any MD in the directory as fallback
                $anyMd = Get-ChildItem $dir.FullName -Filter "*.md" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
                if ($anyMd) {
                    $reports += @{ Code = $stockCode; Name = $stockName; Path = $anyMd.FullName; Dir = $dir.FullName }
                    Write-Host "  [FALLBACK] $stockName($stockCode) -> $($anyMd.Name)"
                } else {
                    Write-Host "  [SKIP] $stockName($stockCode): no MD report found"
                }
            }
        }
    }
}

if ($reports.Count -eq 0) {
    Write-Error "No deep analysis reports found in $reportRoot"
    exit 1
}
Write-Host "  Total: $($reports.Count) stocks"

# ============================================================
# Stage 1: Parse each report
# ============================================================
Write-Host ""
Write-Host "[1/4] Parsing reports..."
$parserScript = Join-Path $scriptDir "Invoke-DeepAnalysisParser.ps1"
$evalDir = Join-Path $rootDir "重点股票\深度分析\后评估报告"
if (-not (Test-Path $evalDir)) {
    New-Item -ItemType Directory -Path $evalDir -Force | Out-Null
}

$evalDataPaths = @()
foreach ($r in $reports) {
    $outPath = Join-Path $evalDir "评估数据_$($r.Code)_${dateLabel}.json"
    Write-Host "  Parsing $($r.Name)($($r.Code))..."
    $result = & $parserScript -ReportPath $r.Path -OutputPath $outPath 2>&1
    if ($LASTEXITCODE -eq 0 -and (Test-Path $outPath)) {
        $evalDataPaths += $outPath
        Write-Host "    [OK] $outPath"
    } else {
        Write-Warning "    [FAIL] $($r.Name): $result"
    }
}

if ($evalDataPaths.Count -eq 0) {
    Write-Error "All parses failed"
    exit 1
}
Write-Host "  Parsed: $($evalDataPaths.Count)/$($reports.Count)"

# ============================================================
# Stage 2: Compute metrics for each stock
# ============================================================
Write-Host ""
Write-Host "[2/4] Computing metrics..."
$metricsScript = Join-Path $scriptDir "Measure-DeepEvalMetrics.ps1"
$evalResultPaths = @()

foreach ($dataPath in $evalDataPaths) {
    $outPath = $dataPath -replace '评估数据_', '评估结果_'
    Write-Host "  Metrics: $([System.IO.Path]::GetFileName($dataPath))"
    $result = & $metricsScript -EvalDataPath $dataPath -HistoricalDir $evalDir -OutputPath $outPath 2>&1
    if ($LASTEXITCODE -eq 0 -and (Test-Path $outPath)) {
        $evalResultPaths += $outPath
        Write-Host "    [OK]"
    } else {
        Write-Warning "    [FAIL]: $result"
    }
}
Write-Host "  Computed: $($evalResultPaths.Count)/$($evalDataPaths.Count)"

# ============================================================
# Stage 3: Cross-stock aggregation
# ============================================================
Write-Host ""
Write-Host "[3/4] Aggregating cross-stock results..."
$stocksSummary = @()
$allAScores = @(); $allBScores = @(); $allTotal = @()
$dimensionData = @{}
$dimKeys = @("b1_catalyst_tracking","b2_market_phase","b3_industry_verification",
    "b4_anti_hallucination","b5_data_source_stability","b6_scenario_calibration",
    "b7_red_flags_predictive","b8_stop_loss_precision","b9_valuation_accuracy",
    "b10_wyckoff_accuracy","b11_company_type_accuracy")
$dimLabels = @("B1催化剂","B2市场阶段","B3行业判断","B4幻觉防范","B5数据源",
    "B6情景概率","B7五红旗","B8止损位","B9估值预测","B10Wyckoff","B11类型判定")

foreach ($dim in $dimKeys) { $dimensionData[$dim] = @() }

foreach ($resultPath in $evalResultPaths) {
    $result = Get-Content $resultPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $m = $result.meta
    $aScore = $result.a_layer.total_score
    $bScore = $result.b_layer.total_score
    $total = $result.total_score

    $allAScores += $aScore
    $allBScores += $bScore
    $allTotal += $total

    $stockEntry = @{
        code = $m.stock_code
        name = $m.stock_name
        a_score = $aScore
        b_score = $bScore
        total_score = $total
        rating = $result.rating
    }
    $stocksSummary += $stockEntry

    # Collect per-dimension data
    foreach ($dim in $dimKeys) {
        $d = $result.b_layer.$dim
        if ($d -and $d.max -gt 0) {
            $dimensionData[$dim] += [PSCustomObject]@{ code=$m.stock_code; name=$m.stock_name; score=$d.score; max=$d.max; pct=[Math]::Round($d.score/$d.max*100) }
        }
    }
}

# Compute cross-stock statistics
$n = $allTotal.Count
function Stat($arr) {
    $mean = [Math]::Round(($arr | Measure-Object -Average).Average, 1)
    $sorted = $arr | Sort-Object
    $median = if ($n % 2 -eq 1) { $sorted[$n/2] } else { [Math]::Round(($sorted[$n/2-1] + $sorted[$n/2]) / 2, 1) }
    if ($n -gt 1) {
        $variance = ($arr | ForEach-Object { [Math]::Pow($_ - $mean, 2) } | Measure-Object -Sum).Sum / ($n - 1)
        $std = [Math]::Round([Math]::Sqrt($variance), 1)
    } else { $std = 0 }
    return @{ mean=$mean; median=$median; std=$std; min=($arr | Measure-Object -Minimum).Minimum; max=($arr | Measure-Object -Maximum).Maximum }
}

$dimMatrix = @()
for ($i = 0; $i -lt $dimKeys.Count; $i++) {
    $d = $dimensionData[$dimKeys[$i]]
    if ($d.Count -gt 0) {
        $pcts = @($d | ForEach-Object { $_.pct })
        $st = Stat $pcts
        $best = $d | Sort-Object pct -Descending | Select-Object -First 1
        $worst = $d | Sort-Object pct | Select-Object -First 1
        $dimMatrix += @{
            index = $i+1
            label = $dimLabels[$i]
            mean = $st.mean
            std = $st.std
            min = $st.min
            max = $st.max
            best_stock = "$($best.name)($($best.code)) $($best.pct)%"
            worst_stock = "$($worst.name)($($worst.code)) $($worst.pct)%"
        }
    }
}

$totalStat = Stat $allTotal
$aStat = Stat $allAScores
$bStat = Stat $allBScores

# Systematic bias detection
$directionCount = @{ "正向"=0; "中性"=0; "反向"=0 }
foreach ($resultPath in $evalResultPaths) {
    $result = Get-Content $resultPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $dir = $result.direction_calibration.direction
    if ($dir) { $directionCount[$dir]++ }
}

$effectiveCount = ($stocksSummary | Where-Object { $_.rating -match "A|B" }).Count
$weakCount = ($stocksSummary | Where-Object { $_.rating -match "D|E" }).Count

$aggregate = @{
    meta = @{
        eval_date = $dateLabel
        stock_count = $reports.Count
        parsed_count = $evalDataPaths.Count
        computed_count = $evalResultPaths.Count
        methodology_version = "v1.2"
        mode = $Mode
    }
    stocks_summary = $stocksSummary
    cross_stock = @{
        composite = @{ mean=$totalStat.mean; median=$totalStat.median; std=$totalStat.std; min=$totalStat.min; max=$totalStat.max }
        a_layer = @{ mean=$aStat.mean; std=$aStat.std }
        b_layer = @{ mean=$bStat.mean; std=$bStat.std }
        effective_count = $effectiveCount
        weak_count = $weakCount
        dimension_matrix = $dimMatrix
    }
    direction_distribution = $directionCount
    suggestions = @()
}

# Generate suggestions based on data
if ($dimMatrix.Count -gt 0) {
    $weakestDim = $dimMatrix | Sort-Object mean | Select-Object -First 1
    if ($weakestDim.mean -lt 40) {
        $aggregate.suggestions += @{
            priority = "P0"
            issue = "$($weakestDim.label)跨股票一致偏弱(均值$($weakestDim.mean)%)"
            suggestion = "方法论$($weakestDim.label)维度需重点审查，建议下期深度分析增加该维度验证步骤"
        }
    }
    $strongestDim = $dimMatrix | Sort-Object mean -Descending | Select-Object -First 1
    if ($strongestDim.mean -gt 80) {
        $aggregate.suggestions += @{
            priority = "P2"
            issue = "$($strongestDim.label)表现优异(均值$($strongestDim.mean)%)"
            suggestion = "该维度方法可固化，作为模板推广到其他分析场景"
        }
    }
}
if ($totalStat.std -gt 15) {
    $aggregate.suggestions += @{
        priority = "P1"
        issue = "股票间评分差异大(std=$($totalStat.std))"
        suggestion = "检查是否存在行业/市值因子导致的系统性评估偏差"
    }
}

$aggregatePath = Join-Path $evalDir "聚合结果_${dateLabel}.json"
$aggregateJson = $aggregate | ConvertTo-Json -Depth 5 -Compress
[System.IO.File]::WriteAllText($aggregatePath, $aggregateJson, [System.Text.Encoding]::UTF8)
Write-Host "  Aggregate: $aggregatePath"
Write-Host "  Composite: mean=$($totalStat.mean) std=$($totalStat.std)"
Write-Host "  Effective: $effectiveCount / Weak: $weakCount"
Write-Host "  Direction: 正向$($directionCount['正向']) 中性$($directionCount['中性']) 反向$($directionCount['反向'])"

# ============================================================
# Stage 4: Generate methodology-level PDF
# ============================================================
Write-Host ""
Write-Host "[4/4] Generating methodology-level PDF..."
$reportScript = Join-Path $scriptDir "New-DeepEvalReport.ps1"
$pdfOutput = & $reportScript -Batch -BatchAggregatePath $aggregatePath -Mode $Mode -KeepHtml:$KeepHtml 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Warning "PDF generation warning: $pdfOutput"
}
Write-Host "  PDF: $pdfOutput"

# ============================================================
# Summary
# ============================================================
Write-Host ""
Write-Host "=============================================="
Write-Host "  Batch Post-Evaluation Complete"
Write-Host "=============================================="
Write-Host "  Stocks: $($reports.Count) found, $($evalResultPaths.Count) evaluated"
Write-Host "  Composite Score: mean=$($totalStat.mean) (range $($totalStat.min)-$($totalStat.max))"
Write-Host "  PDF: $pdfOutput"
Write-Host "=============================================="

# Auto-commit
$gitAuto = Join-Path $rootDir "代码文件\tools\git_autocommit.ps1"
if (Test-Path $gitAuto) {
    $null = & $gitAuto -Module "post_eval" -Paths @("重点股票\深度分析\后评估报告") -Message "深度分析后评估批量产出 [$Mode]"
}

exit 0
