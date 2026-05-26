. "$PSScriptRoot/../../../lib/init_encoding.ps1"
# 依赖: dot-source all sibling modules

function Test-AllDataSources {
    Write-Output "====== 数据源综合测试 ======"
    Write-Output "目标股票: 招商银行(600036)`n"

    # [1] 腾讯行情
    Write-Output "--- [1] 腾讯实时行情 ---"
    $quote = Get-StockQuote -Code "600036"
    if ($quote) { Write-Output "  ✅ $($quote.Name) 现价:$($quote.Price) 涨幅:$($quote.ChangePct)% PE:$($quote.PE) 换手:$($quote.TurnoverRate)%" }
    else { Write-Output "  ❌ 失败" }

    # [2] 新浪K线
    Write-Output "--- [2] 新浪K线 ---"
    $klines = Get-StockKLine -Code "600036" -Count 5
    if ($klines) { Write-Output "  ✅ 最近5日: $($klines[-1].Date) 收:$($klines[-1].Close) 量:$($klines[-1].Volume)" }
    else { Write-Output "  ❌ 失败" }

    # [3] 财务数据
    Write-Output "--- [3] 东方财富财务 ---"
    $fin = Get-StockFinancial -Code "600036" -Quarters 2
    if ($fin) { Write-Output "  ✅ EPS:$($fin[0].BASIC_EPS) ROE:$($fin[0].WEIGHTAVG_ROE)% 营收:$($fin[0].TOTAL_OPERATE_INCOME) 净利:$($fin[0].PARENT_NETPROFIT)" }
    else { Write-Output "  ❌ 失败" }

    # [5] 技术指标
    Write-Output "--- [5] 技术指标 ---"
    $klines120 = Get-StockKLine -Code "600036" -Count 120
    if ($klines120) {
        $ma5 = Calc-MovingAverage -Data $klines120 -Period 5
        $ma20 = Calc-MovingAverage -Data $klines120 -Period 20
        $rsi = Calc-RSI -Data $klines120 -Period 14
        $macd = Calc-MACD -Data $klines120
        $boll = Calc-Bollinger -Data $klines120
        Write-Output "  ✅ MA5:$($ma5[-1]) MA20:$($ma20[-1]) RSI14:$($rsi[-1])"
        Write-Output "  ✅ MACD DIF:$([math]::Round($macd.DIF[-1],2)) DEA:$([math]::Round($macd.DEA[-1],2))"
        Write-Output "  ✅ Bollinger 上轨:$($boll.Upper[-1]) 中轨:$($boll.MA[-1]) 下轨:$($boll.Lower[-1])"
    } else { Write-Output "  ❌ 失败" }

    # [7] 板块行业
    Write-Output "--- [7] 板块行业TOP5 ---"
    $sectors = Get-SectorData -Top 5
    if ($sectors) { $sectors | ForEach-Object { Write-Output "  ✅ $($_.SectorName) $($_.ChangePct)% 成交$($_.Turnover)亿" } }
    else { Write-Output "  ❌ 失败" }

    # [9] 个股资金流向
    Write-Output "--- [9] 个股资金流向 ---"
    $fund = Get-StockFundFlow -Code "600036" -Days 3
    if ($fund) { $fund | ForEach-Object { Write-Output "  ✅ $($_.Date) 主力净流入:$([math]::Round($_.MainNetInflow/10000,0))万" } }
    else { Write-Output "  ❌ 失败" }

    # [10] 行业资金流向
    Write-Output "--- [10] 行业资金流向TOP5 ---"
    $sfund = Get-SectorFundFlow -Top 5
    if ($sfund) { $sfund | ForEach-Object { Write-Output "  ✅ $($_.SectorName) 净流入:$([math]::Round($_.NetInflow/100000000,2))亿" } }
    else { Write-Output "  ❌ 失败" }

    # PE百分位
    Write-Output "--- PE百分位 ---"
    $pe = Get-PEPercentile -Code "600036"
    if ($pe) { Write-Output "  ✅ 当前PE:$($pe.CurrentPE) 百分位:$($pe.Percentile)% 估值:$($pe.Valuation) (样本:$($pe.SampleCount)天)" }
    else { Write-Output "  ❌ 失败(数据不足或EPS问题)" }

    # [8] 北向资金
    Write-Output "--- [8] 北向资金持股 ---"
    $nb = Get-NorthboundHold -Code "600036"
    if ($nb) { Write-Output "  ✅ $($nb.Name) 北向持股:$([math]::Round($nb.HoldShares/10000,0))万股 占比:$($nb.SharesRatio)% (数据:$($nb.TradeDate))" }
    else { Write-Output "  ❌ 失败" }

    # [11] 研报
    Write-Output "--- [11] 研报/评级(近30天) ---"
    $research = Get-StockResearch -Code "600036" -Count 3
    if ($research) { $research | ForEach-Object { Write-Output "  ✅ $($_.PublishDate.Substring(0,10)) $($_.OrgName) $($_.Title) [$($_.EmRating)]" } }
    else { Write-Output "  ❌ 失败或无数据" }

    # [12] 融资融券
    Write-Output "--- [12] 融资融券(近3天) ---"
    $margin = Get-MarginData -Code "600036" -Days 3
    if ($margin) { $margin | ForEach-Object { Write-Output "  ✅ $($_.Date.Substring(0,10)) 融资余额:$([math]::Round($_.RZYE/100000000,2))亿 融券余额:$([math]::Round($_.RQYE/100000000,2))亿" } }
    else { Write-Output "  ❌ 失败" }

    # 数据源跟踪
    Write-Output "`n--- 数据源跟踪 ---"
    $src = Get-LastUsedSource
    foreach ($key in $src.Keys) {
        $status = if ($src[$key] -eq "失败") { "❌" } else { "✅" }
        Write-Output "  $status $key → $($src[$key])"
    }

    Write-Output "`n====== 测试完成 ======"
}

Export-ModuleMember -Function Get-StockQuote, Get-StockQuoteBatch, Get-StockKLine, Get-StockFinancial, Get-SectorData, Get-SectorConstituents, Get-StockFundFlow, Get-SectorFundFlow, Get-PEPercentile, Get-NorthboundHold, Get-StockResearch, Get-MarginData, Get-LastUsedSource, Invoke-ThrottledApiCall, Invoke-ThsFallback, Calc-MovingAverage, Calc-RSI, Calc-MACD, Calc-Bollinger, Calc-ADX, Calc-OBV, Calc-ATR, Test-AllDataSources

# ============================================================
# 加载 PDF 转换验证工具（被各报告脚本共享使用）
# ============================================================
$pdfHelper = Join-Path $PSScriptRoot "..\..\..\监督机制\ConvertTo-Pdf.ps1"
if (Test-Path $pdfHelper) {
    . $pdfHelper
} else {
    Write-Warning "[模块] PDF转换工具未找到: $pdfHelper"
}
