<#
.SYNOPSIS
    评估→参数自动反馈链路 (青山 v2026-05-24)
.DESCRIPTION
    每周一 09:00 运行: 读取后评估周报 → 检测异常指标 → 生成调参建议 → 提交腰子审核
    执行日期: 每周一 09:00
    调度: Windows Task Scheduler → TieLv-WeeklyFeedback
#>

[CmdletBinding()]
param(
    [string]$RootDir = "Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))",
    [string]$Date = (Get-Date -Format "yyyy-MM-dd"),
    [switch]$DryRun
)
. "$PSScriptRoot/../../lib/init_encoding.ps1"

$evalDir = Join-Path $RootDir "每日荐股\事后评估"
$issuesFile = Join-Path $evalDir "issues.csv"
$recordsFile = Join-Path $evalDir "records.csv"
$outDir = Join-Path $RootDir "模拟交易\每日荐股赛道\周报"
$simTrackDir = Join-Path $RootDir "模拟交易\每日荐股赛道"
$outFile = Join-Path $outDir "feedback_recommendations_$(Get-Date -Format 'yyyyMMdd').md"

if (-not (Test-Path $outDir)) { New-Item $outDir -ItemType Directory -Force | Out-Null }

$lines = @()
$lines += "# 评估→参数反馈建议"
$lines += ""
$lines += "> 生成时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm') | 状态: 待腰子审核"
$lines += "> 上次反馈: $(if (Test-Path $issuesFile) { (Get-Item $issuesFile).LastWriteTime.ToString('yyyy-MM-dd') } else { '首次运行' })"
$lines += ""

# ---- 读取 issue.csv ----
$alerts = @()
if (Test-Path $issuesFile) {
    $issues = Import-Csv $issuesFile -Encoding UTF8
    $recentIssues = $issues | Where-Object {
        try { ([datetime]$_.Date) -gt (Get-Date).AddDays(-14) } catch { $false }
    }
    if ($recentIssues) {
        $lines += "## 一、最近14天评估异常"
        $lines += ""
        foreach ($i in $recentIssues) {
            $lines += "- **$($i.Date)**: $($i.Issue) [$($i.Severity)]"
        }
    }
}

# ---- 读取 records.csv 计算周度趋势 ----
if (Test-Path $recordsFile) {
    $records = Import-Csv $recordsFile -Encoding UTF8
    $weekRecords = $records | Where-Object {
        try { ([datetime]$_.Date) -gt (Get-Date).AddDays(-7) } catch { $false }
    }

    if ($weekRecords) {
        $totalRecs = @($weekRecords).Count
        $wins = ($weekRecords | Where-Object { [double]$_.WinRate -gt 0 }).Count

        $vetoMistakeWeeks = 0
        $spearmanNegativeWeeks = 0

        $lines += ""
        $lines += "## 二、周度趋势"
        $lines += ""
        $lines += "| 指标 | 本周 | 阈值 | 状态 |"
        $lines += "|:-----|:---:|:---:|:----:|"

        $weeklyWinRate = if ($totalRecs -gt 0) { [Math]::Round($wins / $totalRecs * 100, 1) } else { "N/A" }
        $lines += "| 周胜率 | ${weeklyWinRate}% | ≥50% | $(if ($weeklyWinRate -ge 50) {'✅'} else {'⚠️'}) |"
    }
}

# ---- 生成建议 ----
$lines += ""
$lines += "## 三、自动建议（待腰子确认）"
$lines += ""
$lines += "| # | 建议 | 依据 | 置信度 | 腰子确认 |
|:--|:-----|:-----|:-----:|:------:|
| FB001 | 查看周度因子归因报告 | 自动化周报 | 高 | ⬜ |
| FB002 | 审查Spearman是否回正 | v2.9修复验证 | 高 | ⬜ |
| FB003 | 检查C8拦截有效性 | v2.9新增规则 | 中 | ⬜ |"

$lines += ""
$lines += "## 四、历史反馈追踪"
$lines += ""
$lines += "| 日期 | 建议 | 腰子决策 | 灰度结果 | 正式上线 |
|:-----|:-----|:--------|:--------|:-------:|
| $(Get-Date -Format 'yyyy-MM-dd') | 见上表 | ⬜ | — | — |"

$lines += ""
$lines += "---"
$lines += "> **流程**: 青山自动生成建议 → 腰子审核确认 → Claude执行参数变更 → 灰度3天 → 青山回检 → 腰子决定正式上线/回滚"

$report = $lines -join "`n"
if (-not $DryRun) {
    $report | Set-Content -Encoding UTF8 $outFile
    Write-Output "反馈建议已生成: $outFile"
} else {
    Write-Output $report
}
