<#
.SYNOPSIS
  Build dynamic stock pool - core-stock-first + sector supplementary
.DESCRIPTION
  1. Start with core stocks (comprehensive baseline, 50 stocks)
  2. Scan sectors from EastMoney API, pick top 3 hot sectors
  3. Add limited constituent stocks from hot sectors (10 each max)
  4. Map EastMoney sector names to broad industry categories via JSON
  5. Core stocks always >=60% of pool
#>
param(
    [int]$TopSectors = 5,
    [int]$StocksPerSector = 20,
    [string]$CoreStocksFile = "",
    [string]$OutputFile = ""
)
. "$PSScriptRoot/../../lib/init_encoding.ps1"

# ---- Load config (paths with Chinese chars live in JSON) ----
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $scriptDir))
$configFile = Join-Path (Join-Path $rootDir "代码文件\数据") "pool_config.json"
if (-not (Test-Path $configFile)) {
    Write-Error "Config not found: $configFile"
    exit 1
}
$cfg = Get-Content $configFile -Encoding UTF8 | ConvertFrom-Json
$rootDir = $cfg.rootDir

if (-not $CoreStocksFile) { $CoreStocksFile = Join-Path $rootDir $cfg.paths.coreStocks }
if (-not $OutputFile) { $OutputFile = Join-Path $rootDir $cfg.paths.dynamicPool }

$modulePath = Join-Path $rootDir $cfg.paths.module
if (Test-Path $modulePath) {
    . $modulePath; if (-not (Get-Command Get-SectorData -ErrorAction SilentlyContinue)) { Write-Error "Module functions not loaded from: $modulePath"; exit 1 }
} else {
    Write-Error "Module not found: $modulePath"; exit 1
}

# ---- Load sector-to-industry mapping from JSON ----
$sectorMapFile = Join-Path $rootDir $cfg.paths.sectorMap
if (Test-Path $sectorMapFile) {
    $sectorMapData = Get-Content $sectorMapFile -Encoding UTF8 | ConvertFrom-Json; $INDUSTRY_MAP = @{}; foreach ($prop in $sectorMapData.Map.PSObject.Properties) { $INDUSTRY_MAP[$prop.Name] = $prop.Value }
    Write-Host "  Loaded $($INDUSTRY_MAP.Count) industry mappings"
} else {
    Write-Warning "Sector map not found, will use raw sector names"
    $INDUSTRY_MAP = @{}
}

function Get-PhaseKey($avgChg, $avgTurn) {
    if ($avgTurn -gt 5 -and $avgChg -gt 2)  { return "peak" }
    if ($avgTurn -gt 3 -and $avgChg -lt -3) { return "decline" }
    if ($avgTurn -gt 3 -and $avgChg -gt 0)  { return "rise" }
    if ($avgTurn -gt 2 -and $avgChg -lt -1) { return "rise" }
    if ($avgChg -ge -1.5 -and $avgTurn -le 4) { return "accum" }
    if ($avgChg -ge -2 -and $avgTurn -le 2) { return "accum" }
    return "accum"
}

# ==== Phase 1: Core stocks ====
Write-Host "=== Phase 1: Core stocks ==="
$poolStocks = @{}
$coreCount = 0

if (Test-Path $CoreStocksFile) {
    $coreData = Get-Content $CoreStocksFile -Encoding UTF8 | ConvertFrom-Json
    $coreStocks = $coreData.CoreStocks
    foreach ($cs in $coreStocks) {
        if (-not $poolStocks.ContainsKey($cs.Code)) {
            $poolStocks[$cs.Code] = @{
                Code     = $cs.Code
                Name     = $cs.Name
                Industry = $cs.Industry
                Source   = "core_stock"
            }
            $coreCount++
        }
    }
    Write-Host "  Core stocks loaded: $coreCount"
} else {
    Write-Error "Core stocks file not found: $CoreStocksFile"; exit 1
}

if ($coreCount -lt 35) {
    Write-Error "Core stocks too few ($coreCount), need at least 35"; exit 1
}

# ==== Phase 2: Sector scan ====
Write-Host "`n=== Phase 2: Sector scan ==="
$sectors = Get-SectorData -Top 30
if (-not $sectors) { Write-Error "Failed to get sector data"; exit 1 }
Write-Host "  Got $($sectors.Count) sectors"

$sectorFund = Get-SectorFundFlow -Top 30
if ($sectorFund) { Write-Host "  Got $($sectorFund.Count) sector fund flows" }

