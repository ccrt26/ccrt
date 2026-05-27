<#
.SYNOPSIS 批量数据采集 — 行情/K线/资金流/财务/板块/北向/两融/研报
.INPUT dynamic_pool.json .OUTPUT data_full.json
#>
param(
    [string]$PoolFile = "",
    [string]$OutputFile = "",
    [switch]$SkipKLine
)
. "$PSScriptRoot/../../lib/init_encoding.ps1"

$rootDir = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
if (-not $PoolFile) { $PoolFile = Join-Path $rootDir "代码文件\数据\dynamic_pool.json" }
if (-not $OutputFile) { $OutputFile = Join-Path $rootDir "代码文件\数据\data_full.json" }
if (-not (Test-Path $PoolFile)) { Write-Error "动态池文件不存在: $PoolFile"; exit 1 }

Import-Module (Join-Path $rootDir "代码文件\每日荐股\scripts\stock_data_fetcher.psm1") -Force -DisableNameChecking

$pool = Get-Content $PoolFile -Encoding UTF8 | ConvertFrom-Json
$stocks = $pool.Stocks
if (-not $stocks -or $stocks.Count -eq 0) { Write-Error "动态池为空"; exit 1 }
Write-Host "动态池: $($stocks.Count) 只股票, 开始采集数据"
# --- 1. 批量行情 ---
Write-Host "`n[1/5] 批量行情..."
$codes = $stocks | ForEach-Object { $_.Code }
$quotes = Get-StockQuoteBatch -Codes $codes
$quoteMap = @{}
if ($quotes) { foreach ($q in $quotes) { $quoteMap[$q.Code] = $q } } else { Write-Warning "批量行情失败" }
Write-Host "  成功: $(if($quotes){$quotes.Count}else{0})/$($codes.Count)"

# --- 2. 财务数据（缓存为主） ---
Write-Host "[2/5] 财务数据..."
$finMap = @{}
$finCount = 0
foreach ($s in $stocks) {
    $fin = Invoke-ThrottledApiCall { Get-StockFinancial -Code $s.Code -Quarters 4 }
    if ($fin) { $finMap[$s.Code] = $fin; $finCount++ }
}
Write-Host "  成功: $finCount/$($stocks.Count)"

# --- 2b. 财务明细(毛利率/商誉/扣非EPS) — v2026-05-27 修复全线缺失 ---
$finDetailMap = @{}
$finDetailCount = 0
foreach ($s in $stocks) {
    $finDetail = Invoke-ThrottledApiCall { Get-FinancialDetail -Code $s.Code -Quarters 1 }
    if ($finDetail) { $finDetailMap[$s.Code] = $finDetail; $finDetailCount++ }
}
Write-Host "  财务明细: $finDetailCount/$($stocks.Count)"

# --- 2c. 每股经营现金流(CFPS) — 东方财富主源不含，THS financial_abstract 专有 ---
$cfpsMap = @{}
$keystockCodes = @("600114","601727","603019","301075","601689","000967","002230","603092")
$thsScript = Join-Path $PSScriptRoot "stock_data_fetcher_ths.py"
if (Test-Path $thsScript) {
    foreach ($code in $keystockCodes) {
        try {
            $tmpFile = [System.IO.Path]::GetTempFileName()
            cmd /c "python `"$thsScript`" financial --code $code --quarters 1 > `"$tmpFile`"" 2>$null
            if ((Test-Path $tmpFile) -and ((Get-Item $tmpFile).Length -gt 0)) {
                $raw = [System.IO.File]::ReadAllText($tmpFile, [System.Text.Encoding]::UTF8)
                Remove-Item $tmpFile -Force -ErrorAction SilentlyContinue
                if ($raw.Trim().Length -gt 0) {
                    $parsed = $raw | ConvertFrom-Json
                    if ($parsed -and $parsed.Count -gt 0 -and $parsed[0].CFPS) {
                        $cfpsMap[$code] = [double]$parsed[0].CFPS
                    }
                }
            } else {
                Remove-Item $tmpFile -Force -ErrorAction SilentlyContinue
            }
        } catch { }
    }
}
Write-Host "  CFPS(THS 重点8只): $($cfpsMap.Count)/8"

# --- 3. 资金流向（缓存为主） ---
Write-Host "[3/5] 资金流向..."
$fundMap = @{}
$fundCount = 0
foreach ($s in $stocks) {
    $fund = Invoke-ThrottledApiCall { Get-StockFundFlow -Code $s.Code -Days 5 }
    if ($fund) { $fundMap[$s.Code] = $fund; $fundCount++ }
}
Write-Host "  成功: $fundCount/$($stocks.Count)"

# --- 4. K线数据 ---
$klineMap = @{}
if (-not $SkipKLine) {
    Write-Host "[4/5] K线数据(60日)..."
    $klCount = 0
    foreach ($s in $stocks) {
        $klines = Invoke-ThrottledApiCall { Get-StockKLine -Code $s.Code -Scale "240" -Count 60 }
        if ($klines -and $klines.Count -gt 0) {
            $klineMap[$s.Code] = @{
                KDate   = $klines | ForEach-Object { $_.Date }
                KClose  = $klines | ForEach-Object { [double]$_.Close }
                KVolume = $klines | ForEach-Object { [long]$_.Volume }
                KOpen   = $klines | ForEach-Object { [double]$_.Open }
                KHigh   = $klines | ForEach-Object { [double]$_.High }
                KLow    = $klines | ForEach-Object { [double]$_.Low }
            }
            $klCount++
        }
        if ($klCount % 20 -eq 0) { Write-Host "  ... $klCount/$($stocks.Count)" }
    }
    Write-Host "  成功: $klCount/$($stocks.Count)"
} else {
    Write-Host "[4/5] K线: 跳过"
}

