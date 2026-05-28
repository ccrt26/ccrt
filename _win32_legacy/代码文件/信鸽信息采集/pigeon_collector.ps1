# L1 — 信鸽信息采集主控脚本
# 设计文档: 审计报告/架构设计/design_pigeon_info_collection_v1.0.md §三.2.1
# 每日15:30由千光调度触发，节假日自动跳过
# 闸门1a S1-S4优化建议已纳入

param(
    [string[]]$Stocks,
    [string]$Date = $null,
    [switch]$SkipFilter,
    [string]$OutputPath = $null
)

$ErrorActionPreference = "Continue"
$scriptDir = $PSScriptRoot

# ============================================================
# 初始化
# ============================================================
. "$scriptDir\pigeon_cninfo.ps1"
. "$scriptDir\pigeon_filter.ps1"
. "$scriptDir\pigeon_output.ps1"
. "$scriptDir\..\每日荐股\scripts\modules\core.ps1"

# ============================================================
# 辅助函数 (必须在主执行流程前定义)
# ============================================================

function Invoke-BaostockForecast {
    param([string]$StockCode, [string]$StockName, [string]$StartDate, [string]$EndDate)
    $market = if ($StockCode -match '^6') { 'sh' } else { 'sz' }
    $baostockCode = "$market.$StockCode"
    $results = @()
    try {
        $forecast = Invoke-BaostockFallback -Action "forecast" -Params "--code $baostockCode --start $StartDate --end $EndDate"
        if ($forecast -and $forecast -is [array]) {
            foreach ($item in $forecast) {
                if ($item.forecastType) {
                    $results += [PSCustomObject]@{
                        title        = "$StockName 业绩预告: $($item.forecastType) $($item.profitRange)"
                        publish_time = if ($item.forecastDate) { $item.forecastDate } else { $EndDate }
                        sec_name     = $StockName
                        sec_code     = $StockCode
                        source       = "baostock"
                        source_type  = "primary"
                    }
                }
            }
        }
        $express = Invoke-BaostockFallback -Action "express" -Params "--code $baostockCode --start $StartDate --end $EndDate"
        if ($express -and $express -is [array]) {
            foreach ($item in $express) {
                $results += [PSCustomObject]@{
                    title        = "$StockName 业绩快报: 营收$($item.operateIncome) 净利$($item.netProfit)"
                    publish_time = if ($item.expressDate) { $item.expressDate } else { $EndDate }
                    sec_name     = $StockName
                    sec_code     = $StockCode
                    source       = "baostock"
                    source_type  = "primary"
                }
            }
        }
    } catch {
        Write-Warning "baostock fallback error: $($_.Exception.Message)"
    }
    return $results
}

function Invoke-ResearchNewsOnly {
    param([string]$StockCode, [string]$StockName, [string]$StartDate, [string]$EndDate)
    $results = @()
    try {
        $researchScript = Join-Path $projectRoot "代码文件\每日荐股\scripts\stock_data_fetcher_legacy.psm1"
        if (Test-Path $researchScript) {
            Import-Module $researchScript -Force -ErrorAction SilentlyContinue
            $researchData = Get-ResearchData -Code $StockCode -MaxCount 5 -ErrorAction SilentlyContinue
            if ($researchData -and $researchData -is [array]) {
                foreach ($r in $researchData) {
                    if ($r.title) {
                        $results += [PSCustomObject]@{
                            title        = $r.title
                            publish_time = if ($r.publishDate) { $r.publishDate } else { $EndDate }
                            sec_name     = $StockName
                            sec_code     = $StockCode
                            source       = "eastmoney_research"
                            source_type  = "primary"
                        }
                    }
                }
            }
        }
    } catch { }
    return $results
}

function Get-ExistingEventsForDedup {
    param([string]$StockCode)
    $dbPath = Join-Path $projectRoot $config.output.events_db
    if (-not (Test-Path $dbPath)) { return @() }
    try {
        $allEvents = Get-Content -Path $dbPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $threeDaysAgo = (Get-Date).AddDays(-3).ToString("yyyy-MM-dd")
        return @($allEvents | Where-Object {
            $_.code -eq $StockCode -and $_.fetch_date -ge $threeDaysAgo
        })
    } catch {
        return @()
    }
}

