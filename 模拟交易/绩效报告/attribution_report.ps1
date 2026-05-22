<#
.SYNOPSIS
    Attribution Analysis Report for Simulated Trading -- v1.1
.DESCRIPTION
    Multi-dimensional attribution analysis based on transactions, snapshots
    and evaluation data.
      a) Per-stock PnL contribution
      b) Per-prediction direction effectiveness
      c) Per-score-segment performance
      d) Per-exit-reason breakdown
    Corresponds to: post-eval whitepaper S4 Performance Metrics
.PARAMETER RootDir
    Project root directory (with Chinese chars, pass explicitly)
.PARAMETER OutputFile
    Optional JSON output path
.PARAMETER Compact
    Compact output mode (tables only)
.EXAMPLE
    .\attribution_report.ps1 -RootDir "C:\path\to\gupiao_fenxi"
    .\attribution_report.ps1 -RootDir "C:\path\to\gupiao_fenxi" -OutputFile result.json
#>
[CmdletBinding()]
param(
    [string]$RootDir = "",
    [string]$OutputFile = "",
    [switch]$Compact = $false
)

# NOTE: This script must be saved as UTF-8 with BOM for PowerShell to handle
# Chinese characters in string literals correctly on non-English systems.
# If you see garbled paths, re-save the file with UTF-8 BOM encoding.

if ([string]::IsNullOrEmpty($RootDir)) {
    Write-Error "RootDir is required. Usage: attribution_report.ps1 -RootDir `"C:\Users\34269\Documents\Claude\gupiao_fenxi`""
    exit 1
}

# ============================================================
# PATH SETUP - all paths constructed from RootDir parameter
# ============================================================
$simDir = Join-Path $RootDir "模拟交易"
$txnFile = Join-Path $simDir "持仓记录/transactions.csv"
$posFile = Join-Path $simDir "持仓记录/positions.json"
$perfFile = Join-Path $simDir "绩效报告/perf_summary.json"
$configFile = Join-Path $simDir "sim_config.json"
$snapshotDir = Join-Path $simDir "每日快照"
$evalDir = Join-Path $RootDir "重点股票/次日评估"

# ============================================================
# CONFIG
# ============================================================
$config = Get-Content $configFile -Raw -Encoding UTF8 | ConvertFrom-Json
$initialCapital = [double]$config.InitialCapital

# ============================================================
# SCORE SEGMENTS
# ============================================================
$scoreSegments = @(
    @{ Label = "Exc(>=80)";    Min = 80; Max = 100 }
    @{ Label = "Good(65-79)";  Min = 65; Max = 79  }
    @{ Label = "Avg(45-64)";   Min = 45; Max = 64  }
    @{ Label = "Poor(30-44)";  Min = 30; Max = 44  }
    @{ Label = "Bad(<30)";     Min = 0;  Max = 29  }
)

function Write-Banner {
    param([string]$T, [string]$C = "=", [int]$W = 72)
    $p = [Math]::Max(0, ($W - $T.Length - 2) / 2)
    $C * $W | Write-Output
    if ($p -gt 0) { (" " * [Math]::Floor($p)) + " " + $T + " " + (" " * [Math]::Ceiling($p)) | Write-Output }
    else { $T | Write-Output }
    $C * $W | Write-Output
}

function Write-SH {
    param([string]$T)
    $d = 68 - $T.Length
    if ($d -lt 0) { $d = 0 }
    "`n--- " + $T + " " + ("-" * $d) | Write-Output
}

function FmtP {
    param([double]$V)
    if ($V -ge 0) { return "+$([Math]::Round($V, 2))%" }
    return "$([Math]::Round($V, 2))%"
}

function FmtY {
    param([double]$V)
    if ($V -ge 0) { return "+Y$([Math]::Round($V, 2))" }
    return "-Y$([Math]::Abs([Math]::Round($V, 2)))"
}