# --- 5. 板块行情数据（从东方财富获取真实市场数据） ---
Write-Host "[5/5] 板块行情数据..."
$sectorRanking = Get-SectorData -Top 30
$sectorFundFlow = Get-SectorFundFlow -Top 30
if ($sectorRanking) {
    Write-Host "  板块行情: $($sectorRanking.Count) 个行业"
} else {
    Write-Warning "  板块行情获取失败"
}

# --- 6. 板块指数K线采集[6/6] ---
Write-Host "[6/6] 板块指数K线采集..."
$sectorKLineDict = @{}  # dict[sector_code] = [ {close, volume, date}, ... ]
if ($sectorRanking -and $sectorRanking.Count -gt 0) {
    $sectorKLCacheDir = Join-Path $rootDir "代码文件\每日荐股\data_cache\sector_kline"
    if (-not (Test-Path $sectorKLCacheDir)) { New-Item -ItemType Directory -Path $sectorKLCacheDir -Force | Out-Null }

    $sectorKlOk = 0
    $sectorKlTotal = $sectorRanking.Count
    foreach ($s in $sectorRanking) {
        $sc = $s.SectorCode
        $sn = $s.SectorName
        if (-not $sn) { continue }

        # THS 备份数据没有 BK 代码（SectorCode 为空），直接走 THS K线
        if (-not $sc) {
            Write-Debug "  THS来源板块K线: ${sn}"
            $thsData = Invoke-ThsFallback -Action "sector_kline" -Params "--name $sn --days 60"
            if ($thsData -and $thsData.Count -gt 0) {
                $klineList = @()
                foreach ($item in $thsData) {
                    $klineList += [PSCustomObject]@{
                        close  = [double]$item.close
                        volume = [long]$item.volume
                        date   = $item.date
                    }
                }
                # 用行业名作为 key 存储
                $sectorKLineDict[$sn] = $klineList
                $sectorKlOk++
            } else {
                Write-Warning "  THS板块K线无数据: ${sn}"
            }
            if ($sectorKlOk % 10 -eq 0) { Write-Host "  ... ${sectorKlOk}/${sectorKlTotal}" }
            continue
        }

        # 尝试从缓存加载（24h TTL）
        $cacheFile = Join-Path $sectorKLCacheDir "${sc}.json"
        $cached = $null
        if (Test-Path $cacheFile) {
            try {
                $cached = Get-Content $cacheFile -Encoding UTF8 -Raw | ConvertFrom-Json
                $age = [datetime]::Now - [datetime]::Parse($cached.Timestamp)
                if ($age.TotalHours -le 24) { $cached = $cached.Data } else { $cached = $null }
            } catch { $cached = $null }
        }
        if ($cached) {
            # 兼容: 旧缓存格式含 SectorCode/ClosePrices 字段，新格式是 list[close,volume,date]
            if ($cached.SectorCode) {
                # 旧格式: 转成新格式
                $klist = @()
                for ($i = 0; $i -lt $cached.ClosePrices.Count; $i++) {
                    $klist += [PSCustomObject]@{
                        close  = $cached.ClosePrices[$i]
                        volume = $cached.Volumes[$i]
                        date   = $cached.Dates[$i]
                    }
                }
                $sectorKLineDict[$cached.SectorCode] = $klist
            } elseif ($cached -is [array]) {
                $sectorKLineDict[$sc] = $cached
            } elseif ($cached -is [System.Management.Automation.PSCustomObject]) {
                # 单个对象包装成列表
                $sectorKLineDict[$sc] = @($cached)
            }
            $sectorKlOk++
            continue
        }

        # 调用东方财富板块K线API（主源）
        $klines = Invoke-ThrottledApiCall {
            $url = "http://push2.eastmoney.com/api/qt/stock/kline/get?secid=90.${sc}&fields1=f1,f2,f3&fields2=f51,f52,f53,f54,f55,f56,f57&klt=101&fqt=1&end=20500101&lmt=60"
            try {
                $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8 -Headers @{"User-Agent"="Mozilla/5.0"}
                $json = $r.Content | ConvertFrom-Json
                if ($json.data -and $json.data.klines -and $json.data.klines.Count -gt 0) { return $json.data.klines }
            } catch {
                Write-Warning "  板块K线API失败: ${sc} ${sn} : $_"
            }
            return $null
        }

        # 东方财富失败 → 尝试同花顺 THS 备份
        if (-not $klines) {
            Write-Warning "  板块K线尝试同花顺 THS 备份: ${sn}"
            $thsData = Invoke-ThsFallback -Action "sector_kline" -Params "--name $sn --days 60"
            if ($thsData -and $thsData.Count -gt 0) {
                # THS 返回 [{"date","close","volume","open","high","low"}]
                $klines = @()
                foreach ($item in $thsData) {
                    $klines += "${item.date},${item.open},${item.close},${item.high},${item.low},${item.volume},0"
                }
                Write-Warning "  THS备份成功: ${sn}"
            }
        }

        if ($klines -and $klines.Count -gt 0) {
            $dates = [System.Collections.Generic.List[string]]@()
            $closes = [System.Collections.Generic.List[double]]@()
            $volumes = [System.Collections.Generic.List[long]]@()

            foreach ($kl in $klines) {
                $parts = $kl -split ','
                if ($parts.Count -ge 6) {
                    $dates.Add($parts[0])
                    $closes.Add([double]$parts[2])
                    $volumes.Add([long]$parts[5])
                }
            }

            # 计算每日涨跌幅
            $chgPcts = [System.Collections.Generic.List[double]]@()
            for ($i = 0; $i -lt $closes.Count; $i++) {
                if ($i -eq 0) { $chgPcts.Add(0); continue }
                $prev = $closes[$i-1]
                if ($prev -ne 0) {
                    $chgPcts.Add([math]::Round(($closes[$i] - $prev) / $prev * 100, 2))
                } else {
                    $chgPcts.Add(0)
                }
            }

            # 构建 scoring_engine_v2.py 所需的格式: { "BKxxxx": [{"close":x, "volume":y}, ...] }
            $klineList = @()
            for ($i = 0; $i -lt $closes.Count; $i++) {
                $klineList += [PSCustomObject]@{
                    close  = $closes[$i]
                    volume = $volumes[$i]
                    date   = $dates[$i]
                }
            }

    # 板块K线缓存（24h TTL），兼容旧格式，新读取侧优先匹配新格式
            $toCache = @{ Timestamp = (Get-Date).ToString("o"); Data = $klineList }
            $toCache | ConvertTo-Json -Depth 5 -Compress | Set-Content $cacheFile -Encoding UTF8

            $sectorKLineDict[$sc] = $klineList
            $sectorKlOk++
        } else {
            Write-Warning "  板块K线无数据: ${sc} ${sn}"
        }

        if ($sectorKlOk % 10 -eq 0) { Write-Host "  ... ${sectorKlOk}/${sectorKlTotal}" }
    }
    Write-Host "  成功: ${sectorKlOk}/${sectorKlTotal}"
} else {
    Write-Warning "  [6/6] 板块排名数据不可用，跳过板块K线采集"
}

