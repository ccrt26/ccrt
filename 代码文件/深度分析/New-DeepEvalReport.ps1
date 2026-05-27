<#
.SYNOPSIS
  New-DeepEvalReport — 深度分析后评估报告生成器 (L1)
.DESCRIPTION
  根据评估结果JSON生成HTML报告并转换为PDF。支持三种模式：Quick/Monthly/Quarterly。
  新增Batch模式：接收跨股票聚合JSON，生成方法论级别综合PDF。
  PDF输出到 深度分析/后评估报告/ 目录。
#>
param(
    [Parameter(Mandatory=$false)]
    [string]$EvalResultPath,             # 评估结果JSON路径（单股票模式）
    [ValidateSet("Quick","Monthly","Quarterly")]
    [string]$Mode = "Quick",             # 报告模式
    [string]$OutputDir = "",             # PDF输出目录
    [switch]$KeepHtml = $false,
    [switch]$Batch,                      # 批量综合报告模式
    [string]$BatchAggregatePath = ""     # 跨股票聚合JSON路径（Batch模式必需）
)

. "$PSScriptRoot/../lib/init_encoding.ps1"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = Split-Path -Parent (Split-Path -Parent $scriptDir)

if (-not $OutputDir) {
    $OutputDir = Join-Path $rootDir "重点股票\深度分析\后评估报告"
}
if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

if ($Batch) {
    if (-not $BatchAggregatePath -or -not (Test-Path $BatchAggregatePath)) {
        Write-Error "Batch mode requires -BatchAggregatePath to an existing JSON file"
        exit 1
    }
    $aggregate = Get-Content $BatchAggregatePath -Raw -Encoding UTF8 | ConvertFrom-Json
    $meta = $aggregate.meta
    $reportDate = $meta.eval_date
    $todayLabel = $meta.eval_date
    $stockCount = $meta.stock_count
} else {
    if (-not $EvalResultPath) {
        Write-Error "Non-batch mode requires -EvalResultPath"
        exit 1
    }
    $evalResult = Get-Content $EvalResultPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $meta = $evalResult.meta
    $reportDate = $meta.report_date
    $todayLabel = $meta.eval_date
    $code = $meta.stock_code
    $name = $meta.stock_name
}

# Edge路径
$edgePath = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if (-not (Test-Path $edgePath)) {
    $edgePath = "C:\Program Files\Microsoft\Edge\Application\msedge.exe"
}

