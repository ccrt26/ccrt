# L0 — 结构化输出 + 缓存管理
# 设计文档: 审计报告/架构设计/design_pigeon_info_collection_v1.0.md §三.2.4
# 闸门1a S3: events_db.json预留T+N回测字段

function Export-PigeonEventJson {
    <#
    .SYNOPSIS
      将过滤后的事件写入日期JSON文件 + 追加到events_db.json
    .PARAMETER FilteredEvents
      过滤后的事件数组 (按股票分组)
    .PARAMETER FilterStats
      过滤统计信息 (每层入/出计数)
    .PARAMETER OutputDir
      输出目录 (相对于项目根目录)
    #>
    param(
        [Parameter(Mandatory=$true)][hashtable]$FilteredEvents,
        [Parameter(Mandatory=$true)][hashtable]$FilterStats,
        [Parameter(Mandatory=$true)][string]$OutputDir
    )

    $projectRoot = (Get-Item "$PSScriptRoot\..\..").FullName
    $outDir = Join-Path $projectRoot $OutputDir
    if (-not (Test-Path $outDir)) {
        New-Item -ItemType Directory -Path $outDir -Force | Out-Null
    }

    $fetchDate = (Get-Date).ToString("yyyy-MM-dd")
    $fetchTime = (Get-Date).ToString("HH:mm:ss")

    # 汇总所有股票的事件
    $allEvents = @()
    $totalRaw = 0
    $totalL1Drop = 0; $totalL2Drop = 0; $totalL3Drop = 0; $totalL4Drop = 0
    $totalFinal = 0

    foreach ($code in $FilteredEvents.Keys) {
        $result = $FilteredEvents[$code]
        $allEvents += $result.events
        $totalFinal += $result.events.Count

        if ($result.stats) {
            $totalRaw += $result.stats.L1_in
            $totalL1Drop += ($result.stats.L1_in - $result.stats.L1_out)
            $totalL2Drop += ($result.stats.L2_in - $result.stats.L2_out)
            $totalL3Drop += ($result.stats.L3_in - $result.stats.L3_out)
            $totalL4Drop += ($result.stats.L4_in - $result.stats.L4_out)
        }
    }

    # 构建输出JSON
    $output = [PSCustomObject]@{
        fetch_date    = $fetchDate
        fetch_time    = $fetchTime
        total_raw     = $totalRaw
        total_filtered = $totalFinal
        filter_stats  = [PSCustomObject]@{
            L1_dropped = $totalL1Drop
            L2_dropped = $totalL2Drop
            L3_dropped = $totalL3Drop
            L4_dropped = $totalL4Drop
        }
        events        = @($allEvents)
    }

    # 写入日期文件
    $dateFile = Join-Path $outDir "${fetchDate}_events.json"
    $output | ConvertTo-Json -Depth 6 | Set-Content -Path $dateFile -Encoding UTF8
    Write-Host "[output] Date file written: $dateFile ($($allEvents.Count) events)"

    # 追加到events_db.json (S3: 预留回测字段)
    $dbPath = Join-Path $projectRoot (Join-Path $OutputDir "events_db.json")
    $existingDb = @()
    if (Test-Path $dbPath) {
        try {
            $existingDb = Get-Content -Path $dbPath -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($existingDb -isnot [array]) { $existingDb = @() }
        } catch {
            Write-Warning "[output] events_db.json parse failed, creating new"
            $existingDb = @()
        }
    }

    foreach ($event in $allEvents) {
        $dbEntry = [PSCustomObject]@{
            event_id       = $event.event_id
            code           = $event.code
            name           = $event.name
            category       = $event.category
            subtype        = $event.subtype
            title          = $event.title
            direction      = $event.direction
            impact_score   = $event.impact_score
            pdf_url         = $event.pdf_url
            content         = $event.content
            announcement_id = $event.announcement_id
            cninfo_url      = $event.cninfo_url
            fetch_date      = $fetchDate
            # S3: T+N回测预留字段 (事后由青山回填)
            actual_return_T1  = $null
            actual_return_T3  = $null
            actual_return_T5  = $null
            market_return_T1  = $null
            market_return_T3  = $null
            market_return_T5  = $null
            excess_return_T1  = $null
            excess_return_T3  = $null
            excess_return_T5  = $null
            verified          = $false
            verified_date     = $null
        }
        $existingDb += $dbEntry
    }

    $existingDb | ConvertTo-Json -Depth 5 | Set-Content -Path $dbPath -Encoding UTF8
    Write-Host "[output] events_db.json updated: $($existingDb.Count) total records"

    return @{
        date_file = $dateFile
        db_file   = $dbPath
        count     = $allEvents.Count
    }
}

function Update-PigeonCache {
    <#
    .SYNOPSIS
      更新缓存[C] — 当日采集结果的缓存副本，TTL=24h
    #>
    param(
        [Parameter(Mandatory=$true)]$OutputData,
        [Parameter(Mandatory=$true)][string]$CacheDir
    )

    $projectRoot = (Get-Item "$PSScriptRoot\..\..").FullName
    $cachePath = Join-Path $projectRoot $CacheDir
    if (-not (Test-Path $cachePath)) {
        New-Item -ItemType Directory -Path $cachePath -Force | Out-Null
    }

    $fetchDate = (Get-Date).ToString("yyyy-MM-dd")
    $cacheFile = Join-Path $cachePath "${fetchDate}_cache.json"

    $cacheEntry = [PSCustomObject]@{
        cached_at  = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
        ttl_hours  = 24
        expires_at = (Get-Date).AddHours(24).ToString("yyyy-MM-dd HH:mm:ss")
        data       = $OutputData
    }

    $cacheEntry | ConvertTo-Json -Depth 6 | Set-Content -Path $cacheFile -Encoding UTF8
    Write-Host "[cache] Written: $cacheFile"

    # 清理过期缓存 (>7天)
    Get-ChildItem -Path $cachePath -Filter "*_cache.json" | Where-Object {
        $_.LastWriteTime -lt (Get-Date).AddDays(-7)
    } | Remove-Item -Force
}

function Get-PigeonCache {
    <#
    .SYNOPSIS
      读取缓存[C] — 当主源+备源均不可用时兜底
    #>
    param(
        [Parameter(Mandatory=$true)][string]$CacheDir,
        [string]$Date = $null
    )

    if (-not $Date) {
        $Date = (Get-Date).ToString("yyyy-MM-dd")
    }

    $projectRoot = (Get-Item "$PSScriptRoot\..\..").FullName
    $cachePath = Join-Path $projectRoot $CacheDir
    $cacheFile = Join-Path $cachePath "${Date}_cache.json"

    if (Test-Path $cacheFile) {
        try {
            $cache = Get-Content -Path $cacheFile -Raw -Encoding UTF8 | ConvertFrom-Json
            if ((Get-Date) -lt [datetime]::Parse($cache.expires_at)) {
                Write-Host "[cache] Hit: $cacheFile (expires $($cache.expires_at))"
                return $cache.data
            } else {
                Write-Warning "[cache] Expired: $cacheFile"
            }
        } catch {
            Write-Warning "[cache] Read failed: $cacheFile"
        }
    }
    return $null
}
