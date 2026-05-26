$rootDir = "c:\Users\34269\Documents\Claude\股票分析"
$analysisScript = Join-Path $rootDir "代码文件\重点股票\run_keystock_analysis.ps1"
Write-Host "Script path: $analysisScript"
Write-Host "Exists: $(Test-Path $analysisScript)"
if (Test-Path $analysisScript) {
    & $analysisScript -Date "20260525" -TargetStocks "601689","600114","301075"
} else {
    Write-Error "Script not found"
}
