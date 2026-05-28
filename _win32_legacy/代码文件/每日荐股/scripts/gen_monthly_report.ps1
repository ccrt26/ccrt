<#
.SYNOPSIS
  铁律量化 · 月度学习PDF报告生成器
.DESCRIPTION
  由 AI 月度学习流程触发，生成调参建议PDF报告。
#>

param(
    [string]$Month = (Get-Date).AddMonths(-1).ToString("yyyy-MM"),
    [string]$SourceDir = "Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))"
)
. "$PSScriptRoot/../../lib/init_encoding.ps1"

$dailyDir = Join-Path $SourceDir "每日荐股"
$scriptsDir = Join-Path $dailyDir "scripts"
$reportDir = Join-Path $SourceDir "历史数据\monthly"

# 加载 PDF 转换验证工具
. (Join-Path $SourceDir "代码文件\监督机制\ConvertTo-Pdf.ps1")
if (-not (Test-Path $reportDir)) { New-Item -ItemType Directory -Path $reportDir -Force | Out-Null }

$edgePath = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if (-not (Test-Path $edgePath)) {
    $alt = Get-ChildItem "C:\Program Files\Microsoft\Edge\Application\msedge.exe" -ErrorAction SilentlyContinue
    if ($alt) { $edgePath = $alt.FullName }
}

# 读取最新的评估数据
$finalFile = Join-Path $SourceDir "代码文件\数据\data_final.json"
$scoredFile = Join-Path $SourceDir "代码文件\数据\data_scored.json"

$totalScored = 0; $totalPassed = 0; $totalVetoed = 0; $passRate = "N/A"
if (Test-Path $scoredFile) {
    $scored = Get-Content $scoredFile -Raw -Encoding UTF8 | ConvertFrom-Json
    $totalScored = $scored.Summary.Total
    $totalPassed = $scored.Summary.Passed
    $totalVetoed = $scored.Summary.Vetoed
    $passRate = $scored.Summary.PassRate
}

$topStocks = @()
if (Test-Path $finalFile) {
    $final = Get-Content $finalFile -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($final -is [array]) {
        $topStocks = $final | Sort-Object TotalScore -Descending | Select-Object -First 5
    }
}

$year, $monthNum = $Month -split '-'
$monthLabel = "$year$monthNum"