# ============================================================
# LOAD DATA
# ============================================================
Write-Output "[INFO] Loading data..."
if (-not (Test-Path $txnFile)) { Write-Error "No txns: $txnFile"; exit 1 }
$allTxns = Import-Csv $txnFile | ForEach-Object {
    [PSCustomObject]@{
        Date = $_.date; Code = $_.code; Name = $_.name
        Action = $_.action; Price = [double]$_.price; Shares = [int]$_.shares
        Amount = [double]$_.amount; Commission = [double]$_.commission
        StampTax = [double]$_.stamp_tax; TotalCost = [double]$_.total_cost
        Reason = $_.reason; EntryPrediction = $_.entry_prediction
    }
}
Write-Output "  Txns: $($allTxns.Count)"

$snapshots = @()
if (Test-Path $snapshotDir) {
    Get-ChildItem $snapshotDir -Filter "snapshot_*.json" | Sort-Object Name | ForEach-Object {
        $snapshots += Get-Content $_.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
    }
}
Write-Output "  Snapshots: $($snapshots.Count)"

$curPos = @{}
if (Test-Path $posFile) {
    $pd = Get-Content $posFile -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($pd.Positions) {
        $pd.Positions.PSObject.Properties | ForEach-Object { $curPos[$_.Name] = $_.Value }
    }
}
Write-Output "  Holdings: $($curPos.Count)"

$perf = $null
if (Test-Path $perfFile) { $perf = Get-Content $perfFile -Raw -Encoding UTF8 | ConvertFrom-Json }

# ============================================================
# EVAL DATA CACHE
# ============================================================
$evalCache = @{}
function Get-Eval {
    param([string]$D)
    if ($evalCache.ContainsKey($D)) { return $evalCache[$D] }
    # Try configured eval dir first
    $f = Join-Path $evalDir ("评估数据_$D.json")
    if ((Test-Path $f)) {
        try {
            $d = Get-Content $f -Raw -Encoding UTF8 | ConvertFrom-Json
            $m = @{}; $d.Stocks | ForEach-Object { $m[$_.Code] = $_ }
            $evalCache[$D] = $m; return $m
        } catch { }
    }
    # Fallback: search for JSON files matching date pattern
    $searchRoot = Split-Path $RootDir -Parent
    $candidates = @(Get-ChildItem $searchRoot -Filter "*_${D}.json" -Recurse -ErrorAction SilentlyContinue)
    foreach ($ef in $candidates) {
        try {
            $testData = Get-Content $ef.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($testData.Stocks -and $testData.Date -eq $D) {
                $m = @{}; $testData.Stocks | ForEach-Object { $m[$_.Code] = $_ }
                $evalCache[$D] = $m; return $m
            }
        } catch { continue }
    }
    $evalCache[$D] = $null; return $null
}

# ============================================================
# HEADER
# ============================================================
Write-Banner -T "Attribution Analysis Report"
if (-not $Compact) {
    $rd = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "Generated: ${rd}" | Write-Output
    "Initial Capital: Y$([Math]::Round($initialCapital, 2))" | Write-Output
    if ($perf) {
        "Current Value: Y$([Math]::Round($perf.CurrentValue, 2))" | Write-Output
        "Total Return: $(FmtP $perf.TotalReturnPct)" | Write-Output
        "Max DD: $(FmtP $perf.MaxDrawdown)" | Write-Output
        "Total Trades: $($perf.TotalTrades)" | Write-Output
        "Win Rate: $($perf.WinRate)%" | Write-Output
    }
}

# ============================================================
# STEP 1: PER-STOCK (FIFO matching)
# ============================================================
Write-SH -T "1. Per-Stock Attribution"

$stockGrps = $allTxns | Group-Object Code
$perStk = @()
$allTradePnLs = @()

