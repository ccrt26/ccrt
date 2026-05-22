# 铁律量化 - 重点股票分析报告生成引擎
# 基于：重点股票跟踪分析逻辑白皮书 v2.0
# 输出：每只股票独立PDF分析报告
# 数据源：[1]~[12] HTTP API已实测
# 最后更新：2026-05-21

param(
    [string]$Date = "",           # 指定日期 YYYYMMDD，默认今天
    [switch]$KeepHtml = $false,    # 保留中间HTML文件
    [string[]]$TargetStocks = @()  # 指定股票代码，默认全部6只
)

# ============================================================
# 配置
# ============================================================
$rootDir = "C:\Users\34269\Documents\Claude\股票分析"
$outRoot = Join-Path $rootDir "重点股票\股票报告"
$modulePath = Join-Path $rootDir "每日荐股\scripts\stock_data_fetcher.psm1"
$edgePath = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

if ($Date -ne "") { $reportDate = Get-Date $Date } else { $reportDate = Get-Date }
$dateStr = $reportDate.ToString("yyyyMMdd")
$dateLabel = $reportDate.ToString("yyyy-MM-dd")

# 全部6只股票
$allStocks = @(
    @{ Code = "603019"; Name = "中科曙光"; Industry = "计算机" },
    @{ Code = "601689"; Name = "拓普集团"; Industry = "汽车零部件" },
    @{ Code = "600114"; Name = "东睦股份"; Industry = "电子/机械" },
    @{ Code = "301075"; Name = "多瑞医药"; Industry = "医药" },
    @{ Code = "000967"; Name = "盈峰环境"; Industry = "环保" },
    @{ Code = "600036"; Name = "招商银行"; Industry = "银行" }
)
if ($TargetStocks.Count -gt 0) {
    $stocks = $allStocks | Where-Object { $_.Code -in $TargetStocks }
} else {
    $stocks = $allStocks
}

# API节流
$script:apiCallCount = 0
function Invoke-ThrottledApi($scriptBlock) {
    Start-Sleep -Milliseconds 300
    $script:apiCallCount++
    if ($script:apiCallCount % 10 -eq 0) { Start-Sleep -Seconds 2 }
    return & $scriptBlock
}

# ============================================================
# 导入数据模块
# ============================================================
if (-not (Test-Path $modulePath)) {
    Write-Error "Module not found: $modulePath"; exit 1
}
Import-Module $modulePath -Force -WarningAction SilentlyContinue 2>$null
Write-Host "✅ 数据模块已导入: stock_data_fetcher ($(Get-Date -Format 'HH:mm:ss'))"

# ============================================================
# Phase 1: Collect-StockFullData
# ============================================================
function Collect-StockFullData {
    param([string]$Code)

    # [1] 腾讯实时行情
    $quote = Invoke-ThrottledApi { Get-StockQuote -Code $Code }
    if (-not $quote) {
        Write-Warning "  [WARN] Quote failed for $Code, using placeholder"
        $quote = [PSCustomObject]@{ Name = "N/A"; Price = 0; ChangePct = 0; PE = 0; TurnoverRate = 0; MktCap = 0; Amplitude = 0; Time = "" }
    }

    # [2] 新浪K线 120日
    $klines = Invoke-ThrottledApi { Get-StockKLine -Code $Code -Scale 240 -Count 120 }
    if (-not $klines -or $klines.Count -lt 10) {
        Write-Warning "  [WARN] K-line data insufficient for $Code"
        $klines = @()
    }

    # [5] 本地技术指标
    $ma5 = @(); $ma10 = @(); $ma20 = @(); $ma50 = @(); $ma120 = @()
    $rsi14 = @(); $macd = $null; $boll = $null; $vol5 = @(); $vol20 = @()
    if ($klines.Count -ge 20) {
        $ma5 = Calc-MovingAverage -Data $klines -Period 5
        $ma10 = Calc-MovingAverage -Data $klines -Period 10
        $ma20 = Calc-MovingAverage -Data $klines -Period 20
        $rsi14 = Calc-RSI -Data $klines -Period 14
        $macd = Calc-MACD -Data $klines
        $boll = Calc-Bollinger -Data $klines
        $vol5 = Calc-MovingAverage -Data $klines -Field "Volume" -Period 5
        $vol20 = Calc-MovingAverage -Data $klines -Field "Volume" -Period 20
        if ($klines.Count -ge 50) { $ma50 = Calc-MovingAverage -Data $klines -Period 50 }
        if ($klines.Count -ge 120) { $ma120 = Calc-MovingAverage -Data $klines -Period 120 }
    }

    # [3] 财务数据
    $financial = Invoke-ThrottledApi { Get-StockFinancial -Code $Code -Quarters 4 }

    # [2]+[3]→[5] PE百分位
    $pePercentile = Invoke-ThrottledApi { Get-PEPercentile -Code $Code -LookbackYears 5 }

    # [9] 个股资金流向
    $fundFlow = Invoke-ThrottledApi { Get-StockFundFlow -Code $Code -Days 5 }

    # [8] 北向资金
    $northbound = Invoke-ThrottledApi { Get-NorthboundHold -Code $Code }

    # [11] 研报
    $research = Invoke-ThrottledApi { Get-StockResearch -Code $Code -Count 5 -DaysBack 30 }

    # [12] 融资融券
    $margin = Invoke-ThrottledApi { Get-MarginData -Code $Code -Days 5 }

    return [PSCustomObject]@{
        Code = $Code; Name = $quote.Name; Price = $quote.Price
        Quote = $quote; KLines = $klines
        MA5 = $ma5; MA10 = $ma10; MA20 = $ma20; MA50 = $ma50; MA120 = $ma120
        RSI14 = $rsi14; MACD = $macd; Bollinger = $boll
        VolMA5 = $vol5; VolMA20 = $vol20
        Financial = $financial; PEPercentile = $pePercentile
        FundFlow = $fundFlow; Northbound = $northbound
        Research = $research; Margin = $margin
    }
}

# ============================================================
# Phase 2: 六维评分函数
# ============================================================

function Get-TechScore {
    param($D)
    $score = 0
    if (-not $D.KLines -or $D.KLines.Count -lt 20 -or -not $D.MACD) { return 40 }
    # A. MA趋势 (30分)
    $ma5v = $D.MA5[-1]; $ma10v = $D.MA10[-1]; $ma20v = $D.MA20[-1]; $price = $D.Price
    if     ($ma5v -gt $ma10v -and $ma10v -gt $ma20v -and $price -gt $ma20v) { $score += 30 }
    elseif ($ma5v -gt $ma10v -and $price -gt $ma10v)                       { $score += 20 }
    elseif ($ma5v -gt $ma10v)                                                { $score += 12 }
    elseif ($ma5v -lt $ma10v -and $ma10v -lt $ma20v)                        { $score += 3 }
    else                                                                      { $score += 8 }
    # B. MACD (20分)
    $dif = $D.MACD.DIF[-1]; $dea = $D.MACD.DEA[-1]
    if     ($dif -gt $dea -and $dif -gt 0 -and $D.MACD.DIF[-1] -gt $D.MACD.DIF[-2]) { $score += 20 }
    elseif ($dif -gt $dea -and $dif -gt 0)                                           { $score += 15 }
    elseif ($dif -gt $dea)                                                            { $score += 8 }
    else                                                                               { $score += 3 }
    # C. RSI (20分)
    $rsi = [double]$D.RSI14[-1]
    if     ($rsi -ge 45 -and $rsi -le 65)   { $score += 20 }
    elseif ($rsi -ge 35 -and $rsi -lt 45)   { $score += 12 }
    elseif ($rsi -gt 65 -and $rsi -le 75)   { $score += 12 }
    elseif ($rsi -gt 75 -and $rsi -le 85)   { $score += 5 }
    elseif ($rsi -lt 25)                     { $score += 5 }
    else                                      { $score += 8 }
    # D. 布林带 (15分)
    $close = $D.KLines[-1].Close; $bm = $D.Bollinger.MA[-1]
    $bu = $D.Bollinger.Upper[-1]; $bd = $D.Bollinger.Lower[-1]
    $bmPrev = if ($D.Bollinger.MA.Count -ge 3) { $D.Bollinger.MA[-3] } else { $bm }
    if     ($close -ge $bm -and $close -le $bu -and $bm -gt $bmPrev) { $score += 15 }
    elseif ($close -lt $bm -and $close -gt $bd -and $bm -gt $bmPrev) { $score += 10 }
    elseif ($close -ge $bu)                                            { $score += 8 }
    elseif ($close -le $bd)                                            { $score += 3 }
    else                                                               { $score += 8 }
    # E. 量能 (15分)
    $vol = $D.KLines[-1].Volume; $v5 = $D.VolMA5[-2]; $chg = $D.Quote.ChangePct
    if     ($chg -ge 2 -and $vol -gt $v5 * 1.5)   { $score += 15 }
    elseif ($chg -ge 0 -and $vol -le $v5 * 1.2)   { $score += 8 }
    elseif ($chg -lt -2 -and $vol -gt $v5 * 1.5)  { $score += 2 }
    elseif ($chg -lt 0 -and $vol -lt $v5 * 0.8)   { $score += 5 }
    else                                            { $score += 10 }
    return [Math]::Min([Math]::Max($score, 0), 100)
}

