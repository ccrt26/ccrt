# 铁律量化 - 报告输出完整性验证脚本
# PowerShell -File 执行，UTF-8 BOM 编码
param(
    [string]$ReportDir,
    [string]$Date = (Get-Date).ToString("yyyyMMdd"),
    [int]$MinPdfSizeKB = 50
)

$rootDir = "C:\Users\34269\Documents\Claude\股票分析"
$reportRoot = Join-Path $rootDir $ReportDir

if (-not (Test-Path $reportRoot)) {
    Write-Error "[VERIFY] 报告目录不存在: $reportRoot"
    exit 1
}

Write-Host "=== 报告输出完整性验证 ===" -ForegroundColor Cyan
Write-Host "目录: $reportRoot"
Write-Host "日期: $Date`n"

$allPassed = $true
$stockDirs = Get-ChildItem $reportRoot -Directory

if ($stockDirs.Count -eq 0) {
    $htmlFiles = Get-ChildItem $reportRoot -Filter "*${Date}*.html" -ErrorAction SilentlyContinue
    $pdfFiles = Get-ChildItem $reportRoot -Filter "*${Date}*.pdf" -ErrorAction SilentlyContinue
    if ($htmlFiles.Count -eq 0) { Write-Host "  [FAIL] HTML 未找到" -ForegroundColor Red; $allPassed = $false }
    else { foreach ($f in $htmlFiles) { Write-Host "  [PASS] HTML: $($f.Name)" -ForegroundColor Green } }
    if ($pdfFiles.Count -eq 0) { Write-Host "  [FAIL] PDF 未找到" -ForegroundColor Red; $allPassed = $false }
    else {
        foreach ($f in $pdfFiles) {
            $sizeOk = $f.Length -gt ($MinPdfSizeKB * 1KB)
            $tag = if ($sizeOk) { "PASS" } else { "FAIL" }
            $color = if ($sizeOk) { "Green" } else { "Red" }
            Write-Host "  [$tag] PDF: $($f.Name) ($([Math]::Round($f.Length/1KB,0)) KB)" -ForegroundColor $color
            if (-not $sizeOk) { $allPassed = $false }
        }
    }
} else {
    foreach ($dir in $stockDirs) {
        Write-Host "[$($dir.Name)]" -ForegroundColor Yellow
        $htmlFiles = Get-ChildItem $dir.FullName -Filter "*${Date}*.html" -ErrorAction SilentlyContinue
        $pdfFiles = Get-ChildItem $dir.FullName -Filter "*${Date}*.pdf" -ErrorAction SilentlyContinue
        if ($htmlFiles.Count -eq 0) { Write-Host "  [FAIL] HTML 未找到" -ForegroundColor Red; $allPassed = $false }
        else { foreach ($f in $htmlFiles) { Write-Host "  [PASS] HTML: $($f.Name)" -ForegroundColor Green } }
        if ($pdfFiles.Count -eq 0) { Write-Host "  [FAIL] PDF 未找到" -ForegroundColor Red; $allPassed = $false }
        else {
            foreach ($f in $pdfFiles) {
                $sizeOk = $f.Length -gt ($MinPdfSizeKB * 1KB)
                $tag = if ($sizeOk) { "PASS" } else { "FAIL" }
                $color = if ($sizeOk) { "Green" } else { "Red" }
                Write-Host "  [$tag] PDF: $($f.Name) ($([Math]::Round($f.Length/1KB,0)) KB)" -ForegroundColor $color
                if (-not $sizeOk) { $allPassed = $false }
            }
        }
        Write-Host ""
    }
}

if ($allPassed) { Write-Host "结果: 全部通过" -ForegroundColor Green; exit 0 }
else { Write-Host "结果: 存在失败项目" -ForegroundColor Red; exit 1 }
