# 铁律量化 - 股票数据获取模块
# 数据源：腾讯行情[1], 新浪K线[2], 东方财富财务[3][6][7][9][10]
# 最后更新：2026-05-22
# 合规状态：详见 §1.5 数据源实测状态

# ============================================================
# 数据源优先级配置（主 → 备）
# ============================================================
# ============================================================
# API调用限速器（全局，避免被反爬）
# ============================================================
$script:GlobalApiCallCount = 0
$script:LastApiCallTime = [datetime]::MinValue

function Invoke-ThrottledApiCall {
    param([scriptblock]$ScriptBlock)
    $elapsed = ([datetime]::Now - $script:LastApiCallTime).TotalMilliseconds
    if ($elapsed -lt 300) { Start-Sleep -Milliseconds (300 - $elapsed) }
    $script:GlobalApiCallCount++
    if ($script:GlobalApiCallCount % 10 -eq 0) { Start-Sleep -Seconds 2 }
    $script:LastApiCallTime = [datetime]::Now
    return & $ScriptBlock
}

$script:SourcePriority = @{
    Quote      = @("腾讯", "新浪")         # 实时行情
    KLine      = @("新浪", "腾讯")         # K线数据
    Financial  = @("东方财富", "新浪")      # 财务数据
    Sector     = @("东方财富")             # 板块行情（仅东方财富）
    FundFlow   = @("东方财富")             # 资金流向（独有）
    Northbound = @("东方财富")             # 北向资金（独有）
    Research   = @("东方财富")             # 研报（独有）
    Margin     = @("东方财富")             # 融资融券（独有）
}
$script:SourceUsed = @{}    # 记录每次调用实际使用的源

# ============================================================
# 本地数据缓存层（所有数据通用兜底）
# ============================================================
$script:CacheDir = Join-Path (Split-Path $PSScriptRoot -Parent) "data_cache"
if (-not (Test-Path $script:CacheDir)) { New-Item -ItemType Directory -Path $script:CacheDir -Force | Out-Null }

# 缓存有效时长（小时）
$script:CacheTTL = @{
    Quote      = 1    # 行情变化快，1小时
    KLine      = 24   # K线收盘后不变，24小时
    Financial  = 168  # 财务数据季度更新，7天
    Sector     = 6    # 板块数据半日更新
    FundFlow   = 24   # 资金流向盘后固定，日频
    Northbound = 24   # 北向资金日频
    Research   = 24   # 研报每日更新
    Margin     = 24   # 融资融券每日更新
    PEPercentile = 168 # PE百分位变化慢，7天
}

function Save-DataCache {
    param([string]$Key, $Data)
    if (-not $Data) { return }
    $path = Join-Path $script:CacheDir "$Key.json"
    try {
        $toSave = @{
            _schema_version = "1.0"
            Timestamp = (Get-Date).ToString("o")
            Data = $Data
        }
        $toSave | ConvertTo-Json -Depth 5 -Compress | Set-Content $path -Encoding UTF8
    } catch { Write-Debug "Cache save failed for $Key : $_" }
}

function Load-DataCache {
    param([string]$Key, [int]$TTLHours = 24)
    $path = Join-Path $script:CacheDir "$Key.json"
    if (-not (Test-Path $path)) { return $null }
    try {
        $cached = Get-Content $path -Encoding UTF8 -Raw | ConvertFrom-Json
        $age = [datetime]::Now - [datetime]::Parse($cached.Timestamp)
        if ($age.TotalHours -gt $TTLHours) {
            Write-Debug "Cache expired for $Key (age: $($age.TotalHours.ToString('0.0'))h)"
            return $null
        }
        return $cached.Data
    } catch { return $null }
}

