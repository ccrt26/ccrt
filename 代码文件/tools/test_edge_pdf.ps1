# Test Edge headless PDF conversion
param($HtmlFile, $PdfFile)

$edgePath = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if (-not (Test-Path $edgePath)) {
    $edgePath = "C:\Program Files\Microsoft\Edge\Application\msedge.exe"
}

Write-Host "Edge path: $edgePath"
Write-Host "Exists: $(Test-Path $edgePath)"

$ver = (Get-Item $edgePath).VersionInfo.ProductVersion
Write-Host "Edge version: $ver"

if (-not $HtmlFile) {
    # Try with a simple test HTML
    $HtmlFile = Join-Path $env:TEMP "test_edge.html"
    "<html><body><h1>Test PDF</h1><p>Hello world</p></body></html>" | Set-Content $HtmlFile -Encoding UTF8
    $PdfFile = Join-Path $env:TEMP "test_edge.pdf"
}

Write-Host "HTML: $HtmlFile ($((Get-Item $HtmlFile).Length) bytes)"
Write-Host "PDF target: $PdfFile"

# Remove old PDF
if (Test-Path $PdfFile) { Remove-Item $PdfFile -Force }

# Test 1: old --headless
Write-Host "`n=== Test 1: --headless (old) ==="
$uri = "file:///$($HtmlFile.Replace('\','/'))"
$args1 = @("--headless", "--disable-gpu", "--no-sandbox", "--print-to-pdf=$PdfFile", "--no-pdf-header-footer", $uri)
Write-Host "Args: $($args1 -join ' ')"
$p1 = Start-Process -FilePath $edgePath -ArgumentList $args1 -Wait -PassThru -NoNewWindow
Write-Host "Exit code: $($p1.ExitCode)"
if (Test-Path $PdfFile) { Write-Host "PDF size: $((Get-Item $PdfFile).Length) bytes" } else { Write-Host "PDF NOT created" }

# Remove for test 2
if (Test-Path $PdfFile) { Remove-Item $PdfFile -Force }

# Test 2: --headless=new
Write-Host "`n=== Test 2: --headless=new ==="
$args2 = @("--headless=new", "--disable-gpu", "--no-sandbox", "--print-to-pdf=$PdfFile", "--no-pdf-header-footer", $uri)
Write-Host "Args: $($args2 -join ' ')"
$p2 = Start-Process -FilePath $edgePath -ArgumentList $args2 -Wait -PassThru -NoNewWindow
Write-Host "Exit code: $($p2.ExitCode)"
if (Test-Path $PdfFile) { Write-Host "PDF size: $((Get-Item $PdfFile).Length) bytes" } else { Write-Host "PDF NOT created" }