function Get-FundamentalScore {
    param($D)
    $score = 0
    $fin = $D.Financial
    if (-not $fin -or $fin.Count -eq 0) { return 40 }
    # A. ROE (25分)
    $roe = [double]$fin[0].WEIGHTAVG_ROE
    if     ($roe -ge 15)  { $score += 25 }
    elseif ($roe -ge 10)  { $score += 15 }
    elseif ($roe -ge 5)   { $score += 8 }
    else                  { $score += 2 }
    # B. 毛利率估算 (20分)
    $rev = [double]$fin[0].TOTAL_OPERATE_INCOME; $cost = [double]$fin[0].OPERATE_COST
    if ($rev -gt 0) {
        $gm = ($rev - $cost) / $rev * 100
        if     ($gm -ge 50)  { $score += 20 }
        elseif ($gm -ge 30)  { $score += 15 }
        elseif ($gm -ge 15)  { $score += 8 }
        elseif ($gm -ge 5)   { $score += 3 }
        else                 { $score += 0 }
    } else { $score += 8 }
    # C. 营收增速 (20分)
    if ($fin.Count -ge 2 -and [double]$fin[1].TOTAL_OPERATE_INCOME -ne 0) {
        $revGrowth = ([double]$fin[0].TOTAL_OPERATE_INCOME - [double]$fin[1].TOTAL_OPERATE_INCOME) / [Math]::Abs([double]$fin[1].TOTAL_OPERATE_INCOME) * 100
        if     ($revGrowth -ge 30)  { $score += 20 }
        elseif ($revGrowth -ge 15)  { $score += 14 }
        elseif ($revGrowth -ge 0)   { $score += 8 }
        elseif ($revGrowth -ge -10) { $score += 4 }
        else                        { $score += 0 }
    } else { $score += 8 }
    # D. PE百分位 (20分)
    $pep = $D.PEPercentile
    if ($pep) {
        $pct = $pep.Percentile
        if     ($pct -lt 20)  { $score += 20 }
        elseif ($pct -lt 40)  { $score += 15 }
        elseif ($pct -lt 60)  { $score += 10 }
        elseif ($pct -lt 80)  { $score += 5 }
        else                  { $score += 2 }
    } else { $score += 10 }
    # E. 负债率 (15分)
    $debt = [double]$fin[0].DEBT_ASSET_RATIO
    if     ($debt -lt 30)   { $score += 15 }
    elseif ($debt -lt 50)   { $score += 10 }
    elseif ($debt -lt 65)   { $score += 5 }
    elseif ($debt -lt 80)   { $score += 2 }
    else                    { $score += 0 }
    return [Math]::Min([Math]::Max($score, 0), 100)
}

function Get-SentimentScore {
    param($D)
    $score = 0
    $r = $D.Research
    if (-not $r -or $r.Count -eq 0) { return 25 }
    # A. 研报数量 (30分)
    $cnt = $r.Count
    if     ($cnt -ge 5)   { $score += 30 }
    elseif ($cnt -ge 3)   { $score += 22 }
    elseif ($cnt -ge 1)   { $score += 12 }
    # B. 评级分布 (35分)
    $buy = ($r | Where-Object { $_.EmRating -eq '买入' }).Count
    $hold = ($r | Where-Object { $_.EmRating -eq '增持' }).Count
    $positive = $buy + $hold
    $positiveRatio = if ($cnt -gt 0) { $positive / $cnt } else { 0 }
    if     ($positiveRatio -ge 0.8)  { $score += 35 }
    elseif ($positiveRatio -ge 0.5)  { $score += 20 }
    elseif ($positiveRatio -ge 0.2)  { $score += 8 }
    else                              { $score += 3 }
    # C. 市场关注度 (35分)
    $tr = $D.Quote.TurnoverRate; $chg5 = if ($D.KLines.Count -ge 5) { ($D.KLines[-1].Close / $D.KLines[-5].Close - 1) * 100 } else { 0 }
    $attention = 0
    if ($cnt -ge 3) { $attention += 15 }; if ($tr -gt 3) { $attention += 10 }; if ($chg5 -gt 0) { $attention += 10 }
    $score += $attention
    return [Math]::Min([Math]::Max($score, 0), 100)
}

function Get-SectorScore {
    param($D, $GlobalSectors, $GlobalSectorFund)
    $score = 0
    $ind = $D.Name  # 用股票名匹配板块 — 实际需要行业字段
    # 从财务数据获取行业
    $industry = ""
    if ($D.Financial -and $D.Financial.Count -gt 0 -and $D.Financial[0].INDUSTRY) {
        $industry = $D.Financial[0].INDUSTRY
    }
    # A. 板块相位 (40分) — 基于板块涨跌幅和资金流向判断
    $secData = $null; $secFund = $null
    if ($industry -ne "") {
        $secData = $GlobalSectors | Where-Object { $_.SectorName -eq $industry }
        $secFund = $GlobalSectorFund | Where-Object { $_.SectorName -eq $industry }
    }
    # 如果没有精确匹配，使用行业板块TOP20的平均值
    if ($secData) {
        $chg = $secData.ChangePct
        if     ($chg -ge 3)   { $score += 40 }  # 主升
        elseif ($chg -ge 1)   { $score += 30 }  # 启动
        elseif ($chg -ge 0)   { $score += 20 }  # 见底/企稳
        elseif ($chg -ge -1)  { $score += 15 }  # 高潮期回落
        else                  { $score += 5 }   # 退潮
    } else {
        # 使用TOP20均值
        $avgChg = ($GlobalSectors | Measure-Object ChangePct -Average).Average
        if     ($avgChg -ge 1)  { $score += 25 }
        elseif ($avgChg -ge 0)  { $score += 18 }
        else                    { $score += 10 }
    }
    # B. 板块资金流 (30分)
    if ($secFund) {
        $ni = $secFund.NetInflow
        if     ($ni -gt 5e8)   { $score += 30 }
        elseif ($ni -gt 0)     { $score += 20 }
        elseif ($ni -gt -3e8)  { $score += 10 }
        else                   { $score += 3 }
    } else { $score += 15 }
    # C. 个股vs板块表现 (30分)
    if ($secData -and $D.Quote.ChangePct -ne 0) {
        $relStr = $D.Quote.ChangePct - $secData.ChangePct
        if     ($relStr -gt 2)   { $score += 30 }
        elseif ($relStr -gt 0)   { $score += 20 }
        elseif ($relStr -gt -2)  { $score += 10 }
        else                     { $score += 3 }
    } else { $score += 15 }
    return [Math]::Min([Math]::Max($score, 0), 100)
}

function Get-CapitalScore {
    param($D)
    $score = 0
    # A. 主力资金 (35分)
    $ff = $D.FundFlow
    if ($ff -and $ff.Count -gt 0) {
        $netInflows = $ff | ForEach-Object { $_.MainNetInflow }
        $posDays = ($netInflows | Where-Object { $_ -gt 0 }).Count
        $total = $netInflows.Count
        if ($total -gt 0) {
            $ratio = $posDays / $total
            $cum = ($netInflows | Measure-Object -Sum).Sum
            if     ($ratio -ge 0.8 -and $cum -gt 0)  { $score += 35 }
            elseif ($ratio -ge 0.6)                   { $score += 22 }
            elseif ($ratio -ge 0.4)                   { $score += 12 }
            else                                      { $score += 4 }
        }
    } else { $score += 15 }
    # B. 北向持股 (35分)
    $nb = $D.Northbound
    if ($nb -and $nb.SharesRatio -gt 0) {
        $sr = $nb.SharesRatio
        if     ($sr -ge 5)   { $score += 35 }
        elseif ($sr -ge 3)   { $score += 25 }
        elseif ($sr -ge 1)   { $score += 15 }
        else                 { $score += 8 }
    } else { $score += 15 }
    # C. 融资融券 (30分)
    $mg = $D.Margin
    if ($mg -and $mg.Count -ge 2) {
        $rzStart = $mg[0].RZYE; $rzEnd = $mg[-1].RZYE
        if ($rzStart -gt 0) {
            $chg = ($rzEnd - $rzStart) / $rzStart * 100
            if     ($chg -gt 1)    { $score += 30 }
            elseif ($chg -gt -0.5) { $score += 18 }
            elseif ($chg -gt -3)   { $score += 8 }
            else                   { $score += 3 }
        }
    } else { $score += 15 }
    return [Math]::Min([Math]::Max($score, 0), 100)
}

function Get-MacroScore {
    param($GlobalSectors)
    $score = 0
    $total = $GlobalSectors.Count
    if ($total -eq 0) { return 50 }
    $positive = ($GlobalSectors | Where-Object { $_.ChangePct -ge 0 }).Count
    $posRatio = $positive / $total
    $score += [Math]::Round($posRatio * 50)
    $strong = ($GlobalSectors | Where-Object { $_.ChangePct -ge 2 -and $_.Turnover -gt 80 }).Count
    $strongRatio = $strong / $total
    $score += [Math]::Round([Math]::Min($strongRatio * 100, 50))
    return [Math]::Min($score, 100)
}

# ============================================================
# Phase 3: 综合评分 + 趋势健康度 + 三周期预判
# ============================================================

function Get-CompositeScore {
    param($TechS, $FundS, $SentS, $SectS, $CapS, $MacS)
    $composite = $TechS * 0.25 + $FundS * 0.20 + $SentS * 0.15 + $SectS * 0.20 + $CapS * 0.15 + $MacS * 0.05
    $composite = [Math]::Round([Math]::Max([Math]::Min($composite, 100), 0))
    $rating = if     ($composite -ge 85) { "★★★★ 强烈关注" }
              elseif ($composite -ge 70) { "★★★ 关注" }
              elseif ($composite -ge 55) { "★★ 观察" }
              elseif ($composite -ge 40) { "★ 谨慎" }
              else                       { "☆ 回避" }
    $ratingShort = if ($composite -ge 85) { "强烈关注" } elseif ($composite -ge 70) { "关注" } elseif ($composite -ge 55) { "观察" } elseif ($composite -ge 40) { "谨慎" } else { "回避" }
    return @{ Score = $composite; Rating = $rating; RatingShort = $ratingShort }
}