# 通用：获取数据（API优先 → 缓存兜底）
function Invoke-DataWithCache {
    param(
        [Parameter(Mandatory=$true)][string]$DataName,
        [Parameter(Mandatory=$true)][scriptblock]$ApiCall
    )
    # 先尝试API
    try {
        $result = & $ApiCall
        if ($null -ne $result) {
            Save-DataCache -Key $DataName -Data $result
            return $result
        }
    } catch {
        Write-Warning "[$DataName] API失败: $_"
    }
    # API失败 → 尝试缓存
    $ttl = if ($script:CacheTTL.ContainsKey($DataName)) { $script:CacheTTL[$DataName] } else { 24 }
    $cached = Load-DataCache -Key $DataName -TTLHours $ttl
    if ($null -ne $cached) {
        Write-Warning "[$DataName] API失败，使用缓存（有效期${ttl}h内）"
        return $cached
    }
    Write-Warning "[$DataName] API失败，缓存不可用"
    return $null
}

# 通用：查询某类数据上次使用的源
function Get-LastUsedSource {
    param([string]$DataName)
    if ($DataName) { return $script:SourceUsed[$DataName] }
    return $script:SourceUsed
}

# ============================================================
# [1] 腾讯实时行情（主） + 新浪实时行情（备）
# API: qt.gtimg.cn
# 返回：实时报价（当前价/涨跌幅/量比/换手率/PE/市值等）
# ============================================================
function Get-StockQuote {
    param(
        [Parameter(Mandatory=$true)][string]$Code
    )
    # --- 腾讯（主） ---
    try {
        $prefix = if ($Code.StartsWith("6")) { "sh" } else { "sz" }
        $url = "http://qt.gtimg.cn/q=${prefix}${Code}"
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 5
        $raw = $r.Content.Trim()
        if ($raw -match '"(.*)"') {
            $fields = $matches[1] -split '~'
            $result = [PSCustomObject]@{
                Code       = $fields[2]
                Name       = $fields[1]
                Price      = [double]$fields[3]
                PrevClose  = [double]$fields[4]
                Open       = [double]$fields[5]
                Volume     = [long]$fields[6]
                Turnover   = [double]$fields[37]
                High       = [double]$fields[33]
                Low        = [double]$fields[34]
                Change     = [double]$fields[31]
                ChangePct  = [double]$fields[32]
                PE         = [double]$fields[39]
                TurnoverRate = [double]$fields[38]
                MktCap     = [double]$fields[44]
                Amplitude  = [double]$fields[43]
                Time       = $fields[30]
            }
            $script:SourceUsed["Quote"] = "腾讯"
            Save-DataCache -Key "Quote_$Code" -Data $result
            return $result
        }
    } catch {
        Write-Warning "[行情] 腾讯失败: $_"
    }

    # --- 新浪（备） ---
    try {
        $prefix = if ($Code.StartsWith("6")) { "sh" } else { "sz" }
        $url = "http://hq.sinajs.cn/list=${prefix}${Code}"
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 5 -Headers @{"Referer"="http://finance.sina.com.cn"}
        $raw = $r.Content.Trim()
        if ($raw -match '"([^"]*)"') {
            $fields = $matches[1] -split ','
            if ($fields.Count -ge 32) {
                $result = [PSCustomObject]@{
                    Code       = $Code
                    Name       = $fields[0]
                    Price      = [double]$fields[3]
                    PrevClose  = [double]$fields[2]
                    Open       = [double]$fields[1]
                    Volume     = [long]($fields[8] -replace '\D','')  # 手
                    Turnover   = [double]($fields[9] -replace '\D','') / 10000  # 成交额转万
                    High       = [double]$fields[4]
                    Low        = [double]$fields[5]
                    Change     = [double]$fields[3] - [double]$fields[2]
                    ChangePct  = [math]::Round(([double]$fields[3] - [double]$fields[2]) / [double]$fields[2] * 100, 2)
                    PE         = $null  # 新浪行情不直接提供PE
                    TurnoverRate = $null
                    MktCap     = $null
                    Amplitude  = $null
                    Time       = $fields[31]
                }
                $script:SourceUsed["Quote"] = "新浪"
            Save-DataCache -Key "Quote_$Code" -Data $result
            return $result
            }
        }
    } catch {
        Write-Warning "[行情] 新浪失败: $_"
    }

    $script:SourceUsed["Quote"] = "失败"
    # 最后兜底：从缓存加载
    $cached = Load-DataCache -Key "Quote_$Code" -TTLHours 1
    if ($cached) { Write-Warning "[行情] 使用缓存数据"; return $cached }
    return $null
}

