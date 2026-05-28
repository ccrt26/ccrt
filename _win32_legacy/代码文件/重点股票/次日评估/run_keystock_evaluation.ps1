# 重点股票分析逻辑后评估引擎
# 基于：重点股票次日后评估白皮书 v1.7
# 核心：复盘分析逻辑有效性，而非个股涨跌对错
# 输入：前日分析报告评估数据JSON + 当日行情
# 输出：逻辑诊断报告PDF + 知识积累文件更新

param(
    [string]$PreviousDate = "",    # 被评估的报告日期 YYYYMMDD，默认昨天
    [switch]$KeepHtml = $false      # 保留中间HTML文件
)
. "$PSScriptRoot/../../lib/init_encoding.ps1"

# ============================================================
# 配置
# ============================================================
$rootDir = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$evalRoot = Join-Path $rootDir "重点股票\次日评估"
$modulePath = Join-Path $rootDir "代码文件\每日荐股\scripts\stock_data_fetcher.psm1"
$edgePath = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
$reportDir = Join-Path $evalRoot "复盘报告"
$logicDir = Join-Path $evalRoot "逻辑积累"
$trackFile = Join-Path $logicDir "指标有效性跟踪.csv"
$improveLog = Join-Path $logicDir "改进日志.md"
$suggestFile = Join-Path $logicDir "优化建议.json"
$resultDir = Join-Path $evalRoot "评估结果"

# 确保目录存在
foreach ($d in @($reportDir, $logicDir, $resultDir)) {
    if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
}

# v1.7 新增目录
$linkageLogDir = Join-Path $evalRoot "逻辑积累\联动日志"
$attributionDir = Join-Path $evalRoot "逻辑积累\失效归因"
$metabolismDir = Join-Path $evalRoot "逻辑积累\知识代谢"
$distillationDir = Join-Path $evalRoot "逻辑积累\知识蒸馏"
$combRulesDir = Join-Path $evalRoot "逻辑积累\条件规则"
$experimentDir = Join-Path $evalRoot "逻辑积累\实验提案"
foreach ($d in @($linkageLogDir, $attributionDir, $metabolismDir, $distillationDir, $combRulesDir, $experimentDir)) {
    if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
}

# 日期处理
$today = Get-Date
if ($PreviousDate -ne "") {
    $prevDate = [DateTime]::ParseExact($PreviousDate, "yyyyMMdd", [System.Globalization.CultureInfo]::InvariantCulture)
} else {
    $prevDate = $today.AddDays(-1)
}
$prevDateStr = $prevDate.ToString("yyyyMMdd")
$todayStr = $today.ToString("yyyyMMdd")
$todayLabel = $today.ToString("yyyy-MM-dd")
$prevLabel = $prevDate.ToString("yyyy-MM-dd")

# API节流
$script:apiCallCount = 0
function Invoke-ThrottledApi($scriptBlock) {
    Start-Sleep -Milliseconds 300
    $script:apiCallCount++
    if ($script:apiCallCount % 10 -eq 0) { Start-Sleep -Seconds 2 }
    return & $scriptBlock
}

# ============================================================
# 导入
# ============================================================
if (-not (Test-Path $modulePath)) {
    Write-Error "Module not found: $modulePath"; exit 1
}
Import-Module $modulePath -Force -WarningAction SilentlyContinue 2>$null
Write-Host "✅ 数据模块已导入 ($(Get-Date -Format 'HH:mm:ss'))"

# ============================================================
# 辅助函数
# ============================================================

# 计算 Spearman 秩相关系数
function Get-SpearmanR {
    param([double[]]$X, [double[]]$Y)
    $n = $X.Length
    if ($n -lt 3) { return 0, 0 }
    # Rank function
    function Get-Ranks([double[]]$arr) {
        $n = $arr.Count
        $indexed = @(for ($i=0; $i -lt $n; $i++) { [PSCustomObject]@{Idx=$i; Val=$arr[$i]} })
        $sorted = $indexed | Sort-Object Val
        $ranks = New-Object double[] $n
        $j = 0
        while ($j -lt $n) {
            $k = $j
            while ($k+1 -lt $n -and [Math]::Abs($sorted[$k+1].Val - $sorted[$j].Val) -lt 1e-10) { $k++ }
            $avgRank = ($j + $k) / 2.0 + 1
            for ($t = $j; $t -le $k; $t++) { $ranks[$sorted[$t].Idx] = $avgRank }
            $j = $k + 1
        }
        return $ranks
    }
    $rankX = Get-Ranks $X
    $rankY = Get-Ranks $Y
    $meanRx = ($rankX | Measure-Object -Average).Average
    $meanRy = ($rankY | Measure-Object -Average).Average
    $cov = 0.0; $varX = 0.0; $varY = 0.0
    for ($i = 0; $i -lt $n; $i++) {
        $dx = $rankX[$i] - $meanRx
        $dy = $rankY[$i] - $meanRy
        $cov += $dx * $dy
        $varX += $dx * $dx
        $varY += $dy * $dy
    }
    $denom = [Math]::Sqrt($varX * $varY)
    if ($denom -eq 0) { return 0, $n }
    $rho = $cov / $denom
    return [Math]::Round($rho, 4), $n
}

# 计算 ICIR (Information Coefficient Information Ratio)
function Get-ICIR {
    param([double[]]$ICValues)
    if ($ICValues.Count -lt 2) { return 0 }
    $meanIC = ($ICValues | Measure-Object -Average).Average
    $stdIC = [Math]::Sqrt((($ICValues | ForEach-Object { [Math]::Pow($_ - $meanIC, 2) }) | Measure-Object -Average).Average)
    if ($stdIC -eq 0) { return 0 }
    return [Math]::Round($meanIC / $stdIC, 3)
}

# 信号胜率分析
function Get-SignalWinRate {
    param($MatchedList, $SignalField, $SignalValue)
    $matching = $MatchedList | Where-Object { $_."$SignalField" -eq $SignalValue }
    $cnt = @($matching).Count
    if ($cnt -eq 0) { return @{ Count=0; Wins=0; WinRate=0 } }
    $wins = @($matching | Where-Object { $_.ReturnPct -gt 0 }).Count
    return @{ Count=$cnt; Wins=$wins; WinRate=[Math]::Round($wins/$cnt*100, 1) }
}

# 信号评级
function Get-SignalRating {
    param($WinRate)
    if ($WinRate -ge 65) { return "强有效" }
    elseif ($WinRate -ge 50) { return "有参考价值" }
    elseif ($WinRate -ge 40) { return "随机水平" }
    else { return "反向信号" }
}

# 维度有效性评级
function Get-DimensionRating {
    param($Rho)
    if ($Rho -ge 0.3) { return "有效" }
    elseif ($Rho -ge 0.15) { return "参考" }
    elseif ($Rho -ge 0) { return "微弱" }
    else { return "反向" }
}

# 阈值有效性评分
function Get-ThresholdScore {
    param($ExcellentReturn, $PoorReturn)
    $diff = $ExcellentReturn - $PoorReturn
    if ($diff -ge 2.0) { return 20 }
    elseif ($diff -ge 1.0) { return 12 }
    elseif ($diff -ge 0) { return 5 }
    else { return 0 }
}

# ============================================================
# 读取前日评估数据
# ============================================================
$evalFile = Join-Path $evalRoot "评估数据_${prevDateStr}.json"
if (-not (Test-Path $evalFile)) {
    Write-Error "未找到前日评估数据: $evalFile"
    Write-Host "请先生成前日的分析报告"
    exit 1
}
$evalDataRaw = Get-Content $evalFile -Raw -Encoding UTF8
$evalData = $evalDataRaw | ConvertFrom-Json
$stocks = $evalData.Stocks
Write-Host "✅ 已读取前日($prevLabel)评估数据: $($stocks.Count)只股票"

