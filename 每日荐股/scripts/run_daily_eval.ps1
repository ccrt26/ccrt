# 铁律量化 - 每日荐股次日后评估执行脚本
# 基于：次日后评估白皮书 v1.2
# 输出：每日荐股后评估报告 PDF
# 调用方式：.\run_daily_eval.ps1 [-ReportDate "YYYYMMDD"] [-KeepHtml]

param(
    [string]$ReportDate = "",
    [switch]$KeepHtml = $false
)

$rootDir = "C:\Users\34269\Documents\Claude\股票分析"
$modulePath = Join-Path $rootDir "每日荐股\scripts\stock_data_fetcher.psm1"
$dataFile = Join-Path $rootDir "data_final.json"
$edgePath = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

# 输出目录
$evalReportDir = Join-Path $rootDir "每日荐股\评估报告"
if (-not (Test-Path $evalReportDir)) { New-Item -ItemType Directory -Path $evalReportDir -Force | Out-Null }

# 导入数据模块
if (Test-Path $modulePath) {
    Import-Module $modulePath -Force -WarningAction SilentlyContinue 2>$null
    Write-Host "数据模块已导入"
} else {
    Write-Error "Module not found: $modulePath"
    exit 1
}

$execDate = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$todayStr = Get-Date -Format "yyyyMMdd"

# ============================================================
# 读取 T 日荐股数据
# ============================================================
Write-Host "`n========== 每日荐股次日后评估 =========="
Write-Host "执行时间: $execDate`n"

if (-not (Test-Path $dataFile)) {
    Write-Error "数据文件不存在: $dataFile"
    exit 1
}

$rawData = Get-Content $dataFile -Raw -Encoding UTF8 | ConvertFrom-Json

# 选取推荐股票（总分>=60 或 排名前5）
if ($rawData -is [array]) {
    $topN = $rawData | Sort-Object TotalScore -Descending | Select-Object -First 8
} else {
    $topN = @($rawData) | Sort-Object TotalScore -Descending | Select-Object -First 8
}

Write-Host "T日荐股数据: $($rawData.Count) 只候选, 选取前 $($topN.Count) 只评估`n"
Write-Host ("{0,-10} {1,-10} {2,-8} {3,-8} {4,-8}" -f "代码", "名称", "T日价", "总分", "评级")
Write-Host ("{0,-10} {1,-10} {2,-8} {3,-8} {4,-8}" -f "------", "------", "------", "----", "----")

foreach ($s in $topN) {
    $rating = if ($s.TotalScore -ge 70) { "推荐" } elseif ($s.TotalScore -ge 55) { "观察" } elseif ($s.TotalScore -ge 40) { "谨慎" } else { "回避" }
    Write-Host ("{0,-10} {1,-10} {2,-8} {3,-8} {4,-8}" -f $s.Code, $s.Name, [Math]::Round($s.Price,2), $s.TotalScore, $rating)
}

# ============================================================
# 获取 T+1 日行情（对比评估）
# ============================================================
Write-Host "`n获取 T+1 日行情数据对比..."

$evalResults = @()
$totalWin = 0; $totalLoss = 0; $winCount = 0; $lossCount = 0
$totalReturn = 0

# 维度回检 - 使用英文键名避免编码问题
$dimCorrect = @{ tech=0; fund=0; money=0; news=0; risk=0 }
$dimTotal   = @{ tech=0; fund=0; money=0; news=0; risk=0 }
$dimNames   = @{ tech="技术"; fund="基本面"; money="资金"; news="消息"; risk="风控" }