# --- 6.5. 全市场成交额采集（v2.7 TECH-01: V5动态阈值依赖） ---
Write-Host "[6.5/7] 全市场成交额..."
$marketTurnover = $null
try {
    $turnoverUrl = "http://push2.eastmoney.com/api/qt/stock/get?secid=1.000001&fields=f43,f44,f45,f46,f47,f48,f50,f51,f52,f57,f58,f60,f107,f116,f117,f162,f167,f168,f169,f170,f171"
    $turnoverResp = Invoke-WebRequest -Uri $turnoverUrl -UseBasicParsing -TimeoutSec 8 -Headers @{"User-Agent"="Mozilla/5.0"}
    $turnoverJson = $turnoverResp.Content | ConvertFrom-Json
    if ($turnoverJson.data) {
        # 上证成交额(元) → 转换为亿元
        $shTurnover = [double]($turnoverJson.data.f44) / 1e8
        Write-Host "  上证成交额: $([math]::Round($shTurnover, 0))亿"
    }
    $szTurnoverUrl = "http://push2.eastmoney.com/api/qt/stock/get?secid=0.399001&fields=f43,f44,f45,f46,f47,f48,f50,f51,f52,f57,f58,f60,f107,f116,f117,f162,f167,f168,f169,f170,f171"
    $szResp = Invoke-WebRequest -Uri $szTurnoverUrl -UseBasicParsing -TimeoutSec 8 -Headers @{"User-Agent"="Mozilla/5.0"}
    $szJson = $szResp.Content | ConvertFrom-Json
    if ($szJson.data) {
        $szTurnover = [double]($szJson.data.f44) / 1e8
        Write-Host "  深证成交额: $([math]::Round($szTurnover, 0))亿"
    }
    if ($shTurnover -and $szTurnover) {
        $totalTurnover = $shTurnover + $szTurnover
        Write-Host "  沪深合计: $([math]::Round($totalTurnover, 0))亿"
        $marketTurnover = [math]::Round($totalTurnover, 0)
    }
} catch {
    Write-Warning "  全市场成交额获取失败: $_"
}
# 加载历史成交额缓存（近5日均值）
$turnoverCacheFile = Join-Path $rootDir "代码文件\每日荐股\data_cache\market_turnover_5d.json"
$turnoverHistory = @()
if (Test-Path $turnoverCacheFile) {
    try {
        $cached = Get-Content $turnoverCacheFile -Encoding UTF8 -Raw | ConvertFrom-Json
        $turnoverHistory = [System.Collections.Generic.List[double]]($cached.History)
    } catch { $turnoverHistory = @() }
}
if ($marketTurnover) {
    [void]$turnoverHistory.Add($marketTurnover)
    if ($turnoverHistory.Count -gt 5) {
        $turnoverHistory = $turnoverHistory[-5..-1]
    }
    @{ History = $turnoverHistory; LastUpdate = (Get-Date).ToString("o") } | ConvertTo-Json -Compress | Set-Content $turnoverCacheFile -Encoding UTF8
}
$avgMarketTurnover = if ($turnoverHistory.Count -gt 0) { [math]::Round(($turnoverHistory | Measure-Object -Average).Average, 0) } else { $null }
if ($avgMarketTurnover) {
    Write-Host "  近5日均成交额: ${avgMarketTurnover}亿"
}

