# 铁律量化 - 股票数据获取模块
# 数据源：腾讯行情[1], 新浪K线[2], 东方财富财务[3][6][7][9][10]
# 最后更新：2026-05-21
# 合规状态：详见 §1.5 数据源实测状态

# ============================================================
# [1] 腾讯实时行情
# API: qt.gtimg.cn
# 返回：实时报价（当前价/涨跌幅/量比/换手率/PE/市值等）
# ============================================================
function Get-StockQuote {
    param(
        [Parameter(Mandatory=$true)][string]$Code  # e.g. "600036" or "000858"
    )
    # Determine prefix: 6xxxxx → sh, 0xxxxx/3xxxxx → sz
    $prefix = if ($Code.StartsWith("6")) { "sh" } else { "sz" }
    $url = "http://qt.gtimg.cn/q=${prefix}${Code}"

    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 5
        $raw = $r.Content.Trim()
        # Parse pipe-delimited response
        if ($raw -match '"(.*)"') {
            $fields = $matches[1] -split '~'
            return [PSCustomObject]@{
                Code       = $fields[2]
                Name       = $fields[1]
                Price      = [double]$fields[3]
                PrevClose  = [double]$fields[4]
                Open       = [double]$fields[5]
                Volume     = [long]$fields[6]  # 手
                Turnover   = [double]$fields[37]  # 成交额(万)
                High       = [double]$fields[33]
                Low        = [double]$fields[34]
                Change     = [double]$fields[31]
                ChangePct  = [double]$fields[32]
                PE         = [double]$fields[39]
                TurnoverRate = [double]$fields[38]  # 换手率(%)
                MktCap     = [double]$fields[44]  # 流通市值(亿)
                Amplitude  = [double]$fields[43]  # 振幅(%)
                Time       = $fields[30]
            }
        }
    } catch {
        Write-Warning "Get-StockQuote failed for $Code : $_"
        return $null
    }
}

# ============================================================
# [2] 新浪K线数据
# API: money.finance.sina.com.cn
# 参数: scale=240(日), 60(60min), 30(30min), 15(15min), 5(5min)
# ============================================================
function Get-StockKLine {
    param(
        [Parameter(Mandatory=$true)][string]$Code,
        [string]$Scale = "240",  # 240=daily
        [int]$Count = 120
    )
    $prefix = if ($Code.StartsWith("6")) { "sh" } else { "sz" }
    $url = "http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol=${prefix}${Code}&scale=${Scale}&ma=5&datalen=${Count}"

    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8 -Headers @{"User-Agent"="Mozilla/5.0"}
        $json = $r.Content | ConvertFrom-Json
        return $json | ForEach-Object {
            [PSCustomObject]@{
                Date   = $_.day
                Open   = [double]$_.open
                High   = [double]$_.high
                Low    = [double]$_.low
                Close  = [double]$_.close
                Volume = [long]$_.volume
            }
        }
    } catch {
        Write-Warning "Get-StockKLine failed for $Code : $_"
        return $null
    }
}

# ============================================================
# [3] 东方财富财务数据
# API: datacenter.eastmoney.com
# 返回：EPS/ROE/营收/净利润/毛利率等74个字段
# ============================================================
function Get-StockFinancial {
    param(
        [Parameter(Mandatory=$true)][string]$Code,
        [int]$Quarters = 4  # 返回最近N个季度
    )
    $secucode = if ($Code.StartsWith("6")) { "${Code}.SH" } else { "${Code}.SZ" }
    $encoded = [System.Web.HttpUtility]::UrlEncode($secucode)
    $url = "http://datacenter.eastmoney.com/api/data/v1/get?reportName=RPT_LICO_FN_CPD&columns=ALL&filter=(SECUCODE=%22${encoded}%22)&pageSize=${Quarters}&sortColumns=NOTICE_DATE&sortTypes=-1"

    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8 -Headers @{"User-Agent"="Mozilla/5.0"}
        $json = $r.Content | ConvertFrom-Json
        return $json.result.data
    } catch {
        Write-Warning "Get-StockFinancial failed for $Code : $_"
        return $null
    }
}