foreach ($s in $topN) {
    # 获取最新行情
    $quote = Get-StockQuote -Code $s.Code
    if (-not $quote -or $quote.Price -eq 0) {
        Write-Host "  !! $($s.Name)($($s.Code)) 行情获取失败，跳过"
        continue
    }

    $tPrice = $s.Price                 # T日收盘价
    $t1Price = $quote.Price            # T+1日当前价
    $t1Change = $quote.ChangePct       # T+1日涨跌幅
    $returnPct = ($t1Price - $tPrice) / $tPrice * 100

    $isWin = $returnPct -gt 0
    if ($isWin) { $winCount++; $totalWin += $returnPct } else { $lossCount++; $totalLoss += $returnPct }
    $totalReturn += $returnPct

    # 简单维度归因
    $dimNotes = @()
    if ($s.S_Tech -ge 7) { $dimTotal.tech++; if ($returnPct -lt -2) { $dimNotes += "技术面误判" } else { $dimCorrect.tech++ } }
    if ($s.S_Fund -ge 7) { $dimTotal.fund++; if ($returnPct -lt -2) { $dimNotes += "基本面误判" } else { $dimCorrect.fund++ } }
    if ($s.S_Money -ge 7) { $dimTotal.money++; if ($returnPct -lt -2) { $dimNotes += "资金面误判" } else { $dimCorrect.money++ } }
    if ($s.S_News -ge 7) { $dimTotal.news++; if ($returnPct -lt -2) { $dimNotes += "消息面误判" } else { $dimCorrect.news++ } }
    if ($s.S_Risk -ge 5) { $dimTotal.risk++; if ($returnPct -lt -2) { $dimNotes += "风控误判" } else { $dimCorrect.risk++ } }

    $signal = if ($isWin) { "+" } else { "" }
    $misjudge = if ($dimNotes.Count -gt 0) { $dimNotes -join ";" } else { "-" }
    $winMark = if ($isWin) { "[OK]" } else { "[--]" }

    Write-Host ("  {0,-10} {1,-8} T价:{2,-8} 现价:{3,-8} 涨幅:{4,7}% {5,-8} {6}" -f $s.Name, $s.Code, [Math]::Round($tPrice,2), [Math]::Round($t1Price,2), "$signal$([Math]::Round($returnPct,2))", $winMark, $misjudge)

    $evalResults += [PSCustomObject]@{
        Code = $s.Code; Name = $s.Name
        TPrice = [Math]::Round($tPrice,2)
        T1Price = [Math]::Round($t1Price,2)
        ReturnPct = [Math]::Round($returnPct,2)
        TotalScore = $s.TotalScore
        IsWin = $isWin
        S_Tech = $s.S_Tech; S_Fund = $s.S_Fund
        S_Money = $s.S_Money; S_News = $s.S_News; S_Risk = $s.S_Risk
        Misjudge = $misjudge
    }
}

# ============================================================
# 计算汇总指标
# ============================================================
$totalEval = $evalResults.Count
$winRate = if ($totalEval -gt 0) { [Math]::Round($winCount / $totalEval * 100, 1) } else { 0 }
$avgWin = if ($winCount -gt 0) { [Math]::Round($totalWin / $winCount, 2) } else { 0 }
$avgLoss = if ($lossCount -gt 0) { [Math]::Round($totalLoss / $lossCount, 2) } else { 0 }
$profitLossRatio = if ($avgLoss -ne 0) { [Math]::Round([Math]::Abs($avgWin / $avgLoss), 2) } else { 0 }
$portfolioReturn = if ($totalEval -gt 0) { [Math]::Round($totalReturn / $totalEval, 2) } else { 0 }
$bestStock = $evalResults | Sort-Object ReturnPct -Descending | Select-Object -First 1
$worstStock = $evalResults | Sort-Object ReturnPct | Select-Object -First 1

# 维度回检
$dimChecks = @()
foreach ($key in @("tech","fund","money","news","risk")) {
    $cor = $dimCorrect[$key]; $tot = $dimTotal[$key]
    $rate = if ($tot -gt 0) { [Math]::Round($cor / $tot * 100, 1) } else { "-" }
    $dimChecks += [PSCustomObject]@{ Dim=$dimNames[$key]; Correct=$cor; Total=$tot; Rate=$rate }
}

Write-Host "`n========== 评估汇总 =========="
Write-Host "评估股票: $totalEval 只"
Write-Host "次日胜率: $winRate% ($winCount胜/$lossCount负)"
Write-Host "平均盈利: $avgWin% | 平均亏损: $avgLoss%"
Write-Host "盈亏比: $profitLossRatio : 1"
Write-Host "组合日收益: $portfolioReturn%"
if ($bestStock) { Write-Host "最佳: $($bestStock.Name) $($bestStock.ReturnPct)%" }
if ($worstStock) { Write-Host "最差: $($worstStock.Name) $($worstStock.ReturnPct)%" }

# ============================================================
# 生成 HTML 报告
# ============================================================
Write-Host "`n生成评估报告..."

