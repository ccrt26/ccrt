# L0 — 信鸽数据同步到云端 Render 部署
# 用法:
#   .\sync_to_cloud.ps1 -Url "https://xxx.onrender.com"
#   或设置环境变量 $env:PIGEON_CLOUD_URL 和 $env:PIGEON_AUTH_TOKEN

param(
    [string]$Url = $env:PIGEON_CLOUD_URL,
    [string]$Token = $env:PIGEON_AUTH_TOKEN
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path "$ScriptDir\..\.."
$DataDir = "$ProjectRoot\重点股票\消息面数据"
$ConfigFile = "$ScriptDir\pigeon_config.json"

if (-not $Url) {
    Write-Host "错误: 请指定 Render URL" -ForegroundColor Red
    Write-Host "用法: .\sync_to_cloud.ps1 -Url 'https://pigeon-dashboard.onrender.com'"
    Write-Host "或设置: `$env:PIGEON_CLOUD_URL = 'https://xxx.onrender.com'"
    exit 1
}

$Url = $Url.TrimEnd('/')
Write-Host "=== 信鸽数据同步 ===" -ForegroundColor Cyan
Write-Host "目标: $Url" -ForegroundColor Gray
Write-Host ""

# 1. 读取 events_db.json
$eventsDbPath = "$DataDir\events_db.json"
if (-not (Test-Path $eventsDbPath)) {
    Write-Host "错误: 找不到 $eventsDbPath" -ForegroundColor Red
    exit 1
}
$eventsDb = Get-Content $eventsDbPath -Raw -Encoding UTF8 | ConvertFrom-Json
Write-Host "[1/3] events_db.json : $($eventsDb.Count) 条事件" -ForegroundColor Green

# 2. 读取每日统计文件
$dailyStats = @()
Get-ChildItem "$DataDir\*-*-*_events.json" | Sort-Object Name -Descending | ForEach-Object {
    $stat = Get-Content $_.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
    $dailyStats += @{
        date = $stat.fetch_date
        fetch_time = $stat.fetch_time
        total_raw = $stat.total_raw
        total_filtered = $stat.total_filtered
        filter_stats = $stat.filter_stats
    }
}
Write-Host "[2/3] 每日统计 : $($dailyStats.Count) 天" -ForegroundColor Green

# 3. 读取配置
$config = Get-Content $ConfigFile -Raw -Encoding UTF8 | ConvertFrom-Json
Write-Host "[3/3] 配置文件 : $($config.target_stocks.Count) 只股票" -ForegroundColor Green

# 构建同步数据包
$syncData = @{
    events_db = $eventsDb
    daily_stats = $dailyStats
    config = $config
} | ConvertTo-Json -Depth 10 -Compress

# 发送同步请求
Write-Host ""
Write-Host "正在同步到 $Url/api/sync ..." -ForegroundColor Yellow

$headers = @{
    "Content-Type" = "application/json"
}
if ($Token) {
    $headers["Authorization"] = "Bearer $Token"
}

try {
    $result = Invoke-RestMethod -Uri "$Url/api/sync" -Method Post -Body $syncData -Headers $headers -TimeoutSec 30
    Write-Host "同步成功!" -ForegroundColor Green
    Write-Host ($result | ConvertTo-Json)
} catch {
    if ($_.Exception.Response) {
        $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
        $responseBody = $reader.ReadToEnd()
        Write-Host "同步失败: $responseBody" -ForegroundColor Red
    } else {
        Write-Host "同步失败: $_" -ForegroundColor Red
    }
    exit 1
}

Write-Host ""
Write-Host "完成! 访问 $Url/pigeon_dashboard.html 查看" -ForegroundColor Cyan