# ============================================================
# [5] 技术指标计算
# ============================================================
function Calc-MovingAverage {
    param([array]$Data, [string]$Field = "Close", [int]$Period = 5)
    $values = $Data | ForEach-Object { [double]$_.$Field }
    $result = @()
    for ($i = 0; $i -lt $values.Count; $i++) {
        if ($i -lt $Period - 1) { $result += $null; continue }
        $sum = 0
        for ($j = 0; $j -lt $Period; $j++) { $sum += $values[$i - $j] }
        $result += [math]::Round($sum / $Period, 2)
    }
    return $result
}

function Calc-RSI {
    param([array]$Data, [int]$Period = 14)
    $values = $Data | ForEach-Object { [double]$_.Close }
    $result = @()
    for ($i = 0; $i -lt $values.Count; $i++) {
        if ($i -lt $Period) { $result += $null; continue }
        $gains = 0; $losses = 0
        for ($j = $i - $Period + 1; $j -le $i; $j++) {
            $diff = $values[$j] - $values[$j-1]
            if ($diff -gt 0) { $gains += $diff } else { $losses -= $diff }
        }
        $avgGain = $gains / $Period
        $avgLoss = $losses / $Period
        if ($avgLoss -eq 0) { $result += 100 } else { $result += [math]::Round(100 - (100 / (1 + $avgGain/$avgLoss)), 2) }
    }
    return $result
}

function Calc-MACD {
    param([array]$Data, [int]$Fast = 12, [int]$Slow = 26, [int]$Signal = 9)
    $values = $Data | ForEach-Object { [double]$_.Close }
    # EMA calculation
    function Get-EMA($vals, $n) {
        $ema = @(); $k = 2.0 / ($n + 1)
        for ($i = 0; $i -lt $vals.Count; $i++) {
            if ($i -eq 0) { $ema += $vals[$i] }
            else { $ema += $vals[$i] * $k + $ema[-1] * (1 - $k) }
        }
        return $ema
    }
    $emaFast = Get-EMA $values $Fast
    $emaSlow = Get-EMA $values $Slow
    $dif = @(); for ($i = 0; $i -lt $values.Count; $i++) { $dif += $emaFast[$i] - $emaSlow[$i] }
    $dea = Get-EMA $dif $Signal
    $macd = @(); for ($i = 0; $i -lt $dif.Count; $i++) { $macd += ($dif[$i] - $dea[$i]) * 2 }
    return [PSCustomObject]@{ DIF = $dif; DEA = $dea; MACD = $macd }
}

function Calc-Bollinger {
    param([array]$Data, [int]$Period = 20, [double]$Multiplier = 2.0)
    $ma = Calc-MovingAverage -Data $Data -Field "Close" -Period $Period
    $values = $Data | ForEach-Object { [double]$_.Close }
    $upper = @(); $lower = @()
    for ($i = 0; $i -lt $values.Count; $i++) {
        if ($i -lt $Period - 1) { $upper += $null; $lower += $null; continue }
        $sumSq = 0
        for ($j = 0; $j -lt $Period; $j++) { $sumSq += [math]::Pow($values[$i - $j] - $ma[$i], 2) }
        $stdDev = [math]::Sqrt($sumSq / $Period)
        $upper += [math]::Round($ma[$i] + $Multiplier * $stdDev, 2)
        $lower += [math]::Round($ma[$i] - $Multiplier * $stdDev, 2)
    }
    return [PSCustomObject]@{ MA = $ma; Upper = $upper; Lower = $lower }
}

# ============================================================
# [7] 东方财富板块行业数据（TOP N）
# ============================================================
function Get-SectorData {
    param([int]$Top = 10)
    $url = "http://push2.eastmoney.com/api/qt/clist/get?cb=&pn=1&pz=${Top}&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f3&fs=m:90+t:2&fields=f2,f3,f4,f12,f14"
    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8 -Headers @{"User-Agent"="Mozilla/5.0"}
        $json = $r.Content | ConvertFrom-Json
        return $json.data.diff | ForEach-Object {
            [PSCustomObject]@{
                SectorCode  = $_.f12
                SectorName  = $_.f14
                Index       = [double]$_.f2
                ChangePct   = [double]$_.f3
                Turnover    = [double]$_.f4  # 成交额(亿)
            }
        }
    } catch {
        Write-Warning "Get-SectorData failed: $_"
        return $null
    }
}