# --- 7. 大宗商品期货价格采集 (v2.7 TECH-05) ---
Write-Host "[7/7] 大宗商品期货价格..."
$commodityPrices = $null
try {
    $thsCommodityScript = Join-Path $rootDir "代码文件\每日荐股\scripts\stock_data_fetcher_ths.py"
    if (Test-Path $thsCommodityScript) {
        $commodityJson = python $thsCommodityScript commodity_price --days 20 2>&1
        $commodityPrices = $commodityJson | ConvertFrom-Json
        if ($commodityPrices) {
            $validCount = ($commodityPrices | Where-Object { -not $_.error }).Count
            Write-Host "  商品价格: ${validCount}/$($commodityPrices.Count) 个品种"
            foreach ($cp in $commodityPrices) {
                if ($cp.error) {
                    Write-Warning "  $($cp.name)($($cp.symbol)): $($cp.error)"
                } else {
                    Write-Host "  $($cp.display_name)($($cp.symbol)): $($cp.price) | 10d $($cp.trend_10d)% | 20d $($cp.trend_20d)%"
                }
            }
        }
    } else {
        Write-Warning "  THS桥接脚本不存在: $thsCommodityScript"
    }
} catch {
    Write-Warning "  商品价格采集失败: $_"
}

# --- 8. 北向资金 (v2.8: 接入评分链) ---
Write-Host "[8/10] 北向资金..."
$northboundMap = @{}
$nbCount = 0
foreach ($s in $stocks) {
    $nb = Invoke-ThrottledApiCall { Get-NorthboundHold -Code $s.Code }
    if ($nb) { $northboundMap[$s.Code] = $nb; $nbCount++ }
}
Write-Host "  成功: $nbCount/$($stocks.Count)"

# --- 9. 南向资金 (v2026-05-27: 补位北向日频失效) ---
Write-Host "[9/10] 南向资金(日频)..."
$southboundFlow = $null
try {
    $sbResult = Invoke-ThrottledApiCall { Get-SouthboundFlow -Days 5 }
    if ($sbResult -and $sbResult.data) {
        $southboundFlow = $sbResult
        Write-Host "  成功: 南向日频数据 ($($sbResult.source)), $($sbResult.data.Count)日"
    } else {
        Write-Host "  失败: 南向数据不可用"
    }
} catch {
    Write-Warning "  南向资金采集失败: $_"
}

# --- 10. 融资融券 (v2.8: 接入评分链) ---
Write-Host "[10/10] 融资融券..."
$marginMap = @{}
$mgCount = 0
foreach ($s in $stocks) {
    $mg = Invoke-ThrottledApiCall { Get-MarginData -Code $s.Code -Days 5 }
    if ($mg) { $marginMap[$s.Code] = $mg; $mgCount++ }
}
Write-Host "  成功: $mgCount/$($stocks.Count)"

# --- 10. 研报一致预期 (v2.8: ConsensusGrowth → PEG评分) ---
Write-Host "[10/10] 研报一致预期..."
$researchMap = @{}
$researchCount = 0
foreach ($s in $stocks) {
    $reports = Invoke-ThrottledApiCall { Get-StockResearch -Code $s.Code -Count 10 -DaysBack 365 }
    if ($reports -and $reports.Count -gt 0) {
        # 计算一致预期增长率: (avg(NextYearEPS) - avg(ThisYearEPS)) / avg(ThisYearEPS) * 100
        $thisYearSum = 0; $nextYearSum = 0; $validCount = 0
        foreach ($r in $reports) {
            if ($r.ThisYearEPS -and $r.NextYearEPS -and $r.ThisYearEPS -gt 0) {
                $thisYearSum += [double]$r.ThisYearEPS
                $nextYearSum += [double]$r.NextYearEPS
                $validCount++
            }
        }
        if ($validCount -gt 0) {
            $avgThisYear = $thisYearSum / $validCount
            $avgNextYear = $nextYearSum / $validCount
            $consensusGrowth = [math]::Round(($avgNextYear - $avgThisYear) / $avgThisYear * 100, 2)
            $researchMap[$s.Code] = @{
                ConsensusGrowth = $consensusGrowth
                ReportCount     = $validCount
                AvgThisYearEPS  = [math]::Round($avgThisYear, 4)
                AvgNextYearEPS  = [math]::Round($avgNextYear, 4)
            }
            $researchCount++
        }
    }
}
Write-Host "  成功: $researchCount/$($stocks.Count)"

