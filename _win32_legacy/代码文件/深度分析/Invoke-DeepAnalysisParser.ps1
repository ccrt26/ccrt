<#
.SYNOPSIS
  Invoke-DeepAnalysisParser — 深度分析报告 MD → 评估数据 JSON (L0)
.DESCRIPTION
  调度 Python 解析器 parse_deep_analysis_report.py，将深度分析报告Markdown
  转换为结构化评估数据JSON。提取版本声明、六维评分、催化剂、估值、Wyckoff等。
#>
param(
    [Parameter(Mandatory=$true)]
    [string]$ReportPath,
    [string]$OutputPath = ""
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pyScript = Join-Path $scriptDir "parse_deep_analysis_report.py"

if (-not (Test-Path $pyScript)) {
    Write-Error "Parser not found: $pyScript"
    exit 1
}
if (-not (Test-Path $ReportPath)) {
    Write-Error "Report not found: $ReportPath"
    exit 1
}

if (-not $OutputPath) {
    $dateStr = (Get-Date -Format 'yyyyMMdd')
    $rootDir = Split-Path -Parent (Split-Path -Parent $scriptDir)
    $OutputPath = Join-Path $rootDir "重点股票\深度分析\后评估报告\评估数据_深度分析_${dateStr}.json"
}

$outDir = Split-Path -Parent $OutputPath
if (-not (Test-Path $outDir)) {
    New-Item -ItemType Directory -Path $outDir -Force | Out-Null
}

$pyArgs = @($pyScript, $ReportPath, '--output', $OutputPath)
$result = python $pyArgs 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Error "Parser failed: $result"
    exit 1
}

Write-Host "✅ 解析完成: $OutputPath"
return $OutputPath
