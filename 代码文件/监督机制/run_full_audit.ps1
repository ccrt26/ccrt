<#
.SYNOPSIS
  铁律量化 · 综合审计脚本 (Phase 1: Section A~G)
.DESCRIPTION
  四级审计体系 — 第四级技术健康审计的完整实现。
  9大板块 ~55项检查，全部确定性 pass/warn/fail。
  只读不写，输出 JSON 到 历史数据/audit_report_YYYYMMDD.json。
.PARAMETER Quick
  快速模式：仅 Section A子集 + F + G，约5秒
.PARAMETER Date
  审计日期标签，默认今天
.EXAMPLE
  .\run_full_audit.ps1              完整审计
  .\run_full_audit.ps1 -Quick       快速日检
  .\run_full_audit.ps1 -Date 2026-05-23
.NOTES
  版本: v1.1 | 2026-05-24 | 审计官: 旧影
  变更: v1.1 — 拆分为 core/sections 两子模块，$rootDir 改为 $PSScriptRoot 相对路径
#>

param(
    [switch]$Quick,
    [string]$Date = (Get-Date -Format "yyyy-MM-dd")
)

# $PSScriptRoot = 代码文件/监督机制/，上溯2级到项目根
$rootDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

# Dot-source 子模块
. "$PSScriptRoot/modules/audit_core.ps1"
. "$PSScriptRoot/modules/audit_sections.ps1"

# ============================================================
# 汇总
# ============================================================
$allPass = 0; $allWarn = 0; $allFail = 0
foreach ($v in $script:results.Values) {
    if ($v.status -eq 'PASS') { $allPass++ }
    elseif ($v.status -eq 'WARN') { $allWarn++ }
    elseif ($v.status -eq 'FAIL') { $allFail++ }
}
$total = $allPass + $allWarn + $allFail

if ($allFail -eq 0 -and $allWarn -le 5) { $verdict = "PASS" }
elseif ($allFail -le 2) { $verdict = "WARN" }
else { $verdict = "FAIL" }

# 按Section分组
$sectionGroups = @{}
foreach ($v in $script:results.Values) {
    $sec = $v.section
    if (-not $sectionGroups.ContainsKey($sec)) {
        $sectionGroups[$sec] = @{ section = $sec; pass = 0; warn = 0; fail = 0 }
    }
    if ($v.status -eq 'PASS') { $sectionGroups[$sec].pass++ }
    elseif ($v.status -eq 'WARN') { $sectionGroups[$sec].warn++ }
    elseif ($v.status -eq 'FAIL') { $sectionGroups[$sec].fail++ }
}
$sections = @($sectionGroups.Values)

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  审计结论: $verdict" -ForegroundColor $(if($verdict -eq 'PASS'){'Green'}elseif($verdict -eq 'WARN'){'Yellow'}else{'Red'})
Write-Host "  总计: $total | PASS: $allPass | WARN: $allWarn | FAIL: $allFail" -ForegroundColor White
Write-Host "========================================" -ForegroundColor Cyan

if ($script:failures.Count -gt 0) {
    Write-Host "`n❌ FAIL 项:" -ForegroundColor Red
    $script:failures | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
    Write-Host ""
    Write-Host "⛔ =======================================" -ForegroundColor Red
    Write-Host "  审计状态: 未关闭 (OPEN)" -ForegroundColor Red
    Write-Host "  仍有 $($script:failures.Count) 项 FAIL 未修复，禁止关闭此审计。" -ForegroundColor Red
    Write-Host "  旧影必须汇报阿黑 → 修复 → 重新审计 → 验证通过。" -ForegroundColor Red
    Write-Host "⛔ =======================================" -ForegroundColor Red
}
if ($script:warnings.Count -gt 0) {
    Write-Host "`n⚠ WARN 项:" -ForegroundColor Yellow
    $script:warnings | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
}

# P1-4: 错误案例库 — FAIL项自动入库
if ($script:failures.Count -gt 0) {
    $errLibFile = Join-Path $rootDir ".claude\knowledge\常见错误.md"
    if (Test-Path $errLibFile) {
        $entry = "`n### $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') — 审计失败`n"
        foreach ($f in $script:failures) {
            $entry += "- $f`n"
        }
        $entry += "`n**标签**: #数据  `n**审计模式**: $(if ($Quick) {'Quick'} else {'Full'})`n`n---`n"
        Add-Content -Path $errLibFile -Value $entry -Encoding UTF8
        Write-Host "`n📝 错误案例库已更新: $errLibFile" -ForegroundColor DarkGray
    }
}

# ---- 输出 JSON ----
$reportOutDir = Join-Path $rootDir "历史数据\审计报告"
$dateNum = $Date -replace '-',''
$auditStatus = if ($allFail -gt 0) { "open" } else { "closed" }
$reportSummary = @{
    overall_verdict = $verdict
    total_checks = $total
    pass = $allPass
    warn = $allWarn
    fail = $allFail
    sections = $sections
    audit_status = $auditStatus
}
$report = @{
    audit = @{
        version = "1.0"
        timestamp = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
        date = $dateNum
        mode = if ($Quick) { "quick" } else { "full" }
    }
    summary = $reportSummary
    failures = @($script:failures)
    warnings = @($script:warnings)
    metrics = $script:metrics
    checks = @($script:results.Values | ForEach-Object {
        @{ section = $_.section; id = $_.id; desc = $_.desc; status = $_.status; detail = $_.detail }
    })
}

if (-not (Test-Path $reportOutDir)) { New-Item -ItemType Directory -Path $reportOutDir -Force | Out-Null }
$reportFile = Join-Path $reportOutDir "audit_report_${dateNum}.json"
if ($Quick) { $reportFile = Join-Path $reportOutDir "audit_report_${dateNum}_quick.json" }
$report | ConvertTo-Json -Depth 4 | Out-File $reportFile -Encoding UTF8 -Force
Write-Host "`n报告已保存: $reportFile" -ForegroundColor Gray

# ---- 生成 PDF 版本 ----
$supervisorDir = Join-Path $rootDir "代码文件\监督机制"
$pdfScript = Join-Path $supervisorDir "generate_audit_pdf.py"
if (Test-Path $pdfScript) {
    try {
        $pdfResult = python $pdfScript $reportFile 2>&1 | Out-String
        if ($LASTEXITCODE -le 2) {
            $pdfFile = Join-Path $reportOutDir ("audit_report_${dateNum}" + $(if($Quick){'_quick'}) + ".pdf")
            Write-Host "PDF已生成: $pdfFile" -ForegroundColor Gray
        } else {
            Write-Host "PDF生成异常: $pdfResult" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "PDF生成失败: $_" -ForegroundColor Yellow
    }
} else {
    Write-Host "PDF生成脚本不可用，跳过" -ForegroundColor Yellow
}

# 退出码
if ($allFail -gt 0) { exit 1 } else { exit 0 }
