# 铁律量化 - 重点股票分析报告生成引擎
# 基于：重点股票跟踪分析逻辑白皮书 v3.0
# 输出：每只股票独立PDF分析报告
# 数据源：[1]~[12] HTTP API已实测
# 最后更新：2026-05-23
# 引擎版本：v3.0
# 变更：全面对齐白皮书v3.0 — 权重调整/四维技术框架/极端事件/不做清单/信号冲突裁决/ADX+OBV+RSI9/扣非+商誉+杜邦/Wyckoff量化/板块相位量化/预期差框架/催化剂市值调整/机构共识修正

param(
    [string]$Date = "",           # 指定日期 YYYY-MM-DD 或 YYYYMMDD，默认今天
    [switch]$KeepHtml = $false,    # 保留中间HTML文件
    [string[]]$TargetStocks = @()  # 指定股票代码，默认全部6只
)
. "$PSScriptRoot/../lib/init_encoding.ps1"

# ============================================================
# 配置
# ============================================================
$rootDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$outRoot = Join-Path $rootDir "重点股票\股票报告"
$modulePath = Join-Path $rootDir "代码文件\每日荐股\scripts\stock_data_fetcher.psm1"
$edgePath = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

if ($Date -ne "") {
    # 支持 YYYYMMDD 和 YYYY-MM-DD / YYYY/MM/DD 格式
    if ($Date -match '^(\d{4})(\d{2})(\d{2})$') { $Date = "$($matches[1])-$($matches[2])-$($matches[3])" }
    $reportDate = Get-Date $Date
} else { $reportDate = Get-Date }
$dateStr = $reportDate.ToString("yyyyMMdd")
$dateLabel = $reportDate.ToString("yyyy-MM-dd")

# 交易日检查（非交易日跳过，除非显式 -Force）
$marketCheckScript = Join-Path $rootDir "代码文件\每日荐股\scripts\is_market_open.ps1"
$holidayFile = Join-Path $rootDir "每日荐股\运营记录\holidays_2026.csv"
if (Test-Path $marketCheckScript) {
    $isOpen = & $marketCheckScript -Date $dateLabel -HolidayFile $holidayFile
    if ($LASTEXITCODE -ne 0) {
        Write-Host "非交易日 ($dateLabel)，跳过重点股票分析" -ForegroundColor Yellow
        exit 0
    }
    Write-Host "交易日确认: $dateLabel" -ForegroundColor Green
}

