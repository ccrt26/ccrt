# 铁律量化 - 股票数据获取模块
# 数据源：腾讯行情[1], 新浪K线[2], 东方财富财务[3][6][7][9][10]
# 最后更新：2026-05-22
# 合规状态：详见 §1.5 数据源实测状态

# ============================================================
# 数据源优先级配置（主 → 备）
# ============================================================
# ============================================================
# API调用限速器（全局，避免被反爬）
# ============================================================
$script:GlobalApiCallCount = 0
$script:LastApiCallTime = [datetime]::MinValue

function Invoke-ThrottledApiCall {
    param([scriptblock]$ScriptBlock)
    $elapsed = ([datetime]::Now - $script:LastApiCallTime).TotalMilliseconds
    if ($elapsed -lt 300) { Start-Sleep -Milliseconds (300 - $elapsed) }
    $script:GlobalApiCallCount++
    if ($script:GlobalApiCallCount % 10 -eq 0) { Start-Sleep -Seconds 2 }
    $script:LastApiCallTime = [datetime]::Now
    return & $ScriptBlock
}

$script:SourcePriority = @{
    Quote      = @("腾讯", "新浪")         # 实时行情
    KLine      = @("新浪", "腾讯")         # K线数据
    Financial  = @("东方财富", "同花顺")    # 财务数据（THS备份）
    Sector     = @("东方财富", "同花顺")    # 板块行情（THS备份）
    FundFlow   = @("东方财富", "同花顺")    # 资金流向（THS备份）
    Northbound = @("东方财富")             # 北向资金（独有）
    Research   = @("东方财富")             # 研报（独有）
    Margin     = @("东方财富")             # 融资融券（独有）
}
$script:SourceUsed = @{}    # 记录每次调用实际使用的源

# ============================================================
# 本地数据缓存层（所有数据通用兜底）
# ============================================================
$script:CacheDir = Join-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) "data_cache"
if (-not (Test-Path $script:CacheDir)) { New-Item -ItemType Directory -Path $script:CacheDir -Force | Out-Null }

# 缓存有效时长（小时）
$script:CacheTTL = @{
    Quote      = 1    # 行情变化快，1小时
    KLine      = 24   # K线收盘后不变，24小时
    Financial  = 168  # 财务数据季度更新，7天
    Sector     = 6    # 板块数据半日更新
    FundFlow   = 24   # 资金流向盘后固定，日频
    Northbound = 24   # 北向资金日频
    Research   = 24   # 研报每日更新
    Margin     = 24   # 融资融券每日更新
    PEPercentile = 168 # PE百分位变化慢，7天
}

function Save-DataCache {
    param([string]$Key, $Data)
    if (-not $Data) { return }
    $path = Join-Path $script:CacheDir "$Key.json"
    try {
        $toSave = @{ Timestamp = (Get-Date).ToString("o"); Data = $Data }
        $toSave | ConvertTo-Json -Depth 5 -Compress | Set-Content $path -Encoding UTF8
    } catch { Write-Debug "Cache save failed for $Key : $_" }
}

function Load-DataCache {
    param([string]$Key, [int]$TTLHours = 24)
    $path = Join-Path $script:CacheDir "$Key.json"
    if (-not (Test-Path $path)) { return $null }
    try {
        $cached = Get-Content $path -Encoding UTF8 -Raw | ConvertFrom-Json
        $age = [datetime]::Now - [datetime]::Parse($cached.Timestamp)
        if ($age.TotalHours -gt $TTLHours) {
            Write-Debug "Cache expired for $Key (age: $($age.TotalHours.ToString('0.0'))h)"
            return $null
        }
        return $cached.Data
    } catch { return $null }
}

# 通用：获取数据（API优先 → 缓存兜底）
function Invoke-DataWithCache {
    param(
        [Parameter(Mandatory=$true)][string]$DataName,
        [Parameter(Mandatory=$true)][scriptblock]$ApiCall
    )
    # 先尝试API
    try {
        $result = & $ApiCall
        if ($null -ne $result) {
            Save-DataCache -Key $DataName -Data $result
            return $result
        }
    } catch {
        Write-Warning "[$DataName] API失败: $_"
    }
    # API失败 → 尝试缓存
    $ttl = if ($script:CacheTTL.ContainsKey($DataName)) { $script:CacheTTL[$DataName] } else { 24 }
    $cached = Load-DataCache -Key $DataName -TTLHours $ttl
    if ($null -ne $cached) {
        Write-Warning "[$DataName] API失败，使用缓存（有效期${ttl}h内）"
        return $cached
    }
    Write-Warning "[$DataName] API失败，缓存不可用"
    return $null
}

# 通用：查询某类数据上次使用的源
function Get-LastUsedSource {
    param([string]$DataName)
    if ($DataName) { return $script:SourceUsed[$DataName] }
    return $script:SourceUsed
}

# ============================================================
# 同花顺 THS 回退调用桥接
# ============================================================
function Invoke-ThsFallback {
    <#
    .SYNOPSIS
      调用 Python 桥接脚本获取同花顺 THS 数据作为东方财富的备份
    #>
    param(
        [Parameter(Mandatory=$true)][string]$Action,
        [string]$Params = ""
    )
    $thsScript = Join-Path (Split-Path $PSScriptRoot -Parent) "stock_data_fetcher_ths.py"
    if (-not (Test-Path $thsScript)) {
        Write-Warning "THS桥接脚本不存在: $thsScript"
        return $null
    }
    try {
        # 设置环境变量确保 Python 使用 UTF-8 输出
        $oldEncoding = $env:PYTHONIOENCODING
        $env:PYTHONIOENCODING = "utf-8"

        # 通过 cmd /c 重定向到临时文件，再用 UTF-8 读取
        $tmpFile = [System.IO.Path]::GetTempFileName()
        cmd /c "python `"$thsScript`" $Action $Params > `"$tmpFile`"" 2>$null

        $env:PYTHONIOENCODING = $oldEncoding

        if ((Test-Path $tmpFile) -and ((Get-Item $tmpFile).Length -gt 0)) {
            $raw = [System.IO.File]::ReadAllText($tmpFile, [System.Text.Encoding]::UTF8)
            Remove-Item $tmpFile -Force -ErrorAction SilentlyContinue
            if ($raw.Trim().Length -gt 0) {
                $parsed = $raw | ConvertFrom-Json
                if ($parsed -is [array] -and $parsed.Count -gt 0 -and $parsed[0].error) {
                    Write-Warning "THS fallback returned error: $($parsed[0].error)"
                    return $null
                }
                return $parsed
            }
        } else {
            Remove-Item $tmpFile -Force -ErrorAction SilentlyContinue
        }
    } catch {
        Write-Warning "THS fallback failed for $Action : $_"
    }
    return $null
}

# ============================================================
# [1] 腾讯实时行情（主） + 新浪实时行情（备）
# API: qt.gtimg.cn
# 返回：实时报价（当前价/涨跌幅/量比/换手率/PE/市值等）
# ============================================================