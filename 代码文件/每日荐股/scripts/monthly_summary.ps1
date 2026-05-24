<#
.SYNOPSIS
  TieLv Monthly Data Summary Script
.DESCRIPTION
  Monthly (1st) or manual trigger. Collects eval data from 历史数据/.
  Outputs structured JSON for AI learning session.
.PARAMETER Month
  Target month, format yyyy-MM. Default last month.
.PARAMETER SourceDir
  Project root.
#>

param(
    [string]$Month = (Get-Date).AddMonths(-1).ToString("yyyy-MM"),
    [string]$SourceDir = "Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))"
)

$archiveRoot = Join-Path $SourceDir "历史数据"
$dailyDir = Join-Path $SourceDir "每日荐股"
$scriptsDir = Join-Path $dailyDir "运营记录"
$monthlyDir = Join-Path $archiveRoot "monthly"
$logFile = Join-Path $scriptsDir "workflow_$(Get-Date -Format yyyyMM).log"

if (-not (Test-Path $monthlyDir)) { New-Item -ItemType Directory -Path $monthlyDir -Force | Out-Null }

function Write-Log {
    param([string]$Msg, [string]$Level = "INFO")
    $time = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$time][MONTHLY][$Level] $Msg"
    Add-Content -Path $logFile -Value $line -Encoding UTF8
    Write-Output $line
}

Write-Log -Msg "===== Monthly summary started ($Month) ====="

$year, $monthNum = $Month -split '-'
$monthLabel = "$year$monthNum"

# 1. Collect monthly eval data
Write-Log -Msg "[1/4] Collecting eval data..."
$evalDir = Join-Path $archiveRoot "eval"
$monthlyEvalFiles = @()
if (Test-Path $evalDir) {
    $monthlyEvalFiles = Get-ChildItem $evalDir -Filter "${monthLabel}*" | Sort-Object Name
}

$finalDir = Join-Path $archiveRoot "final"
$monthlyFinalFiles = @()
if (Test-Path $finalDir) {
    $monthlyFinalFiles = Get-ChildItem $finalDir -Filter "${monthLabel}*" | Sort-Object Name
}
Write-Log -Msg "  Eval reports: $($monthlyEvalFiles.Count), Final data: $($monthlyFinalFiles.Count)"

# 2. Workflow records
Write-Log -Msg "[2/4] Reading workflow records..."
$recordsFile = Join-Path $scriptsDir "workflow_records.csv"
$monthlyRecords = @()
if (Test-Path $recordsFile) {
    $allRecords = Import-Csv $recordsFile -Encoding UTF8
    $monthlyRecords = $allRecords | Where-Object {
        $_.Date -and $_.Date -match "^${year}-${monthNum}"
    }
}
$totalEvalRuns = ($monthlyRecords | Where-Object { $_.Mode -eq "eval" }).Count
$totalDailyRuns = ($monthlyRecords | Where-Object { $_.Mode -like "daily*" }).Count
Write-Log -Msg "  Runs: ${totalDailyRuns} analysis, ${totalEvalRuns} eval"

# 3. Key stock data
Write-Log -Msg "[3/4] Key stock data..."
$keystoreEvalDir = Join-Path $archiveRoot "重点股票"
$keystockMonthFiles = @()
if (Test-Path $keystoreEvalDir) {
    $keystockMonthFiles = Get-ChildItem $keystoreEvalDir -Filter "${monthLabel}*" | Sort-Object Name
}
Write-Log -Msg "  Key stock files: $($keystockMonthFiles.Count)"

# 4. Latest eval PDF
$evalReportDir = Join-Path $dailyDir "评估报告"
$latestEvalPdf = ""
if (Test-Path $evalReportDir) {
    $pdfs = Get-ChildItem $evalReportDir -Filter "*.pdf" | Sort-Object LastWriteTime -Descending
    if ($pdfs.Count -gt 0) { $latestEvalPdf = $pdfs[0].FullName }
}

# 5. Output JSON
$summaryJson = @{
    Month = $Month
    GeneratedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    EvalReportsCount = $monthlyEvalFiles.Count
    FinalDataCount = $monthlyFinalFiles.Count
    TotalEvalRuns = $totalEvalRuns
    TotalDailyRuns = $totalDailyRuns
    KeystockFilesCount = $keystockMonthFiles.Count
    LatestEvalPdf = $latestEvalPdf
    DataPaths = @{
        EvalDir = $evalDir
        FinalDir = $finalDir
        MonthlyDir = $monthlyDir
    }
} | ConvertTo-Json -Depth 3

$jsonFile = Join-Path $monthlyDir "${monthLabel}_monthly_data.json"
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($jsonFile, $summaryJson, $utf8NoBom)
Write-Log -Msg "  JSON output: $jsonFile"
Write-Log -Msg "===== Monthly summary complete ====="
Write-Log -Msg "Next: inform AI to run monthly learning"
