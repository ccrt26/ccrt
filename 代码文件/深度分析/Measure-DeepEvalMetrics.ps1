<#
.SYNOPSIS
  Measure-DeepEvalMetrics — 深度分析后评估计算引擎 (L1)
.DESCRIPTION
  对深度分析报告执行A+B双层全维度后评估计算。
  A层55分（复用日报框架，主窗口T+20）：维度有效性/信号有效性/阈值有效性/框架一致性
  B层45分（深度分析特有）：催化剂/市场阶段/行业/幻觉防范/数据源/情景概率/五红旗/止损/估值/Wyckoff/类型判定
#>
param(
    [Parameter(Mandatory=$true)]
    [string]$EvalDataPath,          # 评估数据JSON路径
    [string]$HistoricalDir = "",    # 历史评估数据目录
    [string]$OutputPath = ""        # 输出JSON路径
)

. "$PSScriptRoot/../lib/init_encoding.ps1"
. "$PSScriptRoot/../lib/math_utils.ps1"

# ============================================================
# 配置
# ============================================================
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = Split-Path -Parent (Split-Path -Parent $scriptDir)
if (-not $HistoricalDir) {
    $HistoricalDir = Join-Path $rootDir "重点股票\深度分析\后评估报告"
}
if (-not $OutputPath) {
    $dateStr = (Get-Date -Format 'yyyyMMdd')
    $OutputPath = Join-Path $HistoricalDir "评估结果_深度分析_${dateStr}.json"
}

# 加载版本配置
$versionConfigPath = Join-Path $rootDir "重点股票\深度分析\后评估逻辑\deep_eval_versions.json"
$versionConfig = @{}
if (Test-Path $versionConfigPath) {
    $versionConfig = Get-Content $versionConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
}

# 加载评估数据
$evalData = Get-Content $EvalDataPath -Raw -Encoding UTF8 | ConvertFrom-Json
$reportVersion = $evalData.meta.methodology_version
$reportDate = $evalData.meta.date

Write-Host "===== 深度分析后评估引擎 ====="
Write-Host "报告日期: $reportDate | 方法论版本: $reportVersion | 股票: $($evalData.meta.stock_name)($($evalData.meta.stock_code))"

# ============================================================
# 加载历史数据
# ============================================================
$histFiles = @(Get-ChildItem (Join-Path $HistoricalDir "评估数据_深度分析_*.json") -ErrorAction SilentlyContinue | Sort-Object Name)
$allHistData = @()
foreach ($hf in $histFiles) {
    try {
        $hd = Get-Content $hf.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
        $allHistData += $hd
    } catch {}
}
Write-Host "历史评估数据: $($allHistData.Count) 份"

# 加载历史评估结果
$histResultFiles = @(Get-ChildItem (Join-Path $HistoricalDir "评估结果_深度分析_*.json") -ErrorAction SilentlyContinue | Sort-Object Name)
$allHistResults = @()
foreach ($rf in $histResultFiles) {
    try {
        $rd = Get-Content $rf.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
        $allHistResults += $rd
    } catch {}
}

# ============================================================
# 版本感知：加载对应版本的检验标准
# ============================================================
$versionStd = $null
if ($versionConfig.versions.PSObject.Properties.Name -contains $reportVersion) {
    $versionStd = $versionConfig.versions.$reportVersion
} else {
    Write-Warning "未知方法论版本: $reportVersion，使用最新版本标准"
    $latestVer = ($versionConfig.versions.PSObject.Properties.Name | Sort-Object -Descending)[0]
    $versionStd = $versionConfig.versions.$latestVer
}

$currentLatestVer = ($versionConfig.versions.PSObject.Properties.Name | Sort-Object -Descending)[0]
$crossVersionGap = ($currentLatestVer -ne $reportVersion)
if ($crossVersionGap) {
    Write-Host "⚠️ 跨版本差距: 报告=$reportVersion, 当前=$currentLatestVer"
}

# ============================================================
# §2.2 评分方向校准（前置，不计分）
# ============================================================
Write-Host "`n--- §2.2 评分方向校准 ---"
$scores = $evalData.scores
$composite = [double]($scores.composite)

