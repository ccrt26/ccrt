<#
.SYNOPSIS
  Invoke-DeepEvalPipeline - Deep analysis post-evaluation orchestrator (L1)
.DESCRIPTION
  Main entry point for deep analysis post-evaluation. Orchestrates parse->calculate->report->knowledge.
  Triggered weekly on Fridays. Supports Quick/Monthly/Quarterly modes.
.PARAMETER ReportPath
  Target deep analysis report .md file path (required)
.PARAMETER Mode
  Evaluation mode: Quick/Monthly/Quarterly
.PARAMETER KeepHtml
  Keep intermediate HTML files
#>
param(
    [Parameter(Mandatory=$true)]
    [string]$ReportPath,
    [ValidateSet("Quick","Monthly","Quarterly")]
    [string]$Mode = "Quick",
    [switch]$KeepHtml = $false
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot/../lib/init_encoding.ps1"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = Split-Path -Parent (Split-Path -Parent $scriptDir)
$today = Get-Date
$todayStr = $today.ToString("yyyyMMdd")
$todayLabel = $today.ToString("yyyy-MM-dd")

Write-Host "=============================================="
Write-Host "  Deep Eval Pipeline v1.0"
Write-Host "  Mode: $Mode"
Write-Host "  Date: $todayLabel"
Write-Host "=============================================="
Write-Host ""

# ============================================================
# Stage 1: Parse deep analysis report
# ============================================================
Write-Host "[1/4] Parsing deep analysis report..."
$parserScript = Join-Path $scriptDir "Invoke-DeepAnalysisParser.ps1"
if (-not (Test-Path $parserScript)) {
    Write-Error "Parser not found: $parserScript"
    exit 1
}

$evalDataDir = Join-Path $rootDir "重点股票\深度分析\后评估报告"
if (-not (Test-Path $evalDataDir)) {
    New-Item -ItemType Directory -Path $evalDataDir -Force | Out-Null
}

$dateFromReport = ""
if ($ReportPath -match '(\d{8})') {
    $dateFromReport = $matches[1]
} else {
    $dateFromReport = $todayStr
}
$evalDataPath = Join-Path $evalDataDir "评估数据_深度分析_${dateFromReport}.json"

$parseResult = & $parserScript -ReportPath $ReportPath -OutputPath $evalDataPath 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Error "Parse failed: $parseResult"
    exit 1
}
Write-Host "  [OK] Eval data: $evalDataPath"

if (-not (Test-Path $evalDataPath)) {
    Write-Error "Eval data JSON not generated"
    exit 1
}
$evalData = Get-Content $evalDataPath -Raw -Encoding UTF8 | ConvertFrom-Json
Write-Host "  Stock: $($evalData.meta.stock_name)($($evalData.meta.stock_code))"
Write-Host "  Methodology: $($evalData.meta.methodology_version)"
Write-Host "  Catalysts: $($evalData.catalysts.Count)"
Write-Host "  Signals: $($evalData.signals.PSObject.Properties.Name.Count)"

# ============================================================
# Stage 2: Run evaluation metrics
# ============================================================
Write-Host ""
Write-Host "[2/4] Computing evaluation metrics..."
$metricsScript = Join-Path $scriptDir "Measure-DeepEvalMetrics.ps1"
if (-not (Test-Path $metricsScript)) {
    Write-Error "Metrics engine not found: $metricsScript"
    exit 1
}

$evalResultPath = Join-Path $evalDataDir "评估结果_深度分析_${dateFromReport}.json"
$metricsResult = & $metricsScript -EvalDataPath $evalDataPath -HistoricalDir $evalDataDir -OutputPath $evalResultPath 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Error "Metrics computation failed: $metricsResult"
    exit 1
}
Write-Host "  [OK] Eval result: $evalResultPath"

# ============================================================
# Stage 3: Generate PDF report
# ============================================================
Write-Host ""
Write-Host "[3/4] Generating PDF report (Mode=$Mode)..."
$reportScript = Join-Path $scriptDir "New-DeepEvalReport.ps1"
if (-not (Test-Path $reportScript)) {
    Write-Error "Report generator not found: $reportScript"
    exit 1
}

$pdfOutput = & $reportScript -EvalResultPath $evalResultPath -Mode $Mode -KeepHtml:$KeepHtml 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Report generation warning: $pdfOutput"
}
Write-Host "  [OK] PDF: $pdfOutput"

# ============================================================
# Stage 4: Update knowledge base
# ============================================================
Write-Host ""
Write-Host "[4/4] Updating knowledge base..."
$knowledgeScript = Join-Path $scriptDir "Update-DeepEvalKnowledge.ps1"
if (-not (Test-Path $knowledgeScript)) {
    Write-Error "Knowledge updater not found: $knowledgeScript"
    exit 1
}

$knowledgeResult = & $knowledgeScript -EvalResultPath $evalResultPath 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Knowledge update warning: $knowledgeResult"
}

# ============================================================
# Summary
# ============================================================
$evalResult = Get-Content $evalResultPath -Raw -Encoding UTF8 | ConvertFrom-Json
$totalScore = $evalResult.total_score
$totalMax = $evalResult.total_max
$rating = $evalResult.rating

Write-Host ""
Write-Host "=============================================="
Write-Host "  Post-Evaluation Complete"
Write-Host "=============================================="
Write-Host "  Report: $($evalData.meta.stock_name)($($evalData.meta.stock_code))"
Write-Host "  Date: $dateFromReport"
Write-Host "  Score: ${totalScore}/${totalMax} [$rating]"
Write-Host "  PDF: $pdfOutput"
Write-Host "=============================================="
Write-Host ""

# ============================================================
# Cycle trigger check
# ============================================================
$metaTrackFile = Join-Path $rootDir "重点股票\深度分析\后评估逻辑\逻辑积累\元评估\评估系统有效性跟踪.csv"
if (Test-Path $metaTrackFile) {
    $metaLines = @(Get-Content $metaTrackFile -Encoding UTF8)
    $evalCount = $metaLines.Count - 1
    if ($evalCount -gt 0) {
        Write-Host "Accumulated evaluations: $evalCount"

        if ($evalCount % 8 -eq 0) {
            Write-Host "[MESO-CYCLE] Triggered at $evalCount evals. Actions: failure attribution + condition rule learning + knowledge decay"
        }
        if ($evalCount % 16 -eq 0) {
            Write-Host "[MACRO-CYCLE] Triggered at $evalCount evals. Actions: knowledge distillation + rumination + external fusion"
        }
        if ($evalCount % 24 -eq 0) {
            Write-Host "[QUARTERLY] Triggered at $evalCount evals. Actions: methodology version upgrade assessment"
        }
    }
}

# Auto-commit
$gitAuto = Join-Path $rootDir "代码文件\tools\git_autocommit.ps1"
if (Test-Path $gitAuto) {
    $null = & $gitAuto -Module "post_eval" -Paths @("重点股票\深度分析\后评估报告") -Message "深度分析后评估产出 [$Mode]"
}

exit 0