# ============================================================
# [1b] 腾讯批量行情 — 单次查询多只股票
# API: qt.gtimg.cn/q=code1,code2,...
# 返回：数组（与Get-StockQuote同结构）
# ============================================================
function Get-StockQuoteBatch {
    param([Parameter(Mandatory=$true)][string[]]$Codes)
    if ($Codes.Count -eq 0) { return @() }
    # 构建批量查询URL (腾讯支持逗号分隔多代码)
    $prefixes = $Codes | ForEach-Object { if ($_.StartsWith("6")) { "sh$_" } else { "sz$_" } }
    $codesStr = $prefixes -join ","
    $url = "http://qt.gtimg.cn/q=${codesStr}"

    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 10
        $content = $r.Content.Trim()
        $lines = $content -split ';'
        $results = @()
        foreach ($line in $lines) {
            if ($line -match '"(.*)"') {
                $fields = $matches[1] -split '~'
                if ($fields.Count -ge 44 -and $fields[2]) {
                    $results += [PSCustomObject]@{
                        Code       = $fields[2]
                        Name       = $fields[1]
                        Price      = [double]$fields[3]
                        PrevClose  = [double]$fields[4]
                        Open       = [double]$fields[5]
                        Volume     = [long]$fields[6]
                        Turnover   = [double]$fields[37]
                        High       = [double]$fields[33]
                        Low        = [double]$fields[34]
                        Change     = [double]$fields[31]
                        ChangePct  = [double]$fields[32]
                        PE         = [double]$fields[39]
                        TurnoverRate = [double]$fields[38]
                        MktCap     = [double]$fields[44]
                        Amplitude  = [double]$fields[43]
                        Time       = $fields[30]
                    }
                }
            }
        }
        if ($results.Count -gt 0) {
            $script:SourceUsed["Quote"] = "腾讯(批量)"
            # 逐只缓存
            foreach ($r2 in $results) { Save-DataCache -Key "Quote_$($r2.Code)" -Data $r2 }
            return $results
        }
    } catch {
        Write-Warning "[批量行情] 腾讯失败: $_"
    }

    # 备源：逐只回退到Get-StockQuote
    Write-Warning "[批量行情] 腾讯批量失败，逐只回退..."
    return $Codes | ForEach-Object { Get-StockQuote -Code $_ }
}