# --- 7. 组装输出 ---
Write-Host "`n组装输出..."
$output = @()
foreach ($s in $stocks) {
    $q = $quoteMap[$s.Code]
    $fin = $finMap[$s.Code]
    $fund = $fundMap[$s.Code]
    $k = $klineMap[$s.Code]
    $nb = $northboundMap[$s.Code]
    $mg = $marginMap[$s.Code]
    $research = $researchMap[$s.Code]

    if (-not $q) {
        Write-Warning "  缺少行情: $($s.Code) $($s.Name)"
        continue
    }

    # 财务数据（多季度）— BPS/营收/增长率 用于三路径PE评分
    $epsTTM = $null         # v2026-05-27: TTM EPS = SUM(最近4Q) → PE(TTM)计算
    $epsAvgQ = $null        # v2026-05-27: 季度平均EPS（保持兼容）
    $epsQuarterly = @()
    $bps = $null           # 每股净资产 → PB估值(周期成长路径)
    $revenueTTM = $null    # 营业总收入TTM → PS估值(强成长路径)
    $revenueYoy = $null    # 营收同比增长率 → 成长验证
    $netProfitYoy = $null  # 净利润同比增长率 → PEG计算
    $grossMargin = $null   # 销售毛利率 → 质量参考
    $goodwill = $null      # v2026-05-27: 商誉 → 减值风险评估(红线§三.4)
    $goodwillToNA = $null  # v2026-05-27: 商誉/净资产比率(%)
    $deductedEPS = $null   # v2026-05-27: 扣非EPS → 利润真实性验证
    $debtRatio = $null     # v2026-05-27: 资产负债率 → 财务健康
    if ($fin -and $fin.Count -gt 0) {
        $epsVals = $fin | ForEach-Object { [double]$_.BASIC_EPS }
        $epsTTM = ($epsVals | Measure-Object -Sum).Sum          # v2026-05-27: TTM求和(红线§1.2)
        $epsAvgQ = ($epsVals | Measure-Object -Average).Average  # 季度均值(保持兼容)
        $epsQuarterly = $epsVals

        # 每股净资产 (BPS/NAPS — 东方财富用BPS，同花顺也用BPS)
        # v2026-05-27: 增强备选字段名 + 遍历记录(部分新股首条BPS=null)
        $bpsVal = $null
        foreach ($r in $fin) {
            if ($r.BPS) { $bpsVal = $r.BPS; break }
            if ($r.NAPS) { $bpsVal = $r.NAPS; break }
            if ($r.TOTAL_EQUITY) { $bpsVal = $r.TOTAL_EQUITY; break }
            if ($r.SHAREHOLDERS_EQUITY) { $bpsVal = $r.SHAREHOLDERS_EQUITY; break }
            if ($r.TOTAL_SHAREHOLDER_EQUITY) { $bpsVal = $r.TOTAL_SHAREHOLDER_EQUITY; break }
        }
        if ($bpsVal) { $bps = [double]$bpsVal }

        # 营业总收入TTM (用最近4个季度累加)
        $revVals = $fin | ForEach-Object {
            $v = $_.TOTAL_OPERATE_INCOME
            if (-not $v) { $v = $_.OPERATE_INCOME }
            if (-not $v) { $v = $_.TOTAL_OPERATE_REVENUE }
            if ($v) { [double]$v } else { 0 }
        }
        if ($revVals -and ($revVals | Measure-Object -Sum).Sum -gt 0) {
            $revenueTTM = ($revVals | Measure-Object -Sum).Sum
        }

        # 增长率 (取最近季度)
        $revYoyVal = $fin[0].REVENUE_YOY
        if (-not $revYoyVal) { $revYoyVal = $fin[0].OPERATE_INCOME_YOY }
        if ($revYoyVal) { $revenueYoy = [double]$revYoyVal }

        $npYoyVal = $fin[0].NETPROFIT_YOY
        if (-not $npYoyVal) { $npYoyVal = $fin[0].PARENT_NETPROFIT_YOY }
        if (-not $npYoyVal) { $npYoyVal = $fin[0].DEDUCTED_YOY }
        if ($npYoyVal) { $netProfitYoy = [double]$npYoyVal }

        # 毛利率 — v2026-05-27: XSMLL(销售毛利率)来自RPT_LICO_FN_CPD, 遍历记录取有效值
        $finDetail = $finDetailMap[$s.Code]
        $gmVal = $null
        foreach ($r in $fin) {
            if ($r.XSMLL) { $gmVal = $r.XSMLL; break }
            if ($r.GROSS_MARGIN) { $gmVal = $r.GROSS_MARGIN; break }
            if ($r.GROSS_PROFIT_MARGIN) { $gmVal = $r.GROSS_PROFIT_MARGIN; break }
            if ($r.SALE_GROSS_PROFIT_RATIO) { $gmVal = $r.SALE_GROSS_PROFIT_RATIO; break }
        }
        if (-not $gmVal -and $finDetail -and $finDetail.OPERATE_COST -and $finDetail.TOTAL_OPERATE_INCOME) {
            # 从利润表详细端点自算: (营收-营业成本)/营收
            $rev = [double]$finDetail.TOTAL_OPERATE_INCOME
            $cost = [double]$finDetail.OPERATE_COST
            if ($rev -gt 0) { $gmVal = [math]::Round(($rev - $cost) / $rev * 100, 2) }
        }
        if ($gmVal) { $grossMargin = [double]$gmVal }

        # 商誉 — v2026-05-27: 从财务明细端点获取（红线§三.4 利润真实性验证）
        if ($finDetail -and $finDetail.GOODWILL) {
            $goodwill = [double]$finDetail.GOODWILL
            if ($bps -and $bps -gt 0) {
                $goodwillToNA = [math]::Round($goodwill / ($bps * 1e8) * 100, 2)
                # 流金风控联动: 商誉/净资产比率告警
                if ($goodwillToNA -gt 50) {
                    Write-Warning "[风控] ${Code}: 商誉/净资产=${goodwillToNA}% → 红牌！(>50%)"
                } elseif ($goodwillToNA -gt 30) {
                    Write-Warning "[风控] ${Code}: 商誉/净资产=${goodwillToNA}% → 黄牌！(>30%)"
                }
            }
        }

        # 扣非EPS — v2026-05-27: DEDUCT_BASIC_EPS来自RPT_LICO_FN_CPD, 遍历记录
        $deVal = $null
        foreach ($r in $fin) {
            if ($r.DEDUCT_BASIC_EPS) { $deVal = $r.DEDUCT_BASIC_EPS; break }
        }
        if (-not $deVal -and $finDetail -and $finDetail.DEDUCT_PARENT_NETPROFIT) {
            $deVal = $finDetail.DEDUCT_PARENT_NETPROFIT  # 仅作标记(非每股)
        }
        if ($deVal) { $deductedEPS = [double]$deVal }

        # 资产负债率 — v2026-05-27: 从已有财务数据提取
        if ($fin[0].DEBT_ASSET_RATIO) { $debtRatio = [double]$fin[0].DEBT_ASSET_RATIO }

        # v2026-05-24 P1: 股息率 — 稳定价值蓝筹估值锚点
        $divYield = $null
        $zxgxlVal = $fin[0].ZXGXL
        if ($zxgxlVal) { $divYield = [double]$zxgxlVal }
    }

    # RevenueTTM 有效性校验 — v2026-05-27
    if ($revenueTTM -and $revenueTTM -gt 0 -and $q.MktCap -and $q.MktCap -gt 0) {
        $revYi = $revenueTTM / 1e8
        $psCheck = [math]::Round([double]$q.MktCap / $revYi, 2)
        if ($psCheck -lt 0.1) {
            Write-Warning "[财务] ${Code}: RevenueTTM异常 — Rev=${revYi}亿 MktCap=$($q.MktCap)亿 PS=${psCheck}(<0.1 极端异常)"
        }
    }

    # F1: PS(TTM) = 总市值 / 营业总收入TTM
    $ps = $null
    if ($revenueTTM -and $revenueTTM -gt 0 -and $q.MktCap -and $q.MktCap -gt 0) {
        $revenueTTM_Yi = $revenueTTM / 1e8
        if ($revenueTTM_Yi -gt 0) { $ps = [math]::Round([double]$q.MktCap / $revenueTTM_Yi, 2) }
    }
    # F2: 每股经营现金流 — 主源MGJYXJJE(RPT_LICO_FN_CPD,遍历记录) + 备源THS
    $cfps = $null
    foreach ($r in $fin) {
        if ($r.MGJYXJJE) { $cfps = [double]$r.MGJYXJJE; break }
    }
    if (-not $cfps) { $cfps = $cfpsMap[$s.Code] }
    # F3: 主力净流入昨日基线 (FundFlow_History数组倒数第二个)
    $fundMainNetPrev = $null
    if ($fund) {
        $fundArr = @($fund)
        if ($fundArr.Count -ge 2) { $fundMainNetPrev = [double]$fundArr[1].MainNetInflow }
    }
    # F4: 融资余额/净买入昨日基线 ($mg日频数组取昨日)
    $marginRZYE_Prev = $null; $marginRZJME_Prev = $null
    if ($mg -and $mg.Count -ge 2) {
        $marginRZYE_Prev = [double]$mg[1].RZYE
        $marginRZJME_Prev = [double]$mg[1].RZJME
    }

# 初始化各维度评分（由 scoring_engine_v2.py 重新计算）
    $obj = [PSCustomObject]@{
        Code         = $s.Code
        Name         = $s.Name
        Industry     = $s.Industry
        Price        = $q.Price
        ChangePct    = $q.ChangePct
        Volume       = $q.Volume
        TurnoverRate = $q.TurnoverRate
        Amplitude    = $q.Amplitude
        Open         = $q.Open
        High         = $q.High
        Low          = $q.Low
        PrevClose    = $q.PrevClose
        PE_Quote     = if ($q.PE -and $q.PE -gt 0) { $q.PE } else { 0 }    # v2026-05-27: 行情静态PE(来源不明，仅参考)
        PE           = if ($epsTTM -gt 0) { [math]::Round($q.Price / $epsTTM, 2) } else { if ($q.PE -gt 0) { $q.PE } else { 0 } }  # v2026-05-27: PE(TTM)=Price/EPS_TTM [3+自算] 优先
        MktCap       = $q.MktCap
        TotalScore   = 50
        S_Base       = 5
        S_Fund       = 10
        S_Tech       = 13
        S_Money      = 10
        S_News       = 10
        S_Risk       = 3
        PoolSource   = $s.Source
        # K线数组（由 scoring_engine_v2.py 使用）
        KDate        = if ($k) { $k.KDate } else { @() }   # v2026-05-24: 日期数组，供周线/月线聚合
        KClose       = if ($k) { $k.KClose } else { @() }
        KVolume      = if ($k) { $k.KVolume } else { @() }
        KOpen        = if ($k) { $k.KOpen } else { @() }
        KHigh        = if ($k) { $k.KHigh } else { @() }
        KLow         = if ($k) { $k.KLow } else { @() }
        # 东方财富K线 → 日期→换手率映射（新浪K线不含换手率，东方财富[3]含f61字段）
        $turnoverMap = @{}
        try {
            $emPrefix = if ($s.Code.StartsWith("6")) { "1" } else { "0" }
            $emKlineUrl = "http://push2his.eastmoney.com/api/qt/stock/kline/get?secid=${emPrefix}.$($s.Code)&fields1=f1,f2,f3&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&klt=101&fqt=0&end=20500101&lmt=5"
            $emResp = Invoke-WebRequest -Uri $emKlineUrl -UseBasicParsing -TimeoutSec 5 -Headers @{"User-Agent"="Mozilla/5.0"}
            $emJson = $emResp.Content | ConvertFrom-Json
            if ($emJson.data -and $emJson.data.klines) {
                foreach ($kl in $emJson.data.klines) {
                    $parts = $kl -split ','
                    if ($parts.Count -ge 11 -and $parts[10] -and [double]::TryParse($parts[10], [ref]$null)) {
                        $turnoverMap[$parts[0]] = [double]$parts[10]
                    }
                }
            }
        } catch { }
        # 预计算近4日数据（供日报1.2节直接读取，避免AI解析K线数组）
        Recent4Days  = if ($k -and $k.KDate -and $k.KDate.Count -gt 0) {
            $recent = @()
            $n = $k.KDate.Count
            $start = [Math]::Max(0, $n - 4)
            for ($i = $start; $i -lt $n; $i++) {
                $prevClose = if ($i -gt 0) { $k.KClose[$i-1] } else { $k.KClose[0] }
                $chg = if ($prevClose -ne 0) { [math]::Round(($k.KClose[$i] - $prevClose) / $prevClose * 100, 2) } else { 0 }
                $recent += @{
                    Date         = $k.KDate[$i]
                    Close        = $k.KClose[$i]
                    ChangePct    = $chg
                    High         = $k.KHigh[$i]
                    Low          = $k.KLow[$i]
                    Volume       = $k.KVolume[$i]
                    TurnoverRate = if ($turnoverMap.ContainsKey($k.KDate[$i])) { $turnoverMap[$k.KDate[$i]] } else { $null }
                }
            }
            # 追加今日快照
            $todayStr = (Get-Date).ToString("yyyy-MM-dd")
            if ($recent.Count -eq 0 -or $recent[-1].Date -ne $todayStr) {
                $recent += @{
                    Date         = $todayStr
                    Close        = $q.Price
                    ChangePct    = $q.ChangePct
                    High         = $q.High
                    Low          = $q.Low
                    Volume       = $q.Volume
                    TurnoverRate = $q.TurnoverRate
                }
            }
            ,@($recent | Select-Object -Last 4)
        } else { @() }
        # 财务数据
        EPS          = $epsAvgQ       # v2026-05-27: 季度平均EPS(保持兼容)
        EPS_TTM      = $epsTTM        # v2026-05-27: TTM EPS = SUM(最近4Q) [3+自算]
        EPS_Quarterly = $epsQuarterly # 4个季度EPS序列
        BPS          = $bps           # v2.6: 每股净资产 → PB估值
        RevenueTTM   = $revenueTTM    # v2.6: 营业总收入TTM → PS估值
        RevenueYOY   = $revenueYoy    # v2.6: 营收同比增长率
        NetProfitYOY = $netProfitYoy  # v2.6: 净利润同比增长率 → PEG
        GrossMargin  = $grossMargin   # v2.6: 销售毛利率
        CFPS         = $cfps          # 每股经营现金流 (THS备源可用，主源可能null)
        DividendYield = $divYield     # v2026-05-24 P1: 股息率 [3]
        PS           = $ps            # PS(TTM) = MktCap / RevenueTTM
        Goodwill     = $goodwill      # v2026-05-27: 商誉(元) [3a]
        GoodwillToNA = $goodwillToNA  # v2026-05-27: 商誉/净资产比率(%) [3a+自算]
        DeductedEPS  = $deductedEPS   # v2026-05-27: 扣非基本EPS [3a]
        AssetLiabilityRatio = $debtRatio  # v2026-05-27: 资产负债率(%) [3]
        # 资金流向(多日)
        FundMainNet       = if ($fund) { $fundArr = @($fund); if ($fundArr.Count -gt 0) { [double]$fundArr[0].MainNetInflow } else { 0 } } else { 0 }
        FundFlow_History  = if ($fund) { $fund | ForEach-Object { [double]$_.MainNetInflow } } else { @() }
        FundMainNet_Prev  = $fundMainNetPrev  # 昨日主力净流入(日报资金面基线)
        # 北向资金 [8] (v2.8: 接入评分链, 季度滞后~57天)
        NorthboundSharesRatio = if ($nb -and $nb.SharesRatio) { [double]$nb.SharesRatio } else { 0 }
        NorthboundFreeRatio   = if ($nb -and $nb.FreeRatio) { [double]$nb.FreeRatio } else { 0 }
        NorthboundHoldMktCap  = if ($nb -and $nb.HoldMarketCap) { [double]$nb.HoldMarketCap } else { 0 }
        # 南向资金 [THS-SB] (v2026-05-27: 日频补位北向失效)
        SouthboundNetFlow  = if ($southboundFlow -and $southboundFlow.data -and $southboundFlow.data.Count -gt 0) { [double]$southboundFlow.data[-1].net_flow } else { 0 }
        SouthboundFlow_5d  = if ($southboundFlow -and $southboundFlow.data) { ($southboundFlow.data | ForEach-Object { [double]$_.net_flow } | Measure-Object -Sum).Sum } else { 0 }
        SouthboundSignal   = if ($southboundFlow -and $southboundFlow.data) {
            $sbSignals = $southboundFlow.data | ForEach-Object { if ([double]$_.net_flow -gt 5) { 1 } elseif ([double]$_.net_flow -lt -5) { -1 } else { 0 } }
            $posDays = ($sbSignals | Where-Object { $_ -eq 1 }).Count
            $negDays = ($sbSignals | Where-Object { $_ -eq -1 }).Count
            if ($negDays -ge 3) { -1 } elseif ($posDays -ge 3) { 1 } else { 0 }
        } else { 0 }
        # 融资融券 [12] (v2.8: 接入评分链)
        MarginRZYE   = if ($mg -and $mg.Count -gt 0) { [double]$mg[0].RZYE } else { 0 }
        MarginRZMRE  = if ($mg -and $mg.Count -gt 0) { [double]$mg[0].RZMRE } else { 0 }
        MarginRZJME  = if ($mg -and $mg.Count -gt 0) { [double]$mg[0].RZJME } else { 0 }
        MarginRQYL   = if ($mg -and $mg.Count -gt 0) { [double]$mg[0].RQYL } else { 0 }
        # v2.8: 融资余额5日趋势 (day0 - day4 差值, 正数=杠杆资金流入)
        MarginRZYE_5dChange = if ($mg -and $mg.Count -ge 5) { [double]($mg[0].RZYE - $mg[4].RZYE) } else { 0 }
        MarginRZYE_Prev  = $marginRZYE_Prev   # 昨日融资余额(日报资金面基线)
        MarginRZJME_Prev = $marginRZJME_Prev  # 昨日融资净买入
        # 研报一致预期 [11] (v2.8: ConsensusGrowth → PEG评分第一条路径)
        ConsensusGrowth     = if ($research -and $research.ConsensusGrowth) { [double]$research.ConsensusGrowth } else { 0 }
        ResearchReportCount = if ($research -and $research.ReportCount) { [int]$research.ReportCount } else { 0 }
    }
    $output += $obj
}