# ============================================================
# 读取全部历史评估数据（跨期累积）
# ============================================================
Write-Host "`n📂 扫描历史评估数据..."
$allHistFiles = Get-ChildItem (Join-Path $evalRoot "评估数据_*.json") | Sort-Object Name
$allHistoricalStocks = @()
foreach ($hf in $allHistFiles) {
    $hd = Get-Content $hf.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($hs in $hd.Stocks) {
        $allHistoricalStocks += [PSCustomObject]@{
            Date=$hd.Date; Code=$hs.Code; Name=$hs.Name
            TechScore=[double]$hs.Scores.Technical; FundScore=[double]$hs.Scores.Fundamental
            SentScore=[double]$hs.Scores.Sentiment; SectScore=[double]$hs.Scores.Sector
            CapScore=[double]$hs.Scores.Capital; MacScore=[double]$hs.Scores.Macro
            CompScore=[double]$hs.Scores.Composite; Rating=$hs.Rating
            ShortDir=$hs.Prediction.Short; MidDir=$hs.Prediction.Mid; LongDir=$hs.Prediction.Long
            Confidence=$hs.Prediction.Confidence
            Support=[double]$hs.KeyLevels.Support; Resistance=[double]$hs.KeyLevels.Resistance
            MA_Trend=$hs.Signals.MA_Trend; MACD_Position=$hs.Signals.MACD_Position
            RSI_Zone=$hs.Signals.RSI_Zone; RSI_Value=[double]$hs.Signals.RSI_Value
            Bollinger_Position=$hs.Signals.Bollinger_Position
            Volume_Relation=$hs.Signals.Volume_Relation
            ROE_Level=$hs.Signals.ROE_Level; PE_Percentile_Zone=$hs.Signals.PE_Percentile_Zone
            Debt_Level=$hs.Signals.Debt_Level
            Research_Coverage=$hs.Signals.Research_Coverage
            FundFlow_Trend=$hs.Signals.FundFlow_Trend
            ShortBull=[int]$hs.Signals.ShortBull_Score
            MidBull=[int]$hs.Signals.MidBull_Score
            LongBull=[int]$hs.Signals.LongBull_Score
        }
    }
}
Write-Host "  累计 ${#allHistoricalStocks} 条记录 (来自 $($allHistFiles.Count) 次分析)"

# ============================================================
# 采集当日行情（匹配次日收益）
# ============================================================
Write-Host "`n========== 逻辑诊断分析 =========="
Write-Host "分析日期: $todayLabel | 报告日期: $prevLabel"
Write-Host ""

$matchedResults = @()
$idx = 0

foreach ($s in $stocks) {
    $idx++
    $code = $s.Code; $name = $s.Name
    Write-Host "[$idx/$($stocks.Count)] $name($code) — 获取行情..."

    # 带重试的行情获取（API间歇不可达时最多重试3次）
    $maxRetries = 3
    $retryCount = 0
    $quote = $null
    do {
        $retryCount++
        $quote = Invoke-ThrottledApi { Get-StockQuote -Code $code }
        if ($quote -and $quote.Price -gt 0) { break }
        if ($retryCount -lt $maxRetries) {
            Write-Host "  ⚠️ 行情获取失败，${retryCount}/${maxRetries}次重试，等待2s..."
            Start-Sleep -Seconds 2
        }
    } while ($retryCount -lt $maxRetries)

    if (-not $quote -or $quote.Price -eq 0) {
        Write-Host "  ❌ 行情获取失败（${maxRetries}次重试后仍失败），跳过 $name($code)"
        continue
    }
    $returnPct = $quote.ChangePct
    Write-Host "  [行情] ¥$($quote.Price) 涨跌幅 $returnPct%"

    $matchedResults += [PSCustomObject]@{
        Date=$prevDateStr; Code=$code; Name=$name
        TechScore=[double]$s.Scores.Technical
        FundScore=[double]$s.Scores.Fundamental
        SentScore=[double]$s.Scores.Sentiment
        SectScore=[double]$s.Scores.Sector
        CapScore=[double]$s.Scores.Capital
        MacScore=[double]$s.Scores.Macro
        CompScore=[double]$s.Scores.Composite
        Rating=$s.Rating; RatingFull=$s.RatingFull
        ShortDir=$s.Prediction.Short; MidDir=$s.Prediction.Mid; LongDir=$s.Prediction.Long
        Confidence=$s.Prediction.Confidence
        Support=[double]$s.KeyLevels.Support
        Resistance=[double]$s.KeyLevels.Resistance
        StopLoss=[double]$s.KeyLevels.StopLoss
        ReturnPct=$returnPct
        # Signals
        MA_Trend=$s.Signals.MA_Trend
        MACD_Position=$s.Signals.MACD_Position
        RSI_Value=[double]$s.Signals.RSI_Value
        RSI_Zone=$s.Signals.RSI_Zone
        Bollinger_Position=$s.Signals.Bollinger_Position
        Volume_Relation=$s.Signals.Volume_Relation
        ROE_Level=$s.Signals.ROE_Level
        PE_Percentile_Zone=$s.Signals.PE_Percentile_Zone
        Debt_Level=$s.Signals.Debt_Level
        Research_Coverage=$s.Signals.Research_Coverage
        FundFlow_Trend=$s.Signals.FundFlow_Trend
        ShortBull=[int]$s.Signals.ShortBull_Score
        MidBull=[int]$s.Signals.MidBull_Score
        LongBull=[int]$s.Signals.LongBull_Score
    }
}

# ============================================================
# 保存当日评估结果（供后续跨期累积）
# ============================================================
$resultFile = Join-Path $resultDir "评估结果_${prevDateStr}.json"
$resultObj = @{ Date=$prevDateStr; GeneratedAt=$todayLabel; Results=$matchedResults }
$resultObj | ConvertTo-Json -Depth 3 | Set-Content $resultFile -Encoding UTF8
Write-Host "✅ 评估结果已保存: $resultFile"

# ============================================================
# 读取全部历史评估结果（跨期累积分析用）
# ============================================================
$allMatched = @()
$histResultFiles = Get-ChildItem (Join-Path $resultDir "评估结果_*.json") | Sort-Object Name
foreach ($rf in $histResultFiles) {
    $rd = Get-Content $rf.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($rr in $rd.Results) {
        $allMatched += $rr
    }
}
Write-Host "📊 累积分析: $($allMatched.Count) 条匹配记录 (来自 $($histResultFiles.Count) 次评估)"
$allMatchedCount = $allMatched.Count

# ============================================================
# 1. 维度有效性分析 (30分)
# ============================================================
Write-Host "`n`n===== 维度有效性分析 ====="

$dimensions = @(
    @{ Name="技术面(Technical)"; Field="TechScore" },
    @{ Name="基本面(Fundamental)"; Field="FundScore" },
    @{ Name="消息面(Sentiment)"; Field="SentScore" },
    @{ Name="板块面(Sector)"; Field="SectScore" },
    @{ Name="资金面(Capital)"; Field="CapScore" },
    @{ Name="宏观面(Macro)"; Field="MacScore" },
    @{ Name="综合(Composite)"; Field="CompScore" }
)

$dimResults = @()
$dimSummaryLines = @()

foreach ($dim in $dimensions) {
    $scores = $allMatched | ForEach-Object { [double]$_.$($dim.Field) }
    $returns = $allMatched | ForEach-Object { [double]$_.ReturnPct }
    $Rho, $n = Get-SpearmanR -X $scores -Y $returns
    $rating = Get-DimensionRating -Rho $Rho

    # 区分度分析
    $highGroup = $allMatched | Where-Object { [double]$_.$($dim.Field) -ge 60 }
    $lowGroup  = $allMatched | Where-Object { [double]$_.$($dim.Field) -lt 40 }
    $highRet = if ($highGroup.Count -gt 0) { ($highGroup | Measure-Object ReturnPct -Average).Average } else { 0 }
    $lowRet  = if ($lowGroup.Count -gt 0)  { ($lowGroup  | Measure-Object ReturnPct -Average).Average } else { 0 }
    $discrimination = $highRet - $lowRet

    $dimResults += [PSCustomObject]@{
        Name=$dim.Name; Field=$dim.Field
        Rho=$Rho; SampleCount=$n; Rating=$rating
        HighCount=$highGroup.Count; LowCount=$lowGroup.Count
        HighReturn=[Math]::Round($highRet, 2)
        LowReturn=[Math]::Round($lowRet, 2)
        Discrimination=[Math]::Round($discrimination, 2)
    }

    $rhoStr = if ($Rho -gt 0) { "+$Rho" } else { "$Rho" }
    Write-Host "  $($dim.Name): ρ=$rhoStr n=$n → $rating (区分度 $([Math]::Round($discrimination,2))%)"
}

