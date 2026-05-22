# 采集42只股票的K线数据供Python评分引擎使用
$rootDir = "C:\Users\34269\Documents\Claude\股票分析"
Import-Module (Join-Path $rootDir "每日荐股\scripts\stock_data_fetcher.psm1") -Force -WarningAction SilentlyContinue 2>$null

$jsonPath = Join-Path $rootDir "代码文件\数据\data_final.json"
$stocks = Get-Content $jsonPath -Encoding UTF8 | ConvertFrom-Json

$allData = @()

foreach ($s in $stocks) {
    $code = $s.Code
    $name = $s.Name
    Write-Host ("采集: " + $code + " " + $name)

    $klines = Get-StockKLine -Code $code -Scale 240 -Count 60
    if ($klines -eq $null -or $klines.Count -lt 20) {
        Write-Host "  -> K线不足"
        continue
    }

    # 提取数值字段
    $prices = $klines | ForEach-Object { [double]$_.Close }
    $volumes = $klines | ForEach-Object { [double]$_.Volume }
    $opens = $klines | ForEach-Object { [double]$_.Open }
    $highs = $klines | ForEach-Object { [double]$_.High }
    $lows = $klines | ForEach-Object { [double]$_.Low }

    $item = New-Object PSObject -Property @{
        Code = $code
        Name = $name
        Industry = $s.Industry
        Price = [double]$s.Price
        ChangePct = [double]$s.ChangePct
        Volume = [double]$s.Volume
        TurnoverRate = [double]$s.TurnoverRate
        PE = [double]$s.PE
        MktCap = [double]$s.MktCap
        Amplitude = [double]$s.Amplitude
        S_Base = [int]$s.S_Base
        S_Fund = [int]$s.S_Fund
        S_Tech = [int]$s.S_Tech
        S_Money = [int]$s.S_Money
        S_News = [int]$s.S_News
        S_Risk = [int]$s.S_Risk
        TotalScore = [int]$s.TotalScore
        KClose = $prices
        KVolume = $volumes
        KOpen = $opens
        KHigh = $highs
        KLow = $lows
    }
    $allData += $item
    Write-Host ("  -> " + $klines.Count + "根K线")
}

$outPath = Join-Path $rootDir "临时回溯\klines_data.json"
$allData | ConvertTo-Json -Depth 3 | Out-File $outPath -Encoding UTF8
$cnt = $allData.Count
Write-Host ("输出: " + $outPath + " (" + $cnt + "只股票)")