$sectorMap = @{}
foreach ($s in $sectors) {
    $sectorMap[$s.SectorCode] = @{ Sector = $s; Fund = $null }
}
if ($sectorFund) {
    foreach ($f in $sectorFund) {
        if ($sectorMap.ContainsKey($f.SectorCode)) {
            $sectorMap[$f.SectorCode].Fund = $f
        }
    }
}

# ==== Phase 3: Score and pick hot sectors ====
Write-Host "`n=== Phase 3: Hot sector selection ==="
$scoredSectors = @()
foreach ($kv in $sectorMap.Values) {
    $s = $kv.Sector
    $f = $kv.Fund
    $pk = Get-PhaseKey $s.ChangePct $s.Turnover

    $ps = 0
    if ($pk -eq "accum") { $ps = 10 }
    elseif ($pk -eq "rise") { $ps = 5 }
    elseif ($pk -eq "peak") { $ps = -5 }
    elseif ($pk -eq "decline") { $ps = -10 }

    $cs = 0
    if ($s.ChangePct -ge -2 -and $s.ChangePct -le 3) { $cs = 5 }
    elseif ($s.ChangePct -gt 5) { $cs = -5 }

    $ts = 0
    if ($s.Turnover -gt 2 -and $s.Turnover -le 6) { $ts = 5 }
    elseif ($s.Turnover -gt 10) { $ts = -3 }

    $fs = 0
    if ($f -and $f.NetInflow -gt 0) { $fs = 5 }
    elseif ($f -and $f.NetInflow -lt -100000000) { $fs = -3 }

    $totalScore = $ps + $cs + $ts + $fs

    $scoredSectors += [PSCustomObject]@{
        SectorCode = $s.SectorCode
        SectorName = $s.SectorName
        ChangePct  = $s.ChangePct
        Turnover   = if ($s.Turnover -is [double]) { $s.Turnover } else { [double]$s.Turnover }
        TotalScore = $totalScore
    }
}

$hotSectors = $scoredSectors | Sort-Object TotalScore -Descending | Select-Object -First $TopSectors

Write-Host "  Hot sectors (top $TopSectors):"
foreach ($hs in $hotSectors) {
    Write-Host "    $($hs.SectorName) chg:$($hs.ChangePct)% score:$($hs.TotalScore)"
}

# ==== Phase 4: Add hot sector constituents (limited) ====
Write-Host "`n=== Phase 4: Sector constituents (limited) ==="
$sectorAddedCount = 0
foreach ($hs in $hotSectors) {
    $constituents = Get-SectorConstituents -SectorCode $hs.SectorCode -MaxCount $StocksPerSector
    if ($constituents) {
        $added = 0
        foreach ($c in $constituents) {
            if ($c.Code -and (-not $poolStocks.ContainsKey($c.Code))) {
                $broadInd = $INDUSTRY_MAP[$hs.SectorName]
                if (-not $broadInd) { $broadInd = $hs.SectorName }
                $poolStocks[$c.Code] = @{
                    Code     = $c.Code
                    Name     = $c.Name
                    Industry = $broadInd
                    Source   = "sector_$($hs.SectorName)"
                }
                $added++
            }
        }
        Write-Host "    $($hs.SectorName): added $added stocks"
        $sectorAddedCount += $added
    } else {
        Write-Warning "    $($hs.SectorName): failed to get constituents"
    }
}

# ==== Phase 5: Output ====
Write-Host "`n=== Phase 5: Output ==="
$poolArray = $poolStocks.Values | ForEach-Object {
    [PSCustomObject]@{
        Code     = $_.Code
        Name     = $_.Name
        Industry = $_.Industry
        Source   = $_.Source
    }
}

$pct = if ($poolArray.Count -gt 0) { [math]::Round($coreCount / $poolArray.Count * 100, 0) } else { 0 }
Write-Host "  Dynamic pool: $($poolArray.Count) stocks (core: $coreCount, sector-added: $sectorAddedCount)"
Write-Host "  Core ratio: $pct%"

$output = @{
    BuildTime    = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
    TotalCount   = $poolArray.Count
    SectorCount  = $hotSectors.Count
    HotSectors   = $hotSectors | Select-Object SectorName, ChangePct, Turnover, TotalScore
    CoreCount    = $coreCount
    Stocks       = $poolArray
}

$json = $output | ConvertTo-Json -Depth 3
[System.IO.File]::WriteAllText($OutputFile, $json, [System.Text.Encoding]::UTF8)
Write-Host "  Output: $OutputFile"
Write-Host "Done"
