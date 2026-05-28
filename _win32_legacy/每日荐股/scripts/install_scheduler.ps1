<#
.SYNOPSIS
  铁律量化 · Windows Task Scheduler 一键安装
.DESCRIPTION
  注册两个定时任务，各带双触发器（每日定时 + 开机补跑）。
  幂等：已存在的任务自动替换。无需管理员权限（S4U模式）。
.PARAMETER Uninstall
  移除已注册的任务而非创建。
#>

param(
    [switch]$Uninstall
)
. "$PSScriptRoot/../../lib/init_encoding.ps1"

$ErrorActionPreference = "Continue"
$rootDir = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$scriptsDir = Join-Path $rootDir "代码文件\每日荐股\scripts"
$taskPrefix = "TieLv"
$psPath = "powershell.exe"

# === Uninstall mode ===
if ($Uninstall) {
    Write-Output "===== 卸载 TieLv 定时任务 ====="
    $tasks = @("$taskPrefix-DailyPipeline", "$taskPrefix-DailyPipeline-Boot", "$taskPrefix-DailyStock", "$taskPrefix-Evaluation")
    foreach ($name in $tasks) {
        $existing = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
        if ($existing) {
            Unregister-ScheduledTask -TaskName $name -Confirm:$false
            Write-Output "  [已移除] $name"
        } else {
            Write-Output "  [跳过] $name — 不存在"
        }
    }
    Write-Output "卸载完成"
    exit 0
}

# === Pre-flight checks ===
if (-not (Get-Command Register-ScheduledTask -ErrorAction SilentlyContinue)) {
    Write-Error "ScheduledTasks 模块不可用，需要 Windows 8/Server 2012+"
    exit 1
}

$invokeScript = Join-Path $scriptsDir "invoke_daily.ps1"
$workflowScript = Join-Path $scriptsDir "daily_workflow.ps1"
if (-not (Test-Path $invokeScript)) {
    Write-Error "找不到 invoke_daily.ps1: $invokeScript"
    exit 1
}
if (-not (Test-Path $workflowScript)) {
    Write-Error "找不到 daily_workflow.ps1: $workflowScript"
    exit 1
}

$userName = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
Write-Output "===== 铁律量化 · 安装定时任务 ====="
Write-Output "  用户: $userName"
Write-Output "  脚本目录: $scriptsDir"
Write-Output ""

# === Task definitions ===
$taskDefs = @(
    @{
        Name        = "$taskPrefix-DailyPipeline"
        Description = "铁律量化 · 每日数据管线（19:00定时）"
        Time        = "19:00"
        ScriptPath  = $invokeScript
        ScriptArgs  = ""
        DualTrigger = $false  # 仅定时触发，不开机补跑
    },
    @{
        Name        = "$taskPrefix-DailyPipeline-Boot"
        Description = "铁律量化 · 管线开机补跑（登录触发，invoke_daily内含20:00时间闸门）"
        Time        = $null
        ScriptPath  = $invokeScript
        ScriptArgs  = ""
        BootOnly    = $true  # 仅登录触发
    },
    @{
        Name        = "$taskPrefix-DailyStock"
        Description = "铁律量化 · 每日重点股票分析报告（20:00定时）"
        Time        = "20:00"
        ScriptPath  = $workflowScript
        ScriptArgs  = "-Mode daily_latest"
        DualTrigger = $false
    },
    @{
        Name        = "$taskPrefix-Evaluation"
        Description = "铁律量化 · 每日后评估（19:30定时 或 开机补跑）"
        Time        = "19:30"
        ScriptPath  = $workflowScript
        ScriptArgs  = "-Mode eval"
        DualTrigger = $true
    }
)

# === Register each task ===
foreach ($def in $taskDefs) {
    $name = $def.Name
    Write-Output "--- 注册: $name ---"

    # Remove existing task (idempotent)
    $existing = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if ($existing) {
        Unregister-ScheduledTask -TaskName $name -Confirm:$false
        Write-Output "  [替换] 旧任务已删除"
    }

    # Build action
    $argString = '-NoProfile -ExecutionPolicy Bypass -File "' + $def.ScriptPath + '"'
    if ($def.ScriptArgs) {
        $argString += " " + $def.ScriptArgs
    }
    $action = New-ScheduledTaskAction -Execute $psPath -Argument $argString

    # Build triggers based on task config
    $triggers = @()
    if (-not $def.BootOnly) {
        $triggers += New-ScheduledTaskTrigger -Daily -At $def.Time
    }
    if ($def.DualTrigger -or $def.BootOnly) {
        $triggers += New-ScheduledTaskTrigger -AtLogon -RandomDelay (New-TimeSpan -Seconds 120)
    }

    # Build settings
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
        -MultipleInstances IgnoreNew

    # Build principal (S4U: no password needed, runs only when user is logged on)
    $principal = New-ScheduledTaskPrincipal -UserId $userName -LogonType S4U -RunLevel Limited

    # Register
    try {
        Register-ScheduledTask -TaskName $name `
            -Description $def.Description `
            -Action $action `
            -Trigger $triggers `
            -Settings $settings `
            -Principal $principal `
            -Force `
            -ErrorAction Stop | Out-Null
        Write-Output "  [OK] $name"
        if ($def.BootOnly) {
            Write-Output "       触发器: AtLogon(120s)"
        } elseif ($def.DualTrigger) {
            Write-Output "       触发器: Daily $($def.Time) + AtLogon(120s)"
        } else {
            Write-Output "       触发器: Daily $($def.Time)"
        }
        Write-Output "       脚本: $(Split-Path $def.ScriptPath -Leaf)"
    } catch {
        Write-Output "  [FAIL] $name : $_"
    }
}

# === Verify ===
Write-Output ""
Write-Output "===== 验证 ====="
foreach ($def in $taskDefs) {
    $task = Get-ScheduledTask -TaskName $def.Name -ErrorAction SilentlyContinue
    if ($task) {
        $triggers = $task.Triggers | ForEach-Object { $_.CimClass.CimClassName -replace 'MSFT_Task','' }
        Write-Output "  [OK] $($def.Name) — 状态: $($task.State), 触发器: $($triggers -join ', ')"
    } else {
        Write-Output "  [FAIL] $($def.Name) — 未找到"
    }
}

Write-Output ""
Write-Output "===== 完成 ====="
Write-Output "可使用 taskschd.msc 查看或修改。"
Write-Output "下次交易日历更新: 2027年春节前需更新 is_market_open.ps1 中的节假日列表。"
Write-Output "卸载: install_scheduler.ps1 -Uninstall"