$stockRows = ""
foreach ($r in $evalResults) {
    $cls = if ($r.IsWin) { "win" } else { "loss" }
    $mark = if ($r.IsWin) { "[OK]" } else { "[--]" }
    $stockRows += @"
<tr class="$cls">
    <td>$($r.Code)</td><td>$($r.Name)</td>
    <td>$($r.TPrice)</td><td>$($r.T1Price)</td>
    <td class="$cls">$(if($r.IsWin){'+'})$($r.ReturnPct)%</td>
    <td>$($r.TotalScore)</td>
    <td style="font-size:12px;">$mark</td>
    <td style="font-size:12px;color:#999;">$($r.Misjudge)</td>
</tr>
"@
}

$dimRows = ""
foreach ($d in $dimChecks) {
    $cls = if ($d.Rate -ne "-" -and [double]$d.Rate -ge 60) { "color:#27ae60" } elseif ($d.Rate -ne "-") { "color:#e67e22" } else { "color:#999" }
    $dimRows += "<tr><td>$($d.Dim)</td><td>$($d.Correct)/$($d.Total)</td><td style='$cls'>$($d.Rate)%</td></tr>"
}

# 评分有效性分析
$scoreValidityHtml = ""
if ($evalResults.Count -ge 2) {
    $highScore = $evalResults | Where-Object { $_.TotalScore -ge 55 }
    $lowScore = $evalResults | Where-Object { $_.TotalScore -lt 55 }
    $hsWin = 0; $hsTotal = 0; $lsWin = 0; $lsTotal = 0
    if ($highScore) { $hsTotal = $highScore.Count; $hsWin = ($highScore | Where-Object IsWin).Count }
    if ($lowScore) { $lsTotal = $lowScore.Count; $lsWin = ($lowScore | Where-Object IsWin).Count }
    $hsWinRate = if ($hsTotal -gt 0) { [Math]::Round($hsWin / $hsTotal * 100, 1) } else { 0 }
    $lsWinRate = if ($lsTotal -gt 0) { [Math]::Round($lsWin / $lsTotal * 100, 1) } else { 0 }
    $diff = [Math]::Round($hsWinRate - $lsWinRate, 1)
    $diffMark = if ($diff -ge 15) { "良好" } elseif ($diff -ge 5) { "一般" } else { "不足" }
    $scoreValidityHtml = "<p>高分组（>=55分）胜率：<strong>$hsWinRate%</strong> | 低分组（<55分）胜率：<strong>$lsWinRate%</strong> | 区分度：<strong>$diff%</strong> ($diffMark)</p>"
} else {
    $scoreValidityHtml = "<p>数据不足，无法计算评分区分度</p>"
}

# 评估结论
$verdictHtml = ""
if ($winRate -ge 60) {
    $verdictHtml = "<div class='verdict-box verdict-good'><div class='v-title' style='color:#27ae60;'>整体表现达标</div><div class='v-detail'>胜率 $winRate% >= 目标60%，推荐体系有效</div></div>"
} elseif ($winRate -ge 45) {
    $verdictHtml = "<div class='verdict-box verdict-warn'><div class='v-title' style='color:#f39c12;'>表现需关注</div><div class='v-detail'>胜率 $winRate% 低于目标60%，需审查评分逻辑</div></div>"
} else {
    $verdictHtml = "<div class='verdict-box verdict-bad'><div class='v-title' style='color:#e74c3c;'>表现不佳</div><div class='v-detail'>胜率 $winRate% 显著低于目标，建议全面排查评分体系</div></div>"
}

$plHtml = ""
if ($profitLossRatio -ge 1.5) {
    $plHtml = "<p style='margin-top:8px;'>盈亏比 $profitLossRatio:1 >= 目标1.5:1，赔率结构健康</p>"
} else {
    $plHtml = "<p style='margin-top:8px;'>盈亏比 $profitLossRatio:1 低于目标1.5:1，盈利覆盖亏损能力不足</p>"
}

