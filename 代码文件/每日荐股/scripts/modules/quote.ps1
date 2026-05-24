# 依赖: dot-source "$PSScriptRoot/core.ps1"

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
    $staleCache = Load-DataCache -Key $cacheKey -TTLHours 720  # 30天，基本不过滤
    if ($staleCache) { Write-Warning "[K线] API双源失败，使用过期缓存兜底"; return $staleCache }
    return $null
}

# ============================================================
# [3] 东方财富财务数据（主）
# API: datacenter.eastmoney.com
# 返回：EPS/ROE/营收/净利润/毛利率等74个字段
# ============================================================