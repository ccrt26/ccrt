<#
.SYNOPSIS
    数据质检脚本 — 每日荐股模拟交易前置检查 (玉夜设计)
.DESCRIPTION
    检查API连通性、数据完整性、缓存新鲜度，输出质检报告。
    被 sim_trading_daily.ps1 在 Step 4 调用。
.PARAMETER Mode
    daily_sim (每日荐股模拟) / key_stock (重点股票模拟) / eval (后评估)
.PARAMETER DataFile
    待检查的数据文件路径
.PARAMETER RootDir
    项目根目录
.OUTPUT
    JSON质检报告 → stdout
#>

[CmdletBinding()]
param(
    [ValidateSet("daily_sim", "key_stock", "eval")]
    [string]$Mode = "daily_sim",
    [string]$DataFile = "",
    [string]$RootDir = ""
)
. "$PSScriptRoot/../lib/init_encoding.ps1"

# Auto-detect project root if not provided
if (-not $RootDir) {
    $RootDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
}

$result = [PSCustomObject]@{
    CheckedAt       = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss")
    Mode            = $Mode
    Flag            = "normal"   # normal | degraded | cached
    AlertLevel      = "L0"       # L0=正常, L1=轻微降级, L2=中度降级, L3=严重(双源全挂)
    Passed          = $true
    DegradedFields  = @()
    CachedFields    = @()
    Checks          = @()
    ApiLatencyMs    = 0
    Messages        = @()
}

function Add-Check {
    param([string]$Name, [bool]$Passed, [string]$Level, [string]$Detail)
    $check = [PSCustomObject]@{ Name = $Name; Passed = $Passed; Level = $Level; Detail = $Detail }
    $result.Checks += $check
    if (-not $Passed -and $Level -eq "ERROR") { $result.Passed = $false }
}

# ---- 1. API 连通性 ----
$apiStart = Get-Date
try {
    $tencentUrl = "http://qt.gtimg.cn/q=sh000001"
    $tencentResp = Invoke-WebRequest -Uri $tencentUrl -TimeoutSec 3 -UseBasicParsing
    $latency = [Math]::Round(((Get-Date) - $apiStart).TotalMilliseconds, 0)
    $result.ApiLatencyMs = $latency
    if ($tencentResp.Content -match "sh000001") {
        Add-Check "腾讯API连通" $true "INFO" "延迟${latency}ms"
    } else {
        Add-Check "腾讯API连通" $false "WARN" "响应内容异常"
        $result.Flag = "degraded"
        $result.DegradedFields += "quote_primary"
    }
} catch {
    Add-Check "腾讯API连通" $false "WARN" "超时/不可达: $_"
    $result.Flag = "degraded"
    $result.DegradedFields += "quote_primary"
}

# 新浪备源
try {
    $sinaUrl = "http://hq.sinajs.cn/list=sh000001"
    $sinaResp = Invoke-WebRequest -Uri $sinaUrl -TimeoutSec 3 -UseBasicParsing
    if ($sinaResp.Content -match "上证指数") {
        Add-Check "新浪API连通" $true "INFO" "备源可用"
    } else {
        Add-Check "新浪API连通" $false "WARN" "备源响应异常"
        if ($result.Flag -eq "degraded") { $result.Flag = "cached" }
        $result.CachedFields += "quote_backup"
    }
} catch {
    Add-Check "新浪API连通" $false "WARN" "备源不可达"
    if ($result.Flag -eq "degraded") { $result.Flag = "cached" }
}