# 最佳/最差
$bestHtml = ""
$worstHtml = ""
if ($bestStock) {
    $bestHtml = "<div class='bw-item bw-best'><div class='bw-label'>最佳表现</div><div class='bw-name' style='color:#e74c3c;'>$($bestStock.Name)</div><div class='bw-ret'>$($bestStock.Code) | 评分 $($bestStock.TotalScore) | 涨幅 <strong>$(if($bestStock.ReturnPct -gt 0){'+'})$($bestStock.ReturnPct)%</strong></div></div>"
}
if ($worstStock) {
    $worstHtml = "<div class='bw-item bw-worst'><div class='bw-label'>最差表现</div><div class='bw-name' style='color:#27ae60;'>$($worstStock.Name)</div><div class='bw-ret'>$($worstStock.Code) | 评分 $($worstStock.TotalScore) | 涨幅 <strong>$($worstStock.ReturnPct)%</strong></div></div>"
}

# 胜率显示颜色
$wrColor = if ($winRate -ge 60) { "#27ae60" } elseif ($winRate -ge 40) { "#f39c12" } else { "#e74c3c" }
$prColor = if ($portfolioReturn -gt 0) { "#e74c3c" } else { "#27ae60" }

$html = @"
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>每日荐股后评估报告</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: "Microsoft YaHei", "微软雅黑", sans-serif; color: #333; background: #f0f2f5; padding: 20px; }
.report-page { max-width: 210mm; margin: 0 auto; background: #fff; padding: 15mm 18mm; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
.header { background: #1a1a2e; color: #fff; padding: 28px 30px; border-radius: 10px; margin-bottom: 20px; }
.header h1 { font-size: 24px; margin-bottom: 8px; }
.header .subtitle { font-size: 15px; opacity: 0.8; }
.section { margin: 18px 0; }
.section h2 { font-size: 18px; color: #16213e; border-bottom: 2px solid #1a1a2e; padding-bottom: 6px; margin-bottom: 12px; }
.section h3 { font-size: 15px; color: #333; margin: 10px 0 6px; }
table { width: 100%; border-collapse: collapse; margin: 8px 0 14px; font-size: 13px; }
th { background: #1a1a2e; color: #fff; padding: 8px 10px; text-align: center; font-weight: normal; }
td { padding: 6px 10px; border: 1px solid #e0e0e0; text-align: center; }
tr:nth-child(even) { background: #f8f9fa; }
.win { color: #e74c3c; } .loss { color: #27ae60; }
.summary-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 12px 0; }
.summary-item { text-align: center; padding: 16px; background: #f8f9fa; border-radius: 8px; border-left: 4px solid #3498db; }
.summary-item .val { font-size: 28px; font-weight: bold; margin: 4px 0; }
.summary-item .lbl { font-size: 13px; color: #888; }
.best-worst { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin: 12px 0; }
.bw-item { padding: 14px; border-radius: 8px; }
.bw-best { background: #fde8e8; border: 1px solid #f5c6c6; }
.bw-worst { background: #e8f5e9; border: 1px solid #c6e6c8; }
.bw-item .bw-label { font-size: 11px; color: #888; }
.bw-item .bw-name { font-size: 18px; font-weight: bold; }
.bw-item .bw-ret { font-size: 14px; }
.verdict-box { padding: 16px; border-radius: 8px; margin: 12px 0; text-align: center; }
.verdict-good { background: #e8f5e9; border: 2px solid #27ae60; }
.verdict-warn { background: #fff8e1; border: 2px solid #f39c12; }
.verdict-bad { background: #fde8e8; border: 2px solid #e74c3c; }
.verdict-box .v-title { font-size: 16px; font-weight: bold; }
.verdict-box .v-detail { font-size: 13px; margin-top: 4px; }
.disclaimer { margin-top: 24px; padding-top: 12px; border-top: 1px solid #ddd; font-size: 11px; color: #999; line-height: 1.8; }
</style>
</head>
<body>
<div class="report-page">
    <div class="header">
        <h1>每日荐股后评估报告</h1>
        <div class="subtitle">评估 T日荐股表现 | 生成时间: $execDate | 评估股票: $totalEval 只</div>
    </div>

    <div class="section">
        <h2>整体表现</h2>
        <div class="summary-grid">
            <div class="summary-item" style="border-left-color:#27ae60;"><div class="lbl">次日胜率</div><div class="val" style="color:$wrColor">$winRate%</div><div class="lbl">$winCount胜 / $lossCount负</div></div>
            <div class="summary-item" style="border-left-color:#2980b9;"><div class="lbl">盈亏比</div><div class="val" style="color:#2980b9;">$profitLossRatio : 1</div><div class="lbl">平均盈利 $avgWin% / 亏损 $avgLoss%</div></div>
            <div class="summary-item" style="border-left-color:#f39c12;"><div class="lbl">组合日收益</div><div class="val" style="color:$prColor">$(if($portfolioReturn -gt 0){'+'})$portfolioReturn%</div><div class="lbl">推荐组合等权平均</div></div>
            <div class="summary-item" style="border-left-color:#8e44ad;"><div class="lbl">评估数量</div><div class="val" style="color:#8e44ad;">$totalEval</div><div class="lbl">入选推荐标的</div></div>
        </div>

        <div class="best-worst">
            $bestHtml
            $worstHtml
        </div>
    </div>

    <div class="section">
        <h2>逐股评估明细</h2>
        <table>
            <tr><th>代码</th><th>名称</th><th>T日收盘</th><th>T+1日现价</th><th>涨跌幅</th><th>总分</th><th>结果</th><th>归因</th></tr>
            $stockRows
        </table>
    </div>

    <div class="section">
        <h2>维度回检</h2>
        <table>
            <tr><th>维度</th><th>正确/总次数</th><th>正确率</th></tr>
            $dimRows
        </table>
        <p style="font-size:12px;color:#888;margin-top:6px;">计分规则：某维度评分>=7且次日涨幅>=-2%计为预期正确；>=7但跌幅>2%计为误判</p>
    </div>

    <div class="section">
        <h2>评分有效性</h2>
        $scoreValidityHtml
    </div>

    <div class="section">
        <h2>评估结论</h2>
        $verdictHtml
        $plHtml
    </div>

    <div class="disclaimer">
        <p><strong>免责声明</strong></p>
        <p>本报告由铁律量化系统自动生成，数据来源包括腾讯行情等公开API。</p>
        <p>评估结果基于T日收盘价与T+1日行情对比，仅反映历史表现，不构成投资建议。</p>
        <p>股票投资有风险，过往表现不代表未来收益。生成时间：$execDate</p>
    </div>
</div>
</body>
</html>
"@

$htmlFile = Join-Path $evalReportDir "每日荐股后评估报告.html"
[System.IO.File]::WriteAllText($htmlFile, $html, [System.Text.Encoding]::UTF8)
Write-Host "  HTML: $htmlFile"

# ============================================================
# 转 PDF
# ============================================================
$pdfFile = Join-Path $evalReportDir "每日荐股后评估报告.pdf"

if (-not (Test-Path $edgePath)) {
    $altEdge = Get-ChildItem "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" -ErrorAction SilentlyContinue
    if (-not $altEdge) { $altEdge = Get-ChildItem "C:\Program Files\Microsoft\Edge\Application\msedge.exe" -ErrorAction SilentlyContinue }
    if ($altEdge) { $edgePath = $altEdge.FullName }
}

if (Test-Path $edgePath) {
    $uri = "file:///$($htmlFile.Replace('\','/'))"
    try {
        $pi = Start-Process -FilePath $edgePath -ArgumentList @(
            "--headless", "--disable-gpu", "--no-sandbox",
            "--print-to-pdf=$pdfFile",
            "--print-to-pdf-no-header",
            "--no-pdf-header-footer",
            "--print-to-pdf-paper-size=A4",
            $uri
        ) -Wait -PassThru -NoNewWindow
        Start-Sleep -Seconds 2
        if ((Test-Path $pdfFile) -and (Get-Item $pdfFile).Length -gt 30000) {
            Write-Host "  PDF: $pdfFile ($([Math]::Round((Get-Item $pdfFile).Length/1KB,0)) KB)"
        } else {
            Write-Host "  !! PDF 转换可能失败，保留HTML文件"
        }
    } catch {
        Write-Warning "PDF转换失败: $_"
    }
} else {
    Write-Warning "Edge not found, 保留HTML文件"
}

if (-not $KeepHtml -and (Test-Path $htmlFile)) {
    Remove-Item $htmlFile -Force
}

Write-Host "`n========== 评估完成 =========="
Write-Host "报告已保存: $pdfFile"
Write-Host "=============================="