# 核查：重点股票数据完整性（日报1.2节依赖 High + Recent4Days）
$keystockCodes = @("600114","601727","603019","301075","601689","000967","002230","603092")
$missingHigh = @(); $missingRecent4 = @(); $missingLow = @()
foreach ($stock in $output) {
    if ($stock.Code -in $keystockCodes) {
        if (-not $stock.High -or $stock.High -eq 0) { $missingHigh += $stock.Code }
        if (-not $stock.Low -or $stock.Low -eq 0) { $missingLow += $stock.Code }
        if (-not $stock.Recent4Days -or $stock.Recent4Days.Count -eq 0) { $missingRecent4 += $stock.Code }
    }
}
if ($missingHigh.Count -gt 0) { Write-Warning "核查: 以下重点股票缺少当日High: $($missingHigh -join ', ')" }
if ($missingLow.Count -gt 0) { Write-Warning "核查: 以下重点股票缺少当日Low: $($missingLow -join ', ')" }
if ($missingRecent4.Count -gt 0) { Write-Warning "核查: 以下重点股票缺少Recent4Days: $($missingRecent4 -join ', ')" }
if ($missingHigh.Count -eq 0 -and $missingLow.Count -eq 0 -and $missingRecent4.Count -eq 0) {
    Write-Host "核查: 8只重点股票 High/Low/Recent4Days 全部OK"
}

