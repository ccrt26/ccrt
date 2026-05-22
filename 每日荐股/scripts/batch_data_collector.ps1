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
if (-not $PoolFile) { $PoolFile = Join-Path $rootDir "dynamic_pool.json" }
if (-not $OutputFile) { $OutputFile = Join-Path $rootDir "data_full.json" }

if (-not (Test-Path $PoolFile)) { Write-Error "动态池文件不存在: $PoolFile"; exit 1 }

Import-Module (Join-Path $rootDir "每日荐股\scripts\stock_data_fetcher.psm1") -Force -DisableNameChecking

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

# --- 6. 组装输出 ---
Write-Host "`n组装输出..."
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

    # 计算EPS（用于PE校验）
    $eps = $null
    if ($fin -and $fin.Count -gt 0) {
        $epsVals = $fin | ForEach-Object { [double]$_.BASIC_EPS }
        $eps = ($epsVals | Measure-Object -Average).Average
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
        # 资金流向(最近1日)
        FundMainNet  = if ($fund -and $fund.Count -gt 0) { [double]$fund[0].MainNetInflow } else { 0 }
    }
    $output += $obj
}

# 构建结构化的输出（含个股数据 + 真实板块行情数据）
$finalOutput = [PSCustomObject]@{
    BuildTime = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Stocks = $output
    SectorData = $sectorRanking
    SectorFundFlow = $sectorFundFlow
}
$finalOutput | ConvertTo-Json -Depth 5 | Set-Content $OutputFile -Encoding UTF8
Write-Host "  个股: $($output.Count) 只, 板块: $(if($sectorRanking){$sectorRanking.Count}else{0}) 个 → $OutputFile"
Write-Host "Done"
