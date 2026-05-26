. "$PSScriptRoot/../../lib/init_encoding.ps1"
<#
.SYNOPSIS
  铁律量化 · 每日管线幂等守卫
.DESCRIPTION
  Task Scheduler 调用的统一入口。检查今日是否已完成管线，已跑过则跳过。
  双触发器（每日19:00 + 开机后120s）都指向此脚本，幂等检查保证不重复执行。
#>

$rootDir = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$targetDate = (Get-Date).ToString("yyyy-MM-dd")

# 幂等检查：今日是否已成功执行 daily_latest
$recordFile = Join-Path $rootDir "每日荐股\运营记录\workflow_records.csv"
$alreadyDone = $false
if (Test-Path $recordFile) {
    $alreadyDone = Select-String -Path $recordFile -Pattern "^$targetDate.*daily_latest.*SUCCESS" -Quiet
}

if ($alreadyDone) {
    $msg = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] 今日管线已完成，跳过"
    Write-Output $msg
    exit 0
}

# 开机健康检测 (L3阻断则不启动管线)
$healthScript = Join-Path $rootDir "代码文件\tools\health_check.ps1"
if (Test-Path $healthScript) {
    $msg = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] 开机健康检测..."
    Write-Output $msg
    $healthResult = & $healthScript -Mode boot -RootDir $rootDir 2>&1
    try {
        $healthJson = $healthResult | Select-Object -Last 1 | ConvertFrom-Json
        if ($healthJson.Flag -eq "blocked" -or $healthJson.AlertLevel -eq "L3") {
            $msg = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] 健康检测L3阻断 — 管线未启动"
            Write-Output $msg
            Write-Host "`n[铁律量化] 数据健康检测不通过 (L3阻断), 管线未启动。详情见: $($healthJson.HtmlReportPath)" -ForegroundColor Red
            exit 1
        }
        $msg = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] 健康检测通过 (Level: $($healthJson.AlertLevel))"
        Write-Output $msg
    } catch {
        $msg = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] 健康检测异常, 继续启动管线: $_"
        Write-Output $msg
    }
} else {
    Write-Output "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] 健康检测脚本不存在, 跳过"
}

# 启动管线
$workflowScript = Join-Path $PSScriptRoot "daily_workflow.ps1"
$msg = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] 启动每日管线: $targetDate"
Write-Output $msg

& $workflowScript -Mode daily_latest -Date $targetDate
exit $LASTEXITCODE
