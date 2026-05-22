$edge = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
$reportDir = "C:\Users\34269\Documents\Claude\股票分析\临时报告"
$htmlFile = Join-Path $reportDir "v2.3_v1.5_evaluation_report.html"
$pdfFile  = Join-Path $reportDir "v2.3_v1.5_evaluation_report.pdf"
$absPath = $htmlFile.Replace("\", "/")
$uri = "file:///" + $absPath

Write-Host "Edge: $edge"
Write-Host "HTML: $htmlFile"
Write-Host "URI:  $uri"
Write-Host "PDF:  $pdfFile"
Write-Host ""

if (-not (Test-Path $edge)) { Write-Error "Edge not found"; exit 1 }
if (-not (Test-Path $htmlFile)) { Write-Error "HTML not found"; exit 1 }

Write-Host "Generating PDF..."
& $edge --headless --disable-gpu --no-sandbox --disable-software-rasterizer --print-to-pdf="$pdfFile" --no-pdf-header-footer --print-to-pdf-margin-bottom=10 --print-to-pdf-margin-top=10 --print-to-pdf-paper-size=A4 $uri 2>&1 | Out-Null
Start-Sleep -Seconds 3

if (Test-Path $pdfFile) {
    $sz = (Get-Item $pdfFile).Length
    if ($sz -lt 5000) {
        Write-Error "PDF too small: $sz bytes"
        exit 1
    }
    Write-Host "SUCCESS: PDF generated at $pdfFile ($sz bytes)"
} else {
    Write-Error "FAILED: PDF not generated at $pdfFile"
    exit 1
}