$config = Get-PigeonConfig

if (-not $OutputPath) {
    $OutputPath = $config.output.base_dir
}

if (-not $Date) {
    $Date = (Get-Date).ToString("yyyy-MM-dd")
}
$startDate = ([datetime]::Parse($Date).AddDays(-$config.api.lookback_days)).ToString("yyyy-MM-dd")

# 节假日检查
$projectRoot = (Get-Item "$scriptDir\..\..").FullName
$holidaysFile = Join-Path $projectRoot $config.schedule.holidays_file
if ($config.schedule.skip_holidays -and (Test-Path $holidaysFile)) {
    $today = (Get-Date).ToString("yyyy-MM-dd")
    $holidays = Get-Content -Path $holidaysFile -Encoding UTF8 | Where-Object { $_ -match $today }
    if ($holidays) {
        Write-Host "[pigeon] Today ($today) is a holiday, skipping collection."
        exit 0
    }
}

# 目标股票
if (-not $Stocks -or $Stocks.Count -eq 0) {
    $Stocks = @()
    foreach ($s in $config.target_stocks) {
        $Stocks += $s.code
    }
}

Write-Host "============================================================"
Write-Host "[pigeon] 信鸽信息采集启动"
Write-Host "[pigeon] 日期: $Date | 回溯: $startDate | 目标: $($Stocks.Count)只股票"
Write-Host "============================================================"

# ============================================================
# Step 1-5: 逐只股票采集
# ============================================================
$allResults = @{}
$totalRaw = 0
$sourceStatus = @{}

foreach ($code in $Stocks) {
    $stockInfo = $config.target_stocks | Where-Object { $_.code -eq $code }
    if (-not $stockInfo) {
        Write-Warning "[pigeon] $code : not in target_stocks config, skipping"
        continue
    }
    $name = $stockInfo.name

    Write-Host ""
    Write-Host "--- [$code $name] ---"
    $rawMessages = @()

    # Step 1: baostock[14] 业绩预告/快报
    Write-Host "[Step 1] baostock[14] forecast/express..."
    try {
        $baostockScript = Join-Path $projectRoot "代码文件\每日荐股\scripts\stock_data_fetcher_baostock.py"
        if (Test-Path $baostockScript) {
            $forecastResult = Invoke-BaostockForecast -StockCode $code -StockName $name -StartDate $startDate -EndDate $Date
            if ($forecastResult -and @($forecastResult).Count -gt 0) {
                $rawMessages += @($forecastResult)
                Write-Host "  forecast: $(@($forecastResult).Count) items"
            } else {
                Write-Host "  forecast: 0 items"
            }
        } else {
            Write-Warning "  baostock bridge not found, skipping"
        }
    } catch {
        Write-Warning "[Step 1] baostock failed: $($_.Exception.Message)"
        $sourceStatus["baostock"] = "failed"
    }

    # Step 2: cninfo API [16] 公司公告
    Write-Host "[Step 2] cninfo[16] announcements..."
    try {
        $cninfoResult = Invoke-CninfoAnnouncement -StockCode $code -StockName $name -StartDate $startDate -EndDate $Date
        if ($cninfoResult -and @($cninfoResult).Count -gt 0) {
            $rawMessages += @($cninfoResult)
            Write-Host "  cninfo: $(@($cninfoResult).Count) items"
            $sourceStatus["cninfo"] = "ok"
        } else {
            Write-Host "  cninfo: 0 items or failed"
            $sourceStatus["cninfo"] = "empty"

            # Step 4 (备源触发): cninfo失败 → china-stock-mcp[17]
            Write-Host "[Step 4] china-stock-mcp[17] backup..."
            $mcpResult = Invoke-CninfoAnnouncementBackup -StockCode $code -StockName $name
            if ($mcpResult -and $mcpResult.Count -gt 0) {
                $rawMessages += $mcpResult
                Write-Host "  mcp: $($mcpResult.Count) items"
                $sourceStatus["mcp"] = "ok"
            } else {
                Write-Host "  mcp: no data (cache only)"
                $sourceStatus["mcp"] = "empty"
            }
        }
    } catch {
        Write-Warning "[Step 2] cninfo failed: $($_.Exception.Message)"
        $sourceStatus["cninfo"] = "failed"
    }

    # Step 3: 东财研报[11] (已有1+2架构，此处简化——仅做研报新闻层面采集)
    Write-Host "[Step 3] 东方财富[11] research reports (news angle)..."
    try {
        $researchResult = Invoke-ResearchNewsOnly -StockCode $code -StockName $name -StartDate $startDate -EndDate $Date
        if ($researchResult -and @($researchResult).Count -gt 0) {
            $rawMessages += @($researchResult)
            Write-Host "  research: $(@($researchResult).Count) items"
        } else {
            Write-Host "  research: 0 items"
        }
    } catch {
        Write-Warning "[Step 3] research failed: $($_.Exception.Message)"
    }

    $totalRaw += $rawMessages.Count
    Write-Host "  >> raw total: $($rawMessages.Count) messages"

    # ============================================================
    # 五层过滤
    # ============================================================
    if ($SkipFilter) {
        Write-Host "[filter] SKIPPED [SkipFilter mode]"
        $allResults[$code] = @{
            events = $rawMessages
            stats  = @{ L1_in=$rawMessages.Count; L1_out=$rawMessages.Count;
                        L2_in=0; L2_out=0; L3_in=0; L3_out=0; L4_in=0; L4_out=$rawMessages.Count }
        }
    } else {
        $existingEvents = Get-ExistingEventsForDedup -StockCode $code
        if ($rawMessages.Count -eq 0) {
            Write-Host "[filter] $code : 0 messages, skipping filter"
            $allResults[$code] = @{
                events = @()
                stats  = @{ L1_in=0; L1_out=0; L2_in=0; L2_out=0; L3_in=0; L3_out=0; L4_in=0; L4_out=0 }
            }
        } else {
            $filterResult = Invoke-PigeonFilter -RawMessages $rawMessages -StockCode $code -StockName $name -ExistingEvents $existingEvents
            $allResults[$code] = $filterResult
        }
    }
}