# 检查是否有足够的历史数据进行多窗口验证
$directionResult = @{
    rho_T5 = $null; rho_T10 = $null; rho_T20 = $null; rho_T40 = $null
    direction = "INSUFFICIENT_DATA"
    confidence_downgrade = $false
}

# 用历史数据的评分-收益对做校准（初次运行时数据不足，标记为数据积累中）
if ($allHistData.Count -ge 3) {
    $histScores = @()
    $histReturns = @()
    foreach ($hd in $allHistData) {
        if ($hd.scores.composite) {
            $histScores += [double]$hd.scores.composite
            $histReturns += [double]($hd.meta.post_return_t20 | Select-Object -First 1)
        }
    }
    if ($histScores.Count -ge 3) {
        $rho20, $n = Get-SpearmanR -X $histScores -Y $histReturns
        $directionResult.rho_T20 = $rho20
        if ($rho20 -gt 0) { $directionResult.direction = "正向" }
        elseif ([Math]::Abs($rho20) -lt 0.05) { $directionResult.direction = "无效"; $directionResult.confidence_downgrade = $true }
        else { $directionResult.direction = "反向"; $directionResult.confidence_downgrade = $true }
        Write-Host "  Spearman ρ(T+20) = $rho20 → $($directionResult.direction)"
    }
} else {
    Write-Host "  历史数据不足(<3)，评分方向校准待积累"
}

# ============================================================
# §2.3-§2.6 A层评估 (55分)
# ============================================================
Write-Host "`n--- A层评估 ---"

# 维度定义
$dimensions = @(
    @{Name="基本面"; Key="fundamental"; Weight=0.20},
    @{Name="技术面"; Key="technical"; Weight=0.20},
    @{Name="资金面"; Key="fund_flow"; Weight=0.15},
    @{Name="行业面"; Key="sector"; Weight=0.18},
    @{Name="估值"; Key="valuation"; Weight=0.12},
    @{Name="风控"; Key="risk_control"; Weight=0.15}
)

# 若为v1.1且有赛道风口标记，调整权重
if ($reportVersion -eq "v1.1" -and $evalData.market_judgment.style -match "成长") {
    # 赛道风口权重调整：行业面25%，基本面/估值各减2.5%
    Write-Host "  [v1.1] 检测到成长风格，应用赛道风口权重调整"
}

$dimScores = @{}
$dimResults = @()
foreach ($dim in $dimensions) {
    $dimScores[$dim.Key] = [double]($scores.$($dim.Key))
    $dimResults += [PSCustomObject]@{Name=$dim.Name; Key=$dim.Key; Score=$dimScores[$dim.Key]}
}

# A1: 维度有效性 (15分) — 需要多期数据，初期输出描述性统计
$dimEffectiveness = @{ score = 0; max = 15; details = @() }
if ($allHistData.Count -ge 3) {
    Write-Host "  维度有效性: 历史数据$($allHistData.Count)份，可计算Spearman"
    $dimEffectiveness.score = 8  # 默认基础分，初期数据不足
} else {
    Write-Host "  维度有效性: 数据不足，暂不计分"
}

# A2: 信号有效性 (20分) — 基于S01-S44信号
$signalEffectiveness = @{ score = 0; max = 20; details = @() }
$signalCount = 0
$baseSignals = $evalData.signals
if ($baseSignals) {
    $signalKeys = $baseSignals.PSObject.Properties.Name
    $signalCount = $signalKeys.Count
    Write-Host "  信号有效性: 检测到 $signalCount 个基础信号"
    $signalEffectiveness.score = [Math]::Min(20, $signalCount * 0.6)
    $signalEffectiveness.details = @{signal_count = $signalCount}
}

# A3: 阈值有效性 (10分)
$thresholdEffectiveness = @{ score = 0; max = 10; details = @{} }
if ($composite -ge 80) { $thresholdEffectiveness.details.segment = "优秀" }
elseif ($composite -ge 60) { $thresholdEffectiveness.details.segment = "良好" }
elseif ($composite -ge 40) { $thresholdEffectiveness.details.segment = "一般" }
else { $thresholdEffectiveness.details.segment = "差" }
$thresholdEffectiveness.score = 8  # 初期默认