# 维度有效性评分
$dimScore = 0
$validDims = $dimResults | Where-Object { $_.SampleCount -ge 3 }
foreach ($dr in $validDims) {
    if ($dr.Rho -ge 0.3) { $dimScore += 15 }
    elseif ($dr.Rho -ge 0.15) { $dimScore += 8 }
    elseif ($dr.Rho -ge 0) { $dimScore += 3 }
    # Rho<0 得0分
}
$dimScore = [Math]::Min(30, $dimScore)

# ============================================================
# 2. 指标有效性分析 (30分)
# ============================================================
Write-Host "`n===== 指标有效性分析 ====="

$signalDefs = @(
    @{ ID="S01"; Name="MA多头排列"; Field="MA_Trend"; Value="多头排列" },
    @{ ID="S02"; Name="MA空头排列"; Field="MA_Trend"; Value="空头排列" },
    @{ ID="S03"; Name="MACD零轴上金叉"; Field="MACD_Position"; Value="零轴上金叉" },
    @{ ID="S04"; Name="MACD死叉"; Field="MACD_Position"; Value="死叉" },
    @{ ID="S05"; Name="RSI超买(≥70)"; Field="RSI_Zone"; Value="超买" },
    @{ ID="S06"; Name="RSI超卖(<30)"; Field="RSI_Zone"; Value="超卖" },
    @{ ID="S07"; Name="RSI中性偏强(50-70)"; Field="RSI_Zone"; Value="中性偏强" },
    @{ ID="S08"; Name="布林触及上轨"; Field="Bollinger_Position"; Value="触及上轨" },
    @{ ID="S09"; Name="布林触及下轨"; Field="Bollinger_Position"; Value="触及下轨" },
    @{ ID="S12"; Name="ROE≥15%"; Field="ROE_Level"; Value="优秀(≥15%)" },
    @{ ID="S13"; Name="PE低估(<20%)"; Field="PE_Percentile_Zone"; Value="低估(<20%)" },
    @{ ID="S14"; Name="PE高估(>80%)"; Field="PE_Percentile_Zone"; Value="高估(>80%)" },
    @{ ID="S15"; Name="主力持续流入"; Field="FundFlow_Trend"; Value="主力持续流入" },
    @{ ID="S16"; Name="主力持续流出"; Field="FundFlow_Trend"; Value="主力流出" },
    @{ ID="S18"; Name="有研报覆盖"; Field="Research_Coverage"; Value="有" }
)

# Also add RSI中性偏弱(30-50) and 缩量下跌, 放量上涨 signals
$signalDefs += @{ ID="S07b"; Name="RSI中性偏弱(30-50)"; Field="RSI_Zone"; Value="中性偏弱" }
$signalDefs += @{ ID="S10";  Name="放量上涨"; Field="Volume_Relation"; Value="放量上涨" }
$signalDefs += @{ ID="S11";  Name="缩量下跌"; Field="Volume_Relation"; Value="缩量下跌" }
$signalDefs += @{ ID="S11b"; Name="放量下跌"; Field="Volume_Relation"; Value="放量下跌" }

$signalResults = @()
$signalCsvLines = @()
$todayStrShort = $todayLabel  # For CSV

foreach ($sig in $signalDefs) {
    $wr = Get-SignalWinRate -MatchedList $allMatched -SignalField $sig.Field -SignalValue $sig.Value
    $rating = if ($wr.Count -gt 0) { Get-SignalRating -WinRate $wr.WinRate } else { "无数据" }

    $signalResults += [PSCustomObject]@{
        ID=$sig.ID; Name=$sig.Name; Field=$sig.Field; Value=$sig.Value
        Count=$wr.Count; Wins=$wr.Wins; WinRate=$wr.WinRate; Rating=$rating
    }

    if ($wr.Count -gt 0) {
        Write-Host "  $($sig.ID) $($sig.Name): $($wr.WinRate)% ($($wr.Wins)/$($wr.Count)) → $rating"
        # 累积到CSV行（按信号维度聚合，每日追加行）
        $signalCsvLines += "$($todayStrShort),$($sig.ID),$($sig.Name),$($sig.Field),$($wr.Count),$($wr.Wins),$($wr.WinRate),$($wr.Count),$($wr.WinRate),$rating"
    }
}

# 指标有效性评分
$signalScore = 0
$validSignals = $signalResults | Where-Object { $_.Count -ge 3 }
foreach ($sr in $validSignals) {
    if ($sr.WinRate -ge 65) { $signalScore += 30 / [Math]::Max(1, $validSignals.Count) }
    elseif ($sr.WinRate -ge 50) { $signalScore += 20 / [Math]::Max(1, $validSignals.Count) }
    elseif ($sr.WinRate -ge 40) { $signalScore += 10 / [Math]::Max(1, $validSignals.Count) }
}
$signalScore = [Math]::Min(30, $signalScore)

# ============================================================
# 3. 阈值有效性分析 (20分)
# ============================================================
Write-Host "`n===== 阈值有效性分析 ====="

$segments = @(
    @{ Label="优秀(≥80)"; Min=80; Max=200 },
    @{ Label="良好(60-79)"; Min=60; Max=79 },
    @{ Label="一般(40-59)"; Min=40; Max=59 },
    @{ Label="差(<40)"; Min=-200; Max=39 }
)

$segmentResults = @()
foreach ($seg in $segments) {
    $group = $allMatched | Where-Object {
        $cs = [double]$_.CompScore
        $cs -ge $seg.Min -and $cs -le $seg.Max
    }
    $cnt = @($group).Count
    $avgRet = if ($cnt -gt 0) { ($group | Measure-Object ReturnPct -Average).Average } else { 0 }
    $posRatio = if ($cnt -gt 0) { @($group | Where-Object { $_.ReturnPct -gt 0 }).Count / $cnt * 100 } else { 0 }
    $segmentResults += [PSCustomObject]@{
        Label=$seg.Label; Min=$seg.Min; Max=$seg.Max
        Count=$cnt; AvgReturn=[Math]::Round($avgRet, 2)
        PositiveRatio=[Math]::Round($posRatio, 1)
    }
    Write-Host "  $($seg.Label): n=$cnt 平均收益=$([Math]::Round($avgRet,2))% 正收益比例=$([Math]::Round($posRatio,1))%"
}

# 阈值评分
$excellent = $segmentResults | Where-Object { $_.Label -like "优秀*" }
$poor = $segmentResults | Where-Object { $_.Label -like "差*" }
$thresholdScore = Get-ThresholdScore -ExcellentReturn $excellent.AvgReturn -PoorReturn $poor.AvgReturn

