# 依赖: dot-source "$PSScriptRoot/core.ps1"
# 最后更新: 2026-05-25 — 接入Invoke-DataSource统一降级引擎

function Get-NorthboundHold {
    param(
        [Parameter(Mandatory=$true)][string]$Code
    )
. "$PSScriptRoot/../../../lib/init_encoding.ps1"

    return Invoke-DataSource -Category "Northbound" `
        -CacheKey "Northbound_$Code" `
        -PrimaryName "东方财富[8]" `
        -PrimaryCall {
            $secucode = if ($Code.StartsWith("6")) { "${Code}.SH" } else { "${Code}.SZ" }
            $encoded = [System.Web.HttpUtility]::UrlEncode($secucode)
            $url = "https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_MUTUAL_HOLDSTOCKNORTH_STA&columns=ALL&filter=(SECUCODE=%22${encoded}%22)&pageSize=1&sortColumns=TRADE_DATE&sortTypes=-1"

            $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8 -Headers @{"User-Agent"="Mozilla/5.0"}
            $json = $r.Content | ConvertFrom-Json
            if ($json.result -and $json.result.data -and $json.result.data.Count -gt 0) {
                $d = $json.result.data[0]
                return [PSCustomObject]@{
                    Code          = $Code
                    Name          = $d.SECURITY_NAME
                    TradeDate     = $d.TRADE_DATE
                    HoldShares    = [long]$d.HOLD_SHARES
                    HoldMarketCap = [double]$d.HOLD_MARKET_CAP
                    SharesRatio   = [double]$d.HOLD_SHARES_RATIO
                    FreeRatio     = [double]$d.FREE_SHARES_RATIO
                }
            }
            return $null
        }
}

# ============================================================
# [THS-SB] 南向资金日频流向 — 补位北向[8]失效
# 主源: AKShare stock_hsgt_hist_em → 备源: stock_hsgt_fund_flow_summary_em
# 南向净流出=资金去港股(A股偏空)，南向净流入=资金回A股(A股偏多)
# ============================================================
function Get-SouthboundFlow {
    param([int]$Days = 5)

    $cacheKey = "SouthboundFlow_${Days}"
    $cached = Load-DataCache -Key $cacheKey -TTLHours 24
    if ($cached) {
        $script:SourceUsed["SouthboundFlow"] = "缓存[C]"
        return $cached
    }

    $bridgeScript = Join-Path $PSScriptRoot "..\stock_data_fetcher_ths.py"
    $pythonCmd = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $pythonCmd) { $pythonCmd = (Get-Command python3 -ErrorAction SilentlyContinue).Source }
    if (-not $pythonCmd) {
        Write-Warning "[南向资金] Python不可用"
        return $null
    }

    try {
        $result = & $pythonCmd $bridgeScript northbound_flow --direction south --days $Days 2>&1 | Out-String
        $data = $result | ConvertFrom-Json
        if ($data.data -and @($data.data).Count -gt 0) {
            $script:SourceUsed["SouthboundFlow"] = "AKShare[THS-SB]"
            Save-DataCache -Key $cacheKey -Data $data
            return $data
        }
    } catch {
        Write-Warning "[南向资金] THS桥接失败: $_"
    }

    $script:SourceUsed["SouthboundFlow"] = "失败"
    $staleCache = Load-DataCache -Key $cacheKey -TTLHours 168
    if ($staleCache) { Write-Warning "[南向资金] 使用过期缓存兜底"; return $staleCache }
    return $null
}
function Get-StockResearch {
    param(
        [Parameter(Mandatory=$true)][string]$Code,
        [int]$Count = 5,
        [string]$DaysBack = "30"
    )

    # 缓存优先 + 数量校验（引擎标准缓存不检查Count，此处前置处理）
    $cacheKey = "Research_${Code}_${Count}_${DaysBack}"
    $cached = Load-DataCache -Key $cacheKey -TTLHours 24
    if ($cached -and @($cached).Count -ge $Count) {
        $script:SourceUsed["Research"] = "缓存[C]"
        return $cached
    }

    return Invoke-DataSource -Category "Research" `
        -CacheKey $cacheKey `
        -PrimaryName "东方财富[11]" `
        -BackupName "同花顺[THS]" `
        -PrimaryCall {
            $endDate = (Get-Date).ToString("yyyy-MM-dd")
            $beginDate = (Get-Date).AddDays(-[int]$DaysBack).ToString("yyyy-MM-dd")
            $url = "https://reportapi.eastmoney.com/report/list?cb=&industryCode=*&pageSize=${Count}&industry=*&rating=*&ratingChange=*&beginTime=${beginDate}&endTime=${endDate}&pageNo=1&fields=&qType=0&code=${Code}&rcode="

            $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8 -Headers @{"User-Agent"="Mozilla/5.0"; "Referer"="https://data.eastmoney.com/report/"}
            $json = $r.Content | ConvertFrom-Json
            if ($json.data -and $json.data.Count -gt 0) {
                return ($json.data | ForEach-Object {
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
                })
            }
            return $null
        } `
        -BackupCall {
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
                return $result
            }
            return $null
        }
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

    # 缓存优先 + 数量校验
    $cacheKey = "Margin_${Code}_${Days}"
    $cached = Load-DataCache -Key $cacheKey -TTLHours 24
    if ($cached -and @($cached).Count -ge $Days) {
        $script:SourceUsed["Margin"] = "缓存[C]"
        return $cached
    }

    return Invoke-DataSource -Category "Margin" `
        -CacheKey $cacheKey `
        -PrimaryName "东方财富[12]" `
        -BackupName "同花顺[THS]" `
        -PrimaryCall {
            $url = "http://datacenter.eastmoney.com/api/data/get?type=RPTA_WEB_RZRQ_GGMX&sty=ALL&source=WEB&p=1&ps=${Days}&st=date&sr=-1&filter=(scode=%22${Code}%22)"

            $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8 -Headers @{"User-Agent"="Mozilla/5.0"; "Referer"="http://data.eastmoney.com/"}
            $json = $r.Content | ConvertFrom-Json
            if ($json.result -and $json.result.data -and $json.result.data.Count -gt 0) {
                return ($json.result.data | ForEach-Object {
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
                })
            }
            return $null
        } `
        -BackupCall {
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
                return $result
            }
            return $null
        }
}

# ============================================================
# 综合测试函数
# ============================================================