# ============================================================
# [9] 个股资金流向
# ============================================================
function Get-StockFundFlow {
    param([Parameter(Mandatory=$true)][string]$Code, [int]$Days = 5)
    $market = if ($Code.StartsWith("6")) { "1" } else { "0" }
    $url = "http://push2.eastmoney.com/api/qt/stock/fflow/daykline/get?cb=&secid=${market}.${Code}&fields1=f1,f2,f3,f4,f5,f6,f7&fields2=f51,f52,f53,f54,f55&lmt=${Days}"
    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8 -Headers @{"User-Agent"="Mozilla/5.0"}
        $json = $r.Content | ConvertFrom-Json
        $result = @()
        foreach ($kline in $json.data.klines) {
            $parts = $kline -split ','
            $result += [PSCustomObject]@{
                Date        = $parts[0]
                MainNetInflow  = [double]$parts[1]  # 主力净流入
                SuperLargeIn   = [double]$parts[2]  # 超大单净流入
                LargeIn        = [double]$parts[3]  # 大单净流入
                SmallIn        = [double]$parts[4]  # 小单净流入
            }
        }
        return $result
    } catch {
        Write-Warning "Get-StockFundFlow failed for $Code : $_"
        return $null
    }
}

# ============================================================
# [10] 行业资金流向
# ============================================================
function Get-SectorFundFlow {
    param([int]$Top = 10)
    $url = "http://push2.eastmoney.com/api/qt/clist/get?cb=&pn=1&pz=${Top}&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f62&fs=m:90+t:2&fields=f12,f14,f62,f184,f66,f69"
    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8 -Headers @{"User-Agent"="Mozilla/5.0"}
        $json = $r.Content | ConvertFrom-Json
        return $json.data.diff | ForEach-Object {
            [PSCustomObject]@{
                SectorCode  = $_.f12
                SectorName  = $_.f14
                NetInflow   = [double]$_.f62
                MainInflow  = [double]$_.f66
                ChangePct   = [double]$_.f184
                TurnRate    = [double]$_.f69
            }
        }
    } catch {
        Write-Warning "Get-SectorFundFlow failed: $_"
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

    return [PSCustomObject]@{
        CurrentPE  = $currentPE
        MinPE      = $minPE
        MaxPE      = $maxPE
        AvgPE      = $avgPE
        Percentile = $percentile
        SampleCount = $peHistory.Count
        Valuation  = if ($percentile -lt 30) { "低估" } elseif ($percentile -gt 70) { "高估" } else { "合理" }
    }
}

# ============================================================
# [8] 北向资金持股（季度）
# API: datacenter-web.eastmoney.com RPT_MUTUAL_HOLDSTOCKNORTH_STA
# 返回：北向资金持股数量/市值/占总股本比例
# ============================================================
function Get-NorthboundHold {
    param(
        [Parameter(Mandatory=$true)][string]$Code
    )
    $secucode = if ($Code.StartsWith("6")) { "${Code}.SH" } else { "${Code}.SZ" }
    $encoded = [System.Web.HttpUtility]::UrlEncode($secucode)
    $url = "https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_MUTUAL_HOLDSTOCKNORTH_STA&columns=ALL&filter=(SECUCODE=%22${encoded}%22)&pageSize=1&sortColumns=TRADE_DATE&sortTypes=-1"

    try {
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
                SharesRatio   = [double]$d.HOLD_SHARES_RATIO  # 占总股本%
                FreeRatio     = [double]$d.FREE_SHARES_RATIO  # 占流通股本%
            }
        }
        return $null
    } catch {
        Write-Warning "Get-NorthboundHold failed for $Code : $_"
        return $null
    }
}

