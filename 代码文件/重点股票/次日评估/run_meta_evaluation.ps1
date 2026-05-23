# 重点股票评估系统自检脚本 — 中循环
# 功能：评估系统自身的权重优化、信号管理、阈值校验、§6.8桥接扫描、失效归因、条件规则
# 触发条件：每20次后评估后触发（白皮书 v1.7 §7.1）
# 基于：重点股票次日后评估白皮书 v1.7 §7.2-§7.9

param(
    [switch]$GenerateReport = $true  # 是否生成PDF自检报告
)

# ============================================================
# 配置
# ============================================================
$rootDir = "C:\Users\34269\Documents\Claude\股票分析"
$evalRoot = Join-Path $rootDir "重点股票\次日评估"
$logicDir = Join-Path $evalRoot "逻辑积累"
$metaDir = Join-Path $logicDir "元评估"
$signalDiscoveryDir = Join-Path $logicDir "信号发现"
$reportDir = Join-Path $evalRoot "复盘报告"
$edgePath = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

$metaTrackFile = Join-Path $metaDir "评估系统有效性跟踪.csv"
$changeLogFile = Join-Path $metaDir "评估系统变更日志.md"
$candidateFile = Join-Path $signalDiscoveryDir "候选信号.json"
$retiredFile = Join-Path $signalDiscoveryDir "已淘汰信号.json"
$signalTrackFile = Join-Path $logicDir "指标有效性跟踪.csv"
$suggestFile = Join-Path $logicDir "优化建议.json"

$todayLabel = (Get-Date).ToString("yyyy-MM-dd")

Write-Host "============================================"
Write-Host "  评估系统自检 — 中循环"
Write-Host "  日期: $todayLabel"
Write-Host "============================================"

# ============================================================
# 1. 检查数据是否充足
# ============================================================
if (-not (Test-Path $metaTrackFile)) {
    Write-Warning "未找到元评估跟踪数据，请先运行至少1次后评估"
    exit 1
}
$metaData = Get-Content $metaTrackFile -Encoding UTF8 | ConvertFrom-Csv
$evalCount = $metaData.Count
Write-Host "`n累积评估次数: $evalCount"

if ($evalCount -lt 20) {
    Write-Host "评估次数不足20次，中循环需要至少20次数据才有效"
    Write-Host "当前$evalCount次，还需$(20 - $evalCount)次才能触发有意义的自检"
    exit 0
}

# ============================================================
# 2. 维度权重优化分析
# ============================================================
Write-Host "`n===== 1/3: 维度权重合理性分析 ====="

# 当前各维度得分
$dimScores = @()
$indicatorScores = @()
$thresholdScores = @()
$frameworkScores = @()
$compositeScores = @()

foreach ($row in $metaData) {
    $dimScores += [double]$row.维度有效性得分
    $indicatorScores += [double]$row.指标有效性得分
    $thresholdScores += [double]$row.阈值有效性得分
    $frameworkScores += [double]$row.框架一致性得分
    $compositeScores += [double]$row.综合评分
}

# 计算各维度得分方差（方差越大说明区分度越好）
function Get-Variance {
    param([double[]]$Values)
    if ($Values.Count -lt 2) { return 0 }
    $mean = ($Values | Measure-Object -Average).Average
    return ($Values | ForEach-Object { [Math]::Pow($_ - $mean, 2) } | Measure-Object -Average).Average
}

function Get-Mean {
    param([double[]]$Values)
    if ($Values.Count -eq 0) { return 0 }
    return ($Values | Measure-Object -Average).Average
}

$dimVar = Get-Variance $dimScores
$indVar = Get-Variance $indicatorScores
$thrVar = Get-Variance $thresholdScores
$fraVar = Get-Variance $frameworkScores

$dimMean = Get-Mean $dimScores
$indMean = Get-Mean $indicatorScores
$thrMean = Get-Mean $thresholdScores
$fraMean = Get-Mean $frameworkScores

Write-Host "  维度有效性: 均值=$([Math]::Round($dimMean,1)) 方差=$([Math]::Round($dimVar,1)) (权重30)"
Write-Host "  指标有效性: 均值=$([Math]::Round($indMean,1)) 方差=$([Math]::Round($indVar,1)) (权重30)"
Write-Host "  阈值有效性: 均值=$([Math]::Round($thrMean,1)) 方差=$([Math]::Round($thrVar,1)) (权重20)"
Write-Host "  框架一致性: 均值=$([Math]::Round($fraMean,1)) 方差=$([Math]::Round($fraVar,1)) (权重20)"

