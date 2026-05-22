<#
.SYNOPSIS
  批量数据采集 — 对动态池中所有股票采集行情/K线/资金流/财务数据
.DESCRIPTION
  输入: dynamic_pool.json (由 build_dynamic_pool.ps1 生成)
  输出: data_full.json (含K线数组，供 scoring_engine_v2.py 使用)
.PARAMETER PoolFile
  动态池文件路径
.PARAMETER OutputFile
  输出文件路径
.PARAMETER SkipKLine
  跳过K线采集（仅更新行情）
#>
param(
    [string]$PoolFile = "",
    [string]$OutputFile = "",
    [switch]$SkipKLine
)

$rootDir = "C:\Users\34269\Documents\Claude\股票分析"
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
if ($quotes) {
    foreach ($q in $quotes) { $quoteMap[$q.Code] = $q }
    Write-Host "  成功: $($quotes.Count)/$($codes.Count)"
} else {
    Write-Warning "  批量行情失败"
}

# --- 2. 财务数据（缓存为主） ---
Write-Host "[2/5] 财务数据..."
$finMap = @{}
$finCount = 0
foreach ($s in $stocks) {
    $fin = Invoke-ThrottledApiCall { Get-StockFinancial -Code $s.Code -Quarters 4 }
    if ($fin) { $finMap[$s.Code] = $fin; $finCount++ }
}
Write-Host "  成功: $finCount/$($stocks.Count)"

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
                KClose = $klines | ForEach-Object { [double]$_.Close }
                KVolume = $klines | ForEach-Object { [long]$_.Volume }
                KOpen = $klines | ForEach-Object { [double]$_.Open }
                KHigh = $klines | ForEach-Object { [double]$_.High }
                KLow = $klines | ForEach-Object { [double]$_.Low }
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
    $sectorKLCacheDir = Join-Path $rootDir "代码文件\data_cache\sector_kline"
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

            # 写入缓存（兼容旧缓存格式，但新读取侧优先匹配新格式）
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

# --- 7. 组装输出 ---
Write-Host "`n组装输出..."
$output = @()
foreach ($s in $stocks) {
    $q = $quoteMap[$s.Code]
    $fin = $finMap[$s.Code]
    $fund = $fundMap[$s.Code]
    $k = $klineMap[$s.Code]

    if (-not $q) {
        Write-Warning "  缺少行情: $($s.Code) $($s.Name)"
        continue
    }

    # 财务数据（多季度）
    $eps = $null
    $epsQuarterly = @()
    if ($fin -and $fin.Count -gt 0) {
        $epsVals = $fin | ForEach-Object { [double]$_.BASIC_EPS }
        $eps = ($epsVals | Measure-Object -Average).Average
        $epsQuarterly = $epsVals  # 保留4个季度的EPS序列
    }

    # 初始化各维度评分（将在 scoring_engine_v2.py 中重新计算）
    $obj = [PSCustomObject]@{
        Code         = $s.Code
        Name         = $s.Name
        Industry     = $s.Industry
        Price        = $q.Price
        ChangePct    = $q.ChangePct
        Volume       = $q.Volume
        TurnoverRate = $q.TurnoverRate
        Amplitude    = $q.Amplitude
        PE           = if ($q.PE -and $q.PE -gt 0) { $q.PE } else { 0 }
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
        KClose       = if ($k) { $k.KClose } else { @() }
        KVolume      = if ($k) { $k.KVolume } else { @() }
        KOpen        = if ($k) { $k.KOpen } else { @() }
        KHigh        = if ($k) { $k.KHigh } else { @() }
        KLow         = if ($k) { $k.KLow } else { @() }
        # 财务数据
        EPS          = $eps
        EPS_Quarterly = $epsQuarterly  # 4个季度EPS序列
        # 资金流向(多日)
        FundMainNet       = if ($fund -and $fund.Count -gt 0) { [double]$fund[0].MainNetInflow } else { 0 }
        FundFlow_History  = if ($fund) { $fund | ForEach-Object { [double]$_.MainNetInflow } } else { @() }
    }
    $output += $obj
}

# 构建结构化的输出（含个股数据 + 真实板块行情数据）
$finalOutput = [PSCustomObject]@{
    BuildTime = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Stocks = $output
    SectorData = $sectorRanking
    SectorFundFlow = $sectorFundFlow
    SectorKLine = $sectorKLineDict
}
$finalOutput | ConvertTo-Json -Depth 5 | Set-Content $OutputFile -Encoding UTF8
Write-Host "  个股: $($output.Count) 只, 板块: $(if($sectorRanking){$sectorRanking.Count}else{0}) 个, 板块K线: $(if($sectorKLineDict){$sectorKLineDict.Count}else{0}) 条 → $OutputFile"
Write-Host "Done"