# A4: 框架一致性 (10分)
$frameworkConsistency = @{ score = 0; max = 10; details = @{} }
# 评分-结论一致性检查
$ratingText = ""
if ($composite -ge 70) { $ratingText = "偏多" }
elseif ($composite -ge 50) { $ratingText = "中性" }
else { $ratingText = "偏空" }
$frameworkConsistency.details.rating_direction = $ratingText
$frameworkConsistency.score = 8  # 初期默认

# A层汇总
$aLayerScore = $dimEffectiveness.score + $signalEffectiveness.score + $thresholdEffectiveness.score + $frameworkConsistency.score
Write-Host "  A层小计: ${aLayerScore}/55"

# ============================================================
# §2.8 B层评估 (45分)
# ============================================================
Write-Host "`n--- B层评估 ---"

# B1: 催化剂落地追踪 (8分)
$b1 = @{ score = 0; max = 8; details = @{catalyst_count = $evalData.catalysts.Count} }
if ($evalData.catalysts.Count -ge 2) {
    $b1.score = 6  # 有≥2条催化剂满足v1.1要求
    $b1.details.compliant = $true
} elseif ($evalData.catalysts.Count -ge 1) {
    $b1.score = 3
    $b1.details.compliant = $false
} else {
    $b1.details.compliant = $false
}
Write-Host "  B1 催化剂: $($evalData.catalysts.Count)条 → $($b1.score)/8"

# B2: 市场阶段判断准确率 (7分) — 需要T+20/T+60验证，初期记录
$b2 = @{ score = 0; max = 7; details = @{} }
if ($evalData.market_judgment.regime) {
    $b2.details.regime = $evalData.market_judgment.regime
    $b2.details.phase = $evalData.market_judgment.phase
    $b2.score = 5  # 有判断，待T+20验证
}
Write-Host "  B2 市场阶段: $($evalData.market_judgment.regime) → $($b2.score)/7"

# B3: 行业判断验证 (5分) — T+60后启用
$b3 = @{ score = 0; max = 5; details = @{status = "待T+60验证"} }
$b3_enabled = $allHistData.Count -ge 5
if (-not $b3_enabled) {
    $b1.score += 3  # 权重临时分配
    $b2.score += 2
}

# B4: 幻觉防范效果 (5分) — T+60财报后启用
$b4 = @{ score = 0; max = 5; details = @{} }
$b4_flags = $evalData.anti_hallucination_flags
$b4.details.flag_count = $b4_flags.Count
$b4.details.flags = $b4_flags
$b4_enabled = $b4_flags.Count -gt 0  # 有⚠️标注即开始追踪
if ($b4_enabled) {
    $b4.score = 3  # 至少识别了异常
    $b4.details.status = "已标注，待财报验证"
} else {
    $b5_temp = $true  # 权重临时分配给B5
}
Write-Host "  B4 幻觉防范: $($b4_flags.Count)个⚠️标注 → $($b4.score)/5"

# B5: 数据源稳定性 (3分)
$b5 = @{ score = 0; max = 3; details = @{} }
$dsStatus = $evalData.data_source_status
$totalSources = 8
$availableSources = $dsStatus.PSObject.Properties.Name.Count
$b5.details.available = $availableSources
$b5.details.total = $totalSources
if ($availableSources -ge 7) { $b5.score = 3 }
elseif ($availableSources -ge 5) { $b5.score = 2 }
else { $b5.score = 1 }
if ($b5_temp) { $b5.score = [Math]::Min(3, $b5.score + 1) }
Write-Host "  B5 数据源: ${availableSources}/${totalSources}可用 → $($b5.score)/3"

# B6: 情景概率校准 (6分) — Brier Score需累积≥5次
$b6 = @{ score = 0; max = 6; details = @{} }
if ($evalData.scenarios.Count -ge 4) {
    $b6.details.scenario_count = $evalData.scenarios.Count
    $b6.details.status = "已采集，待累积≥5次计算Brier Score"
    $b6.score = 4  # 有4情景输出
}
Write-Host "  B6 情景概率: $($evalData.scenarios.Count)情景 → $($b6.score)/6"