# 最优阈值建议（样本≥20时）
$thresholdAdvice = "样本不足($($allMatchedCount)<20)，暂无法给出最优阈值建议"
if ($allMatchedCount -ge 20) {
    # 尝试不同阈值组合找最大区分度
    $bestDiff = -1; $bestThreshold = 80
    foreach ($t in @(70, 75, 80, 85)) {
        $above = $allMatched | Where-Object { [double]$_.CompScore -ge $t }
        $below = $allMatched | Where-Object { [double]$_.CompScore -lt $t }
        if (@($above).Count -ge 3 -and @($below).Count -ge 3) {
            $avgA = ($above | Measure-Object ReturnPct -Average).Average
            $avgB = ($below | Measure-Object ReturnPct -Average).Average
            if (($avgA - $avgB) -gt $bestDiff) { $bestDiff = $avgA - $avgB; $bestThreshold = $t }
        }
    }
    $thresholdAdvice = "建议优秀阈值为${bestThreshold}分(区分度$([Math]::Round($bestDiff,2))%)"
    Write-Host "  [建议] $thresholdAdvice"
}

# ============================================================
# 4. 框架一致性分析 (20分)
# ============================================================
Write-Host "`n===== 框架一致性分析 ====="

# 4.1 评分-结论一致性
$inconsistent = 0
$totalWithPred = 0
foreach ($m in $allMatched) {
    $cs = [double]$m.CompScore
    $sd = $m.ShortDir
    if ($sd -eq "看多" -or $sd -eq "偏多") {
        $totalWithPred++
        if ($cs -lt 40) { $inconsistent++ }
    } elseif ($sd -eq "看空") {
        $totalWithPred++
        if ($cs -ge 70) { $inconsistent++ }
    }
}
$consistencyRate = if ($totalWithPred -gt 0) { [Math]::Round((1 - $inconsistent/$totalWithPred) * 100, 1) } else { 0 }
$consistencyScore = if ($consistencyRate -ge 90) { 8 } elseif ($consistencyRate -ge 75) { 5 } else { 2 }

# 4.2 置信度校准
$highConf = $allMatched | Where-Object { $_.Confidence -eq "高" }
$midConf  = $allMatched | Where-Object { $_.Confidence -eq "中" }
$highAcc = if (@($highConf).Count -gt 0) { @($highConf | Where-Object { $_.ReturnPct -gt 0 }).Count / @($highConf).Count * 100 } else { 0 }
$midAcc  = if (@($midConf).Count -gt 0)  { @($midConf | Where-Object { $_.ReturnPct -gt 0 }).Count / @($midConf).Count * 100 } else { 0 }
$calibScore = if ($highAcc -ge 70 -and $midAcc -ge 50) { 6 } elseif ($highAcc -ge 50) { 3 } else { 1 }

# 4.3 多期稳定性（有≥3期数据时）
$stabilityScore = 4  # 默认
if ($histResultFiles.Count -ge 3) {
    $periodAvgs = @()
    foreach ($rf in $histResultFiles) {
        $rd = Get-Content $rf.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
        $rets = $rd.Results | ForEach-Object { [double]$_.ReturnPct }
        if (@($rets).Count -gt 0) { $periodAvgs += ($rets | Measure-Object -Average).Average }
    }
    if ($periodAvgs.Count -ge 3) {
        $mean = ($periodAvgs | Measure-Object -Average).Average
        $variation = ($periodAvgs | ForEach-Object { [Math]::Abs($_ - $mean) } | Measure-Object -Average).Average
        $stabilityScore = if ($variation -lt 1.0) { 6 } elseif ($variation -lt 2.0) { 4 } else { 2 }
    }
}

$frameworkScore = $consistencyScore + $calibScore + $stabilityScore
Write-Host "  评分-结论一致性: ${consistencyRate}% → ${consistencyScore}/8"
Write-Host "  置信度校准: 高=${highAcc}% 中=${midAcc}% → ${calibScore}/6"
Write-Host "  多期稳定性: ${stabilityScore}/6"

# ============================================================
# 综合评估得分
# ============================================================
$totalScore = $dimScore + $signalScore + $thresholdScore + $frameworkScore
$totalRating = if ($totalScore -ge 80) { "优秀" } elseif ($totalScore -ge 60) { "良好" } elseif ($totalScore -ge 40) { "一般" } else { "待改进" }

Write-Host "`n`n========== 逻辑评估综合 =========="
Write-Host "  维度有效性: $dimScore/30"
Write-Host "  指标有效性: $signalScore/30"
Write-Host "  阈值有效性: $thresholdScore/20"
Write-Host "  框架一致性: $frameworkScore/20"
Write-Host "  综合评分: $totalScore/100 → $totalRating"
Write-Host "================================"

# ============================================================
# 生成自优化建议
# ============================================================
$suggestions = @()

# 条件1: 某信号胜率<45%且样本≥5
foreach ($sr in $signalResults) {
    if ($sr.Count -ge 5 -and $sr.WinRate -lt 45) {
        $suggestions += [PSCustomObject]@{
            Target="重点股票跟踪分析逻辑白皮书"
            Section="§3.1 技术面评分-$(if($sr.Field -eq 'MA_Trend'){'MA趋势'}else{$sr.Name})"
            Issue="$($sr.Name)信号胜率偏低($($sr.WinRate)%)"
            Suggestion="建议审视该信号权重或在评分中降权处理"
            Evidence="样本$($sr.Count)次，胜率$($sr.WinRate)%"
            Priority="P2"
        }
    }
}

# 条件2: 某维度Spearman ρ<0.1且样本≥10
foreach ($dr in $dimResults) {
    if ($dr.SampleCount -ge 10 -and [Math]::Abs($dr.Rho) -lt 0.1) {
        $suggestions += [PSCustomObject]@{
            Target="重点股票跟踪分析逻辑白皮书"
            Section="§3 $($dr.Name)"
            Issue="$($dr.Name)维度与次日收益几乎不相关(ρ=$($dr.Rho))"
            Suggestion="建议审视该维度的评分逻辑，或考虑降低权重"
            Evidence="样本$($dr.SampleCount)次，ρ=$($dr.Rho)"
            Priority="P1"
        }
    }
}

# 条件3: 优秀段收益≤差段收益
if ($excellent.Count -gt 0 -and $poor.Count -gt 0 -and $excellent.AvgReturn -le $poor.AvgReturn) {
    $suggestions += [PSCustomObject]@{
        Target="重点股票次日后评估白皮书"
        Section="§2.3 阈值有效性"
        Issue="优秀段收益($($excellent.AvgReturn)%) ≤ 差段收益($($poor.AvgReturn)%)"
        Suggestion="全面审视评分阈值设定，当前分段无法有效区分优劣"
        Evidence="优秀组n=$($excellent.Count)，差组n=$($poor.Count)"
        Priority="P0"
    }
}

# 条件4: 累积评估≥5次
if ($histResultFiles.Count -ge 5) {
    # 趋势分析
    $trendReturns = @()
    foreach ($rf in $histResultFiles) {
        $rd = Get-Content $rf.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
        $avgRet = ($rd.Results | ForEach-Object { [double]$_.ReturnPct } | Measure-Object -Average).Average
        $trendReturns += $avgRet
    }
    # 简单趋势判断
    $recent3 = $trendReturns | Select-Object -Last 3
    $declining = $true
    for ($i = 1; $i -lt $recent3.Count; $i++) {
        if ($recent3[$i] -ge $recent3[$i-1]) { $declining = $false; break }
    }
    if ($declining -and $recent3.Count -eq 3) {
        $suggestions += [PSCustomObject]@{
            Target="重点股票跟踪分析逻辑白皮书"
            Section="§1 分析框架"
            Issue="综合评分准确率连续3期下降($([Math]::Round($recent3[0],2))% → $([Math]::Round($recent3[1],2))% → $([Math]::Round($recent3[2],2))%)"
            Suggestion="建议方法论整体审视，检查是否有市场环境变化导致框架失效"
            Evidence="最近3期平均收益: $([string]::Join(' → ', ($trendReturns | Select-Object -Last 3 | ForEach-Object { "$([Math]::Round($_,2))%" })))"
            Priority="P0"
        }
    }
}

# ============================================================
# 更新知识积累文件
# ============================================================
Write-Host "`n===== 更新知识积累 ====="

