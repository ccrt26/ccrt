# P2-2: 数据质量仪表盘 — 从审计JSON生成HTML趋势图
param(
    [string]$RootDir = "",
    [string]$OutputFile = ""
)
. "$PSScriptRoot/../lib/init_encoding.ps1"
if (-not $RootDir) { $RootDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot) }
if (-not $OutputFile) { $OutputFile = Join-Path $RootDir "历史数据\03_分析报告\quality_dashboard.html" }

$auditDir = Join-Path $RootDir "历史数据\审计报告"
if (-not (Test-Path $auditDir)) {
    Write-Host "审计报告目录不存在: $auditDir" -ForegroundColor Yellow
    exit 0
}

$reports = Get-ChildItem $auditDir -Filter "audit_report_*.json" | Sort-Object Name
if ($reports.Count -eq 0) {
    Write-Host "暂无审计报告JSON" -ForegroundColor Yellow
    exit 0
}

$rows = @()
foreach ($rpt in $reports) {
    try {
        $data = Get-Content $rpt.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
        $rows += [PSCustomObject]@{
            Date = if ($data.date) { $data.date } else { $rpt.BaseName -replace 'audit_report_','' }
            Verdict = if ($data.overall_verdict) { $data.overall_verdict } else { "N/A" }
            Total = [int]($data.total_checks -as [int])
            Pass = [int]($data.pass -as [int])
            Warn = [int]($data.warn -as [int])
            Fail = [int]($data.fail -as [int])
        }
    } catch {}
}

if ($rows.Count -eq 0) { Write-Host "无有效审计数据" -ForegroundColor Yellow; exit 0 }

# HTML生成
$totalRuns = $rows.Count
$passRuns = ($rows | Where-Object { $_.Fail -eq 0 }).Count
$totalChecks = ($rows | Measure-Object -Property Total -Sum).Sum
$totalPassed = ($rows | Measure-Object -Property Pass -Sum).Sum
$totalFail = ($rows | Measure-Object -Property Fail -Sum).Sum
$passRate = if ($totalChecks -gt 0) { [Math]::Round($totalPassed / $totalChecks * 100, 1) } else { 0 }

$tableRows = ""
foreach ($r in ($rows | Sort-Object Date -Descending)) {
    $color = if ($r.Fail -gt 0) { "#e74c3c" } elseif ($r.Warn -gt 0) { "#f39c12" } else { "#27ae60" }
    $tableRows += "<tr style='border-bottom:1px solid #333'><td>$($r.Date)</td><td style='color:$color;font-weight:bold'>$($r.Verdict)</td><td>$($r.Total)</td><td style='color:#27ae60'>$($r.Pass)</td><td style='color:#f39c12'>$($r.Warn)</td><td style='color:#e74c3c'>$($r.Fail)</td></tr>`n"
}

$html = @"
<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>铁律量化 · 数据质量仪表盘</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',system-ui,sans-serif;background:#1a1a2e;color:#e0e0e0;padding:20px}
h1{color:#e0e0e0;margin-bottom:15px;font-size:1.6em}
.cards{display:flex;gap:15px;margin-bottom:25px;flex-wrap:wrap}
.card{background:#16213e;border-radius:10px;padding:18px 22px;min-width:140px;flex:1}
.card .num{font-size:2em;font-weight:bold}
.card .label{font-size:0.8em;color:#888;margin-top:4px}
table{width:100%;border-collapse:collapse;background:#16213e;border-radius:8px;overflow:hidden}
th{background:#0f3460;padding:10px 14px;text-align:left;font-size:0.85em;color:#aaa}
td{padding:9px 14px;font-size:0.9em}
.footer{color:#666;font-size:0.75em;margin-top:20px}
</style></head>
<body>
<h1>铁律量化 · 数据质量仪表盘</h1>
<div class="cards">
<div class="card"><div class="num" style="color:#e0e0e0">$totalRuns</div><div class="label">审计次数</div></div>
<div class="card"><div class="num" style="color:#27ae60">$passRuns</div><div class="label">通过轮次</div></div>
<div class="card"><div class="num" style="color:#e0e0e0">$passRate%</div><div class="label">总通过率</div></div>
<div class="card"><div class="num" style="color:#27ae60">$totalPassed</div><div class="label">PASS项</div></div>
<div class="card"><div class="num" style="color:#e74c3c">$totalFail</div><div class="label">FAIL项</div></div>
</div>
<table>
<tr><th>日期</th><th>结论</th><th>总检查</th><th>PASS</th><th>WARN</th><th>FAIL</th></tr>
$tableRows
</table>
<div class="footer">铁律量化 · 数据质量仪表盘 · 自动生成于 $(Get-Date -Format 'yyyy-MM-dd HH:mm')</div>
</body></html>
"@

$outDir = Split-Path -Parent $OutputFile
if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir -Force | Out-Null }
[System.IO.File]::WriteAllText($OutputFile, $html, [System.Text.UTF8Encoding]::new($false))
Write-Host "质量仪表盘已生成: $OutputFile ($totalRuns 次审计, 通过率 $passRate%)"