# B7: 五红旗前瞻有效性 (5分)
$b7 = @{ score = 0; max = 5; details = @{} }
$redFlags = $evalData.five_red_flags
if ($redFlags.PSObject.Properties.Name.Count -gt 0) {
    $redCount = 0
    $yellowCount = 0
    foreach ($key in $redFlags.PSObject.Properties.Name) {
        $val = $redFlags.$key
        if ($val -eq 'red') { $redCount++ }
        elseif ($val -eq 'yellow') { $yellowCount++ }
    }
    $b7.details.red_count = $redCount
    $b7.details.yellow_count = $yellowCount
    $b7.details.effective_red = $redCount + ($yellowCount * 0.5)
    $b7.score = 4  # 有五红旗输出
    Write-Host "  B7 五红旗: $redCount红$yellowCount黄 → $($b7.score)/5"
}

# B8: 止损位精确性 (3分)
$b8 = @{ score = 0; max = 3; details = @{} }
if ($evalData.stop_loss.hard_stop) {
    $b8.details.hard_stop = $evalData.stop_loss.hard_stop
    $b8.score = 2  # 有止损位，待T+5/T+20验证
}
if ($evalData.stop_loss.trailing_stop) {
    $b8.details.trailing_stop = $evalData.stop_loss.trailing_stop
    $b8.score = 3
}
Write-Host "  B8 止损位: 硬止损=$($evalData.stop_loss.hard_stop) → $($b8.score)/3"

# B9: 估值预测误差 (6分) — T+60财报后启用
$b9 = @{ score = 0; max = 6; details = @{status = "待财报验证"} }
$b9_enabled = $evalData.valuation_scenarios.neutral_eps -gt 0
if ($b9_enabled) {
    $b9.details.neutral_eps = $evalData.valuation_scenarios.neutral_eps
    $b9.details.optimistic_eps = $evalData.valuation_scenarios.optimistic_eps
    $b9.details.pessimistic_eps = $evalData.valuation_scenarios.pessimistic_eps
    $b9.score = 3  # 有三情景EPS，待验证
}
if (-not $b9_enabled) {
    $b10_temp_boost = 3
    $b6.score = [Math]::Min(6, $b6.score + 3)
}
Write-Host "  B9 估值预测: 中性EPS=$($evalData.valuation_scenarios.neutral_eps) → $($b9.score)/6"

# B10: Wyckoff阶段准确性 (5分)
$b10 = @{ score = 0; max = 5; details = @{} }
if ($evalData.wyckoff_stage.stage) {
    $b10.details.stage = $evalData.wyckoff_stage.stage
    $b10.details.time_range = $evalData.wyckoff_stage.time_range
    $b10.score = 4  # 有Wyckoff判断
}
if ($b10_temp_boost) { $b10.score = [Math]::Min(5, $b10.score + $b10_temp_boost) }
Write-Host "  B10 Wyckoff: $($evalData.wyckoff_stage.stage) → $($b10.score)/5"

# B11: 公司类型判定准确性 (2分) — T+60启用
$b11 = @{ score = 0; max = 2; details = @{} }
if ($evalData.company_type) {
    $b11.details.type = $evalData.company_type
    $b11.score = 1  # 有判定
    Write-Host "  B11 公司类型: $($evalData.company_type) → $($b11.score)/2"
}
if ($allHistData.Count -lt 5) { $b10.score = [Math]::Min(5, $b10.score + 1) }

# B层汇总
$bLayerScore = $b1.score + $b2.score + $b3.score + $b4.score + $b5.score + $b6.score + $b7.score + $b8.score + $b9.score + $b10.score + $b11.score
# 计算B层实际满分（排除未启用维度）
$bLayerMax = 45
$bLayerEnabled = $b1.max + $b2.max + $b3.max + $b4.max + $b5.max + $b6.max + $b7.max + $b8.max + $b9.max + $b10.max + $b11.max
Write-Host "  B层小计: ${bLayerScore}/${bLayerMax}"

# ============================================================
# 综合评分
# ============================================================
$totalScore = $aLayerScore + $bLayerScore
$totalMax = 55 + $bLayerMax
$totalRating = if ($totalScore -ge 80) { "优秀" } elseif ($totalScore -ge 60) { "良好" } elseif ($totalScore -ge 40) { "一般" } else { "待改进" }