foreach ($grp in $stockGrps) {
    $code = $grp.Name
    $txns = $grp.Group | Sort-Object Date
    $name = $txns[0].Name
    $buyQ = @(); $rPnL = 0; $wCt = 0; $lCt = 0

    foreach ($t in $txns) {
        if ($t.Action -eq "BUY") {
            $buyQ += @{ S=$t.Shares; C=$t.Price; D=$t.Date; P=$t.EntryPrediction }
        } elseif ($t.Action -eq "SELL_HALF") {
            $rem = $t.Shares; $nq = @()
            foreach ($lot in $buyQ) {
                if ($rem -le 0) { $nq += $lot; continue }
                if ($lot.S -le $rem) { $rPnL += ($t.Price - $lot.C) * $lot.S; $rem -= $lot.S }
                else { $rPnL += ($t.Price - $lot.C) * $rem; $lot.S -= $rem; $nq += $lot; $rem = 0 }
            }
            $buyQ = $nq
        } elseif ($t.Action -eq "SELL") {
            $rem = $t.Shares; $nq = @(); $trPnL = 0
            foreach ($lot in $buyQ) {
                if ($rem -le 0) { $nq += $lot; continue }
                if ($lot.S -le $rem) { $p = ($t.Price - $lot.C) * $lot.S; $trPnL += $p; $rPnL += $p; $rem -= $lot.S }
                else { $p = ($t.Price - $lot.C) * $rem; $trPnL += $p; $rPnL += $p; $lot.S -= $rem; $nq += $lot; $rem = 0 }
            }
            $buyQ = $nq
            if ($trPnL -gt 0) { $wCt++ } else { $lCt++ }
            $allTradePnLs += @{ Code=$code; Name=$name; PnL=$trPnL; ExitDate=$t.Date; ExitReason=$t.Reason }
        }
    }

    $uPnL = 0; $cShr = 0
    if ($curPos.ContainsKey($code)) { $p = $curPos[$code]; $cShr = [int]$p.Shares; $uPnL = [double]$p.UnrealizedPnL }
    $totTr = $wCt + $lCt
    $wr = if ($totTr -gt 0) { [Math]::Round($wCt/$totTr*100,1) } else { $null }
    $avgPnL = if ($totTr -gt 0) { [Math]::Round($rPnL/$totTr,2) } else { $null }

    $perStk += [PSCustomObject]@{
        Code=$code; Name=$name; Tr=$totTr; W=$wCt; L=$lCt; WR=$wr
        RPnL=[Math]::Round($rPnL,2); AvgPnL=$avgPnL
        UPnL=[Math]::Round($uPnL,2); TPnL=[Math]::Round($rPnL+$uPnL,2); Shr=$cShr
    }
}
if ($perStk.Count -eq 0) { Write-Output "  (no data)" }

$perStk = $perStk | Sort-Object TPnL -Descending
"{0,-8} {1,-12} {2,5} {3,5} {4,5} {5,7} {6,11} {7,11} {8,11} {9,7}" -f
    "Code","Name","Trd","Win","Lse","Win%","RealPnL","UnrealPnL","TotalPnL","Shrs" | Write-Output
"-"*90 | Write-Output
foreach ($s in $perStk) {
    $ws = if ($s.WR -ne $null) { "$($s.WR)%" } else { "N/A" }
    "{0,-8} {1,-12} {2,5} {3,5} {4,5} {5,7} {6,11} {7,11} {8,11} {9,7}" -f
        $s.Code,$s.Name,$s.Tr,$s.W,$s.L,$ws,(FmtY $s.RPnL),(FmtY $s.UPnL),(FmtY $s.TPnL),$s.Shr | Write-Output
}
$tTrAll = ($perStk | Measure-Object Tr -Sum).Sum
$tRAll = ($perStk | Measure-Object RPnL -Sum).Sum
$tUAll = ($perStk | Measure-Object UPnL -Sum).Sum
$tPAll = ($perStk | Measure-Object TPnL -Sum).Sum
"-"*90 | Write-Output
"{0,-8} {1,-12} {2,5} {3,5} {4,5} {5,7} {6,11} {7,11} {8,11}" -f
    "TOTAL","",$tTrAll,"","","",(FmtY $tRAll),(FmtY $tUAll),(FmtY $tPAll) | Write-Output

# ============================================================
# STEP 2: PER-PREDICTION
# ============================================================
Write-SH -T "2. Per-Prediction Attribution"

