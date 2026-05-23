param($HtmlFile)

$pdf = Join-Path $env:TEMP "test_real_report.pdf"
if (Test-Path $pdf) { Remove-Item $pdf -Force }

$edge = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
$uri = "file:///" + $HtmlFile.Replace('\', '/')

Write-Host "HTML: $HtmlFile ($((Get-Item $HtmlFile).Length) bytes)"
Write-Host "URI: $uri"

$p = Start-Process -FilePath $edge -ArgumentList @(
    "--headless=new", "--disable-gpu", "--no-sandbox",
    "--print-to-pdf=$pdf",
    "--no-pdf-header-footer",
    $uri
) -Wait -PassThru -NoNewWindow

Write-Host "Exit code: $($p.ExitCode)"
if (Test-Path $pdf) {
    $size = (Get-Item $pdf).Length
    Write-Host "PDF size: $size bytes"
    if ($size -lt 30000) {
        Write-Host "PDF TOO SMALL - content:"
        Get-Content $pdf -Raw
    }
} else {
    Write-Host "PDF NOT created"
}
