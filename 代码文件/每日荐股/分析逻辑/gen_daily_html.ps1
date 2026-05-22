<#
.SYNOPSIS
  生成铁律量化每日推荐报告（横板 HTML）
  遵循白皮书：每日荐股分析逻辑白皮书 v2.4（§报告输出格式、§数据源标注）
.DESCRIPTION
  读取 data_final.json，计算板块轮动和突破评分，
  生成横板 A4 横向 HTML 报告，并转为 PDF。
.PARAMETER Date
  报告日期 (yyyy-MM-dd)，默认今天
.PARAMETER DataFile
  data_final.json 路径，默认自动查找
.PARAMETER OutDir
  输出目录，默认股票报告目录
.PARAMETER SkipPdf
  跳过 PDF 生成，只输出 HTML
#>
param(
    [string]$Date = (Get-Date -Format "yyyy-MM-dd"),
    [string]$DataFile = "",
    [string]$OutDir = "",
    [switch]$SkipPdf
)

$rootDir = "C:\Users\34269\Documents\Claude\股票分析"
if (-not $DataFile) { $DataFile = Join-Path $rootDir "代码文件\数据\data_scored.json" }
if (-not $OutDir)  { $OutDir  = Join-Path $rootDir "每日荐股\股票报告" }

# 加载 PDF 转换验证工具
. (Join-Path $rootDir "代码文件\监督机制\ConvertTo-Pdf.ps1")

if (-not (Test-Path $DataFile)) { Write-Error "$DataFile not found. Run scoring_engine_v2.py first."; exit 1 }
$data = Get-Content $DataFile -Encoding UTF8 -Raw | ConvertFrom-Json

# 兼容 v2 新格式 (data_scored.json) 和旧格式 (data_final.json)
if ($data.AllStocks) {
    $allStocks = $data.AllStocks
    $summaryInfo = $data.Summary
    # 数据源标记映射表（红线规则 v1.4 §1.2）
    $fieldSources = @{}
    if ($data.FieldSources) {
        foreach ($prop in $data.FieldSources.PSObject.Properties) { $fieldSources[$prop.Name] = $prop.Value }
    }
} else {
    # 旧格式兼容
    $allStocks = $data | Where-Object { $_.TotalScore -ne $null }
    $recommended = $allStocks | Sort-Object TotalScore -Descending
    $summaryInfo = $null
}

# AllStocks 已不含否决股（scoring_engine_v2 输出时已过滤），直接使用
$stocks = $allStocks
if (-not $stocks -or $stocks.Count -eq 0) {
    Write-Warning "No passed stocks, using fallback all stocks"
    $stocks = $allStocks
}

# ----- Sector phase helper -----
# Load industry mapping for sector name resolution
$indMapFile = Join-Path $rootDir "代码文件\数据\eastmoney_sector_map.json"
$INDUSTRY_MAP = @{}
if (Test-Path $indMapFile) {
    $rawMap = Get-Content $indMapFile -Encoding UTF8 | ConvertFrom-Json
foreach ($prop in $rawMap.Map.PSObject.Properties) { $INDUSTRY_MAP[$prop.Name] = $prop.Value }
}
# Reverse map: broad industry -> sub-sector names
$BROAD_TO_EM = @{}
foreach ($em in $INDUSTRY_MAP.Keys) { $broad = $INDUSTRY_MAP[$em]; if (-not $BROAD_TO_EM.ContainsKey($broad)) { $BROAD_TO_EM[$broad] = @() }; $BROAD_TO_EM[$broad] += $em }
function Get-PhaseName($avgChg, $avgTurn, $count) {
    if ($count -le 0) { return "衰退期" }
    if ($avgTurn -gt 5 -and $avgChg -gt 2)  { return "高潮期" }
    if ($avgTurn -gt 3 -and $avgChg -lt -3) { return "衰退期" }
    if ($avgTurn -gt 3 -and $avgChg -gt 0)  { return "主升调整" }
    if ($avgTurn -gt 2 -and $avgChg -lt -1) { return "主升调整" }
    if ($avgChg -ge -1.5 -and $avgTurn -le 4) { return "潜伏期" }
    if ($avgChg -ge -2 -and $avgTurn -le 2) { return "潜伏期" }
    return "潜伏期"
}
function Get-PhaseAdvice($p) {
    if ($p -eq "潜伏期")  { return @("提前埋伏", "t-green") }
    if ($p -eq "主升调整") { return @("持有不加仓", "t-yellow") }
    if ($p -eq "高潮期")  { return @("减仓回避", "t-red") }
    return @("减仓回避", "t-red")
}
function Get-PhaseEmoji($p) {
    if ($p -eq "潜伏期")  { return "🟢" }
    if ($p -eq "高潮期")  { return "🔴" }
    if ($p -eq "衰退期")  { return "🔴" }
    return "🟡"
}
function Get-ShortPhase($p) {
    if ($p -eq "潜伏期")  { return "潜伏" }
    if ($p -eq "主升调整") { return "主升" }
    if ($p -eq "高潮期")  { return "高潮" }
    if ($p -eq "衰退期")  { return "衰退" }
    return $p
}