$predGrps = @{}; $matchTr = @()
foreach ($grp in $stockGrps) {
    $txns = $grp.Group | Sort-Object Date; $buyQ = @()
    foreach ($t in $txns) {
        if ($t.Action -eq "BUY") { $buyQ += @{ P=$t.EntryPrediction; S=$t.Shares; Pr=$t.Price } }
        elseif ($t.Action -eq "SELL") {
            $rem = $t.Shares; $pUsed = @{}
            while ($rem -gt 0 -and $buyQ.Count -gt 0) {
                $mb = $buyQ[0]; $stm = [Math]::Min($rem, $mb.S)
                $pp = ($t.Price - $mb.Pr) * $stm
                $d = $mb.P
                if (-not $pUsed.ContainsKey($d)) { $pUsed[$d] = @{S=0;P=0} }
                $pUsed[$d].S += $stm; $pUsed[$d].P += $pp
                $mb.S -= $stm; $rem -= $stm
                if ($mb.S -le 0) { $buyQ = $buyQ | Select-Object -Skip 1 }
            }
            foreach ($d in $pUsed.Keys) {
                $matchTr += @{ Dir=$d; PnL=$pUsed[$d].P }
                if (-not $predGrps.ContainsKey($d)) { $predGrps[$d] = @{T=0;W=0;L=0;P=0} }
                $predGrps[$d].T++
                if ($pUsed[$d].P -gt 0) { $predGrps[$d].W++ } else { $predGrps[$d].L++ }
                $predGrps[$d].P += $pUsed[$d].P
            }
        } elseif ($t.Action -eq "SELL_HALF") {
            $rem = $t.Shares
            while ($rem -gt 0 -and $buyQ.Count -gt 0) {
                $mb = $buyQ[0]; $stm = [Math]::Min($rem, $mb.S)
                $pp = ($t.Price - $mb.Pr) * $stm; $d = $mb.P
                if (-not $predGrps.ContainsKey($d)) { $predGrps[$d] = @{T=0;W=0;L=0;P=0} }
                $predGrps[$d].P += $pp
                $mb.S -= $stm; $rem -= $stm
                if ($mb.S -le 0) { $buyQ = $buyQ | Select-Object -Skip 1 }
            }
        }
    }
}

$openPredPnL = @{}
foreach ($code in $curPos.Keys) {
    $p = $curPos[$code]; $pred = $p.EntryShortPrediction
    if (-not $pred) { continue }
    $u = [double]$p.UnrealizedPnL
    if (-not $openPredPnL.ContainsKey($pred)) { $openPredPnL[$pred] = 0 }
    $openPredPnL[$pred] += $u
}

$allDirs = ($predGrps.Keys + $openPredPnL.Keys) | Sort-Object -Unique
if ($allDirs.Count -eq 0) { Write-Output "  (no data)" }
"{0,-16} {1,7} {2,5} {3,5} {4,7} {5,13} {6,13}" -f
    "Direction","Trd","Win","Lse","Win%","Realized","Unreal" | Write-Output
"-"*70 | Write-Output
foreach ($d in $allDirs) {
    $g = $predGrps[$d]; $tt = if ($g) { $g.T } else { 0 }; $ww = if ($g) { $g.W } else { 0 }; $ll = if ($g) { $g.L } else { 0 }
    $rp = if ($g) { [Math]::Round($g.P,2) } else { 0 }
    $up = if ($openPredPnL.ContainsKey($d)) { [Math]::Round($openPredPnL[$d],2) } else { 0 }
    $wr = if ($tt -gt 0) { "$([Math]::Round($ww/$tt*100,1))%" } else { "N/A" }
    "{0,-16} {1,7} {2,5} {3,5} {4,7} {5,13} {6,13}" -f $d,$tt,$ww,$ll,$wr,(FmtY $rp),(FmtY $up) | Write-Output
}

# ============================================================
# STEP 3: PER-SCORE-SEGMENT
# ============================================================
Write-SH -T "3. Per-Score-Segment Attribution"

$segR = @{}
foreach ($seg in $scoreSegments) { $segR[$seg.Label] = @{T=0;W=0;L=0;P=0} }
$segR["Unknown"] = @{T=0;W=0;L=0;P=0}

