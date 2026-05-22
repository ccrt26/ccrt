$rd = 'C:\Users\34269\Documents\Claude\gupiao_fenxi'
$ed = Join-Path $rd '重点股票/次日评估'
$f = Join-Path $ed '评估数据_20260522.json'
Write-Output "Path: $f"
Write-Output "Exists: $((Test-Path $f))"
if (Test-Path $f) {
    $d = Get-Content $f -Encoding UTF8 | ConvertFrom-Json
    Write-Output "Stocks: $($d.Stocks.Count)"
}