# ----- Generate recommendation reason (tech + phase + catalyst) -----
function Get-Catalyst($n, $i) {
    if ($n -eq "宁德时代") { return "固太电池储能" }
    if ($n -eq "豪威集团") { return "半导体CIS" }
    if ($n -eq "阳光电源") { return "EU能源电网" }
    if ($n -eq "五粮液")   { return "消费催化" }
    if ($n -eq "恒生电子") { return "数字人民币" }
    if ($n -eq "金山办公") { return "AI办公" }
    if ($n -eq "比亚迪")   { return "新车周期" }
    if ($n -eq "北方华创") { return "国产替代" }
    if ($n -eq "海康威视") { return "AI安防" }
    if ($n -eq "贵州茅台") { return "消费复苏" }
    if ($n -eq "招商银行") { return "高股息" }
    if ($n -eq "汇川技术") { return "工控周期" }
    if ($n -eq "昆仑万维") { return "AI应用" }
    if ($n -eq "科大讯飞") { return "大模型" }
    if ($i -eq "计算机") { return "数字中国" }
    if ($i -eq "电子")   { return "半导体周期" }
    if ($i -eq "通信")   { return "算力基建" }
    return $null
}

function Get-ReasonText {
    param($s, $phaseInfo)
    $parts = @()

    # 技术面描述
    $techDesc = $null
    if ($s.TechAnalysis) {
        $techDesc = $s.TechAnalysis
    } elseif ($s.MA5 -and $s.MA10 -and $s.MA20 -and $s.MA5 -gt 0) {
        $maParts = @()
        if ($s.MA5 -gt $s.MA10 -and $s.MA10 -gt $s.MA20) { $maParts += "均线多头排列" }
        elseif ($s.MA10 -le $s.MA20) { $maParts += "均线收敛" }
        else { $maParts += "均线偏多" }
        $maParts += "MA5=$([math]::Round($s.MA5,1)) MA10=$([math]::Round($s.MA10,1)) MA20=$([math]::Round($s.MA20,1))"
        if ($s.RSI) { $rsiVal = [math]::Round($s.RSI,0); if ($rsiVal -ge 60) { $maParts += "RSI$rsiVal偏强" } elseif ($rsiVal -le 40) { $maParts += "RSI$rsiVal偏弱" } else { $maParts += "RSI$rsiVal中性" } }
        if ($s.MACD_Status) { $maParts += "MACD$($s.MACD_Status)" }
        $techDesc = $maParts -join " | "
    }
    if ($techDesc) { $parts += "技术面：$techDesc" }

    # 板块相位与操作建议
    if ($phaseInfo) {
        $phaseAdvice = Get-PhaseAdvice $phaseInfo.phase
        $parts += "板块：$($phaseInfo.name)处于$($phaseInfo.phase)，建议$($phaseAdvice[0])"
    }

    # 催化支撑
    $catText = Get-Catalyst $s.Name $s.Industry
    if ($catText) {
        $parts += "催化：$catText"
    } elseif ($phaseInfo -and $phaseInfo.avgChg -gt 3) {
        $parts += "催化：板块整体走强，资金关注度提升"
    } else {
        $parts += "催化：行业基本面支撑"
    }

    return $parts -join " | "
}

function Get-SourceTag {
    param([string]$fieldName)
    if (-not $fieldSources -or -not $fieldSources.ContainsKey($fieldName)) { return "" }
    return "<sup class=""src-tag"">$($fieldSources[$fieldName])</sup>"
}

