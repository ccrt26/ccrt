$edgePath = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
$tempHtml = "C:\temp\comparison_report.html"
$tempPdf = "C:\temp\comparison_report.pdf"
$uri = "file:///C:/temp/comparison_report.html"

try {
    $pi = Start-Process -FilePath $edgePath -ArgumentList @(
        "--headless", "--disable-gpu", "--no-sandbox",
        "--print-to-pdf=`"$tempPdf`"",
        "--print-to-pdf-no-header",
        "--no-pdf-header-footer",
        "--print-to-pdf-paper-size=A4",
        $uri
    ) -Wait -PassThru -NoNewWindow:$false
    Start-Sleep -Seconds 3
    if (Test-Path $tempPdf) {
        $size = (Get-Item $tempPdf).Length
        Write-Host "PDF generated: $size bytes"
    } else {
        Write-Host "PDF not found"
    }
} catch {
    Write-Host "Error: $_"
}
