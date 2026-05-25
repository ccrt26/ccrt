# 依赖: dot-source "$PSScriptRoot/core.ps1"

function Get-NorthboundHold {
    param(
        [Parameter(Mandatory=$true)][string]$Code
    )

    # --- 缓存优先（北向资金日频更新，Tier 2）---
    $cached = Load-DataCache -Key "Northbound_$Code" -TTLHours 24
    if ($cached) {
        $script:SourceUsed["Northbound"] = "缓存"
        return $cached
    }

    $secucode = if ($Code.StartsWith("6")) { "${Code}.SH" } else { "${Code}.SZ" }
    $encoded = [System.Web.HttpUtility]::UrlEncode($secucode)
    $url = "https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_MUTUAL_HOLDSTOCKNORTH_STA&columns=ALL&filter=(SECUCODE=%22${encoded}%22)&pageSize=1&sortColumns=TRADE_DATE&sortTypes=-1"

    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8 -Headers @{"User-Agent"="Mozilla/5.0"}
        $json = $r.Content | ConvertFrom-Json
        if ($json.result -and $json.result.data -and $json.result.data.Count -gt 0) {
            $d = $json.result.data[0]
            $result = [PSCustomObject]@{
                Code          = $Code
                Name          = $d.SECURITY_NAME
                TradeDate     = $d.TRADE_DATE
                HoldShares    = [long]$d.HOLD_SHARES
                HoldMarketCap = [double]$d.HOLD_MARKET_CAP
                SharesRatio   = [double]$d.HOLD_SHARES_RATIO
                FreeRatio     = [double]$d.FREE_SHARES_RATIO
            }
            $script:SourceUsed["Northbound"] = "东方财富"
            Save-DataCache -Key "Northbound_$Code" -Data $result
            return $result
        }
    } catch {
        Write-Warning "Get-NorthboundHold failed for $Code : $_"
    }
    $script:SourceUsed["Northbound"] = "失败"
    # 过期缓存兜底（API双源均失败时的最后手段）
    $staleCache = Load-DataCache -Key "Northbound_$Code" -TTLHours 720
    if ($staleCache) { Write-Warning "[北向资金] API双源失败，使用过期缓存兜底"; return $staleCache }
    return $null
}

# ============================================================
# [11] 个股研报/分析师评级
# API: reportapi.eastmoney.com
# ============================================================
function Get-StockResearch {
    param(
        [Parameter(Mandatory=$true)][string]$Code,
        [int]$Count = 5,
        [string]$DaysBack = "30"
    )

    # --- 缓存优先（研报日频更新，Tier 2）---
    $cached = Load-DataCache -Key "Research_${Code}_${Count}_${DaysBack}" -TTLHours 24
    if ($cached -and @($cached).Count -ge $Count) {
        $script:SourceUsed["Research"] = "缓存"
        return $cached
    }

    $endDate = (Get-Date).ToString("yyyy-MM-dd")
    $beginDate = (Get-Date).AddDays(-[int]$DaysBack).ToString("yyyy-MM-dd")
    $url = "https://reportapi.eastmoney.com/report/list?cb=&industryCode=*&pageSize=${Count}&industry=*&rating=*&ratingChange=*&beginTime=${beginDate}&endTime=${endDate}&pageNo=1&fields=&qType=0&code=${Code}&rcode="

    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8 -Headers @{"User-Agent"="Mozilla/5.0"; "Referer"="https://data.eastmoney.com/report/"}
        $json = $r.Content | ConvertFrom-Json
        if ($json.data -and $json.data.Count -gt 0) {
            $result = $json.data | ForEach-Object {
                [PSCustomObject]@{
                    Title         = $_.title
                    OrgName       = $_.orgSName
                    PublishDate   = $_.publishDate
                    EmRating      = $_.emRatingName
                    LastRating    = $_.lastEmRatingName
                    ThisYearEPS   = [double]$_.predictThisYearEps
                    NextYearEPS   = [double]$_.predictNextYearEps
                    ThisYearPE    = [double]$_.predictThisYearPe
                    NextYearPE    = [double]$_.predictNextYearPe
                    Author        = $_.author
                }
            }
            $script:SourceUsed["Research"] = "东方财富"
            Save-DataCache -Key "Research_${Code}_${Count}_${DaysBack}" -Data $result
            return $result
        }
    } catch {
        Write-Warning "Get-StockResearch failed for $Code : $_"
    }

    # [THS] AKShare盈利预测备源（同花顺，EPS预测+机构+报告日期）
    Write-Warning "[研报] 尝试AKShare盈利预测备源..."
    $forecastResult = Invoke-ThsFallback -Action "profit_forecast" -Params "--code $Code"
    if ($forecastResult -and $forecastResult.Count -gt 0) {
        $result = $forecastResult | Select-Object -First $Count | ForEach-Object {
            $thisYearEPS = $null
            try { $thisYearEPS = [double]$_.'预测年报每股收益2026预测' } catch {}
            $nextYearEPS = $null
            try { $nextYearEPS = [double]$_.'预测年报每股收益2027预测' } catch {}

            [PSCustomObject]@{
                Title         = "备源-盈利预测"
                OrgName       = $_.'机构名称'
                PublishDate   = $_.'报告日期'
                EmRating      = "备源(同花顺)"
                LastRating    = ""
                ThisYearEPS   = $thisYearEPS
                NextYearEPS   = $nextYearEPS
                ThisYearPE    = $null
                NextYearPE    = $null
                Author        = $_.'研究员'
            }
        }
        $script:SourceUsed["Research"] = "同花顺[THS]"
        Save-DataCache -Key "Research_${Code}_${Count}_${DaysBack}" -Data $result
        return $result
    }

    $script:SourceUsed["Research"] = "失败"
    # 过期缓存兜底（API双源均失败时的最后手段）
    $staleCache = Load-DataCache -Key "Research_${Code}_${Count}_${DaysBack}" -TTLHours 720
    if ($staleCache) { Write-Warning "[研报] API双源失败，使用过期缓存兜底"; return $staleCache }
    return $null
}

