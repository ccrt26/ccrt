# Diagnostic script for stock data APIs
$ErrorActionPreference = "Continue"
Import-Module "$PSScriptRoot\..\代码文件\每日荐股\scripts\stock_data_fetcher.psm1" -Force -WarningAction SilentlyContinue 2>$null
Add-Type -AssemblyName System.Web 2>$null

Write-Host "=== Financial API Diagnostic ===" -ForegroundColor Cyan

foreach ($code in @("000967", "301075", "601689")) {
    Write-Host "`n--- $code ---" -ForegroundColor Yellow

    # 1. Quote
    $q = Get-StockQuote -Code $code
    Write-Host "Quote: $($q.Name) Price=$($q.Price) PE=$($q.PE)"

    # 2. KLine
    $k = Get-StockKLine -Code $code -Scale 240 -Count 120
    if ($k -and $k.Count -gt 0) {
        Write-Host "KLine: $($k.Count) records, LastClose=$($k[-1].Close)"
    } else {
        Write-Host "KLine: FAIL/EMPTY" -ForegroundColor Red
    }

    # 3. Financial - direct test bypassing module function
    $secucode = if ($code.StartsWith("6")) { "${code}.SH" } else { "${code}.SZ" }
    $encoded = [System.Web.HttpUtility]::UrlEncode($secucode)
    $url = "http://datacenter.eastmoney.com/api/data/v1/get?reportName=RPT_LICO_FN_CPD&columns=SECUCODE,NOTICE_DATE,TOTAL_OPERATE_INCOME,PARENT_NETPROFIT&filter=(SECUCODE=%22${encoded}%22)&pageSize=2&sortColumns=NOTICE_DATE&sortTypes=-1"

    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8 -Headers @{"User-Agent"="Mozilla/5.0"}
        $json = $r.Content | ConvertFrom-Json
        if ($json.result -and $json.result.data) {
            $cnt = $json.result.data.Count
            $date = $json.result.data[0].NOTICE_DATE
            $rev = $json.result.data[0].TOTAL_OPERATE_INCOME
            Write-Host "Financial (direct): $cnt records, Latest=$date, Rev=$rev"
        } else {
            Write-Host "Financial (direct): API returned empty data" -ForegroundColor Red
        }
    } catch {
        Write-Host "Financial (direct): FAIL - $($_.Exception.Message.Substring(0, [Math]::Min(100, $_.Exception.Message.Length)))" -ForegroundColor Red
    }

    # 4. Financial via module function
    $f = Get-StockFinancial -Code $code -Quarters 4
    if ($f -and $f.Count -gt 0) {
        Write-Host "Financial (module): $($f.Count) records" -ForegroundColor Green
    } else {
        Write-Host "Financial (module): FAIL/EMPTY" -ForegroundColor Red
    }

    # 5. Other data sources
    $ff = Get-StockFundFlow -Code $code -Days 5
    if ($ff -and @($ff).Count -gt 0) { Write-Host "FundFlow: $($ff.Count) days" } else { Write-Host "FundFlow: EMPTY" -ForegroundColor Red }

    $nb = Get-NorthboundHold -Code $code
    if ($nb -and $nb.SharesRatio -gt 0) { Write-Host "Northbound: ratio=$($nb.SharesRatio)%" } else { Write-Host "Northbound: EMPTY" -ForegroundColor Red }
}

Write-Host "`n=== Done ===" -ForegroundColor Cyan
