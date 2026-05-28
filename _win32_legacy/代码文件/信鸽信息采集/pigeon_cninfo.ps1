# L0 — cninfo公告API封装
# 数据源[16] 巨潮资讯网公开JSON API — 上市公司公告全文检索
# 设计文档: 审计报告/架构设计/design_pigeon_info_collection_v1.0.md §三.2.2

function Invoke-CninfoAnnouncement {
    <#
    .SYNOPSIS
      从巨潮资讯网公开API获取上市公司公告列表
    .DESCRIPTION
      调用 cninfo.com.cn 全文检索接口，返回指定股票在日期范围内的公告。
      返回结构化JSON，无需HTML解析。主源[16]，备源china-stock-mcp[17]。
    .PARAMETER StockCode
      股票代码（6位数字，如 600114）
    .PARAMETER StockName
      股票名称（用于搜索关键词，如 东睦股份）
    .PARAMETER StartDate
      起始日期 yyyy-MM-dd
    .PARAMETER EndDate
      结束日期 yyyy-MM-dd
    .PARAMETER MaxResults
      最大返回条数，默认20
    #>
    param(
        [Parameter(Mandatory=$true)][string]$StockCode,
        [Parameter(Mandatory=$true)][string]$StockName,
        [Parameter(Mandatory=$true)][string]$StartDate,
        [Parameter(Mandatory=$true)][string]$EndDate,
        [int]$MaxResults = 20
    )

    $config = Get-PigeonConfig
    $baseUrl = $config.api.cninfo_base_url
    $timeout = $config.api.cninfo_timeout_sec
    $maxRetries = $config.api.cninfo_max_retries
    $intervalMs = $config.api.cninfo_interval_ms

    $searchKey = [System.Web.HttpUtility]::UrlEncode($StockName)
    $url = "${baseUrl}?searchkey=${searchKey}&sdate=${StartDate}&edate=${EndDate}&isfulltext=true&sortName=pubdate&sortType=desc&pageNum=1"

    $headers = @{
        "User-Agent" = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"
        "Accept" = "application/json"
        "Referer" = "http://www.cninfo.com.cn/new/fulltextSearch"
    }

    $attempt = 0
    $lastError = $null

    while ($attempt -lt $maxRetries) {
        try {
            Start-Sleep -Milliseconds $intervalMs
            $response = Invoke-RestMethod -Uri $url -Headers $headers -TimeoutSec $timeout -ErrorAction Stop

            if ($response -and $response.announcements) {
                $results = @()
                $count = [Math]::Min($response.announcements.Count, $MaxResults)
                for ($i = 0; $i -lt $count; $i++) {
                    $item = $response.announcements[$i]
                    $title = $item.announcementTitle -replace '<em>', '' -replace '</em>', ''
                    $contentText = if ($item.announcementContent) { $item.announcementContent -replace '<em>', '' -replace '</em>', '' } else { "" }

                    # 提取 announcementId（三级回退）
                    $annId = $null
                    if ($item.announcementId) {
                        $annId = "$($item.announcementId)"
                    } elseif ($item.announcementid) {
                        $annId = "$($item.announcementid)"
                    } elseif ($item.adjunctUrl -match '/(\d+)\.PDF$') {
                        $annId = $matches[1]
                    }
                    $cninfoUrl = if ($annId) {
                        "http://www.cninfo.com.cn/new/disclosure/detail?stockCode=$($item.secCode)&announcementId=$annId"
                    } else { $null }

                    $results += [PSCustomObject]@{
                        title           = $title
                        content         = $contentText
                        publish_time    = $item.announcementTime
                        pdf_url         = "http://static.cninfo.com.cn/" + $item.adjunctUrl
                        sec_name        = $item.secName
                        sec_code        = $item.secCode
                        source          = "cninfo"
                        source_type     = "primary"
                        announcement_id = $annId
                        cninfo_url      = $cninfoUrl
                    }
                }
                Write-Host "[cninfo] $StockCode $StockName : $(@($results).Count) announcements fetched"
                return @($results)
            }
            else {
                Write-Host "[cninfo] $StockCode $StockName : 0 announcements (empty response)"
                return @()
            }
        }
        catch {
            $lastError = $_
            $attempt++
            if ($attempt -lt $maxRetries) {
                $backoff = [Math]::Pow(2, $attempt)
                Write-Warning "[cninfo] $StockCode retry $attempt/$maxRetries after ${backoff}s: $($_.Exception.Message)"
                Start-Sleep -Seconds $backoff
            }
        }
    }

    Write-Warning "[cninfo] $StockCode FAILED after $maxRetries attempts: $($lastError.Exception.Message)"
    Write-Warning "[cninfo] $StockCode : falling back to china-stock-mcp[17]"
    return $null
}

function Invoke-CninfoAnnouncementBackup {
    <#
    .SYNOPSIS
      备源[17] — 通过china-stock-mcp获取个股新闻（cninfo主源失败时触发）
    #>
    param(
        [Parameter(Mandatory=$true)][string]$StockCode,
        [Parameter(Mandatory=$true)][string]$StockName,
        [int]$MaxResults = 20
    )

    Write-Host "[china-stock-mcp] $StockCode : attempting backup fetch via MCP..."
    Write-Warning "[china-stock-mcp] MCP备源暂未集成 — 返回空，使用缓存[C]兜底"
    return @()
}

function Get-PigeonConfig {
    <#
    .SYNOPSIS
      加载信鸽配置文件
    #>
    $configPath = Join-Path $PSScriptRoot "pigeon_config.json"
    if (-not (Test-Path $configPath)) {
        throw "Pigeon config not found: $configPath"
    }
    $content = Get-Content -Path $configPath -Raw -Encoding UTF8
    return $content | ConvertFrom-Json
}