# 全部6只股票
$allStocks = @(
    @{ Code = "603019"; Name = "中科曙光"; Industry = "计算机" },
    @{ Code = "601689"; Name = "拓普集团"; Industry = "汽车零部件" },
    @{ Code = "600114"; Name = "东睦股份"; Industry = "电子/机械" },
    @{ Code = "301075"; Name = "多瑞医药"; Industry = "医药" },
    @{ Code = "000967"; Name = "盈峰环境"; Industry = "环保" },
    @{ Code = "601727"; Name = "上海电气"; Industry = "电力设备" },
    @{ Code = "600584"; Name = "长电科技"; Industry = "半导体" }
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
    $ma5 = @(); $ma10 = @(); $ma20 = @(); $ma50 = @(); $ma120 = @(); $ma60 = @()
    $rsi14 = @(); $rsi9 = @(); $macd = $null; $boll = $null; $vol5 = @(); $vol20 = @()
    $adx = $null; $obv = @(); $atr = @()
    if ($klines.Count -ge 20) {
        $ma5 = Measure-MovingAverage -Data $klines -Period 5
        $ma10 = Measure-MovingAverage -Data $klines -Period 10
        $ma20 = Measure-MovingAverage -Data $klines -Period 20
        $rsi14 = Measure-RSI -Data $klines -Period 14
        $rsi9 = Measure-RSI -Data $klines -Period 9
        $macd = Measure-MACD -Data $klines
        $boll = Measure-Bollinger -Data $klines
        $vol5 = Measure-MovingAverage -Data $klines -Field "Volume" -Period 5
        $vol20 = Measure-MovingAverage -Data $klines -Field "Volume" -Period 20
        $obv = Measure-OBV -Data $klines
        $atr = Measure-ATR -Data $klines -Period 14
        if ($klines.Count -ge 30) { $adx = Measure-ADX -Data $klines -Period 14 }
        if ($klines.Count -ge 50) { $ma50 = Measure-MovingAverage -Data $klines -Period 50 }
        if ($klines.Count -ge 60) { $ma60 = Measure-MovingAverage -Data $klines -Period 60 }
        if ($klines.Count -ge 120) { $ma120 = Measure-MovingAverage -Data $klines -Period 120 }
    }

    # [3] 财务数据
    $financial = Invoke-ThrottledApi { Get-StockFinancial -Code $Code -Quarters 4 }

    # [2]+[3]→[5] PE百分位（5年→3年→2年 阶梯降级，兼容上市不足5年的次新股）
    $pePercentile = Invoke-ThrottledApi { Get-PEPercentile -Code $Code -LookbackYears 5 }
    if (-not $pePercentile) { $pePercentile = Invoke-ThrottledApi { Get-PEPercentile -Code $Code -LookbackYears 3 } }
    if (-not $pePercentile) { $pePercentile = Invoke-ThrottledApi { Get-PEPercentile -Code $Code -LookbackYears 2 } }

    # [9] 个股资金流向
    $fundFlow = Invoke-ThrottledApi { Get-StockFundFlow -Code $Code -Days 5 }

    # [8] 北向资金
    $northbound = Invoke-ThrottledApi { Get-NorthboundHold -Code $Code }

    # [11] 研报
    $research = Invoke-ThrottledApi { Get-StockResearch -Code $Code -Count 5 -DaysBack 90 }

    # [12] 融资融券
    $margin = Invoke-ThrottledApi { Get-MarginData -Code $Code -Days 5 }

    return [PSCustomObject]@{
        Code = $Code; Name = $quote.Name; Price = $quote.Price
        Quote = $quote; KLines = $klines
        MA5 = $ma5; MA10 = $ma10; MA20 = $ma20; MA50 = $ma50; MA120 = $ma120; MA60 = $ma60
        RSI14 = $rsi14; RSI9 = $rsi9; MACD = $macd; Bollinger = $boll
        ADX = $adx; OBV = $obv; ATR = $atr
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
    if (-not $D.KLines -or $D.KLines.Count -lt 30) { return 40 }

    # === v3.0: 四维独立确认框架（每维度1个核心指标，消除共线伪多重验证）===

    # A. 趋势维度 — ADX(14) (25分)
    $adxVal = 0; $pdi = 0; $mdi = 0
    if ($D.ADX -and $D.ADX.ADX.Count -gt 0 -and $D.ADX.ADX[-1] -ne $null) {
        $adxVal = [double]$D.ADX.ADX[-1]
        $pdi = [double]$D.ADX.PlusDI[-1]; $mdi = [double]$D.ADX.MinusDI[-1]
        if ($adxVal -gt 25 -and $pdi -gt $mdi) { $score += 25 }
        elseif ($adxVal -gt 25 -and $mdi -gt $pdi) { $score += 5 }
        elseif ($adxVal -gt 20 -and $pdi -gt $mdi) { $score += 15 }
        elseif ($adxVal -gt 20) { $score += 8 }
        elseif ($adxVal -lt 20 -and $pdi -gt $mdi) { $score += 10 }
        else { $score += 5 }
    } else {
        # Fallback to MA trend when ADX unavailable
        $ma5v = $D.MA5[-1]; $ma10v = $D.MA10[-1]; $ma20v = $D.MA20[-1]; $price = $D.Price
        if ($ma5v -gt $ma10v -and $ma10v -gt $ma20v -and $price -gt $ma20v) { $score += 25 }
        elseif ($ma5v -gt $ma10v -and $price -gt $ma10v) { $score += 15 }
        elseif ($ma5v -gt $ma10v) { $score += 10 }
        elseif ($ma5v -lt $ma10v -and $ma10v -lt $ma20v) { $score += 3 }
        else { $score += 8 }
    }

    # B. 动量维度 — RSI(9) A股适配 (25分)
    $rsi = if ($D.RSI9.Count -gt 0 -and $D.RSI9[-1] -ne $null) { [double]$D.RSI9[-1] } else { [double]$D.RSI14[-1] }
    if ($rsi -ge 40 -and $rsi -le 60) {
        # Check direction
        $rsiPrev = if ($D.RSI9.Count -ge 3 -and $D.RSI9[-3] -ne $null) { [double]$D.RSI9[-3] } else { $rsi }
        if ($rsi -gt $rsiPrev) { $score += 25 } else { $score += 18 }
    }
    elseif ($rsi -gt 60 -and $rsi -le 75) { $score += 15 }
    elseif ($rsi -gt 75) { $score += 5 }
    elseif ($rsi -gt 30 -and $rsi -lt 40) { $score += 8 }
    else { $score += 5 }

    # C. 波动维度 — Bollinger Bands (25分)
    if ($D.Bollinger -and $D.Bollinger.MA.Count -gt 0) {
        $close = $D.KLines[-1].Close; $bm = $D.Bollinger.MA[-1]
        $bu = $D.Bollinger.Upper[-1]; $bd = $D.Bollinger.Lower[-1]
        $bmPrev = if ($D.Bollinger.MA.Count -ge 5) { $D.Bollinger.MA[-5] } else { $bm }
        if ($close -ge $bm -and $close -le $bu -and $bm -gt $bmPrev) { $score += 25 }
        elseif ($close -lt $bm -and $close -gt $bd -and $bm -gt $bmPrev) { $score += 15 }
        elseif ($close -ge $bu) { $score += 10 }
        elseif ($close -le $bd) { $score += 5 }
        else { $score += 12 }
    } else { $score += 12 }

    # D. 量能维度 — OBV (25分)
    if ($D.OBV -and $D.OBV.Count -ge 10) {
        $obvNow = $D.OBV[-1]; $obv5ago = if ($D.OBV.Count -ge 6) { $D.OBV[-6] } else { $D.OBV[0] }
        $obvTrend = if ($obv5ago -ne 0) { ($obvNow - $obv5ago) / [Math]::Abs($obv5ago) * 100 } else { 0 }
        $priceNow = $D.Price; $price5ago = $D.KLines[-6].Close
        $priceTrend = if ($price5ago -ne 0) { ($priceNow - $price5ago) / $price5ago * 100 } else { 0 }
        # OBV与价格同向 = 趋势确认；OBV与价格背离 = 预警
        if ($obvTrend -gt 2 -and $priceTrend -gt 0) { $score += 25 }
        elseif ($obvTrend -gt 0 -and $priceTrend -gt 0) { $score += 20 }
        elseif ($obvTrend -gt 2 -and $priceTrend -lt 0) { $score += 8 }
        elseif ($obvTrend -lt -2 -and $priceTrend -lt 0) { $score += 5 }
        elseif ($obvTrend -gt 0) { $score += 12 }
        else { $score += 8 }
    } else {
        # Fallback to volume analysis
        $vol = $D.KLines[-1].Volume; $v5 = $D.VolMA5[-2]; $chg = $D.Quote.ChangePct
        if ($chg -ge 2 -and $vol -gt $v5 * 1.5) { $score += 25 }
        elseif ($chg -ge 0 -and $vol -le $v5 * 1.2) { $score += 12 }
        elseif ($chg -lt -2 -and $vol -gt $v5 * 1.5) { $score += 5 }
        elseif ($chg -lt 0 -and $vol -lt $v5 * 0.8) { $score += 18 }
        else { $score += 10 }
    }

    # P1-1: 量价质量乘数 — 缩量上涨/放量下跌扣分（红线§4 证据加权原则）
    $volQualityMultiplier = 1.0
    if ($D.KLines.Count -ge 3 -and $D.VolMA5.Count -gt 1) {
        $latestVol = $D.KLines[-1].Volume
        $avgVol5 = $D.VolMA5[-2]
        $priceChg = $D.Quote.ChangePct
        if ($avgVol5 -gt 0) {
            $volRatio = $latestVol / $avgVol5
            if ($priceChg -gt 0 -and $volRatio -lt 1.0) { $volQualityMultiplier = 0.85 }      # 缩量上涨→量价背离
            elseif ($priceChg -lt -2 -and $volRatio -gt 1.5) { $volQualityMultiplier = 0.75 } # 放量下跌→主力出货
            elseif ($priceChg -gt 2 -and $volRatio -gt 1.5) { $volQualityMultiplier = 1.05 }  # 放量上涨→轻微加分
        }
    }
    $score = [Math]::Round($score * $volQualityMultiplier)

    return [Math]::Min([Math]::Max($score, 0), 100)
}

function Get-FundamentalScore {
    param($D)
    $score = 0
    $script:DataIssueFlag = $false
    $fin = $D.Financial
    if (-not $fin -or $fin.Count -eq 0) { return 40 }

    # A. ROE (15分) + 杜邦拆解
    $roe = [double]$fin[0].WEIGHTAVG_ROE
    $dupontNote = ""
    if ($fin[0].PSObject.Properties.Name -contains 'NET_PROFIT_MARGIN') {
        $netMargin = [double]$fin[0].NET_PROFIT_MARGIN
        $turnover = if ($fin[0].PSObject.Properties.Name -contains 'ASSET_TURNOVER') { [double]$fin[0].ASSET_TURNOVER } else { 0 }
        $leverage = if ($fin[0].PSObject.Properties.Name -contains 'EQUITY_MULTIPLIER') { [double]$fin[0].EQUITY_MULTIPLIER } else { [double]$fin[0].DEBT_ASSET_RATIO / 100 + 1 }
        if ($leverage -gt 3.5) { $dupontNote = " [杠杆乘数>$leverage,高杠杆驱动]"; $score += 5 }
        elseif ($netMargin -gt 15) { $score += 12 }
        elseif ($netMargin -gt 8) { $score += 8 }
        else { $score += 4 }
    }
    if ($roe -ge 15) { $score += 3 }
    elseif ($roe -ge 10) { $score += 2 }
    elseif ($roe -ge 5) { $score += 1 }
    else { $score += 0 }

    # B. 扣非净利润增长率 (15分) — A股必须
    $deductedGrowth = 0; $hasDeducted = $false
    if ($fin[0].PSObject.Properties.Name -contains 'DEDUCTED_PROFIT') {
        $dp0 = [double]$fin[0].DEDUCTED_PROFIT
        if ($fin.Count -ge 2 -and $fin[1].PSObject.Properties.Name -contains 'DEDUCTED_PROFIT') {
            $dp1 = [double]$fin[1].DEDUCTED_PROFIT
            if ($dp1 -ne 0) { $deductedGrowth = ($dp0 - $dp1) / [Math]::Abs($dp1) * 100; $hasDeducted = $true }
        }
    }
    if ($hasDeducted) {
        if ($deductedGrowth -ge 30) { $score += 15 }
        elseif ($deductedGrowth -ge 15) { $score += 12 }
        elseif ($deductedGrowth -ge 0) { $score += 7 }
        elseif ($deductedGrowth -ge -10) { $score += 3 }
        else { $score += 0 }
    } else {
        # Fallback: 营收增速
        if ($fin.Count -ge 2 -and [double]$fin[1].TOTAL_OPERATE_INCOME -ne 0) {
            $rg = ([double]$fin[0].TOTAL_OPERATE_INCOME - [double]$fin[1].TOTAL_OPERATE_INCOME) / [Math]::Abs([double]$fin[1].TOTAL_OPERATE_INCOME) * 100
            if ($rg -ge 30) { $score += 9 }
            elseif ($rg -ge 15) { $score += 7 }
            elseif ($rg -ge 0) { $score += 4 }
            elseif ($rg -ge -10) { $score += 2 }
        } else { $score += 5 }
    }

    # C. 毛利率 (10分) — P0-1: 数据异常校验
    $rev = [double]$fin[0].TOTAL_OPERATE_INCOME; $cost = [double]$fin[0].OPERATE_COST
    if ($rev -gt 0 -and $cost -gt 0) {
        $gm = ($rev - $cost) / $rev * 100
        # 合理性检查：毛利率≥99%极可能数据异常（OPERATE_COST≈0）
        if ($gm -ge 99) { $score += 5; $script:DataIssueFlag = $true }
        elseif ($gm -ge 50) { $score += 10 }
        elseif ($gm -ge 30) { $score += 8 }
        elseif ($gm -ge 15) { $score += 5 }
        elseif ($gm -ge 5) { $score += 2 }
        else { $score += 0 }
    } else { $score += 5; $script:DataIssueFlag = $true }

    # D. 商誉/净资产 (15分) — A股并购雷区
    $goodwill = 0; $equity = 0; $hasGoodwill = $false
    if ($fin[0].PSObject.Properties.Name -contains 'GOODWILL') {
        $goodwill = [double]$fin[0].GOODWILL
        if ($fin[0].PSObject.Properties.Name -contains 'TOTAL_EQUITY') {
            $equity = [double]$fin[0].TOTAL_EQUITY
        } elseif ($fin[0].PSObject.Properties.Name -contains 'PARENT_EQUITY') {
            $equity = [double]$fin[0].PARENT_EQUITY
        }
        if ($equity -gt 0) { $hasGoodwill = $true; $gwRatio = $goodwill / $equity * 100 }
    }
    if ($hasGoodwill) {
        if ($gwRatio -lt 15) { $score += 15 }
        elseif ($gwRatio -lt 30) { $score += 10 }
        elseif ($gwRatio -lt 50) { $score += 4 }
        else { $score += 0 }
    } else { $score += 8 }

    # E. PE百分位 (15分)
    $pep = $D.PEPercentile
    if ($pep) {
        $pct = $pep.Percentile
        if ($pct -lt 20) { $score += 15 }
        elseif ($pct -lt 40) { $score += 11 }
        elseif ($pct -lt 60) { $score += 7 }
        elseif ($pct -lt 80) { $score += 4 }
        else { $score += 1 }
    } else { $score += 7 }

    # F. PEG (10分) — PE / 一致预期净利润增速
    if ($pep -and $pep.CurrentPE -gt 0) {
        $consensusGrowth = $null
        if ($D.Research -and @($D.Research).Count -gt 0) {
            $epsVals = @($D.Research | Where-Object { $_.ThisYearEPS -gt 0 } | ForEach-Object { $_.ThisYearEPS })
            if ($epsVals.Count -gt 0) { $consensusGrowth = ($epsVals | Measure-Object -Average).Average }
        }
        if ($consensusGrowth -and $consensusGrowth -gt 0) {
            $peg = $pep.CurrentPE / $consensusGrowth
            if ($peg -lt 0.8) { $score += 10 }
            elseif ($peg -lt 1.2) { $score += 7 }
            elseif ($peg -lt 1.8) { $score += 4 }
            else { $score += 1 }
        } else {
            # TTM fallback
            if ($deductedGrowth -gt 0) {
                $pegTTM = $pep.CurrentPE / $deductedGrowth
                if ($pegTTM -lt 0.8) { $score += 7 }
                elseif ($pegTTM -lt 1.5) { $score += 4 }
                else { $score += 2 }
            } else { $score += 3 }
        }
    } else { $score += 4 }

    # G. 负债率 (10分) — P0-1: 数据异常校验
    $debt = [double]$fin[0].DEBT_ASSET_RATIO
    if ($debt -eq 0) { $score += 5; $script:DataIssueFlag = $true }
    elseif ($debt -lt 30) { $score += 10 }
    elseif ($debt -lt 50) { $score += 7 }
    elseif ($debt -lt 65) { $score += 4 }
    elseif ($debt -lt 80) { $score += 1 }
    else { $score += 0 }

    # P1-2: 亏损股基本面分数封顶（红线§1.3 数据驱动+§4 风险第一）
    $netProfit = [double]$fin[0].PARENT_NETPROFIT
    $roeVal = [double]$fin[0].WEIGHTAVG_ROE
    if ($netProfit -lt 0) { $score = [Math]::Min($score, 45) }
    elseif ($roeVal -lt 0) { $score = [Math]::Min($score, 50) }

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
    $industry = ""
    if ($D.Financial -and $D.Financial.Count -gt 0 -and $D.Financial[0].INDUSTRY) {
        $industry = $D.Financial[0].INDUSTRY
    }
    # A. 板块相位 (35分)
    $secData = $null; $secFund = $null
    if ($industry -ne "") {
        $secData = $GlobalSectors | Where-Object { $_.SectorName -eq $industry }
        $secFund = $GlobalSectorFund | Where-Object { $_.SectorName -eq $industry }
    }
    if ($secData) {
        $chg = $secData.ChangePct
        if     ($chg -ge 3)   { $score += 35 }
        elseif ($chg -ge 1)   { $score += 26 }
        elseif ($chg -ge 0)   { $score += 18 }
        elseif ($chg -ge -1)  { $score += 12 }
        else                  { $score += 5 }
    } else {
        # P2-2: 未匹配行业时，用个股涨跌幅vs市场均值做差异化，不再给固定分
        $avgChg = ($GlobalSectors | Measure-Object ChangePct -Average).Average
        $stockChg = $D.Quote.ChangePct
        $diff = $stockChg - $avgChg
        if     ($diff -gt 2)   { $score += 28 }
        elseif ($diff -gt 0)   { $score += 20 }
        elseif ($diff -gt -2)  { $score += 12 }
        else                   { $score += 5 }
    }
    # B. 板块资金流 (30分)
    if ($secFund) {
        $ni = $secFund.NetInflow
        if     ($ni -gt 5e8)   { $score += 30 }
        elseif ($ni -gt 0)     { $score += 20 }
        elseif ($ni -gt -3e8)  { $score += 10 }
        else                   { $score += 3 }
    } else { $score += 15 }
    # C. 个股相对强度 (35分) — P2-2: 增加行业差异化
    $stockChg2 = $D.Quote.ChangePct
    if ($secData) {
        $relStr = $stockChg2 - $secData.ChangePct
    } else {
        $relStr = $stockChg2 - $avgChg
    }
    if     ($relStr -gt 3)   { $score += 35 }
    elseif ($relStr -gt 1)   { $score += 26 }
    elseif ($relStr -gt 0)   { $score += 18 }
    elseif ($relStr -gt -2)  { $score += 10 }
    else                     { $score += 4 }
    return [Math]::Min([Math]::Max($score, 0), 100)
}

function Get-CapitalScore {
    param($D)
    $score = 0
    # A. 主力资金 (35分)
    $ff = $D.FundFlow
    if ($ff -and @($ff).Count -gt 0) {
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

    # A. 市场广度 (35分) — 板块涨跌比
    $positive = ($GlobalSectors | Where-Object { $_.ChangePct -ge 0 }).Count
    $posRatio = $positive / $total
    $score += [Math]::Round($posRatio * 35)

    # B. 强势板块占比 (25分) — 阈值≥3%为强势
    $strong = ($GlobalSectors | Where-Object { $_.ChangePct -ge 3 }).Count
    $strongRatio = $strong / $total
    $score += [Math]::Round([Math]::Min($strongRatio * 100, 25))

    # C. 资金情绪 (20分)
    $avgTurnover = ($GlobalSectors | Measure-Object Turnover -Average).Average
    if ($avgTurnover -gt 100) { $score += 20 }
    elseif ($avgTurnover -gt 50) { $score += 14 }
    elseif ($avgTurnover -gt 20) { $score += 8 }
    else { $score += 3 }

    # D. 市场阶段判定 (20分) — P2-1: 增加实质性分析
    $avgChg = ($GlobalSectors | Measure-Object ChangePct -Average).Average
    if ($posRatio -ge 0.8 -and $avgChg -ge 2) { $score += 20 }       # 强势普涨
    elseif ($posRatio -ge 0.6 -and $avgChg -ge 0) { $score += 14 }   # 偏强震荡
    elseif ($posRatio -ge 0.4 -and $avgChg -ge -1) { $score += 8 }   # 弱势震荡
    elseif ($posRatio -ge 0.2) { $score += 4 }                       # 偏弱
    else { $score += 0 }                                              # 恐慌

    $phaseLabel = if ($score -ge 80) { "强势普涨" } elseif ($score -ge 60) { "偏强震荡" } elseif ($score -ge 40) { "弱势震荡" } elseif ($score -ge 20) { "偏弱调整" } else { "恐慌退潮" }

    return [PSCustomObject]@{ Score = [Math]::Min($score, 100); Phase = $phaseLabel; PosRatio = [Math]::Round($posRatio*100,0); AvgChg = [Math]::Round($avgChg,1) }
}

# ============================================================
# Phase 3: 综合评分 + 趋势健康度 + 三周期预判
# ============================================================

function Get-CompositeScore {
    param($TechS, $FundS, $SentS, $SectS, $CapS, $MacS)
    $composite = $TechS * 0.20 + $FundS * 0.20 + $SentS * 0.15 + $SectS * 0.18 + $CapS * 0.15 + $MacS * 0.12
    $composite = [Math]::Round([Math]::Max([Math]::Min($composite, 100), 0))
    # [回测:原阈值85/70/55/40评分区分度仅0.32%,下调为80/65/45/30]
    $rating = if     ($composite -ge 80) { "★★★★ 强烈关注" }
              elseif ($composite -ge 65) { "★★★ 关注" }
              elseif ($composite -ge 45) { "★★ 观察" }
              elseif ($composite -ge 30) { "★ 谨慎" }
              else                       { "☆ 回避" }
    $ratingShort = if ($composite -ge 80) { "强烈关注" } elseif ($composite -ge 65) { "关注" } elseif ($composite -ge 45) { "观察" } elseif ($composite -ge 30) { "谨慎" } else { "回避" }
    return @{ Score = $composite; Rating = $rating; RatingShort = $ratingShort }
}

function Get-TrendHealth {
    param($D)
    $h = 0
    if (-not $D.KLines -or $D.KLines.Count -lt 20) { return @{ Score = 50; Label = "数据不足" } }

    # 1. 回调幅度 (15分) — 价格维度
    $high20 = ($D.KLines[-20..-1] | Measure-Object High -Maximum).Maximum
    $pullback = ($high20 - $D.Price) / $high20 * 100
    if     ($pullback -lt 3)   { $h += 15 }
    elseif ($pullback -lt 8)   { $h += 11 }
    elseif ($pullback -lt 15)  { $h += 6 }
    else                       { $h += 1 }

    # 2. 量能趋势 (12分) — 量能维度
    $recentVol = ($D.KLines[-3..-1] | Measure-Object Volume -Average).Average
    $avgVol = $D.VolMA20[-1]
    if ($avgVol -gt 0) {
        $vr = $recentVol / $avgVol
        if     ($vr -ge 1.2)  { $h += 12 }
        elseif ($vr -ge 0.8)  { $h += 8 }
        else                  { $h += 3 }
    } else { $h += 6 }

    # 3. 均线发散 (13分) — 价格维度
    $m5 = $D.MA5[-1]; $m20 = $D.MA20[-1]
    if ($m20 -gt 0) {
        $spread = ($m5 - $m20) / $m20 * 100
        if     ($spread -gt 2)   { $h += 13 }
        elseif ($spread -gt 0.5) { $h += 9 }
        elseif ($spread -gt -1)  { $h += 5 }
        elseif ($spread -gt -3)  { $h += 2 }
        else                     { $h += 0 }
    } else { $h += 6 }

    # 4. ADX状态 (15分) — 趋势维度
    if ($D.ADX -and $D.ADX.ADX.Count -gt 0 -and $D.ADX.ADX[-1] -ne $null) {
        $adxV = [double]$D.ADX.ADX[-1]; $pdi = [double]$D.ADX.PlusDI[-1]; $mdi = [double]$D.ADX.MinusDI[-1]
        if ($adxV -gt 25 -and $pdi -gt $mdi) { $h += 15 }
        elseif ($adxV -gt 25 -and $mdi -gt $pdi) { $h += 4 }
        elseif ($adxV -gt 20 -and $pdi -gt $mdi) { $h += 10 }
        elseif ($adxV -gt 20) { $h += 6 }
        elseif ($pdi -gt $mdi) { $h += 5 }
        else { $h += 2 }
    } else {
        # Fallback to MACD
        if ($D.MACD) {
            $df = $D.MACD.DIF[-1]; $da = $D.MACD.DEA[-1]; $mh = $D.MACD.MACD[-1]
            if ($df -gt $da -and $df -gt 0 -and $mh -gt 0) { $h += 15 }
            elseif ($df -gt $da -and $df -gt 0) { $h += 10 }
            elseif ($df -gt $da) { $h += 5 }
            else { $h += 2 }
        } else { $h += 7 }
    }

    # 5. RSI趋势 (10分) — 动量维度
    if ($D.RSI9.Count -ge 5 -and $D.RSI9[-1] -ne $null) {
        $rNow = [double]$D.RSI9[-1]; $rPrev = [double]$D.RSI9[-5]
        if ($rNow -ge 50 -and $rNow -le 70 -and $rNow -gt $rPrev) { $h += 10 }
        elseif ($rNow -ge 40 -and $rNow -le 60) { $h += 6 }
        elseif ($rNow -gt 75) { $h += 3 }
        elseif ($rNow -lt 30) { $h += 2 }
        else { $h += 5 }
    } else { $h += 5 }

    # 6. 资金流向共振 (15分) — v3.0 非价格维度
    $fundFlowScore = 7
    if ($D.FundFlow -and $D.FundFlow.Count -ge 3) {
        $posDays = ($D.FundFlow | Where-Object { $_.MainNetInflow -gt 0 }).Count
        $cumNet = ($D.FundFlow | ForEach-Object { $_.MainNetInflow } | Measure-Object -Sum).Sum
        if ($posDays -ge 3 -and $cumNet -gt 0) { $fundFlowScore = 15 }
        elseif ($posDays -ge 2 -and $cumNet -gt 0) { $fundFlowScore = 11 }
        elseif ($posDays -ge 1) { $fundFlowScore = 7 }
        else { $fundFlowScore = 3 }
    }
    # Northbound check
    if ($D.Northbound -and $D.Northbound.SharesRatio -gt 0) { $fundFlowScore = [Math]::Min($fundFlowScore + 3, 15) }
    $h += $fundFlowScore

    # 7. 板块共振度 (20分) — v3.0 非价格维度
    # Uses FundFlow as proxy for sector strength relative to market
    $sectorScore = 10
    if ($D.FundFlow -and @($D.FundFlow).Count -gt 0) {
        $recentMainIn = ($D.FundFlow[0].MainNetInflow)
        if ($recentMainIn -gt 5e7) { $sectorScore = 20 }
        elseif ($recentMainIn -gt 0) { $sectorScore = 15 }
        elseif ($recentMainIn -gt -3e7) { $sectorScore = 8 }
        else { $sectorScore = 4 }
    }
    $h += $sectorScore

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
    # [回测:看空胜率20%反向信号,改为中性]
    $shortDir = if     ($shortBull -ge 3) { "看多" } elseif ($shortBull -eq 2) { "偏多" } else { "中性" }
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
    # 关键价位（修复：价格在MA20下方时MA20为阻力非支撑）
    if ($D.MA20.Count -gt 0 -and $D.MA20[-1] -lt $D.Price) {
        $support = [Math]::Round($D.MA20[-1], 2)
    } else {
        $support = [Math]::Round($D.Price * 0.95, 2)
    }
    if ($D.MA50.Count -gt 0 -and $D.MA50[-1] -gt $D.Price) {
        $resistance = [Math]::Round($D.MA50[-1], 2)
    } elseif ($D.MA20.Count -gt 0 -and $D.MA20[-1] -gt $D.Price) {
        $resistance = [Math]::Round($D.MA20[-1], 2)
    } else {
        $resistance = [Math]::Round($D.Price * 1.05, 2)
    }
    $confidence = if ($shortBull -ge 3) { "高(>70%)" } elseif ($shortBull -eq 2) { "中(50-70%)" } else { "低(<50%)" }
    return @{
        Short = $shortDir; Mid = $midDir; Long = $longDir
        Support = $support; Resistance = $resistance
        Confidence = $confidence; ShortBull = $shortBull
        MidBull = $midBull; LongBull = $longBull
    }
}

# ============================================================
# Phase 3.5: 操作建议与交易计划计算（v2.0）
# ============================================================

function Get-VolumeProfile {
    param($KLines, [int]$NumBins = 50)
    $vp = $null
    if (-not $KLines -or $KLines.Count -lt 10) { return $vp }
    try {
        $vpInput = @{
            highs    = @($KLines | ForEach-Object { [double]$_.High })
            lows     = @($KLines | ForEach-Object { [double]$_.Low })
            closes   = @($KLines | ForEach-Object { [double]$_.Close })
            volumes  = @($KLines | ForEach-Object { [long]$_.Volume })
            num_bins = $NumBins
            lookback = 60
        } | ConvertTo-Json -Compress

        $vpCliPath = Join-Path $PSScriptRoot "..\每日荐股\分析逻辑\engine\vp_cli.py"
        $vpCliPath = [System.IO.Path]::GetFullPath($vpCliPath)
        if (-not (Test-Path $vpCliPath)) {
            Write-Host "  [VP] vp_cli.py not found: $vpCliPath" -ForegroundColor DarkGray
            return $vp
        }
        # Write input to temp file and pipe to Python (avoid PowerShell pipe issues)
        $tmpFile = [System.IO.Path]::GetTempFileName()
        try {
            [System.IO.File]::WriteAllText($tmpFile, $vpInput, [System.Text.UTF8Encoding]::new($false))
            $psi = New-Object System.Diagnostics.ProcessStartInfo
            $psi.FileName = 'python'
            $psi.Arguments = $vpCliPath
            $psi.RedirectStandardInput = $true
            $psi.RedirectStandardOutput = $true
            $psi.RedirectStandardError = $true
            $psi.UseShellExecute = $false
            $psi.CreateNoWindow = $true
            $proc = New-Object System.Diagnostics.Process
            $proc.StartInfo = $psi
            $proc.Start() | Out-Null
            $proc.StandardInput.Write($vpInput)
            $proc.StandardInput.Close()
            $vpJson = $proc.StandardOutput.ReadToEnd()
            $stderr = $proc.StandardError.ReadToEnd()
            $proc.WaitForExit(10000) | Out-Null
            if (-not $proc.HasExited) { $proc.Kill() }
        } finally {
            if (Test-Path $tmpFile) { Remove-Item $tmpFile -Force -ErrorAction SilentlyContinue }
        }
        if (-not $vpJson) {
            Write-Host "  [VP] python returned empty (stderr: $stderr)" -ForegroundColor DarkGray
            return $vp
        }
        try {
            $vp = $vpJson | ConvertFrom-Json
        } catch {
            Write-Host "  [VP] JSON parse failed: $_" -ForegroundColor DarkGray
        }
    } catch {
        Write-Host "  [VP] compute failed: $_" -ForegroundColor DarkGray
    }
    return $vp
}

function Get-OperationPlan {
    param($D, $Pred, $TechS, $FundS, $CompScore, $VP)

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
    # S3: v3.0 硬优先级链 — ATR×3 → 前低 → MA120 → MA250
    $s3Candidates = @()
    # ① ATR×3 (波动自适应)
    $s3Candidates += [PSCustomObject]@{ Priority=1; Name="ATR×3"; Value=[Math]::Round($P - $ATR * 3, 2) }
    # ② 前重要低点 — 60日最低价
    if ($recentLow) { $s3Candidates += [PSCustomObject]@{ Priority=2; Name="前低(60日)"; Value=$recentLow } }
    # ③ MA120 (趋势防守)
    if ($ma120) { $s3Candidates += [PSCustomObject]@{ Priority=3; Name="MA120"; Value=[Math]::Round($ma120, 2) } }
    # ④ MA250 not available from 120-day kline, skip
    # Pick highest value among valid candidates (least destructive stop)
    $validS3 = $s3Candidates | Where-Object { $_.Value -gt 0 -and $_.Value -lt $P }
    if ($validS3.Count -gt 0) {
        $s3 = [Math]::Round(($validS3 | Sort-Object Value -Descending | Select-Object -First 1).Value, 2)
    } else {
        $s3 = [Math]::Round($P * 0.90, 2)
    }

    # ATR波动调整
    $atrPct = $ATR / $P * 100
    if ($atrPct -gt 5) { $s3 = [Math]::Round($P - $ATR * 4, 2) }
    elseif ($atrPct -lt 2) { $s3 = [Math]::Round($P - $ATR * 2, 2) }

    # Volume Profile 成交密集区增强 (2026-05-26 P2)
    # VP不替代MA，而是交叉验证：HVN节点可提升MA-based支撑/压力的可靠性
    $vpUsed = $false
    if ($VP -and $VP.POC) {
        $vpUsed = $true
        # HVN支撑增强: 最近下方HVN如果在MA-based S1上方且距离<10% → 提升S1
        if ($VP.HVN_Below -and $VP.HVN_Below.Count -gt 0) {
            $nearestHVNLow = [double]$VP.HVN_Below[0][0]
            if ($nearestHVNLow -gt $s1 -and $nearestHVNLow -lt $P -and ($P - $nearestHVNLow) / $P -lt 0.10) {
                $s1 = [Math]::Round($nearestHVNLow, 2)
            }
        }
        # HVN压力增强: 最近上方HVN如果在MA-based R1下方且距离<10% → 调整R1
        if ($VP.HVN_Above -and $VP.HVN_Above.Count -gt 0) {
            $nearestHVNHigh = [double]$VP.HVN_Above[0][0]
            if ($nearestHVNHigh -lt $r1 -and $nearestHVNHigh -gt $P -and ($nearestHVNHigh - $P) / $P -lt 0.10) {
                $r1 = [Math]::Round($nearestHVNHigh, 2)
            }
        }
        # POC支撑: POC在价下方且在S2上方 → 作为S2备选
        $vpPOC = [double]$VP.POC
        if ($vpPOC -lt $P -and $vpPOC -gt $s2 -and ($P - $vpPOC) / $P -lt 0.20) {
            $s2 = [Math]::Round($vpPOC, 2)
        }
    }

    # 合理性修正
    if ($r1 -le $P) { $r1 = [Math]::Round($P * 1.025, 2) }
    if ($r2 -le $r1) { $r2 = [Math]::Round($r1 * 1.03, 2) }
    if ($r3 -le $r2) { $r3 = [Math]::Round($r2 * 1.025, 2) }
    if ($s1 -ge $P) { $s1 = [Math]::Round($P * 0.975, 2) }
    if ($s2 -ge $s1) { $s2 = [Math]::Round($s1 * 0.97, 2) }
    if ($s3 -ge $s2) { $s3 = [Math]::Round($s2 * 0.97, 2) }

    # ========== 仓位 ==========
    $pct = $CompScore
    if ($pct -ge 80) { $maxPos = 30; $posLabel = "可重点配置" }
    elseif ($pct -ge 65) { $maxPos = 20; $posLabel = "正常配置" }
    elseif ($pct -ge 45) { $maxPos = 10; $posLabel = "轻仓试探" }
    elseif ($pct -ge 30) { $maxPos = 5; $posLabel = "极轻仓或观望" }
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
        VP=$VP; VPUsed=$vpUsed
    }
}

# ============================================================
# Phase 3.6: v3.0 新增 — 极端事件/不做清单/信号冲突裁决
# ============================================================

function Test-ExtremeEvent {
    param($D)
    $events = @()
    $price = $D.Price; $prevClose = $D.Quote.PrevClose
    $changePct = $D.Quote.ChangePct; $vol = $D.Quote.Volume

    # 一字跌停检查
    if ($changePct -le -9.9 -and $vol -gt 0) {
        $events += @{ Type="一字跌停"; Severity="CRITICAL"; Action="挂跌停价卖出，无需等待反弹"; Rule="§4.5.1" }
    }
    # 连续跌停(简化：检查近2日)
    if ($D.KLines -and $D.KLines.Count -ge 2) {
        $yestChg = ($D.KLines[-2].Close - $D.KLines[-3].Close) / $D.KLines[-3].Close * 100
        if ($yestChg -le -9.9 -and $changePct -le -5) {
            $events += @{ Type="连续跌停(≥2日)"; Severity="CRITICAL"; Action="继续挂跌停价，不计成本"; Rule="§4.5.1" }
        }
    }
    # ST风险 (检查名称中是否含ST)
    if ($D.Name -match '\*?ST') {
        $events += @{ Type="ST风险警示"; Severity="CRITICAL"; Action="立即清仓，不计成本。ST股票禁止重新进入任何观察池"; Rule="§4.5.2" }
    }
    # 财务退市预警
    if ($D.Financial -and $D.Financial.Count -gt 0) {
        $rev = [double]$D.Financial[0].TOTAL_OPERATE_INCOME
        $np = [double]$D.Financial[0].PARENT_NETPROFIT
        if ($rev -lt 1e8 -and $np -lt 0) {
            $events += @{ Type="财务退市预警(营收<1亿+净利<0)"; Severity="CRITICAL"; Action="无条件清仓，即使综合评分仍高"; Rule="§4.5.2" }
        }
    }
    # 重大利空(跌幅>7%且放量)
    if ($changePct -le -7) {
        $avgVol = if ($D.VolMA20.Count -gt 0) { $D.VolMA20[-1] } else { 0 }
        if ($avgVol -gt 0 -and $vol -gt $avgVol * 1.5) {
            $events += @{ Type="放量暴跌(>$changePct%)"; Severity="HIGH"; Action="减仓50%，次日若续跌→清仓"; Rule="§4.5.3" }
        }
    }

    $hasCritical = ($events | Where-Object { $_.Severity -eq "CRITICAL" }).Count -gt 0
    return @{ HasCritical=$hasCritical; Events=$events }
}

function Get-WyckoffPhase {
    param($D)
    if (-not $D.KLines -or $D.KLines.Count -lt 60) { return "数据不足" }

    $P = $D.Price; $high20 = ($D.KLines[-20..-1] | Measure-Object High -Maximum).Maximum
    $low20 = ($D.KLines[-20..-1] | Measure-Object Low -Minimum).Minimum
    $low250 = if ($D.KLines.Count -ge 120) { ($D.KLines[-120..-1] | Measure-Object Low -Minimum).Minimum } else { $low20 }
    $range = $high20 - $low20
    $avgVol20 = if ($D.VolMA20.Count -gt 0) { $D.VolMA20[-1] } else { 0 }
    $avgVol60 = if ($D.VolMA20.Count -ge 3) { ($D.VolMA20[-3..-1] | Measure-Object -Average).Average } else { $avgVol20 }
    $atrVal = if ($D.ATR -and $D.ATR.Count -gt 0 -and $D.ATR[-1] -ne $null) { [double]$D.ATR[-1] } else { $P * 0.025 }

    # Quantify each phase
    $distFromLow250 = ($P - $low250) / $low250 * 100

    # Accumulation: ① distance < 15% from low ② range < ATR×1.5 ③ avgVol20 > avgVol60×1.2
    $accCond1 = $distFromLow250 -lt 15
    $accCond2 = $range -lt ($atrVal * 1.5)
    $accCond3 = ($avgVol60 -gt 0) -and ($avgVol20 -gt $avgVol60 * 1.2)
    $accScore = [int]$accCond1 + [int]$accCond2 + [int]$accCond3

    # Markup: ① price > high20 ② MA20 > MA60 ③ ADX>25 and +DI > -DI
    $ma20v = if ($D.MA20.Count -gt 0) { $D.MA20[-1] } else { $P }
    $ma60v = if ($D.MA60.Count -gt 0) { $D.MA60[-1] } else { $P }
    $adxV = if ($D.ADX -and $D.ADX.ADX.Count -gt 0 -and $D.ADX.ADX[-1] -ne $null) { [double]$D.ADX.ADX[-1] } else { 0 }
    $pdi = if ($D.ADX -and $D.ADX.PlusDI.Count -gt 0) { [double]$D.ADX.PlusDI[-1] } else { 0 }
    $mdi = if ($D.ADX -and $D.ADX.MinusDI.Count -gt 0) { [double]$D.ADX.MinusDI[-1] } else { 0 }
    $muCond1 = $P -gt $high20
    $muCond2 = $ma20v -gt $ma60v
    $muCond3 = ($adxV -gt 25) -and ($pdi -gt $mdi)
    $muScore = [int]$muCond1 + [int]$muCond2 + [int]$muCond3

    # Distribution: ① >80% above 250d low + flat ② Upthrust pattern ③ weekly RSI>75
    $distCond1 = $distFromLow250 -gt 80
    $distCond3 = if ($D.RSI9.Count -gt 0 -and $D.RSI9[-1] -ne $null) { [double]$D.RSI9[-1] -gt 75 } else { $false }
    $distScore = [int]$distCond1 + [int]$distCond3

    # Decline: ① price < low20 ② MA20 < MA60 ③ ADX>25 and -DI > +DI
    $decCond1 = $P -lt $low20
    $decCond2 = $ma20v -lt $ma60v
    $decCond3 = ($adxV -gt 25) -and ($mdi -gt $pdi)
    $decScore = [int]$decCond1 + [int]$decCond2 + [int]$decCond3

    # Determine phase (best match)
    if ($muScore -ge 2) { return "拉升区 (Markup)" }
    elseif ($decScore -ge 2) { return "下跌区 (Decline)" }
    elseif ($accScore -ge 2) { return "吸筹区 (Accumulation)" }
    elseif ($distScore -ge 2) { return "派发区 (Distribution)" }
    elseif ($muScore -ge 1) { return "疑似拉升区" }
    elseif ($accScore -ge 1) { return "疑似吸筹区" }
    else { return "过渡/不明" }
}

function Get-ConflictArbitration {
    param($TechS, $FundS, $SectS, $CapS, $Pred, $Confidence)

    $conflicts = @()
    $verdict = "按正常权重执行"

    # 1. 基本面恶化一票否决
    if ($FundS -le 40 -and $TechS -ge 60) {
        $conflicts += "基本面偏空($FundS) vs 技术面偏多($TechS)：基本面恶化具有一票否决权"
        $verdict = "维持观望，不因技术面偏多而开仓"
    }
    # 2. 宏观逆风一票否决
    # (Macro score embedded, skipped)
    # 3. 技术+资金+板块共振 vs 基本面偏空
    if ($TechS -ge 60 -and $CapS -ge 55 -and $SectS -ge 55 -and $FundS -le 45) {
        $conflicts += "三面共振(技术+资金+板块) vs 基本面偏空($FundS)：技术面服从基本面"
        $verdict = "维持观望，仓位≤10%试探"
    }
    # 4. 技术偏多 + 其他中性
    if ($TechS -ge 60 -and $FundS -lt 50 -and $SectS -lt 50 -and $CapS -lt 50) {
        $conflicts += "技术面偏多($TechS)但其他维度中性：小仓位试探"
        $verdict = "仓位≤10%，待更多维度确认后加仓"
    }
    # 5. 三周期冲突
    if ($Pred.Short -eq "看多" -and $Pred.Mid -eq "趋势看空") {
        $conflicts += "短期看多 vs 中期看空：短服从长，不追仓"
        if ($verdict -eq "按正常权重执行") { $verdict = "中线持仓但收紧止损，不追仓" }
    }
    # 6. 置信度过滤
    if ($Confidence -match "低" -and $TechS -ge 55) {
        $conflicts += "置信度<50%：降一级操作强度"
        $verdict = "轻仓/观望"
    }

    return @{ Conflicts=$conflicts; Verdict=$verdict; HasConflict=($conflicts.Count -gt 0) }
}

function Get-DontDoCheck {
    param($D, $Pred, $TechS, $CompScore)

    $violations = @()
    $warnings = @()

    # 1. 追涨
    $rsiVal = if ($D.RSI9.Count -gt 0 -and $D.RSI9[-1] -ne $null) { [double]$D.RSI9[-1] } else { 50 }
    $distToS1 = ($D.Price - $Pred.Support) / $D.Price * 100
    if ($rsiVal -gt 80 -and $distToS1 -gt 5) {
        $violations += "追涨买入：RSI(9)=$rsiVal>80 且距S1>5%，禁止开新仓"
    }
    # 2. 亏损加仓 (not trackable in stateless script)
    # 3. 财报前3日 (no earnings calendar data)
    # 4. RSI>80加仓
    if ($rsiVal -gt 80 -and $CompScore -ge 65) {
        $violations += "RSI(9)=$rsiVal>80 加仓：超买区加仓必然高位接盘"
    }
    # 5. 单一板块集中 (not applicable at individual stock level)
    # 6. 单一信号交易
    if ($TechS -ge 55 -and $CompScore -lt 45) {
        $warnings += "警惕单一信号交易：技术面$TechS但综合评分$CompScore<45，至少两个维度确认"
    }
    # 7. 震荡市趋势策略
    $adxV = if ($D.ADX -and $D.ADX.ADX.Count -gt 0 -and $D.ADX.ADX[-1] -ne $null) { [double]$D.ADX.ADX[-1] } else { 25 }
    if ($adxV -lt 20 -and $Pred.Short -in @("看多","偏多")) {
        $warnings += "ADX=$adxV<20震荡市：禁止趋势策略开仓，仅可区间操作"
    }

    return @{ Violations=$violations; Warnings=$warnings; HasIssues=($violations.Count -gt 0 -or $warnings.Count -gt 0) }
}

# ============================================================
# Phase 4: HTML 报告生成
# ============================================================

# ====== 样式锁定 ======
# 本CSS样式已锁定，未经用户（铁律量化）明确书面许可，
# 不得修改任何颜色、布局、间距、字体等视觉属性。
# 锁定日期：2026-05-22 | 锁定版本：卡片式v1.0（优化版样式）
# ======================
$CSS = @'
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:"Microsoft YaHei","微软雅黑",sans-serif;color:#333;background:#f0f2f5;padding:20px}
.report-page{max-width:210mm;margin:0 auto;background:#fff;padding:15mm 18mm;box-shadow:0 2px 10px rgba(0,0,0,0.1)}
.page-break{page-break-before:always}
.header{background:linear-gradient(135deg,#1a1a2e,#16213e);color:#fff;padding:28px 30px;border-radius:10px;margin-bottom:20px;position:relative}
.header h1{font-size:24px;margin-bottom:8px}
.header .subtitle{font-size:17px;line-height:1.7}
.header .badge{position:absolute;top:20px;right:25px;padding:8px 18px;border-radius:20px;font-size:16px;font-weight:bold;text-align:center}
.badge-red{background:#e74c3c;color:#fff}
.badge-orange{background:#e67e22;color:#fff}
.badge-yellow{background:#f39c12;color:#fff}
.badge-green{background:#27ae60;color:#fff}
.badge-blue{background:#2980b9;color:#fff}
.score-card{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:20px}
.score-item{background:#f8f9fa;border-radius:8px;padding:12px 14px;border-left:4px solid #3498db}
.score-item .dim-name{font-size:13px;color:#666}
.score-item .dim-score{font-size:22px;font-weight:bold;margin:4px 0}
.score-item .dim-bar{height:5px;background:#e0e0e0;border-radius:3px;overflow:hidden}
.score-item .dim-bar-fill{height:100%;border-radius:3px;transition:width 0.3s}
.section{margin:18px 0}
.section h2{font-size:18px;color:#16213e;border-bottom:2px solid #1a1a2e;padding-bottom:6px;margin-bottom:12px}
.section h3{font-size:15px;color:#333;margin:10px 0 6px}
table{width:100%;border-collapse:collapse;margin:8px 0 14px;font-size:13px}
th{background:#1a1a2e;color:#fff;padding:8px 10px;text-align:center;font-weight:normal}
td{padding:6px 10px;border:1px solid #e0e0e0;text-align:center}
tr:nth-child(even){background:#f8f9fa}
.prediction-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:10px 0 16px}
.pred-item{text-align:center;padding:12px;border-radius:8px;background:#f8f9fa}
.pred-item .period{font-size:12px;color:#888}
.pred-item .direction{font-size:20px;font-weight:bold;margin:4px 0}
.pred-up{color:#e74c3c}.pred-down{color:#27ae60}.pred-neutral{color:#f39c12}
.ladder-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:10px 0}
.ladder-item{padding:10px;border-radius:6px;text-align:center}
.ladder-resist{background:#fff5f5;border:1px solid #fdd}
.ladder-supp{background:#f0fff4;border:1px solid #dfd}
.ladder-stop{background:#fff8f0;border:1px solid #fed}
.ladder-item .level{font-size:11px;color:#999}
.ladder-item .price{font-size:18px;font-weight:bold}
.ladder-item .note{font-size:11px;color:#888}
.op-section{background:#f8f9fa;border-radius:8px;padding:14px;margin:10px 0;border-left:4px solid #2980b9}
.op-section.buy{border-left-color:#27ae60}
.op-section.sell{border-left-color:#e74c3c}
.op-section.stop{border-left-color:#e67e22}
.op-section .op-title{font-size:14px;font-weight:bold;margin-bottom:6px}
.op-section .op-detail{font-size:13px;color:#555;line-height:1.6}
.scenario-table td:first-child{font-weight:bold;text-align:left;width:22%}
.scenario-table td:nth-child(2){text-align:left;font-size:12px}
.scenario-table td:nth-child(3){width:15%;font-weight:bold;text-align:center}
.pos-meter{display:flex;align-items:center;gap:12px;padding:12px 16px;background:#eef2f7;border-radius:8px;margin:8px 0}
.pos-meter .pos-max{font-size:28px;font-weight:bold;color:#2980b9}
.pos-meter .pos-label{font-size:14px;color:#555}
.pos-bar{flex:1;height:12px;background:#ddd;border-radius:6px;overflow:hidden}
.pos-bar-fill{height:100%;background:#2980b9;border-radius:6px}
.health-meter{display:flex;align-items:center;gap:16px;padding:14px;background:#f8f9fa;border-radius:8px;margin:10px 0}
.health-score{font-size:36px;font-weight:bold;min-width:70px;text-align:center}
.health-label{font-size:16px;padding:4px 12px;border-radius:4px}
.disclaimer{margin-top:24px;padding-top:12px;border-top:1px solid #ddd;font-size:11px;color:#999;line-height:1.8}
.key-levels{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:10px 0}
.level-item{padding:12px;text-align:center;border-radius:8px}
.level-item .lbl{font-size:12px;color:#888}
.level-item .val{font-size:20px;font-weight:bold}
.level-resist{background:#fde8e8;border:1px solid #f5c6c6}.level-resist .val{color:#e74c3c}
.level-supp{background:#e8f5e9;border:1px solid #c6e6c8}.level-supp .val{color:#27ae60}
.level-stop{background:#fff3e0;border:1px solid #ffe0b2}.level-stop .val{color:#e67e22}
.fund-flow-table td:first-child{text-align:left}
.research-list{margin:8px 0}
.research-item{padding:6px 0;border-bottom:1px dashed #e0e0e0;font-size:13px}
.research-item .org{color:#2980b9;font-weight:bold}
.research-item .rating-buy{color:#e74c3c}.research-item .rating-hold{color:#e67e22}
.vp-table{margin:6px 0} .vp-table th{background:#1a1a2e;color:#fff;padding:6px 10px;text-align:center;font-weight:normal;font-size:12px} .vp-table td{padding:5px 10px;border:1px solid #e0e0e0;text-align:center;font-size:12px}
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
    if ($score -ge 80) { return "badge-blue" }
    elseif ($score -ge 65) { return "badge-green" }
    elseif ($score -ge 45) { return "badge-yellow" }
    elseif ($score -ge 30) { return "badge-orange" }
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
        @{N="技术面";S=$Scores.Technical;W="20%"},
        @{N="基本面";S=$Scores.Fundamental;W="20%"},
        @{N="消息面";S=$Scores.Sentiment;W="15%"},
        @{N="板块行业";S=$Scores.Sector;W="18%"},
        @{N="资金面";S=$Scores.Capital;W="15%"},
        @{N="宏观大盘";S=$Scores.Macro;W="12%"}
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
        @{N="技术面";S=$Scores.Technical;W="20%";D="ADX趋势 + RSI(9)动量 + 布林带波动 + OBV量能"},
        @{N="基本面";S=$Scores.Fundamental;W="20%";D="ROE(杜邦) + 扣非增速 + 商誉/净资产 + PE百分位 + PEG"},
        @{N="消息面";S=$Scores.Sentiment;W="15%";D="研报覆盖数 + 分析师评级 + 催化剂市值调整 + 预期差"},
        @{N="板块行业";S=$Scores.Sector;W="18%";D="板块相位(量化) + 相对强度排名 + 资金流向 + 共振度"},
        @{N="资金面";S=$Scores.Capital;W="15%";D="主力资金 + 北向持股 + 融资融券"},
        @{N="宏观大盘";S=$Scores.Macro;W="12%";D="市场广度 + 强势板块占比 + 资金情绪"}
    )
    $rows = ""
    foreach ($d in $dims) {
        $c = New-ScoreColor $d.S; $weighted = [Math]::Round($d.S * [int]($d.W -replace '%','') / 100, 1)
        $rows += "<tr><td>$($d.N)</td><td style='color:$c;font-weight:bold;'>$($d.S)</td><td>$($d.W)</td><td>$weighted</td><td style='text-align:left;font-size:12px;color:#666;'>$($d.D)</td></tr>"
    }
    $compositeW = $Scores.Technical*0.20 + $Scores.Fundamental*0.20 + $Scores.Sentiment*0.15 + $Scores.Sector*0.18 + $Scores.Capital*0.15 + $Scores.Macro*0.12
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

        # ADX display
        $adxTxt = "N/A"; $adxVal = $null
        if ($D.ADX -and $D.ADX.ADX.Count -gt 0 -and $D.ADX.ADX[-1] -ne $null) {
            $adxVal = [Math]::Round([double]$D.ADX.ADX[-1], 1)
            $pdi = [Math]::Round([double]$D.ADX.PlusDI[-1], 1)
            $mdi = [Math]::Round([double]$D.ADX.MinusDI[-1], 1)
            $adxTxt = if ($adxVal -gt 25 -and $pdi -gt $mdi) { "趋势行情(ADX=$adxVal, +DI>$pdi > -DI$mdi)，趋势向上强劲" }
                      elseif ($adxVal -gt 25) { "趋势行情(ADX=$adxVal, -DI>$mdi > +DI$pdi)，趋势向下" }
                      elseif ($adxVal -gt 20) { "趋势形成中(ADX=$adxVal)" }
                      else { "震荡市(ADX=$adxVal<20)，适合区间操作" }
        }

        # MACD display
        $macdTxt = ""
        if ($D.MACD) {
            $macdTxt = if ($D.MACD.DIF[-1] -gt $D.MACD.DEA[-1] -and $D.MACD.DIF[-1] -gt 0) { "零轴上金叉，多头主导" }
                       elseif ($D.MACD.DIF[-1] -gt $D.MACD.DEA[-1]) { "零轴下金叉，弱势反弹" }
                       else { "死叉状态，空头主导" }
        }

        # RSI(9) display
        $rsiTxt = ""
        if ($D.RSI9.Count -gt 0 -and $D.RSI9[-1] -ne $null) {
            $r9 = [Math]::Round([double]$D.RSI9[-1], 1)
            $rsiTxt = if ($r9 -ge 70) { "超买区域(RSI9=$r9)，注意回调风险" }
                      elseif ($r9 -ge 50) { "中性偏强(RSI9=$r9)，趋势健康" }
                      elseif ($r9 -ge 30) { "中性偏弱(RSI9=$r9)" }
                      else { "超卖区域(RSI9=$r9)，可能存在反弹机会" }
        }

        # OBV display
        $obvTxt = "N/A"
        if ($D.OBV -and $D.OBV.Count -ge 10) {
            $obvTrend = if ($D.OBV[-6] -ne 0) { [Math]::Round(($D.OBV[-1] - $D.OBV[-6]) / [Math]::Abs($D.OBV[-6]) * 100, 1) } else { 0 }
            $priceTrend = if ($D.KLines[-6].Close -ne 0) { [Math]::Round(($D.KLines[-1].Close - $D.KLines[-6].Close) / $D.KLines[-6].Close * 100, 1) } else { 0 }
            if ($obvTrend -gt 2 -and $priceTrend -gt 0) { $obvTxt = "OBV与价格同向上升(${obvTrend}%)，趋势确认" }
            elseif ($obvTrend -gt 2 -and $priceTrend -lt 0) { $obvTxt = "OBV上升但价格下跌(${priceTrend}%)，底背离看多信号" }
            elseif ($obvTrend -lt -2 -and $priceTrend -lt 0) { $obvTxt = "OBV与价格同向下跌(${obvTrend}%)，空头确认" }
            elseif ($obvTrend -lt -2 -and $priceTrend -gt 0) { $obvTxt = "OBV下降但价格上涨(${priceTrend}%)，顶背离看空信号" }
            else { $obvTxt = "OBV变化不大(${obvTrend}%)，量能中性" }
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
            $volTxt = if ($chg -ge 2 -and $vr -ge 1.5) { "放量上涨(量比$([Math]::Round($vr,1)))，增量资金入场" }
                      elseif ($chg -ge 0 -and $vr -le 1.1) { "缩量上涨(量比$([Math]::Round($vr,1)))，上涨动力不足" }
                      elseif ($chg -lt -2 -and $vr -ge 1.5) { "放量下跌，恐慌抛售或主力出货" }
                      elseif ($chg -lt 0 -and $vr -le 0.8) { "缩量下跌，抛压减弱" }
                      else { "量能正常" }
        }

        $lines += @"
<table>
<tr><th>维度</th><th>指标</th><th>数值</th><th>判断</th></tr>
<tr><td>趋势</td><td>ADX(14)</td><td>$(if($adxVal){ "$adxVal / +DI $([Math]::Round([double]$D.ADX.PlusDI[-1],1)) / -DI $([Math]::Round([double]$D.ADX.MinusDI[-1],1))" }else{"N/A"})</td><td>$adxTxt</td></tr>
<tr><td>趋势(辅助)</td><td>MACD</td><td>DIF $([Math]::Round($D.MACD.DIF[-1],3)) DEA $([Math]::Round($D.MACD.DEA[-1],3))</td><td>$macdTxt</td></tr>
<tr><td>动量</td><td>RSI(9)</td><td>$(if($D.RSI9.Count -gt 0 -and $D.RSI9[-1] -ne $null){[Math]::Round([double]$D.RSI9[-1],1)}else{"N/A"})</td><td>$rsiTxt</td></tr>
<tr><td>波动</td><td>布林带</td><td>上$bu 中$([Math]::Round($bm,2)) 下$([Math]::Round($bd,2))</td><td>$bollTxt</td></tr>
<tr><td>量能</td><td>OBV</td><td>$(if($D.OBV -and $D.OBV.Count -gt 0){"趋势 " + $obvTxt}else{"N/A"})</td><td>$obvTxt</td></tr>
<tr><td>量能(辅助)</td><td>量价</td><td>$v 手 / 5日均量 $([Math]::Round($v5,0)) 手</td><td>$volTxt</td></tr>
<tr><td>均线</td><td>MA5/MA10/MA20</td><td>$([Math]::Round($m5,2)) / $([Math]::Round($m10,2)) / $([Math]::Round($m20,2))</td><td>$maTrend</td></tr>
</table>
"@
    }

    # Wyckoff phase quantification
    $wyckoffPhase = Get-WyckoffPhase -D $D
    $wyckoffHtml = @"
<div style="margin-top:10px;padding:10px 14px;background:#f0f4ff;border-radius:6px;border-left:4px solid #2980b9;font-size:13px;">
    <strong>Wyckoff周期阶段：</strong>$wyckoffPhase
    <span style="color:#888;font-size:11px;margin-left:8px;">[v3.0量化判定：每阶段3个条件，≥2项满足]</span>
</div>
"@

    return @"
<div class="section">
    <h2>技术面分析 [2]→[5] ✅已实测 | v3.0四维独立确认(ADX/RSI9/BB/OBV)</h2>
    $lines
    $wyckoffHtml
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
    # 扣非净利润 (v3.0)
    $deductedStr = "N/A"; $deductedEval = "N/A"
    if ($fin[0].PSObject.Properties.Name -contains 'DEDUCTED_PROFIT' -and $fin.Count -ge 2) {
        $dp0 = [double]$fin[0].DEDUCTED_PROFIT
        if ($fin[1].PSObject.Properties.Name -contains 'DEDUCTED_PROFIT') {
            $dp1 = [double]$fin[1].DEDUCTED_PROFIT
            if ($dp1 -ne 0) {
                $dg = ($dp0 - $dp1) / [Math]::Abs($dp1) * 100
                $deductedStr = "$([Math]::Round($dg,1))%"
                $deductedEval = if($dg -ge 15){"优秀(≥15%)"}elseif($dg -ge 0){"正增长"}else{"负增长⚠️"}
            }
        }
    }
    # 商誉/净资产 (v3.0)
    $goodwillStr = "N/A"; $goodwillEval = "N/A"
    if ($fin[0].PSObject.Properties.Name -contains 'GOODWILL') {
        $gw = [double]$fin[0].GOODWILL
        $eq = 0
        if ($fin[0].PSObject.Properties.Name -contains 'TOTAL_EQUITY') { $eq = [double]$fin[0].TOTAL_EQUITY }
        elseif ($fin[0].PSObject.Properties.Name -contains 'PARENT_EQUITY') { $eq = [double]$fin[0].PARENT_EQUITY }
        if ($eq -gt 0) {
            $gwRatio = $gw / $eq * 100
            $goodwillStr = "$([Math]::Round($gwRatio,1))%"
            $goodwillEval = if($gwRatio -gt 50){"🔴 红牌(>50%)"}elseif($gwRatio -gt 30){"🟡 黄牌(>30%)"}else{"安全(<30%)"}
        }
    }
    # PEG (v3.0)
    $pegStr = "N/A"; $pegEval = "N/A"
    if ($D.PEPercentile -and $D.PEPercentile.CurrentPE -gt 0) {
        $consGrowth = $null
        if ($D.Research -and @($D.Research).Count -gt 0) {
            $epsVals = @($D.Research | Where-Object { $_.ThisYearEPS -gt 0 } | ForEach-Object { $_.ThisYearEPS })
            if ($epsVals.Count -gt 0) { $consGrowth = ($epsVals | Measure-Object -Average).Average }
        }
        if ($consGrowth -and $consGrowth -gt 0) {
            $peg = $D.PEPercentile.CurrentPE / $consGrowth
            $pegStr = [Math]::Round($peg, 2)
            $pegEval = if($peg -lt 0.8){"低估(<0.8)"}elseif($peg -lt 1.2){"合理"}elseif($peg -lt 1.8){"偏高"}else{"高估"}
        }
    }
    $peStr = if ($D.PEPercentile) { "$($D.PEPercentile.CurrentPE) / $($D.PEPercentile.MinPE)-$($D.PEPercentile.MaxPE) / 百分位$($D.PEPercentile.Percentile)% ($($D.PEPercentile.Valuation))" } else { "N/A" }
    return @"
<div class="section">
    <h2>基本面分析 [3]→[5] ✅已实测 | v3.0增强(扣非+商誉+杜邦+PEG)</h2>
    <table>
    <tr><th>指标</th><th>最新值</th><th>评估</th></tr>
    <tr><td>ROE</td><td>$([Math]::Round($roe,2))%</td><td>$(if($roe-ge15){'优秀'}elseif($roe-ge10){'良好'}elseif($roe-ge5){'一般'}else{'较差'})</td></tr>
    <tr><td>扣非净利润增速</td><td>$deductedStr</td><td>$deductedEval</td></tr>
    <tr><td>毛利率</td><td>$([Math]::Round($gm,1))%$(if($cost -le 0 -or $gm -ge 99){' <span style="color:#e67e22;font-size:11px;">⚠数据存疑</span>'})</td><td>$(if($gm-ge50){'优秀'}elseif($gm-ge30){'良好'}elseif($gm-ge15){'一般'}else{'较低'})</td></tr>
    <tr><td>营收增速</td><td>$revGrowthStr</td><td>同比</td></tr>
    <tr><td>净利润</td><td>$([Math]::Round($np/100000000,2))亿</td><td>归母净利润</td></tr>
    <tr><td>EPS</td><td>$eps 元</td><td>基本每股收益</td></tr>
    <tr><td>资产负债率</td><td>$([Math]::Round($debt,1))%$(if($debt -eq 0){' <span style="color:#e67e22;font-size:11px;">⚠数据存疑</span>'})</td><td>$(if($debt-lt30){'低杠杆'}elseif($debt-lt50){'合理'}elseif($debt-lt65){'偏高'}else{'高杠杆'})</td></tr>
    <tr><td>商誉/净资产</td><td>$goodwillStr</td><td>$goodwillEval</td></tr>
    <tr><td>PE估值</td><td>$peStr</td><td>$(if($D.PEPercentile){$D.PEPercentile.Valuation}else{'N/A'})</td></tr>
    <tr><td>PEG</td><td>$pegStr</td><td>$pegEval</td></tr>
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
    if ($r -and @($r).Count -gt 0) {
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
    if ($mg -and @($mg).Count -gt 0) {
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
    if ($ff -and @($ff).Count -gt 0) {
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
    param($Health, $D, $Pred, $Ops)
    $c = New-ScoreColor $Health.Score
    $pullbackTxt = if ($Health.Pullback) { "当前从20日高点回调 $([Math]::Round($Health.Pullback,1))%" } else { "" }

    # 构建具体可执行的操作建议（基于实际数据，非模板文案）
    $adviceItems = @()

    # 距止损位距离百分比 — 统一使用Ops.S3为唯一止损源
    $stopDistPct = if ($Ops.S3 -and $D.Price -gt 0) { [Math]::Round(($D.Price - $Ops.S3) / $D.Price * 100, 1) } else { $null }

    if ($Health.Score -ge 80) {
        $adviceItems += "<li><strong>[持有]</strong> 趋势健康，正常持有"
        if ($D.RSI14) {
            $r = [Math]::Round($D.RSI14[-1], 1)
            if ($r -gt 75) { $adviceItems[-1] += " — RSI($r)偏高(<span style='color:#e74c3c;'>超买区&gt;75</span>)，若RSI回落至70以下则减仓1/4锁定利润" }
        }
        $adviceItems[-1] += "</li>"
    } else {
        # 回调幅度预警（含具体价位和动作）
        if ($Health.Pullback -and $Health.Pullback -ge 8) {
            $pct = [Math]::Round($Health.Pullback, 1)
            if ($Health.Pullback -ge 15) {
                $adviceItems += "<li><strong>深度回调${pct}%</strong>，S2(¥$($Pred.Support))为关键支撑 — 若跌破S2则触发清仓信号；可在S2附近等待放量企稳后分批建仓</li>"
            } elseif ($Health.Pullback -ge 10) {
                $adviceItems += "<li><strong>回调${pct}%</strong>，接近预警线 — 明日若续跌超2%则减仓1/3，反弹则继续持有</li>"
            } else {
                $adviceItems += "<li><strong>回调${pct}%</strong>，注意观察 — 关注S1(¥$($Pred.Support))能否企稳，放量跌破则减仓1/4</li>"
            }
        }
        # RSI预警（含具体动作）
        if ($D.RSI14) {
            $r = [Math]::Round($D.RSI14[-1], 1)
            if ($r -gt 70) {
                $adviceItems += "<li><strong>RSI($r)超买区(&gt;70)</strong> — 注意回调风险，若RSI拐头向下则减仓1/4，等待回落至50附近再补回</li>"
            } elseif ($r -lt 50 -and $r -ge 40) {
                $adviceItems += "<li><strong>RSI($r)跌破强弱分界线50</strong> — 趋势转弱，若明日无法站回50则确认短线转弱，减仓1/3</li>"
            } elseif ($r -lt 40) {
                $adviceItems += "<li><strong>RSI($r)进入弱势区(&lt;40)</strong> — 短线回避，等待RSI回升至40以上再考虑介入；若继续跌破30则关注超跌反弹机会</li>"
            }
        }
        # MACD预警（含DIF/DEA数值）
        if ($D.MACD -and $D.MACD.DIF[-1] -lt $D.MACD.DEA[-1]) {
            $dif = [Math]::Round($D.MACD.DIF[-1], 3)
            $dea = [Math]::Round($D.MACD.DEA[-1], 3)
            $adviceItems += "<li><strong>MACD死叉</strong>(DIF=$dif &lt; DEA=$dea) — 短线动能转负，预计调整持续2-4个交易日，待DIF拐头向上或出现底背离再参与</li>"
        }
        # 止损价位（含距止损距离）
        if ($Ops.S3) {
            if ($Health.Score -ge 60) {
                $adviceItems += "<li><strong>止损设于 ¥$($Ops.S3)</strong> — 当前距止损$($stopDistPct)%，未触发前继续持有</li>"
            } elseif ($Health.Score -ge 40) {
                $adviceItems += "<li><strong>跌破¥$($Ops.S3)须减仓一半</strong> — 当前距止损$($stopDistPct)%，跌破后半仓观望，等企稳信号出现再补回</li>"
            } else {
                $adviceItems += "<li><strong>跌破¥$($Ops.S3)(S3)→清仓</strong> — 当前距止损$($stopDistPct)%，严格执行止损纪律，不因中长线看好而扛单</li>"
            }
        }
    }
    if ($adviceItems.Count -eq 0) { $adviceItems += "<li>无特殊预警信号，正常持有</li>" }
    $adviceHtml = $adviceItems -join ""

    # ====== 趋势健康度与中/长期预判背离提醒 ======
    $divergenceNote = ""
    if ($Health.Score -lt 40 -and ($Pred.Mid -eq "趋势看多" -or $Pred.Long -eq "长期看好")) {
        $divergenceNote = @"
<div style="margin-top:10px;padding:10px 14px;background:#fff3e0;border-radius:6px;border-left:4px solid #e67e22;font-size:13px;color:#555;line-height:1.7;">
    <strong style="color:#e67e22;">⚠ 短线与中长线背离：</strong>趋势健康度（$($Health.Score)分）反映的是<strong>短期技术面</strong>（20日回撤、均线、MACD、RSI），当前确实偏弱。
    但中/长期基本面与板块逻辑未变（$($Pred.Mid)/$($Pred.Long)），两者并不矛盾。<br>
    <strong>应对策略：</strong>中长线持仓者可等待企稳信号（MACD金叉+RSI回升至50以上）再考虑加仓，不建议在当前技术面恶化时盲目清仓。
    短线交易者应严格执行止损纪律。
</div>
"@
    } elseif ($Health.Score -lt 60 -and ($Pred.Mid -eq "趋势看空" -or $Pred.Long -eq "长期看空")) {
        $divergenceNote = @"
<div style="margin-top:10px;padding:10px 14px;background:#fde8e8;border-radius:6px;border-left:4px solid #e74c3c;font-size:13px;color:#555;line-height:1.7;">
    <strong style="color:#e74c3c;">⚠ 多周期共振偏弱：</strong>短期技术面趋势健康度$($Health.Score)分，中/长期展望也偏空（$($Pred.Mid)/$($Pred.Long)）。
    多个周期指向一致，建议控制仓位、谨慎对待。
</div>
"@
    }

    return @"
<div class="section">
    <h2>趋势健康度评估 <span style="font-size:13px;color:#999;font-weight:normal;">（衡量趋势可持续性，非综合评分，详见白皮书§3.2）</span></h2>
    <div class="health-meter">
        <div class="health-score" style="color:$c">$($Health.Score)</div>
        <div><span class="health-label" style="background:$c;color:#fff;">$($Health.Label)</span></div>
        <div style="font-size:13px;color:#666;flex:1;">$pullbackTxt</div>
    </div>
    <div style="font-size:13px;color:#555;background:#fff8f0;padding:10px 14px;border-radius:6px;border-left:4px solid $c;">
        <strong>具体执行建议：</strong>
        <ul style="margin:6px 0 0 0;padding-left:18px;line-height:1.8;">
            $adviceHtml
        </ul>
    </div>
    $divergenceNote
</div>
"@
}

function New-KeyLevelsSection {
    param($Pred, $Ops)
    return @"
<div class="section">
    <h2>关键价位</h2>
    <div class="key-levels">
        <div class="level-item level-resist"><div class="lbl">上方阻力</div><div class="val">¥$($Pred.Resistance)</div></div>
        <div class="level-item level-supp"><div class="lbl">下方支撑</div><div class="val">¥$($Pred.Support)</div></div>
        <div class="level-item level-stop"><div class="lbl">止损价位</div><div class="val">¥$($Ops.S3)</div></div>
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
    <tr><td>[5]</td><td>本地计算</td><td>MA/MACD/RSI/布林/PE百分位/ADX/OBV/ATR</td><td>✅ 已实测</td></tr>
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

function New-VolumeProfileSection {
    param($Ops, $P)
    if (-not $Ops.VP -or -not $Ops.VP.POC) { return "" }
    $vp = $Ops.VP
    $poc = [double]$vp.POC
    $vah = [double]$vp.VAH
    $val = [double]$vp.VAL
    $delta = [Math]::Round(($P - $poc) / $poc * 100, 1)
    $deltaSign = if ($delta -gt 0) { "+" } else { "" }
    $deltaColor = if ($P -gt $poc) { "color:#e74c3c" } else { "color:#27ae60" }
    $vpUsedNote = if ($Ops.VPUsed) { "(已用于价格梯队增强)" } else { "(仅展示参考)" }

    $sb = [System.Text.StringBuilder]::new()
    [void]$sb.Append("<div class='section'><h2>成交密集区 · Volume Profile <span style='font-size:11px;color:#888'>$vpUsedNote</span></h2>")
    [void]$sb.Append("<p style='font-size:12px;color:#888;margin-bottom:8px;'>基于近60日OHLCV数据，50档价格区间成交量分布。HVN=高成交量节点(>1.5倍均值)，LVN=低成交量节点(<0.5倍均值)。</p>")
    [void]$sb.Append("<table class='vp-table'><tr><th>POC 公允价</th><td style='$deltaColor'>¥$poc</td><td style='font-size:12px;color:#888'>当前价${deltaSign}${delta}%</td></tr>")
    [void]$sb.Append("<tr><th>VAH 价值区上沿</th><td style='color:#e74c3c'>¥$vah</td><td></td></tr>")
    [void]$sb.Append("<tr><th>VAL 价值区下沿</th><td style='color:#27ae60'>¥$val</td><td></td></tr></table>")

    if ($vp.HVN_Above -and $vp.HVN_Above.Count -gt 0) {
        [void]$sb.Append("<p style='margin:8px 0 4px;font-weight:bold;font-size:13px;'>上方HVN（阻力）</p><table class='vp-table'><tr><th>价格</th><th>成交量</th><th>类型</th></tr>")
        foreach ($h in $vp.HVN_Above) {
            $c = [double]$h[0]; $v = [double]$h[1]
            $vStr = if($v -gt 1e8){[Math]::Round($v/1e8,1).ToString()+'亿'}else{[Math]::Round($v/1e4,0).ToString()+'万'}
            [void]$sb.Append("<tr><td style='color:#e74c3c'>¥$c</td><td>$vStr</td><td>阻力</td></tr>")
        }
        [void]$sb.Append("</table>")
    }
    if ($vp.HVN_Below -and $vp.HVN_Below.Count -gt 0) {
        [void]$sb.Append("<p style='margin:8px 0 4px;font-weight:bold;font-size:13px;'>下方HVN（支撑）</p><table class='vp-table'><tr><th>价格</th><th>成交量</th><th>类型</th></tr>")
        foreach ($h in $vp.HVN_Below) {
            $c = [double]$h[0]; $v = [double]$h[1]
            $vStr = if($v -gt 1e8){[Math]::Round($v/1e8,1).ToString()+'亿'}else{[Math]::Round($v/1e4,0).ToString()+'万'}
            [void]$sb.Append("<tr><td style='color:#27ae60'>¥$c</td><td>$vStr</td><td>支撑</td></tr>")
        }
        [void]$sb.Append("</table>")
    }
    if ($vp.LVN_Zones -and $vp.LVN_Zones.Count -gt 0) {
        [void]$sb.Append("<p style='margin:8px 0 4px;font-weight:bold;font-size:13px;'>LVN（快速穿越区）</p><table class='vp-table'><tr><th>价格区间</th><th>相对位置</th><th>特征</th></tr>")
        foreach ($z in $vp.LVN_Zones) {
            $lo = [double]$z[0]; $hi = [double]$z[1]
            $tag = if ($P -gt $hi) { "下方" } elseif ($P -lt $lo) { "上方" } else { "当前" }
            [void]$sb.Append("<tr><td>¥$lo - ¥$hi</td><td>$tag</td><td style='color:#f39c12'>快速穿越区</td></tr>")
        }
        [void]$sb.Append("</table>")
    }
    [void]$sb.Append("<p style='font-size:11px;color:#888;margin-top:6px;'>说明：HVN代表密集成交区，价格到此附近易获支撑/压力。LVN代表成交稀疏区，价格可能快速穿越。</p></div>")
    return $sb.ToString()
}

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

# ============================================================
# v3.0 新增 HTML 模板：极端事件/冲突裁决/不做清单
# ============================================================

function New-ExtremeEventSection {
    param($ExtremeEvents)
    if (-not $ExtremeEvents -or $ExtremeEvents.Events.Count -eq 0) { return "" }
    $rows = ""
    foreach ($e in $ExtremeEvents.Events) {
        $sevColor = if ($e.Severity -eq "CRITICAL") { "#e74c3c" } else { "#e67e22" }
        $rows += "<tr><td style='color:$sevColor;font-weight:bold;'>$($e.Severity)</td><td>$($e.Type)</td><td>$($e.Action)</td><td style='font-size:11px;color:#888;'>$($e.Rule)</td></tr>"
    }
    $titleColor = if ($ExtremeEvents.HasCritical) { "#e74c3c" } else { "#e67e22" }
    return @"
<div class="section">
    <h2 style="color:$titleColor;">⛔ 极端事件预警 | v3.0 §4.5</h2>
    <p style="font-size:12px;color:#e74c3c;margin-bottom:8px;">极端事件触发时，所有正常分析规则失效，以下表规则为准。</p>
    <table>
    <tr><th>严重级别</th><th>事件类型</th><th>操作指令</th><th>规则引用</th></tr>
    $rows
    </table>
</div>
"@
}

function New-ConflictSection {
    param($ConflictResult)
    if (-not $ConflictResult -or -not $ConflictResult.HasConflict) { return "" }
    $conflictRows = ""
    foreach ($c in $ConflictResult.Conflicts) {
        $conflictRows += "<li style='margin-bottom:4px;'>$c</li>"
    }
    return @"
<div class="section">
    <h2>信号冲突裁决 | v3.0 §6.4</h2>
    <div style="padding:10px 14px;background:#fff8f0;border-radius:6px;border-left:4px solid #e67e22;font-size:13px;">
        <strong style="color:#e67e22;">⚠ 存在信号冲突：</strong>
        <ul style="margin:8px 0 0 18px;line-height:1.8;">$conflictRows</ul>
        <p style="margin-top:8px;font-weight:bold;">裁决结果：$($ConflictResult.Verdict)</p>
    </div>
</div>
"@
}

function New-DontDoSection {
    param($DontDoResult)
    if (-not $DontDoResult -or -not $DontDoResult.HasIssues) { return "" }
    $html = "<div class='section'><h2>⛔ 不做清单检查 | v3.0 §6.5</h2>"
    if ($DontDoResult.Violations.Count -gt 0) {
        $html += "<div style='padding:10px 14px;background:#fde8e8;border-radius:6px;border-left:4px solid #e74c3c;font-size:13px;margin-bottom:8px;'>"
        $html += "<strong style='color:#e74c3c;'>绝对禁止项：</strong><ul style='margin:6px 0 0 18px;line-height:1.8;'>"
        foreach ($v in $DontDoResult.Violations) { $html += "<li>$v</li>" }
        $html += "</ul></div>"
    }
    if ($DontDoResult.Warnings.Count -gt 0) {
        $html += "<div style='padding:10px 14px;background:#fff3e0;border-radius:6px;border-left:4px solid #e67e22;font-size:13px;'>"
        $html += "<strong style='color:#e67e22;'>条件性警告：</strong><ul style='margin:6px 0 0 18px;line-height:1.8;'>"
        foreach ($w in $DontDoResult.Warnings) { $html += "<li>$w</li>" }
        $html += "</ul></div>"
    }
    $html += "</div>"
    return $html
}

function New-StockReportHtml {
    param($D, $Scores, $Pred, $Health, $Ops, $GlobalSectors, $GlobalSectorFund, $dateLabel, $ExtremeEvents, $ConflictResult, $DontDoResult)
    $sb = New-Object System.Text.StringBuilder
    [void]$sb.Append('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">')
    [void]$sb.Append("<title>$($D.Name)($($D.Code))分析报告 $dateLabel</title>")
    [void]$sb.Append("<style>$CSS</style></head><body><div class='report-page'>")
    [void]$sb.Append((New-RptHeader -D $D -Scores $Scores -dateLabel $dateLabel))

    # v3.0: Extreme events first (overrides all normal analysis)
    if ($ExtremeEvents -and $ExtremeEvents.Events.Count -gt 0) {
        [void]$sb.Append((New-ExtremeEventSection -ExtremeEvents $ExtremeEvents))
    }
    # v3.0: Don't-do checklist
    if ($DontDoResult -and $DontDoResult.HasIssues) {
        [void]$sb.Append((New-DontDoSection -DontDoResult $DontDoResult))
    }

    [void]$sb.Append((New-ExecutiveSummary -Scores $Scores -Pred $Pred))
    [void]$sb.Append((New-PriceLadder -Ops $Ops -P $D.Price))
    [void]$sb.Append((New-VolumeProfileSection -Ops $Ops -P $D.Price))
    [void]$sb.Append((New-ShortTermAction -Ops $Ops -Pred $Pred -P $D.Price))
    [void]$sb.Append((New-PositionSizingSection -Ops $Ops -Pred $Pred -CompScore $Scores.Composite))

    # v3.0: Conflict arbitration
    if ($ConflictResult -and $ConflictResult.HasConflict) {
        [void]$sb.Append((New-ConflictSection -ConflictResult $ConflictResult))
    }

    [void]$sb.Append((New-SixDimDetail -Scores $Scores))
    [void]$sb.Append("<div class='page-break'></div>")
    [void]$sb.Append((New-TechSection -D $D))
    [void]$sb.Append((New-FundamentalSection -D $D))
    [void]$sb.Append("<div class='page-break'></div>")
    [void]$sb.Append((New-SentimentSection -D $D))
    [void]$sb.Append((New-SectorSection -D $D -GlobalSectors $GlobalSectors -GlobalSectorFund $GlobalSectorFund))
    [void]$sb.Append((New-CapitalSection -D $D))
    [void]$sb.Append((New-TrendHealthSection -Health $Health -D $D -Pred $Pred -Ops $Ops))
    [void]$sb.Append((New-KeyLevelsSection -Pred $Pred -Ops $Ops))
    [void]$sb.Append((New-Disclaimer))
    [void]$sb.Append('</div></body></html>')
    return $sb.ToString()
}

# ============================================================
# Phase 5: PDF转换
# ============================================================
function Convert-HtmlToPdf {
    param([string]$HtmlFile, [string]$PdfFile)
    # 委托给共享函数（从 stock_data_fetcher.psm1 加载，带文件锁检测）
    return ConvertTo-Pdf -HtmlFile $HtmlFile -PdfFile $PdfFile -EdgePath $edgePath
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
    $pdfFile = Join-Path $outDir "${folderName}跟踪日报_${dateStr}.pdf"
    $htmlFile = Join-Path $outDir "${folderName}跟踪日报_${dateStr}.html"

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
    $comp = Get-CompositeScore -TechS $techS -FundS $fundS -SentS $sentS -SectS $sectS -CapS $capS -MacS $macS.Score
    $health = Get-TrendHealth -D $stockData
    $pred = Get-ThreePeriodPrediction -D $stockData -TechS $techS -FundS $fundS -SectS $sectS -CapS $capS
    $scores = @{ Technical=$techS; Fundamental=$fundS; Sentiment=$sentS; Sector=$sectS; Capital=$capS; Macro=$macS.Score; MacroPhase=$macS.Phase; Composite=$comp.Score; Rating=$comp.Rating; RatingShort=$comp.RatingShort }
    Write-Host "  [评分] 技术$techS 基本面$fundS 消息$sentS 板块$sectS 资金$capS 宏观$($macS.Score)($($macS.Phase)) → 综合$($comp.Score)分 [$($comp.RatingShort)]"
    Write-Host "  [预判] 短期:$($pred.Short) 中期:$($pred.Mid) 长期:$($pred.Long) 支撑:$($pred.Support) 阻力:$($pred.Resistance)"

    # 极端事件检查 (v3.0)
    $extremeEvents = Test-ExtremeEvent -D $stockData
    if ($extremeEvents.Events.Count -gt 0) {
        if ($extremeEvents.HasCritical) {
            Write-Host "  [⛔ 极端事件] CRITICAL: $(($extremeEvents.Events | Where-Object {$_.Severity -eq 'CRITICAL'}).Type -join ', ')" -ForegroundColor Red
        } else {
            Write-Host "  [⚠ 极端事件] $(($extremeEvents.Events).Type -join ', ')"
        }
    }

    # Volume Profile (G1: 成交密集区 → 增强支撑/压力位)
    $vp = Get-VolumeProfile -KLines $stockData.KLines

    # 操作建议计算 (v3.0 S3硬优先级)
    $ops = Get-OperationPlan -D $stockData -Pred $pred -TechS $techS -FundS $fundS -CompScore $comp.Score -VP $vp
    Write-Host "  [操作] S1:$($ops.S1) R1:$($ops.R1) 止损:S3=$($ops.StopLoss) 仓位上限:$($ops.MaxPosition)%"

    # 信号冲突裁决 (v3.0)
    $confidence = $pred.Confidence
    $conflict = Get-ConflictArbitration -TechS $techS -FundS $fundS -SectS $sectS -CapS $capS -Pred $pred -Confidence $confidence
    if ($conflict.HasConflict) {
        Write-Host "  [冲突裁决] $($conflict.Verdict)"
    }

    # 不做清单检查 (v3.0)
    $dontDo = Get-DontDoCheck -D $stockData -Pred $pred -TechS $techS -CompScore $comp.Score
    if ($dontDo.HasIssues) {
        Write-Host "  [不做清单] 违规$(($dontDo.Violations).Count)项 / 警告$(($dontDo.Warnings).Count)项"
    }

    # 生成HTML
    $html = New-StockReportHtml -D $stockData -Scores $scores -Pred $pred -Health $health -Ops $ops -GlobalSectors $globalSectors -GlobalSectorFund $globalSectorFund -dateLabel $dateLabel -ExtremeEvents $extremeEvents -ConflictResult $conflict -DontDoResult $dontDo
    [System.IO.File]::WriteAllText($htmlFile, $html, [System.Text.UTF8Encoding]::new($false))
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

    # 只在PDF转换成功时才清理HTML；转换失败时保留HTML供人工查看
    if ($ok -and -not $KeepHtml) {
        if (Test-Path $htmlFile) { Remove-Item $htmlFile -Force }
    }

    # 累积评估数据（含指标级信号）
    # --- 构建信号状态 ---
    $_ma5 = $stockData.MA5[-1]; $_ma10 = $stockData.MA10[-1]; $_ma20 = $stockData.MA20[-1]; $_p = $stockData.Price
    $_maTrend = if ($_ma5 -gt $_ma10 -and $_ma10 -gt $_ma20 -and $_p -gt $_ma20) { "多头排列" } elseif ($_ma5 -lt $_ma10 -and $_ma10 -lt $_ma20) { "空头排列" } else { "纠缠/不明" }
    $_macdPos = if ($stockData.MACD) { $d=$stockData.MACD.DIF[-1]; $e=$stockData.MACD.DEA[-1]; if($d -gt $e -and $d -gt 0){"零轴上金叉"}elseif($d -gt $e){"零轴下金叉"}else{"死叉"} } else { "N/A" }
    $_rsiVal = if ($stockData.RSI9.Count -gt 0 -and $stockData.RSI9[-1] -ne $null) { [double]$stockData.RSI9[-1] } elseif ($stockData.RSI14.Count -gt 0) { [double]$stockData.RSI14[-1] } else { 50 }
    $_rsiZone = if ($_rsiVal -ge 70) { "超买" } elseif ($_rsiVal -ge 50) { "中性偏强" } elseif ($_rsiVal -ge 30) { "中性偏弱" } else { "超卖" }
    $_adxVal = if ($stockData.ADX -and $stockData.ADX.ADX.Count -gt 0 -and $stockData.ADX.ADX[-1] -ne $null) { [Math]::Round([double]$stockData.ADX.ADX[-1],1) } else { 0 }
    $_adxTrend = if ($_adxVal -gt 25) { "趋势行情" } elseif ($_adxVal -gt 20) { "趋势形成中" } else { "震荡市(ADX<20)" }
    $_obvTrend = "N/A"
    if ($stockData.OBV -and $stockData.OBV.Count -ge 6) {
        $obvChg = if ($stockData.OBV[-6] -ne 0) { [Math]::Round(($stockData.OBV[-1] - $stockData.OBV[-6]) / [Math]::Abs($stockData.OBV[-6]) * 100, 1) } else { 0 }
        $pChg = if ($stockData.KLines[-6].Close -ne 0) { [Math]::Round(($stockData.KLines[-1].Close - $stockData.KLines[-6].Close) / $stockData.KLines[-6].Close * 100, 1) } else { 0 }
        $_obvTrend = if ($obvChg -gt 2 -and $pChg -gt 0) { "量价同升" } elseif ($obvChg -gt 2 -and $pChg -lt 0) { "底背离" } elseif ($obvChg -lt -2 -and $pChg -gt 0) { "顶背离" } elseif ($obvChg -lt -2) { "量价同跌" } else { "中性" }
    }
    $_bollPos = if ($stockData.Bollinger -and $stockData.KLines.Count -gt 0) { $c=$stockData.KLines[-1].Close; $u=$stockData.Bollinger.Upper[-1]; $m=$stockData.Bollinger.MA[-1]; $l=$stockData.Bollinger.Lower[-1]; if($c -ge $u){"触及上轨"}elseif($c -ge $m){"中轨上方"}elseif($c -ge $l){"中轨下方"}else{"触及下轨"} } else { "N/A" }
    $_volRel = if ($stockData.VolMA5.Count -gt 1 -and $stockData.VolMA5[-2] -gt 0) { $vr=$stockData.KLines[-1].Volume/$stockData.VolMA5[-2]; $cg=$stockData.Quote.ChangePct; if($cg -ge 2 -and $vr -ge 1.5){"放量上涨"}elseif($cg -ge 0 -and $vr -le 1.1){"缩量上涨"}elseif($cg -lt -2 -and $vr -ge 1.5){"放量下跌"}elseif($cg -lt 0 -and $vr -le 0.8){"缩量下跌"}else{"量能正常"} } else { "N/A" }
    $_fin = $stockData.Financial
    $_finArr = @($_fin)
    $_roeLevel = if ($_finArr.Count -gt 0) { $r=[double]$_finArr[0].WEIGHTAVG_ROE; if($r -ge 15){"优秀(≥15%)"}elseif($r -ge 10){"良好(≥10%)"}elseif($r -ge 5){"一般(≥5%)"}else{"较差(<5%)"} } else { "N/A" }
    $_peZone = if ($stockData.PEPercentile) { $p=$stockData.PEPercentile.Percentile; if($p -lt 20){"低估(<20%)"}elseif($p -lt 40){"偏低(20-40%)"}elseif($p -lt 60){"合理(40-60%)"}elseif($p -lt 80){"偏高(60-80%)"}else{"高估(>80%)"} } else { "N/A" }
    $_debtLevel = if ($_finArr.Count -gt 0) { $d=[double]$_finArr[0].DEBT_ASSET_RATIO; if($d -lt 30){"低杠杆"}elseif($d -lt 50){"合理"}elseif($d -lt 65){"偏高"}else{"高杠杆"} } else { "N/A" }
    $_rArr = @($stockData.Research)
    $_rCover = if ($_rArr.Count -gt 0) { "有($($_rArr.Count)篇)" } else { "无研报" }
    $_ffArr = @($stockData.FundFlow)
    $_ffTrend = if ($_ffArr.Count -gt 0) { $pos=(@($_ffArr | Where-Object {$_.MainNetInflow -gt 0})).Count; if($pos -ge 3){"主力持续流入"}elseif($pos -ge 1){"主力流入>流出"}else{"主力流出"} } else { "N/A" }
    $_wyckoffPhase = Get-WyckoffPhase -D $stockData

    $script:evalStocks += @{
        Code = $code; Name = $name; Industry = $s.Industry; Date = $dateStr; Price = [Math]::Round($stockData.Price, 2)
        Scores = @{ Technical=$techS; Fundamental=$fundS; Sentiment=$sentS; Sector=$sectS; Capital=$capS; Macro=$macS; Composite=$comp.Score }
        Rating = $comp.RatingShort; RatingFull = $comp.Rating
        Prediction = @{ Short=$pred.Short; Mid=$pred.Mid; Long=$pred.Long; Confidence=$pred.Confidence; ShortBull=$pred.ShortBull; MidBull=$pred.MidBull; LongBull=$pred.LongBull }
        KeyLevels = @{ Support=[Math]::Round($pred.Support,2); Resistance=[Math]::Round($pred.Resistance,2); StopLoss=[Math]::Round($ops.StopLoss,2) }
        TrendHealth = @{ Score=$health.Score; Label=$health.Label }
        Signals = @{
            MA_Trend = $_maTrend; MACD_Position = $_macdPos
            RSI_Value = [Math]::Round($_rsiVal,1); RSI_Zone = $_rsiZone
            ADX_Value = $_adxVal; ADX_Trend = $_adxTrend
            OBV_Trend = $_obvTrend
            Bollinger_Position = $_bollPos; Volume_Relation = $_volRel
            ROE_Level = $_roeLevel; PE_Percentile_Zone = $_peZone; Debt_Level = $_debtLevel
            Research_Coverage = $_rCover; FundFlow_Trend = $_ffTrend
            Wyckoff_Phase = $_wyckoffPhase
            ShortBull_Score = $pred.ShortBull; MidBull_Score = $pred.MidBull; LongBull_Score = $pred.LongBull
        }
    }

    # 写入预判记录 CSV（闭环数据起点）
    $predCsvDir = Join-Path $rootDir "重点股票\预判记录"
    if (-not (Test-Path $predCsvDir)) { New-Item -ItemType Directory -Path $predCsvDir -Force | Out-Null }
    $predCsvFile = Join-Path $predCsvDir "predictions.csv"
    $predHeader = "date,stock_code,stock_name,short_term_dir,mid_term_dir,long_term_dir,resistance_r1,resistance_r2,resistance_r3,support_s1,support_s2,support_s3,confidence,accuracy,notes"
    if (-not (Test-Path $predCsvFile)) {
        Add-Content -Path $predCsvFile -Value $predHeader -Encoding UTF8
    }
    $predRow = "$dateStr,$code,$name,$($pred.Short),$($pred.Mid),$($pred.Long),$($ops.R1),$($ops.R2),$($ops.R3),$($ops.S1),$($ops.S2),$($ops.S3),$($pred.Confidence),,"
    Add-Content -Path $predCsvFile -Value $predRow -Encoding UTF8

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
$evalJson = @{
    Date = $dateStr
    GeneratedAt = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
    Stocks = $script:evalStocks
    _schema_version = "1.0"
    _generated_by = "run_keystock_analysis.ps1"
    _generated_at = (Get-Date -Format 'yyyy-MM-ddTHH:mm:ss')
} | ConvertTo-Json -Depth 10
[System.IO.File]::WriteAllText($evalFile, $evalJson, [System.Text.UTF8Encoding]::new($false))
Write-Host "评估数据保存: $evalFile"

# P0-1: 双写到历史数据/02_评估数据/ (情墨持久化架构)
$archiveEvalDir = Join-Path $rootDir "历史数据\02_评估数据"
if (-not (Test-Path $archiveEvalDir)) { New-Item -ItemType Directory -Path $archiveEvalDir -Force | Out-Null }
$archiveEvalFile = Join-Path $archiveEvalDir "评估数据_${dateStr}.json"
Copy-Item $evalFile $archiveEvalFile -Force
Write-Host "评估数据双写: $archiveEvalFile"

# v3.0 字段完整性校验
$requiredV30Fields = @("ADX_Value", "ADX_Trend", "OBV_Trend", "Wyckoff_Phase")
$schemaOk = $true
foreach ($s in $script:evalStocks) {
    foreach ($f in $requiredV30Fields) {
        if (-not $s.Signals.ContainsKey($f)) {
            Write-Warning "评估数据 v3.0字段缺失: $($s.Code) $($s.Name) — $f"
            $schemaOk = $false
        }
    }
}
if ($schemaOk) {
    Write-Host "v3.0字段完整性校验通过 ($($script:evalStocks.Count)只股票 x $($requiredV30Fields.Count)字段)" -ForegroundColor Green
} else {
    Write-Warning "v3.0字段完整性校验失败，请检查报告输出"
}

# Auto-commit: deep_analysis outputs
$gitAuto = Join-Path $rootDir "代码文件\tools\git_autocommit.ps1"
if (Test-Path $gitAuto) {
    $null = & $gitAuto -Module "deep_analysis" -Paths @("重点股票\股票报告\", "重点股票\次日评估\") -Message "深度分析产出"
}