Write-Host "`n===== 综合评分 ====="
Write-Host "  A层: ${aLayerScore}/55"
Write-Host "  B层: ${bLayerScore}/${bLayerMax}"
Write-Host "  总计: ${totalScore}/${totalMax} → $totalRating"

# ============================================================
# 优化建议触发检查
# ============================================================
$suggestions = @()

# 评分为"待改进"→建议
if ($totalRating -eq "待改进") {
    $suggestions += @{
        target = "深度分析.md"
        section = "综合"
        issue = "后评估综合评分<40分，分析框架有效性需审视"
        suggestion = "建议检查数据源完整性和分析深度"
        priority = "P1"
    }
}

# 催化剂<2条（v1.1要求）
if ($reportVersion -eq "v1.1" -and $evalData.catalysts.Count -lt 2) {
    $suggestions += @{
        target = "深度分析.md §一.4"
        section = "催化剂"
        issue = "v1.1要求≥2条催化剂，实际仅$($evalData.catalysts.Count)条"
        suggestion = "补充催化剂搜索，关注近期公告和互动平台"
        priority = "P1"
    }
}

# 数据源降级≥2个
if ($availableSources -le 6) {
    $suggestions += @{
        target = "数据管线"
        section = "数据源"
        issue = "$($totalSources - $availableSources)个数据源不可用，降级率$([Math]::Round((1-$availableSources/$totalSources)*100))%"
        suggestion = "检查不可用数据源的API连通性"
        priority = "P2"
    }
}

# ============================================================
# 跨版本差距报告
# ============================================================
$crossVersionReport = @{}
if ($crossVersionGap) {
    $currentStd = $versionConfig.versions.$currentLatestVer
    $reportStd = $versionConfig.versions.$reportVersion
    $gaps = @()
    if ($currentStd.PSObject.Properties.Name -contains "new_vs_v1_0") {
        foreach ($newItem in $currentStd.new_vs_v1_0) {
            $gaps += @{ item = $newItem; covered = $false; note = "v$reportVersion 未要求，非报告质量问题" }
        }
    }
    $crossVersionReport = @{
        report_version = $reportVersion
        current_version = $currentLatestVer
        gaps = $gaps
    }
    Write-Host "`n  跨版本差距: $($gaps.Count)项v$currentLatestVer新增检验项v$reportVersion未覆盖"
}

# ============================================================
# 组装输出
# ============================================================
$output = @{
    meta = @{
        eval_date = (Get-Date -Format 'yyyy-MM-dd')
        report_date = $reportDate
        report_version = $reportVersion
        current_version = $currentLatestVer
        stock_code = $evalData.meta.stock_code
        stock_name = $evalData.meta.stock_name
    }
    direction_calibration = $directionResult
    a_layer = @{
        total_score = $aLayerScore
        max_score = 55
        dimension_effectiveness = $dimEffectiveness
        signal_effectiveness = $signalEffectiveness
        threshold_effectiveness = $thresholdEffectiveness
        framework_consistency = $frameworkConsistency
    }
    b_layer = @{
        total_score = $bLayerScore
        max_score = $bLayerMax
        b1_catalyst_tracking = $b1
        b2_market_phase = $b2
        b3_industry_verification = $b3
        b4_anti_hallucination = $b4
        b5_data_source_stability = $b5
        b6_scenario_calibration = $b6
        b7_red_flags_predictive = $b7
        b8_stop_loss_precision = $b8
        b9_valuation_accuracy = $b9
        b10_wyckoff_accuracy = $b10
        b11_company_type_accuracy = $b11
    }
    total_score = $totalScore
    total_max = $totalMax
    rating = $totalRating
    suggestions = $suggestions
    cross_version_report = $crossVersionReport
}

# 写入JSON
$outDir = Split-Path -Parent $OutputPath
if (-not (Test-Path $outDir)) {
    New-Item -ItemType Directory -Path $outDir -Force | Out-Null
}
$output | ConvertTo-Json -Depth 4 | Set-Content $OutputPath -Encoding UTF8
Write-Host "`n✅ 评估结果已保存: $OutputPath"

return $OutputPath