# 生成权重建议
$weightSuggestions = @()

# 如果方差太小（<1），说明该维度几乎每次都得同样分数，没有区分度
if ($thrVar -lt 1.0 -and $thrMean -gt 18) {
    $weightSuggestions += [PSCustomObject]@{
        项目="阈值有效性权重"; 当前权重=20; 问题="得分几乎没有波动(方差$([Math]::Round($thrVar,2)))，每次接近满分"
        建议="阈值设定可能过于宽松，建议收紧阈值标准使该维度产生区分度，或考虑降低权重"
    }
}

# 如果某维度均值得分显著低于其他维度，说明该维度评分标准过于严格
$allMeans = @($dimMean, $indMean, $thrMean, $fraMean)
$overallMean = ($allMeans | Measure-Object -Average).Average
foreach ($m in @(@{name="维度有效性";val=$dimMean;w=30},@{name="指标有效性";val=$indMean;w=30},@{name="阈值有效性";val=$thrMean;w=20},@{name="框架一致性";val=$fraMean;w=20})) {
    if ($m.val -lt $overallMean * 0.5 -and $m.val -ge 0) {
        $weightSuggestions += [PSCustomObject]@{
            项目="$($m.name)评分标准"; 当前权重=$m.w; 问题="均值得分($([Math]::Round($m.val,1)))显著低于整体均值($([Math]::Round($overallMean,1)))"
            建议="该维度评分标准可能过于严格，建议审视评分阈值"
        }
    }
}

if ($weightSuggestions.Count -eq 0) {
    Write-Host "  [OK] 当前权重配置合理，无需调整"
} else {
    Write-Host "  发现 $($weightSuggestions.Count) 条权重相关建议"
    foreach ($ws in $weightSuggestions) {
        Write-Host "    - $($ws.建议)"
    }
}

# ============================================================
# 3. 信号列表管理
# ============================================================
Write-Host "`n===== 2/3: 信号列表管理 ====="

$signalChanges = @()

# 检查候选信号
if (Test-Path $candidateFile) {
    $candidates = Get-Content $candidateFile -Raw -Encoding UTF8 | ConvertFrom-Json
    $readySignals = $candidates | Where-Object { [int]$_.样本数 -ge 10 -and [double]$_.胜率 -ge 60 }
    if ($readySignals) {
        foreach ($rs in $readySignals) {
            $signalChanges += [PSCustomObject]@{
                类型="加入"; 信号名称="$($rs.字段) = $($rs.信号值)"
                样本数=$rs.样本数; 胜率=$rs.胜率
                说明="胜率>=60%且样本>=10，建议加入跟踪列表"
            }
        }
    }
}

# 检查跟踪信号中胜率长期在40-60%的
if (Test-Path $signalTrackFile) {
    $trackedData = Get-Content $signalTrackFile -Encoding UTF8 | ConvertFrom-Csv
    $signalGroups = $trackedData | Group-Object 信号名称
    foreach ($sg in $signalGroups) {
        $recent = $sg.Group | Select-Object -Last 10
        $avgWinRate = ($recent | ForEach-Object { [double]$_.胜率 } | Measure-Object -Average).Average
        if ($sg.Count -ge 20 -and $avgWinRate -gt 40 -and $avgWinRate -lt 60) {
            $signalChanges += [PSCustomObject]@{
                类型="淘汰"; 信号名称=$sg.Name
                样本数=$sg.Count; 胜率=[Math]::Round($avgWinRate,1)
                说明="长期在40-60%区间徘徊，无预测价值"
            }
        }
    }
}

if ($signalChanges.Count -eq 0) {
    Write-Host "  信号列表当前稳定，无增删建议"
} else {
    foreach ($sc in $signalChanges) {
        $tag = if ($sc.类型 -eq "加入") { "建议加入" } else { "建议淘汰" }
        Write-Host "  ${tag}: $($sc.信号名称) (胜率$($sc.胜率)%, $($sc.样本数)次) - $($sc.说明)"
    }
}

# ============================================================
# 4. 评估阈值校验（需要>=50样本，否则暂略）
# ============================================================
Write-Host "`n===== 3/3: 评估阈值校验 ====="