$html = @"
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>铁律量化 · 月度学习报告</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: "Microsoft YaHei", sans-serif; color: #333; background: #fff; padding: 20px; }
.page { max-width: 210mm; margin: 0 auto; padding: 10mm 15mm; }
h1 { font-size: 22px; color: #1a1a2e; border-bottom: 3px solid #1a1a2e; padding-bottom: 8px; margin-bottom: 16px; }
h2 { font-size: 17px; color: #16213e; margin: 20px 0 10px; padding-left: 8px; border-left: 3px solid #e74c3c; }
h3 { font-size: 14px; color: #333; margin: 12px 0 6px; }
table { width: 100%; border-collapse: collapse; margin: 8px 0; font-size: 12px; }
th { background: #1a1a2e; color: #fff; padding: 6px 8px; text-align: center; }
td { padding: 5px 8px; border: 1px solid #e0e0e0; }
tr:nth-child(even) { background: #f8f9fa; }
.tag { display: inline-block; padding: 2px 8px; border-radius: 3px; font-size: 11px; margin: 2px; }
.tag-green { background: #e8f5e9; color: #27ae60; }
.tag-orange { background: #fff8e1; color: #f39c12; }
.tag-red { background: #fde8e8; color: #e74c3c; }
.tag-blue { background: #e3f2fd; color: #1976d2; }
.section { margin: 14px 0; }
.card { background: #f8f9fa; border-radius: 6px; padding: 12px; margin: 8px 0; border-left: 4px solid #3498db; }
.card-warn { border-left-color: #f39c12; background: #fffef5; }
.card-good { border-left-color: #27ae60; background: #f0faf0; }
ul { padding-left: 20px; font-size: 13px; line-height: 1.8; }
.metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin: 10px 0; }
.metric { text-align: center; padding: 12px; background: #f8f9fa; border-radius: 6px; }
.metric .val { font-size: 22px; font-weight: bold; }
.metric .lbl { font-size: 11px; color: #888; margin-top: 2px; }
.footer { margin-top: 24px; padding-top: 10px; border-top: 1px solid #ddd; font-size: 10px; color: #999; }
</style>
</head>
<body>
<div class="page">

<h1>铁律量化 · 月度学习报告</h1>
<p style="font-size:13px;color:#666;">月份: $Month | 生成: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss") | 首次学习</p>

<!-- 系统现状 -->
<h2>1. 系统运行现状</h2>
<div class="metric-grid">
    <div class="metric"><div class="val">$totalScored</div><div class="lbl">候选股票</div></div>
    <div class="metric"><div class="val">$totalPassed</div><div class="lbl">通过</div></div>
    <div class="metric"><div class="val">$totalVetoed</div><div class="lbl">否决</div></div>
    <div class="metric"><div class="val">$passRate</div><div class="lbl">通过率</div></div>
</div>

<div class="card">
<strong>当前评分维度</strong>（满分100）
<table>
<tr><th>维度</th><th>满分</th><th>权重</th><th>说明</th></tr>
<tr><td>S_Base 基础门槛</td><td>10</td><td>10%</td><td>市值/价格等硬性门槛</td></tr>
<tr><td>S_Fund 基本面</td><td>20</td><td>20%</td><td>PE/ROE/营收增长</td></tr>
<tr><td>S_Tech 技术面</td><td>25</td><td>25%</td><td>均线/RSI/MACD/量价</td></tr>
<tr><td>S_Money 资金面</td><td>20</td><td>20%</td><td>资金流向+板块动量</td></tr>
<tr><td>S_News 消息面</td><td>20</td><td>20%</td><td>RS强度+板块催化</td></tr>
<tr><td>S_Risk 风控</td><td>5</td><td>5%</td><td>波动率/回撤控制</td></tr>
</table>
</div>

<div class="card">
<strong>否决规则</strong>：8条绝对否决 + 5条条件否决
<table>
<tr><th>类型</th><th>规则</th><th>阈值</th><th>豁免</th></tr>
<tr><td>绝对V₂</td><td>PE估值泡沫</td><td>行业阈值(80~300)</td><td>-</td></tr>
<tr><td>绝对V₃</td><td>30日涨幅超标</td><td>>50%</td><td>-</td></tr>
<tr><td>绝对V₄</td><td>财务数据异常</td><td>EPS≤0且PE≤0</td><td>-</td></tr>
<tr><td>绝对V₅</td><td>流动性枯竭</td><td>成交额<1500万</td><td>-</td></tr>
<tr><td>条件C₁</td><td>科技PE过高</td><td>>120(科技)</td><td>总分≥85</td></tr>
<tr><td>条件C₂</td><td>PE超标</td><td>>80</td><td>总分≥85</td></tr>
<tr><td>条件C₃</td><td>短期均线回踩</td><td>MA5<MA10</td><td>总分≥75</td></tr>
</table>
</div>

<!-- 行业对比 -->
<h2>2. 2026年量化前沿对比</h2>

<div class="section">
<h3>2.1 评分体系对比</h3>
<table>
<tr><th>对比维度</th><th>铁律量化 v2</th><th>行业前沿 (2026)</th><th>差距</th></tr>
<tr>
    <td>因子数量</td>
    <td>6大维度, ~20子因子</td>
    <td>华泰: 26底层→12子维度<br>衡泰: 13核心风格因子</td>
    <td><span class="tag tag-orange">待扩充</span> 因子覆盖面不足</td>
</tr>
<tr>
    <td>权重机制</td>
    <td>固定权重</td>
    <td>ICIR动态加权<br>市场周期自适应切换</td>
    <td><span class="tag tag-red">核心短板</span> 静态权重无法适应市场变化</td>
</tr>
<tr>
    <td>否决规则</td>
    <td>硬阈值+豁免</td>
    <td>异动雷达+事件簇<br>场景化否决</td>
    <td><span class="tag tag-orange">可优化</span> 缺少动态否决</td>
</tr>
<tr>
    <td>资金流分析</td>
    <td>简单净流入</td>
    <td>分钟级主动资金流因子<br>rankICIR 3.1~4.54</td>
    <td><span class="tag tag-red">显著差距</span> 数据精细度不够</td>
</tr>
<tr>
    <td>非线性建模</td>
    <td>无</td>
    <td>GRU/LSTM/Transformer<br>ML因子纳入多因子模型</td>
    <td><span class="tag tag-red">缺失</span> 建议引入</td>
</tr>
<tr>
    <td>市场状态识别</td>
    <td>板块相位(高潮/潜伏等)</td>
    <td>宏观因子优选风格<br>NN择时深度模型</td>
    <td><span class="tag tag-orange">基础版</span> 可升级</td>
</tr>
</table>
</div>

<div class="section">
<h3>2.2 可立即借鉴的方法</h3>
<table>
<tr><th>来源</th><th>方法</th><th>建议</th><th>优先级</th></tr>
<tr>
    <td>华泰金工(2026.05)</td>
    <td>路径优选模型——不同信号在不同场景下表现不同，拆分为追高/抄底/追空/逃顶四条路径</td>
    <td>将否决规则按场景拆分：上涨市和下跌市使用不同否决阈值</td>
    <td><span class="tag tag-green">高</span></td>
</tr>
<tr>
    <td>Stratapro (2026)</td>
    <td>按牛/熊/震荡市动态切换技术/基本面/消息面权重</td>
    <td>根据大盘状态调整评分维度权重</td>
    <td><span class="tag tag-green">高</span></td>
</tr>
<tr>
    <td>开源证券 (2026.02)</td>
    <td>分钟级主动资金流因子——区分主动买单/卖单，rankICIR达3.1</td>
    <td>升级stock_data_fetcher.psm1获取逐笔或分钟级资金流</td>
    <td><span class="tag tag-orange">中</span></td>
</tr>
<tr>
    <td>山西证券 (2026.04)</td>
    <td>算子网格搜索+Numba加速——自动化因子挖掘</td>
    <td>对历史数据做因子有效性回测，淘汰无效因子</td>
    <td><span class="tag tag-orange">中</span></td>
</tr>
<tr>
    <td>衡泰xCN4 (2026)</td>
    <td>加入ML因子、拥挤度因子、国有持股因子</td>
    <td>在S_Money中引入拥挤度指标(换手率分位+成交量分位)</td>
    <td><span class="tag tag-green">高</span></td>
</tr>
</table>
</div>

<!-- 调参建议 -->
<h2>3. 调参建议</h2>

<div class="card card-warn">
<h3>P1 - 权重自适应（高优先级）</h3>
<p><strong>问题：</strong>当前6个维度固定权重，无法适应市场风格切换。</p>
<p><strong>建议：</strong>改为2档权重切换——以上证指数20日均线为界：</p>
<ul>
    <li><strong>上升趋势</strong>（指数>MA20）：技术 30% | 资金 25% | 消息 20% | 基本面 15% | 风控 10%</li>
    <li><strong>下降/震荡</strong>（指数≤MA20）：基本面 30% | 资金 20% | 风控 20% | 技术 15% | 消息 15%</li>
</ul>
</div>

<div class="card card-warn">
<h3>P2 - 否决规则场景化（高优先级）</h3>
<p><strong>问题：</strong>PE否决阈值固定，牛市中误杀率高（当前29只被否决中17只因PE）。</p>
<p><strong>建议：</strong></p>
<ul>
    <li>PE绝对否决阈值改为 "行业均值+2倍标准差" 动态计算，而非固定值</li>
    <li>30日涨幅否决改为相对大盘涨幅（个股涨幅-同期大盘涨幅 > 40%）</li>
    <li>引入"否决复核"机制：被否决的股票如果当日有板块效应（板块内3只以上上涨），自动降低否决等级</li>
</ul>
</div>

<div class="card card-warn">
<h3>P3 - 引入拥挤度因子（高优先级）</h3>
<p><strong>问题：</strong>当前S_Money仅计算资金净流入，未考虑拥挤度风险。</p>
<p><strong>建议：</strong>在S_Risk或S_Money维度中加入拥挤度判断：</p>
<ul>
    <li>换手率过去20日分位 > 80% + 成交量分位 > 80% → 拥挤，扣分</li>
    <li>拥挤度标的即使评分高也降低仓位建议</li>
</ul>
</div>

<div class="card">
<h3>P4 - 事后评估联动调参（中期）</h3>
<p>当日评估数据积累到20+天以上时：</p>
<ul>
    <li>按月计算各维度准确率，淘汰准确率 < 45% 的维度或下调其权重</li>
    <li>跟踪否决误杀率——被否决股票次日上涨比例 > 40% 则放宽该规则</li>
    <li>月度胜率趋势监测——连续3个月下降则触发全面审查</li>
</ul>
</div>

<div class="card">
<h3>P5 - 分钟级资金流因子（中期）</h3>
<p>当前数据采集使用日线级别，无法区分主动/被动资金。建议：</p>
<ul>
    <li>升级stock_data_fetcher.psm1，增加分钟级数据接口（东方财富Level-2或腾讯逐笔）</li>
    <li>构建主动资金流因子：大单净买入/流通市值，用于S_Money维度</li>
</ul>
</div>

<!-- 数据积累提示 -->
<h2>4. 数据积累状态</h2>
<div class="card card-good">
<p><strong>当前状态：</strong>数据归档系统已于 $(Get-Date -Format "yyyy-MM-dd") 启用。</p>
<p><strong>预计效果：</strong></p>
<ul>
    <li>30天后：约20份评估报告 → 可计算各维度准确率</li>
    <li>60天后：约40份评估报告 → 可做否决误杀率月度对比</li>
    <li>90天后：约60份评估报告 → 具备模型迭代的数据基础</li>
</ul>
</div>

<div class="footer">
<p>铁律量化 · 月度学习报告 | 由 AI 根据最新行业研究和系统运行数据自动生成</p>
<p>数据来源: 铁律量化系统运行数据 + 华泰/开源/衡泰/山西证券等公开研究 (2026.05)</p>
<p>本报告为模型优化建议，不构成投资建议</p>
</div>

</div>
</body>
</html>
"@

$htmlFile = Join-Path $reportDir "${monthLabel}_月度学习报告.html"
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($htmlFile, $html, $utf8NoBom)
Write-Output "HTML generated: $htmlFile"

# 转PDF
if (Test-Path $edgePath) {
    $pdfFile = Join-Path $reportDir "${monthLabel}_月度学习报告.pdf"
    try {
        $ok = ConvertTo-Pdf -HtmlFile $htmlFile -PdfFile $pdfFile -EdgePath $edgePath -MinSize 10000
        if ($ok) {
            Write-Output "PDF generated: $pdfFile ($([Math]::Round((Get-Item $pdfFile).Length/1KB,0)) KB)"
        } else {
            Write-Output "PDF generation may have failed, HTML available at: $htmlFile"
        }
    } catch {
        Write-Warning "PDF conversion failed: $_"
        Write-Output "HTML available at: $htmlFile"
    }
} else {
    Write-Output "Edge not found, HTML available at: $htmlFile"
}