foreach ($grp in $stockGrps) {
    $txns = $grp.Group | Sort-Object Date; $buyQ = @()
    foreach ($t in $txns) {
        if ($t.Action -eq "BUY") {
            $ev = Get-Eval -D $t.Date; $sc = $null
            if ($ev -and $ev.ContainsKey($t.Code)) { $se = $ev[$t.Code]; if ($se.Scores) { $sc = [double]$se.Scores.Composite } }
            $buyQ += @{ S=$t.Shares; Pr=$t.Price; Sc=$sc }
        } elseif ($t.Action -eq "SELL") {
            $rem = $t.Shares
            while ($rem -gt 0 -and $buyQ.Count -gt 0) {
                $mb = $buyQ[0]; $stm = [Math]::Min($rem, $mb.S); $pp = ($t.Price - $mb.Pr) * $stm
                $sl = "Unknown"
                if ($mb.Sc -ne $null) { foreach ($seg in $scoreSegments) { if ($mb.Sc -ge $seg.Min -and $mb.Sc -le $seg.Max) { $sl = $seg.Label; break } } }
                if (-not $segR.ContainsKey($sl)) { $segR[$sl] = @{T=0;W=0;L=0;P=0} }
                $segR[$sl].T++; if ($pp -gt 0) { $segR[$sl].W++ } else { $segR[$sl].L++ }; $segR[$sl].P += $pp
                $mb.S -= $stm; $rem -= $stm; if ($mb.S -le 0) { $buyQ = $buyQ | Select-Object -Skip 1 }
            }
        } elseif ($t.Action -eq "SELL_HALF") {
            $rem = $t.Shares
            while ($rem -gt 0 -and $buyQ.Count -gt 0) {
                $mb = $buyQ[0]; $stm = [Math]::Min($rem, $mb.S); $pp = ($t.Price - $mb.Pr) * $stm
                $sl = "Unknown"
                if ($mb.Sc -ne $null) { foreach ($seg in $scoreSegments) { if ($mb.Sc -ge $seg.Min -and $mb.Sc -le $seg.Max) { $sl = $seg.Label; break } } }
                if (-not $segR.ContainsKey($sl)) { $segR[$sl] = @{T=0;W=0;L=0;P=0} }
                $segR[$sl].P += $pp; $mb.S -= $stm; $rem -= $stm
                if ($mb.S -le 0) { $buyQ = $buyQ | Select-Object -Skip 1 }
            }
        }
    }
}

$hasSeg = $false
foreach ($seg in $scoreSegments) { $r = $segR[$seg.Label]; if ($r -and ($r.T -gt 0 -or $r.P -ne 0)) { $hasSeg = $true; break } }
if (-not $hasSeg) { Write-Output "  (no completed trades for segment analysis)" } else {
    "{0,-16} {1,7} {2,5} {3,5} {4,7} {5,13}" -f "Seg","Trd","Win","Lse","Win%","TotalPnL" | Write-Output
    "-"*60 | Write-Output
    foreach ($seg in $scoreSegments) {
        $r = $segR[$seg.Label]; if (-not $r) { continue }
        $wr = if ($r.T -gt 0) { "$([Math]::Round($r.W/$r.T*100,1))%" } else { "N/A" }
        "{0,-16} {1,7} {2,5} {3,5} {4,7} {5,13}" -f $seg.Label,$r.T,$r.W,$r.L,$wr,(FmtY $r.P) | Write-Output
    }
    if ($segR.ContainsKey("Unknown") -and $segR["Unknown"].P -ne 0) {
        $r = $segR["Unknown"]; "{0,-16} {1,7} {2,5} {3,5} {4,7} {5,13}" -f "Unknown",$r.T,$r.W,$r.L,"N/A",(FmtY $r.P) | Write-Output
    }
}

# ============================================================
# STEP 4: PER-EXIT-REASON
# ============================================================
Write-SH -T "4. Per-Exit-Reason Attribution"

