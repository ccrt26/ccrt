# P1-1: L3事件告警 — 严重数据质量事件写入issues.csv
function Write-DataAlert {
    param(
        [Parameter(Mandatory=$true)][string]$Date,
        [Parameter(Mandatory=$true)][string]$AlertLevel,
        [Parameter(Mandatory=$true)][string]$Flag,
        [string[]]$DegradedFields = @(),
        [string[]]$CachedFields = @(),
        [string]$Detail = ""
    )
. "$PSScriptRoot/../../lib/init_encoding.ps1"
    $rootDir = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
    $issuesFile = Join-Path $rootDir "每日荐股\运营记录\issues.csv"
    $issuesDir = Split-Path -Parent $issuesFile
    if (-not (Test-Path $issuesDir)) { New-Item -ItemType Directory -Path $issuesDir -Force | Out-Null }

    $fields = if ($DegradedFields.Count -gt 0) { "Degraded: $($DegradedFields -join ',')" } else { "" }
    if ($CachedFields.Count -gt 0) { $fields += " Cached: $($CachedFields -join ',')" }

    $row = [PSCustomObject]@{
        date        = $Date
        type        = "data_quality"
        level       = $AlertLevel
        flag        = $Flag
        fields      = $fields.Trim()
        detail      = $Detail
    }

    $row | Export-Csv -Path $issuesFile -Encoding UTF8 -NoTypeInformation -Append
    Write-Warning "[ALERT] 数据质量告警已写入: $issuesFile (Level: $AlertLevel)"
}