# ---- 2. 数据文件检查 ----
if ($DataFile -and (Test-Path $DataFile)) {
    $fileAge = [Math]::Round(((Get-Date) - (Get-Item $DataFile).LastWriteTime).TotalHours, 1)
    if ($fileAge -gt 6) {
        Add-Check "数据文件新鲜度" $false "WARN" "文件已${fileAge}h未更新(>6h)"
        if ($result.Flag -ne "cached") { $result.Flag = "degraded" }
    } else {
        Add-Check "数据文件新鲜度" $true "INFO" "${fileAge}h前更新"
    }

    try {
        $data = Get-Content $DataFile -Raw -Encoding UTF8 | ConvertFrom-Json
        $recCount = 0
        $records = if ($data.Recommendations) { $data.Recommendations } elseif ($data.Stocks) { $data.Stocks } else { @() }
        $recCount = @($records).Count

        if ($recCount -lt 20) {
            Add-Check "推荐股票数" $false "WARN" "仅${recCount}只(<20), 异常少"
        } else {
            Add-Check "推荐股票数" $true "INFO" "${recCount}只"
        }

        # null值穿透检查
        $nullCritical = @()  # TotalScore → ERROR
        $nullDegraded = @()  # MA/技术指标 → WARN
        foreach ($r in $records) {
            if (-not $r.TotalScore -or $r.TotalScore -lt 0) { $nullCritical += "$($r.Code):TotalScore" }
            if (-not $r.MA5) { $nullDegraded += "$($r.Code):MA5" }
            if (-not $r.MA10) { $nullDegraded += "$($r.Code):MA10" }
            if (-not $r.MA20) { $nullDegraded += "$($r.Code):MA20" }
        }
        if ($nullCritical.Count -gt 0) {
            Add-Check "null值穿透" $false "ERROR" "检测到null关键字段: $($nullCritical -join ', ')"
        } elseif ($nullDegraded.Count -gt 0) {
            Add-Check "null值穿透" $true "WARN" "技术指标缺失(K线降级): $($nullDegraded -join ', ')"
        } else {
            Add-Check "null值穿透" $true "INFO" "无null关键字段"
        }

        # data_quality_flag (v2.9+)
        if ($data.data_quality -and $data.data_quality.flag) {
            $dqFlag = $data.data_quality.flag
            if ($dqFlag -eq "cached") {
                $result.Flag = "cached"
                $result.CachedFields += @($data.data_quality.cached_fields)
                Add-Check "数据质量标记" $false "WARN" "评分引擎标记cached: $($data.data_quality.cached_fields -join ',')"
            } elseif ($dqFlag -eq "degraded") {
                if ($result.Flag -ne "cached") { $result.Flag = "degraded" }
                $result.DegradedFields += @($data.data_quality.degraded_fields)
                Add-Check "数据质量标记" $true "INFO" "评分引擎标记degraded: $($data.data_quality.degraded_fields -join ',')"
            } else {
                Add-Check "数据质量标记" $true "INFO" "评分引擎标记normal"
            }
        }
    } catch {
        Add-Check "数据文件解析" $false "ERROR" "JSON解析失败: $_"
    }
} else {
    Add-Check "数据文件存在" $false "ERROR" "文件不存在: $DataFile"
    $result.Flag = "cached"
}

# ---- 3. 财务缓存新鲜度 ----
$cacheDir = Join-Path $RootDir "代码文件/数据/cache"
if (Test-Path $cacheDir) {
    $cacheFiles = Get-ChildItem $cacheDir -Filter "financial_*.json" -ErrorAction SilentlyContinue
    $staleCount = 0
    foreach ($f in $cacheFiles) {
        $age = [Math]::Round(((Get-Date) - $f.LastWriteTime).TotalHours, 0)
        if ($age -gt 168) { $staleCount++ }
    }
    if ($staleCount -gt 0) {
        Add-Check "财务缓存新鲜度" $false "WARN" "${staleCount}个缓存超168h"
    } else {
        Add-Check "财务缓存新鲜度" $true "INFO" "全部在TTL内"
    }
} else {
    Add-Check "财务缓存目录" $false "INFO" "缓存目录不存在, 首次运行"
}

# ---- AlertLevel 判定 (P1-1: L3事件告警) ----
if ($result.Flag -eq "cached") {
    if (-not $result.Passed) { $result.AlertLevel = "L3" }
    else { $result.AlertLevel = "L2" }
} elseif ($result.Flag -eq "degraded") {
    $result.AlertLevel = "L1"
}

# ---- 输出 ----
$json = $result | ConvertTo-Json -Depth 4 -Compress
Write-Output $json