$exitGrps = @{}
foreach ($t in $allTxns) {
    if ($t.Action -ne "SELL") { continue }
    $r = $t.Reason; $cat = "Other"
    if ($r -match "StopLoss") { $cat = "P1-StopLoss" }
    elseif ($r -match "危险") { $cat = "P2-TrendWorsen" }
    elseif ($r -match "预判转空") { $cat = "P3-PredTurn" }
    elseif ($r -match "R3") { $cat = "P4-FullTP" }
    elseif ($r -match "R2") { $cat = "P5-HalfTP" }
    $mp = 0
    foreach ($tp in $allTradePnLs) { if ($tp.ExitDate -eq $t.Date -and $tp.Code -eq $t.Code) { $mp = $tp.PnL; break } }
    if ($mp -eq 0) { foreach ($mt in $matchTr) { if ($mt.ExitReason -eq $t.Reason) { $mp += $mt.PnL } } }
    if (-not $exitGrps.ContainsKey($cat)) { $exitGrps[$cat] = @{C=0;P=0;W=0;L=0} }
    $exitGrps[$cat].C++; $exitGrps[$cat].P += $mp; if ($mp -gt 0) { $exitGrps[$cat].W++ } else { $exitGrps[$cat].L++ }
}
if ($exitGrps.Keys.Count -eq 0) { Write-Output "  (no completed trades)" } else {
    "{0,-20} {1,7} {2,7} {3,7} {4,13}" -f "Reason","Count","Wins","Loss","TotalPnL" | Write-Output
    "-"*60 | Write-Output
    foreach ($k in ($exitGrps.Keys | Sort-Object)) { $g = $exitGrps[$k]; "{0,-20} {1,7} {2,7} {3,7} {4,13}" -f $k,$g.C,$g.W,$g.L,(FmtY $g.P) | Write-Output }
}

# ============================================================
# STEP 5: DIMENSION EFFECTIVENESS
# ============================================================
Write-SH -T "5. Dimension Effectiveness"

$dimSamples = @()
foreach ($t in $allTxns) {
    if ($t.Action -ne "BUY") { continue }
    $ev = Get-Eval -D $t.Date
    if (-not $ev -or -not $ev.ContainsKey($t.Code)) { continue }
    $se = $ev[$t.Code]; if (-not $se.Scores) { continue }
    $s = @{ C=$t.Code; D=$t.Date; Pr=$t.Price
        Co=[double]$se.Scores.Composite; Te=[double]$se.Scores.Technical
        Fu=[double]$se.Scores.Fundamental; Se2=[double]$se.Scores.Sentiment
        Ca=[double]$se.Scores.Capital; Sc=[double]$se.Scores.Sector; Ma=[double]$se.Scores.Macro
    }
    $nxt = (Get-Date $t.Date).AddDays(1).ToString("yyyyMMdd")
    $ev2 = Get-Eval -D $nxt
    if ($ev2 -and $ev2.ContainsKey($t.Code)) { $ns = $ev2[$t.Code]
        if ($ns.Price -and $t.Price -gt 0) { $s.Ret = [Math]::Round(($ns.Price/$t.Price-1)*100,2) }
        else { $s.Ret = $null }
    } else { $s.Ret = $null }
    $dimSamples += $s
}

if ($dimSamples.Count -gt 0) {
    $dims = @("Co","Te","Fu","Se2","Ca","Sc","Ma")
    $dN = @{Co="Composite";Te="Technical";Fu="Fundamental";Se2="Sentiment";Ca="Capital";Sc="Sector";Ma="Macro"}
    "{0,-14} {1,7} {2,11} {3,13}" -f "Dim","N","AvgRet%","Win%" | Write-Output
    "-"*50 | Write-Output
    foreach ($dm in $dims) {
        $vs = $dimSamples | Where-Object { $_.$dm -ne $null -and $_.Ret -ne $null }
        $ct = ($vs | Measure-Object).Count
        if ($ct -eq 0) { "{0,-14} {1,7} {2,11} {3,13}" -f $dN[$dm],0,"N/A","N/A" | Write-Output; continue }
        $avg = ($vs | Measure-Object Ret -Average).Average
        $pos = ($vs | Where-Object { $_.Ret -gt 0 } | Measure-Object).Count
        $pp = [Math]::Round($pos/$ct*100,1)
        "{0,-14} {1,7} {2,11} {3,13}" -f $dN[$dm],$ct,(FmtP $avg),"$pp%" | Write-Output
    }
} else { Write-Output "  (insufficient data)" }