# 更新指标有效性跟踪CSV
$csvHeaderExists = Test-Path $trackFile
$csvContent = @()
if ($signalCsvLines.Count -gt 0) {
    if (-not $csvHeaderExists) {
        $csvContent += "日期,信号ID,信号名称,维度,样本数,正确数,胜率,累积样本,累积胜率,有效性评级"
    }
    $csvContent += $signalCsvLines
    $csvContent | Add-Content $trackFile -Encoding UTF8
    Write-Host "  ✅ 指标有效性跟踪已更新: $trackFile"
}

# 更新优化建议JSON
if ($suggestions.Count -gt 0) {
    # 读取现有建议（如有）
    $existingSuggestions = @()
    if (Test-Path $suggestFile) {
        try {
            $existingData = Get-Content $suggestFile -Raw -Encoding UTF8 | ConvertFrom-Json
            $existingSuggestions = $existingData.suggestions
        } catch { $existingSuggestions = @() }
    }
    $allSuggestions = @($existingSuggestions) + @($suggestions | ForEach-Object {
        @{ target=$_.Target; section=$_.Section; issue=$_.Issue;
           suggestion=$_.Suggestion; evidence=$_.Evidence; priority=$_.Priority }
    })
    $suggestObj = @{ date=$todayLabel; suggestions=$allSuggestions }
    $suggestObj | ConvertTo-Json -Depth 3 | Set-Content $suggestFile -Encoding UTF8
    Write-Host "  ✅ 优化建议已更新: $suggestFile ($($suggestions.Count) 条新建议)"
} else {
    Write-Host "  ℹ️ 暂无新增优化建议"
}

# 更新改进日志
if ($suggestions.Count -gt 0) {
    $logEntry = @"
### ${todayLabel}: [自优化触发] 分析逻辑改进建议

- **触发条件**：后评估发现以下问题
- **证据**：

$(foreach ($sg in $suggestions) { "- $($sg.Issue) (优先级:$($sg.Priority))`n" })
- **建议**：
$(foreach ($sg in $suggestions) { "- $($sg.Suggestion) (`$($sg.Section)`)`n" })
- **状态**：待确认

---
"@
    Add-Content $improveLog -Encoding UTF8 -Value $logEntry
    Write-Host "  ✅ 改进日志已更新: $improveLog"
} else {
    # 强制写入：无建议也记录，确保评估→输出链不断裂
    $noIssueEntry = @"
### ${todayLabel}: 无异常

- **样本数**：$($matchedResults.Count)/$($stocks.Count)只
- **结论**：本次评估未触发优化建议
- **状态**：已记录

---
"@
    Add-Content $improveLog -Encoding UTF8 -Value $noIssueEntry
    Write-Host "  📝 改进日志已记录（本次无异常）: $improveLog"
}


# ============================================================
# 微循环：元评估数据采集 + 自动信号发现
# ============================================================
Write-Host "`n===== 微循环：自我进化 ====="

# --- 元评估数据采集 ---
$metaEvalDir = Join-Path $evalRoot "逻辑积累\元评估"
if (-not (Test-Path $metaEvalDir)) { New-Item -ItemType Directory -Path $metaEvalDir -Force | Out-Null }
$metaTrackFile = Join-Path $metaEvalDir "评估系统有效性跟踪.csv"

$metaHeader = "评估日期,累积样本数,维度有效性得分,指标有效性得分,阈值有效性得分,框架一致性得分,综合评分,建议数,高置信度标记"
$metaRow = "$todayLabel,$allMatchedCount,$dimScore,$([Math]::Round($signalScore,1)),$thresholdScore,$frameworkScore,$totalScore,$($suggestions.Count),$(if($allMatchedCount -ge 20){'是'}else{'否'})"

$metaHeaderExists = Test-Path $metaTrackFile
if (-not $metaHeaderExists) {
    $metaHeader | Add-Content $metaTrackFile -Encoding UTF8
}
$metaRow | Add-Content $metaTrackFile -Encoding UTF8
Write-Host "  ✅ 元评估数据已记录: $metaTrackFile"

# --- 自动信号发现 ---
$signalDiscoveryDir = Join-Path $evalRoot "逻辑积累\信号发现"
if (-not (Test-Path $signalDiscoveryDir)) { New-Item -ItemType Directory -Path $signalDiscoveryDir -Force | Out-Null }
$candidateFile = Join-Path $signalDiscoveryDir "候选信号.json"
$retiredFile = Join-Path $signalDiscoveryDir "已淘汰信号.json"

# 读取现有候选和已淘汰列表
$candidates = @()
$retired = @()
if (Test-Path $candidateFile) { try { $candidates = @(Get-Content $candidateFile -Raw -Encoding UTF8 | ConvertFrom-Json) } catch {} }
if (Test-Path $retiredFile) { try { $retired = @(Get-Content $retiredFile -Raw -Encoding UTF8 | ConvertFrom-Json) } catch {} }

# 定义已知跟踪的信号值列表（避免重复发现）
$trackedSignalValues = @(
    "多头排列","空头排列","纠缠/不明",
    "零轴上金叉","零轴下金叉","死叉",
    "超买","中性偏强","中性偏弱","超卖",
    "触及上轨","中轨上方","中轨下方","触及下轨",
    "放量上涨","缩量上涨","放量下跌","缩量下跌","量能正常",
    "优秀(≥15%)","良好(≥10%)","一般(≥5%)","较差(<5%)",
    "低估(<20%)","偏低(20-40%)","合理(40-60%)","偏高(60-80%)","高估(>80%)",
    "低杠杆","合理","偏高","高杠杆",
    "有研报","无研报",
    "主力持续流入","主力流入>流出","主力流出","N/A",
    "有(0篇)","有(1篇)","有(2篇)","有(3篇)","有(4篇+)"
)

# 扫描累积数据中的各Signal字段值
$signalFields = @("MA_Trend","MACD_Position","RSI_Zone","Bollinger_Position","Volume_Relation","ROE_Level","PE_Percentile_Zone","Debt_Level","Research_Coverage","FundFlow_Trend")
$newCandidatesFound = 0
$retireCandidatesFound = 0

foreach ($field in $signalFields) {
    $values = $allMatched | Where-Object { $_.$field -and $_.$field -ne "" } | ForEach-Object { $_.$field } | Group-Object | Select-Object Name, Count
    foreach ($v in $values) {
        if ($v.Count -lt 3) { continue }
        $valName = $v.Name
        $valCount = $v.Count
        $winCount = @($allMatched | Where-Object { $_."$field" -eq $valName -and $_.ReturnPct -gt 0 }).Count
        $winRate = [Math]::Round($winCount / $valCount * 100, 1)

        $isTracked = $false
        foreach ($tv in $trackedSignalValues) {
            if ($valName -like "*$tv*" -or $tv -like "*$valName*") { $isTracked = $true; break }
        }
        $alreadyCandidate = $candidates | Where-Object { $_."信号值" -eq $valName }

        if (-not $isTracked -and -not $alreadyCandidate -and $winRate -ge 60) {
            $candidates += [PSCustomObject]@{
                日期=$todayLabel; 字段=$field; 信号值=$valName
                样本数=$valCount; 正确数=$winCount; 胜率=$winRate
            }
            $newCandidatesFound++
            Write-Host "  [信号发现] 新候选: $field = $valName ($winRate%, $valCount次)"
        }

        if ($isTracked -and $valCount -ge 10 -and $winRate -lt 40) {
            $alreadyRetired = $retired | Where-Object { $_."信号值" -eq $valName }
            if (-not $alreadyRetired) {
                $retired += [PSCustomObject]@{
                    日期=$todayLabel; 字段=$field; 信号值=$valName
                    样本数=$valCount; 正确数=$winCount; 胜率=$winRate; 淘汰原因="胜率低于40%"
                }
                $retireCandidatesFound++
                Write-Host "  [信号发现] 建议淘汰: $field = $valName ($winRate%, $valCount次)"
            }
        }
    }
}

