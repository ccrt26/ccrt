# 依赖: dot-source "$PSScriptRoot/core.ps1"

function Get-StockFundFlow {
    param([Parameter(Mandatory=$true)][string]$Code, [int]$Days = 5)

    # --- 缓存优先（资金流向盘后固定，Tier 2）---
    $cached = Load-DataCache -Key "FundFlow_${Code}_${Days}" -TTLHours 24
    if ($cached -and @($cached).Count -ge $Days) {
        $script:SourceUsed["FundFlow"] = "缓存"
        return $cached
    }

    $market = if ($Code.StartsWith("6")) { "1" } else { "0" }
    $url = "http://push2.eastmoney.com/api/qt/stock/fflow/daykline/get?cb=&secid=${market}.${Code}&fields1=f1,f2,f3,f4,f5,f6,f7&fields2=f51,f52,f53,f54,f55&lmt=${Days}"
    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8 -Headers @{"User-Agent"="Mozilla/5.0"}
        $json = $r.Content | ConvertFrom-Json
        $result = @()
        if ($json.data -and $json.data.klines) {
            foreach ($kline in $json.data.klines) {
                $parts = $kline -split ','
                $result += [PSCustomObject]@{
                    Date        = $parts[0]
                    MainNetInflow  = [double]$parts[1]
                    SuperLargeIn   = [double]$parts[2]
                    LargeIn        = [double]$parts[3]
                    SmallIn        = [double]$parts[4]
                }
            }
            $script:SourceUsed["FundFlow"] = "东方财富"
            Save-DataCache -Key "FundFlow_${Code}_${Days}" -Data $result
            return $result
        }
    } catch {
        Write-Warning "Get-StockFundFlow failed for $Code : $_"
    }
    $script:SourceUsed["FundFlow"] = "失败"
    # 过期缓存兜底（API双源均失败时的最后手段）
    $staleCache = Load-DataCache -Key "FundFlow_${Code}_${Days}" -TTLHours 720
    if ($staleCache) { Write-Warning "[资金流向] API双源失败，使用过期缓存兜底"; return $staleCache }
    return $null
}

# ============================================================
# [10] 行业资金流向
# ============================================================
function Get-SectorFundFlow {
    param([int]$Top = 10)
    $url = "http://push2.eastmoney.com/api/qt/clist/get?cb=&pn=1&pz=${Top}&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f62&fs=m:90+t:2&fields=f12,f14,f62,f184,f66,f69"
    try {
        $r = Invoke-ThrottledApiCall { Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8 -Headers @{"User-Agent"="Mozilla/5.0"} }
        $json = $r.Content | ConvertFrom-Json
        if ($json.data -and $json.data.diff) {
            $result = $json.data.diff | ForEach-Object {
                [PSCustomObject]@{
                    SectorCode  = $_.f12
                    SectorName  = $_.f14
                    NetInflow   = [double]$_.f62
                    MainInflow  = [double]$_.f66
                    ChangePct   = [double]$_.f184
                    TurnRate    = [double]$_.f69
                }
            }
            $script:SourceUsed["SectorFundFlow"] = "东方财富"
            Save-DataCache -Key "SectorFundFlow_$Top" -Data $result
            return $result
        }
    } catch {
        Write-Warning "Get-SectorFundFlow failed: $_"
        # 尝试同花顺 THS 备份
        Write-Warning "[行业资金] 尝试同花顺 THS 备份..."
        $thsResult = Invoke-ThsFallback -Action "sector_fund_flow" -Params "--top $Top"
        if ($thsResult) {
            $script:SourceUsed["SectorFundFlow"] = "同花顺"
            Save-DataCache -Key "SectorFundFlow_$Top" -Data $thsResult
            return $thsResult
        }
    }
    $script:SourceUsed["SectorFundFlow"] = "失败"
    $cached = Load-DataCache -Key "SectorFundFlow_$Top" -TTLHours 6
    if ($cached) { Write-Warning "[行业资金] API失败，使用缓存"; return $cached }
    return $null
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
# [8] 北向资金持股（季度）
# API: datacenter-web.eastmoney.com RPT_MUTUAL_HOLDSTOCKNORTH_STA
# 返回：北向资金持股数量/市值/占总股本比例
# ============================================================