# ============================================================
# STEP 6: PORTFOLIO RISK
# ============================================================
Write-SH -T "6. Portfolio Risk Metrics"

if ($snapshots.Count -ge 2) {
    $dr = @(); $pv = $null
    foreach ($snap in ($snapshots | Sort-Object Date)) {
        $v = [double]$snap.TotalValue
        if ($pv -ne $null -and $pv -gt 0) { $dr += ($v/$pv-1)*100 }
        $pv = $v
    }
    if ($dr.Count -gt 0) {
        $adr = ($dr | Measure-Object -Average).Average; $sdr = 0
        if ($dr.Count -gt 1) {
            $vr = ($dr | ForEach-Object { ($_-$adr)*($_-$adr) } | Measure-Object -Sum).Sum / ($dr.Count-1)
            $sdr = [Math]::Sqrt($vr)
        }
        $rf = 2.5/252; $ex = $adr - $rf
        $sr = if ($sdr -gt 0) { [Math]::Round($ex/$sdr*[Math]::Sqrt(252),2) } else { $null }
        "  Avg Daily: $(FmtP $adr)" | Write-Output
        "  Daily Std: $([Math]::Round($sdr,2))%" | Write-Output
        "  Sharpe(ann,Rf=2.5%): $(if ($sr) { $sr } else { 'N/A' })" | Write-Output
        $mcl = 0; $ccl = 0
        foreach ($r in $dr) { if ($r -lt 0) { $ccl++ } else { $ccl=0 }; if ($ccl -gt $mcl) { $mcl=$ccl } }
        "  Max Consec Loss Days: $mcl" | Write-Output
    }
} else { Write-Output "  (need >=2 snapshots)" }

# ============================================================
# STEP 7: ENTRY SCORE REVIEW
# ============================================================
Write-SH -T "7. Entry Score Review"

if ($perStk.Count -gt 0) {
    "{0,-8} {1,-12} {2,7} {3,7} {4,7} {5,7} {6,7} {7,9} {8,13}" -f "Code","Name","Comp","Tech","Fund","Sent","Cap","Pred","TotalPnL" | Write-Output
    "-"*85 | Write-Output
    foreach ($s in $perStk) {
        $bt = $allTxns | Where-Object { $_.Code -eq $s.Code -and $_.Action -eq "BUY" } | Sort-Object Date -Descending
        $ls = $null; $lp = ""
        if ($bt.Count -gt 0) {
            $ev = Get-Eval -D $bt[0].Date
            if ($ev -and $ev.ContainsKey($s.Code)) { $se = $ev[$s.Code]; if ($se.Scores) { $ls = $se.Scores }; if ($se.Prediction) { $lp = $se.Prediction.Short } }
        }
        $cs = if ($ls) { "$($ls.Composite)" } else { "N/A" }; $ts = if ($ls) { "$($ls.Technical)" } else { "N/A" }
        $fs = if ($ls) { "$($ls.Fundamental)" } else { "N/A" }; $ss = if ($ls) { "$($ls.Sentiment)" } else { "N/A" }
        $cas = if ($ls) { "$($ls.Capital)" } else { "N/A" }
        "{0,-8} {1,-12} {2,7} {3,7} {4,7} {5,7} {6,7} {7,9} {8,13}" -f $s.Code,$s.Name,$cs,$ts,$fs,$ss,$cas,$lp,(FmtY $s.TPnL) | Write-Output
    }
}

# ============================================================
# STEP 8: PerStock FIELD CHECK
# ============================================================
Write-SH -T "8. PerStock Field Completeness"