# ----- Compute sector rotation (from real market data, with pool fallback) -----
$sectorPhaseMap = $null
if ($data.SectorPhaseMap) { $sectorPhaseMap = $data.SectorPhaseMap }
$sectorGroups = $allStocks | Group-Object Industry
$sectorRows = @()
foreach ($g in $sectorGroups) {
    $sp = if ($sectorPhaseMap) { $sectorPhaseMap.$($g.Name) } else { $null }
    if (-not $sp -and $BROAD_TO_EM.ContainsKey($g.Name)) {
        foreach ($sub in $BROAD_TO_EM[$g.Name]) { if ($sectorPhaseMap.$sub) { $sp = $sectorPhaseMap.$sub; break } }
    }
    if ($sp) {
        # 使用真实市场数据（来自 scoring_engine_v2.py 的 SectorPhaseMap）
        $ac = $sp.avg_chg
        $at = $sp.avg_turn
        $p = $sp.phase
    } else {
        # 池内聚合备选
        $ac = ($g.Group | Measure-Object ChangePct -Average).Average
        $at = ($g.Group | Measure-Object TurnoverRate -Average).Average
        $p = Get-PhaseName $ac $at $g.Count
    }
    $ad = Get-PhaseAdvice $p
    $sectorRows += @{ name=$g.Name; count=$g.Count; avgChg=$ac; avgTurn=$at; phase=$p; advice=$ad[0]; tagClass=$ad[1] }
}
$phaseOrder = @{ "潜伏期"=0; "主升调整"=1; "高潮期"=2; "衰退期"=3 }
$sectorRows = $sectorRows | Sort-Object @{e={$phaseOrder[$_.phase]}; a=$true}, @{e={[math]::Abs($_.avgChg)}; d=$true}
$phaseMap = @{}; foreach ($r in $sectorRows) { $phaseMap[$r.name] = $r }

# ----- Compute scores (from recommended passed stocks) -----
$scored = @()
foreach ($s in $stocks) {
    $scored += @{ s=$s; total=$s.TotalScore }
}
$scored = $scored | Sort-Object @{Expression={$_.total}} -Descending
$top5 = $scored | Select-Object -First 5

# ----- Build HTML strings -----
$sectorHtml = ""
foreach ($r in $sectorRows) {
    $cc = "down"; if ($r.avgChg -ge 0) { $cc = "up" }
    $emoji = Get-PhaseEmoji $r.phase
    $cs = "{0:F2}%" -f $r.avgChg; if ($r.avgChg -ge 0) { $cs = "+{0:F2}%" -f $r.avgChg }
    $sectorHtml += "<tr><td style=""font-weight:600"">$($r.name)</td><td>$($r.count)</td><td class=""$cc"">$cs</td><td>{0:F2}%</td>" -f $r.avgTurn
    $sectorHtml += "<td>$emoji $($r.phase)</td><td><span class=""tag $($r.tagClass)"">$($r.advice)</span></td></tr>`n"
}

$cardHtml = ""
foreach ($item in $top5) {
    $s = $item.s
    $cc = "down"; if ($s.ChangePct -ge 0) { $cc = "up" }
    $pi = $phaseMap[$s.Industry]
    $pl = ""; $ptc = "t-green"; if ($pi) { $pl = $pi.phase; $ptc = $pi.tagClass }
    $cs = "{0:F2}%" -f $s.ChangePct; if ($s.ChangePct -ge 0) { $cs = "+{0:F2}%" -f $s.ChangePct }
    $reason = Get-ReasonText -s $s -phaseInfo $pi
    $cardHtml += "<div class=""card""><div class=""c-hdr""><div><span class=""c-name"">$($s.Name)</span><span class=""c-code"">$($s.Code)</span></div><div><span class=""tag $ptc"">$pl</span><span class=""c-scr"" style=""margin-left:10px"">$($item.total)<span>/100</span></span></div></div>"
    $cardHtml += "<div class=""c-meta""><span class=""c-meta-item"">$($s.Industry)</span><span class=""c-meta-item"">$($s.Price)$(Get-SourceTag 'Price')元</span><span class=""c-meta-item $cc"">$cs$(Get-SourceTag 'ChangePct')</span><span class=""c-meta-item"">换手$($s.TurnoverRate)$(Get-SourceTag 'TurnoverRate')%</span><span class=""c-meta-item"">PE $($s.PE)$(Get-SourceTag 'PE')</span></div>"
    $cardHtml += "<div class=""c-logic"">$reason</div>"
    $cardHtml += "<div class=""s-bar""><div class=""s-fill bg-green"" style=""width:$($item.total)%""></div></div></div>`n"
}

