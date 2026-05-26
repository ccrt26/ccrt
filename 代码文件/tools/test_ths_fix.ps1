. "$PSScriptRoot/../lib/init_encoding.ps1"
# Test THS fallback after path fix
Write-Host "=== Test THS sector_ranking via Python ==="
$thsPath = "C:\Users\34269\Documents\Claude\股票分析\代码文件\每日荐股\scripts\stock_data_fetcher_ths.py"
Write-Host ("Script exists: {0}" -f (Test-Path $thsPath))

try {
    $env:PYTHONIOENCODING = "utf-8"
    $result = & python $thsPath sector_ranking --top 5 2>&1
    Write-Host ("Result type: {0}" -f $result.GetType().Name)
    Write-Host ("Lines: {0}" -f $result.Count)
    Write-Host "Raw output:"
    Write-Host ($result -join "`n")
} catch {
    $e = $_.Exception
    Write-Host ("FAIL: {0} | {1}" -f $e.GetType().Name, $e.Message)
}

Write-Host ""
Write-Host "=== Test THS sector_fund_flow ==="
try {
    $env:PYTHONIOENCODING = "utf-8"
    $result = & python $thsPath sector_fund_flow --top 5 2>&1
    Write-Host ("Lines: {0}" -f $result.Count)
    Write-Host "Raw output (first 500 chars):"
    $text = $result -join " "
    Write-Host $text.Substring(0, [Math]::Min(500, $text.Length))
} catch {
    $e = $_.Exception
    Write-Host ("FAIL: {0} | {1}" -f $e.GetType().Name, $e.Message)
}