$candidates | ConvertTo-Json -Depth 2 | Set-Content $candidateFile -Encoding UTF8
$retired | ConvertTo-Json -Depth 2 | Set-Content $retiredFile -Encoding UTF8
if ($newCandidatesFound -gt 0) { Write-Host "  ✅ 新增 $newCandidatesFound 个候选信号" }
if ($retireCandidatesFound -gt 0) { Write-Host "  ⚠️ 建议淘汰 $retireCandidatesFound 个信号" }
if ($newCandidatesFound -eq 0 -and $retireCandidatesFound -eq 0) { Write-Host "  ℹ️ 信号发现：未发现新的候选或淘汰信号" }

# 检查中循环触发条件（每5次）
if (Test-Path $metaTrackFile) {
    $metaData = Get-Content $metaTrackFile -Encoding UTF8 | ConvertFrom-Csv
    $evalCount = $metaData.Count
    if ($evalCount % 20 -eq 0 -and $evalCount -gt 0) {
        Write-Host "  🔔 已累积 $evalCount 次评估，达中循环触发条件(每20次)！运行: .\run_meta_evaluation.ps1"
    }
}

# ============================================================
# v1.7: §6.8 桥接检测 — 后评估→分析逻辑白皮书联动
# ============================================================
Write-Host "`n===== §6.8 桥接检测 ====="
$bridgeLinkFile = Join-Path $linkageLogDir "分析逻辑联动建议.json"
$bridgeSuggestions = @()

# 读取现有联动建议
$existingBridges = @()
if (Test-Path $bridgeLinkFile) {
    try { $existingBridges = @(Get-Content $bridgeLinkFile -Raw -Encoding UTF8 | ConvertFrom-Json) } catch {}
}

# B1: 维度有效性连续2次 ρ<0.1 → 建议降权
foreach ($dr in $dimResults) {
    if ($dr.SampleCount -ge 10 -and [Math]::Abs($dr.Rho) -lt 0.1 -and $dr.Rho -ne 0) {
        # 检查历史趋势（简化：仅当有≥2期数据时检查）
        if ($histResultFiles.Count -ge 2) {
            $bridgeSuggestions += [PSCustomObject]@{
                linkage_id = "LNK-$(Get-Date -Format 'yyyyMMdd')-B1-$($dr.Field)"
                bridge = "B1"
                trigger_condition = "$($dr.Name) Spearman ρ=$($dr.Rho) < 0.1"
                trigger_date = $todayLabel
                target_doc = "重点股票跟踪分析逻辑白皮书"
                target_section = "§3.1"
                proposed_change = "审查$($dr.Name)权重"
                priority = "P1"
                status = "待腰子确认"
            }
        }
    }
}

# B2: 信号ICIR连续下降>30% → 审查参数
foreach ($sr in $signalResults) {
    if ($sr.Count -ge 5 -and $sr.WinRate -lt 45) {
        $bridgeSuggestions += [PSCustomObject]@{
            linkage_id = "LNK-$(Get-Date -Format 'yyyyMMdd')-B2-$($sr.ID)"
            bridge = "B2"
            trigger_condition = "$($sr.Name) 胜率=$($sr.WinRate)% < 45%"
            trigger_date = $todayLabel
            target_doc = "重点股票跟踪分析逻辑白皮书"
            target_section = "§1.1-1.5"
            proposed_change = "审查$($sr.Name)信号参数/阈值"
            priority = "P2"
            status = "待青山审查"
        }
    }
}

# B6: 相邻评级区间T+5收益差异不显著 → 审查阈值
if ($allMatchedCount -ge 20) {
    $excellentGroup = $allMatched | Where-Object { [double]$_.CompScore -ge 80 }
    $goodGroup = $allMatched | Where-Object { [double]$_.CompScore -ge 65 -and [double]$_.CompScore -lt 80 }
    if (@($excellentGroup).Count -ge 5 -and @($goodGroup).Count -ge 5) {
        $excRet = ($excellentGroup | Measure-Object ReturnPct -Average).Average
        $goodRet = ($goodGroup | Measure-Object ReturnPct -Average).Average
        if ([Math]::Abs($excRet - $goodRet) -lt 0.5) {
            $bridgeSuggestions += [PSCustomObject]@{
                linkage_id = "LNK-$(Get-Date -Format 'yyyyMMdd')-B6-001"
                bridge = "B6"
                trigger_condition = "优秀段vs良好段T+1收益差异=$([Math]::Round([Math]::Abs($excRet-$goodRet),2))% < 0.5%"
                trigger_date = $todayLabel
                target_doc = "重点股票跟踪分析逻辑白皮书"
                target_section = "§3.1.1"
                proposed_change = "审查评分阈值，优秀/良好区间区分度不足"
                priority = "P1"
                status = "待青山审查"
            }
        }
    }
}

# 保存联动建议
$allBridges = @($existingBridges) + @($bridgeSuggestions)
if ($bridgeSuggestions.Count -gt 0) {
    $allBridges | ConvertTo-Json -Depth 3 | Set-Content $bridgeLinkFile -Encoding UTF8
    Write-Host "  ✅ §6.8 桥接检测: $($bridgeSuggestions.Count) 条新联动建议 → $bridgeLinkFile"
} else {
    Write-Host "  ℹ️ §6.8 桥接检测: 无新触发条件（数据积累中，当前 $allMatchedCount 条）"
}

# ============================================================
# 生成逻辑诊断报告HTML/PDF
# ============================================================
Write-Host "`n===== 生成逻辑诊断报告 ====="

$pdfFile = Join-Path $reportDir "重点股票每日分析后评估报告_${prevDateStr}.pdf"
$htmlFile = Join-Path $reportDir "重点股票每日分析后评估报告_${prevDateStr}.html"