# ============================================================
# 汇总输出
# ============================================================
Write-Host ""
Write-Host "============================================================"
Write-Host "[pigeon] 采集完成 — 汇总统计"
Write-Host "============================================================"

$totalFiltered = 0
$allStats = @{}

foreach ($code in $Stocks) {
    $result = $allResults[$code]
    if ($result) {
        $totalFiltered += $result.events.Count
        $allStats[$code] = $result.stats
        Write-Host "  $code : $($result.stats.L1_in) raw → $($result.stats.L4_out) filtered"
    }
}

# Step 5: WebFetch 行业政策 (仅周二/周五, Phase 2)
$dow = (Get-Date).DayOfWeek
$skipIndustryPolicy = $true
if ($dow -eq 'Tuesday' -or $dow -eq 'Friday') {
    Write-Host "[Step 5] Industry policy scan (Phase 2 placeholder — skipped)"
    # Phase 2: WebFetch 工信部/发改委
}

# 输出结果
Write-Host ""
Write-Host "[pigeon] Writing output..."

$outResult = Export-PigeonEventJson -FilteredEvents $allResults -FilterStats $allStats -OutputDir $OutputPath
Update-PigeonCache -OutputData $outResult -CacheDir $config.output.cache_dir

Write-Host ""
Write-Host "============================================================"
Write-Host "[pigeon] 完成: $totalRaw 条原始消息 → $totalFiltered 条入库"
Write-Host "[pigeon] 输出: $($outResult.date_file)"
Write-Host "[pigeon] 数据库: $($outResult.db_file)"
Write-Host "============================================================"

# 退出码
$allOk = $true
foreach ($code in $Stocks) {
    if ($sourceStatus["cninfo"] -eq "failed" -and $sourceStatus["mcp"] -eq "empty") {
        $allOk = $false
        break
    }
}

if ($allOk) {
    exit 0
} elseif ($totalFiltered -gt 0) {
    Write-Warning "[pigeon] 部分源失败，已降级 — 退出码 1"
    exit 1
} else {
    Write-Warning "[pigeon] 全部源失败，仅缓存兜底 — 退出码 2"
    exit 2
}
