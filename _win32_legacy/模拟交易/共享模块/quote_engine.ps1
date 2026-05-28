# ============================================================
# quote_engine.ps1 — 行情获取共享模块
# 1+2架构: 腾讯行情[1] → 新浪行情[1B] → 缓存[C]
# 两个模拟交易赛道共用
# ============================================================

function Get-QuoteMap {
    param(
        [hashtable[]]$StockList,     # @(@{Code="600888"; Market="sh"}, ...)
        [string]$CacheFile = "",
        [string]$SimDir = ""
    )
    $qtCodes = $StockList | ForEach-Object { "$($_.Market)$($_.Code)" }
    $result = @{}
    $dataSourceLog = ""

    # Tier 1: 腾讯行情[1]
    try {
        $wc = New-Object System.Net.WebClient
        $rawBytes = $wc.DownloadData("https://qt.gtimg.cn/q=$($qtCodes -join ',')")
        $utf16text = [System.Text.Encoding]::GetEncoding("GBK").GetString($rawBytes)
        ($utf16text -split ';') | ForEach-Object {
            $m = [regex]::Match($_, '"(.*)"')
            if (-not $m.Success) { return }
            $parts = $m.Groups[1].Value -split '~'
            if ($parts.Count -lt 45) { return }
            $code = $parts[2]
            $openP = 0; [double]::TryParse($parts[5], [ref]$openP) | Out-Null
            $nowP  = 0; [double]::TryParse($parts[3], [ref]$nowP) | Out-Null
            $chgP  = 999; [double]::TryParse($parts[32], [ref]$chgP) | Out-Null
            $highP = 0; [double]::TryParse($parts[33], [ref]$highP) | Out-Null
            $lowP  = 0; [double]::TryParse($parts[34], [ref]$lowP) | Out-Null
            $prevCloseP = 0; [double]::TryParse($parts[4], [ref]$prevCloseP) | Out-Null
            $turnover = 0; [double]::TryParse($parts[38], [ref]$turnover) | Out-Null
            $result[$code] = @{
                OpenPrice   = $openP
                Price       = $nowP
                ChangePct   = $chgP
                High        = $highP
                Low         = $lowP
                PrevClose   = $prevCloseP
                TurnoverRate = $turnover
                Name        = $parts[1]
                DataSource  = "[1]"
            }
        }
        if ($result.Count -gt 0) { $dataSourceLog = "腾讯行情[1]" }
    } catch {
        Write-Warning "腾讯行情[1]异常: $_"
    }

    # Tier 2: 新浪行情[1B]
    if ($result.Count -eq 0) {
        Write-Warning "腾讯行情[1]不可用，尝试新浪行情[1B]..."
        try {
            $sinaUrl = "https://hq.sinajs.cn/list=$($qtCodes -join ',')"
            $wc = New-Object System.Net.WebClient
            $wc.Headers.Add("Referer", "https://finance.sina.com.cn")
            $rawBytes = $wc.DownloadData($sinaUrl)
            $utf16text = [System.Text.Encoding]::GetEncoding("GBK").GetString($rawBytes)
            ($utf16text -split ';') | ForEach-Object {
                if ($_.Trim().Length -eq 0) { return }
                $m = [regex]::Match($_, 'var hq_str_(\w+)="(.*)"')
                if (-not $m.Success) { return }
                $fullCode = $m.Groups[1].Value
                $parts = $m.Groups[2].Value -split ','
                if ($parts.Count -lt 32) { return }
                $code = $fullCode -replace '^(sh|sz|bj)', ''
                $openP = 0; [double]::TryParse($parts[1], [ref]$openP) | Out-Null
                $nowP  = 0; [double]::TryParse($parts[3], [ref]$nowP) | Out-Null
                $prevClose = 0; [double]::TryParse($parts[2], [ref]$prevClose) | Out-Null
                $chgP = 999
                if ($prevClose -gt 0) { $chgP = [Math]::Round(($nowP / $prevClose - 1) * 100, 2) }
                $result[$code] = @{
                    OpenPrice   = $openP
                    Price       = $nowP
                    ChangePct   = $chgP
                    High        = 0
                    Low         = 0
                    PrevClose   = $prevClose
                    TurnoverRate = 0
                    Name        = $parts[0]
                    DataSource  = "[1B]"
                }
            }
            if ($result.Count -gt 0) { $dataSourceLog = "新浪行情[1B]" }
        } catch {
            Write-Warning "新浪行情[1B]异常: $_"
        }
    }

    # Tier 3: 缓存兜底[C]
    if ($result.Count -eq 0) {
        Write-Warning "行情API均不可用，尝试缓存[C]..."
        if ($CacheFile -and (Test-Path $CacheFile)) {
            try {
                $cache = Get-Content $CacheFile -Raw | ConvertFrom-Json
                foreach ($stock in $StockList) {
                    $code = $stock.Code
                    if ($null -ne $cache.$code -and $cache.$code.Price -gt 0) {
                        $result[$code] = @{
                            OpenPrice   = [double]$cache.$code.Price
                            Price       = [double]$cache.$code.Price
                            ChangePct   = 0
                            High        = [double]$cache.$code.Price
                            Low         = [double]$cache.$code.Price
                            TurnoverRate = 0
                            Name        = $stock.Name
                            DataSource  = "[C]"
                            PrevClose   = [double]$cache.$code.Price
                        }
                    }
                }
                if ($result.Count -gt 0) { $dataSourceLog = "缓存[C]" }
            } catch {
                Write-Warning "缓存[C]读取失败: $_"
            }
        }
    }

    if ($dataSourceLog) {
        Write-Host "[行情] 数据来源: $dataSourceLog ($($result.Count)只)"
    } else {
        Write-Warning "[行情] 所有行情源均无数据"
    }
    return @{ Quotes = $result; Source = $dataSourceLog }
}

function Get-BenchmarkValue {
    param([string]$Code = "sh000300")
    try {
        $wc = New-Object System.Net.WebClient
        $rawBytes = $wc.DownloadData("https://qt.gtimg.cn/q=$Code")
        $utf16text = [System.Text.Encoding]::GetEncoding("GBK").GetString($rawBytes)
        $m = [regex]::Match($utf16text, '"(.*)"')
        if (-not $m.Success) { return $null }
        $parts = $m.Groups[1].Value -split '~'
        if ($parts.Count -lt 6) { return $null }
        $price = [double]$parts[3]
        $prevClose = [double]$parts[4]
        $changePct = 0
        if ($prevClose -gt 0) { $changePct = [Math]::Round(($price / $prevClose - 1) * 100, 2) }
        $turnover = 0; [double]::TryParse($parts[37], [ref]$turnover) | Out-Null
        return @{ Price = $price; Open = [double]$parts[5]; ChangePct = $changePct; Turnover = $turnover }
    } catch { return $null }
}

function Save-QuoteCache {
    param([hashtable]$Quotes, [string]$CacheFile)
    if (-not $CacheFile) { return }
    $cacheObj = @{}
    foreach ($kv in $Quotes.GetEnumerator()) {
        $cacheObj[$kv.Key] = @{ Price = $kv.Value.Price; Name = $kv.Value.Name }
    }
    $cacheObj | ConvertTo-Json -Depth 3 | Set-Content -Encoding UTF8 $CacheFile
}