function Get-TrendHealth {
    param($D)
    $h = 0
    if (-not $D.KLines -or $D.KLines.Count -lt 20) { return @{ Score = 50; Label = "数据不足" } }
    # 1. 回调幅度 (20分)
    $high20 = ($D.KLines[-20..-1] | Measure-Object High -Maximum).Maximum
    $pullback = ($high20 - $D.Price) / $high20 * 100
    if     ($pullback -lt 3)   { $h += 20 }
    elseif ($pullback -lt 8)   { $h += 15 }
    elseif ($pullback -lt 15)  { $h += 8 }
    else                       { $h += 2 }
    # 2. 量能趋势 (20分)
    $recentVol = ($D.KLines[-3..-1] | Measure-Object Volume -Average).Average
    $avgVol = $D.VolMA20[-1]
    if ($avgVol -gt 0) {
        $vr = $recentVol / $avgVol
        if     ($vr -ge 1.2)  { $h += 20 }
        elseif ($vr -ge 0.8)  { $h += 12 }
        else                  { $h += 5 }
    } else { $h += 10 }
    # 3. 均线发散 (20分)
    $m5 = $D.MA5[-1]; $m20 = $D.MA20[-1]
    if ($m20 -gt 0) {
        $spread = ($m5 - $m20) / $m20 * 100
        if     ($spread -gt 2)   { $h += 20 }
        elseif ($spread -gt 0.5) { $h += 14 }
        elseif ($spread -gt -1)  { $h += 8 }
        elseif ($spread -gt -3)  { $h += 3 }
        else                     { $h += 0 }
    } else { $h += 10 }
    # 4. MACD状态 (20分)
    if ($D.MACD) {
        $df = $D.MACD.DIF[-1]; $da = $D.MACD.DEA[-1]; $mh = $D.MACD.MACD[-1]
        if     ($df -gt $da -and $df -gt 0 -and $mh -gt 0) { $h += 20 }
        elseif ($df -gt $da -and $df -gt 0)                { $h += 14 }
        elseif ($df -gt $da)                                { $h += 8 }
        else                                                { $h += 2 }
    } else { $h += 10 }
    # 5. RSI趋势 (20分)
    if ($D.RSI14.Count -ge 5) {
        $rNow = [double]$D.RSI14[-1]; $rPrev = [double]$D.RSI14[-5]
        if     ($rNow -ge 50 -and $rNow -le 70 -and $rNow -gt $rPrev) { $h += 20 }
        elseif ($rNow -ge 40 -and $rNow -le 60)                       { $h += 12 }
        elseif ($rNow -gt 70)                                          { $h += 5 }
        elseif ($rNow -lt 30)                                          { $h += 3 }
        else                                                           { $h += 8 }
    } else { $h += 10 }
    $hs = [Math]::Min([Math]::Max($h, 0), 100)
    $label = if ($hs -ge 80) { "健康" } elseif ($hs -ge 60) { "预警关注" } elseif ($hs -ge 40) { "警戒" } else { "危险" }
    return @{ Score = $hs; Label = $label; Pullback = $pullback }
}

function Get-ThreePeriodPrediction {
    param($D, $TechS, $FundS, $SectS, $CapS)
    # 短期
    $shortBull = 0
    if ($D.KLines.Count -ge 5 -and $D.MA5[-1] -gt $D.MA10[-1]) { $shortBull++ }
    if ($D.RSI14.Count -gt 0 -and [double]$D.RSI14[-1] -gt 45 -and [double]$D.RSI14[-1] -lt 70) { $shortBull++ }
    if ($D.MACD -and $D.MACD.DIF[-1] -gt $D.MACD.DEA[-1]) { $shortBull++ }
    if ($D.KLines.Count -ge 3 -and $D.KLines[-1].Close -gt $D.KLines[-3].Close) { $shortBull++ }
    $shortDir = if     ($shortBull -ge 3) { "看多" } elseif ($shortBull -eq 2) { "偏多" } elseif ($shortBull -eq 1) { "中性" } else { "看空" }
    # 中期
    $midBull = 0
    if ($D.MA20.Count -gt 0 -and $D.MA50.Count -gt 0 -and $D.MA20[-1] -gt $D.MA50[-1]) { $midBull++ }
    if ($SectS -ge 55) { $midBull++ }
    if ($FundS -ge 55) { $midBull++ }
    $midDir = if     ($midBull -ge 2) { if ($midBull -eq 3) { "趋势看多" } else { "区间震荡" } } else { "趋势看空" }
    # 长期
    $longBull = 0
    if ($D.PEPercentile -and $D.PEPercentile.Percentile -lt 45) { $longBull++ }
    if ($FundS -ge 55) { $longBull++ }
    if ($D.MA120.Count -gt 0 -and $D.Price -gt $D.MA120[-1]) { $longBull++ }
    $longDir = if ($longBull -ge 2) { "长期看好" } elseif ($longBull -eq 1) { "长期中性" } else { "长期看空" }
    # 关键价位
    $support = if ($D.MA20.Count -gt 0) { [Math]::Round($D.MA20[-1], 2) } else { [Math]::Round($D.Price * 0.95, 2) }
    $resistance = if ($D.MA50.Count -gt 0) { [Math]::Round($D.MA50[-1], 2) } elseif ($D.MA20.Count -gt 0) { [Math]::Round($D.MA20[-1] * 1.05, 2) } else { [Math]::Round($D.Price * 1.05, 2) }
    $stopLoss = [Math]::Round($support * 0.93, 2)
    $confidence = if ($shortBull -ge 3) { "高(>70%)" } elseif ($shortBull -eq 2) { "中(50-70%)" } else { "低(<50%)" }
    return @{
        Short = $shortDir; Mid = $midDir; Long = $longDir
        Support = $support; Resistance = $resistance; StopLoss = $stopLoss
        Confidence = $confidence; ShortBull = $shortBull
        MidBull = $midBull; LongBull = $longBull
    }
}

# ============================================================
# Phase 3.5: 操作建议与交易计划计算（v2.0）
# ============================================================

function Get-OperationPlan {
    param($D, $Pred, $TechS, $FundS, $CompScore)

    $P = $D.Price
    $ATR = $null

    # 计算 ATR(14)
    if ($D.KLines -and $D.KLines.Count -ge 16) {
        $trs = @()
        for ($i = [Math]::Max(1, $D.KLines.Count - 14); $i -lt $D.KLines.Count; $i++) {
            $h = $D.KLines[$i].High; $l = $D.KLines[$i].Low; $pc = $D.KLines[$i-1].Close
            $tr = [Math]::Max([Math]::Max($h - $l, [Math]::Abs($h - $pc)), [Math]::Abs($l - $pc))
            $trs += $tr
        }
        if ($trs.Count -ge 5) { $ATR = ($trs | Measure-Object -Average).Average }
    }
    if (-not $ATR -or $ATR -le 0) { $ATR = $P * 0.025 }

    # ========== 六层价格体系 ==========
    $ma10 = if ($D.MA10.Count -gt 0) { $D.MA10[-1] } else { $P }
    $ma20 = if ($D.MA20.Count -gt 0) { $D.MA20[-1] } else { $P }
    $ma50 = if ($D.MA50.Count -gt 0) { $D.MA50[-1] } else { $null }
    $ma120 = if ($D.MA120.Count -gt 0) { $D.MA120[-1] } else { $null }

    $recentHigh = $null; $recentLow = $null
    if ($D.KLines -and $D.KLines.Count -gt 0) {
        $lookback = [Math]::Min(60, $D.KLines.Count)
        $recentHigh = ($D.KLines[-$lookback..-1] | Measure-Object High -Maximum).Maximum
        $recentLow = ($D.KLines[-$lookback..-1] | Measure-Object Low -Minimum).Minimum
    }

    # R1
    $r1 = if ($ma20 -gt $P) { $ma20 } else { [Math]::Max($ma10, $P * 1.025) }
    $r1 = [Math]::Round($r1, 2)
    # R2
    $r2Candidates = @()
    if ($ma50) { $r2Candidates += $ma50 }
    if ($ma120) { $r2Candidates += $ma120 }
    if ($recentHigh) { $r2Candidates += $recentHigh }
    if ($r2Candidates.Count -gt 0) { $r2 = ($r2Candidates | Measure-Object -Average).Average } else { $r2 = $P * 1.06 }
    $r2 = [Math]::Round($r2, 2)
    # R3
    $r3 = [Math]::Round($r2 + $ATR * 1.5, 2)
    # S1
    $s1 = if ($ma20 -lt $P) { $ma20 } else { [Math]::Min($ma10, $P * 0.975) }
    $s1 = [Math]::Round($s1, 2)
    # S2
    $s2Candidates = @()
    if ($ma50 -and $ma50 -lt $P) { $s2Candidates += $ma50 }
    if ($ma120 -and $ma120 -lt $P) { $s2Candidates += $ma120 }
    if ($recentLow) { $s2Candidates += $recentLow }
    if ($s2Candidates.Count -gt 0) { $s2 = ($s2Candidates | Measure-Object -Average).Average } else { $s2 = $P * 0.94 }
    $s2 = [Math]::Round($s2, 2)
    # S3
    $s3 = [Math]::Round($s2 - $ATR * 1.2, 2)

    # 合理性修正
    if ($r1 -le $P) { $r1 = [Math]::Round($P * 1.025, 2) }
    if ($r2 -le $r1) { $r2 = [Math]::Round($r1 * 1.03, 2) }
    if ($r3 -le $r2) { $r3 = [Math]::Round($r2 * 1.025, 2) }
    if ($s1 -ge $P) { $s1 = [Math]::Round($P * 0.975, 2) }
    if ($s2 -ge $s1) { $s2 = [Math]::Round($s1 * 0.97, 2) }
    if ($s3 -ge $s2) { $s3 = [Math]::Round($s2 * 0.97, 2) }

    # ========== 仓位 ==========
    $pct = $CompScore
    if ($pct -ge 85) { $maxPos = 30; $posLabel = "可重点配置" }
    elseif ($pct -ge 70) { $maxPos = 20; $posLabel = "正常配置" }
    elseif ($pct -ge 55) { $maxPos = 10; $posLabel = "轻仓试探" }
    elseif ($pct -ge 40) { $maxPos = 5; $posLabel = "极轻仓或观望" }
    else { $maxPos = 0; $posLabel = "不参与" }

    $entry1 = $s1; $entry1Pct = [Math]::Round($maxPos * 0.4, 0)
    $entry2 = $s2; $entry2Pct = [Math]::Round($maxPos * 0.3, 0)
    $target1 = $r1; $target2 = $r2
    $stopLoss = $s3

    # ========== 明日情景 ==========
    $isBullish = ($Pred.Short -eq "看多" -or $Pred.Short -eq "偏多")
    $isBearish = ($Pred.Short -eq "看空")
    $isNeutral = ($Pred.Short -eq "中性")
    $distToR1 = [Math]::Round(($r1 - $P) / $P * 100, 1)
    $distToS1 = [Math]::Round(($P - $s1) / $P * 100, 1)

    $scenarios = @()
    if ($isBullish) {
        $scenarios += @{ Title="情景1：高开>1.5%"; Action="已有持仓则持有，不追仓。未持仓则等待回调至S1（${s1}元）附近再介入"; Adjust="持有/观望" }
        $scenarios += @{ Title="情景2：平开或小幅低开（-1%~+1%）"; Action=if($P -le $s1*1.02){"股价已在S1（${s1}元）附近，可建仓第一笔（约${entry1Pct}%仓位）"}else{"等待回踩S1（${s1}元）附近企稳后建仓第一笔"}; Adjust="建仓${entry1Pct}%" }
        $scenarios += @{ Title="情景3：盘中回踩S1（${s1}元）"; Action="观察是否企稳（下影线/缩量十字星），企稳则建仓，跌破则等S2"; Adjust="企稳建仓" }
        $scenarios += @{ Title="情景4：盘中回踩S2（${s2}元）"; Action="深度回调如不放量跌破则加仓第二笔"; Adjust="加仓至${entry2Pct}%" }
        $scenarios += @{ Title="情景5：盘中触及R1（${r1}元）"; Action="放量突破则持有/加仓；缩量触及则减仓做T"; Adjust="突破持有/遇阻减仓" }
        $scenarios += @{ Title="情景6：跌破止损（${s3}元）"; Action="无条件止损，不再持有"; Adjust="清仓" }
    } elseif ($isNeutral) {
        $scenarios += @{ Title="情景1：高开>1.5%"; Action="观察成交量，放量可轻仓试探，缩量则不动"; Adjust="观望/轻仓" }
        $scenarios += @{ Title="情景2：平开/低开"; Action="保持观望，方向不明时减少交易"; Adjust="观望" }
        $scenarios += @{ Title="情景3：盘中大幅波动>3%"; Action="等待方向明确后再操作，不抄底不追高"; Adjust="观望" }
    } else {
        $scenarios += @{ Title="情景1：任何开盘"; Action="不建议买入。如有持仓利用反弹至R1（${r1}元）附近减仓"; Adjust="减仓/清仓" }
        $scenarios += @{ Title="情景2：盘中反弹至R1（${r1}元）"; Action="减仓或清仓的最后机会"; Adjust="减仓" }
        $scenarios += @{ Title="情景3：跌破S1（${s1}元）"; Action="及时止损，避免更大亏损"; Adjust="止损" }
    }

    return @{
        R3=$r3; R2=$r2; R1=$r1; S1=$s1; S2=$s2; S3=$s3
        ATR=[Math]::Round($ATR,2); MaxPosition=$maxPos; PositionLabel=$posLabel
        Entry1=$entry1; Entry1Pct=$entry1Pct; Entry2=$entry2; Entry2Pct=$entry2Pct
        Target1=$target1; Target2=$target2; StopLoss=$stopLoss
        Scenarios=$scenarios; Bullish=$isBullish; Neutral=$isNeutral; Bearish=$isBearish
        DistToR1=$distToR1; DistToS1=$distToS1
    }
}