# ============================================================
# CSS
# ============================================================
$CSS = @'
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: "Microsoft YaHei", "微软雅黑", sans-serif; color: #333; background: #f0f2f5; padding: 20px; }
.report-page { max-width: 210mm; margin: 0 auto; background: #fff; padding: 15mm 18mm; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
.header { background: #1a1a2e; color: #fff; padding: 24px 28px; border-radius: 10px; margin-bottom: 20px; }
.header h1 { font-size: 20px; margin-bottom: 4px; }
.header .subtitle { font-size: 14px; opacity: 0.9; }
.section { margin: 16px 0; }
.section h2 { font-size: 17px; color: #16213e; border-bottom: 2px solid #1a1a2e; padding-bottom: 5px; margin-bottom: 10px; }
table { width: 100%; border-collapse: collapse; margin: 8px 0 12px; font-size: 12px; }
th { background: #1a1a2e; color: #fff; padding: 6px 8px; text-align: center; }
td { padding: 5px 8px; border: 1px solid #e0e0e0; text-align: center; }
tr:nth-child(even) { background: #f8f9fa; }
.summary-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin: 8px 0 14px; }
.summary-item { padding: 14px; border-radius: 8px; text-align: center; }
.summary-item .num { font-size: 24px; font-weight: bold; }
.summary-item .lbl { font-size: 12px; color: #666; margin-top: 3px; }
.effective { background: #e8f5e9; color: #27ae60; }
.reference { background: #fff3e0; color: #e67e22; }
.weak { background: #f5f5f5; color: #999; }
.reverse { background: #fde8e8; color: #e74c3c; }
.level-ok { color: #27ae60; font-weight: bold; }
.level-warn { color: #e67e22; font-weight: bold; }
.level-fail { color: #e74c3c; font-weight: bold; }
.insight-box { background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 6px; padding: 10px; margin: 8px 0; font-size: 12px; }
.warn-box { background: #fef2f2; border: 1px solid #fecaca; border-radius: 6px; padding: 10px; margin: 8px 0; font-size: 12px; }
.info-box { background: #eef2ff; border: 1px solid #c7d2fe; border-radius: 6px; padding: 10px; margin: 8px 0; font-size: 12px; }
.tag { display: inline-block; padding: 1px 6px; border-radius: 3px; font-size: 10px; margin: 1px; }
.tag-p0 { background: #fde8e8; color: #e74c3c; font-weight: bold; }
.tag-p1 { background: #fff3e0; color: #e67e22; }
.tag-p2 { background: #eef2ff; color: #4a6cf7; }
.disclaimer { margin-top: 20px; padding-top: 10px; border-top: 1px solid #ddd; font-size: 10px; color: #999; line-height: 1.6; }
'@

# ============================================================
# 文件命名
# ============================================================
$dateLabel = $reportDate
switch ($Mode) {
    "Quick" {
        $pdfName = "深度分析后评估报告_${dateLabel}.pdf"
        $htmlName = "深度分析后评估报告_${dateLabel}.html"
    }
    "Monthly" {
        $monthStr = $dateLabel.Substring(0, 6)
        $pdfName = "深度分析后评估月报_${monthStr}.pdf"
        $htmlName = "深度分析后评估月报_${monthStr}.html"
    }
    "Quarterly" {
        $q = [Math]::Ceiling([int]$dateLabel.Substring(4,2) / 3)
        $yearStr = $dateLabel.Substring(0, 4)
        $pdfName = "深度分析后评估季报_${yearStr}Q${q}.pdf"
        $htmlName = "深度分析后评估季报_${yearStr}Q${q}.html"
    }
}
$pdfFile = Join-Path $OutputDir $pdfName
$htmlFile = Join-Path $OutputDir $htmlName

# ============================================================
# 生成HTML
# ============================================================
if ($Batch) {
    # === Batch mode: methodology-level comprehensive report ===
    $cs = $aggregate.cross_stock
    $dirDist = $aggregate.direction_distribution

    $summaryGrid = ""
    $summaryGrid += "<div class='summary-item effective'><div class='num'>$($cs.effective_count)/$stockCount</div><div class='lbl'>有效标的(A/B级)</div></div>"
    $summaryGrid += "<div class='summary-item reference'><div class='num'>$($cs.composite.mean)</div><div class='lbl'>综合均分(std=$($cs.composite.std))</div></div>"
    $summaryGrid += "<div class='summary-item' style='background:#e3f2fd;'><div class='num' style='color:#1976d2;'>$($cs.a_layer.mean)</div><div class='lbl'>A层均分(通用维度)</div></div>"
    $summaryGrid += "<div class='summary-item' style='background:#f3e5f5;'><div class='num' style='color:#7b1fa2;'>$($cs.b_layer.mean)</div><div class='lbl'>B层均分(特有维度)</div></div>"

    $dimTableRows = ""
    foreach ($dim in $cs.dimension_matrix) {
        $pctCls = if ($dim.mean -ge 70) { "level-ok" } elseif ($dim.mean -ge 40) { "level-warn" } else { "level-fail" }
        $dimTableRows += "<tr><td>$($dim.index)</td><td>$($dim.label)</td><td class='$pctCls'>$($dim.mean)%</td><td>$($dim.std)</td><td>$($dim.min)%</td><td>$($dim.max)%</td><td>$($dim.best_stock)</td><td>$($dim.worst_stock)</td></tr>`n"
    }

    $stockTableRows = ""
    foreach ($s in ($aggregate.stocks_summary | Sort-Object total_score -Descending)) {
        $cls = if ($s.rating -match "A|B") { "level-ok" } elseif ($s.rating -match "D|E") { "level-fail" } else { "level-warn" }
        $stockTableRows += "<tr><td>$($s.name)($($s.code))</td><td>$($s.a_score)</td><td>$($s.b_score)</td><td class='$cls'>$($s.total_score)</td><td>$($s.rating)</td></tr>`n"
    }

    $sgHtml = ""
    if ($aggregate.suggestions.Count -gt 0) {
        $sgHtml += "<div class='section'><h2>框架优化建议</h2>"
        foreach ($sg in $aggregate.suggestions) {
            $tagClass = "tag-$($sg.priority.ToLower())"
            $boxClass = if ($sg.priority -eq "P0") { "warn-box" } else { "info-box" }
            $sgHtml += "<div class='$boxClass'><span class='tag $tagClass'>$($sg.priority)</span> <strong>$($sg.issue)</strong><br><span style='font-size:11px;color:#666;'>$($sg.suggestion)</span></div>"
        }
        $sgHtml += "</div>"
    }

    $html = @"
<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<title>深度分析后评估 — 方法论综合报告 $dateLabel</title><style>$CSS</style></head>
<body><div class="report-page">
<div class="header">
    <h1>深度分析后评估 — $Mode 方法论综合报告</h1>
    <div class="subtitle">评估日期: $dateLabel | 覆盖标的: $stockCount只 | 方法论版本: $($meta.methodology_version)</div>
    <div class="subtitle">综合均分: $($cs.composite.mean) (范围 $($cs.composite.min)-$($cs.composite.max)) | 有效标的: $($cs.effective_count)/$stockCount</div>
</div>
<div class='section'><h2>评估总览</h2>
<div class='summary-grid'>$summaryGrid</div>
<div class='info-box'><strong>评分方向分布:</strong> 正向$($dirDist['正向']) / 中性$($dirDist['中性']) / 反向$($dirDist['反向'])</div>
</div>
<div class='section'><h2>各股票评分排名</h2>
<table><tr><th>标的</th><th>A层</th><th>B层</th><th>总分</th><th>评级</th></tr>
$stockTableRows
</table></div>
<div class='section'><h2>B层维度跨股票矩阵</h2>
<table><tr><th>#</th><th>维度</th><th>均值%</th><th>Std</th><th>Min%</th><th>Max%</th><th>最佳</th><th>最差</th></tr>
$dimTableRows
</table></div>
$sgHtml
<div class="disclaimer">
<p><strong>免责声明</strong>：本后评估报告由铁律量化系统自动生成，仅用于评估深度分析方法论的有效性，不构成任何投资建议。</p>
<p>评估方法: 深度分析后评估逻辑 v1.0 | 生成时间: $((Get-Date).ToString('yyyy-MM-dd HH:mm:ss')) | 核心原则：复盘的是"分析逻辑本身"，不是"股票涨跌对错"</p>
</div>
</div></body></html>
"@

} else {
    # === Single-stock mode (existing behavior) ===
    $totalScore = $evalResult.total_score
    $totalMax = $evalResult.total_max
    $rating = $evalResult.rating
    $direction = $evalResult.direction_calibration.direction
    $dirRho = $evalResult.direction_calibration.rho_T20
    $aScore = $evalResult.a_layer.total_score
    $bScore = $evalResult.b_layer.total_score
    $bMax = $evalResult.b_layer.max_score

    $html = @"
<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<title>深度分析后评估 — $name($code) $dateLabel</title><style>$CSS</style></head>
<body><div class="report-page">
<div class="header">
    <h1>深度分析后评估 — $Mode 报告</h1>
    <div class="subtitle">$name($code) | 报告日期: $reportDate | 评估日期: $todayLabel | 方法论版本: $($meta.report_version)</div>
    <div class="subtitle">综合评分: ${totalScore}/${totalMax} [$rating] | 评分方向: $direction</div>
</div>
"@
    $html += "<div class='section'><h2>评估摘要</h2>"
    $html += "<div class='summary-grid'>"
    $html += "<div class='summary-item' style='background:#e8f5e9;'><div class='num' style='color:#27ae60;'>${aScore}/55</div><div class='lbl'>A层（通用维度）</div></div>"
    $html += "<div class='summary-item' style='background:#e3f2fd;'><div class='num' style='color:#1976d2;'>${bScore}/${bMax}</div><div class='lbl'>B层（特有维度）</div></div>"
    $html += "</div>"
    if ($dirRho) {
        $dirClass = if ($direction -eq "正向") { "level-ok" } elseif ($direction -eq "反向") { "level-fail" } else { "level-warn" }
        $html += "<div class='info-box'><strong>评分方向校准:</strong> Spearman ρ(T+20) = <span class='$dirClass'>$dirRho</span> → $direction</div>"
    }
    if ($evalResult.direction_calibration.confidence_downgrade) {
        $html += "<div class='warn-box'>⚠️ 置信度降档：评分方向异常，本次评估结论降一档置信度</div>"
    }
    $html += "</div>"
    $html += "<div class='section'><h2>B层评估详情</h2>"
    $html += "<table><tr><th>维度</th><th>得分</th><th>满分</th><th>关键信息</th></tr>"
    $bItems = @(
        @{label="B1 催化剂落地追踪"; data=$evalResult.b_layer.b1_catalyst_tracking},
        @{label="B2 市场阶段判断"; data=$evalResult.b_layer.b2_market_phase},
        @{label="B3 行业判断验证"; data=$evalResult.b_layer.b3_industry_verification},
        @{label="B4 幻觉防范效果"; data=$evalResult.b_layer.b4_anti_hallucination},
        @{label="B5 数据源稳定性"; data=$evalResult.b_layer.b5_data_source_stability},
        @{label="B6 情景概率校准"; data=$evalResult.b_layer.b6_scenario_calibration},
        @{label="B7 五红旗前瞻"; data=$evalResult.b_layer.b7_red_flags_predictive},
        @{label="B8 止损位精确性"; data=$evalResult.b_layer.b8_stop_loss_precision},
        @{label="B9 估值预测误差"; data=$evalResult.b_layer.b9_valuation_accuracy},
        @{label="B10 Wyckoff准确性"; data=$evalResult.b_layer.b10_wyckoff_accuracy},
        @{label="B11 公司类型判定"; data=$evalResult.b_layer.b11_company_type_accuracy}
    )
    foreach ($item in $bItems) {
        $d = $item.data
        $score = $d.score
        $max = $d.max
        $pct = if ($max -gt 0) { [Math]::Round($score/$max*100) } else { 0 }
        $cls = if ($pct -ge 70) { "level-ok" } elseif ($pct -ge 40) { "level-warn" } else { "level-fail" }
        $detail = ""
        if ($d.details.status) { $detail = $d.details.status }
        elseif ($d.details.stage) { $detail = $d.details.stage }
        elseif ($d.details.type) { $detail = $d.details.type }
        elseif ($d.details.available) { $detail = "$($d.details.available)/$($d.details.total)源可用" }
        elseif ($d.details.red_count -ge 0) { $detail = "$($d.details.red_count)红$($d.details.yellow_count)黄" }
        elseif ($d.details.catalyst_count -ge 0) { $detail = "$($d.details.catalyst_count)条催化剂" }
        $html += "<tr><td>$($item.label)</td><td class='$cls'>${score}/${max}</td><td>$max</td><td>$detail</td></tr>"
    }
    $html += "</table></div>"
    if ($evalResult.suggestions.Count -gt 0) {
        $html += "<div class='section'><h2>优化建议</h2>"
        foreach ($sg in $evalResult.suggestions) {
            $tagClass = "tag-$($sg.priority.ToLower())"
            $boxClass = if ($sg.priority -eq "P0") { "warn-box" } else { "info-box" }
            $html += "<div class='$boxClass'><span class='tag $tagClass'>$($sg.priority)</span> <strong>$($sg.issue)</strong><br><span style='font-size:11px;color:#666;'>$($sg.suggestion)</span></div>"
        }
        $html += "</div>"
    }
    if ($evalResult.cross_version_report.gaps) {
        $html += "<div class='section'><h2>跨版本差距报告</h2>"
        $html += "<div class='info-box'><strong>报告版本: $($evalResult.cross_version_report.report_version) → 当前版本: $($evalResult.cross_version_report.current_version)</strong></div>"
        $html += "<table><tr><th>#</th><th>当前版本新增检验项</th><th>报告覆盖</th><th>说明</th></tr>"
        $i = 1
        foreach ($gap in $evalResult.cross_version_report.gaps) {
            $html += "<tr><td>$i</td><td>$($gap.item)</td><td>❌ 未覆盖</td><td>$($gap.note)</td></tr>"
            $i++
        }
        $html += "</table></div>"
    }
    $html += @"
<div class="disclaimer">
<p><strong>免责声明</strong>：本后评估报告由铁律量化系统自动生成，仅用于评估深度分析方法论的有效性，不构成任何投资建议。</p>
<p>评估方法: 深度分析后评估逻辑 v1.0 | 生成时间: $((Get-Date).ToString('yyyy-MM-dd HH:mm:ss')) | 核心原则：复盘的是"分析逻辑本身"，不是"股票涨跌对错"</p>
</div>
</div></body></html>
"@
}

# 写HTML
[System.IO.File]::WriteAllText($htmlFile, $html, [System.Text.Encoding]::UTF8)
Write-Host "✅ HTML: $htmlFile"

# ============================================================
# HTML → PDF (Edge headless)
# ============================================================
if (Test-Path $edgePath) {
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
        if ((Test-Path $pdfFile) -and (Get-Item $pdfFile).Length -gt 5000) {
            Write-Host "✅ PDF: $pdfFile ($([Math]::Round((Get-Item $pdfFile).Length/1KB)) KB)"
        } else {
            Write-Warning "PDF may not have generated correctly: $pdfFile"
        }
    } catch {
        Write-Warning "PDF generation error: $_"
    }
} else {
    Write-Warning "Edge not found at $edgePath — PDF skipped"
}

# 清理HTML
if (-not $KeepHtml -and (Test-Path $htmlFile)) {
    Remove-Item $htmlFile -Force
    Write-Host "  HTML已清理 (--KeepHtml保留)"
}

return $pdfFile
