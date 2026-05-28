# Pigeon Scheduler Registration
# TieLv Quant | 2026-05-26
# MUST run as Administrator

$ErrorActionPreference = "Continue"

$batDaily = Join-Path $PSScriptRoot "pigeon_daily.bat"
$batBoot  = Join-Path $PSScriptRoot "pigeon_boot.bat"

# Check admin
if (-NOT ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Host "ERROR: Must run as Administrator."
    Write-Host "Right-click PowerShell -> Run as Administrator, then re-run this script."
    exit 1
}

Write-Host "=== Pigeon Scheduler Registration ==="

# Remove old
schtasks /DELETE /TN "TieLv-Pigeon" /F 2>&1 | Out-Null
schtasks /DELETE /TN "TieLv-PigeonBoot" /F 2>&1 | Out-Null
Write-Host "Old tasks cleaned."

# Task 1: Daily 19:00
schtasks /CREATE /TN "TieLv-Pigeon" /SC DAILY /ST 19:00 /TR "$batDaily" /RL HIGHEST /F
if ($LASTEXITCODE -eq 0) { Write-Host "TieLv-Pigeon: Daily 19:00 OK" }
else { Write-Host "TieLv-Pigeon: FAILED" }

# Task 2: Boot check (2min delay for network)
schtasks /CREATE /TN "TieLv-PigeonBoot" /SC ONSTART /TR "$batBoot" /RL HIGHEST /F /DELAY 0002:00
if ($LASTEXITCODE -eq 0) { Write-Host "TieLv-PigeonBoot: Boot check OK" }
else { Write-Host "TieLv-PigeonBoot: FAILED" }

# Verify
Write-Host ""
schtasks /QUERY /TN "TieLv-Pigeon" /FO LIST 2>&1 | Select-String "TaskName|Status|Schedule"
schtasks /QUERY /TN "TieLv-PigeonBoot" /FO LIST 2>&1 | Select-String "TaskName|Status|Schedule"
Write-Host "=== Done ==="