# ============================================================
# [2] 新浪K线数据（主） + 腾讯K线数据（备）
# API: money.finance.sina.com.cn
# 参数: scale=240(日), 60(60min), 30(30min), 15(15min), 5(5min)
# ============================================================
function Get-StockKLine {
    param(
        [Parameter(Mandatory=$true)][string]$Code,
        [string]$Scale = "240",
        [int]$Count = 120
    )
    $cacheKey = "KLine_${Code}_${Scale}"

    # --- 缓存优先（日线K线收盘后不可变，Tier 2）---
    $cached = Load-DataCache -Key $cacheKey -TTLHours 24
    if ($cached -and @($cached).Count -ge $Count) {
        $script:SourceUsed["KLine"] = "缓存"
        return $cached
    }

    # --- 新浪（主） ---
    try {
        $prefix = if ($Code.StartsWith("6")) { "sh" } else { "sz" }
        $url = "http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol=${prefix}${Code}&scale=${Scale}&ma=5&datalen=${Count}"
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8 -Headers @{"User-Agent"="Mozilla/5.0"}
        $json = $r.Content | ConvertFrom-Json
        if ($json -and $json.Count -gt 0) {
            $result = $json | ForEach-Object {
                [PSCustomObject]@{
                    Date   = $_.day
                    Open   = [double]$_.open
                    High   = [double]$_.high
                    Low    = [double]$_.low
                    Close  = [double]$_.close
                    Volume = [long]$_.volume
                }
            }
            $script:SourceUsed["KLine"] = "新浪"
            Save-DataCache -Key $cacheKey -Data $result
            return $result
        }
    } catch {
        Write-Warning "[K线] 新浪失败: $_"
    }

    # --- 腾讯（备） ---
    try {
        $prefix = if ($Code.StartsWith("6")) { "sh" } else { "sz" }
        $url = "http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=${prefix}${Code},day,,,${Count},qfq"
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8 -Headers @{"User-Agent"="Mozilla/5.0"}
        $json = $r.Content | ConvertFrom-Json
        # 腾讯返回嵌套结构: data.{code}.day 或 data.{code}.qfqday
        $data = $null
        if ($json.data.$Code.qfqday) { $data = $json.data.$Code.qfqday }
        elseif ($json.data.$Code.day) { $data = $json.data.$Code.day }
        if ($data -and $data.Count -gt 0) {
            $result = $data | ForEach-Object {
                [PSCustomObject]@{
                    Date   = $_[0]
                    Open   = [double]$_[1]
                    Close  = [double]$_[2]
                    High   = [double]$_[3]
                    Low    = [double]$_[4]
                    Volume = [long]$_[5]
                }
            }
            $script:SourceUsed["KLine"] = "腾讯"
            Save-DataCache -Key $cacheKey -Data $result
            return $result
        }
    } catch {
        Write-Warning "[K线] 腾讯失败: $_"
    }

    $script:SourceUsed["KLine"] = "失败"
    # 过期缓存兜底（API双源均失败时的最后手段）
    $staleCache = Load-DataCache -Key $cacheKey -TTLHours 720
    if ($staleCache) { Write-Warning "[K线] API双源失败，使用过期缓存兜底"; return $staleCache }
    return $null
}

# ============================================================
# [3] 东方财富财务数据（主）
# API: datacenter.eastmoney.com
# 返回：EPS/ROE/营收/净利润/毛利率等74个字段
# ============================================================
function Get-StockFinancial {
    param(
        [Parameter(Mandatory=$true)][string]$Code,
        [int]$Quarters = 4  # 返回最近N个季度
    )

    # --- 缓存优先（财务数据季度更新，Tier 3）---
    $cached = Load-DataCache -Key "Financial_$Code" -TTLHours 168
    if ($cached) {
        $script:SourceUsed["Financial"] = "缓存"
        return $cached
    }

    $secucode = if ($Code.StartsWith("6")) { "${Code}.SH" } else { "${Code}.SZ" }
    $encoded = [System.Web.HttpUtility]::UrlEncode($secucode)
    $url = "http://datacenter.eastmoney.com/api/data/v1/get?reportName=RPT_LICO_FN_CPD&columns=ALL&filter=(SECUCODE=%22${encoded}%22)&pageSize=${Quarters}&sortColumns=NOTICE_DATE&sortTypes=-1"

    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8 -Headers @{"User-Agent"="Mozilla/5.0"}
        $json = $r.Content | ConvertFrom-Json
        if ($json.result -and $json.result.data) {
            $script:SourceUsed["Financial"] = "东方财富"
            Save-DataCache -Key "Financial_$Code" -Data $json.result.data
            return $json.result.data
        }
    } catch {
        Write-Warning "Get-StockFinancial failed for $Code : $_"
    }
    $script:SourceUsed["Financial"] = "失败"
    # 过期缓存兜底（API双源均失败时的最后手段）
    $staleCache = Load-DataCache -Key "Financial_$Code" -TTLHours 720
    if ($staleCache) { Write-Warning "[财务] API双源失败，使用过期缓存兜底"; return $staleCache }
    return $null
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
        if ($json.data -and $json.data.diff) {
            $result = $json.data.diff | ForEach-Object {
                [PSCustomObject]@{
                    SectorCode  = $_.f12
                    SectorName  = $_.f14
                    Index       = [double]$_.f2
                    ChangePct   = [double]$_.f3
                    Turnover    = [double]$_.f4
                }
            }
            $script:SourceUsed["Sector"] = "东方财富"
            Save-DataCache -Key "Sector_$Top" -Data $result
            return $result
        }
    } catch {
        Write-Warning "Get-SectorData failed: $_"
    }
    $script:SourceUsed["Sector"] = "失败"
    $cached = Load-DataCache -Key "Sector_$Top" -TTLHours 6
    if ($cached) { Write-Warning "[板块] API失败，使用缓存"; return $cached }
    return $null
}

