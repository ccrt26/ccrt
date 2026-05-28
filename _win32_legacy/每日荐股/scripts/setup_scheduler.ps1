<#
.SYNOPSIS
  铁律量化 · Windows Task Scheduler 安装脚本
.DESCRIPTION
  注册两个定时任务（After first day, both run daily）:
    1. TieLv-Evaluation  (每日 19:00) → daily_workflow.ps1 -Mode eval
    2. TieLv-DailyStock   (每日 20:00) → daily_workflow.ps1 -Mode daily_latest

  每个任务内建开盘判断，非交易日自动跳过。
.PARAMETER Uninstall
  移除已注册的任务而非创建。
.PARAMETER UserName
  运行任务的Windows用户名。默认当前用户。
.PARAMETER Password
  任务计划程序密码（需明文），如不提供则创建任务但可能无法保存凭据。
#>

param(
    [switch]$Uninstall,
    [string]$UserName = "",
    [string]$Password = ""
)
. "$PSScriptRoot/../../lib/init_encoding.ps1"

$taskPrefix = "TieLv"
$rootDir = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$scriptsDir = Join-Path $rootDir "代码文件\每日荐股\scripts"
$psPath = "powershell.exe"
$psArgs = '-NoProfile -ExecutionPolicy Bypass -File'

# 域/用户名检测
if (-not $UserName) {
    $currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $UserName = $currentUser
    Write-Output "Using current user: $UserName"
}

$tasks = @(
    @{
        Name = "$taskPrefix-Evaluation"
        Desc = "TieLv Post-Evaluation (daily 19:00)"
        Time = "19:00"
        Arg  = "$psArgs `"$scriptsDir\daily_workflow.ps1`" -Mode eval"
        TriggerType = "Daily"
    },
    @{
        Name = "$taskPrefix-DailyStock"
        Desc = "TieLv Daily Stock Analysis (daily 20:00)"
        Time = "20:00"
        Arg  = "$psArgs `"$scriptsDir\daily_workflow.ps1`" -Mode daily_latest"
        TriggerType = "Daily"
    },
    @{
        Name = "$taskPrefix-MonthlySummary"
        Desc = "TieLv Monthly Summary & Learning Prep (1st of month 09:00)"
        Time = "09:00"
        Arg  = "$psArgs `"$scriptsDir\monthly_summary.ps1`""
        TriggerType = "Monthly"
    },
    @{
        Name = "$taskPrefix-WeeklyFeedback"
        Desc = "TieLv Weekly Feedback Loop (Mon 09:00)"
        Time = "09:00"
        Arg  = "$psArgs `"$scriptsDir\weekly_feedback_loop.ps1`""
        TriggerType = "Weekly"
    },
    @{
        Name = "$taskPrefix-MonthlyCalibration"
        Desc = "TieLv Phase Discount Monthly Calibration (1st Mon 10:00)"
        Time = "10:00"
        Arg  = "$psArgs `"$scriptsDir\monthly_phase_calibration.ps1`""
        TriggerType = "Monthly"
    }
)

<#
Note on task schedule:
  On day N (first run):  manual `daily_workflow.ps1 -Mode daily`
  On day N+1 onward:
    19:00 → Evaluation (eval, also triggers archive)
    20:00 → Analysis (daily_latest, includes archive step)
  On 1st of each month:
    09:00 → Monthly summary (aggregates last month's eval data for AI learning)
  Data archiving is built into both eval and daily_latest modes.
#>

if ($Uninstall) {
    Write-Output "===== Uninstalling Tasks ====="
    foreach ($t in $tasks) {
        $existing = Get-ScheduledTask -TaskName $t.Name -ErrorAction SilentlyContinue
        if ($existing) {
            Unregister-ScheduledTask -TaskName $t.Name -Confirm:$false
            Write-Output "  [Removed] $($t.Name)"
        } else {
            Write-Output "  [Skipped] $($t.Name) — not found"
        }
    }
    Write-Output "Uninstall complete"
    exit 0
}

Write-Output "===== Installing Scheduled Tasks ====="

if (-not (Get-Command Register-ScheduledTask -ErrorAction SilentlyContinue)) {
    Write-Error "ScheduledTasks module not available. Requires Windows 8/Server 2012+."
    exit 1
}

if (-not (Test-Path "$scriptsDir\daily_workflow.ps1")) {
    Write-Error "Cannot find $scriptsDir\daily_workflow.ps1"
    exit 1
}

$usePassword = $Password -ne ""
if (-not $usePassword) {
    Write-Warning "No -Password provided. Tasks may need manual credential setup in taskschd.msc"
    Write-Warning "Recommended: setup_scheduler.ps1 -Password 'your_password'"
}

foreach ($t in $tasks) {
    # Remove if exists
    $existing = Get-ScheduledTask -TaskName $t.Name -ErrorAction SilentlyContinue
    if ($existing) {
        Unregister-ScheduledTask -TaskName $t.Name -Confirm:$false
        Write-Output "  [Replaced] $($t.Name)"
    }

    $action = New-ScheduledTaskAction -Execute $psPath -Argument $t.Arg
    if ($t.TriggerType -eq "Monthly") {
        $trigger = New-ScheduledTaskTrigger -Monthly -At $t.Time -DaysOfMonth 1
    } else {
        $trigger = New-ScheduledTaskTrigger -Daily -At $t.Time
    }
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2)

    # Try to create with S4U logon type (no saved password needed if user is logged in)
    if ($usePassword) {
        $principal = New-ScheduledTaskPrincipal -UserId $UserName -LogonType Password -RunLevel Limited
        Register-ScheduledTask -TaskName $t.Name -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Password $Password -Force | Out-Null
    } else {
        # Without password: creates task but only runs when user is logged on
        $principal = New-ScheduledTaskPrincipal -UserId $UserName -LogonType S4U -RunLevel Limited
        Register-ScheduledTask -TaskName $t.Name -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
    }
    Write-Output "  [Registered] $($t.Name) — daily at $($t.Time)"
}

Write-Output ""
Write-Output "Done. Use taskschd.msc to verify or modify."
Write-Output ""
foreach ($t in $tasks) {
    $existing = Get-ScheduledTask -TaskName $t.Name -ErrorAction SilentlyContinue
    $status = if ($existing) { "OK" } else { "FAILED" }
    Write-Output "  [$status] $($t.Name)"
}
