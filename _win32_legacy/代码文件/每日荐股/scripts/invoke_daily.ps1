. "$PSScriptRoot/../../lib/init_encoding.ps1"
<#
.SYNOPSIS
  铁律量化 · 每日管线幂等守卫 + 开机补跑入口
.DESCRIPTION
  由 TieLv-DailyPipeline (19:00) 和 TieLv-DailyPipeline-Boot (登录触发) 调用。
  每日20:00前直接跳过（由 TieLv-DailyStock 直接调用 daily_workflow.ps1 执行）。
  20:00后的调用视为补跑，经幂等检查后启动全量管线。
#>

$rootDir = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$targetDate = (Get-Date).ToString("yyyy-MM-dd")

# 时间闸门：20:00之前不启动任何管线
# 定时执行由 TieLv-DailyStock (20:00) 直接调用 daily_workflow.ps1 -Mode daily_latest 完成
# 此脚本仅用于20:00后的补跑场景（如夜间开机、错过定时任务等）
$now = Get-Date
$cutoff = Get-Date -Hour 20 -Minute 0 -Second 0
if ($now -lt $cutoff) {
    $msg = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] 当前时间早于20:00，跳过（TieLv-DailyStock 20:00定时任务将执行当日分析）"
    Write-Output $msg
    exit 0
}

# 幂等检查：今日是否已成功执行 daily_latest
$recordFile = Join-Path $rootDir "每日荐股\运营记录\workflow_records.csv"
$alreadyDone = $false
if (Test-Path $recordFile) {
    $alreadyDone = Select-String -Path $recordFile -Pattern "^$targetDate.*daily_latest.*SUCCESS" -Quiet
}

if ($alreadyDone) {
    $msg = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] 今日管线已完成，跳过补跑"
    Write-Output $msg
    exit 0
}

$msg = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] 补跑模式：当前时间晚于20:00，启动管线"
Write-Output $msg

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
