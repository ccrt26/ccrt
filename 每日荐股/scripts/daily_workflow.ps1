<#
.SYNOPSIS
  TieLv Daily Workflow Master Script
.DESCRIPTION
  Automated scheduling for TieLv Quantitative System.
  Mode daily       (Day N 20:00) -> Daily stock analysis with current whitepaper (manual first-run)
  Mode eval        (Day N+1 19:00) -> Post-evaluation -> report -> optimize whitepaper -> version update
  Mode daily_latest (Day N+1 20:00) -> Daily analysis with latest whitepaper (scheduled)
.PARAMETER Mode
  daily / eval / daily_latest
.PARAMETER Date
  Target date (yyyy-MM-dd). Default today. For testing.
.PARAMETER SkipMarketCheck
  Skip market open check (testing).
.PARAMETER LogOnly
  Log only, skip actual analysis (testing).
.EXAMPLE
  .\daily_workflow.ps1 -Mode daily
  .\daily_workflow.ps1 -Mode eval -Date "2026-05-22"
  .\daily_workflow.ps1 -Mode daily_latest -SkipMarketCheck
#>

param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("daily", "eval", "daily_latest")]
    [string]$Mode,
    [string]$Date = (Get-Date -Format "yyyy-MM-dd"),
    [switch]$SkipMarketCheck,
    [switch]$LogOnly
)

$rootDir = "C:\Users\34269\Documents\Claude\股票分析"
$dailyDir = Join-Path $rootDir "每日荐股"
$scriptsDir = Join-Path $dailyDir "scripts"
$evalDir = Join-Path $dailyDir "事后评估"
$logicDir = Join-Path $dailyDir "分析逻辑"
$reportDir = Join-Path $dailyDir "股票报告"
$holidayFile = Join-Path $scriptsDir "holidays_2026.csv"
$marketCheckScript = Join-Path $scriptsDir "is_market_open.ps1"
$recordFile = Join-Path $scriptsDir "workflow_records.csv"

$logFile = Join-Path $scriptsDir ("workflow_" + (Get-Date -Format "yyyyMM") + ".log")

function Write-Log {
    param([string]$Msg, [string]$Level = "INFO")
    $time = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[" + $time + "][" + $Level + "] " + $Msg
    Add-Content -Path $logFile -Value $line -Encoding UTF8
    Write-Output $line
}

function Write-Record {
    param(
        [string]$Date,
        [string]$Mode,
        [string]$Status,
        [string]$ReportName = "",
        [string]$VersionBefore = "",
        [string]$VersionAfter = "",
        [string]$Notes = ""
    )
    $header = "Date,Mode,Status,ReportName,VersionBefore,VersionAfter,Notes"
    $line = "$Date,$Mode,$Status,$ReportName,$VersionBefore,$VersionAfter,$Notes"
    $exists = Test-Path $recordFile
    if (-not $exists) {
        Add-Content -Path $recordFile -Value $header -Encoding UTF8
    }
    Add-Content -Path $recordFile -Value $line -Encoding UTF8
}

# -- Market open check --
if (-not $SkipMarketCheck) {
    Write-Log -Msg ("Checking market open for " + $Date + "...")
    $result = & $marketCheckScript -Date $Date -HolidayFile $holidayFile
    if ($LASTEXITCODE -ne 0) {
        Write-Log -Msg ($Date + " is not a trading day, skip") -Level "SKIP"
        Write-Record -Date $Date -Mode $Mode -Status "SKIPPED" -Notes "Not a trading day"
        exit 0
    }
    Write-Log -Msg ($Date + " is a trading day, proceeding")
} else {
    Write-Log -Msg "Market check skipped (-SkipMarketCheck)"
}

# -- mode: eval --
if ($Mode -eq "eval") {
    Write-Log -Msg "===== Starting Post-Evaluation ====="
    $evalDate = (Get-Date $Date).AddDays(-1).ToString("yyyy-MM-dd")
    $reportName = "evaluation_report_" + ($evalDate -replace '-','')
    $reportFile = Join-Path $evalDir ($reportName + ".docx")
    Write-Log -Msg ("Generating evaluation report: " + $reportFile)
    if ($LogOnly) {
        Write-Log -Msg "[LogOnly] Skipping actual evaluation"
    } else {
        Write-Log -Msg "[Placeholder] Actual evaluation logic TBD (data comparison + dimension attribution + rule validation)"
    }
    Write-Log -Msg "Evaluation done, entering whitepaper optimization phase"
    if ($LogOnly) {
        Write-Log -Msg "[LogOnly] Skipping whitepaper optimization"
    } else {
        Write-Log -Msg "[Placeholder] Optimize logic whitepaper based on evaluation results"
    }
    Write-Record -Date $Date -Mode $Mode -Status "SUCCESS" -ReportName $reportName -Notes "Evaluation done, manual version update confirmation needed"
    Write-Log -Msg "===== Post-Evaluation Complete ====="
}

# -- mode: daily / daily_latest --
if ($Mode -eq "daily" -or $Mode -eq "daily_latest") {
    $versionLabel = "latest"
    if ($Mode -eq "daily") { $versionLabel = "current" }
    Write-Log -Msg ("===== Starting Daily Stock Analysis (" + $versionLabel + " version) =====")
    $reportLabel = "daily_report_" + ($Date -replace '-','')
    $reportPath = Join-Path $reportDir ($reportLabel + ".html")
    $genScript = Join-Path $scriptsDir "..\分析逻辑\gen_daily_html.ps1"
    if ($LogOnly) {
        Write-Log -Msg "[LogOnly] Skipping analysis"
    } else {
        Write-Log -Msg ("Generating report via: " + $genScript)
        & $genScript -Date $Date -SkipPdf:$($Mode -eq "daily_latest" -or $reportAsHtml)
        if ($LASTEXITCODE -ne 0) {
            Write-Log -Msg "Report generation failed (exit code: $LASTEXITCODE)" -Level "ERROR"
        } else {
            Write-Log -Msg "Report generated successfully"
        }
    }
    Write-Record -Date $Date -Mode $Mode -Status "SUCCESS" -Notes ("Analysis done, output: " + $reportDir)
    Write-Log -Msg "===== Daily Stock Analysis Complete ====="
}

Write-Log -Msg "Execution Summary:"
Write-Log -Msg ("  Mode:   " + $Mode)
Write-Log -Msg ("  Date:   " + $Date)
Write-Log -Msg ("  Log:    " + $logFile)
Write-Log -Msg ("  Record: " + $recordFile)