#requires -RunAsAdministrator
<#
.SYNOPSIS
  铁律量化 · 注册定时任务（管理员权限）
.DESCRIPTION
  使用 schtasks.exe 注册，PowerShell 语法已验证通过。
  关键：PowerShell 中用双引号配合 `" 转义传递引号路径。
.PARAMETER Uninstall
  卸载所有 TieLv 定时任务
#>

param([switch]$Uninstall)

$scriptsDir = "Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))\代码文件\每日荐股\scripts"
$prefix = "TieLv"

function Add-Task {
    param([string]$Name, [string]$Time, [string]$Script, [string]$Arg = "", [string]$Schedule = "DAILY", [int]$Day = 1)

    $full = "$prefix-$Name"
    $cmd = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + $Script + '"' + $Arg

    $sch = "schtasks /CREATE /SC $Schedule"
    if ($Schedule -eq "MONTHLY") { $sch += " /D $Day" }
    $sch += " /TN $full /TR `"$cmd`" /ST $Time /RL HIGHEST /F"

    # 实际执行：Invoke-Expression 保持引号完整
    Invoke-Expression $sch

    if ($LASTEXITCODE -eq 0) {
        Write-Output "  [OK] $full → $Time"
    } else {
        Write-Output "  [FAIL] $full (exit: $LASTEXITCODE)"
    }
}

function Remove-Task {
    param([string]$Name)
    schtasks /DELETE /TN "$prefix-$Name" /F 2>$null | Out-Null
    Write-Output "  [Removed] $prefix-$Name"
}

# ===== Main =====
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]"Administrator")) {
    Write-Warning "需要管理员权限！右键 → 以管理员身份运行"
    exit 1
}

Write-Output "===== TieLv 定时任务注册 =====`n"

if ($Uninstall) {
    Write-Output "--- 卸载 ---"
    Remove-Task "Evaluation"; Remove-Task "DailyStock"; Remove-Task "MonthlySummary"
    Write-Output "`n卸载完成"
    exit 0
}

Write-Output "--- 注册 ---`n"

Add-Task -Name "Evaluation"     -Time "19:00" -Script "$scriptsDir\daily_workflow.ps1" -Arg " -Mode eval"
Add-Task -Name "DailyStock"     -Time "20:00" -Script "$scriptsDir\daily_workflow.ps1" -Arg " -Mode daily_latest"
Add-Task -Name "MonthlySummary" -Time "09:00" -Script "$scriptsDir\monthly_summary.ps1" -Schedule "MONTHLY" -Day 1

Write-Output "`n--- 验证 ---"
schtasks /QUERY /TN "$prefix-*" /FO LIST 2>$null

Write-Output "`n===== 完成 ====="
