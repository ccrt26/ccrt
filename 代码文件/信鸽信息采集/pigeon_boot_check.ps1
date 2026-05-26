﻿# 信鸽开机自检 — 检测当日19:00采集是否漏执行，漏则补齐
# 由 Windows Task Scheduler "At startup" 触发器调用
# 设计: 开机→检查今日events.json→缺失则执行采集

$ErrorActionPreference = "Continue"
$scriptDir = $PSScriptRoot
$projectRoot = (Get-Item "$scriptDir\..\..").FullName

$today = (Get-Date).ToString("yyyy-MM-dd")
$eventsFile = Join-Path $projectRoot "重点股票\消息面数据\${today}_events.json"
$logDir = Join-Path $projectRoot "重点股票\消息面数据"
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

$bootLog = Join-Path $logDir "boot_check.log"

function Write-BootLog {
    param([string]$Level, [string]$Msg)
    $ts = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    "$ts [$Level] $Msg" | Out-File -FilePath $bootLog -Append -Encoding UTF8
}

# ============================================================
# 检查当日是否已采集
# ============================================================
if (Test-Path $eventsFile) {
    Write-BootLog "INFO" "今日采集已完成: $eventsFile"
    Write-BootLog "INFO" "开机自检通过，跳过采集。"
    exit 0
}

Write-BootLog "INFO" "今日采集缺失 ($today)，开机补采启动..."

# ============================================================
# 节假日检查 (复用主控逻辑)
# ============================================================
$configPath = Join-Path $scriptDir "pigeon_config.json"
if (Test-Path $configPath) {
    $config = Get-Content -Path $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $holidaysFile = Join-Path $projectRoot $config.schedule.holidays_file
    if ($config.schedule.skip_holidays -and (Test-Path $holidaysFile)) {
        $holidays = Get-Content -Path $holidaysFile -Encoding UTF8 | Where-Object { $_ -match $today }
        if ($holidays) {
            Write-BootLog "INFO" "今日为节假日 ($today)，跳过采集。"
            exit 0
        }
    }
} else {
    Write-BootLog "WARN" "配置文件不存在: $configPath，使用默认参数继续。"
}

# ============================================================
# 调用主控采集 (已过19:00，直接采集今日)
# ============================================================
Write-BootLog "INFO" "启动信鸽采集: pigeon_collector.ps1"

$collectorScript = Join-Path $scriptDir "pigeon_collector.ps1"
$result = & $collectorScript 2>&1
$exitCode = $LASTEXITCODE

# 记录结果
$resultSummary = ($result | Select-Object -Last 5) -join " | "
Write-BootLog "INFO" "采集完成 | ExitCode=$exitCode | $resultSummary"

if ($exitCode -eq 0) {
    Write-BootLog "INFO" "开机补采成功。"
} elseif ($exitCode -eq 1) {
    Write-BootLog "WARN" "开机补采部分完成(部分源失败)。"
} else {
    Write-BootLog "ERROR" "开机补采失败(全部源不可用)。"
}

exit $exitCode
