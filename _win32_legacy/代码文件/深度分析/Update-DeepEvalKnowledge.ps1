<#
.SYNOPSIS
  Update-DeepEvalKnowledge — 深度分析后评估知识库更新 (L0)
.DESCRIPTION
  将评估结果写入持久化知识库：信号跟踪CSV、改进日志、优化建议JSON、催化剂映射、元评估。
#>
param(
    [Parameter(Mandatory=$true)]
    [string]$EvalResultPath,      # 评估结果JSON路径
    [string]$KnowledgeDir = ""    # 知识库根目录
)

. "$PSScriptRoot/../lib/init_encoding.ps1"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = Split-Path -Parent (Split-Path -Parent $scriptDir)

if (-not $KnowledgeDir) {
    $KnowledgeDir = Join-Path $rootDir "重点股票\深度分析\后评估逻辑\逻辑积累"
}

# 确保子目录存在
$subDirs = @("元评估", "条件规则", "失效归因", "知识代谢", "知识蒸馏")
foreach ($sd in $subDirs) {
    $d = Join-Path $KnowledgeDir $sd
    if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
}

$evalResult = Get-Content $EvalResultPath -Raw -Encoding UTF8 | ConvertFrom-Json
$meta = $evalResult.meta
$reportDate = $meta.report_date
$todayLabel = $meta.eval_date

Write-Host "===== 知识库更新 ====="

# 1. 信号有效性跟踪CSV
$signalTrackFile = Join-Path $KnowledgeDir "指标有效性跟踪.csv"
$signalHeaderExists = Test-Path $signalTrackFile
$bLayer = $evalResult.b_layer
$signalCsvLine = "$todayLabel,$($meta.stock_code),$($meta.stock_name),$($evalResult.total_score),$($evalResult.rating),$($bLayer.b1_catalyst_tracking.score),$($bLayer.b2_market_phase.score),$($bLayer.b5_data_source_stability.score),$($bLayer.b10_wyckoff_accuracy.score)"
if (-not $signalHeaderExists) {
    "评估日期,股票代码,股票名称,综合评分,评级,B1催化剂,B2市场阶段,B5数据源,B10_Wyckoff" | Add-Content $signalTrackFile -Encoding UTF8
}
$signalCsvLine | Add-Content $signalTrackFile -Encoding UTF8
Write-Host "  ✅ 信号跟踪: $signalTrackFile"

# 2. 改进日志MD
$improveLogFile = Join-Path $KnowledgeDir "改进日志.md"
$suggestions = $evalResult.suggestions
$logEntry = @"

### ${todayLabel}: $($meta.stock_name)($($meta.stock_code)) 深度分析后评估

- **综合评分**: $($evalResult.total_score)/$($evalResult.total_max) [$($evalResult.rating)]
- **方法论版本**: $($meta.report_version) | **报告日期**: $reportDate
"@

if ($suggestions.Count -gt 0) {
    $logEntry += "`n- **优化建议**: $($suggestions.Count)条`n"
    foreach ($sg in $suggestions) {
        $logEntry += "  - [$($sg.priority)] $($sg.issue)`n"
    }
} else {
    $logEntry += "`n- **结论**: 本次评估未触发优化建议`n"
}
$logEntry += "`n---`n"
Add-Content $improveLogFile -Encoding UTF8 -Value $logEntry
Write-Host "  ✅ 改进日志: $improveLogFile"

# 3. 优化建议JSON
$suggestFile = Join-Path $KnowledgeDir "优化建议.json"
if ($suggestions.Count -gt 0) {
    $existingSugs = @()
    if (Test-Path $suggestFile) {
        try {
            $existingData = Get-Content $suggestFile -Raw -Encoding UTF8 | ConvertFrom-Json
            $existingSugs = @($existingData.suggestions)
        } catch { $existingSugs = @() }
    }
    $newSugs = @($suggestions | ForEach-Object {
        @{
            date = $todayLabel
            target = $_.target
            section = $_.section
            issue = $_.issue
            suggestion = $_.suggestion
            priority = $_.priority
            status = "待确认"
        }
    })
    $allSugs = @($existingSugs) + $newSugs
    @{ date = $todayLabel; suggestions = $allSugs } | ConvertTo-Json -Depth 3 | Set-Content $suggestFile -Encoding UTF8
    Write-Host "  ✅ 优化建议: $suggestFile ($($newSugs.Count)条新增)"
} else {
    Write-Host "  ℹ️ 优化建议: 无新增"
}

# 4. 催化剂映射库更新
if ($evalResult.b_layer.b1_catalyst_tracking.details.catalyst_count -gt 0) {
    $catalystFile = Join-Path $KnowledgeDir "催化剂映射.json"
    # 从原始评估数据读取催化剂详情
    $evalDataPath = $EvalResultPath -replace '评估结果', '评估数据'
    if (Test-Path $evalDataPath) {
        $evalData = Get-Content $evalDataPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $existingCats = @()
        if (Test-Path $catalystFile) {
            try { $existingCats = @(Get-Content $catalystFile -Raw -Encoding UTF8 | ConvertFrom-Json) } catch {}
        }
        foreach ($cat in $evalData.catalysts) {
            $existingCats += @{
                date = $reportDate
                stock = $meta.stock_code
                level = $cat.level
                category = $cat.category
                description = $cat.description
                expected_impact = $cat.expected_impact
                status = $cat.status
                probability = $cat.probability
            }
        }
        $existingCats | ConvertTo-Json -Depth 3 | Set-Content $catalystFile -Encoding UTF8
        Write-Host "  ✅ 催化剂映射: $catalystFile"
    }
}

# 5. 元评估数据采集
$metaEvalDir = Join-Path $KnowledgeDir "元评估"
$metaTrackFile = Join-Path $metaEvalDir "评估系统有效性跟踪.csv"
$metaHeaderExists = Test-Path $metaTrackFile
$totalScore = $evalResult.total_score
$sugCount = $suggestions.Count
$metaRow = "$todayLabel,$($meta.stock_code),$($evalResult.direction_calibration.direction),$totalScore,$sugCount,$($evalResult.a_layer.total_score),$($evalResult.b_layer.total_score)"
if (-not $metaHeaderExists) {
    "评估日期,股票代码,评分方向,综合评分,建议数,A层得分,B层得分" | Add-Content $metaTrackFile -Encoding UTF8
}
$metaRow | Add-Content $metaTrackFile -Encoding UTF8
Write-Host "  ✅ 元评估: $metaTrackFile"

Write-Host "===== 知识库更新完成 ====="
return $KnowledgeDir