"  Current perf_summary.json PerStock: empty object {}" | Write-Output
"  Engine never populates PerStock (sim_trading.ps1 Step 13)." | Write-Output
"" | Write-Output
"  Missing fields to add:" | Write-Output
"    - Trades, WinningTrades, LosingTrades, WinRate" | Write-Output
"    - TotalRealizedPnL, AvgRealizedPnL" | Write-Output
"    - TotalUnrealizedPnL, TotalPnL" | Write-Output
"    - AvgEntryScore, MaxDrawdown" | Write-Output
"    - Predictions (array of entry prediction labels)" | Write-Output

# ============================================================
# SUMMARY
# ============================================================
Write-Banner -T "Attribution Summary"
"  Realized: $(FmtY $tRAll)" | Write-Output
"  Unrealized: $(FmtY $tUAll)" | Write-Output
"  Combined: $(FmtY ($tRAll+$tUAll))" | Write-Output
"  Stocks: $($perStk.Count)" | Write-Output
"  Completed Trades: $tTrAll" | Write-Output

if ($perStk.Count -gt 0) {
    $best = $perStk | Sort-Object TPnL -Descending | Select-Object -First 1
    $worst = $perStk | Sort-Object TPnL | Select-Object -First 1
    "  Best: $($best.Name) ($(FmtY $best.TPnL))" | Write-Output
    "  Worst: $($worst.Name) ($(FmtY $worst.TPnL))" | Write-Output
    $most = $perStk | Sort-Object Tr -Descending | Select-Object -First 1
    if ($most.Tr -gt 0) { "  Most Active: $($most.Name) ($($most.Tr) trades)" | Write-Output }
}
$bestDir = $null; $bestDirP = -999999
foreach ($d in $predGrps.Keys) { if ($predGrps[$d].P -gt $bestDirP) { $bestDirP = $predGrps[$d].P; $bestDir = $d } }
if ($bestDir) { "  Best Prediction: $bestDir ($(FmtY $bestDirP))" | Write-Output }

# ============================================================
# OPTIONAL JSON OUTPUT
# ============================================================
if ($OutputFile) {
    $op = if ([System.IO.Path]::IsPathRooted($OutputFile)) { $OutputFile } else { Join-Path (Get-Location).Path $OutputFile }
    $rPS=@{}; foreach($s in $perStk){$rPS[$s.Code]=@{Name=$s.Name;Trades=$s.Tr;Wins=$s.W;Losses=$s.L;WinRate=$s.WR;RealPnL=$s.RPnL;AvgPnL=$s.AvgPnL;UnrealPnL=$s.UPnL;TotalPnL=$s.TPnL}}
    $rPP=@{}; foreach($d in $predGrps.Keys){$g=$predGrps[$d];$rPP[$d]=@{Trades=$g.T;Wins=$g.W;Losses=$g.L;TotalPnL=[Math]::Round($g.P,2)}}
    $rPSeg=@{}; foreach($seg in $scoreSegments){$r=$segR[$seg.Label];if($r-and($r.T-gt0-or$r.P-ne0)){$rPSeg[$seg.Label]=@{Trades=$r.T;Wins=$r.W;Losses=$r.L;TotalPnL=[Math]::Round($r.P,2)}}}
    $rPE=@{}; foreach($k in $exitGrps.Keys){$g=$exitGrps[$k];$rPE[$k]=@{Count=$g.C;Wins=$g.W;Losses=$g.L;TotalPnL=[Math]::Round($g.P,2)}}
    $result=@{GeneratedAt=(Get-Date -Format "yyyy-MM-dd HH:mm:ss");PerStock=$rPS;PerPrediction=$rPP;PerScoreSegment=$rPSeg;PerExitReason=$rPE;Summary=@{Realized=[Math]::Round($tRAll,2);Unrealized=[Math]::Round($tUAll,2);Total=[Math]::Round($tRAll+$tUAll,2);Trades=$tTrAll;Stocks=$perStk.Count}}
    $result | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 $op
    "`n[INFO] JSON written: $op" | Write-Output
}
"`n[DONE]" | Write-Output
