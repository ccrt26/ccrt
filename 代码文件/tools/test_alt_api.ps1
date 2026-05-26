. "$PSScriptRoot/../lib/init_encoding.ps1"
# Test alternative sector data sources
Write-Host "=== Test: nufm.dfcfw.com sector data format ==="
try {
    $r = Invoke-WebRequest -Uri "http://nufm.dfcfw.com/EM_Finance2014NumericApplication/JS.aspx?type=CT&cmd=C._BKHY&sty=DCRRBK&st=(ChangePercent)&sr=-1&p=1&ps=3&token=7bc05d0d4c3c22ef9c8a2d912d779c" -UseBasicParsing -TimeoutSec 10
    Write-Host ("Status={0} Length={1}" -f $r.StatusCode, $r.Content.Length)
    Write-Host "First 800 chars:"
    Write-Host $r.Content.Substring(0, [Math]::Min(800, $r.Content.Length))
} catch {
    $e = $_.Exception
    Write-Host ("FAIL: {0} | {1}" -f $e.GetType().Name, $e.Message)
}

Write-Host ""
Write-Host "=== Test: THS fallback (correct path) ==="
$thsPath = "C:\Users\34269\Documents\Claude\股票分析\代码文件\每日荐股\scripts\stock_data_fetcher_ths.py"
try {
    $env:PYTHONIOENCODING = "utf-8"
    $output = cmd /c "python `"$thsPath`" sector_ranking --top 3 2>&1"
    Write-Host ("THS output ({0} lines):" -f $output.Count)
    Write-Host ($output -join "`n")
} catch {
    $e = $_.Exception
    Write-Host ("THS FAIL: {0} | {1}" -f $e.GetType().Name, $e.Message)
}

Write-Host ""
Write-Host "=== Test: core.ps1 $PSScriptRoot value ==="
$corePath = "C:\Users\34269\Documents\Claude\股票分析\代码文件\每日荐股\scripts\modules\core.ps1"
$moduleDir = Split-Path $corePath -Parent
Write-Host ("modules dir: {0}" -f $moduleDir)
$thsFromCore = Join-Path $moduleDir "stock_data_fetcher_ths.py"
Write-Host ("THS path from core logic: {0}" -f $thsFromCore)
Write-Host ("Exists: {0}" -f (Test-Path $thsFromCore))
$correctPath = Join-Path (Split-Path $moduleDir -Parent) "stock_data_fetcher_ths.py"
Write-Host ("Correct path: {0}" -f $correctPath)
Write-Host ("Exists: {0}" -f (Test-Path $correctPath))
