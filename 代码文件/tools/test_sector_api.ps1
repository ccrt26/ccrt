# Sector API diagnostics
Set-ExecutionPolicy Bypass -Scope Process -Force

Write-Host "=== Test 1: Direct HTTP to push2 ==="
try {
    $r = Invoke-WebRequest -Uri "http://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=2&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f3&fs=m:90+t:2&fields=f2,f3,f4,f12,f14" -UseBasicParsing -TimeoutSec 10
    Write-Host ("OK Status={0} Length={1}" -f $r.StatusCode, $r.Content.Length)
} catch {
    $e = $_.Exception
    Write-Host ("FAIL: {0} | {1}" -f $e.GetType().Name, $e.Message)
    if ($e.InnerException) {
        Write-Host ("  Inner: {0} | {1}" -f $e.InnerException.GetType().Name, $e.InnerException.Message)
    }
}

Write-Host ""
Write-Host "=== Test 2: With different User-Agent ==="
try {
    $r = Invoke-WebRequest -Uri "http://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=2&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f3&fs=m:90+t:2&fields=f2,f3,f4,f12,f14" -UseBasicParsing -TimeoutSec 10 -Headers @{"User-Agent"="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    Write-Host ("OK Status={0} Length={1}" -f $r.StatusCode, $r.Content.Length)
} catch {
    $e = $_.Exception
    Write-Host ("FAIL: {0} | {1}" -f $e.GetType().Name, $e.Message)
}

Write-Host ""
Write-Host "=== Test 3: Alternative Eastmoney endpoint (nufm.dfcfw.com) ==="
try {
    $r = Invoke-WebRequest -Uri "http://nufm.dfcfw.com/EM_Finance2014NumericApplication/JS.aspx?type=CT&cmd=C._BKHY&sty=DCRRBK&st=(ChangePercent)&sr=-1&p=1&ps=5&token=7bc05d0d4c3c22ef9fca8c2a912d779c" -UseBasicParsing -TimeoutSec 10
    Write-Host ("OK Status={0} Length={1}" -f $r.StatusCode, $r.Content.Length)
} catch {
    $e = $_.Exception
    Write-Host ("FAIL: {0} | {1}" -f $e.GetType().Name, $e.Message)
}

Write-Host ""
Write-Host "=== Test 4: push2 with HTTPS ==="
try {
    $r = Invoke-WebRequest -Uri "https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=2&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f3&fs=m:90+t:2&fields=f2,f3,f4,f12,f14" -UseBasicParsing -TimeoutSec 10
    Write-Host ("OK Status={0} Length={1}" -f $r.StatusCode, $r.Content.Length)
} catch {
    $e = $_.Exception
    Write-Host ("FAIL: {0} | {1}" -f $e.GetType().Name, $e.Message)
}

Write-Host ""
Write-Host "=== Test 5: Test another Eastmoney API to see if it's push2-specific ==="
try {
    $r = Invoke-WebRequest -Uri "http://push2.eastmoney.com/api/qt/stock/get?secid=1.600584&fields=f43,f44,f45,f46,f47,f48,f50,f51,f52,f55,f57,f58,f60,f116,f117,f162,f167,f168,f169,f170,f171" -UseBasicParsing -TimeoutSec 10
    Write-Host ("OK Status={0} Length={1}" -f $r.StatusCode, $r.Content.Length)
} catch {
    $e = $_.Exception
    Write-Host ("FAIL: {0} | {1}" -f $e.GetType().Name, $e.Message)
}

Write-Host ""
Write-Host "=== Test 6: THS fallback script check ==="
$thsScript = "C:\Users\34269\Documents\Claude\股票分析\代码文件\每日荐股\scripts\modules\stock_data_fetcher_ths.py"
if (Test-Path $thsScript) {
    Write-Host ("THS script exists: {0}" -f $thsScript)
    try {
        $env:PYTHONIOENCODING = "utf-8"
        $result = & python $thsScript sector_ranking --top 3 2>&1
        Write-Host ("THS result type: {0}" -f $result.GetType().Name)
        Write-Host ("THS output: {0}" -f ($result -join "`n"))
    } catch {
        $e = $_.Exception
        Write-Host ("THS FAIL: {0} | {1}" -f $e.GetType().Name, $e.Message)
    }
} else {
    Write-Host "THS script NOT FOUND!"
}