$fullHtml = ""
$rank = 0
$allScored = $stocks | Sort-Object TotalScore -Descending | Select-Object -First 25 | ForEach-Object { @{ s=$_; total=$_.TotalScore } }
foreach ($item in $allScored) {
    $rank++; $s = $item.s
    $cc = "down"; if ($s.ChangePct -ge 0) { $cc = "up" }
    $sc = ""; if ($s.TotalScore -ge 60) { $sc = "sc-high" } elseif ($s.TotalScore -ge 48) { $sc = "sc-mid" }
    $star = ""; if ($s.TotalScore -ge 60) { $star = "⭐⭐" } elseif ($s.TotalScore -ge 48) { $star = "⭐" }
    $pi2 = $phaseMap[$s.Industry]; $sp = ""; $emoji2 = ""
    if ($pi2) { $sp = Get-ShortPhase $pi2.phase; $emoji2 = Get-PhaseEmoji $pi2.phase }
    $cs = "{0:F2}%" -f $s.ChangePct; if ($s.ChangePct -ge 0) { $cs = "+{0:F2}%" -f $s.ChangePct }
    $stTrend = if ($null -ne $s.S_SectorTrend) { $s.S_SectorTrend } else { 0 }
$fullHtml += "<tr><td>$rank</td><td>$($s.Code)</td><td style=""font-weight:600;text-align:left;padding-left:8px"">$($s.Name)</td><td>$($s.Industry)</td><td>$($s.Price)$(Get-SourceTag 'Price')</td><td class=""$cc"">$cs$(Get-SourceTag 'ChangePct')</td><td>$($s.TurnoverRate)$(Get-SourceTag 'TurnoverRate')%</td><td>$($s.Amplitude)%</td><td>$($s.PE)$(Get-SourceTag 'PE')</td><td>$($s.S_Base)</td><td>$($s.S_Fund)</td><td>$($s.S_Tech)</td><td>$($s.S_Money)</td><td>$($s.S_News)</td><td>$($s.S_Risk)</td><td>$stTrend</td><td class=""$sc"">$($s.TotalScore)</td><td>$star</td><td>$emoji2$sp</td></tr>`n"
}