# ============================================================
# Phase 4: HTML 报告生成
# ============================================================

$CSS = @'
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: "Microsoft YaHei", "微软雅黑", sans-serif; color: #333; background: #f0f2f5; padding: 20px; }
.report-page { max-width: 210mm; margin: 0 auto; background: #fff; padding: 15mm 18mm; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
.page-break { page-break-before: always; }
.header { background: #1a1a2e; color: #fff; padding: 28px 30px; border-radius: 10px; margin-bottom: 20px; position: relative; }
.header h1 { font-size: 24px; margin-bottom: 8px; }
.header .subtitle { font-size: 17px; opacity: 1; text-shadow: 0 0 4px rgba(255,255,255,0.1); }
.header .badge { position: absolute; top: 20px; right: 25px; padding: 8px 18px; border-radius: 20px; font-size: 16px; font-weight: bold; text-align: center; }
.badge-red { background: #e74c3c; color: #fff; }
.badge-orange { background: #e67e22; color: #fff; }
.badge-yellow { background: #f39c12; color: #fff; }
.badge-green { background: #27ae60; color: #fff; }
.badge-blue { background: #2980b9; color: #fff; }
.score-card { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 20px; }
.score-item { background: #f8f9fa; border-radius: 8px; padding: 12px 14px; border-left: 4px solid #3498db; }
.score-item .dim-name { font-size: 13px; color: #666; }
.score-item .dim-score { font-size: 22px; font-weight: bold; margin: 4px 0; }
.score-item .dim-bar { height: 5px; background: #e0e0e0; border-radius: 3px; overflow: hidden; }
.score-item .dim-bar-fill { height: 100%; border-radius: 3px; transition: width 0.3s; }
.section { margin: 18px 0; }
.section h2 { font-size: 18px; color: #16213e; border-bottom: 2px solid #1a1a2e; padding-bottom: 6px; margin-bottom: 12px; }
.section h3 { font-size: 15px; color: #333; margin: 10px 0 6px; }
table { width: 100%; border-collapse: collapse; margin: 8px 0 14px; font-size: 13px; }
th { background: #1a1a2e; color: #fff; padding: 8px 10px; text-align: center; font-weight: normal; }
td { padding: 6px 10px; border: 1px solid #e0e0e0; text-align: center; }
tr:nth-child(even) { background: #f8f9fa; }
.prediction-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 10px 0 16px; }
.pred-item { text-align: center; padding: 12px; border-radius: 8px; background: #f8f9fa; }
.pred-item .period { font-size: 12px; color: #888; }
.pred-item .direction { font-size: 20px; font-weight: bold; margin: 4px 0; }
.pred-up { color: #e74c3c; } .pred-down { color: #27ae60; } .pred-neutral { color: #f39c12; }
.ladder-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin: 10px 0; }
.ladder-item { padding: 10px; border-radius: 6px; text-align: center; }
.ladder-resist { background: #fff5f5; border: 1px solid #fdd; }
.ladder-supp { background: #f0fff4; border: 1px solid #dfd; }
.ladder-stop { background: #fff8f0; border: 1px solid #fed; }
.ladder-item .level { font-size: 11px; color: #999; }
.ladder-item .price { font-size: 18px; font-weight: bold; }
.ladder-item .note { font-size: 11px; color: #888; }
.op-section { background: #f8f9fa; border-radius: 8px; padding: 14px; margin: 10px 0; border-left: 4px solid #2980b9; }
.op-section.buy { border-left-color: #27ae60; }
.op-section.sell { border-left-color: #e74c3c; }
.op-section.stop { border-left-color: #e67e22; }
.op-section .op-title { font-size: 14px; font-weight: bold; margin-bottom: 6px; }
.op-section .op-detail { font-size: 13px; color: #555; line-height: 1.6; }
.scenario-table td:first-child { font-weight: bold; text-align: left; width: 25%; }
.scenario-table td:nth-child(2) { text-align: left; font-size: 12px; }
.scenario-table td:nth-child(3) { width: 15%; font-weight: bold; }
.pos-meter { display: flex; align-items: center; gap: 12px; padding: 12px 16px; background: #eef2f7; border-radius: 8px; margin: 8px 0; }
.pos-meter .pos-max { font-size: 28px; font-weight: bold; color: #2980b9; }
.pos-meter .pos-label { font-size: 14px; color: #555; }
.pos-bar { flex: 1; height: 12px; background: #ddd; border-radius: 6px; overflow: hidden; }
.pos-bar-fill { height: 100%; background: #2980b9; border-radius: 6px; }
.health-meter { display: flex; align-items: center; gap: 16px; padding: 14px; background: #f8f9fa; border-radius: 8px; margin: 10px 0; }
.health-score { font-size: 36px; font-weight: bold; min-width: 70px; text-align: center; }
.health-label { font-size: 16px; padding: 4px 12px; border-radius: 4px; }
.disclaimer { margin-top: 24px; padding-top: 12px; border-top: 1px solid #ddd; font-size: 11px; color: #999; line-height: 1.8; }
.data-src { font-size: 11px; color: #888; vertical-align: super; }
.key-levels { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 10px 0; }
.level-item { padding: 12px; text-align: center; border-radius: 8px; }
.level-item .lbl { font-size: 12px; color: #888; }
.level-item .val { font-size: 20px; font-weight: bold; }
.level-resist { background: #fde8e8; border: 1px solid #f5c6c6; } .level-resist .val { color: #e74c3c; }
.level-supp { background: #e8f5e9; border: 1px solid #c6e6c8; } .level-supp .val { color: #27ae60; }
.level-stop { background: #fff3e0; border: 1px solid #ffe0b2; } .level-stop .val { color: #e67e22; }
.fund-flow-table td:first-child { text-align: left; }
.research-list { margin: 8px 0; }
.research-item { padding: 6px 0; border-bottom: 1px dashed #e0e0e0; font-size: 13px; }
.research-item .org { color: #2980b9; font-weight: bold; }
.research-item .rating-buy { color: #e74c3c; } .research-item .rating-hold { color: #e67e22; }
'@

function New-ScoreColor {
    param($s)
    if ($s -ge 80) { return "#27ae60" }
    elseif ($s -ge 60) { return "#2980b9" }
    elseif ($s -ge 40) { return "#f39c12" }
    else { return "#e74c3c" }
}

function New-RatingBadgeClass {
    param($score)
    if ($score -ge 85) { return "badge-blue" }
    elseif ($score -ge 70) { return "badge-green" }
    elseif ($score -ge 55) { return "badge-yellow" }
    elseif ($score -ge 40) { return "badge-orange" }
    else { return "badge-red" }
}

function New-DirectionClass {
    param($dir)
    if ($dir -eq "看多" -or $dir -eq "偏多" -or $dir -eq "趋势看多" -or $dir -eq "长期看好") { return "pred-up" }
    elseif ($dir -eq "看空" -or $dir -eq "趋势看空" -or $dir -eq "长期看空") { return "pred-down" }
    else { return "pred-neutral" }
}

function New-RptHeader {
    param($D, $Scores, $dateLabel)
    $bc = New-RatingBadgeClass $Scores.Composite
    $sc = $Scores.Composite
    return @"
<div class="header">
    <h1>$($D.Name) ($($D.Code))</h1>
    <div class="subtitle">$dateLabel | 现价 ¥$([Math]::Round($D.Price,2)) | 涨跌幅 $($D.Quote.ChangePct)% | 换手 $($D.Quote.TurnoverRate)% | PE $($D.Quote.PE) | 流通市值 $([Math]::Round($D.Quote.MktCap,0))亿</div>
    <div class="badge $bc">$sc 分<br><span style="font-size:12px;">$($Scores.RatingShort)</span></div>
</div>
"@
}

function New-ExecutiveSummary {
    param($Scores, $Pred)
    $dims = @(
        @{N="技术面";S=$Scores.Technical;W="25%"},
        @{N="基本面";S=$Scores.Fundamental;W="20%"},
        @{N="消息面";S=$Scores.Sentiment;W="15%"},
        @{N="板块行业";S=$Scores.Sector;W="20%"},
        @{N="资金面";S=$Scores.Capital;W="15%"},
        @{N="宏观大盘";S=$Scores.Macro;W="5%"}
    )
    $cards = ""
    foreach ($d in $dims) {
        $c = New-ScoreColor $d.S; $pct = [Math]::Max([Math]::Min($d.S, 100), 0)
        $cards += "<div class='score-item' style='border-left-color:$c'>
            <div class='dim-name'>$($d.N) <span style='float:right;color:#999;font-size:11px;'>$($d.W)</span></div>
            <div class='dim-score' style='color:$c'>$($d.S)</div>
            <div class='dim-bar'><div class='dim-bar-fill' style='width:${pct}%;background:$c'></div></div>
        </div>"
    }
    return @"
<div class="section">
    <h2>执行摘要</h2>
    <div class="score-card">$cards</div>
    <div class="prediction-grid">
        <div class="pred-item"><div class="period">短期 (1-5日)</div><div class="direction $(New-DirectionClass $Pred.Short)">$($Pred.Short)</div><div style="font-size:11px;color:#999;">置信度 $($Pred.Confidence)</div></div>
        <div class="pred-item"><div class="period">中期 (1-4周)</div><div class="direction $(New-DirectionClass $Pred.Mid)">$($Pred.Mid)</div></div>
        <div class="pred-item"><div class="period">长期 (1-6月)</div><div class="direction $(New-DirectionClass $Pred.Long)">$($Pred.Long)</div></div>
    </div>
</div>
"@
}

function New-SixDimDetail {
    param($Scores)
    $dims = @(
        @{N="技术面";S=$Scores.Technical;W="25%";D="均线排列 + MACD + RSI + 布林带 + 量价关系"},
        @{N="基本面";S=$Scores.Fundamental;W="20%";D="ROE + 毛利率 + 营收增速 + PE百分位 + 负债率"},
        @{N="消息面";S=$Scores.Sentiment;W="15%";D="研报覆盖数 + 分析师评级 + 市场关注度"},
        @{N="板块行业";S=$Scores.Sector;W="20%";D="板块相位 + 资金流向 + 个股相对强度"},
        @{N="资金面";S=$Scores.Capital;W="15%";D="主力资金 + 北向持股 + 融资融券"},
        @{N="宏观大盘";S=$Scores.Macro;W="5%";D="市场广度 + 板块涨跌比"}
    )
    $rows = ""
    foreach ($d in $dims) {
        $c = New-ScoreColor $d.S; $weighted = [Math]::Round($d.S * [int]($d.W -replace '%','') / 100, 1)
        $rows += "<tr><td>$($d.N)</td><td style='color:$c;font-weight:bold;'>$($d.S)</td><td>$($d.W)</td><td>$weighted</td><td style='text-align:left;font-size:12px;color:#666;'>$($d.D)</td></tr>"
    }
    $compositeW = $Scores.Technical*0.25 + $Scores.Fundamental*0.20 + $Scores.Sentiment*0.15 + $Scores.Sector*0.20 + $Scores.Capital*0.15 + $Scores.Macro*0.05
    return @"
<div class="section">
    <h2>六维评分详情</h2>
    <table><thead><tr><th>维度</th><th>得分</th><th>权重</th><th>加权得分</th><th>评分依据</th></tr></thead><tbody>$rows</tbody></table>
    <p style="text-align:right;font-size:14px;font-weight:bold;margin-top:6px;">综合评分：<span style="color:$(New-ScoreColor $Scores.Composite);font-size:20px;">$($Scores.Composite) 分</span> — $($Scores.Rating)</p>
</div>
"@
}

function New-TechSection {
    param($D)
    $lines = ""
    if ($D.MA5.Count -gt 0 -and $D.MA10.Count -gt 0 -and $D.MA20.Count -gt 0) {
        $m5 = $D.MA5[-1]; $m10 = $D.MA10[-1]; $m20 = $D.MA20[-1]; $p = $D.Price
        $maTrend = if ($m5 -gt $m10 -and $m10 -gt $m20 -and $p -gt $m20) { "多头排列（强势上行趋势）" }
                   elseif ($m5 -gt $m10 -and $p -gt $m10) { "短期多头（短期均线向上）" }
                   elseif ($m5 -lt $m10 -and $m10 -lt $m20) { "空头排列（下行趋势）" }
                   else { "均线纠缠（方向不明）" }
        $macdTxt = ""
        if ($D.MACD) {
            $df = [Math]::Round($D.MACD.DIF[-1], 3); $da = [Math]::Round($D.MACD.DEA[-1], 3); $mh = [Math]::Round($D.MACD.MACD[-1], 3)
            $macdTxt = if ($D.MACD.DIF[-1] -gt $D.MACD.DEA[-1] -and $D.MACD.DIF[-1] -gt 0) { "零轴上金叉，多头主导" }
                       elseif ($D.MACD.DIF[-1] -gt $D.MACD.DEA[-1]) { "零轴下金叉，弱势反弹" }
                       else { "死叉状态，空头主导" }
        }
        $rsiTxt = ""
        if ($D.RSI14.Count -gt 0) {
            $r = [Math]::Round([double]$D.RSI14[-1], 1)
            $rsiTxt = if ($r -ge 70) { "超买区域($r)，注意回调风险" }
                      elseif ($r -ge 50) { "中性偏强($r)，趋势健康" }
                      elseif ($r -ge 30) { "中性偏弱($r)" }
                      else { "超卖区域($r)，可能存在反弹机会" }
        }
        $bollTxt = ""
        if ($D.Bollinger -and $D.KLines.Count -gt 0) {
            $c = $D.KLines[-1].Close; $bu = $D.Bollinger.Upper[-1]; $bd = $D.Bollinger.Lower[-1]; $bm = $D.Bollinger.MA[-1]
            $bollTxt = if ($c -ge $bu) { "触及上轨($bu)，超买区域" }
                       elseif ($c -ge $bm) { "中轨($bm)和上轨($bu)之间，偏强" }
                       elseif ($c -ge $bd) { "中轨($bm)和下轨($bd)之间，偏弱" }
                       else { "触及下轨($bd)，超卖区域" }
        }
        $volTxt = ""; $v = $D.KLines[-1].Volume; $v5 = if ($D.VolMA5.Count -gt 1) { $D.VolMA5[-2] } else { 0 }
        $chg = $D.Quote.ChangePct
        if ($v5 -gt 0) {
            $vr = $v / $v5
            $volTxt = if    ($chg -ge 2 -and $vr -ge 1.5) { "放量上涨(量比$([Math]::Round($vr,1)))，增量资金入场" }
                      elseif ($chg -ge 0 -and $vr -le 1.1) { "缩量上涨(量比$([Math]::Round($vr,1)))，上涨动力不足" }
                      elseif ($chg -lt -2 -and $vr -ge 1.5) { "放量下跌，恐慌抛售或主力出货" }
                      elseif ($chg -lt 0 -and $vr -le 0.8) { "缩量下跌，抛压减弱" }
                      else { "量能正常" }
        }
        $lines += @"
<table>
<tr><th>指标</th><th>数值</th><th>判断</th></tr>
<tr><td>MA5/MA10/MA20</td><td>$([Math]::Round($m5,2)) / $([Math]::Round($m10,2)) / $([Math]::Round($m20,2))</td><td>$maTrend</td></tr>
<tr><td>MACD</td><td>DIF $([Math]::Round($D.MACD.DIF[-1],3)) DEA $([Math]::Round($D.MACD.DEA[-1],3))</td><td>$macdTxt</td></tr>
<tr><td>RSI(14)</td><td>$([Math]::Round([double]$D.RSI14[-1],1))</td><td>$rsiTxt</td></tr>
<tr><td>布林带</td><td>上$bu 中$([Math]::Round($bm,2)) 下$([Math]::Round($bd,2))</td><td>$bollTxt</td></tr>
<tr><td>量能</td><td>$v 手 / 5日均量 $([Math]::Round($v5,0)) 手</td><td>$volTxt</td></tr>
</table>
"@
    }
    return @"
<div class="section">
    <h2>技术面分析 [2]→[5] ✅已实测</h2>
    $lines
</div>
"@
}

function New-FundamentalSection {
    param($D)
    $fin = $D.Financial
    if (-not $fin -or $fin.Count -eq 0) { return "<div class='section'><h2>基本面分析</h2><p style='color:#999;'>财务数据暂缺</p></div>" }
    $roe = [double]$fin[0].WEIGHTAVG_ROE
    $rev = [double]$fin[0].TOTAL_OPERATE_INCOME; $cost = [double]$fin[0].OPERATE_COST
    $gm = if ($rev -gt 0) { ($rev - $cost) / $rev * 100 } else { 0 }
    $np = [double]$fin[0].PARENT_NETPROFIT
    $debt = [double]$fin[0].DEBT_ASSET_RATIO
    $eps = [double]$fin[0].BASIC_EPS
    $revGrowthStr = "N/A"
    if ($fin.Count -ge 2 -and [double]$fin[1].TOTAL_OPERATE_INCOME -ne 0) {
        $rg = ([double]$fin[0].TOTAL_OPERATE_INCOME - [double]$fin[1].TOTAL_OPERATE_INCOME) / [Math]::Abs([double]$fin[1].TOTAL_OPERATE_INCOME) * 100
        $revGrowthStr = "$([Math]::Round($rg,1))%"
    }
    $peStr = if ($D.PEPercentile) { "$($D.PEPercentile.CurrentPE) / $($D.PEPercentile.MinPE)-$($D.PEPercentile.MaxPE) / 百分位$($D.PEPercentile.Percentile)% ($($D.PEPercentile.Valuation))" } else { "N/A" }
    return @"
<div class="section">
    <h2>基本面分析 [3]→[5] ✅已实测</h2>
    <table>
    <tr><th>指标</th><th>最新值</th><th>评估</th></tr>
    <tr><td>ROE</td><td>$([Math]::Round($roe,2))%</td><td>$(if($roe-ge15){'优秀'}elseif($roe-ge10){'良好'}elseif($roe-ge5){'一般'}else{'较差'})</td></tr>
    <tr><td>毛利率</td><td>$([Math]::Round($gm,1))%</td><td>$(if($gm-ge50){'优秀'}elseif($gm-ge30){'良好'}elseif($gm-ge15){'一般'}else{'较低'})</td></tr>
    <tr><td>营收增速</td><td>$revGrowthStr</td><td>同比</td></tr>
    <tr><td>净利润</td><td>$([Math]::Round($np/100000000,2))亿</td><td>归母净利润</td></tr>
    <tr><td>EPS</td><td>$eps 元</td><td>基本每股收益</td></tr>
    <tr><td>资产负债率</td><td>$([Math]::Round($debt,1))%</td><td>$(if($debt-lt30){'低杠杆'}elseif($debt-lt50){'合理'}elseif($debt-lt65){'偏高'}else{'高杠杆'})</td></tr>
    <tr><td>PE估值</td><td>$peStr</td><td>$(if($D.PEPercentile){$D.PEPercentile.Valuation}else{'N/A'})</td></tr>
    </table>
</div>
"@
}

function New-SentimentSection {
    param($D)
    $html = @"
<div class="section">
    <h2>消息面与情绪分析 [11] ✅已实测</h2>
"@
    $r = $D.Research
    if ($r -and $r.Count -gt 0) {
        $buyC = ($r | Where-Object { $_.EmRating -eq '买入' }).Count
        $holdC = ($r | Where-Object { $_.EmRating -eq '增持' }).Count
        $neutralC = ($r | Where-Object { $_.EmRating -eq '中性' -or $_.EmRating -eq '持有' }).Count
        $html += "<p>近30天研报覆盖：<strong>$($r.Count)篇</strong> | 买入 $buyC / 增持 $holdC / 中性 $neutralC</p><div class='research-list'>"
        foreach ($rp in $r) {
            $rClass = if ($rp.EmRating -eq '买入') { "rating-buy" } elseif ($rp.EmRating -eq '增持') { "rating-hold" } else { "" }
            $dateStr = if ($rp.PublishDate -and $rp.PublishDate.Length -ge 10) { $rp.PublishDate.Substring(0,10) } else { "" }
            $html += "<div class='research-item'><span class='org'>$($rp.OrgName)</span> <span class='$rClass'>[$($rp.EmRating)]</span> $dateStr — $($rp.Title)</div>"
        }
        $html += "</div>"
    } else {
        $html += "<p style='color:#999;'>近30天无研报覆盖</p>"
    }
    # 融资融券情绪
    $mg = $D.Margin
    if ($mg -and $mg.Count -gt 0) {
        $html += "<h3>融资融券 [12] ✅已实测</h3><table><tr><th>日期</th><th>融资余额(亿)</th><th>融券余额(亿)</th><th>融资净买入(万)</th></tr>"
        foreach ($m in $mg) {
            $dt = if ($m.Date -and $m.Date.Length -ge 10) { $m.Date.Substring(0,10) } else { "" }
            $html += "<tr><td>$dt</td><td>$([Math]::Round($m.RZYE/100000000,2))</td><td>$([Math]::Round($m.RQYE/100000000,2))</td><td>$([Math]::Round($m.RZJME/10000,0))</td></tr>"
        }
        $html += "</table>"
    } else {
        $html += "<p style='color:#999;'>融资融券数据暂缺</p>"
    }
    $html += "</div>"
    return $html
}

function New-SectorSection {
    param($D, $GlobalSectors, $GlobalSectorFund)
    $industry = if ($D.Financial -and $D.Financial.Count -gt 0 -and $D.Financial[0].INDUSTRY) { $D.Financial[0].INDUSTRY } else { "" }
    $html = "<div class='section'><h2>板块行业分析 [7] ✅已实测</h2>"
    if ($industry -ne "") {
        $sec = $GlobalSectors | Where-Object { $_.SectorName -eq $industry }
        $sf = $GlobalSectorFund | Where-Object { $_.SectorName -eq $industry }
        if ($sec) {
            $phaseTxt = if ($sec.ChangePct -ge 3) { "主升期" } elseif ($sec.ChangePct -ge 1) { "启动期" } elseif ($sec.ChangePct -ge -0.5) { "见底/企稳" } elseif ($sec.ChangePct -ge -2) { "调整期" } else { "退潮期" }
            $html += "<p>所属行业：<strong>$industry</strong> | 板块涨幅：$($sec.ChangePct)% | 板块相位：$phaseTxt</p>"
            if ($sf) { $html += "<p>行业资金净流入：$([Math]::Round($sf.NetInflow/100000000,2))亿 | 主力净流入：$([Math]::Round($sf.MainInflow/100000000,2))亿</p>" }
        } else {
            $html += "<p>所属行业：$industry（未在TOP20板块中找到精确匹配）</p>"
        }
    } else {
        $html += "<p>行业信息：暂无</p>"
    }
    # TOP5板块排行
    $html += "<h3>市场板块TOP5表现</h3><table><tr><th>板块</th><th>涨幅%</th><th>成交额(亿)</th></tr>"
    $top5 = $GlobalSectors | Select-Object -First 5
    foreach ($s in $top5) {
        $html += "<tr><td>$($s.SectorName)</td><td>$(if($s.ChangePct-ge0){'+'})$($s.ChangePct)%</td><td>$($s.Turnover)</td></tr>"
    }
    $html += "</table></div>"
    return $html
}

function New-CapitalSection {
    param($D)
    $html = "<div class='section'><h2>资金面分析 [8][9][10] ✅已实测</h2>"
    # 主力资金
    $ff = $D.FundFlow
    if ($ff -and $ff.Count -gt 0) {
        $html += "<h3>个股资金流向 [9]</h3><table class='fund-flow-table'><tr><th>日期</th><th>主力净流入(万)</th><th>超大单(万)</th><th>大单(万)</th><th>小单(万)</th></tr>"
        foreach ($f in $ff) {
            $html += "<tr><td>$($f.Date)</td><td>$([Math]::Round($f.MainNetInflow/10000,0))</td><td>$([Math]::Round($f.SuperLargeIn/10000,0))</td><td>$([Math]::Round($f.LargeIn/10000,0))</td><td>$([Math]::Round($f.SmallIn/10000,0))</td></tr>"
        }
        $html += "</table>"
    }
    # 北向资金
    $nb = $D.Northbound
    if ($nb) {
        $html += "<h3>北向资金持股 [8]</h3><p>持股数量：$([Math]::Round($nb.HoldShares/10000,0))万股 | 持股市值：$([Math]::Round($nb.HoldMarketCap/100000000,2))亿 | 占总股本：$($nb.SharesRatio)% | 占流通股本：$($nb.FreeRatio)%</p>"
    }
    $html += "</div>"
    return $html
}

function New-TrendHealthSection {
    param($Health, $D)
    $c = New-ScoreColor $Health.Score
    $pullbackTxt = if ($Health.Pullback) { "当前从20日高点回调 $([Math]::Round($Health.Pullback,1))%" } else { "" }
    $advice = if ($Health.Score -ge 80) { "趋势健康，正常持有" }
              elseif ($Health.Score -ge 60) { "关注预警指标，设定止损" }
              elseif ($Health.Score -ge 40) { "进入警戒状态，准备减仓" }
              else { "立即评估是否需要清仓" }
    return @"
<div class="section">
    <h2>趋势健康度评估</h2>
    <div class="health-meter">
        <div class="health-score" style="color:$c">$($Health.Score)</div>
        <div><span class="health-label" style="background:$c;color:#fff;">$($Health.Label)</span></div>
        <div style="font-size:13px;color:#666;flex:1;">$pullbackTxt</div>
    </div>
    <p style="font-size:13px;color:#666;">建议操作：$advice（白皮书§3.2.1规则）</p>
</div>
"@
}

function New-KeyLevelsSection {
    param($Pred)
    return @"
<div class="section">
    <h2>关键价位</h2>
    <div class="key-levels">
        <div class="level-item level-resist"><div class="lbl">上方阻力</div><div class="val">¥$($Pred.Resistance)</div></div>
        <div class="level-item level-supp"><div class="lbl">下方支撑</div><div class="val">¥$($Pred.Support)</div></div>
        <div class="level-item level-stop"><div class="lbl">止损价位</div><div class="val">¥$($Pred.StopLoss)</div></div>
    </div>
</div>
"@
}

function New-DataSourceAppendix {
    return @"
<div class="section">
    <h2>数据来源附录</h2>
    <table>
    <tr><th>编号</th><th>数据源</th><th>用途</th><th>状态</th></tr>
    <tr><td>[1]</td><td>腾讯行情API</td><td>现价/涨跌幅/PE/换手率/市值</td><td>✅ 已实测</td></tr>
    <tr><td>[2]</td><td>新浪K线</td><td>日K线(OHLCV) / 分钟K线</td><td>✅ 已实测</td></tr>
    <tr><td>[3]</td><td>东方财富财务</td><td>ROE/毛利率/营收/净利/EPS/负债率</td><td>✅ 已实测</td></tr>
    <tr><td>[4]</td><td>Baostock</td><td>K线验证/交叉验证</td><td>✅ 已实测</td></tr>
    <tr><td>[5]</td><td>本地计算</td><td>MA/MACD/RSI/布林/PE百分位</td><td>✅ 已实测</td></tr>
    <tr><td>[6]</td><td>深度财务</td><td>EV/EBITDA</td><td>⚠️ 待验证</td></tr>
    <tr><td>[7]</td><td>东方财富板块</td><td>板块指数/行业排名</td><td>✅ 已实测</td></tr>
    <tr><td>[8]</td><td>东方财富北向资金</td><td>个股北向持股明细</td><td>✅ 已实测</td></tr>
    <tr><td>[9]</td><td>东方财富个股资金流向</td><td>主力净流入/超大单/大单</td><td>✅ 已实测</td></tr>
    <tr><td>[10]</td><td>东方财富行业资金流向</td><td>行业资金净流入排名</td><td>✅ 已实测</td></tr>
    <tr><td>[11]</td><td>东方财富研报/评级</td><td>研报标题/机构/评级/盈利预测</td><td>✅ 已实测</td></tr>
    <tr><td>[12]</td><td>东方财富融资融券</td><td>融资余额/融券余额/净买入</td><td>✅ 已实测</td></tr>
    </table>
</div>
"@
}

function New-Disclaimer {
    return @"
<div class="disclaimer">
    <p><strong>免责声明</strong></p>
    <p>本报告由铁律量化系统自动生成，数据来源包括腾讯行情[1]、新浪K线[2]、东方财富[3][7][8][9][10][11][12]等公开API。报告中的所有分析、评分和预判仅基于历史数据和量化模型，不构成任何投资建议。</p>
    <p>股票投资有风险，过往表现不代表未来收益。本报告中的评分和预判仅供参考，投资者应独立判断并自行承担投资风险。</p>
    <p>数据延迟：实时行情数据可能存在分钟级延迟，财务数据为季度更新。生成时间：$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')</p>
</div>
"@
}

# ============================================================
# 操作建议 HTML 模板函数（v2.0 新增）
# ============================================================

function New-PriceLadder {
    param($Ops, $P)
    $r3c = if ($Ops.R3 -gt $P) { "color:#e74c3c" } else { "color:#555" }
    $r2c = if ($Ops.R2 -gt $P) { "color:#e74c3c" } else { "color:#555" }
    $r1c = if ($Ops.R1 -gt $P) { "color:#e74c3c" } else { "color:#555" }
    $s1c = if ($Ops.S1 -lt $P) { "color:#27ae60" } else { "color:#555" }
    $s2c = if ($Ops.S2 -lt $P) { "color:#27ae60" } else { "color:#555" }
    $s3c = if ($Ops.S3 -lt $P) { "color:#27ae60" } else { "color:#555" }
    return @"
<div class="section">
    <h2>价格分层体系（六层价位）</h2>
    <p style="font-size:12px;color:#888;margin-bottom:8px;">现价 ¥$P | ATR(14) ¥$($Ops.ATR) | 距S1 $($Ops.DistToS1)% | 距R1 $($Ops.DistToR1)%</p>
    <div class="ladder-grid">
        <div class="ladder-item ladder-resist"><div class="level">R3 强阻力</div><div class="price" style="$r3c">¥$($Ops.R3)</div><div class="note">突破则趋势加速</div></div>
        <div class="ladder-item ladder-resist"><div class="level">R2 中阻力</div><div class="price" style="$r2c">¥$($Ops.R2)</div><div class="note">中期目标位</div></div>
        <div class="ladder-item ladder-resist"><div class="level">R1 弱阻力</div><div class="price" style="$r1c">¥$($Ops.R1)</div><div class="note">短期止盈位</div></div>
        <div class="ladder-item ladder-supp"><div class="level">S1 弱支撑</div><div class="price" style="$s1c">¥$($Ops.S1)</div><div class="note">第一买入参考</div></div>
        <div class="ladder-item ladder-supp"><div class="level">S2 中支撑</div><div class="price" style="$s2c">¥$($Ops.S2)</div><div class="note">第二买入参考</div></div>
        <div class="ladder-item ladder-stop"><div class="level">S3 强支撑/止损</div><div class="price" style="$s3c">¥$($Ops.S3)</div><div class="note">趋势防守底线</div></div>
    </div>
</div>
"@
}

function New-ShortTermAction {
    param($Ops, $Pred, $P)
    $dirColor = if ($Ops.Bullish) { "color:#e74c3c" } elseif ($Ops.Bearish) { "color:#27ae60" } else { "color:#f39c12" }
    $scRows = ""
    foreach ($s in $Ops.Scenarios) {
        $adjColor = if ($s.Adjust -match "建仓|加仓|持有") { "color:#27ae60" } elseif ($s.Adjust -match "减仓|清仓|止损") { "color:#e74c3c" } else { "color:#f39c12" }
        $scRows += "<tr><td>$($s.Title)</td><td>$($s.Action)</td><td style='$adjColor'>$($s.Adjust)</td></tr>"
    }
    return @"
<div class="section">
    <h2>短期操作建议（明日/1-5日）</h2>
    <p style="font-size:13px;color:#666;margin-bottom:8px;">趋势判断：<strong style="$dirColor">$($Pred.Short)</strong> | 置信度：$($Pred.Confidence)</p>
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:12px;">
        <div class="op-section buy"><div class="op-title">买入计划</div><div class="op-detail">第一买入点：¥$($Ops.Entry1)（买入$($Ops.Entry1Pct)%）<br>第二买入点：¥$($Ops.Entry2)（买入$($Ops.Entry2Pct)%）</div></div>
        <div class="op-section sell"><div class="op-title">卖出计划</div><div class="op-detail">第一目标：¥$($Ops.Target1)（短线止盈）<br>第二目标：¥$($Ops.Target2)（中线止盈）</div></div>
        <div class="op-section stop"><div class="op-title">止损计划</div><div class="op-detail">止损价位：¥$($Ops.StopLoss)<br>最大亏损约：$([Math]::Round(($P - $Ops.StopLoss) / $P * 100, 1))%</div></div>
    </div>
    <h3>明日操作情景计划</h3>
    <table class="scenario-table"><tr><th>情景</th><th>操作指引</th><th>仓位调整</th></tr>$scRows</table>
</div>
"@
}

function New-PositionSizingSection {
    param($Ops, $Pred, $CompScore)
    $pc = $Ops.MaxPosition
    $color = if ($pc -ge 20) { "#27ae60" } elseif ($pc -ge 10) { "#f39c12" } elseif ($pc -gt 0) { "#e67e22" } else { "#e74c3c" }

    # 中期方向
    $midColor = if ($Pred.Mid -eq "趋势看多") { "color:#e74c3c" } elseif ($Pred.Mid -eq "趋势看空") { "color:#27ae60" } else { "color:#f39c12" }
    $longColor = if ($Pred.Long -eq "长期看好") { "color:#e74c3c" } elseif ($Pred.Long -eq "长期看空") { "color:#27ae60" } else { "color:#666" }

    return @"
<div class="section">
    <h2>仓位与周期策略</h2>
    <div class="pos-meter">
        <div class="pos-max" style="color:$color">$($Ops.MaxPosition)%</div>
        <div class="pos-label">单只上限 · $($Ops.PositionLabel)</div>
        <div class="pos-bar"><div class="pos-bar-fill" style="width:$(if($pc -ge 30){100}else{$pc*3.33})%;background:$color"></div></div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:8px;">
        <div class="op-section"><div class="op-title">中期配置（1-4周）</div><div class="op-detail">方向：<strong style="$midColor">$($Pred.Mid)</strong><br>建仓区间：¥$($Ops.S2) - ¥$($Ops.S1)<br>中期目标：¥$($Ops.Target2)<br>波段止损：¥$($Ops.S3)</div></div>
        <div class="op-section"><div class="op-title">长期配置（1-6月）</div><div class="op-detail">方向：<strong style="$longColor">$($Pred.Long)</strong><br>战略仓位：$($Ops.MaxPosition)%以内<br>分批建仓参考：第一笔 $($Ops.Entry1Pct)% 在S1（¥$($Ops.S1)）附近，第二笔 $($Ops.Entry2Pct)% 在S2（¥$($Ops.S2)）附近</div></div>
    </div>
</div>
"@
}

function New-StockReportHtml {
    param($D, $Scores, $Pred, $Health, $Ops, $GlobalSectors, $GlobalSectorFund, $dateLabel)
    $sb = New-Object System.Text.StringBuilder
    [void]$sb.Append('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">')
    [void]$sb.Append("<title>$($D.Name)($($D.Code))分析报告 $dateLabel</title>")
    [void]$sb.Append("<style>$CSS</style></head><body><div class='report-page'>")
    [void]$sb.Append((New-RptHeader -D $D -Scores $Scores -dateLabel $dateLabel))
    [void]$sb.Append((New-ExecutiveSummary -Scores $Scores -Pred $Pred))
    [void]$sb.Append((New-PriceLadder -Ops $Ops -P $D.Price))
    [void]$sb.Append((New-ShortTermAction -Ops $Ops -Pred $Pred -P $D.Price))
    [void]$sb.Append((New-PositionSizingSection -Ops $Ops -Pred $Pred -CompScore $Scores.Composite))
    [void]$sb.Append((New-SixDimDetail -Scores $Scores))
    [void]$sb.Append("<div class='page-break'></div>")
    [void]$sb.Append((New-TechSection -D $D))
    [void]$sb.Append((New-FundamentalSection -D $D))
    [void]$sb.Append("<div class='page-break'></div>")
    [void]$sb.Append((New-SentimentSection -D $D))
    [void]$sb.Append((New-SectorSection -D $D -GlobalSectors $GlobalSectors -GlobalSectorFund $GlobalSectorFund))
    [void]$sb.Append((New-CapitalSection -D $D))
    [void]$sb.Append((New-TrendHealthSection -Health $Health -D $D))
    [void]$sb.Append((New-KeyLevelsSection -Pred $Pred))
    [void]$sb.Append((New-DataSourceAppendix))
    [void]$sb.Append((New-Disclaimer))
    [void]$sb.Append('</div></body></html>')
    return $sb.ToString()
}

# ============================================================
# Phase 5: PDF转换
# ============================================================
function Convert-HtmlToPdf {
    param([string]$HtmlFile, [string]$PdfFile)
    if (-not (Test-Path $edgePath)) {
        Write-Warning "Edge not found at $edgePath"
        # 尝试自动查找Edge
        $altEdge = Get-ChildItem "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" -ErrorAction SilentlyContinue
        if (-not $altEdge) { $altEdge = Get-ChildItem "C:\Program Files\Microsoft\Edge\Application\msedge.exe" -ErrorAction SilentlyContinue }
        if (-not $altEdge) { return $false }
        $edgePath = $altEdge.FullName
    }
    $uri = "file:///$($HtmlFile.Replace('\','/'))"
    try {
        $pi = Start-Process -FilePath $edgePath -ArgumentList @(
            "--headless", "--disable-gpu", "--no-sandbox",
            "--print-to-pdf=`"$PdfFile`"",
            "--print-to-pdf-no-header",
            "--no-pdf-header-footer",
            "--print-to-pdf-paper-size=A4",
            $uri
        ) -Wait -PassThru -NoNewWindow:$false
        Start-Sleep -Seconds 2
        if ((Test-Path $PdfFile)) {
            $size = (Get-Item $PdfFile).Length
            if ($size -gt 30000) { return $true }
        }
        return $false
    } catch {
        Write-Warning "PDF conversion error: $_"
        return $false
    }
}

# ============================================================
# Main
# ============================================================
Write-Host "`n========== 铁律量化 - 重点股票分析报告生成 =========="
Write-Host "日期: $dateLabel | 股票数: $($stocks.Count)"
Write-Host "数据API节流: 每次调用间隔300ms, 每10次休息2s"
Write-Host "开始时间: $(Get-Date -Format 'HH:mm:ss')`n"

# 全局数据（只需抓取一次）
Write-Host "[全局] 获取板块数据..."
$globalSectors = Get-SectorData -Top 20
$globalSectorFund = Get-SectorFundFlow -Top 20
Write-Host "  ✅ 板块TOP20已获取 ($($globalSectors.Count) 行业 / $($globalSectorFund.Count) 资金流向)`n"

$results = @()
$script:evalStocks = @()
$total = $stocks.Count
$idx = 0
foreach ($s in $stocks) {
    $idx++
    $code = $s.Code; $name = $s.Name
    $folderName = "${name}(${code})"
    $outDir = Join-Path $outRoot $folderName
    $pdfFile = Join-Path $outDir "${folderName}分析报告__${dateStr}.pdf"
    $htmlFile = Join-Path $outDir "${folderName}_${dateStr}.html"

    if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir -Force | Out-Null }

    Write-Host "[$idx/$total] $name($code) — 开始分析 $(Get-Date -Format 'HH:mm:ss')"

    # 数据采集
    $stockData = Collect-StockFullData -Code $code
    Write-Host "  [数据] 报价:$($stockData.Quote.Name) K线:$($stockData.KLines.Count)日 财务:$($stockData.Financial.Count)季 研报:$($stockData.Research.Count)篇"

    # 评分
    $techS = Get-TechScore -D $stockData
    $fundS = Get-FundamentalScore -D $stockData
    $sentS = Get-SentimentScore -D $stockData
    $sectS = Get-SectorScore -D $stockData -GlobalSectors $globalSectors -GlobalSectorFund $globalSectorFund
    $capS = Get-CapitalScore -D $stockData
    $macS = Get-MacroScore -GlobalSectors $globalSectors
    $comp = Get-CompositeScore -TechS $techS -FundS $fundS -SentS $sentS -SectS $sectS -CapS $capS -MacS $macS
    $health = Get-TrendHealth -D $stockData
    $pred = Get-ThreePeriodPrediction -D $stockData -TechS $techS -FundS $fundS -SectS $sectS -CapS $capS
    $scores = @{ Technical=$techS; Fundamental=$fundS; Sentiment=$sentS; Sector=$sectS; Capital=$capS; Macro=$macS; Composite=$comp.Score; Rating=$comp.Rating; RatingShort=$comp.RatingShort }
    Write-Host "  [评分] 技术$techS 基本面$fundS 消息$sentS 板块$sectS 资金$capS 宏观$macS → 综合$($comp.Score)分 [$($comp.RatingShort)]"
    Write-Host "  [预判] 短期:$($pred.Short) 中期:$($pred.Mid) 长期:$($pred.Long) 支撑:$($pred.Support) 阻力:$($pred.Resistance)"

    # 操作建议计算 (v2.0)
    $ops = Get-OperationPlan -D $stockData -Pred $pred -TechS $techS -FundS $fundS -CompScore $comp.Score
    Write-Host "  [操作] S1:$($ops.S1) R1:$($ops.R1) 止损:$($ops.StopLoss) 仓位上限:$($ops.MaxPosition)%"

    # 生成HTML
    $html = New-StockReportHtml -D $stockData -Scores $scores -Pred $pred -Health $health -Ops $ops -GlobalSectors $globalSectors -GlobalSectorFund $globalSectorFund -dateLabel $dateLabel
    [System.IO.File]::WriteAllText($htmlFile, $html, [System.Text.Encoding]::UTF8)
    Write-Host "  [HTML] $htmlFile"

    # 转PDF
    $ok = Convert-HtmlToPdf -HtmlFile $htmlFile -PdfFile $pdfFile
    if ($ok) {
        $sizeKB = [Math]::Round((Get-Item $pdfFile).Length / 1KB)
        Write-Host "  [PDF] ✅ $pdfFile ($sizeKB KB)"
        $results += [PSCustomObject]@{ Name=$name; Code=$code; Score=$comp.Score; Rating=$comp.RatingShort; Status="✅"; PdfKB=$sizeKB }
    } else {
        Write-Host "  [PDF] ❌ 转换失败，HTML文件保留: $htmlFile"
        $results += [PSCustomObject]@{ Name=$name; Code=$code; Score=$comp.Score; Rating=$comp.RatingShort; Status="❌"; PdfKB=0 }
    }

    if (-not $KeepHtml) {
        if (Test-Path $htmlFile) { Remove-Item $htmlFile -Force }
    }

    # 累积评估数据（含指标级信号）
    # --- 构建信号状态 ---
    $_ma5 = $stockData.MA5[-1]; $_ma10 = $stockData.MA10[-1]; $_ma20 = $stockData.MA20[-1]; $_p = $stockData.Price
    $_maTrend = if ($_ma5 -gt $_ma10 -and $_ma10 -gt $_ma20 -and $_p -gt $_ma20) { "多头排列" } elseif ($_ma5 -lt $_ma10 -and $_ma10 -lt $_ma20) { "空头排列" } else { "纠缠/不明" }
    $_macdPos = if ($stockData.MACD) { $d=$stockData.MACD.DIF[-1]; $e=$stockData.MACD.DEA[-1]; if($d -gt $e -and $d -gt 0){"零轴上金叉"}elseif($d -gt $e){"零轴下金叉"}else{"死叉"} } else { "N/A" }
    $_rsiVal = if ($stockData.RSI14.Count -gt 0) { [double]$stockData.RSI14[-1] } else { 50 }
    $_rsiZone = if ($_rsiVal -ge 70) { "超买" } elseif ($_rsiVal -ge 50) { "中性偏强" } elseif ($_rsiVal -ge 30) { "中性偏弱" } else { "超卖" }
    $_bollPos = if ($stockData.Bollinger -and $stockData.KLines.Count -gt 0) { $c=$stockData.KLines[-1].Close; $u=$stockData.Bollinger.Upper[-1]; $m=$stockData.Bollinger.MA[-1]; $l=$stockData.Bollinger.Lower[-1]; if($c -ge $u){"触及上轨"}elseif($c -ge $m){"中轨上方"}elseif($c -ge $l){"中轨下方"}else{"触及下轨"} } else { "N/A" }
    $_volRel = if ($stockData.VolMA5.Count -gt 1 -and $stockData.VolMA5[-2] -gt 0) { $vr=$stockData.KLines[-1].Volume/$stockData.VolMA5[-2]; $cg=$stockData.Quote.ChangePct; if($cg -ge 2 -and $vr -ge 1.5){"放量上涨"}elseif($cg -ge 0 -and $vr -le 1.1){"缩量上涨"}elseif($cg -lt -2 -and $vr -ge 1.5){"放量下跌"}elseif($cg -lt 0 -and $vr -le 0.8){"缩量下跌"}else{"量能正常"} } else { "N/A" }
    $_fin = $stockData.Financial
    $_roeLevel = if ($_fin -and $_fin.Count -gt 0) { $r=[double]$_fin[0].WEIGHTAVG_ROE; if($r -ge 15){"优秀(≥15%)"}elseif($r -ge 10){"良好(≥10%)"}elseif($r -ge 5){"一般(≥5%)"}else{"较差(<5%)"} } else { "N/A" }
    $_peZone = if ($stockData.PEPercentile) { $p=$stockData.PEPercentile.Percentile; if($p -lt 20){"低估(<20%)"}elseif($p -lt 40){"偏低(20-40%)"}elseif($p -lt 60){"合理(40-60%)"}elseif($p -lt 80){"偏高(60-80%)"}else{"高估(>80%)"} } else { "N/A" }
    $_debtLevel = if ($_fin -and $_fin.Count -gt 0) { $d=[double]$_fin[0].DEBT_ASSET_RATIO; if($d -lt 30){"低杠杆"}elseif($d -lt 50){"合理"}elseif($d -lt 65){"偏高"}else{"高杠杆"} } else { "N/A" }
    $_rCover = if ($stockData.Research -and $stockData.Research.Count -gt 0) { "有($($stockData.Research.Count)篇)" } else { "无研报" }
    $_ffTrend = if ($stockData.FundFlow -and $stockData.FundFlow.Count -gt 0) { $pos=($stockData.FundFlow | Where-Object {$_.MainNetInflow -gt 0}).Count; if($pos -ge 3){"主力持续流入"}elseif($pos -ge 1){"主力流入>流出"}else{"主力流出"} } else { "N/A" }

    $script:evalStocks += @{
        Code = $code; Name = $name; Industry = $s.Industry; Date = $dateStr; Price = [Math]::Round($stockData.Price, 2)
        Scores = @{ Technical=$techS; Fundamental=$fundS; Sentiment=$sentS; Sector=$sectS; Capital=$capS; Macro=$macS; Composite=$comp.Score }
        Rating = $comp.RatingShort; RatingFull = $comp.Rating
        Prediction = @{ Short=$pred.Short; Mid=$pred.Mid; Long=$pred.Long; Confidence=$pred.Confidence; ShortBull=$pred.ShortBull; MidBull=$pred.MidBull; LongBull=$pred.LongBull }
        KeyLevels = @{ Support=[Math]::Round($pred.Support,2); Resistance=[Math]::Round($pred.Resistance,2); StopLoss=[Math]::Round($pred.StopLoss,2) }
        TrendHealth = @{ Score=$health.Score; Label=$health.Label }
        Signals = @{
            MA_Trend = $_maTrend; MACD_Position = $_macdPos
            RSI_Value = [Math]::Round($_rsiVal,1); RSI_Zone = $_rsiZone
            Bollinger_Position = $_bollPos; Volume_Relation = $_volRel
            ROE_Level = $_roeLevel; PE_Percentile_Zone = $_peZone; Debt_Level = $_debtLevel
            Research_Coverage = $_rCover; FundFlow_Trend = $_ffTrend
            ShortBull_Score = $pred.ShortBull; MidBull_Score = $pred.MidBull; LongBull_Score = $pred.LongBull
        }
    }

    Write-Host ""

    Write-Host ""
}

# ============================================================
# Summary
# ============================================================
Write-Host "`n========== 完成汇总 =========="
Write-Host "总耗时: $(Get-Date -Format 'HH:mm:ss') | API调用次数: $script:apiCallCount"
Write-Host ""
$results | Format-Table Name, Code, @{N="综合分";E={$_.Score}}, Rating, Status, @{N="PDF大小";E={"$($_.PdfKB)KB"}} -AutoSize
Write-Host "`n输出目录: $outRoot"
Write-Host "=============================="

# 保存评估数据JSON（用于次日复盘）
$evalDir = Join-Path (Join-Path $rootDir "重点股票") "次日评估"
if (-not (Test-Path $evalDir)) { New-Item -ItemType Directory -Path $evalDir -Force | Out-Null }
$evalFile = Join-Path $evalDir "评估数据_${dateStr}.json"
@{ Date=$dateStr; GeneratedAt=(Get-Date -Format 'yyyy-MM-dd HH:mm:ss'); Stocks=$script:evalStocks } |
    ConvertTo-Json -Depth 10 | Set-Content $evalFile -Encoding UTF8
Write-Host "评估数据保存: $evalFile"

