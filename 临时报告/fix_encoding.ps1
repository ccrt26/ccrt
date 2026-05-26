$f = "c:\Users\34269\Documents\Claude\股票分析\代码文件\模拟交易\generate_dashboard.ps1"
$c = [System.IO.File]::ReadAllText($f)
[System.IO.File]::WriteAllText($f, $c, [System.Text.UTF8Encoding]::new($true))
Write-Host "Done"
