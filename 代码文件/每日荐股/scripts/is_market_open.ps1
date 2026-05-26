<#
.SYNOPSIS
  A股交易日判断脚本
.DESCRIPTION
  判断指定日期（默认今天）是否为A股交易日。
  排除周末、排除中国法定节假日。支持外部CSV配置。
.PARAMETER Date
  要检查的日期，格式 yyyy-MM-dd。默认今天。
.PARAMETER HolidayFile
  节假日配置文件路径（CSV），不指定则使用内置默认日历。
.OUTPUTS
  [bool] $true=交易日, $false=非交易日
  $LASTEXITCODE: 0=交易日, 1=非交易日
.EXAMPLE
  .\is_market_open.ps1
  .\is_market_open.ps1 -Date "2026-05-22"
#>

param(
    [string]$Date = (Get-Date -Format "yyyy-MM-dd"),
    [string]$HolidayFile = ""
)
. "$PSScriptRoot/../../lib/init_encoding.ps1"

$targetDate = Get-Date $Date -ErrorAction Stop
$dateStr = $targetDate.ToString("yyyy-MM-dd")
$weekDay = $targetDate.DayOfWeek

# Step 1: weekend check
if ($weekDay -eq [DayOfWeek]::Saturday -or $weekDay -eq [DayOfWeek]::Sunday) {
    Write-Output "false"
    exit 1
}

# Step 2: holiday check
$builtInHolidays = @()
$builtInHolidays += "2026-01-01"   # New Year
$builtInHolidays += "2026-02-16","2026-02-17","2026-02-18","2026-02-19","2026-02-20"  # Spring Festival
$builtInHolidays += "2026-04-06"   # Qingming
$builtInHolidays += "2026-05-01","2026-05-04","2026-05-05"  # Labor Day
$builtInHolidays += "2026-06-19"   # Dragon Boat
$builtInHolidays += "2026-10-01","2026-10-02","2026-10-05","2026-10-06","2026-10-07","2026-10-08"  # National Day + Mid-Autumn

$makeupWorkdays = @()  # Saturday/Sunday makeup workdays

$holidays = $builtInHolidays

if ($HolidayFile -and (Test-Path $HolidayFile)) {
    try {
        $fileHolidays = Import-Csv $HolidayFile -Encoding UTF8
        if ($fileHolidays.Count -gt 0) {
            $holidays = $fileHolidays | Where-Object { $_.Type -eq "holiday" } | ForEach-Object { $_.Date }
            $makeupWorkdays = $fileHolidays | Where-Object { $_.Type -eq "makeup" } | ForEach-Object { $_.Date }
        }
    } catch {
        Write-Warning ("Holiday file read failed, using built-in: " + $_.Exception.Message)
    }
}

if ($dateStr -in $makeupWorkdays) {
    Write-Output "true"
    exit 0
}

if ($dateStr -in $holidays) {
    Write-Output "false"
    exit 1
}

Write-Output "true"
exit 0