# 构建结构化的输出（含个股数据 + 真实板块行情数据）
$finalOutput = [PSCustomObject]@{
    BuildTime = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Stocks = $output
    SectorData = $sectorRanking
    SectorFundFlow = $sectorFundFlow
    SectorKLine = $sectorKLineDict
    CommodityPrices = if ($commodityPrices) { $commodityPrices } else { @() }  # v2.7 TECH-05
    MarketTurnover = if ($avgMarketTurnover) { $avgMarketTurnover } else { 0 }
    SouthboundFlow = if ($southboundFlow) { $southboundFlow } else { $null }
}
$finalOutput | ConvertTo-Json -Depth 5 | Set-Content $OutputFile -Encoding UTF8
Write-Host "  个股: $($output.Count) 只, 板块: $(if($sectorRanking){$sectorRanking.Count}else{0}) 个, 板块K线: $(if($sectorKLineDict){$sectorKLineDict.Count}else{0}) 条, 全市场成交额: $(if($avgMarketTurnover){"${avgMarketTurnover}亿"}else{'N/A'}) → $OutputFile"

# Auto-commit: data_pipeline outputs
$gitAuto = Join-Path $rootDir "代码文件\tools\git_autocommit.ps1"
if (Test-Path $gitAuto) {
    $null = & $gitAuto -Module "data_pipeline" -Paths @("历史数据\") -Message "批量数据采集产出"
}

Write-Host "Done"