# ============================================================
# [12] 融资融券（个股）
# API: datacenter.eastmoney.com RPTA_WEB_RZRQ_GGMX
# ============================================================
function Get-MarginData {
    param(
        [Parameter(Mandatory=$true)][string]$Code,
        [int]$Days = 5
    )

    # --- 缓存优先（融资融券日频更新，Tier 2）---
    $cached = Load-DataCache -Key "Margin_${Code}_${Days}" -TTLHours 24
    if ($cached -and @($cached).Count -ge $Days) {
        $script:SourceUsed["Margin"] = "缓存"
        return $cached
    }

    $url = "http://datacenter.eastmoney.com/api/data/get?type=RPTA_WEB_RZRQ_GGMX&sty=ALL&source=WEB&p=1&ps=${Days}&st=date&sr=-1&filter=(scode=%22${Code}%22)"

    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8 -Headers @{"User-Agent"="Mozilla/5.0"; "Referer"="http://data.eastmoney.com/"}
        $json = $r.Content | ConvertFrom-Json
        if ($json.result -and $json.result.data -and $json.result.data.Count -gt 0) {
            $result = $json.result.data | ForEach-Object {
                [PSCustomObject]@{
                    Date          = $_.DATE
                    RZYE          = [double]$_.RZYE
                    RQYE          = [double]$_.RQYE
                    RZRQYE        = [double]$_.RZRQYE
                    RZMRE         = [double]$_.RZMRE
                    RZCHE         = [double]$_.RZCHE
                    RZJME         = [double]$_.RZJME
                    RQYL          = [double]$_.RQYL
                    RQMCL         = [double]$_.RQMCL
                }
            }
            $script:SourceUsed["Margin"] = "东方财富"
            Save-DataCache -Key "Margin_${Code}_${Days}" -Data $result
            return $result
        }
    } catch {
        Write-Warning "Get-MarginData failed for $Code : $_"
    }

    # [THS] AKShare融资融券备源（上交所/深交所官方数据）
    Write-Warning "[融资融券] 尝试AKShare备源..."
    $marginResult = Invoke-ThsFallback -Action "margin_detail" -Params "--code $Code --days $Days"
    if ($marginResult -and $marginResult.Count -gt 0) {
        $result = $marginResult | ForEach-Object {
            [PSCustomObject]@{
                Date          = $_.DATE
                RZYE          = [double]$_.RZYE
                RQYE          = [double]$_.RQYE
                RZRQYE        = [double]$_.RZRQYE
                RZMRE         = [double]$_.RZMRE
                RZCHE         = [double]$_.RZCHE
                RZJME         = [double]$_.RZJME
                RQYL          = [double]$_.RQYL
                RQMCL         = [double]$_.RQMCL
            }
        }
        $script:SourceUsed["Margin"] = "同花顺[THS]"
        Save-DataCache -Key "Margin_${Code}_${Days}" -Data $result
        return $result
    }

    $script:SourceUsed["Margin"] = "失败"
    # 过期缓存兜底（API双源均失败时的最后手段）
    $staleCache = Load-DataCache -Key "Margin_${Code}_${Days}" -TTLHours 720
    if ($staleCache) { Write-Warning "[融资融券] API双源失败，使用过期缓存兜底"; return $staleCache }
    return $null
}

# ============================================================
# 综合测试函数
# ============================================================