# ============================================================
# [7b] 东方财富板块成分股 — 获取指定板块内的所有股票
# API: push2.eastmoney.com/api/qt/clist/get?fs=b:BKXXXX
# ============================================================
function Get-SectorConstituents {
    param(
        [Parameter(Mandatory=$true)][string]$SectorCode,
        [int]$MaxCount = 50,
        [string]$SortField = "f3"  # f3=涨跌幅排序
    )

    # --- 缓存优先（成分股调整低频，Tier 3）---
    $cached = Load-DataCache -Key "SectorConstituents_$SectorCode" -TTLHours 168
    if ($cached -and @($cached).Count -ge $MaxCount) {
        $script:SourceUsed["SectorConstituents"] = "缓存"
        return $cached
    }

    $url = "http://push2.eastmoney.com/api/qt/clist/get?cb=&pn=1&pz=${MaxCount}&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=${SortField}&fs=b:${SectorCode}&fields=f12,f14,f2,f3,f4,f15,f16,f17,f18"
    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8 -Headers @{"User-Agent"="Mozilla/5.0"}
        $json = $r.Content | ConvertFrom-Json
        if ($json.data -and $json.data.diff) {
            $result = $json.data.diff | ForEach-Object {
                [PSCustomObject]@{
                    Code        = $_.f12
                    Name        = $_.f14
                    Price       = [double]$_.f2
                    ChangePct   = [double]$_.f3
                    Turnover    = [double]$_.f4
                    High        = [double]$_.f15
                    Low         = [double]$_.f16
                    Open        = [double]$_.f17
                    PrevClose   = [double]$_.f18
                }
            }
            $script:SourceUsed["SectorConstituents"] = "东方财富"
            Save-DataCache -Key "SectorConstituents_$SectorCode" -Data $result
            return $result
        }
    } catch {
        Write-Warning "Get-SectorConstituents failed for $SectorCode : $_"
    }
    $script:SourceUsed["SectorConstituents"] = "失败"
    # 过期缓存兜底（API双源均失败时的最后手段）
    $staleCache = Load-DataCache -Key "SectorConstituents_$SectorCode" -TTLHours 720
    if ($staleCache) { Write-Warning "[板块成分股] API双源失败，使用过期缓存兜底"; return $staleCache }
    return $null
}

# ============================================================
# [9] 个股资金流向
# ============================================================
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
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8 -Headers @{"User-Agent"="Mozilla/5.0"}
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
    $script:SourceUsed["Margin"] = "失败"
    # 过期缓存兜底（API双源均失败时的最后手段）
    $staleCache = Load-DataCache -Key "Margin_${Code}_${Days}" -TTLHours 720
    if ($staleCache) { Write-Warning "[融资融券] API双源失败，使用过期缓存兜底"; return $staleCache }
    return $null
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

    # 数据源跟踪
    Write-Output "`n--- 数据源跟踪 ---"
    $src = Get-LastUsedSource
    foreach ($key in $src.Keys) {
        $status = if ($src[$key] -eq "失败") { "❌" } else { "✅" }
        Write-Output "  $status $key → $($src[$key])"
    }

    Write-Output "`n====== 测试完成 ======"
}

Export-ModuleMember -Function Get-StockQuote, Get-StockQuoteBatch, Get-StockKLine, Get-StockFinancial, Get-SectorData, Get-SectorConstituents, Get-StockFundFlow, Get-SectorFundFlow, Get-PEPercentile, Get-NorthboundHold, Get-StockResearch, Get-MarginData, Get-LastUsedSource, Invoke-ThrottledApiCall, Calc-MovingAverage, Calc-RSI, Calc-MACD, Calc-Bollinger, Test-AllDataSources