# CSS
$CSS = @'
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: "Microsoft YaHei", "微软雅黑", sans-serif; color: #333; background: #f0f2f5; padding: 20px; }
.report-page { max-width: 210mm; margin: 0 auto; background: #fff; padding: 15mm 18mm; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
.header { background: #1a1a2e; color: #fff; padding: 28px 30px; border-radius: 10px; margin-bottom: 20px; }
.header h1 { font-size: 22px; margin-bottom: 6px; }
.header .subtitle { font-size: 15px; opacity: 1; }
.section { margin: 18px 0; }
.section h2 { font-size: 18px; color: #16213e; border-bottom: 2px solid #1a1a2e; padding-bottom: 6px; margin-bottom: 12px; }
.section h3 { font-size: 15px; color: #333; margin: 10px 0 6px; }
table { width: 100%; border-collapse: collapse; margin: 8px 0 14px; font-size: 13px; }
th { background: #1a1a2e; color: #fff; padding: 8px 10px; text-align: center; font-weight: normal; }
td { padding: 6px 10px; border: 1px solid #e0e0e0; text-align: center; }
tr:nth-child(even) { background: #f8f9fa; }
.summary-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 10px 0 16px; }
.summary-item { padding: 16px; border-radius: 8px; text-align: center; }
.summary-item .num { font-size: 28px; font-weight: bold; }
.summary-item .lbl { font-size: 13px; color: #666; margin-top: 4px; }
.effective { background: #e8f5e9; color: #27ae60; }
.reference { background: #fff3e0; color: #e67e22; }
.weak { background: #f5f5f5; color: #999; }
.reverse { background: #fde8e8; color: #e74c3c; }
.level-ok { color: #27ae60; font-weight: bold; }
.level-warn { color: #e67e22; font-weight: bold; }
.level-fail { color: #e74c3c; font-weight: bold; }
.score-bar { display: inline-block; height: 8px; border-radius: 4px; margin-right: 4px; }
.disclaimer { margin-top: 24px; padding-top: 12px; border-top: 1px solid #ddd; font-size: 11px; color: #999; line-height: 1.8; }
.tag { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; margin: 1px; }
.tag-p0 { background: #fde8e8; color: #e74c3c; font-weight: bold; }
.tag-p1 { background: #fff3e0; color: #e67e22; }
.tag-p2 { background: #eef2ff; color: #4a6cf7; }
.insight-box { background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 14px; margin: 10px 0; }
.warn-box { background: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; padding: 14px; margin: 10px 0; }
.info-box { background: #eef2ff; border: 1px solid #c7d2fe; border-radius: 8px; padding: 14px; margin: 10px 0; }
'@

$html = @"
<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<title>逻辑诊断报告 $todayLabel</title><style>$CSS</style></head>
<body><div class="report-page">
"@

# 报告头
$html += @"
<div class="header">
    <h1>逻辑诊断报告</h1>
    <div class="subtitle">报告日期: $prevLabel | 评估日期: $todayLabel | 累积样本: $allMatchedCount | 综合评分: $totalScore/100 [$totalRating]</div>
</div>
"@

# 逻辑诊断摘要
$html += "<div class='section'><h2>逻辑诊断摘要</h2>"
$bestDim = ($dimResults | Sort-Object Rho -Descending | Select-Object -First 1)
$worstDim = ($dimResults | Sort-Object Rho | Select-Object -First 1)
$bestSig = ($signalResults | Where-Object { $_.Count -ge 3 } | Sort-Object WinRate -Descending | Select-Object -First 1)
$worstSig = ($signalResults | Where-Object { $_.Count -ge 3 } | Sort-Object WinRate | Select-Object -First 1)

$html += "<div class='insight-box'><strong>核心发现：</strong>"
$html += "当前框架<br>"
$html += "• 最佳维度: <strong>$($bestDim.Name)</strong> (ρ=$([Math]::Round($bestDim.Rho,3))，$($bestDim.Rating))<br>"
$html += "• 最弱维度: <strong>$($worstDim.Name)</strong> (ρ=$([Math]::Round($worstDim.Rho,3))，$($worstDim.Rating))<br>"
if ($bestSig.Count -ge 3) { $html += "• 最佳信号: <strong>$($bestSig.Name)</strong> ($($bestSig.WinRate)%，$($bestSig.Rating))<br>" }
if ($worstSig.Count -ge 3) { $html += "• 最差信号: <strong>$($worstSig.Name)</strong> ($($worstSig.WinRate)%，$($worstSig.Rating))<br>" }
$html += "• 阈值区分度: 优秀段($($excellent.AvgReturn)%) vs 差段($($poor.AvgReturn)%)<br>"
$html += "• 评估综合: ${totalScore}/100分 [$totalRating]"
$html += "</div></div>"

# 综合评分看板
$html += "<div class='section'><h2>综合评分</h2><div class='summary-grid'>"
$dScore = $dimScore; $sScore = [Math]::Round($signalScore,1); $tScore = $thresholdScore; $fScore = $frameworkScore
$html += "<div class='summary-item' style='background:#e8f5e9;'><div class='num' style='color:#27ae60;'>$dScore/30</div><div class='lbl'>维度有效性</div></div>"
$html += "<div class='summary-item' style='background:#e3f2fd;'><div class='num' style='color:#1976d2;'>$sScore/30</div><div class='lbl'>指标有效性</div></div>"
$html += "<div class='summary-item' style='background:#fff3e0;'><div class='num' style='color:#e67e22;'>$tScore/20</div><div class='lbl'>阈值有效性</div></div>"
$html += "<div class='summary-item' style='background:#f3e5f5;'><div class='num' style='color:#7b1fa2;'>$fScore/20</div><div class='lbl'>框架一致性</div></div>"
$html += "</div></div>"

# --- 维度有效性详情 ---
$html += "<div class='section'><h2>一、维度有效性 (${dimScore}/30)</h2>"
$html += "<table><tr><th>维度</th><th>Spearman ρ</th><th>样本数</th><th>有效性</th><th>高分组收益%</th><th>低分组收益%</th><th>区分度%</th></tr>"
foreach ($dr in $dimResults) {
    $rClass = if ($dr.Rating -eq "有效") { "effective" } elseif ($dr.Rating -eq "参考") { "reference" } elseif ($dr.Rating -eq "反向") { "reverse" } else { "weak" }
    $rhoStr = if ($dr.Rho -gt 0) { "+$($dr.Rho)" } else { "$($dr.Rho)" }
    $html += "<tr><td>$($dr.Name)</td><td class='$rClass'>$rhoStr</td><td>$($dr.SampleCount)</td><td>$($dr.Rating)</td><td>$($dr.HighReturn)%</td><td>$($dr.LowReturn)%</td><td>$($dr.Discrimination)%</td></tr>"
}
$html += "</table>"
$html += "<div class='info-box'><strong>说明：</strong>Spearman ρ>0表示评分越高收益越好，ρ<0表示反向；高分组(评分≥60) vs 低分组(评分<40)。样本<3时相关性不可靠。</div>"
$html += "</div>"

# --- 指标有效性详情 ---
$html += "<div class='section'><h2>二、指标有效性 (${signalScore}/30)</h2>"
$html += "<table><tr><th>ID</th><th>信号名称</th><th>维度</th><th>样本数</th><th>正确数</th><th>胜率%</th><th>有效性</th></tr>"
foreach ($sr in ($signalResults | Where-Object { $_.Count -gt 0 } | Sort-Object WinRate -Descending)) {
    $cls = if ($sr.Rating -eq "强有效") { "effective" } elseif ($sr.Rating -eq "反向信号") { "reverse" } else { "" }
    $html += "<tr><td>$($sr.ID)</td><td>$($sr.Name)</td><td>$($sr.Field)</td><td>$($sr.Count)</td><td>$($sr.Wins)</td><td class='$cls'>$($sr.WinRate)%</td><td>$($sr.Rating)</td></tr>"
}
$html += "</table>"
if ($bestSig.Count -ge 3 -or $worstSig.Count -ge 3) {
    $html += "<div class='insight-box'><strong>信号洞察：</strong><br>"
    if ($bestSig.Count -ge 3) { $html += "✅ 最强信号: $($bestSig.Name) ($($bestSig.WinRate)%)<br>" }
    if ($worstSig.Count -ge 3) { $html += "⚠️ 最弱信号: $($worstSig.Name) ($($worstSig.WinRate)%)" }
    $html += "</div>"
}
$html += "</div>"

# --- 阈值有效性详情 ---
$html += "<div class='section'><h2>三、阈值有效性 (${thresholdScore}/20)</h2>"
$html += "<table><tr><th>评分段</th><th>样本数</th><th>平均收益%</th><th>正收益比例%</th><th>判断</th></tr>"
foreach ($seg in $segmentResults) {
    $judgment = if ($seg.AvgReturn -gt 0) { "✅ 正收益" } elseif ($seg.AvgReturn -eq 0) { "➖ 持平" } else { "❌ 负收益" }
    $html += "<tr><td><strong>$($seg.Label)</strong></td><td>$($seg.Count)</td><td class='$(if($seg.AvgReturn -ge 0){'level-ok'}else{'level-fail'})'>$($seg.AvgReturn)%</td><td>$($seg.PositiveRatio)%</td><td>$judgment</td></tr>"
}
$html += "</table>"
$html += "<div class='info-box'>$thresholdAdvice</div>"
$html += "</div>"

# --- 框架一致性详情 ---
$html += "<div class='section'><h2>四、框架一致性 (${frameworkScore}/20)</h2>"
$html += "<table><tr><th>评估项</th><th>指标值</th><th>得分</th><th>判断</th></tr>"
$html += "<tr><td>评分-结论一致性</td><td>${consistencyRate}%</td><td>${consistencyScore}/8</td><td>$(if($consistencyRate -ge 90){'✅ 自洽'}elseif($consistencyRate -ge 75){'⚠️ 需关注'}else{'❌ 不一致'})</td></tr>"
$html += "<tr><td>高置信度准确率</td><td>$([Math]::Round($highAcc,1))%</td><td colspan='2'>高置信样本 $($highConf.Count) 个</td></tr>"
$html += "<tr><td>中置信度准确率</td><td>$([Math]::Round($midAcc,1))%</td><td>${calibScore}/6</td><td>$(if($highAcc -ge 70 -and $midAcc -ge 50){'✅ 校准良好'}else{'⚠️ 需校准'})</td></tr>"
$html += "<tr><td>多期稳定性</td><td>$(if($histResultFiles.Count -ge 3){$histResultFiles.Count}else{$histResultFiles.Count})期</td><td>${stabilityScore}/6</td><td>$(if($stabilityScore -ge 5){'✅ 稳定'}elseif($stabilityScore -ge 3){'⚠️ 波动'}else{'❌ 不稳定'})</td></tr>"
$html += "</table>"
$html += "</div>"

# --- 优化建议 ---
$html += "<div class='section'><h2>五、优化建议</h2>"
if ($suggestions.Count -gt 0) {
    foreach ($sg in $suggestions) {
        $tagClass = if ($sg.Priority -eq "P0") { "tag-p0" } elseif ($sg.Priority -eq "P1") { "tag-p1" } else { "tag-p2" }
        $boxClass = if ($sg.Priority -eq "P0") { "warn-box" } else { "info-box" }
        $html += "<div class='$boxClass'>"
        $html += "<span class='tag $tagClass'>$($sg.Priority)</span> "
        $html += "<strong>$($sg.Issue)</strong><br>"
        $html += "<span style='font-size:12px;color:#666;'>$($sg.Suggestion) | $($sg.Evidence)</span>"
        $html += "</div>"
    }
} else {
    $html += "<div class='info-box'><p>暂无优化建议，当前分析框架运行正常。</p></div>"
}
$html += "</div>"

# --- 知识积累状态 ---
$html += "<div class='section'><h2>六、知识积累状态</h2>"
$html += "<table><tr><th>文件</th><th>路径</th><th>状态</th></tr>"
$html += "<tr><td>指标有效性跟踪</td><td>$trackFile</td><td>$(if(Test-Path $trackFile){'✅ 已更新'}else{'⏳ 待创建'})</td></tr>"
$html += "<tr><td>改进日志</td><td>$improveLog</td><td>$(if(Test-Path $improveLog){'✅ 已更新'}else{'⏳ 待创建'})</td></tr>"
$html += "<tr><td>优化建议</td><td>$suggestFile</td><td>$(if(Test-Path $suggestFile){'✅ 已更新'}else{'⏳ 待创建'})</td></tr>"
$html += "<tr><td>历史评估数据</td><td>$($evalRoot)评估数据_*.json</td><td>$($allHistFiles.Count) 份</td></tr>"
$html += "<tr><td>历史评估结果</td><td>$($resultDir)评估结果_*.json</td><td>$($histResultFiles.Count) 份</td></tr>"
$html += "</table>"
$html += "</div>"

# 数据来源附录
$html += @"
<div class="section"><h2>数据来源附录</h2>
<table><tr><th>编号</th><th>数据源</th><th>用途</th></tr>
<tr><td>[1]</td><td>腾讯行情API</td><td>当日涨跌幅/最高/最低</td></tr>
<tr><td>[2]</td><td>新浪K线</td><td>当日K线验证</td></tr>
<tr><td>[5]</td><td>本地计算</td><td>技术面信号状态</td></tr>
</table></div>
"@

# 免责声明
$html += @"
<div class="disclaimer">
<p><strong>免责声明</strong></p>
<p>本逻辑诊断报告由铁律量化系统自动生成，仅用于评估分析模型的有效性，不构成任何投资建议。</p>
<p>生成时间: $((Get-Date).ToString('yyyy-MM-dd HH:mm:ss')) | 评估方法: 重点股票次日后评估白皮书 v1.7</p>
<p>核心原则：复盘的是"分析逻辑本身"，不是"股票涨跌对错"</p>
</div>
</div></body></html>
"@

# 写HTML
[System.IO.File]::WriteAllText($htmlFile, $html, [System.Text.Encoding]::UTF8)
Write-Host "  [HTML] $htmlFile"

# 转PDF
if (Test-Path $htmlFile) {
    if (-not (Test-Path $edgePath)) {
        $altEdge = Get-ChildItem "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" -ErrorAction SilentlyContinue
        if (-not $altEdge) { $altEdge = Get-ChildItem "C:\Program Files\Microsoft\Edge\Application\msedge.exe" -ErrorAction SilentlyContinue }
        if ($altEdge) { $edgePath = $altEdge.FullName } else { Write-Warning "Edge not found, skip PDF"; $htmlOnly = $true }
    }
    if (-not $htmlOnly) {
        $uri = "file:///$($htmlFile.Replace('\','/'))"
        try {
            Start-Process -FilePath $edgePath -ArgumentList @(
                "--headless", "--disable-gpu", "--no-sandbox",
                "--print-to-pdf=`"$pdfFile`"",
                "--no-pdf-header-footer",
                "--print-to-pdf-paper-size=A4",
                $uri
            ) -Wait -PassThru -NoNewWindow:$false 2>$null
            Start-Sleep -Seconds 2
            if ((Test-Path $pdfFile) -and (Get-Item $pdfFile).Length -gt 30000) {
                Write-Host "  [PDF] ✅ $pdfFile ($([Math]::Round((Get-Item $pdfFile).Length/1KB)) KB)"
            } else {
                Write-Host "  [PDF] ⚠️ 文件可能未正确生成: $pdfFile"
            }
        } catch {
            Write-Warning "PDF error: $_"
        }
    }
}

# 清理HTML
if (-not $KeepHtml -and (Test-Path $htmlFile)) { Remove-Item $htmlFile -Force }

# ============================================================
# Summary
# ============================================================
Write-Host "`n`n========== 逻辑诊断完成 =========="
Write-Host "评估方法: 重点股票次日后评估白皮书 v1.7"
Write-Host "评估日期: $todayLabel | 报告日期: $prevLabel"
Write-Host "累积样本: $allMatchedCount | API调用: $script:apiCallCount"
Write-Host ""
Write-Host "  维度有效性: $dimScore/30"
Write-Host "  指标有效性: $signalScore/30"
Write-Host "  阈值有效性: $thresholdScore/20"
Write-Host "  框架一致性: $frameworkScore/20"
Write-Host "  ─────────────────"
Write-Host "  综合评分: $totalScore/100 → $totalRating"
Write-Host ""
if ($suggestions.Count -gt 0) {
    Write-Host "  ⚠️  $($suggestions.Count) 条优化建议 (最高优先级: $($suggestions[0].Priority))"
}
Write-Host ""
if ($bridgeSuggestions.Count -gt 0) {
    Write-Host "  §6.8 桥接联动: $($bridgeSuggestions.Count) 条新建议 → $bridgeLinkFile"
}
Write-Host ""
Write-Host "v1.7 新增目录:"
Write-Host "  联动日志: $linkageLogDir"
Write-Host "  失效归因: $attributionDir"
Write-Host "  知识代谢: $metabolismDir"
Write-Host "  知识蒸馏: $distillationDir"
Write-Host "  条件规则: $combRulesDir"
Write-Host "  实验提案: $experimentDir"
Write-Host ""
Write-Host "知识积累文件:"
Write-Host "  指标跟踪: $trackFile"
Write-Host "  改进日志: $improveLog"
Write-Host "  优化建议: $suggestFile"
Write-Host "  评估结果: $resultFile"
Write-Host "逻辑诊断报告: $pdfFile"
Write-Host "================================"

# Auto-commit: post_eval outputs
$gitAuto = Join-Path $rootDir "代码文件\tools\git_autocommit.ps1"
if (Test-Path $gitAuto) {
    $null = & $gitAuto -Module "post_eval" -Paths @("重点股票\次日评估\", "历史数据\02_评估数据\") -Message "重点股票后评估产出"
}