# ============================================================
# [11] 个股研报/分析师评级
# API: reportapi.eastmoney.com
# 返回：研报标题/机构/评级/盈利预测/日期
# ============================================================
function Get-StockResearch {
    param(
        [Parameter(Mandatory=$true)][string]$Code,
        [int]$Count = 5,
        [string]$DaysBack = "30"
    )
    $endDate = (Get-Date).ToString("yyyy-MM-dd")
    $beginDate = (Get-Date).AddDays(-[int]$DaysBack).ToString("yyyy-MM-dd")
    $url = "https://reportapi.eastmoney.com/report/list?cb=&industryCode=*&pageSize=${Count}&industry=*&rating=*&ratingChange=*&beginTime=${beginDate}&endTime=${endDate}&pageNo=1&fields=&qType=0&code=${Code}&rcode="

    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8 -Headers @{"User-Agent"="Mozilla/5.0"; "Referer"="https://data.eastmoney.com/report/"}
        $json = $r.Content | ConvertFrom-Json
        if ($json.data -and $json.data.Count -gt 0) {
            return $json.data | ForEach-Object {
                [PSCustomObject]@{
                    Title         = $_.title
                    OrgName       = $_.orgSName
                    PublishDate   = $_.publishDate
                    EmRating      = $_.emRatingName  # 买入/增持/中性/减持
                    LastRating    = $_.lastEmRatingName
                    ThisYearEPS   = [double]$_.predictThisYearEps
                    NextYearEPS   = [double]$_.predictNextYearEps
                    ThisYearPE    = [double]$_.predictThisYearPe
                    NextYearPE    = [double]$_.predictNextYearPe
                    Author        = $_.author
                }
            }
        }
        return $null
    } catch {
        Write-Warning "Get-StockResearch failed for $Code : $_"
        return $null
    }
}

# ============================================================
# [12] 融资融券（个股）
# API: datacenter.eastmoney.com RPTA_WEB_RZRQ_GGMX
# 返回：融资余额/融券余额/融资买入额/融券余量
# ============================================================
function Get-MarginData {
    param(
        [Parameter(Mandatory=$true)][string]$Code,
        [int]$Days = 5
    )
    $url = "http://datacenter.eastmoney.com/api/data/get?type=RPTA_WEB_RZRQ_GGMX&sty=ALL&source=WEB&p=1&ps=${Days}&st=date&sr=-1&filter=(scode=%22${Code}%22)"

    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8 -Headers @{"User-Agent"="Mozilla/5.0"; "Referer"="http://data.eastmoney.com/"}
        $json = $r.Content | ConvertFrom-Json
        if ($json.result -and $json.result.data -and $json.result.data.Count -gt 0) {
            return $json.result.data | ForEach-Object {
                [PSCustomObject]@{
                    Date          = $_.DATE
                    RZYE          = [double]$_.RZYE       # 融资余额(元)
                    RQYE          = [double]$_.RQYE       # 融券余额(元)
                    RZRQYE        = [double]$_.RZRQYE     # 融资融券余额(元)
                    RZMRE         = [double]$_.RZMRE      # 融资买入额(元)
                    RZCHE         = [double]$_.RZCHE      # 融资偿还额(元)
                    RZJME         = [double]$_.RZJME      # 融资净买额(元)
                    RQYL          = [double]$_.RQYL       # 融券余量(股)
                    RQMCL         = [double]$_.RQMCL      # 融券卖出量(股)
                }
            }
        }
        return $null
    } catch {
        Write-Warning "Get-MarginData failed for $Code : $_"
        return $null
    }
}

