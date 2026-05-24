# Convert key stock HTML report to PDF using Edge headless
param(
    [string]$HtmlPath = "C:\Users\34269\Documents\Claude\股票分析\重点股票\汇总\重点股票分析报告_20260522.html",
    [string]$PdfPath = "C:\Users\34269\Documents\Claude\股票分析\重点股票\汇总\重点股票分析报告_20260522.pdf"
)

$edgePaths = @(
    "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "C:\Program Files\Microsoft\Edge\Application\msedge.exe"
)
$edge = $null
foreach ($p in $edgePaths) {
    if (Test-Path $p) { $edge = $p; break }
}

if (-not $edge) {
    Write-Error "Edge browser not found"
    exit 1
}

Write-Output "Found Edge: $edge"
$htmlFullPath = (Resolve-Path $HtmlPath).Path
$pdfDir = Split-Path $PdfPath -Parent
if (-not (Test-Path $pdfDir)) { New-Item -ItemType Directory -Path $pdfDir -Force | Out-Null }
$pdfFullPath = (Resolve-Path $pdfDir).Path + "\" + (Split-Path $PdfPath -Leaf)
$htmlUri = "file:///" + $htmlFullPath.Replace("\", "/")

Write-Output "Converting: $htmlUri -> $pdfFullPath"

$proc = Start-Process -FilePath $edge -ArgumentList @(
    "--headless",
    "--disable-gpu",
    "--print-to-pdf=$pdfFullPath",
    "--no-pdf-header-footer",
    $htmlUri
) -Wait -NoNewWindow -PassThru

Start-Sleep -Seconds 2

if (Test-Path $PdfPath) {
    $size = [math]::Round((Get-Item $PdfPath).Length / 1KB, 0)
    Write-Output "SUCCESS: PDF generated at $PdfPath ($size KB)"
} else {
    Write-Output "FAILED: PDF not created. Exit code: $($proc.ExitCode)"
    exit 1
}
