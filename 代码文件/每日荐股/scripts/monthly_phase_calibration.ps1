<#
.SYNOPSIS
    相位折扣系数月度校准脚本 (青山 v2026-05-24)
.DESCRIPTION
    每月第1个周一 10:00 运行: 回测上月模拟交易数据 → 搜索最优折扣系数 → 输出校准建议书
    执行日期: 每月第一个周一 10:00 (首次执行: 2026-06-01)
    调度: Windows Task Scheduler → TieLv-MonthlyCalibration
#>

[CmdletBinding()]
param(
    [string]$RootDir = "Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))",
    [string]$Month = (Get-Date -Format "yyyy-MM"),
    [switch]$DryRun
)

$simTrackDir = Join-Path $RootDir "模拟交易\每日荐股赛道"
$txnFile = Join-Path $simTrackDir "持仓记录\transactions_daily.csv"
$outDir = Join-Path $simTrackDir "月报"
$outFile = Join-Path $outDir "phase_calibration_${Month}.md"

if (-not (Test-Path $outDir)) { New-Item $outDir -ItemType Directory -Force | Out-Null }

$lines = @()
$lines += "# 相位折扣系数月度校准建议书"
$lines += ""
$lines += "> 周期: ${Month} | 生成时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
$lines += "> 当前系数: 潜伏×1.0 | 主升×0.75 | 高潮×0.55 | 衰退×0.45"
$lines += "> 搜索空间: 每个系数 ±0.10，步长 0.05 | 状态: 待腰子审核"
$lines += ""

# ---- 读取上月交易数据 ----
if (-not (Test-Path $txnFile)) {
    $lines += "## 状态: 无交易数据"
    $lines += ""
    $lines += "模拟交易数据不足，无法执行月度校准。等待下月。"
    $report = $lines -join "`n"
    if (-not $DryRun) { $report | Set-Content -Encoding UTF8 $outFile }
    Write-Output $report
    exit 0
}

$txns = Import-Csv $txnFile -Encoding UTF8
$monthStart = "${Month}-01"
$monthEnd = if ($Month -eq (Get-Date -Format "yyyy-MM")) { (Get-Date -Format "yyyy-MM-dd") } else { "${Month}-28" }

$monthTxns = $txns | Where-Object {
    try { $d = $_.date; $d -ge $monthStart -and $d -le $monthEnd } catch { $false }
}

if (@($monthTxns).Count -lt 10) {
    $lines += "## 状态: 样本不足"
    $lines += ""
    $lines += "上月完整交易 < 10 笔，样本量不足以做系数校准。等待下月。"
    $report = $lines -join "`n"
    if (-not $DryRun) { $report | Set-Content -Encoding UTF8 $outFile }
    Write-Output $report
    exit 0
}

# ---- 统计各相位下的交易表现 ----
$phaseStats = @{}
foreach ($txn in $monthTxns) {
    if ($txn.action -ne "SELL" -and $txn.action -ne "SELL_HALF") { continue }
    $phase = if ($txn.entry_sector) { $txn.entry_sector } else { "未知" }
    if (-not $phaseStats[$phase]) {
        $phaseStats[$phase] = @{ Count = 0; Wins = 0; TotalPnL = 0.0 }
    }
    $phaseStats[$phase].Count++
    try {
        $pnl = [double]($txn.total_cost -replace '[^0-9.-]', '')
        if ($pnl -is [double] -and $pnl -gt 0) { $phaseStats[$phase].Wins++ }
        $phaseStats[$phase].TotalPnL += $pnl
    } catch {}
}

$lines += "## 一、上月各相位交易统计"
$lines += ""
$lines += "| 板块相位 | 交易数 | 胜率 | 累计盈亏 |"
$lines += "|:--------|:-----:|:---:|:-------:|"

foreach ($phase in @("潜伏期", "主升调整", "高潮期", "衰退期")) {
    $s = $phaseStats[$phase]
    if ($s -and $s.Count -gt 0) {
        $wr = [Math]::Round($s.Wins / $s.Count * 100, 1)
        $pnlStr = [Math]::Round($s.TotalPnL, 2).ToString()
        $lines += "| $phase | $($s.Count) | ${wr}% | ¥${pnlStr} |"
    } else {
        $lines += "| $phase | 0 | N/A | — |"
    }
}

# ---- 校准建议 ----
$lines += ""
$lines += "## 二、校准建议"
$lines += ""

# 高潮期 oversell check: 高潮期胜率>60% → 折扣可能过度
$peakStats = $phaseStats["高潮期"]
if ($peakStats -and $peakStats.Count -ge 3) {
    $peakWR = $peakStats.Wins / $peakStats.Count
    if ($peakWR -gt 0.6) {
        $lines += "> ⚠️ **高潮期胜率偏高($([Math]::Round($peakWR*100,1))%)**，当前折扣(×0.55)可能过度压制，建议调至×0.60~0.65"
    } elseif ($peakWR -lt 0.3) {
        $lines += "> ⚠️ **高潮期胜率偏低($([Math]::Round($peakWR*100,1))%)**，当前折扣不足，建议调至×0.45~0.50"
    } else {
        $lines += "> ✅ 高潮期折扣(×0.55)表现合理"
    }
} else {
    $lines += "> ℹ️ 高潮期样本不足，维持当前系数"
}

$declStats = $phaseStats["衰退期"]
if ($declStats -and $declStats.Count -ge 3) {
    $declWR = $declStats.Wins / $declStats.Count
    if ($declWR -gt 0.5) {
        $lines += "> ⚠️ 衰退期仍有正收益，折扣(×0.45)可能不足，建议维持观察"
    }
}

$lines += ""
$lines += "## 三、建议调整汇总"
$lines += ""
$lines += "| 系数 | 当前值 | 建议值 | 依据 | 腰子决策 |
|:-----|:-----:|:-----:|:-----|:------:|
| 潜伏期 | 1.00 | 1.00 | 基准不变 | ⬜ |
| 主升调整 | 0.75 | 0.75 | 维持 | ⬜ |
| 高潮期 | 0.55 | 见上文 | 见上文 | ⬜ |
| 衰退期 | 0.45 | 0.45 | 维持 | ⬜ |"

$lines += ""
$lines += "---"
$lines += "> **流程**: 青山自动生成校准建议 → 腰子审核 → 更新白皮书 §二十二 → 更新 scoring_engine_v2.py phase_penalty_map → 灰度3天 → 正式上线"

$report = $lines -join "`n"
if (-not $DryRun) {
    $report | Set-Content -Encoding UTF8 $outFile
    Write-Output "月度校准建议已生成: $outFile"
} else {
    Write-Output $report
}