# ============================================================
# 综合测试函数
# ============================================================
function Test-AllDataSources {
    Write-Output "====== 数据源综合测试 ======"
    Write-Output "目标股票: 招商银行(600036)`n"

    # [1] 腾讯行情
    Write-Output "--- [1] 腾讯实时行情 ---"
    $quote = Get-StockQuote -Code "600036"
    if ($quote) { Write-Output "  ✅ $($quote.Name) 现价:$($quote.Price) 涨幅:$($quote.ChangePct)% PE:$($quote.PE) 换手:$($quote.TurnoverRate)%" }
    else { Write-Output "  ❌ 失败" }

    # [2] 新浪K线
    Write-Output "--- [2] 新浪K线 ---"
    $klines = Get-StockKLine -Code "600036" -Count 5
    if ($klines) { Write-Output "  ✅ 最近5日: $($klines[-1].Date) 收:$($klines[-1].Close) 量:$($klines[-1].Volume)" }
    else { Write-Output "  ❌ 失败" }

    # [3] 财务数据
    Write-Output "--- [3] 东方财富财务 ---"
    $fin = Get-StockFinancial -Code "600036" -Quarters 2
    if ($fin) { Write-Output "  ✅ EPS:$($fin[0].BASIC_EPS) ROE:$($fin[0].WEIGHTAVG_ROE)% 营收:$($fin[0].TOTAL_OPERATE_INCOME) 净利:$($fin[0].PARENT_NETPROFIT)" }
    else { Write-Output "  ❌ 失败" }

    # [5] 技术指标
    Write-Output "--- [5] 技术指标 ---"
    $klines120 = Get-StockKLine -Code "600036" -Count 120
    if ($klines120) {
        $ma5 = Calc-MovingAverage -Data $klines120 -Period 5
        $ma20 = Calc-MovingAverage -Data $klines120 -Period 20
        $rsi = Calc-RSI -Data $klines120 -Period 14
        $macd = Calc-MACD -Data $klines120
        $boll = Calc-Bollinger -Data $klines120
        Write-Output "  ✅ MA5:$($ma5[-1]) MA20:$($ma20[-1]) RSI14:$($rsi[-1])"
        Write-Output "  ✅ MACD DIF:$([math]::Round($macd.DIF[-1],2)) DEA:$([math]::Round($macd.DEA[-1],2))"
        Write-Output "  ✅ Bollinger 上轨:$($boll.Upper[-1]) 中轨:$($boll.MA[-1]) 下轨:$($boll.Lower[-1])"
    } else { Write-Output "  ❌ 失败" }

    # [7] 板块行业
    Write-Output "--- [7] 板块行业TOP5 ---"
    $sectors = Get-SectorData -Top 5
    if ($sectors) { $sectors | ForEach-Object { Write-Output "  ✅ $($_.SectorName) $($_.ChangePct)% 成交$($_.Turnover)亿" } }
    else { Write-Output "  ❌ 失败" }

    # [9] 个股资金流向
    Write-Output "--- [9] 个股资金流向 ---"
    $fund = Get-StockFundFlow -Code "600036" -Days 3
    if ($fund) { $fund | ForEach-Object { Write-Output "  ✅ $($_.Date) 主力净流入:$([math]::Round($_.MainNetInflow/10000,0))万" } }
    else { Write-Output "  ❌ 失败" }

    # [10] 行业资金流向
    Write-Output "--- [10] 行业资金流向TOP5 ---"
    $sfund = Get-SectorFundFlow -Top 5
    if ($sfund) { $sfund | ForEach-Object { Write-Output "  ✅ $($_.SectorName) 净流入:$([math]::Round($_.NetInflow/100000000,2))亿" } }
    else { Write-Output "  ❌ 失败" }

    # PE百分位
    Write-Output "--- PE百分位 ---"
    $pe = Get-PEPercentile -Code "600036"
    if ($pe) { Write-Output "  ✅ 当前PE:$($pe.CurrentPE) 百分位:$($pe.Percentile)% 估值:$($pe.Valuation) (样本:$($pe.SampleCount)天)" }
    else { Write-Output "  ❌ 失败(数据不足或EPS问题)" }

    # [8] 北向资金
    Write-Output "--- [8] 北向资金持股 ---"
    $nb = Get-NorthboundHold -Code "600036"
    if ($nb) { Write-Output "  ✅ $($nb.Name) 北向持股:$([math]::Round($nb.HoldShares/10000,0))万股 占比:$($nb.SharesRatio)% (数据:$($nb.TradeDate))" }
    else { Write-Output "  ❌ 失败" }

    # [11] 研报
    Write-Output "--- [11] 研报/评级(近30天) ---"
    $research = Get-StockResearch -Code "600036" -Count 3
    if ($research) { $research | ForEach-Object { Write-Output "  ✅ $($_.PublishDate.Substring(0,10)) $($_.OrgName) $($_.Title) [$($_.EmRating)]" } }
    else { Write-Output "  ❌ 失败或无数据" }

    # [12] 融资融券
    Write-Output "--- [12] 融资融券(近3天) ---"
    $margin = Get-MarginData -Code "600036" -Days 3
    if ($margin) { $margin | ForEach-Object { Write-Output "  ✅ $($_.Date.Substring(0,10)) 融资余额:$([math]::Round($_.RZYE/100000000,2))亿 融券余额:$([math]::Round($_.RQYE/100000000,2))亿" } }
    else { Write-Output "  ❌ 失败" }

    Write-Output "`n====== 测试完成 ======"
}

Export-ModuleMember -Function Get-StockQuote, Get-StockKLine, Get-StockFinancial, Get-SectorData, Get-StockFundFlow, Get-SectorFundFlow, Get-PEPercentile, Get-NorthboundHold, Get-StockResearch, Get-MarginData, Calc-MovingAverage, Calc-RSI, Calc-MACD, Calc-Bollinger, Test-AllDataSources
