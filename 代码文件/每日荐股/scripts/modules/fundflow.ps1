# 依赖: dot-source "$PSScriptRoot/core.ps1"
# 最后更新: 2026-05-25 — 接入Invoke-DataSource统一降级引擎

function Get-StockFundFlow {
    param([Parameter(Mandatory=$true)][string]$Code, [int]$Days = 5)
. "$PSScriptRoot/../../../lib/init_encoding.ps1"

    # 缓存优先 + 数量校验
    $cacheKey = "FundFlow_${Code}_${Days}"
    $cached = Load-DataCache -Key $cacheKey -TTLHours 24
    if ($cached -and @($cached).Count -ge $Days) {
        $script:SourceUsed["FundFlow"] = "缓存[C]"
        return $cached
    }

    return Invoke-DataSource -Category "FundFlow" `
        -CacheKey $cacheKey `
        -PrimaryName "东方财富[9]" `
        -PrimaryCall {
            $market = if ($Code.StartsWith("6")) { "1" } else { "0" }
            $url = "http://push2.eastmoney.com/api/qt/stock/fflow/daykline/get?cb=&secid=${market}.${Code}&fields1=f1,f2,f3,f4,f5,f6,f7&fields2=f51,f52,f53,f54,f55&lmt=${Days}"

            $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8 -Headers @{"User-Agent"="Mozilla/5.0"}
            $json = $r.Content | ConvertFrom-Json
            $result = @()
            if ($json.data -and $json.data.klines) {
                foreach ($kline in $json.data.klines) {
                    $parts = $kline -split ','
                    $result += [PSCustomObject]@{
                        Date          = $parts[0]
                        MainNetInflow = [double]$parts[1]
                        SuperLargeIn  = [double]$parts[2]
                        LargeIn       = [double]$parts[3]
                        SmallIn       = [double]$parts[4]
                    }
                }
                return $result
            }
            return $null
        } `
        -BackupName "同花顺[THS]" `
        -BackupCall {
            Write-Warning "[资金流] 东方财富[9]失败，尝试同花顺THS备源..."
            $thsResult = Invoke-ThsFallback -Action "stock_fund_flow" -Params "--code $Code --days $Days"
            if ($thsResult -and $thsResult.Count -gt 0) {
                $script:SourceUsed["FundFlow"] = "同花顺[THS]"
                return $thsResult
            }
            Write-Warning "[资金流] THS个股资金流不可用（可能仅支持行业级）"
            return $null
        }
}

# ============================================================
# [10] 行业资金流向
# ============================================================
function Get-SectorFundFlow {
    param([int]$Top = 10)

    return Invoke-DataSource -Category "SectorFundFlow" `
        -CacheKey "SectorFundFlow_$Top" `
        -PrimaryName "东方财富[10]" `
        -BackupName "同花顺[THS]" `
        -CacheTTLOverride 0 `
        -PrimaryCall {
            $url = "http://push2.eastmoney.com/api/qt/clist/get?cb=&pn=1&pz=${Top}&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f62&fs=m:90+t:2&fields=f12,f14,f62,f184,f66,f69"

            $r = Invoke-ThrottledApiCall { Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8 -Headers @{"User-Agent"="Mozilla/5.0"} }
            $json = $r.Content | ConvertFrom-Json
            if ($json.data -and $json.data.diff) {
                return ($json.data.diff | ForEach-Object {
                    [PSCustomObject]@{
                        SectorCode  = $_.f12
                        SectorName  = $_.f14
                        NetInflow   = [double]$_.f62
                        MainInflow  = [double]$_.f66
                        ChangePct   = [double]$_.f184
                        TurnRate    = [double]$_.f69
                    }
                })
            }
            return $null
        } `
        -BackupCall {
            Write-Warning "[行业资金] 尝试同花顺 THS 备份..."
            $thsResult = Invoke-ThsFallback -Action "sector_fund_flow" -Params "--top $Top"
            if ($thsResult) {
                $script:SourceUsed["SectorFundFlow"] = "同花顺[THS]"
                return $thsResult
            }
            return $null
        }
}

# ============================================================
# PE百分位计算（基于历史K线 + EPS数据）
# ============================================================
function Get-PEPercentile {
    param(
        [Parameter(Mandatory=$true)][string]$Code,
        [int]$LookbackYears = 5
    )
    $cached = Load-DataCache -Key "PEPercentile_$Code" -TTLHours 168
    if ($cached) { $script:SourceUsed["PEPercentile"] = "缓存"; return $cached }
    # 获取历史K线
    $tradingDays = $LookbackYears * 252  # 约252交易日/年
    $klines = Get-StockKLine -Code $Code -Scale "240" -Count $tradingDays
    if (-not $klines -or $klines.Count -lt 60) { return $null }

    # 获取最近EPS
    $fin = Get-StockFinancial -Code $Code -Quarters 4
    if (-not $fin -or $fin.Count -eq 0) { return $null }

    # 计算TTM EPS
    $epsValues = $fin | ForEach-Object { [double]$_.BASIC_EPS }
    $ttmEps = ($epsValues | Measure-Object -Average).Average
    if ($ttmEps -le 0) { return $null }

    # 计算历史PE
    $peHistory = $klines | ForEach-Object { if ($ttmEps -gt 0) { [math]::Round([double]$_.Close / $ttmEps, 2) } else { $null } }
    $peHistory = $peHistory | Where-Object { $_ -ne $null -and $_ -gt 0 -and $_ -lt 1000 }
    if ($peHistory.Count -lt 20) { return $null }

    # 当前PE
    $currentPE = $peHistory[-1]

    # 排序计算百分位
    $sorted = $peHistory | Sort-Object
    $rank = [array]::IndexOf($sorted, $currentPE)
    if ($rank -lt 0) {
        # Find insertion position
        for ($i = 0; $i -lt $sorted.Count; $i++) { if ($currentPE -le $sorted[$i]) { $rank = $i; break } }
    }
    $percentile = [math]::Round($rank / $sorted.Count * 100, 1)
    $minPE = $sorted[0]; $maxPE = $sorted[-1]; $avgPE = [math]::Round(($sorted | Measure-Object -Average).Average, 2)

    $result = [PSCustomObject]@{
        CurrentPE  = $currentPE
        MinPE      = $minPE
        MaxPE      = $maxPE
        AvgPE      = $avgPE
        Percentile = $percentile
        SampleCount = $peHistory.Count
        Valuation  = if ($percentile -lt 30) { "低估" } elseif ($percentile -gt 70) { "高估" } else { "合理" }
    }
    Save-DataCache -Key "PEPercentile_$Code" -Data $result
    return $result
}

# ============================================================
# [8] 北向资金持股明细
# API: datacenter.eastmoney.com RPT_MUTUAL_HOLDSTOCKNORTH_STA
# 返回：北向资金持股数量/市值/占总股本比例 (日频)
# ============================================================
function Get-NorthboundDetail {
    param([Parameter(Mandatory=$true)][string]$Code)

    $cached = Load-DataCache -Key "NorthboundDetail_${Code}" -TTLHours 24
    if ($cached) {
        $script:SourceUsed["NorthboundDetail"] = "缓存[C]"
        return $cached
    }

    $secucode = if ($Code.StartsWith("6")) { "${Code}.SH" } else { "${Code}.SZ" }
    $encoded = [System.Web.HttpUtility]::UrlEncode($secucode)
    $url = "http://datacenter.eastmoney.com/api/data/v1/get?reportName=RPT_MUTUAL_HOLDSTOCKNORTH_STA&columns=ALL&filter=(SECUCODE=%22${encoded}%22)&pageSize=5&sortColumns=TRADE_DATE&sortTypes=-1"

    try {
        $r = Invoke-ThrottledApiCall { Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8 -Headers @{"User-Agent"="Mozilla/5.0"} }
        $json = $r.Content | ConvertFrom-Json
        if (-not $json.result -or -not $json.result.data -or $json.result.data.Count -eq 0) { return $null }

        $data = $json.result.data
        $latest = $data[0]
        $result = [PSCustomObject]@{
            TradeDate         = $latest.TRADE_DATE
            HoldShares        = [double]$latest.HOLD_SHARES
            HoldMktCap        = [double]$latest.HOLD_MARKET_CAP
            HoldRatio         = [double]$latest.HOLD_RATIO
            FreeHoldRatio     = if ($latest.PSObject.Properties.Name -contains 'FREE_HOLD_RATIO') { [double]$latest.FREE_HOLD_RATIO } else { $null }
            Change1W          = if ($data.Count -ge 5) { [math]::Round(([double]$data[0].HOLD_SHARES - [double]$data[4].HOLD_SHARES) / [double]$data[4].HOLD_SHARES * 100, 2) } else { $null }
            Source            = "东方财富"
        }
        $script:SourceUsed["NorthboundDetail"] = "东方财富"
        Save-DataCache -Key "NorthboundDetail_${Code}" -Data $result
        return $result
    } catch {
        Write-Warning "Get-NorthboundDetail failed for $Code : $_"
    }
    $script:SourceUsed["NorthboundDetail"] = "失败"
    $staleCache = Load-DataCache -Key "NorthboundDetail_${Code}" -TTLHours 720
    if ($staleCache) { Write-Warning "[北向资金] API失败，使用过期缓存兜底"; return $staleCache }
    return $null
}

# ============================================================
# [11] 龙虎榜数据
# API: datacenter.eastmoney.com RPT_DAILY_BILLBOARD_DETAILS
# 注意：无免费备源API，标注"仅供参考"
# ============================================================
function Get-BillboardDetail {
    param(
        [Parameter(Mandatory=$true)][string]$Code,
        [int]$Days = 20
    )

    $cached = Load-DataCache -Key "Billboard_${Code}" -TTLHours 24
    if ($cached) {
        $script:SourceUsed["Billboard"] = "缓存[C]"
        return $cached
    }

    $secucode = if ($Code.StartsWith("6")) { "${Code}.SH" } else { "${Code}.SZ" }
    $encoded = [System.Web.HttpUtility]::UrlEncode($secucode)
    $startDate = (Get-Date).AddDays(-$Days).ToString("yyyy-MM-dd")
    $url = "http://datacenter.eastmoney.com/api/data/v1/get?reportName=RPT_DAILY_BILLBOARD_DETAILS&columns=ALL&filter=(SECUCODE=%22${encoded}%22)(TRADE_DATE%3E=%27${startDate}%27)&pageSize=20&sortColumns=TRADE_DATE&sortTypes=-1"

    try {
        $r = Invoke-ThrottledApiCall { Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8 -Headers @{"User-Agent"="Mozilla/5.0"} }
        $json = $r.Content | ConvertFrom-Json
        if (-not $json.result -or -not $json.result.data -or $json.result.data.Count -eq 0) {
            $result = @()  # 近期无上榜，正常情况
        } else {
            $result = $json.result.data | ForEach-Object {
                [PSCustomObject]@{
                    TradeDate    = $_.TRADE_DATE
                    SecuName     = $_.SECUNAME
                    BuyAmount    = if ($_.BUY_AMOUNT) { [double]$_.BUY_AMOUNT } else { $null }
                    SellAmount   = if ($_.SELL_AMOUNT) { [double]$_.SELL_AMOUNT } else { $null }
                    NetAmount    = if ($_.NET_AMOUNT) { [double]$_.NET_AMOUNT } else { $null }
                    Reason       = $_.BILLBOARD_REASON
                    ChangePct3D  = if ($_.PSObject.Properties.Name -contains 'CHANGE_3D') { [double]$_.CHANGE_3D } else { $null }
                }
            }
        }
        $script:SourceUsed["Billboard"] = "东方财富(仅供参考)"
        Save-DataCache -Key "Billboard_${Code}" -Data $result
        return $result
    } catch {
        Write-Warning "Get-BillboardDetail failed for $Code : $_"
    }
    $script:SourceUsed["Billboard"] = "失败"
    $staleCache = Load-DataCache -Key "Billboard_${Code}" -TTLHours 720
    if ($staleCache) { Write-Warning "[龙虎榜] API失败，使用过期缓存兜底"; return $staleCache }
    return @()
}

# ============================================================
# [13] 机构调研记录
# API: datacenter.eastmoney.com RPT_ORG_INVESTIGATION
# 注意：无免费备源API，标注"仅供参考"
# ============================================================
function Get-InstitutionVisit {
    param(
        [Parameter(Mandatory=$true)][string]$Code,
        [int]$Count = 5
    )

    $cached = Load-DataCache -Key "InstitutionVisit_${Code}" -TTLHours 24
    if ($cached) {
        $script:SourceUsed["InstitutionVisit"] = "缓存[C]"
        return $cached
    }

    $secucode = if ($Code.StartsWith("6")) { "${Code}.SH" } else { "${Code}.SZ" }
    $encoded = [System.Web.HttpUtility]::UrlEncode($secucode)
    $url = "http://datacenter.eastmoney.com/api/data/v1/get?reportName=RPT_ORG_INVESTIGATION&columns=ALL&filter=(SECUCODE=%22${encoded}%22)&pageSize=${Count}&sortColumns=VISIT_DATE&sortTypes=-1"

    try {
        $r = Invoke-ThrottledApiCall { Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8 -Headers @{"User-Agent"="Mozilla/5.0"} }
        $json = $r.Content | ConvertFrom-Json
        if (-not $json.result -or -not $json.result.data -or $json.result.data.Count -eq 0) {
            $result = @()
        } else {
            $result = $json.result.data | ForEach-Object {
                [PSCustomObject]@{
                    VisitDate     = $_.VISIT_DATE
                    OrgCount      = if ($_.ORG_COUNT) { [int]$_.ORG_COUNT } else { $null }
                    OrgTypes      = $_.ORG_TYPES
                    ContentSummary = if ($_.CONTENT_SUMMARY) { $_.CONTENT_SUMMARY.Substring(0, [math]::Min(200, $_.CONTENT_SUMMARY.Length)) } else { "" }
                    SurveyType    = $_.SURVEY_TYPE
                }
            }
        }
        $script:SourceUsed["InstitutionVisit"] = "东方财富(仅供参考)"
        Save-DataCache -Key "InstitutionVisit_${Code}" -Data $result
        return $result
    } catch {
        Write-Warning "Get-InstitutionVisit failed for $Code : $_"
    }
    $script:SourceUsed["InstitutionVisit"] = "失败"
    $staleCache = Load-DataCache -Key "InstitutionVisit_${Code}" -TTLHours 720
    if ($staleCache) { Write-Warning "[机构调研] API失败，使用过期缓存兜底"; return $staleCache }
    return @()
}