if ($evalCount -ge 50) {
    Write-Host "  样本充足($evalCount)，可以进行阈值校验"
    # 分析各r值阈值是否合理
    $rThresholds = @(0, 0.15, 0.3)
    $rDistribution = @($dimScores | Where-Object { $_ -eq 0 }).Count
    Write-Host "  维度得分为0的次数: $rDistribution/$evalCount"
    # 此处可根据实际分布输出阈值调整建议
} else {
    Write-Host "  样本不足($evalCount<50)，暂无法进行阈值校验"
}

# ============================================================
# 5. 生成自检报告
# ============================================================
Write-Host "`n===== 生成自检报告 ====="

$reportContent = @"
# 评估系统自检报告

**生成日期**: $todayLabel
**累积评估次数**: $evalCount
**触发方式**: 中循环（每20次评估）

---

## 一、维度权重分析

| 维度 | 均值 | 方差 | 当前权重 | 建议 |
|:----|:----|:----|:--------|:----|
"@

# 继续添加表格行
foreach ($m in @(
    @{name="维度有效性";mean=$dimMean;var=$dimVar;w=30;note=if($dimVar -lt 1){"区分度不足"}else{"正常"}},
    @{name="指标有效性";mean=$indMean;var=$indVar;w=30;note=if($indVar -lt 1){"区分度不足"}else{"正常"}},
    @{name="阈值有效性";mean=$thrMean;var=$thrVar;w=20;note=if($thrVar -lt 1){"区分度不足"}else{"正常"}},
    @{name="框架一致性";mean=$fraMean;var=$fraVar;w=20;note=if($fraVar -lt 1){"区分度不足"}else{"正常"}}
)) {
    $reportContent += "`n| $($m.name) | $([Math]::Round($m.mean,1)) | $([Math]::Round($m.var,1)) | $($m.w) | $($m.note) |"
}

$reportContent += @"


## 二、信号管理建议

"

if ($signalChanges.Count -gt 0) {
    foreach ($sc in $signalChanges) {
        $reportContent += "- **[$($sc.类型)]** $($sc.信号名称) -- $($sc.说明)`n"
    }
} else {
    $reportContent += "当前信号列表稳定，无增删建议。`n"
}

$reportContent += @"


## 三、总结与建议

**整体评估**: 评估系统运行 $(if($weightSuggestions.Count -eq 0 -and $signalChanges.Count -eq 0){"正常"}else{"需要关注"})
**权重优化**: $(if($weightSuggestions.Count -eq 0){"无需调整"}else{"$($weightSuggestions.Count)条建议"})
**信号管理**: $(if($signalChanges.Count -eq 0){"无变更"}else{"$($signalChanges.Count)条建议"})

**后续动作**: 请人工确认以上建议后，更新白皮书版本。

---

*本报告由 run_meta_evaluation.ps1 自动生成，仅提供建议，不做自动修改。*
"@

# 保存为Markdown
$reportMd = Join-Path $reportDir "评估系统自检报告_$(Get-Date -Format 'yyyyMMdd').md"
$reportContent | Set-Content $reportMd -Encoding UTF8
Write-Host "  自检报告: $reportMd"

# 更新评估系统变更日志
$changelogEntry = @"

### ${todayLabel}: 中循环自检（第${evalCount}次评估后）

**权重分析**:
$(if($weightSuggestions.Count -eq 0){'- 当前权重配置合理，无需调整'}else{foreach($ws in $weightSuggestions){"- $($ws.建议)`n"}})

**信号管理**:
$(if($signalChanges.Count -eq 0){'- 信号列表稳定，无增删建议'}else{foreach($sc in $signalChanges){"- [$($sc.类型)] $($sc.信号名称)`n"}})

**状态**: 待人工确认

---
"@
Add-Content $changeLogFile -Encoding UTF8 -Value $changelogEntry
Write-Host "  变更日志已更新: $changeLogFile"

# ============================================================
# Summary
# ============================================================
Write-Host "`n============================================"
Write-Host "  评估系统自检完成"
Write-Host "  累积评估: $evalCount 次"
Write-Host "  权重建议: $($weightSuggestions.Count) 条"
Write-Host "  信号建议: $($signalChanges.Count) 条"
Write-Host "  报告: $reportMd"
Write-Host "============================================"
