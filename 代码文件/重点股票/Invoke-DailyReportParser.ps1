<#
.SYNOPSIS
  Invoke-DailyReportParser — daily report MD to eval JSON (v1.8)
.DESCRIPTION
  Delegates to Python implementation. L0 utility.
#>
param([string]$Date = (Get-Date -Format 'yyyyMMdd'), [string]$OutputPath = "")

$pyScript = Join-Path (Split-Path $PSScriptRoot) "Invoke-DailyReportParser.py"
$pyArgs = @($pyScript, $Date)
if ($OutputPath) { $pyArgs += $OutputPath }
python $pyArgs