# ----- CSS -----
$css = @"
@page{size:landscape;margin:12mm 15mm}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:"Microsoft YaHei","PingFang SC","Noto Sans SC",sans-serif;background:#f4f5f7;color:#333;padding:24px}
.container{max-width:100%;margin:0 auto}
.hdr{background:#1a1a2e;color:#fff;padding:36px 44px;border-radius:12px;margin-bottom:22px}
.hdr h1{font-size:36px;font-weight:900;margin-bottom:14px}
.hdr .sub{font-size:20px;font-weight:700;display:flex;justify-content:space-between;margin-top:0;color:#fff}
.hdr .tag{font-size:18px;font-weight:600;margin-top:14px;color:#fff;line-height:1.8}
.sec{background:#fff;border-radius:10px;padding:22px;margin-bottom:18px;box-shadow:0 1px 6px rgba(0,0,0,.06)}
.sec h2{font-size:17px;font-weight:700;margin-bottom:14px;padding-bottom:8px;border-bottom:2px solid #1a1a2e}
table{width:100%;border-collapse:collapse;font-size:12px}
th{background:#f0f2f5;padding:7px 8px;text-align:center;font-weight:600;border-bottom:2px solid #ddd;font-size:11px}
td{padding:6px 8px;text-align:center;border-bottom:1px solid #eee;font-size:11.5px}
.card-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.card{border:1px solid #e6e8ed;border-radius:10px;padding:20px 24px;background:#fafbfc}
.c-hdr{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}
.c-name{font-size:22px;font-weight:700}.c-code{font-size:13px;color:#999;margin-left:8px}
.c-scr{font-size:32px;font-weight:800;color:#1a1a2e}.c-scr span{font-size:14px;font-weight:400;color:#aaa}
.c-meta{display:flex;gap:10px;margin-bottom:12px;flex-wrap:wrap}
.c-meta-item{font-size:14px;background:#edf0f7;padding:5px 14px;border-radius:14px}
.c-logic{font-size:14px;color:#444;margin-top:12px;padding:12px 16px;background:#f2f6ff;border-radius:6px;border-left:3px solid #4a6cf7;line-height:1.6}
.s-bar{height:7px;background:#eee;border-radius:4px;margin-top:12px;overflow:hidden}.s-fill{height:100%;border-radius:4px}
.src-tag{font-size:10px;color:#999;font-weight:400;margin-left:1px;white-space:nowrap}
.bg-green{background:#2ecc71}.bg-yellow{background:#f39c12}.bg-red{background:#e74c3c}
.up{color:#e74c3c;font-weight:600}.down{color:#27ae60;font-weight:600}
.tag{display:inline-block;padding:2px 8px;border-radius:8px;font-size:10px;font-weight:600}
.t-green{background:#d4edda;color:#155724}.t-yellow{background:#fff3cd;color:#856404}.t-red{background:#f8d7da;color:#721c24}
.note{border-left:4px solid #1a1a2e;background:#f8f9fa;padding:10px 14px;border-radius:0 8px 8px 0;margin:10px 0;font-size:12px;line-height:1.6}
.ftr{text-align:center;font-size:11px;color:#aaa;padding:16px 0;line-height:1.8}
.sc-high{background:#d4edda;font-weight:700}.sc-mid{background:#fff3cd;font-weight:600}
.row-2{display:flex;gap:14px;margin-bottom:0}.row-2 .col{flex:1;min-width:0}
@media print{body{background:#fff;padding:15px}.sec{box-shadow:none;border:1px solid #ddd;page-break-inside:avoid}}
"@

# ----- Assemble HTML -----
$html = "<!DOCTYPE html><html lang=""zh-CN""><head><meta charset=""UTF-8"">"
$html += "<title>铁律量化 · 每日股票推荐 $Date</title><style>$css</style></head><body><div class=""container"">"

$html += "<div class=""hdr""><h1>铁律量化 · 每日股票推荐</h1>"
$html += "<div class=""sub""><span>${Date} 收盘</span><span>七维前向评分体系 v2.4</span></div>"
$totalCount = if ($summaryInfo) { $summaryInfo.Total } else { $allStocks.Count }
$vetoedCount = if ($summaryInfo) { $summaryInfo.Vetoed } else { 0 }
$html += "<div class=""tag"">动态池: ${totalCount}只 | 通过否决: $($allStocks.Count)只 | 否决: ${vetoedCount}只 | 推荐上限: 25只 | 否决制+七维评分 | 板块轮动选股</div></div>"

$html += "<div class=""sec""><h2>板块轮动速览</h2><table><tr><th>板块</th><th>股票</th><th>平均涨跌</th><th>平均换手</th><th>轮动相位</th><th>操作建议</th></tr>$sectorHtml</table></div>"

# ----- 板块趋势持续性（v2.4新增）-----
$sectorTrendHtml = ""
if ($data.SectorTrendMap) {
    $trendItems = @()
    foreach ($prop in $data.SectorTrendMap.PSObject.Properties) {
        $info = $prop.Value
        $trendItems += @{
            sector_name = if ($info.sector_name) { $info.sector_name } else { $prop.Name }
            trend_score = $info.trend_score
            is_main = $info.is_long_term_main_line
            kline_avail = $info.sector_kline_available
        }
    }
    $trendItems = $trendItems | Sort-Object trend_score -Descending
    foreach ($ti in $trendItems) {
        $mainLineTag = if ($ti.is_main) { "<span class=""tag t-green"">★主线</span>" } else { "<span class=""tag t-yellow"">轮动</span>" }
        $klineTag = if ($ti.kline_avail) { "<span class=""tag t-green"">有</span>" } else { "<span class=""tag t-red"">无</span>" }
        $sectorTrendHtml += "<tr><td style=""font-weight:600"">$($ti.sector_name)</td><td>$($ti.trend_score)分</td><td>$mainLineTag</td><td>$klineTag</td></tr>`n"
    }
} else {
    $sectorTrendHtml = "<tr><td colspan=""4"" style=""color:#999"">暂无板块趋势持续性数据（SectorTrendMap 为空）</td></tr>"
}
$html += "<div class=""sec""><h2>板块趋势持续性 <span style=""font-size:12px;color:#999;font-weight:400"">(v2.4 新增 · 5分制)</span></h2><table><tr><th>板块</th><th>持续性评分</th><th>主线判定</th><th>K线数据</th></tr>$sectorTrendHtml</table></div>"

$html += "<div class=""sec""><h2>精选推荐 Top 5</h2>"
$html += "<div class=""note"" style=""border-left-color:#2ecc71""><strong>评分理念：</strong>一票否决制(14条规则)先筛除不合格股票→通过者按七维总分排序→取前5只展示推荐理由。总分=基础(10)+基本面(15)+技术面(30)+资金面(20)+消息面(15)+风控(5)+板块趋势(5)=100分。</div>"
$html += "<div class=""card-grid"">$cardHtml</div></div>"

$html += "<div class=""sec""><h2>全部标的评分表</h2><div style=""overflow-x:auto""><table>"
$html += "<tr><th>#</th><th>代码</th><th>名称</th><th>行业</th><th>价格</th><th>涨跌</th><th>换手</th><th>振幅</th><th>PE</th><th>基础</th><th>基本</th><th>技术</th><th>资金</th><th>消息</th><th>风控</th><th>趋势</th><th>总分</th><th>评级</th><th>状态</th></tr>$fullHtml</table></div></div>"


$html += "<div class=""row-2""><div class=""col""><div class=""sec""><h2>数据来源</h2><table>"
$html += "<tr><th style=""width:22%"">数据</th><th style=""width:28%"">来源</th><th>说明</th></tr>"
$html += "<tr><td style=""font-weight:600"">个股行情</td><td>腾讯行情</td><td>实时价格、涨跌幅、换手率</td></tr>"
$html += "<tr><td style=""font-weight:600"">板块数据</td><td>东方财富板块API</td><td>行业板块指数+资金流向真实市场数据，计算轮动相位</td></tr>"
$html += "<tr><td style=""font-weight:600"">行业归属</td><td>申万一级行业</td><td>${totalCount}只股票覆盖$($sectorRows.Count)个行业</td></tr>"
$html += "<tr><td style=""font-weight:600"">评分计算</td><td>本地计算</td><td>七维前向评分体系 v2.4</td></tr></table></div></div>"
$html += "<div class=""col""><div class=""sec""><h2>免责声明</h2>"
$html += "<div style=""font-size:11px;color:#666;line-height:1.6"">本报告由铁律量化系统自动生成，仅供学习研究参考，不构成投资建议。股票投资有风险，过往表现不预示未来收益。请理性投资，风险自担。<br><span style=""color:#999"">铁律量化 · v2.4 · ${Date} 收盘</span></div></div></div></div>"

$html += "<div class=""ftr""><strong>免责声明</strong><br>本报告由铁律量化系统自动生成，仅供学习研究参考，不构成投资建议。<br>股票投资有风险，过往表现不预示未来收益。<br><br>铁律量化 · v2.4 · ${Date} 收盘</div>"
$html += "</div></body></html>"

# ----- Write files -----
if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Path $OutDir -Force | Out-Null }
$dc = $Date -replace '-',''
$htmlFile = Join-Path $OutDir "daily_report_${dc}.html"
[System.IO.File]::WriteAllText($htmlFile, $html, [System.Text.Encoding]::UTF8)

# Self-check: verify HTML was written
if (-not (Test-Path $htmlFile)) { Write-Error "FAILED: HTML not written to $htmlFile"; exit 1 }
$htmlSize = (Get-Item $htmlFile).Length
if ($htmlSize -lt 10000) { Write-Error "FAILED: HTML too small ($htmlSize bytes)"; exit 1 }
Write-Host "[OK] HTML: $htmlFile ($htmlSize bytes)"

if (-not $SkipPdf) {
    $edge = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    $pdfFile = Join-Path $OutDir "每日股票推荐_${dc}_landscape.pdf"
    if (Test-Path $edge) {
        $ok = ConvertTo-Pdf -HtmlFile $htmlFile -PdfFile $pdfFile -EdgePath $edge -Landscape -MinSize 50000
        if ($ok) {
            $pdfSize = (Get-Item $pdfFile).Length
            Write-Host "[OK] PDF:  $pdfFile ($pdfSize bytes)"
        } else {
            Write-Error "FAILED: PDF generation failed at $pdfFile"; exit 1
        }
    } else { Write-Warning "Edge not found, skip PDF generation" }
}
Write-Host "Done"
